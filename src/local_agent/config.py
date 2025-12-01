#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
集中管理所有配置项，支持环境变量和配置文件
"""

from operator import truediv
import os
from typing import Dict, Any, Optional
from pathlib import Path

from .logger import get_logger
from .utils.version_utils import get_app_version


class Config:
    """配置管理类"""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_defaults()
        self._load_environment()
        self._validate_config()
    
    def _load_defaults(self):
        """加载默认配置"""
        # 基础配置
        self._config.update({
            # 应用配置
            'app_name': 'Local Agent Service',
            'version': get_app_version(),  # 动态获取版本信息
            'debug': True,
            
            # FastAPI配置
            'api_host': '0.0.0.0',
            'api_port': 8001,
            'api_reload': False,
            'api_workers': 1,
            
            # WebSocket配置
            'websocket_enabled': True,
            'websocket_url': 'ws://192.168.101.42:8000/api/v1/ws/host/host',
            'websocket_reconnect_interval': 10,  # 重连间隔(秒)
            'websocket_timeout': 30,  # 超时时间(秒)
            
            # 日志配置
            'log_level': 'DEBUG',
            'log_file': 'logs/local_agent.log',
            'log_max_size': 10 * 1024 * 1024,  # 10MB
            'log_backup_count': 5,
            
            # 保活配置
            'keepalive_interval': 60,  # 保活检查间隔(秒)
            'max_restart_attempts': 3,  # 最大重启尝试次数
            'restart_delay': 5,  # 重启延迟(秒)
            
            # 性能配置
            'max_memory_mb': 512,  # 最大内存使用(MB)
            'cpu_threshold': 80,  # CPU使用率阈值(%)
            'monitor_interval': 30,  # 监控间隔(秒)
            
            # HTTP客户端配置
            'http_base_url': 'http://192.168.101.42:8000/api/v1',  # HTTP请求基础URL
            'http_timeout': 60,  # HTTP请求超时时间(秒)
        })
    
    def _load_environment(self):
        """加载环境变量配置"""
        logger = get_logger(__name__)
        
        env_mappings = {
            'LOCAL_AGENT_DEBUG': ('debug', lambda x: x.lower() == 'true'),
            'LOCAL_AGENT_API_PORT': ('api_port', int),
            'LOCAL_AGENT_API_HOST': ('api_host', str),
            'LOCAL_AGENT_LOG_LEVEL': ('log_level', str),
            'LOCAL_AGENT_WEBSOCKET_URL': ('websocket_url', str),
            'LOCAL_AGENT_KEEPALIVE_INTERVAL': ('keepalive_interval', int),
            'LOCAL_AGENT_HTTP_BASE_URL': ('http_base_url', str),
            'LOCAL_AGENT_HTTP_TIMEOUT': ('http_timeout', int),
        }
        
        for env_var, (config_key, converter) in env_mappings.items():
            if env_var in os.environ:
                try:
                    self._config[config_key] = converter(os.environ[env_var])
                except (ValueError, TypeError) as e:
                    logger.warning(f"环境变量 {env_var} 转换失败: {e}")
    
    def _validate_config(self):
        """验证配置有效性"""
        # 确保端口在有效范围内
        if not (1 <= self._config['api_port'] <= 65535):
            raise ValueError(f"端口号必须在1-65535之间: {self._config['api_port']}")
        
        # 确保日志目录存在
        log_dir = Path(self._config['log_file']).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        self._config[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self._config.copy()
    
    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self._config[key]
    
    def __setitem__(self, key: str, value: Any):
        """支持字典式设置"""
        self._config[key] = value
    
    def __contains__(self, key: str) -> bool:
        """支持in操作符"""
        return key in self._config


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取全局配置实例"""
    return config


def reload_config():
    """重新加载配置"""
    global config
    config = Config()