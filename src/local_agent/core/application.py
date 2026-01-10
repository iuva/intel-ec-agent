#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local agent application
Implements application lifecycle management and multi-level keep-alive mechanism
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, Any

from ..config import get_config
from ..logger import get_logger
from ..api.server import APIServer
from .host_init import HostInit


class LocalAgentApplication:
    """Local [agent] application [main] class"""
    
    def __init__(self):
        self.config = get_config()
        # Delayed logger initialization to avoid triggering log system initialization in constructor
        self._logger = None
        
        # Application status
        self.running = False
        self.start_time = None
        self.restart_count = 0
        self.debug = False  # Default non-debug mode
        
        # Component instances
        self.api_server: Optional[APIServer] = None
        
        # Wake lock instance - set during application initialization
        self.wake_lock = None
        
        # Task management
        self.main_task: Optional[asyncio.Task] = None
        self.health_check_task: Optional[asyncio.Task] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        
        # Signal handling
        self._setup_signal_handlers()
    
    @property
    def logger(self):
        """[Delayed] get logger"""
        if self._logger is None:
            self._logger = get_logger(__name__)
        return self._logger
    
    def _setup_signal_handlers(self):
        """Set [signal handler]"""
        try:
            # Set Ctrl+C handler on Windows
            if sys.platform == "win32":
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            else:
                # Unix system signal handling
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGHUP, self._signal_handler)
        except Exception as e:
            self.logger.warning(f"Signal handler setup failed: {e}")
    
    def _signal_handler(self, signum, frame):
        """[Signal handling] function"""
        self.logger.info(f"Received signal {signum}, gracefully shutting down...")
        self.stop()
    
    async def initialize(self) -> bool:
        """Initialize application"""
        try:
            self.logger.info("Initializing local agent application...")
            
            # Record startup time
            self.start_time = datetime.now()
            
            # Initialize [wake] module - [Called early in] application start, [ensure] system maintains [wake] status
            try:
                from .wake_lock import get_wake_lock
                self.wake_lock = get_wake_lock()
                
                # Get [[wake] lock], [maintain] system [wake] status
                if self.wake_lock.keep_awake():
                    self.logger.info("System wake lock enabled, will keep computer awake")
                else:
                    self.logger.warning("System wake lock enable failed, computer may enter sleep mode")
            except Exception as e:
                self.logger.warning(f"Wake module initialization failed: {e}, application will continue running but may not maintain wake state")
            
            # Initialize API server
            self.api_server = APIServer()
            
            # [Business logic] initialize
            HostInit()

            self.logger.info("Application initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Application initialization failed: {e}")
            return False
    

    
    async def start(self) -> bool:
        """Start application"""
        try:
            if self.running:
                self.logger.warning("Application is already running")
                return True
            
            # [Record] start [mode]
            mode_str = "debug mode" if self.debug else "normal mode"
            self.logger.info(f"Starting local agent application... ({mode_str})")
            
            # [In] debug [mode], [temporarily modify] configuration
            if self.debug:
                self.logger.info("Enabling debug mode configuration...")
            
            # Initialize application
            await self.initialize()
            
            # Start API server ([non-blocking method])
            if self.api_server:
                # [Pass in] debug parameter
                self.api_server_task = asyncio.create_task(self.api_server.start(debug=self.debug))
                # [In] debug [mode], wait time [can be shorter]
                wait_time = 1 if self.debug else 2
                self.logger.debug(f"Waiting for API server startup, wait time: {wait_time} seconds")
                await asyncio.sleep(wait_time)
            
            # Start [keep-alive task]
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            
            self.running = True
            self.logger.info("Local agent application started successfully")
            
            # Start [main] loop
            self.main_task = asyncio.create_task(self._main_loop())
            
            return True
            
        except Exception as e:
            self.logger.error(f"Application startup failed: {e}")
            await self.stop()
            return False
    
    def _handle_queue_response(self, response: Dict[str, Any]):
        """[Handle queue message response]"""
        self.logger.info(f"Queue message response: {response}")
        # [Here can add specific] response [handling logic]


    async def stop(self):
        """Stop application"""
        if not self.running:
            return
        
        self.logger.info("Stopping local agent application...")
        self.running = False
        
        # [Cancel all tasks]
        tasks_to_cancel = []
        
        if self.main_task:
            self.main_task.cancel()
            tasks_to_cancel.append(self.main_task)
        if self.health_check_task:
            self.health_check_task.cancel()
            tasks_to_cancel.append(self.health_check_task)
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            tasks_to_cancel.append(self.keep_alive_task)
        if hasattr(self, 'api_server_task') and self.api_server_task:
            self.api_server_task.cancel()
            tasks_to_cancel.append(self.api_server_task)
        
        # Wait [for all task cancellation to] complete
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        # Stop WebSocket service ([use] global singleton manager)
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.stop():
                self.logger.info("WebSocket service stopped successfully")
            else:
                self.logger.warning("WebSocket service stop failed")
        except Exception as e:
            self.logger.error(f"Error occurred while stopping WebSocket service: {e}")
        
        # Stop API server
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                self.logger.warning(f"Error occurred while stopping API server: {e}")
        
        # [Release wake lock] - [Restore] system [normal sleep behavior when] application stops
        if hasattr(self, 'wake_lock') and self.wake_lock:
            try:
                self.logger.info(f"Starting to release wake lock, current status: {self.wake_lock.is_active()}")
                if self.wake_lock.release():
                    self.logger.info("System wake lock released, computer can enter sleep mode normally")
                else:
                    self.logger.warning("System wake lock release failed")
                self.logger.info(f"Wake lock status after release: {self.wake_lock.is_active()}")
            except Exception as e:
                self.logger.warning(f"Error occurred while releasing wake lock: {e}")
        
        self.logger.info("Local agent application has stopped")
    
    async def restart(self):
        """Restart application"""
        self.logger.info("Restarting application...")
        
        await self.stop()
        
        # Wait [for a period of] time [before] restart
        await asyncio.sleep(2)
        
        self.restart_count += 1
        
        if not await self.start():
            self.logger.error("Application restart failed")
            # After restart failure, try [to] restart [again]
            await self._handle_restart_failure()
    
    async def _handle_restart_failure(self):
        """[Handle] restart failure"""
        max_restart_attempts = self.config.get('max_restart_attempts', 3)
        
        if self.restart_count >= max_restart_attempts:
            self.logger.error(f"Maximum restart attempts reached: {max_restart_attempts}")
            sys.exit(1)
        
        # [Exponential backoff] retry
        delay = min(2 ** self.restart_count, 60)  # Maximum delay 60 seconds
        self.logger.info(f"Attempting restart {self.restart_count + 1} times after {delay} seconds...")
        
        await asyncio.sleep(delay)
        # [Avoid recursive calls], [directly restart] components [instead of calling] restart()
        await self._restart_components()
    
    async def _restart_components(self):
        """Restart [components] ([avoid recursive calls])"""
        self.logger.info("Restarting components...")
        
        # Stop API server
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                self.logger.warning(f"Error occurred while stopping API server: {e}")
        
        # Stop WebSocket service
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.stop():
                self.logger.info("WebSocket service stopped successfully")
            else:
                self.logger.warning("WebSocket service stop failed")
        except Exception as e:
            self.logger.error(f"Error occurred while stopping WebSocket service: {e}")
        
        # Wait [for a period of] time
        await asyncio.sleep(1)
        
        # [Re]start API server
        if self.api_server:
            try:
                await self.api_server.start()
                self.logger.info("API server restarted successfully")
            except Exception as e:
                self.logger.error(f"API server restart failed: {e}")
                return False

        # [Re]start WebSocket service
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.start():
                self.logger.info("WebSocket service restarted successfully")
            else:
                self.logger.warning("WebSocket service restart failed")
        except Exception as e:
            self.logger.error(f"Error occurred while restarting WebSocket service: {e}")

        return True
    
    async def _main_loop(self):
        """[Main loop]"""
        try:
            while self.running:
                # [Main] loop [task]
                await asyncio.sleep(30)
                
                # Check component status
                await self._check_component_health()
                
        except asyncio.CancelledError:
            self.logger.info("Main loop task cancelled")
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
            # [Avoid recursive calls], [record] error [but do not] restart
            self.logger.warning("Main loop error occurred, but avoiding recursion by not restarting application")

    
    async def _keep_alive_loop(self):
        """[Keep-alive loop] - [Use enhanced heartbeat] manager"""
        try:
            # Initialize [heartbeat] manager
            from .heartbeat_manager import create_heartbeat_manager
            self.heartbeat_manager = create_heartbeat_manager()
            
            # Start [heartbeat] manager
            if not await self.heartbeat_manager.start():
                self.logger.error("Heartbeat manager startup failed")
                return
            
            self.logger.info("Enhanced keep-alive mechanism enabled")
            
            # [Main] loop [maintains running] status
            while self.running:
                await asyncio.sleep(60)  # Check running status every minute
                
        except asyncio.CancelledError:
            self.logger.info("Keep-alive task cancelled")
            if hasattr(self, 'heartbeat_manager'):
                await self.heartbeat_manager.stop()
        except Exception as e:
            self.logger.error(f"Keep-alive loop error: {e}")
            if hasattr(self, 'heartbeat_manager'):
                await self.heartbeat_manager.stop()
    
    async def _check_component_health(self):
        """Check [component health status]"""
        # Check API server status
        if self.api_server and not self.api_server.is_running():
            self.logger.warning("API server abnormal, preparing to restart components")
            await self._restart_components()
            return
        
        # Check WebSocket service status
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if (not manager.is_running() or not manager.is_connected()) and manager.is_supposed():
                self.logger.warning("WebSocket service abnormal, preparing to restart")
                await manager.stop()
                await asyncio.sleep(1)
                await manager.start()
            # If service [is running normally], send [heartbeat]
            if manager.is_running() and manager.is_supposed():
                await manager.send_message({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })

        except Exception as e:
            self.logger.error(f"Error occurred while checking WebSocket service status: {e}")
    

    


# Global application instance
_app_instance: Optional[LocalAgentApplication] = None


def get_application(debug=False) -> LocalAgentApplication:
    """Get global application [instance]"""
    global _app_instance
    if _app_instance is None:
        # When creating application instance, [do not immediately] initialize logger, [avoid duplicate] initialization
        _app_instance = LocalAgentApplication()
        # If [in] debug [mode], set up debug [flag]
        _app_instance.debug = debug
    return _app_instance


async def run_application(debug=False):
    """[Run] application"""
    app = get_application(debug=debug)
    
    try:
        if await app.start():
            # Wait [for] application [to run]
            while app.running:
                await asyncio.sleep(1)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        app.logger.info("Received keyboard interrupt signal")
    except Exception as e:
        app.logger.error(f"Application runtime error: {e}")
    finally:
        await app.stop()