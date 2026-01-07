#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket消息处理器
封装所有WebSocket消息处理逻辑，实现消息处理器的统一管理
"""

import asyncio
from datetime import datetime
from typing import Dict, Any

from ..logger import get_logger
from .message_manager import message_manager
from .message_sender import send_message
from ..utils.subprocess_utils import run_with_logging_safe
from ..utils.message_tool import show_message_box
from ..core.global_cache import cache, get_agent_status, set_agent_status, set_ek_test_info, get_agent_status_by_key
from ..core.constants import APP_UPDATE_CACHE_KEY
from ..core.app_update import update_app
from ..core.ek import EK
from ..core.vnc import VNC


class WebSocketMessageHandler:
    """WebSocket消息处理器类"""
    
    def __init__(self, application):
        """
        初始化消息处理器
        
        Args:
            application: 应用实例，用于访问应用状态和方法
        """
        self.application = application
        self.logger = get_logger(__name__)
        
    def register_all_handlers(self):
        """注册所有消息处理器"""
        self.logger.info("正在注册WebSocket消息处理器...")
        
        # 注册ping消息处理器
        self._register_ping_handler()

        # 服务端超时未得到心跳的处理
        self._register_timeout_handler()

        # 状态更新确认
        self._register_status_update_handler()

        # command 命令
        self._register_command_handler()

        # notification 通知
        self._register_notification_handler()
        
        # 注册更新相关处理器
        self._register_update_handlers()

        # ek 测试相关处理器
        self._register_ek_test_handlers()
    
    def _register_ping_handler(self):
        """注册ping消息处理器"""
        @message_manager.register_handler("heartbeat_ack", "处理ping消息")
        async def handle_ping(message: Dict[str, Any]):
            """处理ping消息"""
            self.logger.debug("收到心跳响应")
    

    def _register_timeout_handler(self):
        """服务器告知心跳超时"""
        @message_manager.register_handler("heartbeat_timeout_warning", "心跳超时")
        async def handle_timeout(message: Dict[str, Any]):
            self.logger.debug("服务器未接收到心跳信息，立即发送一条")
            await send_message({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            })
    
    def _register_status_update_handler(self):
        """状态更新回调"""
        @message_manager.register_handler("status_update_ack", "状态更新")
        async def status_update(message: Dict[str, Any]):
            self.logger.info("收到状态更新回复")

    
    def _register_command_handler(self):
        """命令指示"""
        @message_manager.register_handler("command", "处理重启指令")
        async def handle_command(message: Dict[str, Any]):
            """处理命令"""
            command = message.get('command', '')
            command_id = message.get('command_id', '')
            result = run_with_logging_safe(
                [command],
                command_name='service',
                capture_output=True,
                text=True,
                timeout=10  # 10秒超时
            )
            isOk = result and result.returncode == 0
            
            await send_message({
                "type": "command_response",
                "command_id": command_id,
                "success": isOk,
                "error": result.stderr.strip() if not isOk else None,
                "result": result.stdout.strip() if isOk else None,
                "timestamp": datetime.now().isoformat()
            })
    
    def _register_notification_handler(self):
        """注册状态查询处理器"""
        @message_manager.register_handler("status", "处理状态查询")
        async def handle_notification(message: Dict[str, Any]):
                show_message_box(
                    msg=message.get('content', ''),
                    title=message.get('title', ''),
                )




    def _register_ek_test_handlers(self):
        """注册 ek 测试相关处理器"""
        
        # vnc 连接通知
        @message_manager.register_handler("connection_notification", "vnc 连接通知")
        async def handle_connection_notification(message: Dict[str, Any]):
            """处理 vnc 连接通知"""
            # 检查是否已处于测试状态
            if get_agent_status_by_key('use'):
                self.logger.warning("已处于测试状态，将忽略此消息")
                return

            set_agent_status(use=True)
            set_agent_status(pre=True)
            details = message['details']
            details['host_id'] = message['host_id']
            set_ek_test_info(details)
        
        
        # 释放 host 通知 host_offline_notification
        @message_manager.register_handler("host_offline_notification", "host 离线通知")
        async def handle_host_offline_notification(message: Dict[str, Any]):
            """处理 host 离线通知"""
            EK.test_kill()
            VNC.disconnect()




    def _register_update_handlers(self):
        """注册自更新相关处理器"""
        
        # 注册自更新指令处理器（兼容旧版本）
        @message_manager.register_handler("ota_deploy", "软件更新")
        async def handle_update(message: Dict[str, Any]):
            """处理软件更新指令"""


            name = message.get('conf_name', '')

            # 优先进行反馈，表示接收到了更新通知
            await send_message({
                "type": "ota_deploy_response",
                "conf_name": name,
                "conf_ver": message['conf_ver']
            })

            if not name:
                self.logger.error("更新指令缺少软件名称")
                return
            
            # 新版本信息放入缓存
            update_info = cache.get(APP_UPDATE_CACHE_KEY, {})
            update_info.update({name: message})
            cache.set(APP_UPDATE_CACHE_KEY, update_info)

            # 是否符合更新条件
            agent_state = get_agent_status()
            
            is_test = agent_state.get('test', False)
            is_sut = agent_state.get('sut', False)
            is_vnc = agent_state.get('vnc', False)

            if not is_test and not is_sut and not is_vnc:
                update_app()
            # 不符合更新条件不进行处理，会在测试结束、硬件信息获取结束时触发更新
            # 测试结束是指：测试用例执行并提交完毕，且vnc 断开连接


    
    def get_handler_count(self) -> int:
        """获取已注册的处理器数量"""
        return message_manager.get_handler_count()


# 创建全局消息处理器实例
_message_handler = None


def get_message_handler(application=None) -> WebSocketMessageHandler:
    """
    获取消息处理器实例
    
    Args:
        application: 应用实例，首次调用时需要传入
        
    Returns:
        WebSocketMessageHandler: 消息处理器实例
    """
    global _message_handler
    
    if _message_handler is None and application is not None:
        _message_handler = WebSocketMessageHandler(application)
    
    return _message_handler


def register_websocket_handlers(application):
    """
    注册WebSocket消息处理器（便捷函数）
    
    Args:
        application: 应用实例
    """
    handler = get_message_handler(application)
    if handler:
        # 检查是否已经注册过处理器，避免重复注册
        current_count = message_manager.get_handler_count()
        if current_count > 0:
            handler.logger.info(f"检测到已有 {current_count} 个消息处理器，跳过重复注册")
            return
        handler.register_all_handlers()
