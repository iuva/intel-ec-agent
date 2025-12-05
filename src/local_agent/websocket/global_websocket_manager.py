#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局WebSocket管理器
单例模式，支持一行代码启动和停止WebSocket服务

使用示例：
1. 启动WebSocket服务：
   from src.local_agent.websocket.global_websocket_manager import websocket_manager
   await websocket_manager.start()

2. 停止WebSocket服务：
   await websocket_manager.stop()

3. 重启WebSocket服务：
   await websocket_manager.restart()

4. 发送消息：
   await websocket_manager.send_message({"type": "heartbeat"})

5. 检查连接状态：
   if websocket_manager.is_connected():
       print("WebSocket已连接")
"""

import asyncio
from typing import Dict, Any, Optional, Callable

from ..logger import get_logger
from .websocket_manager import WebSocketManager
from .message_handler import register_websocket_handlers


class GlobalWebSocketManager:
    """全局WebSocket管理器（单例模式）"""
    
    _instance: Optional['GlobalWebSocketManager'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """初始化全局WebSocket管理器"""
        if GlobalWebSocketManager._instance is not None:
            raise RuntimeError("请使用 get_instance() 方法获取单例实例")
        
        self.logger = get_logger(__name__)
        self._websocket_manager: Optional[WebSocketManager] = None
        self._application = None
        self._initialized = False
        
        GlobalWebSocketManager._instance = self
    
    @classmethod
    async def get_instance(cls) -> 'GlobalWebSocketManager':
        """获取全局WebSocket管理器单例实例"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    async def initialize(self, application=None) -> bool:
        """
        初始化WebSocket管理器
        
        Args:
            application: 应用实例（可选，用于消息处理器注册）
            
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            self.logger.info("WebSocket管理器已初始化")
            return True
            
        try:
            self.logger.info("正在初始化全局WebSocket管理器...")
            
            # 创建WebSocket管理器实例
            self._websocket_manager = WebSocketManager()
            self._application = application
            
            self._initialized = True
            self.logger.info("全局WebSocket管理器初始化成功")
            return True
            
        except Exception as e:
            self.logger.error(f"全局WebSocket管理器初始化失败: {e}")
            return False
    
    async def start(self, application=True) -> bool:
        """
        启动WebSocket服务
        
        Args:
            application: 应用实例（可选）
            
        Returns:
            bool: 启动是否成功
        """
        try:
            # 确保已初始化
            if not self._initialized:
                if not await self.initialize(application):
                    return False
            
            if not self._websocket_manager:
                self.logger.error("WebSocket管理器未初始化")
                return False
            
            # 启动WebSocket服务
            return await self._websocket_manager.start(application)
            
        except Exception as e:
            self.logger.error(f"WebSocket服务启动失败: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        停止WebSocket服务
        
        Returns:
            bool: 停止是否成功
        """
        try:
            if not self._websocket_manager:
                self.logger.warning("WebSocket管理器未初始化，无需停止")
                return True
            
            # 停止WebSocket服务
            return await self._websocket_manager.stop()
            
        except Exception as e:
            self.logger.error(f"WebSocket服务停止失败: {e}")
            return False
    
    async def restart(self, application=None) -> bool:
        """
        重启WebSocket服务
        
        Args:
            application: 应用实例（可选）
            
        Returns:
            bool: 重启是否成功
        """
        try:
            # 先停止再启动
            await self.stop()
            await asyncio.sleep(1)  # 等待1秒
            return await self.start(application)
            
        except Exception as e:
            self.logger.error(f"WebSocket服务重启失败: {e}")
            return False
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送WebSocket消息
        
        Args:
            message: 要发送的消息字典
            
        Returns:
            bool: 发送是否成功
        """
        try:
            if not self._websocket_manager:
                self.logger.warning("WebSocket管理器未初始化，无法发送消息")
                return False
            
            return await self._websocket_manager.send_message(message)
            
        except Exception as e:
            self.logger.error(f"发送WebSocket消息失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        检查WebSocket连接状态
        
        Returns:
            bool: 是否已连接
        """
        try:
            if not self._websocket_manager:
                return False
            
            return self._websocket_manager.is_connected()
            
        except Exception as e:
            self.logger.error(f"检查WebSocket连接状态失败: {e}")
            return False
    
    def is_supposed(self) -> bool:
        # 是否应该运行
        if not self._websocket_manager:
            return False
        return self._websocket_manager.is_supposed()
    
    def is_running(self) -> bool:
        """
        检查WebSocket服务运行状态
        
        Returns:
            bool: 是否正在运行
        """
        try:
            if not self._websocket_manager:
                return False
            
            return self._websocket_manager.is_running()
            
        except Exception as e:
            self.logger.error(f"检查WebSocket服务运行状态失败: {e}")
            return False
    
    def set_on_connect(self, callback: Callable):
        """
        设置连接成功回调
        
        Args:
            callback: 回调函数
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_connect(callback)
    
    def set_on_disconnect(self, callback: Callable):
        """
        设置连接断开回调
        
        Args:
            callback: 回调函数
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_disconnect(callback)
    
    def set_on_message(self, callback: Callable):
        """
        设置消息接收回调
        
        Args:
            callback: 回调函数
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_message(callback)
    
    def set_on_error(self, callback: Callable):
        """
        设置错误回调
        
        Args:
            callback: 回调函数
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_error(callback)


