#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Agent Service
一个结构清晰、保活能力强的Python本地代理服务
"""

# 提供简化的日志系统导入接口
from .logger import (
    get_logger,                    # 获取指定名称的日志器
    get_module_logger,             # 自动推断模块名的日志器
    setup_logging,                  # 一键设置日志系统
    setup_global_logging,           # 兼容性函数
    redirect_all_output,            # 重定向输出
    # 全局日志函数
    log_debug, log_info, log_warning, log_error, log_critical,
    # 工具函数
    is_logging_initialized, get_all_loggers, set_log_level, flush_all_logs
)

# 默认日志器（自动初始化）
logger = get_logger("local_agent")

__version__ = "1.0.0"
__author__ = "Local Agent Team"
__description__ = "本地代理服务，提供FastAPI接口和WebSocket客户端"