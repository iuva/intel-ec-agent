#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电脑唤醒保持模块
使用Windows原生API实现高可靠性的系统唤醒保持
"""

import ctypes
import time
import threading
from typing import Optional
from ..logger import get_logger


class SystemWakeLock:
    """
    系统唤醒锁类
    使用Windows原生API保持电脑唤醒状态
    """
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Windows API常量定义
        self.ES_CONTINUOUS = 0x80000000
        self.ES_SYSTEM_REQUIRED = 0x00000001
        self.ES_DISPLAY_REQUIRED = 0x00000002
        self.ES_AWAYMODE_REQUIRED = 0x00000040
        
        # 状态管理
        self._is_active = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        
        # 配置参数
        self.heartbeat_interval = 300  # 5分钟心跳检测
        self.max_retry_count = 3
        
        self.logger.info("系统唤醒锁初始化完成")
    
    def _call_windows_api(self, flags: int) -> bool:
        """
        调用Windows API设置执行状态
        
        Args:
            flags: 执行状态标志
            
        Returns:
            bool: 调用是否成功
        """
        try:
            result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            return result != 0
        except Exception as e:
            self.logger.error(f"调用Windows API失败: {e}")
            return False
    
    def keep_awake(self, display_on: bool = True, away_mode: bool = False) -> bool:
        """
        保持系统唤醒状态
        
        Args:
            display_on: 是否保持显示器亮起
            away_mode: 是否启用离开模式（适用于媒体播放等场景）
            
        Returns:
            bool: 设置是否成功
        """
        # 构建标志位
        flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
        
        if display_on:
            flags |= self.ES_DISPLAY_REQUIRED
        
        if away_mode:
            flags |= self.ES_AWAYMODE_REQUIRED
        
        # 重试机制
        for attempt in range(self.max_retry_count):
            if self._call_windows_api(flags):
                self._is_active = True
                self.logger.info(f"系统唤醒状态设置成功 (显示{'开启' if display_on else '关闭'})")
                
                # 启动心跳检测
                self._start_heartbeat()
                return True
            
            self.logger.warning(f"第{attempt + 1}次设置唤醒状态失败，{'重试中...' if attempt < self.max_retry_count - 1 else '放弃重试'}")
            time.sleep(1)
        
        self.logger.error("设置系统唤醒状态失败")
        return False
    
    def release(self) -> bool:
        """
        释放唤醒状态，允许系统正常休眠
        
        Returns:
            bool: 释放是否成功
        """
        # 如果已经处于非激活状态，直接返回成功
        if not self._is_active:
            self.logger.info("唤醒锁已处于释放状态")
            return True
        
        # 停止心跳检测
        self._stop_heartbeat.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        
        # 释放唤醒状态 - 使用ES_CONTINUOUS重置执行状态
        # 注意：Windows API要求使用ES_CONTINUOUS来清除之前的所有状态
        success = self._call_windows_api(self.ES_CONTINUOUS)
        
        # 无论API调用是否成功，我们都将内部状态设置为非激活
        self._is_active = False
        
        if success:
            self.logger.info("系统唤醒状态已释放")
        else:
            self.logger.warning("释放系统唤醒状态失败，但内部状态已重置")
        
        return success
    
    def _start_heartbeat(self):
        """启动心跳检测线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_worker,
            name="WakeLockHeartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()
        self.logger.info("心跳检测线程已启动")
    
    def _heartbeat_worker(self):
        """心跳检测工作线程"""
        while not self._stop_heartbeat.is_set():
            try:
                # 检查唤醒状态是否仍然有效
                if self._is_active:
                    # 重新设置唤醒状态（心跳）
                    flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
                    if not self._call_windows_api(flags):
                        self.logger.warning("心跳检测发现唤醒状态失效，尝试重新设置")
                        # 尝试重新激活
                        self.keep_awake(display_on=True)
                
                # 等待下一次心跳
                self._stop_heartbeat.wait(self.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"心跳检测线程异常: {e}")
                break
    
    def is_active(self) -> bool:
        """获取当前唤醒状态"""
        return self._is_active
    
    def __enter__(self):
        """上下文管理器入口"""
        self.keep_awake()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.release()


# 全局唤醒锁实例
_wake_lock: Optional[SystemWakeLock] = None


def get_wake_lock() -> SystemWakeLock:
    """
    获取全局唤醒锁实例（单例模式）
    
    Returns:
        SystemWakeLock: 唤醒锁实例
    """
    global _wake_lock
    if _wake_lock is None:
        _wake_lock = SystemWakeLock()
    return _wake_lock


def keep_system_awake(display_on: bool = True, away_mode: bool = False) -> bool:
    """
    便捷函数：保持系统唤醒
    
    Args:
        display_on: 是否保持显示器亮起
        away_mode: 是否启用离开模式
        
    Returns:
        bool: 设置是否成功
    """
    return get_wake_lock().keep_awake(display_on, away_mode)


def release_system_awake() -> bool:
    """
    便捷函数：释放系统唤醒
    
    Returns:
        bool: 释放是否成功
    """
    return get_wake_lock().release()


def is_system_awake() -> bool:
    """
    便捷函数：检查系统是否处于唤醒状态
    
    Returns:
        bool: 是否处于唤醒状态
    """
    return get_wake_lock().is_active()