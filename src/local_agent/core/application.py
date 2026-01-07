#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地代理应用
实现应用生命周期管理和多层级保活机制
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, Any

from local_agent.utils.http_client import http_post

from ..config import get_config
from ..logger import get_logger
from ..api.server import APIServer
from .host_init import HostInit
from .vnc import VNC
from .ek import EK
from .global_cache import set_agent_status, get_agent_status_by_key, get_ek_test_info
from ..core.app_update import update_app


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
            
            # 业务流程初始化
            HostInit()

            self.logger.info("应用初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"应用初始化失败: {e}")
            return False
    

    
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
            await self.initialize()
            
            # 启动API服务器（非阻塞方式）
            if self.api_server:
                # 传入debug参数
                self.api_server_task = asyncio.create_task(self.api_server.start(debug=self.debug))
                # 在debug模式下，等待时间可以短一些
                wait_time = 1 if self.debug else 2
                self.logger.debug(f"等待API服务器启动，等待时间: {wait_time}秒")
                await asyncio.sleep(wait_time)
            
            # 启动保活任务
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            
            self.running = True
            self.logger.info("本地代理应用启动成功")
            
            # 启动主循环
            self.main_task = asyncio.create_task(self._main_loop())
            
            return True
            
        except Exception as e:
            self.logger.error(f"应用启动失败: {e}")
            await self.stop()
            return False
    
    def _handle_queue_response(self, response: Dict[str, Any]):
        """处理队列消息的响应"""
        self.logger.info(f"队列消息响应: {response}")
        # 这里可以添加具体的响应处理逻辑


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
        
        # 等待所有任务取消完成
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        # 停止WebSocket服务（使用全局单例管理器）
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.stop():
                self.logger.info("WebSocket服务停止成功")
            else:
                self.logger.warning("WebSocket服务停止失败")
        except Exception as e:
            self.logger.error(f"停止WebSocket服务时出错: {e}")
        
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
        
        # 停止WebSocket服务
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.stop():
                self.logger.info("WebSocket服务停止成功")
            else:
                self.logger.warning("WebSocket服务停止失败")
        except Exception as e:
            self.logger.error(f"停止WebSocket服务时出错: {e}")
        
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

        # 重新启动WebSocket服务
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if await manager.start():
                self.logger.info("WebSocket服务重启成功")
            else:
                self.logger.warning("WebSocket服务重启失败")
        except Exception as e:
            self.logger.error(f"重启WebSocket服务时出错: {e}")

        return True
    
    async def _main_loop(self):
        """主循环"""
        try:
            flag = False
            while self.running:
                # 主循环任务
                await asyncio.sleep(30)
                
                # 检查组件状态
                await self._check_component_health()

                flag = not flag
                if flag:
                    # 每分钟检查一次vnc连接状态
                    self._check_vnc_connection()
                
        except asyncio.CancelledError:
            self.logger.info("主循环任务被取消")
        except Exception as e:
            self.logger.error(f"主循环错误: {e}")
            # 避免递归调用，记录错误但不重启
            self.logger.warning("主循环发生错误，但为避免递归不重启应用")
    
    def _check_vnc_connection(self):
        """检查vnc连接状态"""
        if not get_agent_status_by_key("use"):
            return

        is_con = VNC.is_connecting()

        status = get_agent_status_by_key("vnc")
        if status != is_con:
            res = http_post(url='/host/agent/vnc/report', data={'vnc_state': 1 if is_con else 2})
            
            res_data = res.get('data', {})
            code = res_data.get('code', 0)

            if code == 200:
                set_agent_status(vnc = is_con)
                if is_con and get_agent_status_by_key("pre"):
                    # 启动 ek 测试
                    test_info = get_ek_test_info()
                    response = http_post(
                        url=f"http://127.0.0.1:8001/test_start",
                        data=test_info
                    )
                    # EK.start_test(test_info['tc_id'], test_info['cycle_name'], test_info['user_name'])
                    set_agent_status(pre = False)

                if not is_con and not get_agent_status_by_key("test"):
                    # 是否完全结束了操作
                    set_agent_status(use = False)
                    # 执行更新补偿
                    update_app()
            
            # 如果code 是 53016 则断开所有 vnc 连接
            elif code == 53016:
                VNC.disconnect()
                set_agent_status(vnc = False)


    
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
        
        # 检查WebSocket服务状态
        try:
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            if (not manager.is_running() or not manager.is_connected()) and manager.is_supposed():
                self.logger.warning("WebSocket服务异常，准备重启")
                await manager.stop()
                await asyncio.sleep(1)
                await manager.start()
            # 如果服务运行正常，发送心跳
            if manager.is_running() and manager.is_supposed():
                await manager.send_message({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })

        except Exception as e:
            self.logger.error(f"检查WebSocket服务状态时出错: {e}")
    

    


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