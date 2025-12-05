#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时器工具类 - 全局可用的定时任务管理
提供单次定时和循环定时的功能，支持异步操作和任务管理
"""

import asyncio
import time
import threading
from typing import Callable, Any, Optional, Dict, Union
from dataclasses import dataclass
from enum import Enum

# 使用项目统一日志系统
from ..logger import get_logger

logger = get_logger(__name__)


class TimerType(Enum):
    """定时器类型枚举"""
    SINGLE = "single"      # 单次定时器
    INTERVAL = "interval"  # 循环定时器


@dataclass
class TimerTask:
    """定时任务数据结构"""
    id: str                    # 任务ID
    timer_type: TimerType      # 定时器类型
    callback: Callable         # 回调函数
    interval: float            # 间隔时间（秒）
    delay: float               # 延迟时间（秒）
    args: tuple                # 位置参数
    kwargs: Dict[str, Any]     # 关键字参数
    created_time: float        # 创建时间
    last_run_time: Optional[float] = None  # 最后运行时间
    run_count: int = 0         # 运行次数
    is_running: bool = False   # 是否正在运行
    is_cancelled: bool = False # 是否已取消


class TimerManager:
    """定时器管理器 - 全局单例"""
    
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
            logger.info("定时器管理器初始化完成")
    
    def start(self) -> bool:
        """启动定时器管理器"""
        with self._lock:
            if self._running:
                logger.warning("定时器管理器已在运行中")
                return True
            
            self._running = True
            self._main_thread = threading.Thread(
                target=self._run_loop, 
                daemon=True,
                name="TimerManagerLoop"
            )
            self._main_thread.start()
            logger.info("定时器管理器启动成功")
            return True
    
    def stop(self) -> bool:
        """停止定时器管理器"""
        with self._lock:
            if not self._running:
                logger.warning("定时器管理器未运行")
                return True
            
            self._running = False
            
            # 取消所有任务
            task_ids = list(self._tasks.keys())
            for task_id in task_ids:
                self.cancel_task(task_id)
            
            logger.info("定时器管理器已停止")
            return True
    
    def _run_loop(self) -> None:
        """定时器主循环"""
        logger.debug("定时器管理器主循环启动")
        
        while self._running:
            try:
                current_time = time.time()
                
                with self._lock:
                    # 检查所有任务是否需要执行
                    for task_id, task in list(self._tasks.items()):
                        if task.is_cancelled:
                            continue
                        
                        # 计算任务应该执行的时间
                        if task.last_run_time is None:
                            # 第一次运行，检查是否达到延迟时间
                            should_run_time = task.created_time + task.delay
                        else:
                            # 后续运行，检查是否达到间隔时间
                            should_run_time = task.last_run_time + task.interval
                        
                        if current_time >= should_run_time:
                            # 执行任务
                            self._execute_task(task)
                
                # 休眠一段时间，避免CPU占用过高
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"定时器循环异常: {e}")
                time.sleep(1)
        
        logger.debug("定时器管理器主循环结束")
    
    def _execute_task(self, task: TimerTask) -> None:
        """执行定时任务"""
        if task.is_running or task.is_cancelled:
            return
        
        task.is_running = True
        task.last_run_time = time.time()
        
        def run_task():
            """在单独线程中运行任务"""
            try:
                logger.debug(f"执行定时任务: {task.id}")
                
                # 检查是否是异步函数
                if asyncio.iscoroutinefunction(task.callback):
                    # 异步函数在当前线程的事件循环中运行
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环正在运行，创建任务
                        asyncio.create_task(task.callback(*task.args, **task.kwargs))
                    else:
                        # 否则直接运行
                        loop.run_until_complete(task.callback(*task.args, **task.kwargs))
                else:
                    # 同步函数直接调用
                    task.callback(*task.args, **task.kwargs)
                
                task.run_count += 1
                
                # 如果是单次定时器，执行后取消
                if task.timer_type == TimerType.SINGLE:
                    self.cancel_task(task.id)
                    
            except Exception as e:
                logger.error(f"定时任务执行失败 [{task.id}]: {e}")
            finally:
                task.is_running = False
        
        # 在新线程中执行任务
        thread = threading.Thread(target=run_task, daemon=True, name=f"TimerTask-{task.id}")
        thread.start()
    
    def add_single_timer(self, 
                        delay: float, 
                        callback: Callable, 
                        task_id: Optional[str] = None,
                        *args, **kwargs) -> str:
        """
        添加单次定时器
        
        Args:
            delay: 延迟时间（秒）
            callback: 回调函数
            task_id: 任务ID（可选，自动生成）
            *args: 回调函数的位置参数
            **kwargs: 回调函数的关键字参数
            
        Returns:
            str: 任务ID
        """
        if task_id is None:
            task_id = f"single_{int(time.time() * 1000)}_{len(self._tasks)}"
        
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"任务ID已存在: {task_id}")
            
            task = TimerTask(
                id=task_id,
                timer_type=TimerType.SINGLE,
                callback=callback,
                interval=0,  # 单次定时器不使用间隔
                delay=delay,
                args=args,
                kwargs=kwargs,
                created_time=time.time()
            )
            
            self._tasks[task_id] = task
            logger.info(f"添加单次定时器: {task_id}, 延迟: {delay}秒")
            
            # 确保定时器管理器在运行
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
        添加循环定时器
        
        Args:
            interval: 间隔时间（秒）
            callback: 回调函数
            delay: 首次执行的延迟时间（秒，默认0）
            task_id: 任务ID（可选，自动生成）
            *args: 回调函数的位置参数
            **kwargs: 回调函数的关键字参数
            
        Returns:
            str: 任务ID
        """
        if task_id is None:
            task_id = f"interval_{int(time.time() * 1000)}_{len(self._tasks)}"
        
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"任务ID已存在: {task_id}")
            
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
            logger.info(f"添加循环定时器: {task_id}, 间隔: {interval}秒, 延迟: {delay}秒")
            
            # 确保定时器管理器在运行
            if not self._running:
                self.start()
            
            return task_id
    
    def cancel_task(self, task_id: str) -> bool:
        """取消定时任务"""
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"取消任务失败: 任务ID不存在 - {task_id}")
                return False
            
            task = self._tasks[task_id]
            task.is_cancelled = True
            del self._tasks[task_id]
            logger.info(f"取消定时任务: {task_id}")
            return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
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
        """获取所有任务状态"""
        with self._lock:
            return {
                task_id: self.get_task_status(task_id)
                for task_id in self._tasks.keys()
            }
    
    def clear_all_tasks(self) -> int:
        """清除所有定时任务"""
        with self._lock:
            count = len(self._tasks)
            task_ids = list(self._tasks.keys())
            
            for task_id in task_ids:
                self.cancel_task(task_id)
            
            logger.info(f"清除所有定时任务，共{count}个")
            return count


