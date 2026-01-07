#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息工具类 - HTTP版本
通过HTTP API调用消息框服务，实现双进程机制
"""

import os
import sys
import requests
import logging
from pathlib import Path
from typing import Optional, Dict, Any


class MessageTool:
    """消息工具类，通过HTTP API调用消息框服务"""
    
    def __init__(self, api_url: str = "http://127.0.0.1:8001"):
        """初始化消息工具类"""
        self.logger = logging.getLogger(__name__)
        self.api_url = api_url
        
        # 获取当前程序所在目录
        self.current_dir = Path(sys.executable).parent if hasattr(sys, 'frozen') else Path.cwd()
        
        # 检测运行环境
        self.is_development = self._detect_development_environment()
        
        self.logger.info(f"消息工具初始化完成 - 环境: {'开发' if self.is_development else '生产'}, API地址: {self.api_url}")
        
        # 检查API服务是否可用
        if self._check_api_available():
            self.logger.info("消息框API服务连接成功")
        else:
            self.logger.warning("消息框API服务不可用，请确保A进程正在运行")
    
    def _detect_development_environment(self) -> bool:
        """
        检测是否为开发环境
        
        Returns:
            bool: True表示开发环境，False表示生产环境
        """
        # 方法1: 检查是否以Python脚本运行（非打包exe）
        if not hasattr(sys, 'frozen'):
            return True
        
        # 方法2: 检查是否在开发目录结构中
        if 'src' in str(self.current_dir) or 'local_agent' in str(self.current_dir):
            return True
        
        # 方法3: 检查是否存在开发环境标志文件
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
        
        # 方法4: 检查环境变量
        dev_env = os.environ.get('LOCAL_AGENT_DEV_MODE', '').lower()
        if dev_env in ('true', '1', 'yes', 'development'):
            return True
        
        return False
    
    def _check_api_available(self) -> bool:
        """检查API服务是否可用
        
        Returns:
            bool: True表示API服务可用
        """
        try:
            response = requests.get(f"{self.api_url}/", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def show_message_box(self, 
                        message: str, 
                        title: str = "系统提示",
                        confirm_show: bool = True,
                        cancel_show: bool = False,
                        confirm_text: str = "确定",
                        cancel_text: str = "取消",
                        timeout: int = 0) -> Optional[str]:
        """显示消息框 - 通过HTTP API调用
        
        Args:
            message: 消息内容
            title: 标题
            confirm_show: 是否显示确认按钮
            cancel_show: 是否显示取消按钮
            confirm_text: 确认按钮文本
            cancel_text: 取消按钮文本
            timeout: 超时时间（秒），0表示不超时（等待用户反馈）
            
        Returns:
            Optional[str]: 用户选择的按钮文本，超时或错误时返回None
        """
        try:
            # 检查API服务是否可用
            if not self._check_api_available():
                self.logger.error("消息框API服务不可用，无法显示消息框")
                self.logger.error("请确保A进程（用户进程）正在运行，提供8001端口的FastAPI服务")
                return None
            
            # 构建API请求数据 - 强制timeout=0确保无超时
            data = {
                "message": message,
                "title": title,
                "confirm_show": confirm_show,
                "cancel_show": cancel_show,
                "confirm_text": confirm_text,
                "cancel_text": cancel_text,
                "timeout": 0  # 强制设置为0，确保无超时，完全等待用户反馈
            }
            
            self.logger.debug(f"调用消息框API: {self.api_url}/show_message")
            self.logger.debug(f"消息内容: {message}, 标题: {title}")
            
            # 调用API - 使用非常长的超时时间模拟同步效果
            # timeout=0表示无限等待，但requests不支持0，所以使用最大整数
            response = requests.post(
                f"{self.api_url}/show_message",
                json=data,
                timeout=None  # 无超时，完全等待用户反馈
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    # 成功执行，返回用户选择
                    user_choice = result.get("user_choice")
                    self.logger.info(f"用户选择了: {user_choice}")
                    return user_choice
                else:
                    # API执行出错
                    error_msg = result.get("error", "未知错误")
                    self.logger.error(f"消息框API执行失败: {error_msg}")
                    return None
            else:
                # HTTP请求失败
                self.logger.error(f"消息框API请求失败: {response.status_code}")
                return None
                
        except requests.Timeout:
            self.logger.warning("消息框API请求超时")
            return None
        except requests.RequestException as e:
            self.logger.error(f"消息框API请求异常: {e}")
            return None
        except Exception as e:
            self.logger.error(f"消息框调用异常: {e}")
            return None
    

    
    def show_confirm_dialog(self, 
                           message: str, 
                           title: str = "确认操作") -> bool:
        """
        显示确认对话框（确认/取消）
        
        Args:
            message: 消息内容
            title: 标题
            
        Returns:
            bool: True表示用户确认，False表示用户取消或出错
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=True,
            confirm_text="确认",
            cancel_text="取消"
        )
        
        return result == "确认"
    
    def show_info_dialog(self, 
                        message: str, 
                        title: str = "信息提示") -> bool:
        """
        显示信息对话框（只有确定按钮）
        
        Args:
            message: 消息内容
            title: 标题
            
        Returns:
            bool: 总是返回True（表示用户已查看）
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="确定"
        )
        
        return result is not None
    
    def show_warning_dialog(self, 
                           message: str, 
                           title: str = "警告") -> bool:
        """
        显示警告对话框
        
        Args:
            message: 消息内容
            title: 标题
            
        Returns:
            bool: True表示用户确认，False表示出错
        """
        result = self.show_message_box(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="我知道了"
        )
        
        return result is not None
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        获取环境信息
        
        Returns:
            Dict[str, Any]: 包含环境信息的字典
        """
        return {
            "is_development": self.is_development,
            "current_directory": str(self.current_dir),
            "api_url": self.api_url,
            "api_available": self._check_api_available(),
            "python_executable": sys.executable,
            "frozen": hasattr(sys, 'frozen')
        }


