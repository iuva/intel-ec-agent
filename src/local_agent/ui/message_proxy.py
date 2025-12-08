"""
消息框代理系统（简化版）
使用智能消息框系统，自动选择服务消息框或普通消息框
无需复杂的进程间通信
"""

import os
import logging
from typing import Optional

from ..logger import get_logger


class MessageProxy:
    """消息框代理类（简化版）"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # 直接使用智能消息框系统，无需复杂检测
        self.logger.info("消息框代理初始化完成（简化版）")
    
    def _detect_service_mode(self) -> bool:
        """检测是否运行在服务模式下（简化版）"""
        # 检查环境变量
        service_mode_env = os.environ.get('LOCAL_AGENT_SERVICE_MODE', '').lower()
        if service_mode_env in ('true', '1', 'yes'):
            return True
        
        # 检查当前会话ID（会话0通常是服务会话）
        try:
            import ctypes
            from ctypes import wintypes
            
            # 获取当前进程的会话ID
            process_id = ctypes.windll.kernel32.GetCurrentProcessId()
            session_id = wintypes.DWORD()
            
            if ctypes.windll.kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
                return session_id.value == 0  # 会话0是系统服务会话
        except Exception:
            pass
        
        return False
    
    def show_message_box(self, msg: str, title: str = "确认",
                        buttons: list = None, default_button: int = 0) -> int:
        """
        显示消息框（简化版）
        
        Args:
            msg: 消息内容
            title: 标题
            buttons: 按钮列表，如["确定", "取消"]
            default_button: 默认按钮索引
            
        Returns:
            选择的按钮索引
        """
        if buttons is None:
            buttons = ["确定"]
            
        # 直接使用智能消息框系统
        try:
            from .message_box import show_message_box
            return show_message_box(msg, title, buttons, default_button)
        except Exception as e:
            self.logger.error(f"消息框调用失败: {e}")
            # 如果消息框调用失败，返回默认按钮
            return default_button
    

    

    
    def close(self):
        """关闭消息代理（简化版，无需特殊处理）"""
        self.logger.info("消息代理已关闭")


# 全局消息框代理实例
_message_proxy = None


def get_message_proxy() -> MessageProxy:
    """获取全局消息框代理实例"""
    global _message_proxy
    if _message_proxy is None:
        _message_proxy = MessageProxy()
    return _message_proxy


def show_message_box(msg: str, title: str = "确认",
                    buttons: list = None, default_button: int = 0) -> int:
    """
    显示消息框的便捷函数（简化版）
    
    此函数会自动使用智能消息框系统
    """
    proxy = get_message_proxy()
    return proxy.show_message_box(msg, title, buttons, default_button)


if __name__ == "__main__":
    # 测试代码
    result = show_message_box("测试消息框", "测试标题")
    print(f"用户选择: {result}")