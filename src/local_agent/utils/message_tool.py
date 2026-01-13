#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Message tool class - HTTP version
Calls message box service through HTTP API, implements dual-process mechanism
"""

import os
import sys
import requests
import logging
from pathlib import Path
from typing import Optional, Dict, Any


class MessageTool:
    """Message utility class, calls message box service through HTTP API"""
    
    def __init__(self, api_url: str = "http://127.0.0.1:8001"):
        """Initialize message utility class"""
        self.logger = logging.getLogger(__name__)
        self.api_url = api_url
        
        # Get current program directory
        self.current_dir = Path(sys.executable).parent if hasattr(sys, 'frozen') else Path.cwd()
        
        # Detect running environment
        self.is_development = self._detect_development_environment()
        
        self.logger.info(f"Message tool initialized - Environment: {'Development' if self.is_development else 'Production'}, API address: {self.api_url}")
        
        # Check if API service is available
        if self._check_api_available():
            self.logger.info("Message box API service connected successfully")
        else:
            self.logger.warning("Message box API service unavailable, please ensure Process A is running")
    
    def _detect_development_environment(self) -> bool:
        """
        Detect if it's development environment
        
        Returns:
            bool: True indicates development environment, False indicates production environment
        """
        # Method 1: Check if running as Python script (not packaged exe)
        if not hasattr(sys, 'frozen'):
            return True
        
        # Method 2: Check if in development directory structure
        if 'src' in str(self.current_dir) or 'local_agent' in str(self.current_dir):
            return True
        
        # Method 3: Check if development environment marker files exist
        dev_files = [
            'requirements.txt',
            'setup.py',
            'pyproject.toml',
            '.git',
            'src'
        ]
        
        for dev_file in dev_files:
            if (self.current_dir / dev_file).exists():
                return True
        
        # Method 4: Check environment variable
        dev_env = os.environ.get('LOCAL_AGENT_DEV_MODE', '').lower()
        if dev_env in ('true', '1', 'yes', 'development'):
            return True
        
        return False
    
    def _check_api_available(self) -> bool:
        """
        Check if API service is available
        
        Returns:
            bool: True indicates API service is available
        """
        try:
            response = requests.get(f"{self.api_url}/", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def show_message_box(self, 
                        message: str, 
                        title: str = "System Prompt",
                        confirm_show: bool = True,
                        cancel_show: bool = False,
                        confirm_text: str = "OK",
                        cancel_text: str = "Cancel",
                        timeout: int = 0,
                        confirm_timeout: Optional[int] = None,
                        cancel_timeout: Optional[int] = None) -> Optional[str]:
        """
        Show message box - via HTTP API call
        
        Args:
            message: Message content
            title: Title
            confirm_show: Whether to show confirm button
            cancel_show: Whether to show cancel button
            confirm_text: Confirm button text
            cancel_text: Cancel button text
            timeout: Timeout in seconds, 0 means no timeout (wait for user feedback)
            confirm_timeout: Confirm button timeout in seconds, None means no timeout (countdown display)
            cancel_timeout: Cancel button timeout in seconds, None means no timeout (countdown display)
            
        Returns:
            Optional[str]: User-selected button text, returns None on timeout or error
        """
        try:
            # Check if API service is available
            if not self._check_api_available():
                self.logger.error("Message box API service unavailable, cannot display message box")
                self.logger.error("Please ensure Process A is running and providing FastAPI service on port 8001")
                return None
            
            # Build API request data - force timeout=0 to ensure no timeout
            data = {
                "message": message,
                "title": title,
                "confirm_show": confirm_show,
                "cancel_show": cancel_show,
                "confirm_text": confirm_text,
                "cancel_text": cancel_text,
                "timeout": 0,  # Force set to 0 to ensure no timeout, completely wait for user feedback
                "confirm_timeout": confirm_timeout,
                "cancel_timeout": cancel_timeout
            }
            
            self.logger.debug(f"Calling message box API: {self.api_url}/show_message")
            self.logger.debug(f"Message content: {message}, Title: {title}")
            
            # Call API - use very long timeout to simulate synchronous effect
            # timeout=0 means infinite wait, but requests doesn't support 0, so use maximum integer
            response = requests.post(
                f"{self.api_url}/show_message",
                json=data,
                timeout=None  # No timeout, completely wait for user feedback
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    # Execute successfully, return user choice
                    user_choice = result.get("user_choice")
                    self.logger.info(f"User selected: {user_choice}")
                    return user_choice
                else:
                    # API execution error
                    error_msg = result.get("error", "Unknown error")
                    self.logger.error(f"Message box API execution failed: {error_msg}")
                    return None
            else:
                # HTTP request failure
                self.logger.error(f"Message box API request failed: {response.status_code}")
                return None
                
        except requests.Timeout:
            self.logger.warning("Message box API request timeout")
            return None
        except requests.RequestException as e:
            self.logger.error(f"Message box API request exception: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Message box call exception: {e}")
            return None
    

    
    def show_confirm_dialog(self, 
                           message: str, 
                           title: str = "Confirm Operation") -> bool:
        """
        Show confirmation dialog (Confirm/Cancel)
        
        Args:
            message: Message content
            title: Title
            
        Returns:
            bool: True indicates user confirmed, False indicates user canceled or error
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=True,
            confirm_text="OK",
            cancel_text="Cancel"
        )
        
        return result == "OK"
    
    def show_info_dialog(self, 
                        message: str, 
                        title: str = "Information Prompt") -> bool:
        """
        Show information dialog (only OK button)
        
        Args:
            message: Message content
            title: Title
            
        Returns:
            bool: Always returns True (indicates user has viewed)
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="OK"
        )
        
        return result is not None
    
    def show_warning_dialog(self, 
                           message: str, 
                           title: str = "Warning") -> bool:
        """
        Show warning dialog
        
        Args:
            message: Message content
            title: Title
            
        Returns:
            bool: True indicates user confirmed, False indicates error
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="OK"
        )
        
        return result is not None
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get environment information
        
        Returns:
            Dict[str, Any]: Dictionary containing environment information
        """
        return {
            "is_development": self.is_development,
            "current_directory": str(self.current_dir),
            "api_url": self.api_url,
            "api_available": self._check_api_available(),
            "python_executable": sys.executable,
            "frozen": hasattr(sys, 'frozen')
        }


# Global message utility instance
_message_tool = None


def get_message_tool() -> MessageTool:
    """
    Get global message tool instance
    
    Returns:
        MessageTool: Message tool instance
    """
    global _message_tool
    if _message_tool is None:
        _message_tool = MessageTool()
    return _message_tool


def show_message_box(msg: str, 
                    title: str = "System Prompt",
                    confirm_show: bool = True,
                    cancel_show: bool = False,
                    confirm_text: str = "OK",
                    cancel_text: str = "Cancel",
                    confirm_timeout: Optional[int] = None,
                    cancel_timeout: Optional[int] = None) -> Optional[str]:
    """
    Convenience function to show message box
    
    Args:
        msg: Message content
        title: Title
        confirm_show: Whether to show confirm button
        cancel_show: Whether to show cancel button
        confirm_text: Confirm button text
        cancel_text: Cancel button text
        confirm_timeout: Confirm button timeout in seconds, None means no timeout (countdown display)
        cancel_timeout: Cancel button timeout in seconds, None means no timeout (countdown display)
        
    Returns:
        Optional[str]: User-selected button text
    """
    tool = get_message_tool()
    return tool.show_message_box(
        message=msg,
        title=title,
        confirm_show=confirm_show,
        cancel_show=cancel_show,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        confirm_timeout=confirm_timeout,
        cancel_timeout=cancel_timeout
    )


def show_confirm_dialog(msg: str, title: str = "Confirm Operation") -> bool:
    """
    Convenience function to show confirmation dialog
    
    Args:
        msg: Message content
        title: Title
        
    Returns:
        bool: True indicates user confirmed
    """
    tool = get_message_tool()
    return tool.show_confirm_dialog(message=msg, title=title)


def show_info_dialog(msg: str, title: str = "Information Prompt") -> bool:
    """
    Convenience function to show information dialog
    
    Args:
        msg: Message content
        title: Title
        
    Returns:
        bool: Always returns True
    """
    tool = get_message_tool()
    return tool.show_info_dialog(message=msg, title=title)


def show_warning_dialog(msg: str, title: str = "Warning") -> bool:
    """
    Convenience function to show warning dialog
    
    Args:
        msg: Message content
        title: Title
        
    Returns:
        bool: True indicates user confirmed
    """
    tool = get_message_tool()
    return tool.show_warning_dialog(message=msg, title=title)


if __name__ == "__main__":
    # Test code
    import logging
    logging.basicConfig(level=logging.INFO)
    
    tool = MessageTool()
    
    # Show environment info
    env_info = tool.get_environment_info()
    print("Environment info:")
    for key, value in env_info.items():
        print(f"  {key}: {value}")
    
    # Test message box
    print("\nTesting info dialog...")
    result = tool.show_info_dialog("This is a test message box", "Test Title")
    print(f"Info dialog result: {result}")
    
    print("\nTesting confirm dialog...")
    result = tool.show_confirm_dialog("Are you sure you want to perform this operation?", "Confirm Operation")
    print(f"Confirm dialog result: {result}")