# 全局定时器管理器实例
_timer_manager = TimerManager()


def set_timeout(delay: float, callback: Callable, *args, **kwargs) -> str:
    """
    设置单次定时器（类似JavaScript的setTimeout）
    
    Args:
        delay: 延迟时间（秒）
        callback: 回调函数
        *args: 回调函数的位置参数
        **kwargs: 回调函数的关键字参数
        
    Returns:
        str: 任务ID，可用于取消定时器
    """
    return _timer_manager.add_single_timer(delay, callback, None, *args, **kwargs)


def set_interval(interval: float, callback: Callable, delay: float = 0, *args, **kwargs) -> str:
    """
    设置循环定时器（类似JavaScript的setInterval）
    
    Args:
        interval: 间隔时间（秒）
        callback: 回调函数
        delay: 首次执行的延迟时间（秒，默认0）
        *args: 回调函数的位置参数
        **kwargs: 回调函数的关键字参数
        
    Returns:
        str: 任务ID，可用于取消定时器
    """
    return _timer_manager.add_interval_timer(interval, callback, delay, None, *args, **kwargs)


def clear_timeout(task_id: str) -> bool:
    """取消单次定时器"""
    return _timer_manager.cancel_task(task_id)


def clear_interval(task_id: str) -> bool:
    """取消循环定时器"""
    return _timer_manager.cancel_task(task_id)


def get_timer_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取定时器状态"""
    return _timer_manager.get_task_status(task_id)


def get_all_timers() -> Dict[str, Dict[str, Any]]:
    """获取所有定时器状态"""
    return _timer_manager.get_all_tasks()


def clear_all_timers() -> int:
    """清除所有定时器"""
    return _timer_manager.clear_all_tasks()


def start_timer_manager() -> bool:
    """启动定时器管理器"""
    return _timer_manager.start()


def stop_timer_manager() -> bool:
    """停止定时器管理器"""
    return _timer_manager.stop()


# 异步版本的定时器函数（使用asyncio）

async def async_set_timeout(delay: float, callback: Callable, *args, **kwargs) -> str:
    """异步设置单次定时器"""
    
    async def async_callback():
        if asyncio.iscoroutinefunction(callback):
            await callback(*args, **kwargs)
        else:
            # 同步函数在异步环境中运行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, *args, **kwargs)
    
    return _timer_manager.add_single_timer(delay, async_callback, None)


async def async_set_interval(interval: float, callback: Callable, delay: float = 0, *args, **kwargs) -> str:
    """异步设置循环定时器"""
    
    async def async_callback():
        if asyncio.iscoroutinefunction(callback):
            await callback(*args, **kwargs)
        else:
            # 同步函数在异步环境中运行
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, *args, **kwargs)
    
    return _timer_manager.add_interval_timer(interval, async_callback, delay, None)


# 便捷的装饰器版本

def timeout(delay: float):
    """单次定时器装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            return set_timeout(delay, func, *args, **kwargs)
        return wrapper
    return decorator


def interval(interval: float, delay: float = 0):
    """循环定时器装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            return set_interval(interval, func, delay, None, *args, **kwargs)
        return wrapper
    return decorator