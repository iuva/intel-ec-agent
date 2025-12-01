#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket消息发送器
实现全局任意位置的WebSocket消息发送功能

使用示例：
1. 发送简单消息
   from local_agent.websocket.message_sender import send_message
   await send_message({"type": "status", "data": "running"})

2. 发送带回调的消息
   async def callback(response):
       print(f"收到响应: {response}")
   
   await send_message(
       {"type": "query", "data": "some_query"},
       response_callback=callback,
       timeout=10
   )

3. 检查连接状态
   from local_agent.websocket.message_sender import is_connected
   if is_connected():
       await send_message({"type": "ping"})
"""

import asyncio
import json
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from ..logger import get_logger


@dataclass
class PendingMessage:
    """待发送消息"""
    message_id: str
    message: Dict[str, Any]
    timestamp: float
    response_callback: Optional[Callable] = None
    timeout: float = 30.0


class WebSocketMessageSender:
    """WebSocket消息发送器"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # WebSocket客户端引用
        self._websocket_client = None
        
        # 待发送消息队列
        self._pending_messages: Dict[str, PendingMessage] = {}
        
        # 锁，用于线程安全
        self._lock = asyncio.Lock()
        
        # 消息ID计数器
        self._message_id_counter = 0
        
        # 清理任务
        self._cleanup_task = None
        
        self.logger.info("WebSocket消息发送器初始化完成")
    
    def set_websocket_client(self, websocket_client):
        """设置WebSocket客户端引用"""
        self._websocket_client = websocket_client
        self.logger.info("已设置WebSocket客户端引用")
        
        # 启动清理任务
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_messages())
    
    def is_connected(self) -> bool:
        """检查WebSocket连接状态"""
        if self._websocket_client is None:
            return False
        return self._websocket_client.is_connected()
    
    async def send_message(self, message: Dict[str, Any], 
                         response_callback: Optional[Callable] = None,
                         timeout: float = 30.0) -> bool:
        """
        发送WebSocket消息
        
        Args:
            message: 消息内容（字典）
            response_callback: 响应回调函数
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否成功发送
        """
        if not self.is_connected():
            self.logger.warning("WebSocket未连接，无法发送消息")
            return False
        
        # 生成消息ID
        message_id = self._generate_message_id()
        
        # 添加消息ID到消息中
        message_with_id = message.copy()
        message_with_id['message_id'] = message_id
        
        # 创建待发送消息
        pending_message = PendingMessage(
            message_id=message_id,
            message=message_with_id,
            timestamp=time.time(),
            response_callback=response_callback,
            timeout=timeout
        )
        
        # 添加到待发送队列
        async with self._lock:
            self._pending_messages[message_id] = pending_message
        
        try:
            # 发送消息
            await self._websocket_client.send_message(json.dumps(message_with_id))
            
            self.logger.debug(f"消息发送成功 (ID: {message_id}), 类型: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            self.logger.error(f"消息发送失败 (ID: {message_id}): {e}")
            
            # 从待发送队列中移除
            async with self._lock:
                self._pending_messages.pop(message_id, None)
            
            return False
    
    async def handle_response(self, response_message: Dict[str, Any]):
        """
        处理响应消息
        
        Args:
            response_message: 响应消息
        """
        message_id = response_message.get('response_to')
        if not message_id:
            return
        
        # 查找对应的待发送消息
        async with self._lock:
            pending_message = self._pending_messages.pop(message_id, None)
        
        if pending_message and pending_message.response_callback:
            try:
                # 执行回调函数
                if asyncio.iscoroutinefunction(pending_message.response_callback):
                    await pending_message.response_callback(response_message)
                else:
                    pending_message.response_callback(response_message)
                
                self.logger.debug(f"响应回调执行成功 (消息ID: {message_id})")
                
            except Exception as e:
                self.logger.error(f"响应回调执行失败 (消息ID: {message_id}): {e}")
    
    def _generate_message_id(self) -> str:
        """生成消息ID"""
        self._message_id_counter += 1
        return f"msg_{self._message_id_counter}_{int(time.time())}"
    
    async def _cleanup_expired_messages(self):
        """清理过期的待发送消息"""
        while True:
            try:
                await asyncio.sleep(10)  # 每10秒清理一次
                
                current_time = time.time()
                expired_messages = []
                
                # 查找过期的消息
                async with self._lock:
                    for message_id, pending_message in self._pending_messages.items():
                        if current_time - pending_message.timestamp > pending_message.timeout:
                            expired_messages.append(message_id)
                
                # 清理过期消息
                for message_id in expired_messages:
                    async with self._lock:
                        expired_message = self._pending_messages.pop(message_id, None)
                    
                    if expired_message:
                        self.logger.warning(f"消息已过期 (ID: {message_id}), 类型: {expired_message.message.get('type', 'unknown')}")
                        
                        # 执行超时回调（如果有）
                        if expired_message.response_callback:
                            try:
                                timeout_response = {
                                    'type': 'timeout',
                                    'response_to': message_id,
                                    'error': '消息响应超时'
                                }
                                
                                if asyncio.iscoroutinefunction(expired_message.response_callback):
                                    await expired_message.response_callback(timeout_response)
                                else:
                                    expired_message.response_callback(timeout_response)
                                    
                            except Exception as e:
                                self.logger.error(f"超时回调执行失败 (消息ID: {message_id}): {e}")
                
            except Exception as e:
                self.logger.error(f"清理过期消息时发生错误: {e}")
    
    def get_pending_message_count(self) -> int:
        """获取待发送消息数量"""
        return len(self._pending_messages)
    
    def clear_pending_messages(self):
        """清空待发送消息队列"""
        async def clear():
            async with self._lock:
                cleared_count = len(self._pending_messages)
                self._pending_messages.clear()
                
            if cleared_count > 0:
                self.logger.info(f"已清空 {cleared_count} 条待发送消息")
        
        asyncio.create_task(clear())


# 创建全局单例实例
_message_sender_instance = None


def get_message_sender() -> WebSocketMessageSender:
    """获取消息发送器实例（单例模式）"""
    global _message_sender_instance
    if _message_sender_instance is None:
        _message_sender_instance = WebSocketMessageSender()
    return _message_sender_instance


# 提供便捷的全局函数
async def send_message(message: Dict[str, Any], 
                     response_callback: Optional[Callable] = None,
                     timeout: float = 30.0) -> bool:
    """
    发送WebSocket消息（全局函数）
    
    Args:
        message: 消息内容（字典）
        response_callback: 响应回调函数
        timeout: 超时时间（秒）
        
    Returns:
        bool: 是否成功发送
    """
    sender = get_message_sender()
    return await sender.send_message(message, response_callback, timeout)


def is_connected() -> bool:
    """检查WebSocket连接状态（全局函数）"""
    sender = get_message_sender()
    return sender.is_connected()


def get_pending_message_count() -> int:
    """获取待发送消息数量（全局函数）"""
    sender = get_message_sender()
    return sender.get_pending_message_count()


def clear_pending_messages():
    """清空待发送消息队列（全局函数）"""
    sender = get_message_sender()
    sender.clear_pending_messages()