# 创建全局单例实例
_global_websocket_manager: Optional[GlobalWebSocketManager] = None


async def get_websocket_manager() -> GlobalWebSocketManager:
    """
    获取全局WebSocket管理器实例
    
    Returns:
        GlobalWebSocketManager: 全局WebSocket管理器实例
    """
    global _global_websocket_manager
    
    if _global_websocket_manager is None:
        _global_websocket_manager = await GlobalWebSocketManager.get_instance()
    
    return _global_websocket_manager


# 便捷函数 - 一行代码启动和停止WebSocket服务

async def start_websocket(application=None) -> bool:
    """
    一行代码启动WebSocket服务
    
    Args:
        application: 应用实例（可选）
        
    Returns:
        bool: 启动是否成功
    """
    manager = await get_websocket_manager()
    return await manager.start(application)


async def stop_websocket() -> bool:
    """
    一行代码停止WebSocket服务
    
    Returns:
        bool: 停止是否成功
    """
    manager = await get_websocket_manager()
    return await manager.stop()


async def restart_websocket(application=None) -> bool:
    """
    一行代码重启WebSocket服务
    
    Args:
        application: 应用实例（可选）
        
    Returns:
        bool: 重启是否成功
    """
    manager = await get_websocket_manager()
    return await manager.restart(application)


async def send_websocket_message(message: Dict[str, Any]) -> bool:
    """
    一行代码发送WebSocket消息
    
    Args:
        message: 要发送的消息字典
        
    Returns:
        bool: 发送是否成功
    """
    manager = await get_websocket_manager()
    return await manager.send_message(message)


def is_websocket_connected() -> bool:
    """
    一行代码检查WebSocket连接状态
    
    Returns:
        bool: 是否已连接
    """
    if _global_websocket_manager is None:
        return False
    return _global_websocket_manager.is_connected()


def is_websocket_running() -> bool:
    """
    一行代码检查WebSocket服务运行状态
    
    Returns:
        bool: 是否正在运行
    """
    if _global_websocket_manager is None:
        return False
    return _global_websocket_manager.is_running()


# 全局单例实例（延迟初始化）
websocket_manager = None


def get_websocket_manager_sync() -> Optional[GlobalWebSocketManager]:
    """同步方式获取全局WebSocket管理器实例
    
    Returns:
        Optional[GlobalWebSocketManager]: 全局WebSocket管理器实例，如果未初始化则返回None
    """
    return _global_websocket_manager