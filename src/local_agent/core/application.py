#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地代理应用
实现应用生命周期管理和多层级保活机制
"""

import asyncio
import json
import signal
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

from ..config import get_config
from ..logger import get_logger
from ..api.server import APIServer
from .host_init import HostInit
from ..websocket.message_manager import message_manager
from ..websocket.message_sender import send_message

# WebSocketClient将在需要时延迟导入以避免循环依赖


class LocalAgentApplication:
    """本地代理应用主类"""
    
    def __init__(self):
        self.config = get_config()
        # 延迟初始化日志器，避免在构造函数中触发日志系统初始化
        self._logger = None
        
        # 应用状态
        self.running = False
        self.start_time = None
        self.restart_count = 0
        self.debug = False  # 默认非debug模式
        
        # 组件实例
        self.api_server: Optional[APIServer] = None
        self.websocket_client: Optional[WebSocketClient] = None
        
        # 自更新管理器
        self.auto_updater: Optional[AutoUpdater] = None
        
        # 唤醒锁实例 - 在应用初始化时设置
        self.wake_lock = None
        
        # 任务管理
        self.main_task: Optional[asyncio.Task] = None
        self.health_check_task: Optional[asyncio.Task] = None
        self.keep_alive_task: Optional[asyncio.Task] = None
        
        # 信号处理
        self._setup_signal_handlers()
    
    @property
    def logger(self):
        """延迟获取日志器"""
        if self._logger is None:
            self._logger = get_logger(__name__)
        return self._logger
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        try:
            # Windows下设置Ctrl+C处理器
            if sys.platform == "win32":
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            else:
                # Unix系统信号处理
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                signal.signal(signal.SIGHUP, self._signal_handler)
        except Exception as e:
            self.logger.warning(f"设置信号处理器失败: {e}")
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        self.logger.info(f"收到信号 {signum}，正在优雅关闭...")
        self.stop()
    
    async def initialize(self) -> bool:
        """初始化应用"""
        try:
            self.logger.info("正在初始化本地代理应用...")
            
            # 记录启动时间
            self.start_time = datetime.now()
            
            # 初始化唤醒模块 - 在应用启动早期调用，确保系统保持唤醒状态
            try:
                from .wake_lock import get_wake_lock
                self.wake_lock = get_wake_lock()
                
                # 获取唤醒锁，保持系统唤醒状态
                if self.wake_lock.keep_awake():
                    self.logger.info("系统唤醒锁已启用，将保持电脑唤醒状态")
                else:
                    self.logger.warning("系统唤醒锁启用失败，电脑可能进入睡眠模式")
            except Exception as e:
                self.logger.warning(f"唤醒模块初始化失败: {e}，应用将继续运行但可能无法保持唤醒状态")
            
            # 初始化API服务器
            self.api_server = APIServer()
            
            # 延迟导入WebSocket客户端以避免循环导入
            from ..websocket.client import WebSocketClient
            
            # 初始化WebSocket客户端
            self.websocket_client = WebSocketClient()
            
            # 初始化自更新管理器
            from local_agent.auto_update.auto_updater import AutoUpdater
            self.auto_updater = AutoUpdater()
            
            # 设置WebSocket回调
            await self._setup_websocket_callbacks()
            
            # 注册WebSocket消息处理器
            await self._register_websocket_handlers()

            # 业务流程初始化
            HostInit()

            self.logger.info("应用初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"应用初始化失败: {e}")
            return False
    
    async def _setup_websocket_callbacks(self):
        """设置WebSocket回调函数"""
        if not self.websocket_client:
            return
        
        async def on_connect():
            self.logger.info("WebSocket连接成功")
        
        async def on_disconnect():
            self.logger.warning("WebSocket连接断开")
        
        async def on_message(message):
            self.logger.debug(f"收到WebSocket消息: {message}")
            # 处理不同类型的消息
            await self._handle_websocket_message(message)
        
        async def on_error(error):
            self.logger.error(f"WebSocket错误: {error}")
        
        self.websocket_client.set_on_connect(on_connect)
        self.websocket_client.set_on_disconnect(on_disconnect)
        self.websocket_client.set_on_message(on_message)
        self.websocket_client.set_on_error(on_error)
    
    async def _register_websocket_handlers(self):
        """注册WebSocket消息处理器"""
        from ..websocket.message_handler import register_websocket_handlers
        
        # 使用新的消息处理器封装
        register_websocket_handlers(self)
    
    async def _handle_websocket_message(self, message: str):
        """处理WebSocket消息（兼容旧逻辑，新消息由消息管理器处理）"""
        try:
            # 解析JSON消息
            data = message
            if isinstance(message, str):
                data = json.loads(message)
            
            message_type = data.get('type', '')
            
            # 记录消息接收，但实际处理由消息管理器完成
            self.logger.debug(f"收到WebSocket消息，类型: {message_type}")
            
            # 这里不再需要具体的消息处理逻辑，因为已经通过消息管理器注册了处理器
            # 消息管理器会自动调用相应的处理器
            
        except Exception as e:
            self.logger.error(f"处理WebSocket消息失败: {e}")
    
    async def start(self) -> bool:
        """启动应用"""
        try:
            if self.running:
                self.logger.warning("应用已在运行中")
                return True
            
            # 记录启动模式
            mode_str = "debug模式" if self.debug else "正常模式"
            self.logger.info(f"正在启动本地代理应用... ({mode_str})")
            
            # 在debug模式下，临时修改配置
            if self.debug:
                self.logger.info("启用debug模式配置...")
            
            # 初始化应用
            if not await self.initialize():
                return False
            
            # 启动API服务器（非阻塞方式）
            if self.api_server:
                # 传入debug参数
                self.api_server_task = asyncio.create_task(self.api_server.start(debug=self.debug))
                # 在debug模式下，等待时间可以短一些
                wait_time = 1 if self.debug else 2
                self.logger.debug(f"等待API服务器启动，等待时间: {wait_time}秒")
                await asyncio.sleep(wait_time)
            
            # 连接WebSocket服务器（非阻塞方式）
            if self.websocket_client:
                self.websocket_task = asyncio.create_task(self.websocket_client.connect())
                # 等待WebSocket连接完成
                await asyncio.sleep(1)
            
            # 启动保活任务
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            
            # 启动健康检查任务
            self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.running = True
            self.logger.info("本地代理应用启动成功")
            
            # 启动主循环
            self.main_task = asyncio.create_task(self._main_loop())
            
            return True
            
        except Exception as e:
            self.logger.error(f"应用启动失败: {e}")
            await self.stop()
            return False
    
    async def stop(self):
        """停止应用"""
        if not self.running:
            return
        
        self.logger.info("正在停止本地代理应用...")
        self.running = False
        
        # 取消所有任务
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
        if hasattr(self, 'websocket_task') and self.websocket_task:
            self.websocket_task.cancel()
            tasks_to_cancel.append(self.websocket_task)
        
        # 等待所有任务取消完成
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        # 停止WebSocket客户端
        if self.websocket_client:
            try:
                await self.websocket_client.disconnect()
            except Exception as e:
                self.logger.warning(f"停止WebSocket客户端时出错: {e}")
        
        # 停止API服务器
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                self.logger.warning(f"停止API服务器时出错: {e}")
        
        # 释放唤醒锁 - 在应用停止时恢复系统正常睡眠行为
        if hasattr(self, 'wake_lock') and self.wake_lock:
            try:
                self.logger.info(f"开始释放唤醒锁，当前状态: {self.wake_lock.is_active()}")
                if self.wake_lock.release():
                    self.logger.info("系统唤醒锁已释放，电脑可正常进入睡眠模式")
                else:
                    self.logger.warning("系统唤醒锁释放失败")
                self.logger.info(f"释放后唤醒锁状态: {self.wake_lock.is_active()}")
            except Exception as e:
                self.logger.warning(f"释放唤醒锁时出错: {e}")
        
        self.logger.info("本地代理应用已停止")
    
    async def restart(self):
        """重启应用"""
        self.logger.info("正在重启应用...")
        
        await self.stop()
        
        # 等待一段时间再重启
        await asyncio.sleep(2)
        
        self.restart_count += 1
        
        if not await self.start():
            self.logger.error("应用重启失败")
            # 重启失败后尝试再次重启
            await self._handle_restart_failure()
    
    async def _handle_restart_failure(self):
        """处理重启失败"""
        max_restart_attempts = self.config.get('max_restart_attempts', 3)
        
        if self.restart_count >= max_restart_attempts:
            self.logger.error(f"已达到最大重启次数: {max_restart_attempts}")
            sys.exit(1)
        
        # 指数退避重试
        delay = min(2 ** self.restart_count, 60)  # 最大延迟60秒
        self.logger.info(f"{delay}秒后尝试第{self.restart_count + 1}次重启...")
        
        await asyncio.sleep(delay)
        # 避免递归调用，直接重新启动组件而不是调用restart()
        await self._restart_components()
    
    async def _restart_components(self):
        """重启组件（避免递归调用）"""
        self.logger.info("正在重启组件...")
        
        # 停止API服务器
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                self.logger.warning(f"停止API服务器时出错: {e}")
        
        # 停止WebSocket客户端
        if self.websocket_client:
            try:
                await self.websocket_client.disconnect()
            except Exception as e:
                self.logger.warning(f"停止WebSocket客户端时出错: {e}")
        
        # 等待一段时间
        await asyncio.sleep(1)
        
        # 重新启动API服务器
        if self.api_server:
            try:
                await self.api_server.start()
                self.logger.info("API服务器重启成功")
            except Exception as e:
                self.logger.error(f"API服务器重启失败: {e}")
                return False
        
        # 重新连接WebSocket
        if self.websocket_client:
            try:
                await self.websocket_client.connect()
                self.logger.info("WebSocket客户端重连成功")
            except Exception as e:
                self.logger.warning(f"WebSocket客户端重连失败: {e}")
        
        return True
    
    async def _main_loop(self):
        """主循环"""
        try:
            while self.running:
                # 主循环任务
                await asyncio.sleep(30)
                
                # 检查组件状态
                await self._check_component_health()
                
        except asyncio.CancelledError:
            self.logger.info("主循环任务被取消")
        except Exception as e:
            self.logger.error(f"主循环错误: {e}")
            # 避免递归调用，记录错误但不重启
            self.logger.warning("主循环发生错误，但为避免递归不重启应用")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        try:
            while self.running:
                # 执行健康检查
                health_status = await self._perform_health_check()
                
                if not health_status['healthy']:
                    self.logger.warning("健康检查失败，准备重启组件")
                    await self._restart_components()
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            self.logger.info("健康检查任务被取消")
        except Exception as e:
            self.logger.error(f"健康检查循环错误: {e}")
    
    async def _keep_alive_loop(self):
        """保活循环 - 使用增强的心跳管理器"""
        try:
            # 初始化心跳管理器
            from .heartbeat_manager import create_heartbeat_manager
            self.heartbeat_manager = create_heartbeat_manager()
            
            # 启动心跳管理器
            if not await self.heartbeat_manager.start():
                self.logger.error("心跳管理器启动失败")
                return
            
            self.logger.info("增强保活机制已启用")
            
            # 主循环保持运行状态
            while self.running:
                await asyncio.sleep(60)  # 每分钟检查一次运行状态
                
        except asyncio.CancelledError:
            self.logger.info("保活任务被取消")
            if hasattr(self, 'heartbeat_manager'):
                await self.heartbeat_manager.stop()
        except Exception as e:
            self.logger.error(f"保活循环错误: {e}")
            if hasattr(self, 'heartbeat_manager'):
                await self.heartbeat_manager.stop()
    
    async def _check_component_health(self):
        """检查组件健康状态"""
        # 检查API服务器状态
        if self.api_server and not self.api_server.is_running():
            self.logger.warning("API服务器异常，准备重启组件")
            await self._restart_components()
            return
        
        # 检查WebSocket连接状态
        if (self.websocket_client and 
            self.websocket_client.connected and 
            not await self._check_websocket_alive()):
            self.logger.warning("WebSocket连接异常，准备重连")
            await self.websocket_client.disconnect()
            await self.websocket_client.connect()
    
    async def _check_websocket_alive(self) -> bool:
        """检查WebSocket连接是否存活"""
        if not self.websocket_client or not self.websocket_client.connected:
            return False
        
        try:
            # 发送ping消息测试连接
            await self.websocket_client.send_message({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            })
            return True
        except Exception:
            return False
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """执行健康检查"""
        health_status = {
            "healthy": True,
            "components": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # 检查API服务器
        if self.api_server:
            api_healthy = self.api_server.is_running()
            health_status["components"]["api_server"] = api_healthy
            if not api_healthy:
                health_status["healthy"] = False
        
        # 检查WebSocket客户端
        if self.websocket_client:
            ws_healthy = self.websocket_client.connected
            health_status["components"]["websocket_client"] = ws_healthy
            # WebSocket连接失败不影响整体健康状态
        
        # 检查内存使用
        import psutil
        memory_percent = psutil.virtual_memory().percent
        health_status["memory_usage"] = memory_percent
        
        if memory_percent > 90:  # 内存使用超过90%
            health_status["healthy"] = False
            self.logger.warning(f"内存使用过高: {memory_percent}%")
        
        return health_status
    
    async def _send_keep_alive_heartbeat(self):
        """发送保活心跳"""
        if self.websocket_client and self.websocket_client.connected:
            try:
                await self.websocket_client.send_message({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                self.logger.warning(f"发送心跳失败: {e}")
    


# 全局应用实例
_app_instance: Optional[LocalAgentApplication] = None


def get_application(debug=False) -> LocalAgentApplication:
    """获取全局应用实例"""
    global _app_instance
    if _app_instance is None:
        # 创建应用实例时不立即初始化日志器，避免重复初始化
        _app_instance = LocalAgentApplication()
        # 如果是debug模式，设置debug标志
        _app_instance.debug = debug
    return _app_instance


async def run_application(debug=False):
    """运行应用"""
    app = get_application(debug=debug)
    
    try:
        if await app.start():
            # 等待应用运行
            while app.running:
                await asyncio.sleep(1)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        app.logger.info("收到键盘中断信号")
    except Exception as e:
        app.logger.error(f"应用运行错误: {e}")
    finally:
        await app.stop()