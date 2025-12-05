#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket消息发送器
实现全局任意位置的WebSocket消息发送功能，支持两种发送模式：
1. 直接发送模式：连接失败立即返回失败
2. 队列缓存模式：连接失败时缓存消息，连接恢复后自动重发

使用示例：
1. 直接发送消息（适合不需要保证送达的场景）
   from local_agent.websocket.message_sender import send_message
   await send_message({"type": "status", "data": "running"})

2. 使用队列发送消息（适合需要保证送达的重要消息）
   from local_agent.websocket.message_sender import send_message_with_queue
   await send_message_with_queue({"type": "important", "data": "critical"}, max_retries=5)

3. 发送带回调的消息
   async def callback(response):
       print(f"收到响应: {response}")
   
   await send_message_with_queue(
       {"type": "query", "data": "some_query"},
       response_callback=callback,
       timeout=10
   )

4. 检查连接状态
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
    
    # 重试相关字段（可选，用于带队列的消息）
    retry_count: int = 0
    max_retries: int = 3
    last_retry_time: float = 0.0


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
        
        # 注册连接恢复回调
        if hasattr(websocket_client, 'on_connect_callback'):
            # 检查是否已经注册过（通过检查当前回调是否是我们注册的）
            current_callback = websocket_client.on_connect_callback
            
            # 如果当前回调不是我们注册的，或者回调为None，则进行注册
            if current_callback is None or not hasattr(current_callback, '__name__') or current_callback.__name__ != 'connection_restored_callback':
                # 保存原有的回调
                original_callback = current_callback
                
                async def connection_restored_callback():
                    # 调用原有的回调（如果有）
                    if original_callback:
                        await original_callback()
                    # 调用消息发送器的连接恢复处理
                    await self.on_connection_restored()
                
                websocket_client.on_connect_callback = connection_restored_callback
                self.logger.info("已注册WebSocket连接恢复回调")
            else:
                self.logger.debug("WebSocket连接恢复回调已注册，跳过重复注册")
        
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
        发送WebSocket消息（直接发送，不进入队列）
        
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

        
        try:
            # 发送消息
            sent_res = await self._websocket_client.send_message(json.dumps(message_with_id))
            if not sent_res:
                # 添加到待发送队列
                async with self._lock:
                    self._pending_messages[message_id] = pending_message
            
            self.logger.debug(f"消息发送成功 (ID: {message_id}), 类型: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            self.logger.error(f"消息发送失败 (ID: {message_id}): {e}")
            
            # 从待发送队列中移除
            async with self._lock:
                self._pending_messages.pop(message_id, None)
            
            return False

    async def send_message_with_queue(self, message: Dict[str, Any], 
                                    response_callback: Optional[Callable] = None,
                                    timeout: float = 30.0,
                                    max_retries: int = 3) -> bool:
        """
        发送WebSocket消息（带队列缓存和重发机制）
        
        Args:
            message: 消息内容（字典）
            response_callback: 响应回调函数
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            
        Returns:
            bool: 是否成功发送或加入队列
        """
        # 生成消息ID
        message_id = self._generate_message_id()
        
        # 添加消息ID到消息中
        message_with_id = message.copy()
        message_with_id['message_id'] = message_id
        
        # 创建待发送消息（带重试信息）
        pending_message = PendingMessage(
            message_id=message_id,
            message=message_with_id,
            timestamp=time.time(),
            response_callback=response_callback,
            timeout=timeout
        )
        
        # 添加重试信息
        pending_message.retry_count = 0
        pending_message.max_retries = max_retries
        pending_message.last_retry_time = time.time()

        # 立即尝试发送
        if self._websocket_client:
            cent_res = await self._websocket_client.send_message(pending_message)
            if not cent_res:
                # 添加到待发送队列
                async with self._lock:
                    self._pending_messages[message_id] = pending_message


    async def _try_send_message(self, pending_message: PendingMessage) -> bool:
        """尝试发送消息，失败则加入重试队列"""
        if not self.is_connected():
            # 连接未建立，记录日志但不移除消息，等待连接恢复后重试
            self.logger.info(f"WebSocket未连接，消息已加入队列 (ID: {pending_message.message_id}), "
                           f"类型: {pending_message.message.get('type', 'unknown')}")
            return True  # 返回True表示消息已接受处理
        
        try:
            # 发送消息
            await self._websocket_client.send_message(json.dumps(pending_message.message))
            
            self.logger.debug(f"消息发送成功 (ID: {pending_message.message_id}), "
                            f"类型: {pending_message.message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            # 发送失败，处理重试逻辑
            pending_message.retry_count += 1
            pending_message.last_retry_time = time.time()
            
            if pending_message.retry_count <= pending_message.max_retries:
                # 还有重试次数，记录日志并保持消息在队列中
                self.logger.warning(f"消息发送失败，将进行第{pending_message.retry_count}次重试 "
                                  f"(ID: {pending_message.message_id}): {e}")
                
                # 计算下次重试时间（指数退避）
                retry_delay = min(2 ** pending_message.retry_count, 60)  # 最大60秒
                
                # 异步安排重试
                asyncio.create_task(self._retry_message(pending_message, retry_delay))
                return True
            else:
                # 重试次数用尽，移除消息
                self.logger.error(f"消息发送失败，重试次数用尽 (ID: {pending_message.message_id}): {e}")
                
                async with self._lock:
                    self._pending_messages.pop(pending_message.message_id, None)
                
                # 执行失败回调（如果有）
                if pending_message.response_callback:
                    try:
                        error_response = {
                            'type': 'error',
                            'response_to': pending_message.message_id,
                            'error': f'消息发送失败，重试次数用尽: {e}'
                        }
                        
                        if asyncio.iscoroutinefunction(pending_message.response_callback):
                            await pending_message.response_callback(error_response)
                        else:
                            pending_message.response_callback(error_response)
                            
                    except Exception as callback_error:
                        self.logger.error(f"失败回调执行失败 (消息ID: {pending_message.message_id}): {callback_error}")
                
                return False

    async def _retry_message(self, pending_message: PendingMessage, delay: float):
        """延迟重试发送消息"""
        await asyncio.sleep(delay)
        
        # 检查消息是否还在队列中（可能已被处理或过期）
        async with self._lock:
            if pending_message.message_id not in self._pending_messages:
                return
        
        # 重新尝试发送
        await self._try_send_message(pending_message)

    async def on_connection_restored(self):
        """WebSocket连接恢复时的回调，重发队列中的消息"""
        self.logger.info("WebSocket连接已恢复，开始重发队列中的消息")
        
        # 获取当前队列中的所有消息
        async with self._lock:
            messages_to_retry = list(self._pending_messages.values())
        
        # 重发所有消息
        for pending_message in messages_to_retry:
            # 重置重试计数（连接恢复后重新开始计数）
            pending_message.retry_count = 0
            pending_message.last_retry_time = time.time()
            
            # 异步重发
            asyncio.create_task(self._try_send_message(pending_message))
    
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
    发送WebSocket消息（全局函数，直接发送不进入队列）
    
    Args:
        message: 消息内容（字典）
        response_callback: 响应回调函数
        timeout: 超时时间（秒）
        
    Returns:
        bool: 是否成功发送
    """
    sender = get_message_sender()
    return await sender.send_message(message, response_callback, timeout)


async def send_message_with_queue(message: Dict[str, Any], 
                                response_callback: Optional[Callable] = None,
                                timeout: float = 30.0,
                                max_retries: int = 3) -> bool:
    """
    发送WebSocket消息（全局函数，带队列缓存和重发机制）
    
    Args:
        message: 消息内容（字典）
        response_callback: 响应回调函数
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        
    Returns:
        bool: 是否成功发送或加入队列
    """
    sender = get_message_sender()
    return await sender.send_message_with_queue(message, response_callback, timeout, max_retries)


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