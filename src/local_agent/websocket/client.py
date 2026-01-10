#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket client
Implements WebSocket connection, message sending/receiving, and reconnection mechanism
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
    """WebSocketclientclass"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Connection status
        self.connected = False
        self.connection = None
        self.reconnect_task = None
        self.reconnect_attempts = 0
        
        # Stop [flag] - [used to determine if service was stopped] via stop method
        self.stopped_by_user = False
        
        # Callback function
        self.on_message_callback: Optional[Callable] = None
        self.on_connect_callback: Optional[Callable] = None
        self.on_disconnect_callback: Optional[Callable] = None
        self.on_error_callback: Optional[Callable] = None
        
        # Message queue
        self.message_queue = asyncio.Queue()
        self.send_task = None
        self.receive_task = None
        
        # [Authentication keepalive task]
        self.auth_keepalive_task = None
        self.auth_check_interval = 300  # Check every 5 minutes
        
        # Message management [manager and] sender
        self.message_manager = get_message_manager()
        self.message_sender = get_message_sender()
    
    async def connect(self) -> bool:
        """[Connect to] WebSocket service [server]"""
        if self.connected:
            self.logger.warning("WebSocket client already connected")
            return True
        
        websocket_url = self.config.get('websocket_url', 'ws://localhost:8765')
        
        try:
            self.logger.info(f"Connecting to WebSocket server: {websocket_url}")
            
            # Get authorization [header]
            headers = await self._get_auth_headers()

            self.logger.info(f"WebSocket request headers: {headers}")

            # [Establish] connection
            self.connection = await websockets.connect(
                websocket_url,
                extra_headers=headers,
                ping_interval=20,  # Send ping every 20 seconds
                ping_timeout=10,   # Disconnect if no pong received within 10 seconds
                close_timeout=10   # Close timeout time
            )
            
            self.connected = True
            self.reconnect_attempts = 0
            self.stopped_by_user = False  # Reset stop flag
            
            self.logger.info("WebSocket connection successful")
            
            # Setup message management [manager and] sender [with] WebSocket client [reference]
            self.message_manager.set_websocket_client(self)
            self.message_sender.set_websocket_client(self)
            
            # Start message send [and] receive [tasks]
            self.send_task = asyncio.create_task(self._send_messages())
            self.receive_task = asyncio.create_task(self._receive_messages())
            
            # Start [authentication keepalive task]
            self.auth_keepalive_task = asyncio.create_task(self._auth_keepalive())
            
            # [Call] connection callback
            if self.on_connect_callback:
                await self.on_connect_callback()
            
            return True
            
        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            self.connected = False
            
            # [调用]ErrorCallback
            if self.on_error_callback:
                await self.on_error_callback(e)
            
            return False
    
    async def disconnect(self, stopped_by_user: bool = False):
        """
        Disconnect WebSocket connection
        
        Args:
            stopped_by_user: Whether the connection is being stopped by user initiative
        """
        if not self.connected:
            return
        
        self.logger.info("Disconnecting WebSocket connection...")
        
        # Setup stop [flag]
        self.stopped_by_user = stopped_by_user
        
        # [Cancel tasks]
        if self.send_task:
            self.send_task.cancel()
        if self.receive_task:
            self.receive_task.cancel()
        if self.auth_keepalive_task:
            self.auth_keepalive_task.cancel()
        
        # [Close] connection
        if self.connection:
            await self.connection.close()
        
        self.connected = False
        self.connection = None
        
        # [Call] disconnect callback
        if self.on_disconnect_callback:
            await self.on_disconnect_callback()
        
        self.logger.info("WebSocket connection disconnected")
    
    async def _get_auth_headers(self) -> dict:
        """Get authorization [request headers]"""
        
        # Wait for auth token to complete initialization
        token = await self._wait_for_auth_token()
        
        if token:
            return {"Authorization": f"Bearer {token}"}
        else:
            self.logger.warning("No valid token obtained, using unauthenticated connection")
            return {}
    
    async def _wait_for_auth_token(self, timeout: int = 30) -> Optional[str]:
        """[Wait for] auth_token [to complete] initialization"""
        import asyncio
        from ..core.global_cache import cache
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # [Get token from] cache
            token = cache.get(AUTHORIZATION_CACHE_KEY)
            if token:
                self.logger.info("Successfully obtained token")
                return token
            else:
                from ..core.auth import auth_token
                auth_token()
                return cache.get(AUTHORIZATION_CACHE_KEY)
                
        
        self.logger.error(f"Waiting for token timeout ({timeout} seconds)")
        return None
    
    async def _refresh_auth_token(self) -> bool:
        """[Refresh authentication] token"""
        from ..core.auth import refresh_token, auth_token
        
        try:
            # [First] try [to refresh] token
            self.logger.info("Attempting to refresh token...")
            if refresh_token():
                self.logger.info("Token refresh successful")
                return True
            
            # [If refresh] fails [then] get [new token]
            self.logger.info("Refresh failed, attempting to obtain token again...")
            if auth_token():
                self.logger.info("Token re-obtained successfully")
                return True
            
            self.logger.error("Token obtain failed")
            return False
            
        except Exception as e:
            self.logger.error(f"Authentication token refresh failed: {e}")
            return False
    
    async def _handle_auth_expired(self) -> bool:
        """[Handle] token [expiration]"""
        # [First] try [to refresh]
        if await self._refresh_auth_token():
            return True
        
        # [If refresh] fails [then retry every] 1 minute
        retry_interval = 60  # 1 minute
        
        while True:
            self.logger.info(f"Waiting for {retry_interval} seconds before retry authentication...")
            await asyncio.sleep(retry_interval)
            
            if await self._refresh_auth_token():
                return True
    
    async def _auth_keepalive(self):
        """[Authentication keepalive task], [periodically] check token [status]"""
        while self.connected:
            try:
                # Wait for check [interval]
                await asyncio.sleep(self.auth_check_interval)
                
                # Check if token [exists]
                from ..core.global_cache import cache
                token = cache.get(AUTHORIZATION_CACHE_KEY)
                
                if not token:
                    self.logger.warning("Detected token expired, attempting to refresh...")
                    if not await self._refresh_auth_token():
                        self.logger.error("Token refresh failed, WebSocket connection may be affected")
                        # [Continue keepalive], [do not interrupt] WebSocket connection
                else:
                    self.logger.debug("Token status normal")
                    
            except asyncio.CancelledError:
                # [Task cancelled], [exit normally]
                break
            except Exception as e:
                self.logger.error(f"Authentication keepalive task exception: {e}")
                # [Continue keepalive], [do not interrupt] WebSocket connection
    
    async def send_message(self, message: Any):
        """[Send message to] service [server]"""
        if not self.connected:
            self.logger.warning("WebSocket not connected, unable to send message")
            return False
        
        try:
            # If [it's a dictionary], [convert to] JSON [string]
            if isinstance(message, dict):
                message = json.dumps(message)
            
            await self.connection.send(message)
            self.logger.debug(f"Sending message: {message}")
            return True
            
        except Exception as e:
            self.logger.error(f"Send message failed: {e}")
            await self._handle_connection_error(e)
            return False
    
    async def _send_messages(self):
        """[Send messages from queue]"""
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
                self.logger.error(f"Send message task error: {e}")
                break
    
    async def _receive_messages(self):
        """[Receive] service [server messages]"""
        while self.connected:
            try:
                message = await asyncio.wait_for(
                    self.connection.recv(),
                    timeout=1.0
                )
                
                self.logger.debug(f"Received message: {message}")
                
                # [Use] message management [manager to process] message
                handled = await self.message_manager.handle_message(message)
                
                # If message management [manager did not process], [call original] message callback
                if not handled and self.on_message_callback:
                    await self.on_message_callback(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Receive message task error: {e}")
                # await self._handle_connection_error(e)
                break

    def is_connected(self):
        return self.connected

    async def _handle_connection_error(self, error: Exception):
        """[Handle connection] error"""
        self.logger.error(f"WebSocket connection error: {error}")
        
        # [Call] error callback
        if self.on_error_callback:
            await self.on_error_callback(error)
        
        # Disconnect connection [and] try [to reconnect]
        await self.disconnect()
        await self._start_reconnect()
    
    async def _start_reconnect(self):
        """Start [reconnection mechanism]"""
        # Check [if service was stopped] via stop method, if [yes then do not reconnect]
        if self.stopped_by_user:
            self.logger.info("Detected service stopped by stop method, not reconnecting")
            return
        
        if self.reconnect_task and not self.reconnect_task.done():
            return
        
        max_attempts = self.config.get('max_restart_attempts', 3)
        if self.reconnect_attempts >= max_attempts:
            self.logger.error(f"Reached maximum reconnection attempts: {max_attempts}")
            return
        
        self.reconnect_attempts += 1
        reconnect_interval = self.config.get('websocket_reconnect_interval', 10)
        
        self.logger.info(f"Attempting reconnection {self.reconnect_attempts} times after {reconnect_interval} seconds...")
        
        self.reconnect_task = asyncio.create_task(self._reconnect_after_delay(reconnect_interval))
    
    async def _reconnect_after_delay(self, delay: int):
        """[Reconnect after delay]"""
        await asyncio.sleep(delay)
        
        if not self.connected:
            # Check token status，if [expired then handle authentication first]
            from ..core.global_cache import cache
            token = cache.get(AUTHORIZATION_CACHE_KEY)
            
            if not token:
                self.logger.info("Detected token expired, handling authentication first...")
                if not await self._handle_auth_expired():
                    self.logger.error("Authentication handling failed, unable to reconnect")
                    return
            
            await self.connect()
    
    def set_on_message(self, callback: Callable):
        """Set [message receive callback]"""
        self.on_message_callback = callback
    
    def set_on_connect(self, callback: Callable):
        """Set [connection] success [callback]"""
        self.on_connect_callback = callback
    
    def set_on_disconnect(self, callback: Callable):
        """Set [disconnect callback]"""
        self.on_disconnect_callback = callback
    
    def set_on_error(self, callback: Callable):
        """Set error [callback]"""
        self.on_error_callback = callback
    
    def get_status(self) -> dict:
        """Get client [status]"""
        return {
            "connected": self.connected,
            "reconnect_attempts": self.reconnect_attempts,
            "websocket_url": self.config.get('websocket_url'),
            "last_activity": datetime.now().isoformat()
        }
    
    async def __aenter__(self):
        """Asynchronous [context] management [manager entry]"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous [context] management [manager exit]"""
        await self.disconnect()
