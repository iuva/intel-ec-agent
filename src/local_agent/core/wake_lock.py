#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Computer wake lock module
Uses Windows native API to implement highly reliable system wake keeping
"""

import ctypes
import time
import threading
from typing import Optional
from ..logger import get_logger


class SystemWakeLock:
    """
    System wake lock class
    Uses Windows native API to keep computer awake
    """
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Windows API constant definitions
        self.ES_CONTINUOUS = 0x80000000
        self.ES_SYSTEM_REQUIRED = 0x00000001
        self.ES_DISPLAY_REQUIRED = 0x00000002
        self.ES_AWAYMODE_REQUIRED = 0x00000040
        
        # Status management
        self._is_active = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        
        # Configuration parameters
        self.heartbeat_interval = 300  # 5 minute heartbeat detection
        self.max_retry_count = 3
        
        self.logger.info("System wake lock initialized")
    
    def _call_windows_api(self, flags: int) -> bool:
        """
        Call Windows API to set execution state
        
        Args:
            flags: Execution state flags
            
        Returns:
            bool: Whether the call was successful
        """
        try:
            result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            return result != 0
        except Exception as e:
            self.logger.error(f"Call Windows API failed: {e}")
            return False
    
    def keep_awake(self, display_on: bool = True, away_mode: bool = False) -> bool:
        """
        Keep system in wake state
        
        Args:
            display_on: Whether to keep display on
            away_mode: Whether to enable away mode (suitable for media playback scenarios)
            
        Returns:
            bool: Whether setting was successful
        """
        # Build flags
        flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
        
        if display_on:
            flags |= self.ES_DISPLAY_REQUIRED
        
        if away_mode:
            flags |= self.ES_AWAYMODE_REQUIRED
        
        # Retry mechanism
        for attempt in range(self.max_retry_count):
            if self._call_windows_api(flags):
                self._is_active = True
                self.logger.info(f"System wake state set successfully (display {'on' if display_on else 'off'})")
                
                # Start heartbeat detection
                self._start_heartbeat()
                return True
            
            self.logger.warning(f"Attempt {attempt + 1} to set wake state failed, {'retrying...' if attempt < self.max_retry_count - 1 else 'giving up'}")
            time.sleep(1)
        
        self.logger.error("Set system wake state failed")
        return False
    
    def release(self) -> bool:
        """
        Release wake state, allow system to sleep normally
        
        Returns:
            bool: Whether release was successful
        """
        # If already in inactive status, return success directly
        if not self._is_active:
            self.logger.info("Wake lock already in released state")
            return True
        
        # Stop heartbeat detection
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        
        # Release wake status - use ES_CONTINUOUS to reset execute status
        # Note: Windows API requires ES_CONTINUOUS to clear all previous status
        success = self._call_windows_api(self.ES_CONTINUOUS)
        
        # Regardless of whether API call was successful, we set internal status to inactive
        self._is_active = False
        
        if success:
            self.logger.info("System wake state has been released")
        else:
            self.logger.warning("Release system wake state failed, but internal state has been reset")
        
        return success
    
    def _start_heartbeat(self):
        """Start heartbeat detection thread"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker,
            name="WakeLockHeartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()
        self.logger.info("Heartbeat detection thread started")
    
    def _heartbeat_worker(self):
        """Heartbeat detection worker thread"""
        while not self._stop_heartbeat.is_set():
            try:
                # Check if wake status is still valid
                if self._is_active:
                    # Reset wake status (heartbeat)
                    flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
                    if not self._call_windows_api(flags):
                        self.logger.warning("Heartbeat detection found wake state invalid, attempting to reset")
                        # Try to reactivate
                        self.keep_awake(display_on=True)
                
                # Wait for next heartbeat
                self._stop_heartbeat.wait(self.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Heartbeat detection thread exception: {e}")
                break
    
    def is_active(self) -> bool:
        """Get current wake state"""
        return self._is_active
    
    def __enter__(self):
        """Context manager entry"""
        self.keep_awake()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.release()


# Global wake lock instance
_wake_lock: Optional[SystemWakeLock] = None


def get_wake_lock() -> SystemWakeLock:
    """
    Get global wake lock instance (singleton pattern)
    
    Returns:
        SystemWakeLock: Wake lock instance
    """
    global _wake_lock
    if _wake_lock is None:
        _wake_lock = SystemWakeLock()
    return _wake_lock


def keep_system_awake(display_on: bool = True, away_mode: bool = False) -> bool:
    """
    Convenience function: Keep system awake
    
    Args:
        display_on: Whether to keep display on
        away_mode: Whether to enable away mode
        
    Returns:
        bool: Whether setting was successful
    """
    return get_wake_lock().keep_awake(display_on, away_mode)


def release_system_awake() -> bool:
    """
    Convenience function: Release system wake
    
    Returns:
        bool: Whether release was successful
    """
    return get_wake_lock().release()


def is_system_awake() -> bool:
    """
    Convenience function: Check if system is in wake state
    
    Returns:
        bool: Whether system is in wake state
    """
    return get_wake_lock().is_active()