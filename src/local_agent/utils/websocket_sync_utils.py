"""
WebSocket 同步操作工具类
提供同步方式调用异步 WebSocket 方法的工具函数
"""

import asyncio
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class WebSocketSyncUtils:
    """WebSocket 同步操作工具类"""
    
    @staticmethod
    def stop_websocket() -> bool:
        """
        同步停止 WebSocket 服务
        
        Returns:
            bool: 停止是否成功
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # 检查当前是否有运行的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行的事件循环，使用 create_task
                async def _stop():
                    manager = await get_websocket_manager()
                    return await manager.stop()
                
                # 在当前事件循环中创建任务
                task = asyncio.create_task(_stop())
                # 等待任务完成
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # 没有运行的事件循环，使用 asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.stop())
            
            logger.info("WebSocket服务已停止")
            return result
        except Exception as e:
            logger.error(f"停止WebSocket服务时出错: {e}")
            return False
    
    @staticmethod
    def start_websocket(application: Optional[Any] = None) -> bool:
        """
        同步启动 WebSocket 服务
        
        Args:
            application: 应用实例（可选）
            
        Returns:
            bool: 启动是否成功
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # 检查当前是否有运行的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行的事件循环，使用 create_task
                async def _start():
                    manager = await get_websocket_manager()
                    return await manager.start(application)
                
                # 在当前事件循环中创建任务
                task = asyncio.create_task(_start())
                # 等待任务完成
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # 没有运行的事件循环，使用 asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.start(application))
            
            if result:
                logger.info("WebSocket服务启动成功")
            else:
                logger.warning("WebSocket服务启动失败")
            return result
        except Exception as e:
            logger.error(f"启动WebSocket服务时出错: {e}")
            return False
    
    @staticmethod
    def restart_websocket(application: Optional[Any] = None) -> bool:
        """
        同步重启 WebSocket 服务
        
        Args:
            application: 应用实例（可选）
            
        Returns:
            bool: 重启是否成功
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # 检查当前是否有运行的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行的事件循环，使用 create_task
                async def _restart():
                    manager = await get_websocket_manager()
                    return await manager.restart(application)
                
                # 在当前事件循环中创建任务
                task = asyncio.create_task(_restart())
                # 等待任务完成
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # 没有运行的事件循环，使用 asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = asyncio.run(manager.restart(application))
            
            if result:
                logger.info("WebSocket服务重启成功")
            else:
                logger.warning("WebSocket服务重启失败")
            return result
        except Exception as e:
            logger.error(f"重启WebSocket服务时出错: {e}")
            return False
    
    @staticmethod
    def get_websocket_status() -> dict:
        """
        获取 WebSocket 服务状态
        
        Returns:
            dict: 服务状态信息
        """
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            
            # 检查当前是否有运行的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果有运行的事件循环，使用 create_task
                async def _get_status():
                    manager = await get_websocket_manager()
                    return {
                        "running": manager.is_running(),
                        "clients_count": len(manager.get_clients()),
                        "server_info": manager.get_server_info()
                    }
                
                # 在当前事件循环中创建任务
                task = asyncio.create_task(_get_status())
                # 等待任务完成
                result = asyncio.run_coroutine_threadsafe(task, loop).result()
            except RuntimeError:
                # 没有运行的事件循环，使用 asyncio.run
                manager = asyncio.run(get_websocket_manager())
                result = {
                    "running": manager.is_running(),
                    "clients_count": len(manager.get_clients()),
                    "server_info": manager.get_server_info()
                }
            
            return result
        except Exception as e:
            logger.error(f"获取WebSocket服务状态时出错: {e}")
            return {"running": False, "clients_count": 0, "server_info": {}}


# 便捷函数
def stop_websocket_sync() -> bool:
    """便捷函数：同步停止 WebSocket 服务"""
    return WebSocketSyncUtils.stop_websocket()


def start_websocket_sync(application: Optional[Any] = None) -> bool:
    """便捷函数：同步启动 WebSocket 服务"""
    return WebSocketSyncUtils.start_websocket(application)


def restart_websocket_sync(application: Optional[Any] = None) -> bool:
    """便捷函数：同步重启 WebSocket 服务"""
    return WebSocketSyncUtils.restart_websocket(application)


def get_websocket_status_sync() -> dict:
    """便捷函数：获取 WebSocket 服务状态"""
    return WebSocketSyncUtils.get_websocket_status()


if __name__ == "__main__":
    # 测试代码
    print("=== WebSocket 同步操作工具类测试 ===")
    
    # 获取状态
    status = get_websocket_status_sync()
    print(f"WebSocket 服务状态: {status}")
    
    # 重启服务
    result = restart_websocket_sync()
    print(f"WebSocket 服务重启结果: {result}")