#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Manager
Implements global WebSocket service startup, stop, and management
"""

import asyncio
import json
from typing import Optional, Callable, Any, Dict

from ..config import get_config
from ..logger import get_logger
# Delay import WebSocketClient to avoid circular dependency
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
    """WebSocket manager class, provides global WebSocket service management"""
    
    _instance: Optional['WebSocketManager'] = None
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize WebSocket manager"""
        if self._initialized:
            return
            
        self.config = get_config()
        self.logger = get_logger(__name__)

        self.logger.info("Initializing WebSocket manager")
        
        # WebSocket client instance
        self.client: Optional[WebSocketClient] = None
        
        # Manager status
        self.supposed = False
        self.running = False
        self.connected = False
        
        # Task management
        self.connect_task: Optional[asyncio.Task] = None
        
        # Callback functions
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None
        self.on_message_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        
        # Message manager and sender
        self.message_manager = get_message_manager()
        self.message_sender = get_message_sender()
        
        self._initialized = True
        self.logger.debug("WebSocket manager initialized")
    
    async def start(self, application: Optional[Any] = None) -> bool:
        """
        Start WebSocket service
        
        Args:
            application: Application instance for message handler registration
            
        Returns:
            bool: Whether startup was successful
        """
        self.supposed = True
        if self.running:
            self.logger.warning("WebSocket service already running")
            return True
            
        try:
            self.logger.info("Starting WebSocket service...")
            
            # Initialize WebSocket client (delayed import)
            WebSocketClient = _get_websocket_client()
            self.client = WebSocketClient()
            
            # Set up callback functions
            await self._setup_callbacks()
            
            # Register message handlers (only register permanent handlers, temporary handlers remain unchanged)
            if application:
                register_websocket_handlers(application)
                self.logger.info("Permanent message handlers re-registered")
            else:
                self.logger.info("Application instance not provided, skipping permanent handler registration")
                count = get_message_handler().get_handler_count()
                self.logger.info(f"Existing handler registration count: {count}")
            
            # Start connection
            self.connect_task = asyncio.create_task(self._connect())
            
            # Wait for connection to complete
            await asyncio.sleep(1)  # Wait 1 second for connection to establish
            
            self.running = True
            self.logger.info("WebSocket service startup successful")
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket service startup failed: {e}")
            await self.stop()
            return False
    
    async def stop(self) -> bool:
        """
        Stop WebSocket service
        
        Returns:
            bool: Whether stop was successful
        """
        self.supposed = False
        if not self.running:
            self.logger.info("WebSocket service not running")
            return True
            
        try:
            self.logger.info("Stopping WebSocket service...")
            
            # Cancel connection task
            if self.connect_task:
                self.connect_task.cancel()
                try:
                    await self.connect_task
                except asyncio.CancelledError:
                    pass
            
            # Disconnect WebSocket connection (marked as stopped by user)
            if self.client:
                await self.client.disconnect(stopped_by_user=True)
            
            # Reset status
            self.running = False
            self.connected = False
            self.client = None
            self.connect_task = None
            
            self.logger.info("WebSocket service stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket service stop failed: {e}")
            return False
    
    async def restart(self) -> bool:
        """
        Restart WebSocket service
        
        Returns:
            bool: Whether restart was successful
        """
        self.logger.info("Restarting WebSocket service...")
        
        # Stop first, then start
        await self.stop()
        await asyncio.sleep(1)  # Wait 1 second
        
        return await self.start()
    
    async def _connect(self):
        """Connect to WebSocket service"""
        if not self.client:
            return
            
        try:
            success = await self.client.connect()
            if success:
                self.connected = True
                self.logger.info("WebSocket connection successful")
            else:
                self.logger.error("WebSocket connection failed")
                
        except Exception as e:
            self.logger.error(f"WebSocket connection exception: {e}")
    
    async def _setup_callbacks(self):
        """Set up WebSocket callback functions"""
        if not self.client:
            return
        
        async def on_connect():
            """Connection success callback"""
            self.connected = True
            self.logger.info("WebSocket connection successful")
            
            # Call user-defined callback
            if self.on_connect_callback:
                await self.on_connect_callback()
        
        async def on_disconnect():
            """Connection disconnect callback"""
            self.connected = False
            self.logger.warning("WebSocket connection disconnected")
            
            # Call user-defined callback
            if self.on_disconnect_callback:
                await self.on_disconnect_callback()
        
        async def on_message(message):
            """Message receive callback"""
            self.logger.debug(f"Received WebSocket message: {message}")
            
            # Call user-defined callback
            if self.on_message_callback:
                await self.on_message_callback(message)
        
        async def on_error(error):
            """Error callback"""
            self.logger.error(f"WebSocket error: {error}")
            
            # Call user-defined callback
            if self.on_error_callback:
                await self.on_error_callback(error)
        
        # Set up callbacks
        self.client.set_on_connect(on_connect)
        self.client.set_on_disconnect(on_disconnect)
        self.client.set_on_message(on_message)
        self.client.set_on_error(on_error)
    
    def set_on_connect(self, callback: Callable):
        """Set connection success callback"""
        self.on_connect_callback = callback
    
    def set_on_disconnect(self, callback: Callable):
        """Set connection disconnect callback"""
        self.on_disconnect_callback = callback
    
    def set_on_message(self, callback: Callable):
        """Set message receive callback"""
        self.on_message_callback = callback
    
    def set_on_error(self, callback: Callable):
        """Set error callback"""
        self.on_error_callback = callback
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send WebSocket message
        
        Args:
            message: Message dictionary to send
            
        Returns:
            bool: Whether send was successful
        """
        if not self.connected or not self.client:
            self.logger.warning("WebSocket not connected, unable to send message")
            return False
            
        try:
            await self.message_sender.send_message(message)
            return True
        except Exception as e:
            self.logger.error(f"Send WebSocket message failed: {e}")
            return False

    def is_connected(self) -> bool:
        """Check WebSocket connection status"""
        return self.connected
    
    def is_supposed(self) -> bool:
        """Check WebSocket service running status"""
        return self.supposed
    
    def is_running(self) -> bool:
        """Check WebSocket service running status"""
        return self.running


def get_websocket_manager() -> WebSocketManager:
    """
    Get WebSocket manager instance (global singleton)
    
    Returns:
        WebSocketManager: WebSocket manager instance
    """
    return WebSocketManager()