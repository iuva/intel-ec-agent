#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket客户端
实现WebSocket连接、消息收发和重连机制
"""

import asyncio
import websockets
import json
from typing import Optional, Callable, Any
from datetime import datetime

from ..config import get_config
from ..logger import get_logger
from ..core.global_cache import cache
from ..core.constants import AUTHORIZATION_CACHE_KEY
from .message_manager import get_message_manager
from .message_sender import get_message_sender

class WebSocketClient:
    """WebSocket客户端类"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # 连接状态
        self.connected = False
        self.connection = None
        self.reconnect_task = None
        self.reconnect_attempts = 0
        
        # 停止标志 - 用于判断是否是通过stop方法停止的服务
        self.stopped_by_user = False
        
        # 回调函数
        self.on_message_callback: Optional[Callable] = None
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        
        # 消息队列
        self.message_queue = asyncio.Queue()
        self.send_task = None
        self.receive_task = None
        
        # 鉴权保活任务
        self.auth_keepalive_task = None
        self.auth_check_interval = 300  # 5分钟检查一次
        
        # 消息管理器和发送器
        self.message_manager = get_message_manager()
        self.message_sender = get_message_sender()
    
    async def connect(self) -> bool:
        """连接到WebSocket服务器"""
        if self.connected:
            self.logger.warning("WebSocket客户端已连接")
            return True
        
        websocket_url = self.config.get('websocket_url', 'ws://localhost:8765')
        
        try:
            self.logger.info(f"正在连接到WebSocket服务器: {websocket_url}")
            
            # 获取Authorization头
            headers = await self._get_auth_headers()

            self.logger.info(f"WebSocket 请求头内容：: {headers}")

            # 建立连接
            self.connection = await websockets.connect(
                websocket_url,
                extra_headers=headers,
                ping_interval=20,  # 20秒发送一次ping
                ping_timeout=10,   # 10秒内未收到pong则断开
                close_timeout=10   # 关闭超时时间
            )
            
            self.connected = True
            self.reconnect_attempts = 0
            self.stopped_by_user = False  # 重置停止标志
            
            self.logger.info("WebSocket连接成功")
            
            # 设置消息管理器和发送器的WebSocket客户端引用
            self.message_manager.set_websocket_client(self)
            self.message_sender.set_websocket_client(self)
            
            # 启动消息发送和接收任务
            self.send_task = asyncio.create_task(self._send_messages())
            self.receive_task = asyncio.create_task(self._receive_messages())
            
            # 启动鉴权保活任务
            self.auth_keepalive_task = asyncio.create_task(self._auth_keepalive())
            
            # 调用连接回调
            if self.on_connect_callback:
                await self.on_connect_callback()
            
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            self.connected = False
            
            # 调用错误回调
            if self.on_error_callback:
                await self.on_error_callback(e)
            
            return False
    
    async def disconnect(self, stopped_by_user: bool = False):
        """
        断开WebSocket连接
        
        Args:
            stopped_by_user: 是否是通过用户主动停止的
        """
        if not self.connected:
            return
        
        self.logger.info("正在断开WebSocket连接...")
        
        # 设置停止标志
        self.stopped_by_user = stopped_by_user
        
        # 取消任务
        if self.send_task:
            self.send_task.cancel()
        if self.receive_task:
            self.receive_task.cancel()
        if self.auth_keepalive_task:
            self.auth_keepalive_task.cancel()
        
        # 关闭连接
        if self.connection:
            await self.connection.close()
        
        self.connected = False
        self.connection = None
        
        # 调用断开回调
        if self.on_disconnect_callback:
            await self.on_disconnect_callback()
        
        self.logger.info("WebSocket连接已断开")
    
    async def _get_auth_headers(self) -> dict:
        """获取Authorization请求头"""
        
        # 等待auth_token完成初始化
        token = await self._wait_for_auth_token()
        
        if token:
            return {"Authorization": f"Bearer {token}"}
        else:
            self.logger.warning("未获取到有效token，将使用无鉴权连接")
            return {}
    
    async def _wait_for_auth_token(self, timeout: int = 30) -> Optional[str]:
        """等待auth_token完成初始化"""
        import asyncio
        from ..core.global_cache import cache
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # 从缓存获取token
            token = cache.get(AUTHORIZATION_CACHE_KEY)
            if token:
                self.logger.info("成功获取到token")
                return token
            else:
                from ..core.auth import auth_token
                auth_token()
                return cache.get(AUTHORIZATION_CACHE_KEY)
                
        
        self.logger.error(f"等待token超时({timeout}秒)")
        return None
    
    async def _refresh_auth_token(self) -> bool:
        """刷新鉴权token"""
        from ..core.auth import refresh_token, auth_token
        
        try:
            # 先尝试刷新token
            self.logger.info("尝试刷新token...")
            if refresh_token():
                self.logger.info("token刷新成功")
                return True
            
            # 刷新失败则重新获取
            self.logger.info("刷新失败，尝试重新获取token...")
            if auth_token():
                self.logger.info("token重新获取成功")
                return True
            
            self.logger.error("token获取失败")
            return False
            
        except Exception as e:
            self.logger.error(f"鉴权token刷新失败: {e}")
            return False
    
    async def _handle_auth_expired(self) -> bool:
        """处理token过期"""
        # 先尝试刷新
        if await self._refresh_auth_token():
            return True
        
        # 刷新失败则每1分钟重试一次
        retry_interval = 60  # 1分钟
        
        while True:
            self.logger.info(f"等待{retry_interval}秒后重试鉴权...")
            await asyncio.sleep(retry_interval)
            
            if await self._refresh_auth_token():
                return True
    
    async def _auth_keepalive(self):
        """鉴权保活任务，定期检查token状态"""
        while self.connected:
            try:
                # 等待检查间隔
                await asyncio.sleep(self.auth_check_interval)
                
                # 检查token是否存在
                from ..core.global_cache import cache
                token = cache.get(AUTHORIZATION_CACHE_KEY)
                
                if not token:
                    self.logger.warning("检测到token过期，尝试刷新...")
                    if not await self._refresh_auth_token():
                        self.logger.error("token刷新失败，WebSocket连接可能受影响")
                        # 继续保活，不中断WebSocket连接
                else:
                    self.logger.debug("token状态正常")
                    
            except asyncio.CancelledError:
                # 任务被取消，正常退出
                break
            except Exception as e:
                self.logger.error(f"鉴权保活任务异常: {e}")
                # 继续保活，不中断WebSocket连接
    
    async def send_message(self, message: Any):
        """发送消息到服务器"""
        if not self.connected:
            self.logger.warning("WebSocket未连接，无法发送消息")
            return False
        
        try:
            # 如果是字典，转换为JSON字符串
            if isinstance(message, dict):
                message = json.dumps(message)
            
            await self.connection.send(message)
            self.logger.debug(f"发送消息: {message}")
            return True
            
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            await self._handle_connection_error(e)
            return False
    
    async def _send_messages(self):
        """从队列发送消息"""
        while self.connected:
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(), 
                    timeout=1.0
                )
                await self.send_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"发送消息任务错误: {e}")
                break
    
    async def _receive_messages(self):
        """接收服务器消息"""
        while self.connected:
            try:
                message = await asyncio.wait_for(
                    self.connection.recv(),
                    timeout=1.0
                )
                
                self.logger.debug(f"收到消息: {message}")
                
                # 使用消息管理器处理消息
                handled = await self.message_manager.handle_message(message)
                
                # 如果消息管理器未处理，调用原始消息回调
                if not handled and self.on_message_callback:
                    await self.on_message_callback(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"接收消息任务错误: {e}")
                # await self._handle_connection_error(e)
                break

    def is_connected(self):
        return self.connected

    async def _handle_connection_error(self, error: Exception):
        """处理连接错误"""
        self.logger.error(f"WebSocket连接错误: {error}")
        
        # 调用错误回调
        if self.on_error_callback:
            await self.on_error_callback(error)
        
        # 断开连接并尝试重连
        await self.disconnect()
        await self._start_reconnect()
    
    async def _start_reconnect(self):
        """启动重连机制"""
        # 检查是否是通过stop方法停止的服务，如果是则不重连
        if self.stopped_by_user:
            self.logger.info("检测到服务是通过stop方法停止的，不进行重连")
            return
        
        if self.reconnect_task and not self.reconnect_task.done():
            return
        
        max_attempts = self.config.get('max_restart_attempts', 3)
        if self.reconnect_attempts >= max_attempts:
            self.logger.error(f"已达到最大重连次数: {max_attempts}")
            return
        
        self.reconnect_attempts += 1
        reconnect_interval = self.config.get('websocket_reconnect_interval', 10)
        
        self.logger.info(f"{reconnect_interval}秒后尝试第{self.reconnect_attempts}次重连...")
        
        self.reconnect_task = asyncio.create_task(self._reconnect_after_delay(reconnect_interval))
    
    async def _reconnect_after_delay(self, delay: int):
        """延迟后重连"""
        await asyncio.sleep(delay)
        
        if not self.connected:
            # 检查token状态，如果过期则先处理鉴权
            from ..core.global_cache import cache
            token = cache.get(AUTHORIZATION_CACHE_KEY)
            
            if not token:
                self.logger.info("检测到token过期，先处理鉴权...")
                if not await self._handle_auth_expired():
                    self.logger.error("鉴权处理失败，无法重连")
                    return
            
            await self.connect()
    
    def set_on_message(self, callback: Callable):
        """设置消息接收回调"""
        self.on_message_callback = callback
    
    def set_on_connect(self, callback: Callable):
        """设置连接成功回调"""
        self.on_connect_callback = callback
    
    def set_on_disconnect(self, callback: Callable):
        """设置断开连接回调"""
        self.on_disconnect_callback = callback
    
    def set_on_error(self, callback: Callable):
        """设置错误回调"""
        self.on_error_callback = callback
    
    def get_status(self) -> dict:
        """获取客户端状态"""
        return {
            "connected": self.connected,
            "reconnect_attempts": self.reconnect_attempts,
            "websocket_url": self.config.get('websocket_url'),
            "last_activity": datetime.now().isoformat()
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.disconnect()
