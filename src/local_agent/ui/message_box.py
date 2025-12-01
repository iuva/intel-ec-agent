"""
消息确认窗口组件
提供带有"重试"和"放弃"按钮的确认对话框
支持自定义按钮显示状态和文本描述
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable
import threading


class MessageBox:
    """消息确认窗口类"""
    
    def __init__(self, title: str = "确认", 
                 show_retry: bool = True, show_cancel: bool = True,
                 retry_text: str = "重试", cancel_text: str = "放弃"):
        """
        初始化消息确认窗口
        
        Args:
            title: 窗口标题
            show_retry: 是否显示重试按钮
            show_cancel: 是否显示放弃按钮
            retry_text: 重试按钮显示文本
            cancel_text: 放弃按钮显示文本
        """
        self.title = title
        self.show_retry = show_retry
        self.show_cancel = show_cancel
        self.retry_text = retry_text
        self.cancel_text = cancel_text
        self.result: Optional[str] = None
        self._callback: Optional[Callable] = None
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_started = False
    
    def show(self, msg: str, callback: Optional[Callable] = None) -> Optional[str]:
        """
        显示消息确认窗口
        
        Args:
            msg: 要显示的消息内容
            callback: 回调函数，当用户点击按钮时调用，参数为按钮类型('retry'或'cancel')
            
        Returns:
            Optional[str]: 如果同步调用，返回按钮类型('retry'或'cancel')；如果异步调用，返回None
        """
        self.msg = msg
        self._callback = callback
        
        # 检查是否在主线程中
        if threading.current_thread() == threading.main_thread():
            # 在主线程中，同步显示
            return self._show_sync()
        else:
            # 在子线程中，异步显示
            self._show_async()
            return None
    
    def _show_sync(self) -> str:
        """同步显示消息窗口"""
        self._create_window()
        self._root.mainloop()
        return self.result
    
    def _show_async(self):
        """异步显示消息窗口"""
        self._thread = threading.Thread(target=self._show_sync)
        self._thread.daemon = True
        self._thread.start()
        self._thread_started = True
    
    def _create_window(self):
        """创建窗口和控件"""
        # 创建主窗口
        self._root = tk.Tk()
        self._root.title(self.title)
        self._root.geometry("400x200")
        self._root.resizable(False, False)
        
        # 隐藏标题栏（包括最小化、最大化、关闭按钮）
        self._root.overrideredirect(True)
        
        # 设置窗口居中
        self._center_window()
        
        # 设置窗口图标（如果有的话）
        try:
            self._root.iconbitmap("")
        except:
            pass
        
        # 创建主框架
        main_frame = ttk.Frame(self._root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 消息框架（占据大部分空间，用于居中显示消息）
        message_frame = ttk.Frame(main_frame)
        message_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 消息标签 - 在消息框架中居中显示
        msg_label = ttk.Label(
            message_frame, 
            text=self.msg, 
            wraplength=360,
            justify=tk.CENTER,
            font=("微软雅黑", 10)
        )
        msg_label.pack(expand=True)  # 使用expand=True让消息在框架中居中
        
        # 按钮框架（固定在底部）
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=20)
        
        # 重试按钮（根据show_retry参数决定是否显示）
        retry_button = None
        if self.show_retry:
            retry_button = ttk.Button(
                button_frame,
                text=self.retry_text,
                command=lambda: self._on_button_click("retry"),
                width=10
            )
            retry_button.pack(side=tk.LEFT, padx=(0, 10), expand=True)
        
        # 放弃按钮（根据show_cancel参数决定是否显示）
        cancel_button = None
        if self.show_cancel:
            cancel_button = ttk.Button(
                button_frame,
                text=self.cancel_text,
                command=lambda: self._on_button_click("cancel"),
                width=10
            )
            cancel_button.pack(side=tk.RIGHT, expand=True)
        
        # 绑定回车和ESC键（根据按钮显示状态动态绑定）
        if self.show_retry:
            self._root.bind('<Return>', lambda e: self._on_button_click("retry"))
        if self.show_cancel:
            self._root.bind('<Escape>', lambda e: self._on_button_click("cancel"))
        
        # 设置默认焦点（优先重试按钮，如果没有重试按钮则使用放弃按钮）
        if self.show_retry and retry_button:
            retry_button.focus_set()
        elif self.show_cancel and cancel_button:
            cancel_button.focus_set()
        
        # 如果两个按钮都不显示，则自动关闭窗口
        if not self.show_retry and not self.show_cancel:
            self._root.after(100, lambda: self._on_button_click("cancel"))
    
    def _center_window(self):
        """窗口居中显示"""
        self._root.update_idletasks()
        width = self._root.winfo_width()
        height = self._root.winfo_height()
        x = (self._root.winfo_screenwidth() // 2) - (width // 2)
        y = (self._root.winfo_screenheight() // 2) - (height // 2)
        self._root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _on_button_click(self, button_type: str):
        """
        按钮点击处理
        
        Args:
            button_type: 按钮类型，'retry'或'cancel'
        """
        self.result = button_type
        
        # 调用回调函数
        if self._callback:
            self._callback(button_type)
        
        # 关闭窗口
        if self._root:
            self._root.quit()
            self._root.destroy()
    
    def wait_for_result(self) -> str:
        """
        等待异步调用的结果
        
        Returns:
            str: 按钮类型('retry'或'cancel')
        """
        if self._thread and self._thread_started:
            self._thread.join()
        return self.result


def show_message_box(msg: str, title: str = "确认",
                      show_retry: bool = True, show_cancel: bool = True,
                      retry_text: str = "重试", cancel_text: str = "放弃") -> str:
    """
    快速显示消息确认窗口的便捷函数
    
    Args:
        msg: 消息内容
        title: 窗口标题
        show_retry: 是否显示重试按钮
        show_cancel: 是否显示放弃按钮
        retry_text: 重试按钮显示文本
        cancel_text: 放弃按钮显示文本
        
    Returns:
        str: 用户选择的按钮类型('retry'或'cancel')
    """
    message_box = MessageBox(title, show_retry, show_cancel, retry_text, cancel_text)
    return message_box.show(msg)


def show_message_box_async(msg: str, callback: Callable, title: str = "确认",
                          show_retry: bool = True, show_cancel: bool = True,
                          retry_text: str = "重试", cancel_text: str = "放弃"):
    """
    异步显示消息确认窗口的便捷函数
    
    Args:
        msg: 消息内容
        callback: 回调函数
        title: 窗口标题
        show_retry: 是否显示重试按钮
        show_cancel: 是否显示放弃按钮
        retry_text: 重试按钮显示文本
        cancel_text: 放弃按钮显示文本
    """
    message_box = MessageBox(title, show_retry, show_cancel, retry_text, cancel_text)
    message_box.show(msg, callback)