#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI服务器
启动和管理FastAPI服务
"""

import asyncio
import uvicorn
import logging
from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

from .routes import router
from ..config import get_config
from ..logger import get_logger


class APIServer:
    """API服务器管理类"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.app = None
        self.server = None
    
    def create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        app = FastAPI(
            title=self.config.get('app_name', 'Local Agent Service'),
            description="本地代理服务API接口",
            version=self.config.get('version', '1.0.0'),
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # 添加CORS中间件
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 添加API访问日志中间件
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            # 记录请求信息
            client_host = request.client.host if request.client else "unknown"
            logger = get_logger("local_agent.api.access")
            
            logger.info(f"API请求: {request.method} {request.url.path} 来自 {client_host}")
            
            # 处理请求
            response = await call_next(request)
            
            # 记录响应信息
            logger.info(f"API响应: {request.method} {request.url.path} 状态码 {response.status_code}")
            
            return response
        
        # 创建根路由（仅用于健康检查）
        root_router = APIRouter()
        
        # 定义健康检查响应模型
        class HealthResponse(BaseModel):
            """健康检查响应模型"""
            status: str
            timestamp: Any
            version: str
            system_info: Dict[str, Any]
            
        # 从原路由中获取健康检查端点并添加到根路由
        # 注意：这种方式可以避免修改routes.py文件的结构
        @root_router.get("/health", response_model=HealthResponse)
        async def health_check():
            """健康检查接口"""
            logger = get_logger(__name__)
            logger.info("健康检查请求")
            
            # 获取系统信息
            import psutil
            import platform
            from datetime import datetime
            
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage('/')
            
            system_info = {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "memory_usage": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent
                },
                "v": '更新前',
                "cpu_usage": cpu_percent,
                "disk_usage": {
                    "total": disk.total,
                    "free": disk.free,
                    "percent": disk.percent
                }
            }
            
            return {
                "status": "healthy",
                "timestamp": datetime.now(),
                "version": self.config.get('version', '1.0.0'),
                "system_info": system_info
            }
        
        # 注册根路由
        app.include_router(root_router)
        
        # 注册其他API路由
        app.include_router(router, prefix="/api/v1")
        
        # 添加启动和关闭事件
        @app.on_event("startup")
        async def startup_event():
            self.logger.info("FastAPI服务器启动中...")
        
        @app.on_event("shutdown")
        async def shutdown_event():
            self.logger.info("FastAPI服务器关闭中...")
        
        self.app = app
        return app
    
    async def start(self, debug=False):
        """启动API服务器"""
        if self.app is None:
            self.create_app()
        
        # 关键优化：检查端口是否已被占用
        # 避免与双进程保活机制中的其他进程冲突
        import socket
        
        host = self.config.get('api_host', '0.0.0.0')
        port = self.config.get('api_port', 8000)
        
        # 检查端口是否可用
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                self.logger.warning(f"端口 {port} 已被占用，FastAPI服务器将不会启动")
                self.logger.info("这是双进程保活机制的正常行为，确保只有一个进程运行服务")
                return  # 端口被占用，不启动服务器
                
        except Exception as e:
            self.logger.warning(f"端口检查失败: {e}")
        
        # 在debug模式下的特殊配置
        if debug:
            self.logger.info("启用API服务器debug模式: 启用热重载，设置日志级别为debug")
            # 临时修改配置以支持debug模式
            reload = True
            log_level = 'debug'
            workers = 1  # 调试模式下只能有一个worker
        else:
            reload = self.config.get('api_reload', False)
            log_level = self.config.get('log_level', 'info').lower()
            workers = self.config.get('api_workers', 1)
        
        # 优化uvicorn配置，提高与双进程保活机制的兼容性
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            reload=reload,
            workers=workers,
            log_level=log_level,
            access_log=True,
            # 关键优化：添加优雅关闭和超时配置
            timeout_keep_alive=5,
            timeout_notify=30,
            timeout_graceful_shutdown=10,
            # 使用asyncio事件循环，提高稳定性
            loop="asyncio",
        )
        
        self.server = uvicorn.Server(config)
        
        self.logger.info(f"启动FastAPI服务器: {host}:{port}")
        self.logger.info(f"API文档地址: http://{host}:{port}/docs")
        
        try:
            await self.server.serve()
        except Exception as e:
            self.logger.error(f"FastAPI服务器启动失败: {e}")
            # 服务器启动失败时，记录错误但不抛出异常
            # 让双进程保活机制决定是否重启进程
            self.logger.info("FastAPI服务器启动失败，但进程将继续运行以支持其他功能")
    
    async def stop(self):
        """停止API服务器"""
        if self.server:
            self.logger.info("正在停止FastAPI服务器...")
            self.server.should_exit = True
            await self.server.shutdown()
            self.logger.info("FastAPI服务器已停止")
    
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self.server is not None and self.server.started
    
    def get_server_info(self) -> dict:
        """获取服务器信息"""
        return {
            "host": self.config.get('api_host', '0.0.0.0'),
            "port": self.config.get('api_port', 8000),
            "status": "running" if self.is_running() else "stopped",
            "docs_url": f"http://{self.config.get('api_host', '0.0.0.0')}:{self.config.get('api_port', 8000)}/docs"
        }


async def start_api_server():
    """启动API服务器的便捷函数"""
    server = APIServer()
    await server.start()