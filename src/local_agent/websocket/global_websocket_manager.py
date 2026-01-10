#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global WebSocket manager
Singleton pattern, supports one-line code to start and stop WebSocket service

Usage examples:
1. Start WebSocket service:
   from src.local_agent.websocket.global_websocket_manager import websocket_manager
   await websocket_manager.start()

2. Stop WebSocket service:
   await websocket_manager.stop()

3. Restart WebSocket service:
   await websocket_manager.restart()

4. Send message:
   await websocket_manager.send_message({"type": "heartbeat"})

5. Check connection status:
   if websocket_manager.is_connected():
       print("WebSocket is connected")
"""

import asyncio
from typing import Dict, Any, Optional, Callable

from ..logger import get_logger
from .websocket_manager import WebSocketManager
from .message_handler import register_websocket_handlers


class GlobalWebSocketManager:
    """Global WebSocket manager (singleton pattern)"""
    
    _instance: Optional['GlobalWebSocketManager'] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """Initialize global WebSocket manager"""
        if GlobalWebSocketManager._instance is not None:
            raise RuntimeError("Please use the get_ince() method to obtain singleton instances")
        
        self.logger = get_logger(__name__)
        self._websocket_manager: Optional[WebSocketManager] = None
        self._application = None
        self._initialized = False
        
        GlobalWebSocketManager._instance = self
    
    @classmethod
    async def get_instance(cls) -> 'GlobalWebSocketManager':
        """Get global WebSocket manager singleton instance"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    async def initialize(self, application=None) -> bool:
        """
        Initialize WebSocket manager
        
        Args:
            application: Application instance (optional, used for message handler registration)
            
        Returns:
            bool: Whether initialization was successful
        """
        if self._initialized:
            self.logger.info("WebSocket manager already initialized")
            return True
            
        try:
            self.logger.info("Initializing global WebSocket manager...")
            
            # Create WebSocket manager instance
            self._websocket_manager = WebSocketManager()
            self._application = application
            
            self._initialized = True
            self.logger.info("Global WebSocket manager initialization successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Global WebSocket manager initialization failed: {e}")
            return False
    
    async def start(self, application=True) -> bool:
        """
        Start WebSocket service
        
        Args:
            application: Application instance (optional)
            
        Returns:
            bool: Whether startup was successful
        """
        try:
            # Ensure already initialized
            if not self._initialized:
                if not await self.initialize(application):
                    return False
            
            if not self._websocket_manager:
                self.logger.error("WebSocket manager not initialized")
                return False
            
            # Start WebSocket service
            return await self._websocket_manager.start(application)
            
        except Exception as e:
            self.logger.error(f"WebSocket service startup failed: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop WebSocket service
        
        Returns:
            bool: Whether stop was successful
        """
        try:
            if not self._websocket_manager:
                self.logger.warning("WebSocket manager not initialized, no need to stop")
                return True
            
            # Stop WebSocket service
            return await self._websocket_manager.stop()
            
        except Exception as e:
            self.logger.error(f"WebSocket service stop failed: {e}")
            return False
    
    async def restart(self, application=None) -> bool:
        """
        Restart WebSocket service
        
        Args:
            application: Application instance (optional)
            
        Returns:
            bool: Whether restart was successful
        """
        try:
            # First stop then start
            await self.stop()
            await asyncio.sleep(1)  # Wait 1 second
            return await self.start(application)
            
        except Exception as e:
            self.logger.error(f"WebSocket service restart failed: {e}")
            return False
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send WebSocket message
        
        Args:
            message: Message dictionary to send
            
        Returns:
            bool: Whether send was successful
        """
        try:
            if not self._websocket_manager:
                self.logger.warning("WebSocket manager not initialized, unable to send message")
                return False
            
            return await self._websocket_manager.send_message(message)
            
        except Exception as e:
            self.logger.error(f"Send WebSocket message failed: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        Check WebSocket connection status
        
        Returns:
            bool: Whether connected
        """
        try:
            if not self._websocket_manager:
                return False
            
            return self._websocket_manager.is_connected()
            
        except Exception as e:
            self.logger.error(f"Check WebSocket connection status failed: {e}")
            return False
    
    def is_supposed(self) -> bool:
        # Whether should run
        if not self._websocket_manager:
            return False
        return self._websocket_manager.is_supposed()
    
    def is_running(self) -> bool:
        """
        Check WebSocket service running status
        
        Returns:
            bool: Whether running
        """
        try:
            if not self._websocket_manager:
                return False
            
            return self._websocket_manager.is_running()
            
        except Exception as e:
            self.logger.error(f"Check WebSocket service running status failed: {e}")
            return False
    
    def set_on_connect(self, callback: Callable):
        """
        Set connection success callback
        
        Args:
            callback: Callback function
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_connect(callback)

    def set_on_disconnect(self, callback: Callable):
        """
        Set connection disconnect callback
        
        Args:
            callback: Callback function
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_disconnect(callback)

    def set_on_message(self, callback: Callable):
        """
        Set message receive callback
        
        Args:
            callback: Callback function
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_message(callback)

    def set_on_error(self, callback: Callable):
        """
        Set error callback
        
        Args:
            callback: Callback function
        """
        if self._websocket_manager:
            self._websocket_manager.set_on_error(callback)


# Create global singleton instance
_global_websocket_manager: Optional[GlobalWebSocketManager] = None


async def get_websocket_manager() -> GlobalWebSocketManager:
    """
    Get global WebSocket manager instance
    
    Returns:
        GlobalWebSocketManager: Global WebSocket manager instance
    """
    global _global_websocket_manager
    
    if _global_websocket_manager is None:
        _global_websocket_manager = await GlobalWebSocketManager.get_instance()
    
    return _global_websocket_manager


# Convenient functions - one-line code to start and stop WebSocket service

async def start_websocket(application=None) -> bool:
    """
    One-line code to start WebSocket service
    
    Args:
        application: Application instance (optional)
        
    Returns:
        bool: Whether startup was successful
    """
    manager = await get_websocket_manager()
    return await manager.start(application)


async def stop_websocket() -> bool:
    """
    One-line code to stop WebSocket service
    
    Returns:
        bool: Whether stop was successful
    """
    manager = await get_websocket_manager()
    return await manager.stop()


async def restart_websocket(application=None) -> bool:
    """
    One-line code to restart WebSocket service
    
    Args:
        application: Application instance (optional)
        
    Returns:
        bool: Whether restart was successful
    """
    manager = await get_websocket_manager()
    return await manager.restart(application)


async def send_websocket_message(message: Dict[str, Any]) -> bool:
    """
    One-line code to send WebSocket message
    
    Args:
        message: Message dictionary to send
        
    Returns:
        bool: Whether send was successful
    """
    manager = await get_websocket_manager()
    return await manager.send_message(message)


def is_websocket_connected() -> bool:
    """
    One-line code to check WebSocket connection status
    
    Returns:
        bool: Whether connected
    """
    if _global_websocket_manager is None:
        return False
    return _global_websocket_manager.is_connected()


def is_websocket_running() -> bool:
    """
    One-line code to check WebSocket service running status
    
    Returns:
        bool: Whether running
    """
    if _global_websocket_manager is None:
        return False
    return _global_websocket_manager.is_running()


# Global singleton instance (delayed initialization)
websocket_manager = None


def get_websocket_manager_sync() -> Optional[GlobalWebSocketManager]:
    """Synchronous way to get global WebSocket manager instance
    
    Returns:
        Optional[GlobalWebSocketManager]: Global WebSocket manager instance, returns None if not initialized
    """
    return _global_websocket_manager