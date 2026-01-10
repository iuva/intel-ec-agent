#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Agent Service
A well-structured Python local agent service with strong keep-alive capabilities
"""

# Provides simplified LogSystem import interface
from .logger import (
    get_logger,                    # Get logger with specified name
    get_module_logger,             # Auto-infer logger name from module
    setup_logging,                  # One-click LogSystem setup
    setup_global_logging,           # Compatibility function
    redirect_all_output,            # Redirect output
    # Global log functions
    log_debug, log_info, log_warning, log_error, log_critical,
    # Utility functions
    is_logging_initialized, get_all_loggers, set_log_level, flush_all_logs
)

# Default logger (auto-initialized)
logger = get_logger("local_agent")

__version__ = "1.0.0"
__author__ = "Local Agent Team"
__description__ = "Local agent service providing FastAPI interface and WebSocket client"