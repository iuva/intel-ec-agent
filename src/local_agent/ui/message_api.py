#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息框HTTP API服务
提供消息框功能的HTTP接口，供其他进程调用
使用本地消息窗口替代exe调用
"""

import asyncio
import logging
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from local_agent.core.ek import EK
from typing import Dict, Any

# 导入本地消息窗口组件
from .message_window import create_message_window, MessageResult


class MessageRequest(BaseModel):
    """消息请求模型"""
    message: str
    title: str = "系统提示"
    confirm_show: bool = True
    cancel_show: bool = False
    confirm_text: str = "确定"
    cancel_text: str = "取消"
    timeout: int = 0


class MessageResponse(BaseModel):
    """消息响应模型"""
    success: bool
    user_choice: Optional[str] = None
    error: Optional[str] = None


class MessageAPIService:
    """消息框API服务类"""
    
    def __init__(self, port: int = 8001):
        """初始化API服务"""
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.app = FastAPI(title="消息框API服务", version="1.0.0")
        
        # 创建本地消息窗口实例
        self.message_window = create_message_window()
        
        # 注册路由
        self._setup_routes()
        
        self.logger.info(f"消息框API服务初始化完成，端口: {self.port}, 使用本地消息窗口")
    
    def _setup_routes(self):
        """设置API路由"""
        
        @self.app.get("/")
        async def root():
            """根路径接口"""
            return {
                "service": "消息框API服务",
                "status": "运行中",
                "port": self.port,
                "message_type": "local_window"
            }
        
        @self.app.get("/health")
        async def health_check():
            """健康检查接口"""
            return {
                "status": "healthy",
                "service": "消息框API服务",
                "port": self.port,
                "message_type": "local_window"
            }
        
        
        @self.app.get("/username")
        async def username():
            """根路径接口"""
            import os
            user_name = os.environ.get('USERNAME')
            if not user_name:
                import getpass
                user_name = getpass.getuser()
            
            return user_name

        @self.app.post("/show_message", response_model=MessageResponse)
        async def show_message(request: MessageRequest) -> MessageResponse:
            """显示消息框"""
            try:
                self.logger.debug(f"显示消息框: title={request.title}, message={request.message}")
                
                # 使用本地消息窗口显示消息
                result = self.message_window.show_message(
                    message=request.message,
                    title=request.title,
                    confirm_show=request.confirm_show,
                    cancel_show=request.cancel_show,
                    confirm_text=request.confirm_text,
                    cancel_text=request.cancel_text,
                    timeout=request.timeout
                )
                
                if result.success:
                    return MessageResponse(
                        success=True,
                        user_choice=result.user_choice
                    )
                else:
                    return MessageResponse(
                        success=False,
                        error=result.error
                    )
                    
            except Exception as e:
                self.logger.error(f"消息框调用异常: {e}")
                return MessageResponse(
                    success=False,
                    error=f"消息框调用异常: {str(e)}"
                )
        
        @self.app.post("/show_confirm", response_model=MessageResponse)
        async def show_confirm(message: str, title: str = "确认操作") -> MessageResponse:
            """显示确认对话框"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=True,
                confirm_text="确认",
                cancel_text="取消"
            )
            return await show_message(request)
        
        @self.app.post("/show_info", response_model=MessageResponse)
        async def show_info(message: str, title: str = "信息提示") -> MessageResponse:
            """显示信息对话框"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=False,
                confirm_text="确定"
            )
            return await show_message(request)
        
        @self.app.post("/show_warning", response_model=MessageResponse)
        async def show_warning(message: str, title: str = "警告") -> MessageResponse:
            """显示警告对话框"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=False,
                confirm_text="我知道了"
            )
            return await show_message(request)

        
        
        @self.app.post("/test_start", response_model=MessageResponse)
        async def test_start(body: Dict[str, Any]) -> MessageResponse:
            """
            因为ek 程序有用户界面，所以应该使用服务调用此接口进行启动
            """
            EK.start_test(body['tc_id'], body['cycle_name'], body['user_name'])
            return MessageResponse(
                success=True,
                user_choice="confirm"
            )
    
    async def start_server(self):
        """启动FastAPI服务器"""
        import uvicorn
        
        self.logger.info(f"启动消息框API服务，端口: {self.port}")
        
        config = uvicorn.Config(
            app=self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()


def create_message_api_service(port: int = 8001) -> MessageAPIService:
    """创建消息框API服务实例"""
    return MessageAPIService(port=port)


async def run_message_api_service(port: int = 8001):
    """运行消息框API服务"""
    service = create_message_api_service(port)
    await service.start_server()


if __name__ == "__main__":
    # 测试代码
    import logging
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        service = create_message_api_service()
        await service.start_server()
    
    asyncio.run(test())