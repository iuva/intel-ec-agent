#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket message manager
Implements unified message processing and temporary registration mechanism, supports temporary message handler registration from any global location

Usage examples:
1. Register permanent message handler (registered when application starts)
   from local_agent.websocket.message_manager import message_manager
   
   @message_manager.register_handler("healthy")
   async def handle_ping(message):
       # Handle ping message
       pass

2. Temporarily register message handler (register from any location)
   handler_id = message_manager.register_temporary_handler("custom_type", async_handler_func)
   
   # Unregister after use
   message_manager.unregister_temporary_handler(handler_id)

3. Send message
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
    """Message handler definition"""
    handler_id: str
    message_type: str
    handler_func: Callable
    is_temporary: bool = False
    description: str = ""


class WebSocketMessageManager:
    """WebSocket message manager"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Message handler registry
        self._handlers: Dict[str, List[MessageHandler]] = {}
        
        # Temporary handler ID set
        self._temporary_handler_ids: Set[str] = set()
        
        # WebSocket client reference
        self._websocket_client = None
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        self.logger.info("WebSocket message manager initialized")
    
    def set_websocket_client(self, websocket_client):
        """Set WebSocket client reference"""
        self._websocket_client = websocket_client
        self.logger.info("WebSocket client reference set")
    
    def register_handler(self, message_type: str, description: str = "") -> Callable:
        """
        Register permanent message handler using decorator
        
        Args:
            message_type: Message type
            description: Handler description
            
        Returns:
            Callable: Decorator function
        """
        def decorator(handler_func: Callable) -> Callable:
            self._register_permanent_handler(message_type, handler_func, description)
            return handler_func
        return decorator
    
    def register_temporary_handler(self, message_type: str, handler_func: Callable, 
                                 description: str = "") -> str:
        """
        Register temporary message handler
        
        Args:
            message_type: Message type
            handler_func: Handler function
            description: Handler description
            
        Returns:
            str: Handler ID, used for unregistering
        """
        handler_id = str(uuid.uuid4())
        
        async def wrapper(message: Dict[str, Any]):
            """Wrapper for handling temporary handlers"""
            try:
                await handler_func(message)
            except Exception as e:
                self.logger.error(f"Temporary handler execution failed (ID: {handler_id}): {e}")
        
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
        
        # Asynchronous registration
        asyncio.create_task(register())
        
        self.logger.info(f"Registered temporary message handler (ID: {handler_id}) - Type: {message_type}")
        return handler_id
    
    def unregister_temporary_handler(self, handler_id: str) -> bool:
        """
        Unregister temporary message handler
        
        Args:
            handler_id: Handler ID
            
        Returns:
            bool: Whether unregistration was successful
        """
        async def unregister():
            async with self._lock:
                if handler_id not in self._temporary_handler_ids:
                    return False
                
                # Remove this handler from all message types
                for message_type in list(self._handlers.keys()):
                    self._handlers[message_type] = [
                        h for h in self._handlers[message_type] 
                        if h.handler_id != handler_id
                    ]
                    
                    # If this type has no handlers left, remove the type
                    if not self._handlers[message_type]:
                        del self._handlers[message_type]
                
                self._temporary_handler_ids.discard(handler_id)
                return True
        
        # Asynchronous unregistration
        asyncio.create_task(unregister())
        
        self.logger.info(f"Unregistered temporary message handler (ID: {handler_id})")
        return True
    
    def _register_permanent_handler(self, message_type: str, handler_func: Callable, 
                                  description: str = ""):
        """Register permanent message handler"""
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
                self.logger.info(f"Registered permanent message handler - Type: {message_type}, Description: {description}, Total handlers: {len(self._handlers.values())}")
        
        # Asynchronous registration
        asyncio.create_task(register())

    
    async def handle_message(self, message: str) -> bool:
        """
        Process WebSocket message
        
        Args:
            message: Raw message string
            
        Returns:
            bool: Whether processing was successful
        """
        try:
            # Parse JSON message
            data = message
            if isinstance(message, str):
                data = json.loads(message)
            
            message_type = data.get('type', '')
            
            if not message_type:
                self.logger.warning("Received message without type, ignoring")
                return False
            
            # Find corresponding handlers
            handlers = self._get_handlers_for_type(message_type)
            
            if not handlers:
                self.logger.debug(f"No handler found for message type '{message_type}'")
                return False
            
            # Asynchronously execute all handlers
            tasks = []
            for handler in handlers:
                task = asyncio.create_task(
                    self._execute_handler(handler, data)
                )
                tasks.append(task)
            
            # Wait for all handlers to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
            self.logger.debug(f"Successfully processed message type: {message_type}, handler count: {len(handlers)}")
            return True
            
        except json.JSONDecodeError:
            self.logger.error("Message JSON parsing failed")
            return False
        except Exception as e:
            self.logger.error(f"Error occurred while processing message: {e}")
            return False
    
    def _get_handlers_for_type(self, message_type: str) -> List[MessageHandler]:
        """Get all handlers for specified message type"""
        handlers = []
        
        # Get exact match handlers
        if message_type in self._handlers:
            handlers.extend(self._handlers[message_type])
        
        # Get wildcard handlers (if implemented)
        if "*" in self._handlers:
            handlers.extend(self._handlers["*"])
        
        return handlers
    
    async def _execute_handler(self, handler: MessageHandler, message: Dict[str, Any]):
        """Execute single handler"""
        try:
            await handler.handler_func(message)
            
            # If it's a temporary handler and execution successful, automatically unregister (optional)
            # if handler.is_temporary:
            #     self.unregister_temporary_handler(handler.handler_id)
                
        except Exception as e:
            self.logger.error(f"Handler execution failed (ID: {handler.handler_id}): {e}")
    
    def get_registered_types(self) -> List[str]:
        """Get list of registered message types"""
        return list(self._handlers.keys())
    
    def get_handler_count(self, message_type: str = None) -> int:
        """Get handler count"""
        if message_type:
            return len(self._handlers.get(message_type, []))
        else:
            total = 0
            for handlers in self._handlers.values():
                total += len(handlers)
            return total
    
    def clear_temporary_handlers(self):
        """Clear all temporary handlers"""
        async def clear():
            async with self._lock:
                # Only keep permanent handlers
                for message_type in list(self._handlers.keys()):
                    self._handlers[message_type] = [
                        h for h in self._handlers[message_type] 
                        if not h.is_temporary
                    ]
                    
                    # If this type has no handlers left, remove the type
                    if not self._handlers[message_type]:
                        del self._handlers[message_type]
                
                self._temporary_handler_ids.clear()
        
        asyncio.create_task(clear())
        self.logger.info("Cleared all temporary message handlers")


# Create global singleton instance
_message_manager_instance = None


def get_message_manager() -> WebSocketMessageManager:
    """Get message manager instance (singleton pattern)"""
    global _message_manager_instance
    if _message_manager_instance is None:
        _message_manager_instance = WebSocketMessageManager()
    return _message_manager_instance


# Provide convenient global instance reference
message_manager = get_message_manager()