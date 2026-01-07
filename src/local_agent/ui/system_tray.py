#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统托盘工具类
用于在系统托盘中显示应用图标和菜单
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
    """系统托盘类"""
    
    def __init__(self, name: str = "agent", icon_path: Optional[str] = None):
        """初始化系统托盘"""
        self.name = name
        self.logger = logging.getLogger(__name__)
        self.icon = None
        self.tray_icon = None
        self.is_running = False
        
        # 检查依赖
        if not HAS_PYSTRAY:
            self.logger.warning("pystray未安装，系统托盘功能不可用")
            return
        
        # 创建或加载图标
        self.icon = self._create_icon(icon_path)
        
        # 创建菜单
        self.menu = self._create_menu()
        
        self.logger.info("系统托盘初始化完成")
    
    def _create_icon(self, icon_path: Optional[str] = None) -> Optional[Image.Image]:
        """创建或加载图标"""
        try:
            if icon_path and os.path.exists(icon_path):
                # 加载现有图标文件
                return Image.open(icon_path)
            else:
                # 创建简单的默认图标
                return self._create_default_icon()
        except Exception as e:
            self.logger.warning(f"创建图标失败: {e}")
            return self._create_default_icon()
    
    def _create_default_icon(self) -> Image.Image:
        """创建默认图标"""
        # 创建一个简单的圆形图标
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 绘制蓝色圆形
        draw.ellipse((2, 2, 62, 62), fill=(0, 120, 215, 255))
        
        # 绘制白色字母"L"
        draw.text((20, 15), "L", fill=(255, 255, 255, 255), font_size=30)
        
        return image
    
    def _create_menu(self) -> pystray.Menu:
        """创建托盘菜单"""
        # 创建菜单项
        menu_items = [
            # pystray.MenuItem("显示状态", self._show_status),
            # pystray.MenuItem("重启服务", self._restart_service),
            # pystray.MenuItem("停止服务", self._stop_service),
            # pystray.MenuItem("-", None),  # 分隔符
            # pystray.MenuItem("退出", self._exit_app)
        ]
        
        return pystray.Menu(*menu_items)
    
    def _show_status(self, icon, item):
        """显示状态信息"""
        self.logger.info("显示应用状态")
        # 这里可以显示状态对话框或通知
        if HAS_WIN32:
            try:
                win32api.MessageBox(
                    0, 
                    "本地代理服务运行中\n\n服务状态: 正常\nAPI端口: 8001\n消息框服务: 运行中", 
                    "服务状态", 
                    win32con.MB_OK | win32con.MB_ICONINFORMATION
                )
            except Exception as e:
                self.logger.warning(f"显示状态对话框失败: {e}")
    
    def _restart_service(self, icon, item):
        """重启服务"""
        self.logger.info("重启服务")
        # 这里可以实现重启逻辑
        if HAS_WIN32:
            try:
                win32api.MessageBox(
                    0, 
                    "服务重启功能开发中...", 
                    "重启服务", 
                    win32con.MB_OK | win32con.MB_ICONINFORMATION
                )
            except Exception as e:
                self.logger.warning(f"显示重启对话框失败: {e}")
    
    def _stop_service(self, icon, item):
        """停止服务"""
        self.logger.info("停止服务")
        # 这里可以实现停止逻辑
        if HAS_WIN32:
            try:
                result = win32api.MessageBox(
                    0, 
                    "确定要停止本地代理服务吗？\n\n停止后需要手动重新启动。", 
                    "停止服务", 
                    win32con.MB_YESNO | win32con.MB_ICONQUESTION
                )
                if result == win32con.IDYES:
                    self.logger.info("用户确认停止服务")
                    # 这里可以添加停止服务的逻辑
            except Exception as e:
                self.logger.warning(f"显示停止对话框失败: {e}")
    
    def _exit_app(self, icon, item):
        """退出应用"""
        self.logger.info("退出应用")
        if HAS_WIN32:
            try:
                result = win32api.MessageBox(
                    0, 
                    "确定要退出本地代理服务吗？\n\n退出后消息框功能将不可用。", 
                    "退出确认", 
                    win32con.MB_YESNO | win32con.MB_ICONQUESTION
                )
                if result == win32con.IDYES:
                    self.logger.info("用户确认退出应用")
                    self.stop()
                    # 强制退出进程
                    os._exit(0)
            except Exception as e:
                self.logger.warning(f"显示退出对话框失败: {e}")
    
    def start(self):
        """启动系统托盘"""
        if not HAS_PYSTRAY or self.icon is None:
            self.logger.warning("系统托盘功能不可用，跳过启动")
            return
        
        if self.is_running:
            self.logger.warning("系统托盘已在运行中")
            return
        
        try:
            # 创建系统托盘图标
            self.tray_icon = pystray.Icon(
                self.name,
                self.icon,
                self.name,
                self.menu
            )
            
            # 在单独的线程中运行系统托盘
            def run_tray():
                try:
                    self.tray_icon.run()
                except Exception as e:
                    self.logger.error(f"系统托盘运行异常: {e}")
            
            tray_thread = threading.Thread(target=run_tray, daemon=True)
            tray_thread.start()
            
            self.is_running = True
            self.logger.info("系统托盘启动成功")
            
        except Exception as e:
            self.logger.error(f"启动系统托盘失败: {e}")
    
    def stop(self):
        """停止系统托盘"""
        if self.tray_icon and self.is_running:
            try:
                self.tray_icon.stop()
                self.is_running = False
                self.logger.info("系统托盘已停止")
            except Exception as e:
                self.logger.error(f"停止系统托盘失败: {e}")
    
    def notify(self, title: str, message: str, duration: int = 5):
        """显示系统通知"""
        if self.tray_icon and self.is_running:
            try:
                self.tray_icon.notify(message, title)
                self.logger.info(f"显示通知: {title} - {message}")
            except Exception as e:
                self.logger.warning(f"显示通知失败: {e}")


def create_system_tray(name: str = "agent", icon_path: Optional[str] = None) -> SystemTray:
    """创建系统托盘实例"""
    return SystemTray(name=name, icon_path=icon_path)


def start_system_tray(name: str = "agent", icon_path: Optional[str] = None) -> SystemTray:
    """启动系统托盘"""
    tray = create_system_tray(name, icon_path)
    tray.start()
    return tray


if __name__ == "__main__":
    # 测试代码
    import logging
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    # 创建并启动系统托盘
    tray = start_system_tray()
    
    # 显示测试通知
    tray.notify("测试通知", "系统托盘功能测试成功")
    
    # 保持运行一段时间
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    
    # 停止系统托盘
    tray.stop()