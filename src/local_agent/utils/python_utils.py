#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python utility class
Provides Python environment-related utility functions, including getting Python executable commands, validating versions, etc.

Main features:
1. Get Python executable commands (priority from cache)
2. Validate if Python version meets requirements
3. Find available Python environments in the system

Usage example:
    from local_agent.utils.python_utils import PythonUtils
    python_path = PythonUtils.get_python_executable()
    version_ok = PythonUtils.validate_python_version(python_path)
"""

import os
import sys
import glob
from typing import Optional

# Import project global components
from ..logger import get_logger
# Import enhanced subprocess utility
from .subprocess_utils import run_with_logging, run_with_logging_safe
# Delay import to avoid circular dependency
# from ..core.global_cache import cache
# Directly define constant to avoid circular dependency
from ..core.constants import PYTHON_CACHE_KEY


class PythonUtils:
    """Pythonutilityclass"""


    @staticmethod
    def get_python_check() -> Optional[str]:
        """
        Check and get Python environment, prompt user if not found
        
        Returns:
            Optional[str]: Python executable file path, returns None if user cancels
        """
        logger = get_logger()
        
        while True:
            python_path = PythonUtils.get_python_executable()
            
            if python_path:
                return python_path
            
            # If no suitable Python environment found, show message window
            logger.error("No available Python environment found")
            # Delay import to avoid circular dependency
            from ..utils.message_tool import show_message_box
            
            result = show_message_box(
                msg="No available Python environment found. Please install Python 3.8 or higher and try again.",
                title="Python Environment Initialization Failed",
                cancel_show=True,
                confirm_text="Retry",
                cancel_text="Abandon"
            )
            
            if result == "Abandon":
                logger.error("User chose to abandon Python environment initialization")
                return None
            else:
                logger.info("User chose to retry, re-searching for Python environment")
                continue

    
    @staticmethod
    def get_python_executable() -> Optional[str]:
        """
        Get Python executable path, priority from cache
        
        Returns:
            Optional[str]: Python executable file path, returns None if not found
        """
        logger = get_logger()
        
        # Delay import to avoid circular dependency
        from ..core.global_cache import cache
        
        # 1. Priority from cache
        cached_python = cache.get(PYTHON_CACHE_KEY)
        if cached_python:
            logger.info(f"Python path obtained from cache: {cached_python}")
            if os.path.exists(cached_python):
                return cached_python
            else:
                logger.warning(f"Cached Python path does not exist: {cached_python}, re-searching")
                cache.delete(PYTHON_CACHE_KEY)
        
        # 2. If cache not found or path invalid, re-search
        python_path = PythonUtils._find_python_executable()
        if python_path:
            # Validate version and store in cache
            if PythonUtils._validate_python_version(python_path):
                cache.set(PYTHON_CACHE_KEY, python_path)
                logger.info(f"Found and cached Python path: {python_path}")
                return python_path
        
        logger.error("No available Python executable found")
        return None
    
    @staticmethod
    def _find_python_executable() -> Optional[str]:
        """
        Find executable Python command in system
        Reference implementation from pythonInit method in host_init.py
        
        Returns:
            Optional[str]: Python executable file path, returns None if not found
        """
        logger = get_logger()
        
        # Common Python installation paths
        common_paths = [
            # Python in system PATH
            "python", "python3", "python.exe", "python3.exe",
            # Common installation paths
            "C:\\Python3*\\python.exe",
            "C:\\Python*\\python.exe", 
            "D:\\Python3*\\python.exe",
            "D:\\Python*\\python.exe",
            "E:\\Python3*\\python.exe",
            "E:\\Python*\\python.exe",
            # Python under user directory
            os.path.expanduser("~\\AppData\\Local\\Programs\\Python\\Python3*\\python.exe"),
            os.path.expanduser("~\\AppData\\Local\\Programs\\Python\\Python*\\python.exe")
        ]
        
        # Check if packaged as exe (if exe, don't depend on current interpreter)
        is_frozen = getattr(sys, 'frozen', False)
        
        # If not packaged exe, can try current Python interpreter
        if not is_frozen and hasattr(sys, 'executable') and sys.executable:
            if os.path.exists(sys.executable):
                logger.info(f"Using current Python interpreter: {sys.executable}")
                return sys.executable
        
        # Find Python in PATH environment variable (priority)
        for cmd in ["python", "python3", "py"]:
            try:
                result = run_with_logging([cmd, "--version"], 
                                        command_name="check_python_version",
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    # Get full path
                    path_result = run_with_logging([cmd, "-c", "import sys; print(sys.executable)"],
                                                 command_name="get_python_executable_path",
                                                 capture_output=True, text=True, timeout=5)
                    if path_result.returncode == 0:
                        python_path = path_result.stdout.strip()
                        if os.path.exists(python_path):
                            logger.info(f"Found Python in PATH: {python_path}")
                            return python_path
            except Exception:
                continue
        
        # Find in common installation paths
        for pattern in common_paths:
            try:
                matches = glob.glob(pattern)
                for match in matches:
                    if os.path.exists(match):
                        logger.info(f"Found Python in common path: {match}")
                        return match
            except Exception:
                continue
        
        logger.warning("No available Python executable found")
        return None
    
    @staticmethod
    def _validate_python_version(python_path: str) -> bool:
        """
        Validate Python version is >= 3.8
        
        Args:
            python_path: Python executable file path
            
        Returns:
            bool: Whether version meets requirements
        """
        logger = get_logger()
        
        try:
            # Get Python version info
            result = run_with_logging([python_path, "-c", 
                                      "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
                                     command_name="validate_python_version",
                                     capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                version_str = result.stdout.strip()
                logger.info(f"Python version: {version_str}")
                
                # Parse version number
                try:
                    major, minor = map(int, version_str.split('.'))
                    if major > 3 or (major == 3 and minor >= 8):
                        logger.info(f"Python version meets requirements: {version_str}")
                        return True
                    else:
                        logger.warning(f"Python version too low: {version_str}, requires >=3.8")
                        return False
                except ValueError:
                    logger.warning(f"Unable to parse Python version: {version_str}")
                    return False
            else:
                logger.warning(f"Failed to obtain Python version: {result.stderr}")
                return False
                
        except Exception as e:
            logger.warning(f"Error occurred while validating Python version: {str(e)}")
            return False
    
    @staticmethod
    def validate_python_version(python_path: str) -> bool:
        """
        Public Python version validation method
        
        Args:
            python_path: Python executable file path
            
        Returns:
            bool: Whether version meets requirements
        """
        return PythonUtils._validate_python_version(python_path)
    
    @staticmethod
    def clear_python_cache():
        """
        Clear Python path cache
        """
        # Delay import to avoid circular dependency
        from ..core.global_cache import cache
        cache.delete(PYTHON_CACHE_KEY)
        get_logger().info("Python path cache cleared")
    