# 全局消息工具实例
_message_tool = None


def get_message_tool() -> MessageTool:
    """
    获取全局消息工具实例
    
    Returns:
        MessageTool: 消息工具实例
    """
    global _message_tool
    if _message_tool is None:
        _message_tool = MessageTool()
    return _message_tool


def show_message_box(msg: str, 
                    title: str = "系统提示",
                    confirm_show: bool = True,
                    cancel_show: bool = False,
                    confirm_text: str = "确定",
                    cancel_text: str = "取消") -> Optional[str]:
    """
    显示消息框的便捷函数
    
    Args:
        msg: 消息内容
        title: 标题
        confirm_show: 是否显示确认按钮
        cancel_show: 是否显示取消按钮
        confirm_text: 确认按钮文本
        cancel_text: 取消按钮文本
        
    Returns:
        Optional[str]: 用户选择的按钮文本
    """
    tool = get_message_tool()
    return tool.show_message_box(
        message=msg,
        title=title,
        confirm_show=confirm_show,
        cancel_show=cancel_show,
        confirm_text=confirm_text,
        cancel_text=cancel_text
    )


def show_confirm_dialog(msg: str, title: str = "确认操作") -> bool:
    """
    显示确认对话框的便捷函数
    
    Args:
        message: 消息内容
        title: 标题
        
    Returns:
        bool: True表示用户确认
    """
    tool = get_message_tool()
    return tool.show_confirm_dialog(message=msg, title=title)


def show_info_dialog(msg: str, title: str = "信息提示") -> bool:
    """
    显示信息对话框的便捷函数
    
    Args:
        message: 消息内容
        title: 标题
        
    Returns:
        bool: 总是返回True
    """
    tool = get_message_tool()
    return tool.show_info_dialog(message=msg, title=title)


def show_warning_dialog(msg: str, title: str = "警告") -> bool:
    """
    显示警告对话框的便捷函数
    
        Args:
        message: 消息内容
        title: 标题
        
    Returns:
        bool: True表示用户确认
    """
    tool = get_message_tool()
    return tool.show_warning_dialog(message=msg, title=title)


if __name__ == "__main__":
    # 测试代码
    import logging
    logging.basicConfig(level=logging.INFO)
    
    tool = MessageTool()
    
    # 显示环境信息
    env_info = tool.get_environment_info()
    print("环境信息:")
    for key, value in env_info.items():
        print(f"  {key}: {value}")
    
    # 测试消息框
    print("\n测试信息对话框...")
    result = tool.show_info_dialog("这是一个测试消息框", "测试标题")
    print(f"信息对话框结果: {result}")
    
    print("\n测试确认对话框...")
    result = tool.show_confirm_dialog("您确定要执行此操作吗？", "确认操作")
    print(f"确认对话框结果: {result}")