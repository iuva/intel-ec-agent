#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API模块
提供FastAPI接口服务
"""

from .server import APIServer
from .routes import router

__all__ = ['APIServer', 'router']