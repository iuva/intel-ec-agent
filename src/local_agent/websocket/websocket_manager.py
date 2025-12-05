#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket管理器
实现全局WebSocket服务的启动、停止和管理
"""

import asyncio
import json
from typing import Optional, Callable, Any, Dict

from ..config import get_config
from ..logger import get_logger
# 延迟导入WebSocketClient以避免循环依赖
WebSocketClient = None
def _get_websocket_client():
    global WebSocketClient
    if WebSocketClient is None:
        from .client import WebSocketClient as WSClient
        WebSocketClient = WSClient
    return WebSocketClient
from .message_handler import register_websocket_handlers, get_message_handler
from .message_manager import get_message_manager
from .message_sender import get_message_sender


class WebSocketManager:
    """WebSocket管理器类，提供全局WebSocket服务管理"""
    
    _instance: Optional['WebSocketManager'] = None
    _initialized = False
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化WebSocket管理器"""
        if self._initialized:
            return
            
        self.config = get_config()
        self.logger = get_logger(__name__)

        self.logger.info("初始化WebSocket管理器")
        
        # WebSocket客户端实例
        self.client: Optional[WebSocketClient] = None
        
        # 管理器状态
        self.supposed = False
        self.running = False
        self.connected = False
        
        # 任务管理
        self.connect_task: Optional[asyncio.Task] = None
        
        # 回调函数
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None
        self.on_message_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        
        # 消息管理器和发送器
        self.message_manager = get_message_manager()
        self.message_sender = get_message_sender()
        
        self._initialized = True
        self.logger.debug("WebSocket管理器初始化完成")
    
    async def start(self, application: Optional[Any] = None) -> bool:
        """
        启动WebSocket服务
        
        Args:
            application: 应用实例，用于消息处理器注册
            
        Returns:
            bool: 启动是否成功
        """
        self.supposed = True
        if self.running:
            self.logger.warning("WebSocket服务已在运行中")
            return True
            
        try:
            self.logger.info("正在启动WebSocket服务...")
            
            # 初始化WebSocket客户端（延迟导入）
            WebSocketClient = _get_websocket_client()
            self.client = WebSocketClient()
            
            # 设置回调函数
            await self._setup_callbacks()
            
            # 注册消息处理器（只注册永久处理器，临时处理器保持不变）
            if application:
                register_websocket_handlers(application)
                self.logger.info("已重新注册永久消息处理器")
            else:
                self.logger.info("未提供应用实例，跳过永久处理器注册")
                count = get_message_handler().get_handler_count()
                self.logger.info(f"已存在的处理器注册数量：{count}")
            
            # 启动连接
            self.connect_task = asyncio.create_task(self._connect())
            
            # 等待连接完成
            await asyncio.sleep(1)  # 等待1秒让连接建立
            
            self.running = True
            self.logger.info("WebSocket服务启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket服务启动失败: {e}")
            await self.stop()
            return False
    
    async def stop(self) -> bool:
        """
        停止WebSocket服务
        
        Returns:
            bool: 停止是否成功
        """
        self.supposed = False
        if not self.running:
            self.logger.info("WebSocket服务未运行")
            return True
            
        try:
            self.logger.info("正在停止WebSocket服务...")
            
            # 取消连接任务
            if self.connect_task:
                self.connect_task.cancel()
                try:
                    await self.connect_task
                except asyncio.CancelledError:
                    pass
            
            # 断开WebSocket连接（标记为通过用户停止）
            if self.client:
                await self.client.disconnect(stopped_by_user=True)
            
            # 重置状态
            self.running = False
            self.connected = False
            self.client = None
            self.connect_task = None
            
            self.logger.info("WebSocket服务已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket服务停止失败: {e}")
            return False
    
    async def restart(self) -> bool:
        """
        重启WebSocket服务
        
        Returns:
            bool: 重启是否成功
        """
        self.logger.info("正在重启WebSocket服务...")
        
        # 先停止再启动
        await self.stop()
        await asyncio.sleep(1)  # 等待1秒
        
        return await self.start()
    
    async def _connect(self):
        """连接WebSocket服务器"""
        if not self.client:
            return
            
        try:
            success = await self.client.connect()
            if success:
                self.connected = True
                self.logger.info("WebSocket连接成功")
            else:
                self.logger.error("WebSocket连接失败")
                
        except Exception as e:
            self.logger.error(f"WebSocket连接异常: {e}")
    
    async def _setup_callbacks(self):
        """设置WebSocket回调函数"""
        if not self.client:
            return
        
        async def on_connect():
            """连接成功回调"""
            self.connected = True
            self.logger.info("WebSocket连接成功")
            
            # 调用用户自定义回调
            if self.on_connect_callback:
                await self.on_connect_callback()
        
        async def on_disconnect():
            """连接断开回调"""
            self.connected = False
            self.logger.warning("WebSocket连接断开")
            
            # 调用用户自定义回调
            if self.on_disconnect_callback:
                await self.on_disconnect_callback()
        
        async def on_message(message):
            """消息接收回调"""
            self.logger.debug(f"收到WebSocket消息: {message}")
            
            # 调用用户自定义回调
            if self.on_message_callback:
                await self.on_message_callback(message)
        
        async def on_error(error):
            """错误回调"""
            self.logger.error(f"WebSocket错误: {error}")
            
            # 调用用户自定义回调
            if self.on_error_callback:
                await self.on_error_callback(error)
        
        # 设置回调
        self.client.set_on_connect(on_connect)
        self.client.set_on_disconnect(on_disconnect)
        self.client.set_on_message(on_message)
        self.client.set_on_error(on_error)
    
    def set_on_connect(self, callback: Callable):
        """设置连接成功回调"""
        self.on_connect_callback = callback
    
    def set_on_disconnect(self, callback: Callable):
        """设置连接断开回调"""
        self.on_disconnect_callback = callback
    
    def set_on_message(self, callback: Callable):
        """设置消息接收回调"""
        self.on_message_callback = callback
    
    def set_on_error(self, callback: Callable):
        """设置错误回调"""
        self.on_error_callback = callback
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送WebSocket消息
        
        Args:
            message: 要发送的消息字典
            
        Returns:
            bool: 发送是否成功
        """
        if not self.connected or not self.client:
            self.logger.warning("WebSocket未连接，无法发送消息")
            return False
            
        try:
            await self.message_sender.send_message(message)
            return True
        except Exception as e:
            self.logger.error(f"发送WebSocket消息失败: {e}")
            return False

    def is_connected(self) -> bool:
        """检查WebSocket连接状态"""
        return self.connected
    
    def is_supposed(self) -> bool:
        """检查WebSocket服务运行状态"""
        return self.supposed
    
    def is_running(self) -> bool:
        """检查WebSocket服务运行状态"""
        return self.running


def get_websocket_manager() -> WebSocketManager:
    """
    获取WebSocket管理器实例（全局单例）
    
    Returns:
        WebSocketManager: WebSocket管理器实例
    """
    return WebSocketManager()