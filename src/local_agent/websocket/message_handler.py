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
from ..ui.message_proxy import show_message_box


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
        
        # 注册自更新相关处理器
        self._register_update_handlers()
    
    def _register_ping_handler(self):
        """注册ping消息处理器"""
        @message_manager.register_handler("heartabeat_ack", "处理ping消息")
        async def handle_ping(message: Dict[str, Any]):
            """处理ping消息"""
            self.logger.debug("收到ping消息，发送pong响应")
    

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
                    show_cancel=False,
                    retry_text="确认",
                )
    
    def _register_update_handlers(self):
        """注册自更新相关处理器"""
        
        # 注册自更新指令处理器（兼容旧版本）
        @message_manager.register_handler("update", "处理自更新指令")
        async def handle_update(message: Dict[str, Any]):
            """处理自更新指令"""
            from ..auto_update.auto_updater import AutoUpdater
            updater = AutoUpdater()
            updater.perform_update("5fb21f3eda3dabf1dcbac96a030216f6", "http://localhost/file/local_agent.exe")
        
        # 注册检查更新请求处理器
        @message_manager.register_handler("check_update", "处理检查更新请求")
        async def handle_check_update(message: Dict[str, Any]):
            """处理检查更新请求"""
            exe_url = message.get('exe_url', '')
            if not exe_url:
                await send_message({
                    "type": "update_check_response",
                    "success": False,
                    "message": "缺少exe_url参数"
                })
                return
            
            result = await self.application.auto_updater.check_update(exe_url)
            await send_message({
                "type": "update_check_response",
                "success": True,
                "result": result
            })
        
        # 注册执行更新请求处理器
        @message_manager.register_handler("perform_update", "处理执行更新请求")
        async def handle_perform_update(message: Dict[str, Any]):
            """处理执行更新请求"""
            exe_url = message.get('exe_url', '')
            if not exe_url:
                await send_message({
                    "type": "update_perform_response",
                    "success": False,
                    "message": "缺少exe_url参数"
                })
                return
            
            result = await self.application.auto_updater.perform_update(exe_url)
            await send_message({
                "type": "update_perform_response",
                "success": True,
                "result": result
            })
    
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
