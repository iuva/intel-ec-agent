#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Message box HTTP API service
Provides HTTP interface for message box functionality, called by other processes
Uses local message window to replace exe calls
"""

import asyncio
import logging
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel
from local_agent.core.ek import EK
from typing import Dict, Any

# Import local message window component
from .message_window import create_message_window, MessageResult


class MessageRequest(BaseModel):
    """Message request model"""
    message: str
    title: str = "System Prompt"
    confirm_show: bool = True
    cancel_show: bool = False
    confirm_text: str = "OK"
    cancel_text: str = "Cancel"
    timeout: int = 0
    confirm_timeout: Optional[int] = None
    cancel_timeout: Optional[int] = None


class MessageResponse(BaseModel):
    """Message response model"""
    success: bool
    user_choice: Optional[str] = None
    error: Optional[str] = None


class MessageAPIService:
    """Message box API service class"""
    
    def __init__(self, port: int = 8001):
        """Initialize API service"""
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.app = FastAPI(title="Message Box API Service", version="1.0.0")
        
        # Create local message window instance
        self.message_window = create_message_window()
        
        # Register routes
        self._setup_routes()
        
        self.logger.info(f"Message box API service initialized, port: {self.port}, using local message window")
    
    def _setup_routes(self):
        """Set up API routes"""
        
        @self.app.get("/")
        async def root():
            """Root path interface"""
            return {
                "service": "Message Box API Service",
                "status": "Running",
                "port": self.port,
                "message_type": "local_window"
            }
        
        @self.app.get("/health")
        async def health_check():
            """Health check interface"""
            return {
                "status": "healthy",
                "service": "Message Box API Service",
                "port": self.port,
                "message_type": "local_window"
            }
        
        
        @self.app.get("/username")
        async def username():
            """Get username"""
            import os
            user_name = os.environ.get('USERNAME')
            if not user_name:
                import getpass
                user_name = getpass.getuser()
            
            return user_name

        @self.app.post("/show_message", response_model=MessageResponse)
        async def show_message(request: MessageRequest) -> MessageResponse:
            """Show message box"""
            try:
                self.logger.debug(f"Show message box: title={request.title}, message={request.message}")
                
                # Use local message window to show message
                result = self.message_window.show_message(
                    message=request.message,
                    title=request.title,                                                                                                                                                                                                                                                                                                                                                                                                                                                                          
                    confirm_show=request.confirm_show,
                    cancel_show=request.cancel_show,
                    confirm_text=request.confirm_text,
                    cancel_text=request.cancel_text,
                    timeout=request.timeout,
                    confirm_timeout=request.confirm_timeout,
                    cancel_timeout=request.cancel_timeout
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
                self.logger.error(f"Message box call exception: {e}")
                return MessageResponse(
                    success=False,
                    error=f"Message box call exception: {str(e)}"
                )
        
        @self.app.post("/show_confirm", response_model=MessageResponse)
        async def show_confirm(message: str, title: str = "Confirm Operation") -> MessageResponse:
            """Show confirm dialog"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=True,
                confirm_text="Confirm",
                cancel_text="Cancel"
            )
            return await show_message(request)
        
        @self.app.post("/show_info", response_model=MessageResponse)
        async def show_info(message: str, title: str = "Information") -> MessageResponse:
            """Show info dialog"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=False,
                confirm_text="OK"
            )
            return await show_message(request)
        
        @self.app.post("/show_warning", response_model=MessageResponse)
        async def show_warning(message: str, title: str = "Warning") -> MessageResponse:
            """Show warning dialog"""
            request = MessageRequest(
                message=message,
                title=title,
                confirm_show=True,
                cancel_show=False,
                confirm_text="OK"
            )
            return await show_message(request)

        
        
        @self.app.post("/test_start", response_model=MessageResponse)
        async def test_start(body: Dict[str, Any]) -> MessageResponse:
            """
            Because EK program has user interface, this interface should be called using service for startup
            """
            EK.start_test(body['tc_id'], body['cycle_name'], body['user_name'])
            return MessageResponse(
                success=True,
                user_choice="confirm"
            )
        
        
        
        
        @self.app.get("/agent_update", response_model=MessageResponse)
        async def agent_update(cmd: str) -> MessageResponse:
            """
            Agent update
            """

            import subprocess

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # Hide window
            
            # [Use] CREATE_NEW_PROCESS_GROUP [to ensure batch] process [is independent]
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            
            # [Use] start [command to create] independent [process]
            subprocess.Popen(
                cmd, 
                shell=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # [Give batch] process [more] execution time, [ensure] update [script can fully] execute
            import time
            time.sleep(25)

            return MessageResponse(
                success=True,
                user_choice="confirm"
            )
    
    async def start_server(self):
        """Start FastAPI server"""
        import uvicorn
        
        self.logger.info(f"Starting message box API service, port: {self.port}")
        
        config = uvicorn.Config(
            app=self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()


def create_message_api_service(port: int = 8001) -> MessageAPIService:
    """Create message box API service instance"""
    return MessageAPIService(port=port)


async def run_message_api_service(port: int = 8001):
    """Run message box API service"""
    service = create_message_api_service(port)
    await service.start_server()


if __name__ == "__main__":
    # Test code
    import logging
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        service = create_message_api_service()
        await service.start_server()
    
    asyncio.run(test())