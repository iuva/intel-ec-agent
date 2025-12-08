#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python工具类
提供Python环境相关的工具函数，包括获取Python可执行命令、验证版本等功能

主要功能：
1. 获取Python可执行命令（优先从缓存获取）
2. 验证Python版本是否符合要求
3. 查找系统中可用的Python环境

使用示例：
    from local_agent.utils.python_utils import PythonUtils
    python_path = PythonUtils.get_python_executable()
    version_ok = PythonUtils.validate_python_version(python_path)
"""

import os
import sys
import glob
from typing import Optional

# 导入项目全局组件
from ..logger import get_logger
# 导入增强的子进程工具
from .subprocess_utils import run_with_logging, run_with_logging_safe
# 延迟导入以避免循环依赖
# from ..core.global_cache import cache
# 直接定义常量以避免循环依赖
PYTHON_CACHE_KEY = "python_path"


class PythonUtils:
    """Python工具类"""


    @staticmethod
    def get_python_check() -> Optional[str]:
        """
        检查并获取Python环境，如果找不到则提示用户
        
        Returns:
            Optional[str]: Python可执行文件路径，如果用户取消则返回None
        """
        logger = get_logger()
        
        while True:
            python_path = PythonUtils.get_python_executable()
            
            if python_path:
                return python_path
            
            # 如果找不到合适的Python环境，弹出消息窗口
            logger.error("未找到可用的Python环境")
            # 延迟导入以避免循环依赖
            from ..ui.message_proxy import show_message_box
            
            result = show_message_box(
                msg="未找到可用的python环境，请安装 3.8 或更高版本后进行重试",
                title="Python环境初始化失败"
            )
            
            if result == "cancel":
                logger.error("用户选择放弃Python环境初始化")
                return None
            else:
                logger.info("用户选择重试，重新查找Python环境")
                continue

    
    @staticmethod
    def get_python_executable() -> Optional[str]:
        """
        获取Python可执行命令路径，优先从缓存中获取
        
        Returns:
            Optional[str]: Python可执行文件路径，如果找不到则返回None
        """
        logger = get_logger()
        
        # 延迟导入以避免循环依赖
        from ..core.global_cache import cache
        
        # 1. 优先从缓存中获取
        cached_python = cache.get(PYTHON_CACHE_KEY)
        if cached_python:
            logger.info(f"从缓存中获取Python路径: {cached_python}")
            if os.path.exists(cached_python):
                return cached_python
            else:
                logger.warning(f"缓存中的Python路径不存在: {cached_python}，重新查找")
                cache.delete(PYTHON_CACHE_KEY)
        
        # 2. 缓存中没有或路径无效，重新查找
        python_path = PythonUtils._find_python_executable()
        if python_path:
            # 验证版本并存入缓存
            if PythonUtils._validate_python_version(python_path):
                cache.set(PYTHON_CACHE_KEY, python_path)
                logger.info(f"找到并缓存Python路径: {python_path}")
                return python_path
        
        logger.error("未找到可用的Python可执行文件")
        return None
    
    @staticmethod
    def _find_python_executable() -> Optional[str]:
        """
        查找系统中可执行的Python命令
        参考host_init.py中的pythonInit方法实现
        
        Returns:
            Optional[str]: Python可执行文件路径，如果找不到则返回None
        """
        logger = get_logger()
        
        # 常见的Python安装路径
        common_paths = [
            # 系统PATH中的python
            "python", "python3", "python.exe", "python3.exe",
            # 常见的安装路径
            "C:\\Python3*\\python.exe",
            "C:\\Python*\\python.exe", 
            "D:\\Python3*\\python.exe",
            "D:\\Python*\\python.exe",
            "E:\\Python3*\\python.exe",
            "E:\\Python*\\python.exe",
            # 用户目录下的Python
            os.path.expanduser("~\\AppData\\Local\\Programs\\Python\\Python3*\\python.exe"),
            os.path.expanduser("~\\AppData\\Local\\Programs\\Python\\Python*\\python.exe")
        ]
        
        # 检查是否打包为exe（如果是exe，不依赖当前解释器）
        is_frozen = getattr(sys, 'frozen', False)
        
        # 如果不是打包的exe，可以尝试当前Python解释器
        if not is_frozen and hasattr(sys, 'executable') and sys.executable:
            if os.path.exists(sys.executable):
                logger.info(f"使用当前Python解释器: {sys.executable}")
                return sys.executable
        
        # 查找PATH环境变量中的Python（优先）
        for cmd in ["python", "python3", "py"]:
            try:
                result = run_with_logging([cmd, "--version"], 
                                        command_name="check_python_version",
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    # 获取完整路径
                    path_result = run_with_logging([cmd, "-c", "import sys; print(sys.executable)"],
                                                 command_name="get_python_executable_path",
                                                 capture_output=True, text=True, timeout=5)
                    if path_result.returncode == 0:
                        python_path = path_result.stdout.strip()
                        if os.path.exists(python_path):
                            logger.info(f"在PATH中找到Python: {python_path}")
                            return python_path
            except Exception:
                continue
        
        # 查找常见安装路径
        for pattern in common_paths:
            try:
                matches = glob.glob(pattern)
                for match in matches:
                    if os.path.exists(match):
                        logger.info(f"在常见路径中找到Python: {match}")
                        return match
            except Exception:
                continue
        
        logger.warning("未找到可用的Python可执行文件")
        return None
    
    @staticmethod
    def _validate_python_version(python_path: str) -> bool:
        """
        验证Python版本是否 >= 3.8
        
        Args:
            python_path: Python可执行文件路径
            
        Returns:
            bool: 版本是否符合要求
        """
        logger = get_logger()
        
        try:
            # 获取Python版本信息
            result = run_with_logging([python_path, "-c", 
                                      "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
                                     command_name="validate_python_version",
                                     capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                version_str = result.stdout.strip()
                logger.info(f"Python版本: {version_str}")
                
                # 解析版本号
                try:
                    major, minor = map(int, version_str.split('.'))
                    if major > 3 or (major == 3 and minor >= 8):
                        logger.info(f"Python版本符合要求: {version_str}")
                        return True
                    else:
                        logger.warning(f"Python版本过低: {version_str}，需要>=3.8")
                        return False
                except ValueError:
                    logger.warning(f"无法解析Python版本: {version_str}")
                    return False
            else:
                logger.warning(f"获取Python版本失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.warning(f"验证Python版本时发生错误: {str(e)}")
            return False
    
    @staticmethod
    def validate_python_version(python_path: str) -> bool:
        """
        公开的Python版本验证方法
        
        Args:
            python_path: Python可执行文件路径
            
        Returns:
            bool: 版本是否符合要求
        """
        return PythonUtils._validate_python_version(python_path)
    
    @staticmethod
    def clear_python_cache():
        """清除Python路径缓存"""
        # 延迟导入以避免循环依赖
        from ..core.global_cache import cache
        cache.delete(PYTHON_CACHE_KEY)
        get_logger().info("已清除Python路径缓存")
    