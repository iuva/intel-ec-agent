#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows服务消息框组件
使用WTSSendMessage API实现服务到用户的跨会话消息通信
"""

import ctypes
from ctypes import wintypes
import logging
from typing import Optional, List, Tuple

# Windows API常量
WTSSessionNotification = 1
WTSTerminalNotification = 2

# Windows消息框类型
MB_OK = 0x00000000
MB_OKCANCEL = 0x00000001
MB_ABORTRETRYIGNORE = 0x00000002
MB_YESNOCANCEL = 0x00000003
MB_YESNO = 0x00000004
MB_RETRYCANCEL = 0x00000005
MB_CANCELTRYCONTINUE = 0x00000006

MB_ICONHAND = 0x00000010
MB_ICONQUESTION = 0x00000020
MB_ICONEXCLAMATION = 0x00000030
MB_ICONASTERISK = 0x00000040
MB_USERICON = 0x00000080
MB_ICONWARNING = MB_ICONEXCLAMATION
MB_ICONERROR = MB_ICONHAND
MB_ICONINFORMATION = MB_ICONASTERISK
MB_ICONSTOP = MB_ICONHAND

MB_DEFBUTTON1 = 0x00000000
MB_DEFBUTTON2 = 0x00000100
MB_DEFBUTTON3 = 0x00000200
MB_DEFBUTTON4 = 0x00000300

MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
MB_SERVICE_NOTIFICATION = 0x00200000

# 消息框返回值
IDOK = 1
IDCANCEL = 2
IDABORT = 3
IDRETRY = 4
IDIGNORE = 5
IDYES = 6
IDNO = 7
IDTRYAGAIN = 10
IDCONTINUE = 11

class ServiceMessageBox:
    """Windows服务消息框类"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 加载Windows API
        self._load_windows_apis()
    
    def _load_windows_apis(self):
        """加载所需的Windows API"""
        try:
            # WTSSendMessage API
            self._wts_send_message = ctypes.windll.wtsapi32.WTSSendMessageW
            self._wts_send_message.argtypes = [
                wintypes.HANDLE,  # hServer
                wintypes.DWORD,   # SessionId
                wintypes.LPCWSTR, # pTitle
                wintypes.DWORD,   # TitleLength
                wintypes.LPCWSTR, # pMessage
                wintypes.DWORD,   # MessageLength
                wintypes.DWORD,   # Style
                wintypes.DWORD,   # Timeout
                wintypes.PDWORD,  # pResponse
                wintypes.BOOL     # bWait
            ]
            self._wts_send_message.restype = wintypes.BOOL
            
            # WTSEnumerateSessions API
            self._wts_enumerate_sessions = ctypes.windll.wtsapi32.WTSEnumerateSessionsW
            self._wts_enumerate_sessions.argtypes = [
                wintypes.HANDLE,  # hServer
                wintypes.DWORD,   # Reserved
                wintypes.DWORD,   # Version
                ctypes.POINTER(ctypes.c_void_p),  # ppSessionInfo
                ctypes.POINTER(wintypes.DWORD)    # pCount
            ]
            self._wts_enumerate_sessions.restype = wintypes.BOOL
            
            # WTSFreeMemory API
            self._wts_free_memory = ctypes.windll.wtsapi32.WTSFreeMemory
            self._wts_free_memory.argtypes = [ctypes.c_void_p]
            self._wts_free_memory.restype = None
            
            # WTSQueryUserToken API
            self._wts_query_user_token = ctypes.windll.wtsapi32.WTSQueryUserToken
            self._wts_query_user_token.argtypes = [
                wintypes.DWORD,   # SessionId
                ctypes.POINTER(wintypes.HANDLE)  # phToken
            ]
            self._wts_query_user_token.restype = wintypes.BOOL
            
            self.logger.info("Windows API加载成功")
            
        except Exception as e:
            self.logger.error(f"Windows API加载失败: {e}")
            raise
    
    def get_active_user_session(self) -> Optional[int]:
        """获取活动用户会话ID"""
        try:
            # 枚举所有会话
            pp_session_info = ctypes.c_void_p()
            p_count = wintypes.DWORD()
            
            if self._wts_enumerate_sessions(
                wintypes.HANDLE(0),  # WTS_CURRENT_SERVER_HANDLE
                0,  # Reserved
                1,  # Version
                ctypes.byref(pp_session_info),
                ctypes.byref(p_count)
            ):
                # 遍历会话，找到活动用户会话
                for i in range(p_count.value):
                    # 这里需要根据WTS_SESSION_INFO结构体来解析
                    # 简化处理：返回第一个非0会话（通常是用户会话）
                    session_id = i + 1  # 简化处理
                    if session_id != 0:
                        self._wts_free_memory(pp_session_info)
                        return session_id
                
                self._wts_free_memory(pp_session_info)
            
            # 如果找不到活动会话，返回None
            return None
            
        except Exception as e:
            self.logger.error(f"获取活动用户会话失败: {e}")
            return None
    
    def show_service_message_box(self, 
                                title: str, 
                                message: str, 
                                message_type: str = "info",
                                buttons: List[str] = None,
                                timeout: int = 0) -> Optional[str]:
        """
        显示服务消息框
        
        Args:
            title: 消息框标题
            message: 消息内容
            message_type: 消息类型 (info, warning, error, question)
            buttons: 按钮列表
            timeout: 超时时间（秒），0表示无限等待
            
        Returns:
            Optional[str]: 用户选择的按钮文本，超时或失败返回None
        """
        try:
            # 获取活动用户会话
            session_id = self.get_active_user_session()
            if session_id is None:
                self.logger.error("无法找到活动用户会话")
                return None
            
            self.logger.info(f"向会话 {session_id} 发送消息框")
            
            # 设置消息框样式
            style = self._get_message_box_style(message_type, buttons)
            
            # 准备参数
            title_wide = ctypes.create_unicode_buffer(title)
            message_wide = ctypes.create_unicode_buffer(message)
            response = wintypes.DWORD(0)
            
            # 发送消息
            result = self._wts_send_message(
                wintypes.HANDLE(0),  # WTS_CURRENT_SERVER_HANDLE
                session_id,
                title_wide,
                len(title) * 2,  # Unicode字符长度
                message_wide,
                len(message) * 2,  # Unicode字符长度
                style,
                timeout * 1000,  # 转换为毫秒
                ctypes.byref(response),
                wintypes.BOOL(True)  # 等待用户响应
            )
            
            if result:
                # 转换响应为按钮文本
                button_text = self._get_button_text_from_response(response.value, buttons)
                self.logger.info(f"用户选择了: {button_text}")
                return button_text
            else:
                self.logger.error("WTSSendMessage调用失败")
                return None
                
        except Exception as e:
            self.logger.error(f"显示服务消息框失败: {e}")
            return None
    
    def _get_message_box_style(self, message_type: str, buttons: List[str]) -> int:
        """获取消息框样式"""
        style = MB_SETFOREGROUND | MB_TOPMOST
        
        # 设置消息类型图标
        if message_type == "warning":
            style |= MB_ICONWARNING
        elif message_type == "error":
            style |= MB_ICONERROR
        elif message_type == "question":
            style |= MB_ICONQUESTION
        else:  # info
            style |= MB_ICONINFORMATION
        
        # 设置按钮样式
        if buttons is None or len(buttons) == 0:
            style |= MB_OK
        elif len(buttons) == 1:
            style |= MB_OK
        elif len(buttons) == 2:
            if "是" in buttons and "否" in buttons:
                style |= MB_YESNO
            else:
                style |= MB_OKCANCEL
        elif len(buttons) == 3:
            style |= MB_YESNOCANCEL
        else:
            style |= MB_OKCANCEL
        
        return style
    
    def _get_button_text_from_response(self, response: int, buttons: List[str]) -> str:
        """根据Windows响应值获取按钮文本"""
        # 如果有自定义按钮，使用自定义映射
        if buttons and len(buttons) > 0:
            # 根据按钮数量进行智能映射
            if len(buttons) == 1:
                # 单按钮：任何响应都返回第一个按钮
                if response in [IDOK, IDYES, IDRETRY, IDCONTINUE]:
                    return buttons[0]
            elif len(buttons) == 2:
                # 双按钮：智能映射为第一个/第二个按钮
                # 对于["重试", "放弃"]，映射IDRETRY->重试，IDCANCEL->放弃
                if response in [IDOK, IDYES, IDRETRY, IDCONTINUE, IDTRYAGAIN]:
                    return buttons[0]  # 第一个按钮
                elif response in [IDCANCEL, IDNO, IDABORT]:
                    return buttons[1]  # 第二个按钮
            elif len(buttons) >= 3:
                # 多按钮：根据标准映射
                if response == IDOK:
                    return buttons[0] if len(buttons) >= 1 else "确定"
                elif response == IDCANCEL:
                    return buttons[1] if len(buttons) >= 2 else "取消"
                elif response == IDYES:
                    return buttons[0] if len(buttons) >= 1 else "是"
                elif response == IDNO:
                    return buttons[1] if len(buttons) >= 2 else "否"
        
        # 默认按钮映射（当没有自定义按钮或映射失败时使用）
        default_mapping = {
            IDOK: "确定",
            IDCANCEL: "取消", 
            IDYES: "是",
            IDNO: "否",
            IDRETRY: "重试",
            IDABORT: "中止",
            IDIGNORE: "忽略",
            IDTRYAGAIN: "重试",
            IDCONTINUE: "继续"
        }
        
        return default_mapping.get(response, "未知")
    
    def show_simple_message_box(self, title: str, message: str) -> Optional[str]:
        """显示简单的确定/取消消息框"""
        return self.show_service_message_box(
            title=title,
            message=message,
            message_type="info",
            buttons=["确定", "取消"],
            timeout=0
        )


def show_service_message_box(title: str, message: str, 
                            message_type: str = "info",
                            buttons: List[str] = None,
                            timeout: int = 0) -> Optional[str]:
    """
    快速显示服务消息框的便捷函数
    
    Args:
        title: 消息框标题
        message: 消息内容
        message_type: 消息类型 (info, warning, error, question)
        buttons: 按钮列表
        timeout: 超时时间（秒）
        
    Returns:
        Optional[str]: 用户选择的按钮文本
    """
    try:
        message_box = ServiceMessageBox()
        return message_box.show_service_message_box(
            title=title,
            message=message,
            message_type=message_type,
            buttons=buttons,
            timeout=timeout
        )
    except Exception as e:
        logging.error(f"显示服务消息框失败: {e}")
        return None