#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地消息窗口组件
提供基于tkinter的消息框功能，替代原来的exe调用
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
    """消息类型枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CONFIRM = "confirm"


class ButtonType(Enum):
    """按钮类型枚举"""
    OK = "确定"
    CANCEL = "取消"
    YES = "是"
    NO = "否"
    RETRY = "重试"
    IGNORE = "忽略"


@dataclass
class MessageResult:
    """消息框结果"""
    success: bool
    user_choice: Optional[str] = None
    error: Optional[str] = None


class MessageWindow:
    """本地消息窗口类"""
    
    def __init__(self):
        """初始化消息窗口"""
        self.logger = logging.getLogger(__name__)
        self._root = None
        self._thread = None
        self._result = None
        self._timeout_thread = None
        self._is_running = False
        
    def _ensure_tk_root(self):
        """确保tkinter根窗口存在"""
        if self._root is None:
            # 创建隐藏的根窗口
            self._root = tk.Tk()
            self._root.withdraw()  # 隐藏主窗口
            self._root.title("消息框服务")
            
    def _create_custom_messagebox(self, 
                                 message: str, 
                                 title: str = "系统提示",
                                 confirm_show: bool = True,
                                 cancel_show: bool = False,
                                 confirm_text: str = "确定",
                                 cancel_text: str = "取消") -> Optional[str]:
        """创建自定义消息框"""
        try:
            # 创建顶层窗口
            top = tk.Toplevel(self._root)
            top.title(title)
            top.geometry("700x300")
            top.resizable(False, False)
            
            # 设置窗口属性确保始终在最前
            top.attributes('-topmost', True)  # 始终置顶
            top.transient(self._root)         # 设置为主窗口的子窗口
            top.grab_set()                    # 独占焦点
            
            # 禁用关闭按钮但不移除标题栏
            top.protocol('WM_DELETE_WINDOW', lambda: None)  # 禁用关闭按钮
            
            # 窗口获得焦点时重新置顶
            def on_focus(event):
                top.attributes('-topmost', True)
            top.bind('<FocusIn>', on_focus)
            
            # 设置窗口图标（如果有）
            try:
                top.iconbitmap("")
            except:
                pass
            
            # 创建消息内容
            message_frame = ttk.Frame(top, padding="10")
            message_frame.pack(fill=tk.BOTH, expand=True)
            
            # 消息文本
            message_label = ttk.Label(
                message_frame, 
                text=message, 
                wraplength=350,
                justify=tk.CENTER,
                font=("微软雅黑", 10)
            )
            message_label.pack(pady=20)
            
            # 按钮框架
            button_frame = ttk.Frame(message_frame)
            button_frame.pack(side=tk.BOTTOM, pady=10)
            
            result = [None]
            
            def on_button_click(choice: str):
                result[0] = choice
                top.destroy()
            
            # 添加确认按钮
            if confirm_show:
                confirm_btn = ttk.Button(
                    button_frame, 
                    text=confirm_text, 
                    command=lambda: on_button_click(confirm_text)
                )
                confirm_btn.pack(side=tk.LEFT, padx=5)
            
            # 添加取消按钮
            if cancel_show:
                cancel_btn = ttk.Button(
                    button_frame, 
                    text=cancel_text, 
                    command=lambda: on_button_click(cancel_text)
                )
                cancel_btn.pack(side=tk.LEFT, padx=5)
            
            # 如果没有按钮，添加默认确定按钮
            if not confirm_show and not cancel_show:
                ok_btn = ttk.Button(
                    button_frame, 
                    text="确定", 
                    command=lambda: on_button_click("确定")
                )
                ok_btn.pack(side=tk.LEFT, padx=5)
            
            # 窗口居中 - 确保窗口完全渲染后再计算位置
            top.update()  # 强制更新所有挂起的任务
            top.update_idletasks()
            
            # 获取准确的窗口尺寸
            width = top.winfo_reqwidth()
            height = top.winfo_reqheight()
            
            # 计算居中位置
            x = (top.winfo_screenwidth() - width) // 2
            y = (top.winfo_screenheight() - height) // 2
            
            # 设置窗口位置和尺寸
            top.geometry(f"{width}x{height}+{x}+{y}")
            
            # 等待窗口关闭
            top.wait_window(top)
            
            return result[0]
            
        except Exception as e:
            self.logger.error(f"创建自定义消息框失败: {e}")
            return None
    
    def show_message(self, 
                    message: str, 
                    title: str = "系统提示",
                    confirm_show: bool = True,
                    cancel_show: bool = False,
                    confirm_text: str = "确定",
                    cancel_text: str = "取消",
                    timeout: int = 0) -> MessageResult:
        """显示消息框
        
        Args:
            message: 消息内容
            title: 标题
            confirm_show: 是否显示确认按钮
            cancel_show: 是否显示取消按钮
            confirm_text: 确认按钮文本
            cancel_text: 取消按钮文本
            timeout: 超时时间（秒），0表示不超时
            
        Returns:
            MessageResult: 消息框结果
        """
        try:
            self._ensure_tk_root()
            
            # 设置超时处理
            if timeout > 0:
                self._setup_timeout(timeout)
            
            # 在主线程中显示消息框
            user_choice = self._create_custom_messagebox(
                message=message,
                title=title,
                confirm_show=confirm_show,
                cancel_show=cancel_show,
                confirm_text=confirm_text,
                cancel_text=cancel_text
            )
            
            # 取消超时处理
            if timeout > 0:
                self._cancel_timeout()
            
            if user_choice is not None:
                self.logger.info(f"用户选择了: {user_choice}")
                return MessageResult(success=True, user_choice=user_choice)
            else:
                return MessageResult(success=False, error="用户未选择或消息框关闭")
                
        except Exception as e:
            self.logger.error(f"显示消息框失败: {e}")
            return MessageResult(success=False, error=str(e))
    
    def _setup_timeout(self, timeout: int):
        """设置超时处理"""
        def timeout_handler():
            time.sleep(timeout)
            if self._is_running:
                # 超时后自动关闭消息框
                try:
                    if self._root:
                        # 这里可以添加超时处理逻辑
                        self.logger.warning(f"消息框超时，自动关闭")
                except:
                    pass
        
        self._timeout_thread = threading.Thread(target=timeout_handler, daemon=True)
        self._timeout_thread.start()
    
    def _cancel_timeout(self):
        """取消超时处理"""
        self._is_running = False
    
    def show_info(self, message: str, title: str = "信息提示") -> MessageResult:
        """显示信息对话框"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="确定"
        )
    
    def show_warning(self, message: str, title: str = "警告") -> MessageResult:
        """显示警告对话框"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="确定"
        )
    
    def show_confirm(self, message: str, title: str = "确认操作") -> MessageResult:
        """显示确认对话框"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=True,
            confirm_text="确认",
            cancel_text="取消"
        )
    
    def show_error(self, message: str, title: str = "错误") -> MessageResult:
        """显示错误对话框"""
        return self.show_message(
            message=message,
            title=title,
            confirm_show=True,
            cancel_show=False,
            confirm_text="确定"
        )
    
    def cleanup(self):
        """清理资源"""
        self._is_running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except:
                pass
            self._root = None


def create_message_window() -> MessageWindow:
    """创建消息窗口实例"""
    return MessageWindow()