#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI server
Start and manage FastAPI services
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
    """API service [server] management class"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.app = None
        self.server = None
    
    def create_app(self) -> FastAPI:
        """Create FastAPI application"""
        app = FastAPI(
            title=self.config.get('app_name', 'Local Agent Service'),
            description="Local Agent Service API Interface",
            version=self.config.get('version', '1.0.0'),
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # [Add] CORS [middleware]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # [Add] API [access] log [middleware]
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            # [Record] request info
            client_host = request.client.host if request.client else "unknown"
            logger = get_logger("local_agent.api.access")
            
            logger.info(f"API request: {request.method} {request.url.path} from {client_host}")
            
            # [Process] request
            response = await call_next(request)
            
            # [Record] response info
            logger.info(f"API response: {request.method} {request.url.path} status code {response.status_code}")
            
            return response
        
        # Create [root router] ([only for health] check)
        root_router = APIRouter()
        
        # [Define health] check response [model]
        class HealthResponse(BaseModel):
            """[Health] check [response model]"""
            status: str
            timestamp: Any
            version: str
            system_info: Dict[str, Any]
            
        # [Get health] check [endpoint from original router and add to root router]
        # [Note]: [This method avoids modifying] routes.py file [structure]
        @root_router.get("/health", response_model=HealthResponse)
        async def health_check():
            """[Health] check [interface]"""
            logger = get_logger(__name__)
            logger.info("Health check request")
            
            # Get system info
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
                "v": 'Before update',
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
        
        # [Register root router]
        app.include_router(root_router)
        
        # [Register other] API [routes]
        app.include_router(router, prefix="/api/v1")
        
        # [Add] startup [and shutdown events]
        @app.on_event("startup")
        async def startup_event():
            self.logger.info("FastAPI service starting...")
        
        @app.on_event("shutdown")
        async def shutdown_event():
            self.logger.info("FastAPI service shutting down...")
        
        self.app = app
        return app
    
    async def start(self, debug=False):
        """Start API service [server]"""
        if self.app is None:
            self.create_app()
        
        # [Key optimization]: Check port [if it's already occupied]
        # [Avoid conflicts with other] processes [in dual-process keep-alive mechanism]
        import socket
        
        host = self.config.get('api_host', '0.0.0.0')
        port = self.config.get('api_port', 8000)
        
        # Check port [availability]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                self.logger.warning(f"Port {port} is already occupied, FastAPI service will not start")
                self.logger.info("This is normal behavior for dual-process keep-alive mechanism, ensuring only one process runs the service")
                return  # Port occupied, do not start server
                
        except Exception as e:
            self.logger.warning(f"Port checking failed: {e}")
        
        # [Special] configuration [in] debug [mode]
        if debug:
            self.logger.info("Enabling API server debug mode: enabling hot reload, setting log level to debug")
            # [Temporarily modify] configuration [to support] debug [mode]
            reload = True
            log_level = 'debug'
            workers = 1  # Only one worker in debug mode
        else:
            reload = self.config.get('api_reload', False)
            log_level = self.config.get('log_level', 'info').lower()
            workers = self.config.get('api_workers', 1)
        
        # [Optimize] uvicorn configuration, [improve compatibility with] dual-process [keep-alive mechanism]
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            reload=reload,
            workers=workers,
            log_level=log_level,
            access_log=True,
            # [Key optimization]: [Add graceful shutdown and] timeout configuration
            timeout_keep_alive=5,
            timeout_notify=30,
            timeout_graceful_shutdown=10,
            # [Use] asyncio [event] loop, [improve stability]
            loop="asyncio",
        )
        
        self.server = uvicorn.Server(config)
        
        self.logger.info(f"Starting FastAPI service: {host}:{port}")
        self.logger.info(f"API documentation address: http://{host}:{port}/docs")
        
        try:
            await self.server.serve()
        except Exception as e:
            self.logger.error(f"FastAPI service startup failed: {e}")
            # When server startup [fails], [record] error [but don't throw] exception
            # [Let the] dual-process [keep-alive mechanism decide whether to] restart process
            self.logger.info("FastAPI service startup failed, but process will continue to run to support other functions")
    
    async def stop(self):
        """Stop API service [server]"""
        if self.server:
            self.logger.info("Stopping FastAPI service...")
            self.server.should_exit = True
            await self.server.shutdown()
            self.logger.info("FastAPI service stopped")
    
    def is_running(self) -> bool:
        """Check service [server if it's running]"""
        return self.server is not None and self.server.started
    
    def get_server_info(self) -> dict:
        """Get service [server] info"""
        return {
            "host": self.config.get('api_host', '0.0.0.0'),
            "port": self.config.get('api_port', 8000),
            "status": "running" if self.is_running() else "stopped",
            "docs_url": f"http://{self.config.get('api_host', '0.0.0.0')}:{self.config.get('api_port', 8000)}/docs"
        }


async def start_api_server():
    """Start API service [server convenience] function"""
    server = APIServer()
    await server.start()