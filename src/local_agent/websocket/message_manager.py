#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket消息管理器
实现统一消息处理和临时注册机制，支持全局任意位置临时注册消息处理器

使用示例：
1. 注册永久消息处理器（在应用启动时注册）
   from local_agent.websocket.message_manager import message_manager
   
   @message_manager.register_handler("healthy")
   async def handle_ping(message):
       # 处理ping消息
       pass

2. 临时注册消息处理器（在任意位置注册）
   handler_id = message_manager.register_temporary_handler("custom_type", async_handler_func)
   
   # 使用后取消注册
   message_manager.unregister_temporary_handler(handler_id)

3. 发送消息
   from local_agent.websocket.message_sender import send_message
   await send_message({"type": "status", "data": "running"})
"""

import asyncio
import json
import uuid
from typing import Optional, Callable, Dict, Any, List, Set
from dataclasses import dataclass

from ..logger import get_logger


@dataclass
class MessageHandler:
    """消息处理器定义"""
    handler_id: str
    message_type: str
    handler_func: Callable
    is_temporary: bool = False
    description: str = ""


class WebSocketMessageManager:
    """WebSocket消息管理器"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # 消息处理器注册表
        self._handlers: Dict[str, List[MessageHandler]] = {}
        
        # 临时处理器ID集合
        self._temporary_handler_ids: Set[str] = set()
        
        # WebSocket客户端引用
        self._websocket_client = None
        
        # 锁，用于线程安全
        self._lock = asyncio.Lock()
        
        self.logger.info("WebSocket消息管理器初始化完成")
    
    def set_websocket_client(self, websocket_client):
        """设置WebSocket客户端引用"""
        self._websocket_client = websocket_client
        self.logger.info("已设置WebSocket客户端引用")
    
    def register_handler(self, message_type: str, description: str = "") -> Callable:
        """
        装饰器方式注册永久消息处理器
        
        Args:
            message_type: 消息类型
            description: 处理器描述
            
        Returns:
            Callable: 装饰器函数
        """
        def decorator(handler_func: Callable) -> Callable:
            self._register_permanent_handler(message_type, handler_func, description)
            return handler_func
        return decorator
    
    def register_temporary_handler(self, message_type: str, handler_func: Callable, 
                                 description: str = "") -> str:
        """
        注册临时消息处理器
        
        Args:
            message_type: 消息类型
            handler_func: 处理函数
            description: 处理器描述
            
        Returns:
            str: 处理器ID，用于取消注册
        """
        handler_id = str(uuid.uuid4())
        
        async def wrapper(message: Dict[str, Any]):
            """包装器，处理临时处理器"""
            try:
                await handler_func(message)
            except Exception as e:
                self.logger.error(f"临时处理器执行失败 (ID: {handler_id}): {e}")
        
        handler = MessageHandler(
            handler_id=handler_id,
            message_type=message_type,
            handler_func=wrapper,
            is_temporary=True,
            description=description
        )
        
        async def register():
            async with self._lock:
                if message_type not in self._handlers:
                    self._handlers[message_type] = []
                self._handlers[message_type].append(handler)
                self._temporary_handler_ids.add(handler_id)
        
        # 异步注册
        asyncio.create_task(register())
        
        self.logger.info(f"注册临时消息处理器 (ID: {handler_id}) - 类型: {message_type}")
        return handler_id
    
    def unregister_temporary_handler(self, handler_id: str) -> bool:
        """
        取消注册临时消息处理器
        
        Args:
            handler_id: 处理器ID
            
        Returns:
            bool: 是否成功取消注册
        """
        async def unregister():
            async with self._lock:
                if handler_id not in self._temporary_handler_ids:
                    return False
                
                # 从所有消息类型中移除该处理器
                for message_type in list(self._handlers.keys()):
                    self._handlers[message_type] = [
                        h for h in self._handlers[message_type] 
                        if h.handler_id != handler_id
                    ]
                    
                    # 如果该类型没有处理器了，移除类型
                    if not self._handlers[message_type]:
                        del self._handlers[message_type]
                
                self._temporary_handler_ids.discard(handler_id)
                return True
        
        # 异步取消注册
        asyncio.create_task(unregister())
        
        self.logger.info(f"取消注册临时消息处理器 (ID: {handler_id})")
        return True
    
    def _register_permanent_handler(self, message_type: str, handler_func: Callable, 
                                  description: str = ""):
        """注册永久消息处理器"""
        handler_id = f"permanent_{message_type}_{id(handler_func)}"
        
        handler = MessageHandler(
            handler_id=handler_id,
            message_type=message_type,
            handler_func=handler_func,
            is_temporary=False,
            description=description
        )
        
        async def register():
            async with self._lock:
                if message_type not in self._handlers:
                    self._handlers[message_type] = []
                self._handlers[message_type].append(handler)
                self.logger.info(f"注册永久消息处理器 - 类型: {message_type}, 描述: {description}, 共{len(self._handlers.values())} 个处理器")
        
        # 异步注册
        asyncio.create_task(register())

    
    async def handle_message(self, message: str) -> bool:
        """
        处理WebSocket消息
        
        Args:
            message: 原始消息字符串
            
        Returns:
            bool: 是否成功处理
        """
        try:
            # 解析JSON消息
            data = message
            if isinstance(message, str):
                data = json.loads(message)
            
            message_type = data.get('type', '')
            
            if not message_type:
                self.logger.warning("收到无类型消息，忽略")
                return False
            
            # 查找对应的处理器
            handlers = self._get_handlers_for_type(message_type)
            
            if not handlers:
                self.logger.debug(f"未找到消息类型 '{message_type}' 的处理器")
                return False
            
            # 异步执行所有处理器
            tasks = []
            for handler in handlers:
                task = asyncio.create_task(
                    self._execute_handler(handler, data)
                )
                tasks.append(task)
            
            # 等待所有处理器完成
            await asyncio.gather(*tasks, return_exceptions=True)
            
            self.logger.debug(f"成功处理消息类型: {message_type}, 处理器数量: {len(handlers)}")
            return True
            
        except json.JSONDecodeError:
            self.logger.error("消息JSON解析失败")
            return False
        except Exception as e:
            self.logger.error(f"处理消息时发生错误: {e}")
            return False
    
    def _get_handlers_for_type(self, message_type: str) -> List[MessageHandler]:
        """获取指定消息类型的所有处理器"""
        handlers = []
        
        # 获取精确匹配的处理器
        if message_type in self._handlers:
            handlers.extend(self._handlers[message_type])
        
        # 获取通配符处理器（如果有实现的话）
        if "*" in self._handlers:
            handlers.extend(self._handlers["*"])
        
        return handlers
    
    async def _execute_handler(self, handler: MessageHandler, message: Dict[str, Any]):
        """执行单个处理器"""
        try:
            await handler.handler_func(message)
            
            # 如果是临时处理器且执行成功，自动取消注册（可选）
            # if handler.is_temporary:
            #     self.unregister_temporary_handler(handler.handler_id)
                
        except Exception as e:
            self.logger.error(f"处理器执行失败 (ID: {handler.handler_id}): {e}")
    
    def get_registered_types(self) -> List[str]:
        """获取已注册的消息类型列表"""
        return list(self._handlers.keys())
    
    def get_handler_count(self, message_type: str = None) -> int:
        """获取处理器数量"""
        if message_type:
            return len(self._handlers.get(message_type, []))
        else:
            total = 0
            for handlers in self._handlers.values():
                total += len(handlers)
            return total
    
    def clear_temporary_handlers(self):
        """清除所有临时处理器"""
        async def clear():
            async with self._lock:
                # 只保留永久处理器
                for message_type in list(self._handlers.keys()):
                    self._handlers[message_type] = [
                        h for h in self._handlers[message_type] 
                        if not h.is_temporary
                    ]
                    
                    # 如果该类型没有处理器了，移除类型
                    if not self._handlers[message_type]:
                        del self._handlers[message_type]
                
                self._temporary_handler_ids.clear()
        
        asyncio.create_task(clear())
        self.logger.info("已清除所有临时消息处理器")


# 创建全局单例实例
_message_manager_instance = None


def get_message_manager() -> WebSocketMessageManager:
    """获取消息管理器实例（单例模式）"""
    global _message_manager_instance
    if _message_manager_instance is None:
        _message_manager_instance = WebSocketMessageManager()
    return _message_manager_instance


# 提供便捷的全局实例引用
message_manager = get_message_manager()