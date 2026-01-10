#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket message sender
Implements global WebSocket message sending functionality from any location, supports two sending modes:
1. Direct sending mode: Returns failure immediately if connection fails
2. Queue caching mode: Caches messages when connection fails, automatically retransmits when connection is restored

Usage examples:
1. Direct message sending (suitable for scenarios where delivery is not guaranteed)
   from local_agent.websocket.message_sender import send_message
   await send_message({"type": "status", "data": "running"})

2. Queue-based message sending (suitable for important messages that require guaranteed delivery)
   from local_agent.websocket.message_sender import send_message_with_queue
   await send_message_with_queue({"type": "important", "data": "critical"}, max_retries=5)

3. Send message with callback
   async def callback(response):
       print(f"Received response: {response}")
   
   await send_message_with_queue(
       {"type": "query", "data": "some_query"},
       response_callback=callback,
       timeout=10
   )

4. Check connection status
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
    """Pending message to be sent"""
    message_id: str
    message: Dict[str, Any]
    timestamp: float
    response_callback: Optional[Callable] = None
    timeout: float = 30.0
    
    # Retry-related fields (optional, for queued messages)
    retry_count: int = 0
    max_retries: int = 3
    last_retry_time: float = 0.0


class WebSocketMessageSender:
    """WebSocket message sender"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # WebSocket client reference
        self._websocket_client = None
        
        # Pending message queue
        self._pending_messages: Dict[str, PendingMessage] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        # Message ID counter
        self._message_id_counter = 0
        
        # Cleanup task
        self._cleanup_task = None
        
        self.logger.info("WebSocket message sender initialized")
    
    def set_websocket_client(self, websocket_client):
        """Set WebSocket client reference"""
        self._websocket_client = websocket_client
        self.logger.info("WebSocket client reference set")
        
        # Register connection recovery callback
        if hasattr(websocket_client, 'on_connect_callback'):
            # Check if already registered (by checking if current callback is the one we registered)
            current_callback = websocket_client.on_connect_callback
            
            # If current callback is not registered by us, or callback is None, then register
            if current_callback is None or not hasattr(current_callback, '__name__') or current_callback.__name__ != 'connection_restored_callback':
                # Save original callback
                original_callback = current_callback
                
                async def connection_restored_callback():
                    # Call original callback (if exists)
                    if original_callback:
                        await original_callback()
                    # Call message sender's connection recovery handler
                    await self.on_connection_restored()
                
                websocket_client.on_connect_callback = connection_restored_callback
                self.logger.info("WebSocket connection recovery callback registered")
            else:
                self.logger.debug("WebSocket connection recovery callback already registered, skipping duplicate registration")
        
        # Start cleanup task
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_messages())
    
    def is_connected(self) -> bool:
        """Check WebSocket connection status"""
        if self._websocket_client is None:
            return False
        return self._websocket_client.is_connected()
    
    async def send_message(self, message: Dict[str, Any], 
                         response_callback: Optional[Callable] = None,
                         timeout: float = 30.0) -> bool:
        """
        Send WebSocket message (direct send, not queued)
        
        Args:
            message: Message content (dict)
            response_callback: Response callback function
            timeout: Timeout in seconds
            
        Returns:
            bool: Whether send was successful
        """
        if not self.is_connected():
            self.logger.warning("WebSocket not connected, unable to send message")
            return False
        
        # Generate message ID
        message_id = self._generate_message_id()
        
        # Add message ID to message
        message_with_id = message.copy()
        message_with_id['message_id'] = message_id
        
        # Create pending message
        pending_message = PendingMessage(
            message_id=message_id,
            message=message_with_id,
            timestamp=time.time(),
            response_callback=response_callback,
            timeout=timeout
        )

        
        try:
            # Send message
            sent_res = await self._websocket_client.send_message(json.dumps(message_with_id))
            if not sent_res:
                # Add to pending send queue
                async with self._lock:
                    self._pending_messages[message_id] = pending_message
            
            self.logger.debug(f"Message sent successfully (ID: {message_id}), type: {message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            self.logger.error(f"Message send failed (ID: {message_id}): {e}")
            
            # Remove from pending send queue
            async with self._lock:
                self._pending_messages.pop(message_id, None)
            
            return False

    async def send_message_with_queue(self, message: Dict[str, Any], 
                                    response_callback: Optional[Callable] = None,
                                    timeout: float = 30.0,
                                    max_retries: int = 3) -> bool:
        """
        Send WebSocket message (with queue caching and retry mechanism)
        
        Args:
            message: Message content (dict)
            response_callback: Response callback function
            timeout: Timeout in seconds
            max_retries: Maximum retry attempts
            
        Returns:
            bool: Whether send was successful or added to queue
        """
        # Generate message ID
        message_id = self._generate_message_id()
        
        # Add message ID to message
        message_with_id = message.copy()
        message_with_id['message_id'] = message_id
        
        # Create pending message (with retry info)
        pending_message = PendingMessage(
            message_id=message_id,
            message=message_with_id,
            timestamp=time.time(),
            response_callback=response_callback,
            timeout=timeout
        )
        
        # Add retry info
        pending_message.retry_count = 0
        pending_message.max_retries = max_retries
        pending_message.last_retry_time = time.time()

        # Try sending immediately
        if self._websocket_client:
            cent_res = await self._websocket_client.send_message(pending_message)
            if not cent_res:
                # Add to pending send queue
                async with self._lock:
                    self._pending_messages[message_id] = pending_message


    async def _try_send_message(self, pending_message: PendingMessage) -> bool:
        """Try to send message, add to retry queue if failed"""
        if not self.is_connected():
            # Connection not established, log but don't remove message, wait for connection recovery to retry
            self.logger.info(f"WebSocket not connected, message added to queue (ID: {pending_message.message_id}), "
                           f"type: {pending_message.message.get('type', 'unknown')}")
            return True  # Return True to indicate message has been accepted for processing
        
        try:
            # Send message
            await self._websocket_client.send_message(json.dumps(pending_message.message))
            
            self.logger.debug(f"Message sent successfully (ID: {pending_message.message_id}), "
                            f"type: {pending_message.message.get('type', 'unknown')}")
            return True
            
        except Exception as e:
            # Send failed, handle retry logic
            pending_message.retry_count += 1
            pending_message.last_retry_time = time.time()
            
            if pending_message.retry_count <= pending_message.max_retries:
                # Still have retry attempts, log and keep message in queue
                self.logger.warning(f"Message send failed, will retry {pending_message.retry_count} times "
                                  f"(ID: {pending_message.message_id}): {e}")
                
                # Calculate next retry time (exponential backoff)
                retry_delay = min(2 ** pending_message.retry_count, 60)  # Maximum 60 seconds
                
                # Asynchronously schedule retry
                asyncio.create_task(self._retry_message(pending_message, retry_delay))
                return True
            else:
                # Retry attempts exhausted, remove message
                self.logger.error(f"Message send failed, retry attempts exhausted (ID: {pending_message.message_id}): {e}")
                
                async with self._lock:
                    self._pending_messages.pop(pending_message.message_id, None)
                
                # Execute failure callback (if exists)
                if pending_message.response_callback:
                    try:
                        error_response = {
                            'type': 'error',
                            'response_to': pending_message.message_id,
                            'error': f'Message sending failed, retry attempts exhausted: {e}'
                        }
                        
                        if asyncio.iscoroutinefunction(pending_message.response_callback):
                            await pending_message.response_callback(error_response)
                        else:
                            pending_message.response_callback(error_response)
                            
                    except Exception as callback_error:
                        self.logger.error(f"Failed callback execution failed (message ID: {pending_message.message_id}): {callback_error}")
                
                return False

    async def _retry_message(self, pending_message: PendingMessage, delay: float):
        """Retry sending message after delay"""
        await asyncio.sleep(delay)
        
        # Check if message is still in queue (may have been processed or expired)
        async with self._lock:
            if pending_message.message_id not in self._pending_messages:
                return
        
        # Try sending again
        await self._try_send_message(pending_message)

    async def on_connection_restored(self):
        """WebSocket connection recovery callback, resend queued messages"""
        self.logger.info("WebSocket connection restored, starting to resend queued messages")
        
        # Get all messages in current queue
        async with self._lock:
            messages_to_retry = list(self._pending_messages.values())
        
        # Resend all messages
        for pending_message in messages_to_retry:
            # Reset retry count (start counting again after connection recovery)
            pending_message.retry_count = 0
            pending_message.last_retry_time = time.time()
            
            # Asynchronously resend
            asyncio.create_task(self._try_send_message(pending_message))
    
    async def handle_response(self, response_message: Dict[str, Any]):
        """
        Process response message
        
        Args:
            response_message: Response message
        """
        message_id = response_message.get('response_to')
        if not message_id:
            return
        
        # Find corresponding pending message
        async with self._lock:
            pending_message = self._pending_messages.pop(message_id, None)
        
        if pending_message and pending_message.response_callback:
            try:
                # Execute callback function
                if asyncio.iscoroutinefunction(pending_message.response_callback):
                    await pending_message.response_callback(response_message)
                else:
                    pending_message.response_callback(response_message)
                
                self.logger.debug(f"Response callback executed successfully (message ID: {message_id})")
                
            except Exception as e:
                self.logger.error(f"Response callback execution failed (message ID: {message_id}): {e}")
    
    def _generate_message_id(self) -> str:
        """Generate message ID"""
        self._message_id_counter += 1
        return f"msg_{self._message_id_counter}_{int(time.time())}"
    
    async def _cleanup_expired_messages(self):
        """Clean up expired pending messages"""
        while True:
            try:
                await asyncio.sleep(10)  # Clean up every 10 seconds
                
                current_time = time.time()
                expired_messages = []
                
                # Find expired messages
                async with self._lock:
                    for message_id, pending_message in self._pending_messages.items():
                        if current_time - pending_message.timestamp > pending_message.timeout:
                            expired_messages.append(message_id)
                
                # Clean up expired messages
                for message_id in expired_messages:
                    async with self._lock:
                        expired_message = self._pending_messages.pop(message_id, None)
                    
                    if expired_message:
                        self.logger.warning(f"Message expired (ID: {message_id}), type: {expired_message.message.get('type', 'unknown')}")
                        
                        # Execute timeout callback (if exists)
                        if expired_message.response_callback:
                            try:
                                timeout_response = {
                                    'type': 'timeout',
                                    'response_to': message_id,
                                    'error': 'Message response timeout'
                                }
                                
                                if asyncio.iscoroutinefunction(expired_message.response_callback):
                                    await expired_message.response_callback(timeout_response)
                                else:
                                    expired_message.response_callback(timeout_response)
                                    
                            except Exception as e:
                                self.logger.error(f"Timeout callback execution failed (message ID: {message_id}): {e}")
                
            except Exception as e:
                self.logger.error(f"Error occurred while cleaning expired messages: {e}")
    
    def get_pending_message_count(self) -> int:
        """Get pending message count"""
        return len(self._pending_messages)
    
    def clear_pending_messages(self):
        """Clear pending message queue"""
        async def clear():
            async with self._lock:
                cleared_count = len(self._pending_messages)
                self._pending_messages.clear()
                
            if cleared_count > 0:
                self.logger.info(f"Cleared {cleared_count} pending messages")
        
        asyncio.create_task(clear())


# Create global singleton instance
_message_sender_instance = None


def get_message_sender() -> WebSocketMessageSender:
    """Get message sender instance (singleton pattern)"""
    global _message_sender_instance
    if _message_sender_instance is None:
        _message_sender_instance = WebSocketMessageSender()
    return _message_sender_instance


# Provide convenient global functions
async def send_message(message: Dict[str, Any], 
                     response_callback: Optional[Callable] = None,
                     timeout: float = 30.0) -> bool:
    """
    Send WebSocket message (global function, direct send not queued)
    
    Args:
        message: Message content (dict)
        response_callback: Response callback function
        timeout: Timeout in seconds
        
    Returns:
        bool: Whether send was successful
    """
    sender = get_message_sender()
    return await sender.send_message(message, response_callback, timeout)


async def send_message_with_queue(message: Dict[str, Any], 
                                response_callback: Optional[Callable] = None,
                                timeout: float = 30.0,
                                max_retries: int = 3) -> bool:
    """
    Send WebSocket message (global function, with queue caching and retry mechanism)
    
    Args:
        message: Message content (dict)
        response_callback: Response callback function
        timeout: Timeout in seconds
        max_retries: Maximum retry attempts
        
    Returns:
        bool: Whether send was successful or added to queue
    """
    sender = get_message_sender()
    return await sender.send_message_with_queue(message, response_callback, timeout, max_retries)


def is_connected() -> bool:
    """Check WebSocket connection status (global function)"""
    sender = get_message_sender()
    return sender.is_connected()


def get_pending_message_count() -> int:
    """Get pending message count (global function)"""
    sender = get_message_sender()
    return sender.get_pending_message_count()


def clear_pending_messages():
    """Clear pending message queue (global function)"""
    sender = get_message_sender()
    sender.clear_pending_messages()