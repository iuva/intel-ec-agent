#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System tray utility class
Used to display application icons and menus in the system tray
"""

import sys
import os
import threading
import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any


try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    

try:
    import win32api
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class SystemTray:
    """System tray class"""
    
    def __init__(self, name: str = "agent", icon_path: Optional[str] = None):
        """Initialize system tray"""
        self.name = name
        self.logger = logging.getLogger(__name__)
        self.icon = None
        self.tray_icon = None
        self.is_running = False
        
        # Check dependencies
        if not HAS_PYSTRAY:
            self.logger.warning("pystray not installed, system tray functionality unavailable")
            return
        
        # Create or load icon
        self.icon = self._create_icon(icon_path)
        
        # Create menu
        self.menu = self._create_menu()
        
        self.logger.info("System tray initialized")
    
    def _create_icon(self, icon_path: Optional[str] = None) -> Optional[Image.Image]:
        """Create or load icon"""
        try:
            if icon_path and os.path.exists(icon_path):
                # Load existing icon file
                return Image.open(icon_path)
            else:
                # Create simple default icon
                return self._create_default_icon()
        except Exception as e:
            self.logger.warning(f"Create icon failed: {e}")
            return self._create_default_icon()
    
    def _create_default_icon(self) -> Image.Image:
        """Create default icon"""
        # Create a simple circular icon
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw blue circle
        draw.ellipse((2, 2, 62, 62), fill=(0, 120, 215, 255))
        
        # Draw white letter "L"
        draw.text((20, 15), "L", fill=(255, 255, 255, 255), font_size=30)
        
        return image
    
    def _create_menu(self) -> pystray.Menu:
        """Create tray menu"""
        # Create menu items
        menu_items = [
            # pystray.MenuItem("Show Status", self._show_status),
            # pystray.MenuItem("RestartService", self._restart_service),
            # pystray.MenuItem("StopService", self._stop_service),
            # pystray.MenuItem("-", None),  # Separator
            # pystray.MenuItem("Exit", self._exit_app)
        ]
        
        return pystray.Menu(*menu_items)
    
    def _show_status(self, icon, item):
        """Show status information"""
        self.logger.info("Show application status")
        # Here you can display status dialog or notification
        if HAS_WIN32:
            try:
                win32api.MessageBox(
                    0, 
                    "Local Agent Service is running\n\nService Status: Normal\nAPI Port: 8001\nMessage Box Service: Running", 
                    "Service Status", 
                    win32con.MB_OK | win32con.MB_ICONINFORMATION
                )
            except Exception as e:
                self.logger.warning(f"Show service status dialog failed: {e}")
    
    def _restart_service(self, icon, item):
        """Restart service"""
        self.logger.info("Restart service")
        # Here you can implement restart logic
        if HAS_WIN32:
            try:
                win32api.MessageBox(
                    0, 
                    "Service restart feature is under development...", 
                    "Restart Service", 
                    win32con.MB_OK | win32con.MB_ICONINFORMATION
                )
            except Exception as e:
                self.logger.warning(f"Show restart dialog failed: {e}")
    
    def _stop_service(self, icon, item):
        """Stop service"""
        self.logger.info("Stop service")
        # Here you can implement stop logic
        if HAS_WIN32:
            try:
                result = win32api.MessageBox(
                    0, 
                    "Are you sure you want to stop the Local Agent Service?\n\nAfter stopping, you will need to manually restart it.", 
                    "Stop Service", 
                    win32con.MB_YESNO | win32con.MB_ICONQUESTION
                )
                if result == win32con.IDYES:
                    self.logger.info("User confirmed to stop service")
                    # Here you can add StopService logic
            except Exception as e:
                self.logger.warning(f"Show stop dialog failed: {e}")
    
    def _exit_app(self, icon, item):
        """Exit application"""
        self.logger.info("Exit application")
        if HAS_WIN32:
            try:
                result = win32api.MessageBox(
                    0, 
                    "Are you sure you want to exit the Local Agent Service?\n\nAfter exiting, the message box feature will be unavailable.", 
                    "Exit Confirmation", 
                    win32con.MB_YESNO | win32con.MB_ICONQUESTION
                )
                if result == win32con.IDYES:
                    self.logger.info("User confirmed to exit application")
                    self.stop()
                    # Force exit process
                    os._exit(0)
            except Exception as e:
                self.logger.warning(f"Show exit dialog failed: {e}")
    
    def start(self):
        """Start system tray"""
        if not HAS_PYSTRAY or self.icon is None:
            self.logger.warning("System tray functionality unavailable, skipping startup")
            return
        
        if self.is_running:
            self.logger.warning("System tray already running")
            return
        
        try:
            # Create system tray icon
            self.tray_icon = pystray.Icon(
                self.name,
                self.icon,
                self.name,
                self.menu
            )
            
            # Run system tray in a separate thread
            def run_tray():
                try:
                    self.tray_icon.run()
                except Exception as e:
                    self.logger.error(f"System tray runtime exception: {e}")
            
            tray_thread = threading.Thread(target=run_tray, daemon=True)
            tray_thread.start()
            
            self.is_running = True
            self.logger.info("System tray started successfully")
            
        except Exception as e:
            self.logger.error(f"Start system tray failed: {e}")
    
    def stop(self):
        """Stop system tray"""
        if self.tray_icon and self.is_running:
            try:
                self.tray_icon.stop()
                self.is_running = False
                self.logger.info("System tray stopped")
            except Exception as e:
                self.logger.error(f"Stop system tray failed: {e}")
    
    def notify(self, title: str, message: str, duration: int = 5):
        """Show system notification"""
        if self.tray_icon and self.is_running:
            try:
                self.tray_icon.notify(message, title)
                self.logger.info(f"Show notification: {title} - {message}")
            except Exception as e:
                self.logger.warning(f"Show notification failed: {e}")


def create_system_tray(name: str = "agent", icon_path: Optional[str] = None) -> SystemTray:
    """Create system tray instance"""
    return SystemTray(name=name, icon_path=icon_path)


def start_system_tray(name: str = "agent", icon_path: Optional[str] = None) -> SystemTray:
    """Start system tray"""
    tray = create_system_tray(name, icon_path)
    tray.start()
    return tray


if __name__ == "__main__":
    # Test code
    import logging
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    # Create and start system tray
    tray = start_system_tray()
    
    # Show test notification
    tray.notify("Test Notification", "System tray function test successful")
    
    # Keep running for a while
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    
    # Stop system tray
    tray.stop()