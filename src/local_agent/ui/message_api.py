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
from local_agent.core.dmr import DMR
from local_agent.core.ifwi_manager import run_flash_cli
from typing import Dict, Any
from ..utils.version_utils import get_app_version
from ..utils.subprocess_utils import run_con_or_none, run_async, run_as_admin
import subprocess

# Import local message window component
from .message_window import create_message_window, MessageResult


class IFWIFlashRequest(BaseModel):
    """IFWI flash request model — forwarded here by Process B (Session 0)
    because the flash programmer device is only visible in Session 1."""
    flash_cli: str
    image_path: str
    timeout_sec: int = 1800


class IFWIFlashResponse(BaseModel):
    """IFWI flash response model, mirrors ifwi_manager.IFWIFlashResult"""
    success: bool = False
    duration_sec: float = 0.0
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""
    programmer_type: str = ""
    stages: list = []


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
                "version": get_app_version(),
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
            res = EK.start_test(body['tc_id'], body['cycle_name'], body['user_name'])
            if res:
                return MessageResponse(
                    success=True,
                    user_choice="confirm"
                )
            else:
                return MessageResponse(
                    success=False,
                    error="Test start failed"
                )
        
        
        @self.app.get("/get_sut", response_model=MessageResponse)
        async def get_sut() -> MessageResponse:
            """
            Because EK program has user interface, this interface should be called using service for startup
            """

            if(DMR.version() is None):
                return MessageResponse(
                    success=False,
                    error="DMR is not found"
                )

            run_async(['dmr-config', 'sut'])


            return MessageResponse(
                success=True,
                user_choice="confirm"
            )
                
        @self.app.get("/get_sut_status", response_model=MessageResponse)
        async def get_sut_status() -> MessageResponse:
            res = run_con_or_none(
                        ['dmr-config', 'status', '--json'],
                        command_name='dmr-config_status',
                        capture_output=True,
                        text=True,
                        timeout=100  # 10 second timeout
                    )
            self.logger.info(type(res))
            return MessageResponse(
                success=True,
                user_choice=res
            )
                
        @self.app.get("/kill_sut", response_model=MessageResponse)
        async def kill_sut() -> MessageResponse:
            
            run_as_admin(
                ['taskkill', '/f', '/im', 'dmr-config.exe'],
                command_name='taskkill_dmr-config.exe',
                capture_output=True,
                text=True,
                timeout=100  # 10 second timeout
            )

            return MessageResponse(
                success=True,
                user_choice="confirm"
            )

        @self.app.post("/ifwi/flash", response_model=IFWIFlashResponse)
        async def ifwi_flash(request: IFWIFlashRequest) -> IFWIFlashResponse:
            """Flash an IFWI image. Runs here (Process A, Session 1) because
            the flash programmer device is not visible to Process B
            (Session 0 service) — see ifwi_manager.IFWIManager.flash().
            """
            # Blocking subprocess (up to timeout_sec) runs in a worker thread
            # so it doesn't stall this event loop's other endpoints.
            try:
                # run_flash_cli() already self-bounds via its internal kill
                # timer + proc.wait(timeout=60); this outer bound is just a
                # belt-and-suspenders cap in case the worker thread itself
                # never returns.
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        run_flash_cli, request.flash_cli, request.image_path, request.timeout_sec
                    ),
                    timeout=request.timeout_sec + 90,
                )
            except asyncio.TimeoutError:
                self.logger.error("IFWI flash worker thread did not return in time")
                return IFWIFlashResponse(
                    error="flash worker thread did not return in time",
                    skipped=True,
                    skip_reason="worker_timeout",
                )
            return IFWIFlashResponse(
                success=result.success,
                duration_sec=result.duration_sec,
                error=result.error,
                skipped=result.skipped,
                skip_reason=result.skip_reason,
                programmer_type=result.programmer_type,
                stages=result.stages,
            )
        
        

        
        # One-time priming flag for GetAsyncKeyState
        _input_primed = {"done": False}

        @self.app.get("/activity/poll")
        async def activity_poll():
            """Poll user input activity from Session 1.

            Called by Session 0 (service) InputDetector as a cross-session proxy.
            Returns keyboard/mouse activity description in the same format as
            InputDetector.check().
            """
            import ctypes
            import ctypes.wintypes

            parts: list = []

            # --- Keyboard scan ---
            _VK_MAP_SIMPLE = {
                0x08: "Bksp", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc",
                0x20: "Space", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
                0x2E: "Del",
            }
            _VK_MAP_SIMPLE.update({k: chr(k) for k in range(0x30, 0x3A)})  # 0-9
            _VK_MAP_SIMPLE.update({k: chr(k) for k in range(0x41, 0x5B)})  # A-Z
            _VK_MAP_SIMPLE.update({0x70 + i: f"F{i+1}" for i in range(12)})  # F1-F12

            _MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
            _SCAN_RANGE = (
                list(range(0x08, 0x0E)) + list(range(0x1B, 0x2F)) +
                list(range(0x30, 0x5B)) + list(range(0x60, 0x70)) +
                list(range(0x70, 0x88)) + list(range(0xBA, 0xE0))
            )

            # Prime GetAsyncKeyState on first call (clear stale 0x0001 bits)
            if not _input_primed["done"]:
                for vk in _SCAN_RANGE:
                    ctypes.windll.user32.GetAsyncKeyState(vk)
                ctypes.windll.user32.GetAsyncKeyState(0x01)  # LButton
                ctypes.windll.user32.GetAsyncKeyState(0x02)  # RButton
                ctypes.windll.user32.GetAsyncKeyState(0x04)  # MButton
                _input_primed["done"] = True
                # Return empty on first call (priming only)
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.wintypes.LONG), ("y", ctypes.wintypes.LONG)]
                pt = POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                return {
                    "activity": None,
                    "cursor_x": pt.x,
                    "cursor_y": pt.y,
                    "idle_ms": 0,
                }

            # Modifiers
            ctrl = (ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000) != 0
            shift = (ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000) != 0
            alt = (ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) != 0
            mods = []
            if ctrl: mods.append("Ctrl")
            if alt: mods.append("Alt")
            if shift: mods.append("Shift")

            pressed = []
            for vk in _SCAN_RANGE:
                if vk in _MODIFIER_VKS:
                    continue
                if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x0001:
                    name = _VK_MAP_SIMPLE.get(vk, f"VK_{vk:#04x}")
                    if mods:
                        name = "+".join(mods + [name])
                    pressed.append(name)
            if pressed:
                display = pressed[:5]
                if len(pressed) > 5:
                    display.append(f"...+{len(pressed)-5} more")
                parts.append(f"keyboard({', '.join(display)})")

            # --- Mouse position ---
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.wintypes.LONG), ("y", ctypes.wintypes.LONG)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cursor_x, cursor_y = pt.x, pt.y

            # --- Mouse clicks ---
            clicks = []
            if ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x0001:
                clicks.append("left")
            if ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x0001:
                clicks.append("right")
            if ctypes.windll.user32.GetAsyncKeyState(0x04) & 0x0001:
                clicks.append("middle")
            if clicks:
                parts.append(f"mouse_click({','.join(clicks)})")

            # --- GetLastInputInfo for idle_ms ---
            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.wintypes.UINT), ("dwTime", ctypes.wintypes.DWORD)]
            lii = LII()
            lii.cbSize = ctypes.sizeof(lii)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            tick = ctypes.windll.kernel32.GetTickCount()
            idle_ms = (tick - lii.dwTime) & 0xFFFFFFFF  # handle tick wrap

            return {
                "activity": " + ".join(parts) if parts else None,
                "cursor_x": cursor_x,
                "cursor_y": cursor_y,
                "idle_ms": idle_ms,
            }

        # Persistent state for screen comparison
        _screen_state = {"prev_frame": None, "sct": None, "monitor": None}
        _screen_lock = asyncio.Lock()

        @self.app.get("/activity/screen")
        async def activity_screen(threshold: float = 0.02):
            """Poll screen change from Session 1.

            Captures a thumbnail screenshot, compares to previous frame,
            returns whether the screen changed significantly.
            Called by Session 0 ScreenDetector as a cross-session proxy.
            """
            try:
                import mss
                from PIL import Image, ImageChops
            except ImportError:
                return {"changed": False, "error": "mss or Pillow not installed"}

            THUMB_W, THUMB_H = 160, 90
            PIXEL_DIFF_THRESHOLD = 10
            # Clock mask: bottom-right 15% x bottom 8%
            MASK_X = int(0.85 * THUMB_W)
            MASK_Y = int(0.92 * THUMB_H)

            async with _screen_lock:
                # Initialize mss on first call
                if _screen_state["sct"] is None:
                    _screen_state["sct"] = mss.mss()
                    monitors = _screen_state["sct"].monitors
                    _screen_state["monitor"] = monitors[1] if len(monitors) > 1 else monitors[0]

                sct = _screen_state["sct"]
                monitor = _screen_state["monitor"]

                # Capture and downsample to grayscale thumbnail
                try:
                    shot = sct.grab(monitor)
                    img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
                    thumb = img.convert("L").resize((THUMB_W, THUMB_H), Image.BILINEAR)
                except Exception as exc:
                    return {"changed": False, "error": str(exc)}

                prev = _screen_state["prev_frame"]
                if prev is None:
                    _screen_state["prev_frame"] = thumb
                    return {"changed": False, "diff_ratio": 0.0}

                # Pixel diff excluding clock region
                diff = ImageChops.difference(thumb, prev)
                diff_px = diff.load()
                changed_pixels = 0
                total_pixels = 0
                for y in range(THUMB_H):
                    for x in range(THUMB_W):
                        if x >= MASK_X and y >= MASK_Y:
                            continue
                        total_pixels += 1
                        if diff_px[x, y] > PIXEL_DIFF_THRESHOLD:
                            changed_pixels += 1

                ratio = changed_pixels / total_pixels if total_pixels > 0 else 0.0
                _screen_state["prev_frame"] = thumb

            return {
                "changed": ratio >= threshold,
                "diff_ratio": round(ratio, 4),
            }

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