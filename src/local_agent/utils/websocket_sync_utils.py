"""
WebSocket synchronous operation utility class
Provides utility functions for calling asynchronous WebSocket methods in synchronous manner
"""

import asyncio
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class WebSocketSyncUtils:
    """WebSocket synchronous operation utility class"""
    
    @staticmethod
    def stop_websocket() -> bool:
        """
        Synchronously stop WebSocket service
        
        Returns:
            bool: Whether stop was successful
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running event loop, use create_task
                async def _stop():
                    manager = await get_websocket_manager()
                    return await manager.stop()
                
                # Create task in current event loop
                task = asyncio.create_task(_stop())
                # Wait for task completion
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # No running event loop, use asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.stop())
            
            logger.info("WebSocket service stopped")
            return result
        except Exception as e:
            logger.error(f"Error occurred while stopping WebSocket service: {e}")
            return False
    
    @staticmethod
    def start_websocket(application: Optional[Any] = None) -> bool:
        """
        Synchronously start WebSocket service
        
        Args:
            application: Application instance (optional)
            
        Returns:
            bool: Whether start was successful
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running event loop, use create_task
                async def _start():
                    manager = await get_websocket_manager()
                    return await manager.start(application)
                
                # Create task in current event loop
                task = asyncio.create_task(_start())
                # Wait for task completion
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # No running event loop, use asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.start(application))
            
            if result:
                logger.info("WebSocket service started successfully")
            else:
                logger.warning("WebSocket service failed to start")
            return result
        except Exception as e:
            logger.error(f"Error occurred while starting WebSocket service: {e}")
            return False
    
    @staticmethod
    def restart_websocket(application: Optional[Any] = None) -> bool:
        """
        Synchronously restart WebSocket service
        
        Args:
            application: Application instance (optional)
            
        Returns:
            bool: Whether restart was successful
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running event loop, use create_task
                async def _restart():
                    manager = await get_websocket_manager()
                    return await manager.restart(application)
                
                # Create task in current event loop
                task = asyncio.create_task(_restart())
                # Wait for task completion
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # No running event loop, use asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.restart(application))
            
            if result:
                logger.info("WebSocket service restarted successfully")
            else:
                logger.warning("WebSocket service failed to restart")
            return result
        except Exception as e:
            logger.error(f"Error occurred while restarting WebSocket service: {e}")
            return False
    
    @staticmethod
    def get_websocket_status() -> dict:
        """
        Get WebSocket service status
        
        Returns:
            dict: Service status information
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # Check if there's a running event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running event loop, use create_task
                async def _get_status():
                    manager = await get_websocket_manager()
                    return {
                        "running": manager.is_running(),
                        "clients_count": len(manager.get_clients()),
                        "server_info": manager.get_server_info()
                    }
                
                # Create task in current event loop
                task = asyncio.create_task(_get_status())
                # Wait for task completion
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # No running event loop, use asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = {
                    "running": manager.is_running(),
                    "clients_count": len(manager.get_clients()),
                    "server_info": manager.get_server_info()
                }
            
            return result
        except Exception as e:
            logger.error(f"Error occurred while obtaining WebSocket service status: {e}")
            return {"running": False, "clients_count": 0, "server_info": {}}


# Convenience functions
def stop_websocket_sync() -> bool:
    """Convenience function: synchronously stop WebSocket service"""
    return WebSocketSyncUtils.stop_websocket()


def start_websocket_sync(application: Optional[Any] = None) -> bool:
    """Convenience function: synchronously start WebSocket service"""
    return WebSocketSyncUtils.start_websocket(application)


def restart_websocket_sync(application: Optional[Any] = None) -> bool:
    """Convenience function: synchronously restart WebSocket service"""
    return WebSocketSyncUtils.restart_websocket(application)


def get_websocket_status_sync() -> dict:
    """Convenience function: get WebSocket service status"""
    return WebSocketSyncUtils.get_websocket_status()


if __name__ == "__main__":
    # Test code
    print("=== WebSocket Synchronous Operation Utility Test ===")
    
    # Get status
    status = get_websocket_status_sync()
    print(f"WebSocket service status: {status}")
    
    # Restart service
    result = restart_websocket_sync()
    print(f"WebSocket service restart result: {result}")