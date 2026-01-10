#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local message window component
Provides tkinter-based message box functionality, replacing the original exe calls
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum


class MessageType(Enum):
    """Message type enumeration"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CONFIRM = "confirm"


class ButtonType(Enum):
    """Button type enumeration"""
    OK = "OK"
    CANCEL = "Cancel"
    YES = "Yes"
    NO = "No"
    RETRY = "Retry"
    IGNORE = "Ignore"


@dataclass
class MessageResult:
    """Message box result"""
    success: bool
    user_choice: Optional[str] = None
    error: Optional[str] = None


class MessageWindow:
    """Local message window class"""
    
    def __init__(self):
        """Initialize message window"""
        self.logger = logging.getLogger(__name__)
        self._root = None
        self._thread = None
        self._result = None
        self._timeout_thread = None
        self._is_running = False
        
    def _ensure_tk_root(self):
        """Ensure tkinter root window exists"""
        if self._root is None:
            # Create hidden root window
            self._root = tk.Tk()
            self._root.withdraw()  # Hide main window
            self._root.title("Message Box Service")
            
    def _create_custom_messagebox(self, 
                                 message: str, 
                                 title: str = "System Prompt",
                                 confirm_show: bool = True,
                                 cancel_show: bool = False,
                                 confirm_text: str = "OK",
                                 cancel_text: str = "Cancel") -> Optional[str]:
        """Create custom message box"""
        try:
            # Create top-level window
            top = tk.Toplevel(self._root)
            top.title(title)
            top.geometry("700x300")
            top.resizable(False, False)
            
            # Set up window attributes to ensure always on top
            top.attributes('-topmost', True)  # Always on top
            top.transient(self._root)         # Set as child window of main window
            top.grab_set()                    # Exclusive focus
            
            # Disable close button but keep title bar
            top.protocol('WM_DELETE_WINDOW', lambda: None)  # Disable close button
            
            # Re-top window when it gains focus
            def on_focus(event):
                top.attributes('-topmost', True)
            top.bind('<FocusIn>', on_focus)
            
            # Set up window icon (if available)
            try:
                top.iconbitmap("")
            except:
                pass
            
            # Create message content
            message_frame = ttk.Frame(top, padding="10")
            message_frame.pack(fill=tk.BOTH, expand=True)
            
            # Message text
            message_label = ttk.Label(
                message_frame, 
                text=message, 
                wraplength=350,
                justify=tk.CENTER,
                font=("Microsoft YaHei", 10)
            )
            message_label.pack(pady=20)
            
            # Button frame
            button_frame = ttk.Frame(message_frame)
            button_frame.pack(side=tk.BOTTOM, pady=10)
            
            result = [None]
            
            def on_button_click(choice: str):
                result[0] = choice
                top.destroy()
            
            # Add confirm button
            if confirm_show:
                confirm_btn = ttk.Button(
                    button_frame, 
                    text=confirm_text, 
                    command=lambda: on_button_click(confirm_text)
                )
                confirm_btn.pack(side=tk.LEFT, padx=5)
            
            # Add cancel button
            if cancel_show:
                cancel_btn = ttk.Button(
                    button_frame, 
                    text=cancel_text, 
                    command=lambda: on_button_click(cancel_text)
                )
                cancel_btn.pack(side=tk.LEFT, padx=5)
            
            # If no buttons, add default confirm button
            if not confirm_show and not cancel_show:
                ok_btn = ttk.Button(
                    button_frame, 
                    text=confirm_text, 
                    command=lambda: on_button_click(confirm_text)
                )
                ok_btn.pack(side=tk.LEFT, padx=5)
            
            # Center window - ensure window is fully rendered before calculating position
            top.update()  # Force update all pending tasks
            top.update_idletasks()
            
            # Get accurate window dimensions
            width = top.winfo_reqwidth()
            height = top.winfo_reqheight()
            
            # Calculate center position
            x = (top.winfo_screenwidth() - width) // 2
            y = (top.winfo_screenheight() - height) // 2
            
            # Set window position and dimensions
            top.geometry(f"{width}x{height}+{x}+{y}")
            
            # Wait for window to close
            top.wait_window(top)
            
            return result[0]
            
        except Exception as e:
            self.logger.error(f"Create custom message box failed: {e}")
            return None
    
    def show_message(self, 
                    message: str, 
                    title: str = "System Prompt",
                    confirm_show: bool = True,
                    cancel_show: bool = False,
                    confirm_text: str = "OK",
                    cancel_text: str = "Cancel",
                    timeout: int = 0) -> MessageResult:
        """Show message box
        
        Args:
            message: Message content
            title: Title
            confirm_show: Whether to show confirm button
            cancel_show: Whether to show cancel button
            confirm_text: Confirm button text
            cancel_text: Cancel button text
            timeout: Timeout time (seconds), 0 means no timeout
            
        Returns:
            MessageResult: Message box result
        """
        try:
            self._ensure_tk_root()
            
            # Set up timeout handling
            if timeout > 0:
                self._setup_timeout(timeout)
            
            # Show message box in main thread
            user_choice = self._create_custom_messagebox(
                message=message,
                title=title,
                confirm_show=confirm_show,
                cancel_show=cancel_show,
                confirm_text=confirm_text,
                cancel_text=cancel_text
            )
            
            # Cancel timeout handling
            if timeout > 0:
                self._cancel_timeout()
            
            if user_choice is not None:
                self.logger.info(f"User selected: {user_choice}")
                return MessageResult(success=True, user_choice=user_choice)
            else:
                return MessageResult(success=False, error="User did not select or message box closed")
                
        except Exception as e:
            self.logger.error(f"Show message box failed: {e}")
            return MessageResult(success=False, error=str(e))
    
    def _setup_timeout(self, timeout: int):
        """Set up timeout handling"""
        def timeout_handler():
            time.sleep(timeout)
            if self._is_running:
                # Auto close message box after timeout
                try:
                    if self._root:
                        # Here you can add timeout handling logic
                        self.logger.warning(f"Message box timeout, auto closing")
                except:
                    pass
        
        self._timeout_thread = threading.Thread(target=timeout_handler, daemon=True)
        self._timeout_thread.start()
    
    def _cancel_timeout(self):
        """Cancel timeout handling"""
        self._is_running = False
    
    def show_info(self, message: str, title: str = "Information Prompt") -> MessageResult:
        """Show info dialog"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="OK"
        )
    
    def show_warning(self, message: str, title: str = "Warning") -> MessageResult:
        """Show warning dialog"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="OK"
        )
    
    def show_confirm(self, message: str, title: str = "Confirm Operation") -> MessageResult:
        """Show confirm dialog"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=True,
            confirm_text="OK",
            cancel_text="Cancel"
        )
    
    def show_error(self, message: str, title: str = "Error") -> MessageResult:
        """Show error dialog"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="OK"
        )
    
    def cleanup(self):
        """Clean up resources"""
        self._is_running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except:
                pass
            self._root = None


def create_message_window() -> MessageWindow:
    """Create message window instance"""
    return MessageWindow()