#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration management module
Centralized management of all configuration items, supporting environment variables and configuration files
"""

from operator import truediv
import os
from typing import Dict, Any, Optional
from pathlib import Path

from .logger import get_logger
from .utils.version_utils import get_app_version


class Config:
    """Configuration management class"""
    
    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_defaults()
        self._load_environment()
        self._validate_config()
    
    def _load_defaults(self):
        """Load default configuration"""
        # Basic Configuration
        self._config.update({
            # Application Configuration
            'app_name': 'Local Agent Service',
            'version': get_app_version(),  # Dynamically get version information
            'debug': True,
            
            # FastAPI Configuration
            'api_host': '0.0.0.0',
            'api_port': 8000,
            'api_reload': False,
            'api_workers': 1,
            
            # WebSocket Configuration
            'websocket_enabled': True,
            'websocket_url': 'ws://10.239.168.44:8000/api/v1/ws/host/host',
            'websocket_reconnect_interval': 10,  # Reconnect interval (seconds)
            'websocket_timeout': 30,  # Timeout time (seconds)
            
            # Log Configuration
            'log_level': 'DEBUG',
            'log_file': 'logs/local_agent.log',
            'log_max_size': 10 * 1024 * 1024,  # 10MB
            'log_backup_count': 5,
            
            # Keep-alive Configuration
            'keepalive_interval': 60,  # Keep-alive check interval (seconds)
            'max_restart_attempts': 3,  # Maximum restart attempts
            'restart_delay': 5,  # Restart delay (seconds)
            
            # Performance Configuration
            'max_memory_mb': 512,  # Maximum memory usage (MB)
            'cpu_threshold': 80,  # CPU usage threshold (%)
            'monitor_interval': 30,  # Monitoring interval (seconds)
            
            # HTTP Client Configuration
            'http_base_url': 'http://10.239.168.44:8000/api/v1',  # HTTP request base URL
            'http_timeout': 60,  # HTTP request timeout time (seconds)
        })
    
    def _load_environment(self):
        """Load environment variable configuration"""
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
                    logger.warning(f"environment variable {env_var} conversion failed: {e}")
    
    def _validate_config(self):
        """Validate configuration validity"""
        # Ensure port is within valid range
        if not (1 <= self._config['api_port'] <= 65535):
            raise ValueError(f"API port number must be between 1-65535: {self._config['api_port']}")
        
        # Ensure log directory exists
        log_dir = Path(self._config['log_file']).parent
        log_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self._config[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self._config.copy()
    
    def __getitem__(self, key: str) -> Any:
        """Support dictionary-style access"""
        return self._config[key]
    
    def __setitem__(self, key: str, value: Any):
        """Support dictionary-style setting"""
        self._config[key] = value
    
    def __contains__(self, key: str) -> bool:
        """Support 'in' operator"""
        return key in self._config


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get global configuration instance"""
    return config


def reload_config():
    """Reload configuration"""
    global config
    config = Config()