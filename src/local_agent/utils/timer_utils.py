#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Timer Utility Class - Globally available scheduled task management
Provides single and recurring timer functionality, supports asynchronous operations and task management
"""

import asyncio
import time
import threading
from typing import Callable, Any, Optional, Dict, Union
from dataclasses import dataclass
from enum import Enum

from ..logger import get_logger

logger = get_logger(__name__)


class TimerType(Enum):
    """Timer type enumeration"""
    SINGLE = "single"      # Single timer
    INTERVAL = "interval"  # Loop timer


@dataclass
class TimerTask:
    """Timer task data structure"""
    id: str                    # Task ID
    timer_type: TimerType      # Timer type
    callback: Callable         # Callback function
    interval: float            # Interval time (seconds)
    delay: float               # Delay time (seconds)
    args: tuple                # Positional arguments
    kwargs: Dict[str, Any]     # Keyword arguments
    created_time: float        # Creation time
    last_run_time: Optional[float] = None  # Last run time
    run_count: int = 0         # Run count
    is_running: bool = False   # Whether running
    is_cancelled: bool = False # Whether cancelled


class TimerManager:
    """Timer manager - global singleton"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._tasks: Dict[str, TimerTask] = {}
            self._lock = threading.RLock()
            self._running = False
            self._main_thread: Optional[threading.Thread] = None
            self._initialized = True
            logger.info("Timer manager initialized")
    
    def start(self) -> bool:
        """Start timer manager"""
        with self._lock:
            if self._running:
                logger.warning("Timer manager is already running")
                return True
            
            self._running = True
            self._main_thread = threading.Thread(
                target=self._run_loop, 
                daemon=True,
                name="TimerManagerLoop"
            )
            self._main_thread.start()
            logger.info("Timer manager started successfully")
            return True
    
    def stop(self) -> bool:
        """Stop timer manager"""
        with self._lock:
            if not self._running:
                logger.warning("Timer manager is not running")
                return True
            
            self._running = False
            
            # Cancel all tasks
            task_ids = list(self._tasks.keys())
            for task_id in task_ids:
                self.cancel_task(task_id)
            
            logger.info("Timer manager stopped")
            return True
    
    def _run_loop(self) -> None:
        """Timer main loop"""
        logger.debug("Timer manager main loop started")
        
        while self._running:
            try:
                current_time = time.time()
                
                with self._lock:
                    # Check all tasks if they need to execute
                    for task_id, task in list(self._tasks.items()):
                        if task.is_cancelled:
                            continue
                        
                        # Calculate when the task should execute
                        if task.last_run_time is None:
                            # First run, check if delay time is reached
                            should_run_time = task.created_time + task.delay
                        else:
                            # Subsequent runs, check if interval time is reached
                            should_run_time = task.last_run_time + task.interval
                        
                        if current_time >= should_run_time:
                            # Execute task
                            self._execute_task(task)
                
                # Sleep for a while to avoid high CPU usage
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Timer loop exception: {e}")
                time.sleep(1)
        
        logger.debug("Timer manager main loop ended")
    
    def _execute_task(self, task: TimerTask) -> None:
        """Execute scheduled task"""
        if task.is_running or task.is_cancelled:
            return
        
        task.is_running = True
        task.last_run_time = time.time()
        
        def run_task():
            """Run task in separate thread"""
            try:
                logger.debug(f"Executing timer task: {task.id}")
                
                # Check if it's an asynchronous function
                if asyncio.iscoroutinefunction(task.callback):
                    # Asynchronous function needs to create event loop in new thread
                    try:
                        # Try to get current thread's event loop
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        # If no event loop, create new one
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Run asynchronous function
                    loop.run_until_complete(task.callback(*task.args, **task.kwargs))
                else:
                    # Synchronous function directly call
                    task.callback(*task.args, **task.kwargs)
                
                task.run_count += 1
                
                # If it's a single timer, cancel after successful execution
                if task.timer_type == TimerType.SINGLE:
                    self.cancel_task(task.id)
                    
            except Exception as e:
                logger.error(f"Timer task execution failed [{task.id}]: {e}")
                if task.timer_type == TimerType.SINGLE:
                    self.cancel_task(task.id)
            finally:
                task.is_running = False
        
        # Execute task in new thread
        thread = threading.Thread(target=run_task, daemon=True, name=f"TimerTask-{task.id}")
        thread.start()
    
    def add_single_timer(self, 
                        delay: float, 
                        callback: Callable, 
                        task_id: Optional[str] = None,
                        *args, **kwargs) -> str:
        """
        Add single timer
        
        Args:
            delay: Delay time (seconds)
            callback: Callback function
            task_id: Task ID (optional, auto-generated)
            *args: Callback function positional arguments
            **kwargs: Callback function keyword arguments
            
        Returns:
            str: Task ID
        """
        if task_id is None:
            task_id = f"single_{int(time.time() * 1000)}_{len(self._tasks)}"
        
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"Task ID already exists: {task_id}")
            
            task = TimerTask(
                id=task_id,
                timer_type=TimerType.SINGLE,
                callback=callback,
                interval=0,  # Single timer doesn't use interval
                delay=delay,
                args=args,
                kwargs=kwargs,
                created_time=time.time()
            )
            
            self._tasks[task_id] = task
            logger.info(f"Added single timer: {task_id}, delay: {delay} seconds")
            
            # Ensure timer manager is running
            if not self._running:
                self.start()
            
            return task_id
    
    def add_interval_timer(self, 
                          interval: float, 
                          callback: Callable, 
                          delay: float = 0,
                          task_id: Optional[str] = None,
                          *args, **kwargs) -> str:
        """
        Add interval timer
        
        Args:
            interval: Interval time (seconds)
            callback: Callback function
            delay: First execution delay time (seconds, default 0)
            task_id: Task ID (optional, auto-generated)
            *args: Callback function positional arguments
            **kwargs: Callback function keyword arguments
            
        Returns:
            str: Task ID
        """
        if task_id is None:
            task_id = f"interval_{int(time.time() * 1000)}_{len(self._tasks)}"
        
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"Task ID already exists: {task_id}")
            
            task = TimerTask(
                id=task_id,
                timer_type=TimerType.INTERVAL,
                callback=callback,
                interval=interval,
                delay=delay,
                args=args,
                kwargs=kwargs,
                created_time=time.time()
            )
            
            self._tasks[task_id] = task
            logger.info(f"Added interval timer: {task_id}, interval: {interval} seconds, delay: {delay} seconds")
            
            # Ensure timer manager is running
            if not self._running:
                self.start()
            
            return task_id
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel scheduled task"""
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Cancel task failed: Task ID does not exist - {task_id}")
                return False
            
            task = self._tasks[task_id]
            task.is_cancelled = True
            del self._tasks[task_id]
            logger.info(f"Cancelled timer task: {task_id}")
            return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        with self._lock:
            if task_id not in self._tasks:
                return None
            
            task = self._tasks[task_id]
            return {
                'id': task.id,
                'type': task.timer_type.value,
                'interval': task.interval,
                'delay': task.delay,
                'created_time': task.created_time,
                'last_run_time': task.last_run_time,
                'run_count': task.run_count,
                'is_running': task.is_running,
                'is_cancelled': task.is_cancelled
            }
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all task statuses"""
        with self._lock:
            return {
                task_id: self.get_task_status(task_id)
                for task_id in self._tasks.keys()
            }
    
    def clear_all_tasks(self) -> int:
        """Clear all scheduled tasks"""
        with self._lock:
            count = len(self._tasks)
            task_ids = list(self._tasks.keys())
            
            for task_id in task_ids:
                self.cancel_task(task_id)
            
            logger.info(f"Cleared all timer tasks, total: {count}")
            return count


# Global timer manager instance
_timer_manager = TimerManager()


def set_timeout(delay: float, callback: Callable, *args, **kwargs) -> str:
    """
    Set single timer (similar to JavaScript's setTimeout)
    
    Args:
        delay: Delay time (seconds)
        callback: Callback function
        *args: Callback function positional arguments
        **kwargs: Callback function keyword arguments
        
    Returns:
        str: Task ID, can be used to cancel timer
    """
    return _timer_manager.add_single_timer(delay, callback, None, *args, **kwargs)


def set_interval(interval: float, callback: Callable, delay: float = 0, *args, **kwargs) -> str:
    """
    Set interval timer (similar to JavaScript's setInterval)
    
    Args:
        interval: Interval time (seconds)
        callback: Callback function
        delay: First execution delay time (seconds, default 0)
        *args: Callback function positional arguments
        **kwargs: Callback function keyword arguments
        
    Returns:
        str: Task ID, can be used to cancel timer
    """
    return _timer_manager.add_interval_timer(interval, callback, delay, None, *args, **kwargs)


def clear_timeout(task_id: str) -> bool:
    """Cancel single timer"""
    return _timer_manager.cancel_task(task_id)


def clear_interval(task_id: str) -> bool:
    """Cancel interval timer"""
    return _timer_manager.cancel_task(task_id)


def get_timer_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get timer status"""
    return _timer_manager.get_task_status(task_id)


def get_all_timers() -> Dict[str, Dict[str, Any]]:
    """Get all timer statuses"""
    return _timer_manager.get_all_tasks()


def clear_all_timers() -> int:
    """Clear all timers"""
    return _timer_manager.clear_all_tasks()


def start_timer_manager() -> bool:
    """Start timer manager"""
    return _timer_manager.start()


def stop_timer_manager() -> bool:
    """Stop timer manager"""
    return _timer_manager.stop()


# Asynchronous version timer functions (using asyncio)

async def async_set_timeout(delay: float, callback: Callable, *args, **kwargs) -> str:
    """Asynchronously set single timer"""
    
    async def async_callback():
        if asyncio.iscoroutinefunction(callback):
            await callback(*args, **kwargs)
        else:
            # Synchronous function runs in asynchronous environment
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, *args, **kwargs)
    
    return _timer_manager.add_single_timer(delay, async_callback, None)


async def async_set_interval(interval: float, callback: Callable, delay: float = 0, *args, **kwargs) -> str:
    """Asynchronously set interval timer"""
    
    async def async_callback():
        if asyncio.iscoroutinefunction(callback):
            await callback(*args, **kwargs)
        else:
            # Synchronous function runs in asynchronous environment
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, *args, **kwargs)
    
    return _timer_manager.add_interval_timer(interval, async_callback, delay, None)


# Convenient decorator version

def timeout(delay: float):
    """Single timer decorator"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            return set_timeout(delay, func, *args, **kwargs)
        return wrapper
    return decorator


def interval(interval: float, delay: float = 0):
    """Interval timer decorator"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            return set_interval(interval, func, delay, None, *args, **kwargs)
        return wrapper
    return decorator