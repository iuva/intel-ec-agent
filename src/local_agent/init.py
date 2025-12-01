#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目初始化模块
提供应用启动前的初始化功能
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)


class ApplicationInitializer:
    """应用初始化器"""
    
    def __init__(self):
        self.config = get_config()
        self.initialized = False
        self.init_steps = []
    
    async def initialize(self) -> bool:
        """执行应用初始化"""
        if self.initialized:
            logger.info("应用已初始化")
            return True
        
        logger.info("开始应用初始化...")
        
        try:
            # 执行初始化步骤
            init_steps = [
                self._setup_environment,
                self._validate_config,
                self._create_directories,
                self._setup_logging,
                self._check_dependencies,
                self._preload_modules
            ]
            
            for step in init_steps:
                step_name = step.__name__
                logger.debug(f"执行初始化步骤: {step_name}")
                
                try:
                    if asyncio.iscoroutinefunction(step):
                        result = await step()
                    else:
                        result = step()
                    
                    if not result:
                        logger.error(f"初始化步骤失败: {step_name}")
                        return False
                        
                except Exception as e:
                    logger.error(f"初始化步骤异常 {step_name}: {e}")
                    return False
            
            self.initialized = True
            logger.info("应用初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"应用初始化失败: {e}")
            return False
    
    def _setup_environment(self) -> bool:
        """设置运行环境"""
        try:
            # 设置Python路径
            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            # 设置工作目录
            os.chdir(project_root)
            
            # 设置环境变量
            os.environ.setdefault('PYTHONPATH', str(project_root))
            
            logger.debug("环境设置完成")
            return True
            
        except Exception as e:
            logger.error(f"环境设置失败: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """验证配置"""
        try:
            required_configs = [
                'api_host',
                'api_port', 
                'websocket_url',
                'log_level',
                'log_file'
            ]
            
            missing_configs = []
            for config_key in required_configs:
                if self.config.get(config_key) is None:
                    missing_configs.append(config_key)
            
            if missing_configs:
                logger.warning(f"缺少配置项: {missing_configs}")
                # 设置默认值
                self._set_default_configs()
            
            # 验证端口范围
            port = self.config.get('api_port', 8000)
            if not (1024 <= port <= 65535):
                logger.warning(f"端口号 {port} 不在有效范围内，使用默认端口 8000")
                self.config.set('api_port', 8000)
            
            logger.debug("配置验证完成")
            return True
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def _set_default_configs(self):
        """设置默认配置"""
        default_configs = {
            'api_host': '0.0.0.0',
            'api_port': 8000,
            'websocket_url': 'ws://localhost:8765',
            'log_level': 'INFO',
            'log_file': 'logs/local_agent.log',
            'agent_id': 'local_agent',
            'max_restart_attempts': 3,
            'websocket_reconnect_interval': 10
        }
        
        for key, value in default_configs.items():
            if self.config.get(key) is None:
                self.config.set(key, value)
                logger.info(f"设置默认配置: {key} = {value}")
    
    def _create_directories(self) -> bool:
        """创建必要的目录"""
        try:
            directories = [
                'logs',
                'data',
                'temp'
            ]
            
            for dir_name in directories:
                dir_path = Path(dir_name)
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"创建目录: {dir_path}")
            
            logger.debug("目录创建完成")
            return True
            
        except Exception as e:
            logger.error(f"目录创建失败: {e}")
            return False
    
    def _setup_logging(self) -> bool:
        """设置日志系统"""
        try:
            # 日志配置已在logger模块中处理
            # 这里主要确保日志文件目录存在
            log_file = self.config.get('log_file')
            if log_file:
                log_dir = Path(log_file).parent
                if not log_dir.exists():
                    log_dir.mkdir(parents=True, exist_ok=True)
            
            logger.debug("日志设置完成")
            return True
            
        except Exception as e:
            logger.error(f"日志设置失败: {e}")
            return False
    
    def _check_dependencies(self) -> bool:
        """检查依赖包"""
        try:
            required_packages = {
                'fastapi': 'FastAPI',
                'uvicorn': 'Uvicorn',
                'websockets': 'WebSockets',
                'psutil': 'psutil'
            }
            
            missing_packages = []
            
            for package, name in required_packages.items():
                try:
                    __import__(package)
                    logger.debug(f"依赖包检查通过: {name}")
                except ImportError:
                    missing_packages.append(name)
            
            if missing_packages:
                logger.error(f"缺少依赖包: {missing_packages}")
                logger.info("请运行: pip install -r requirements.txt")
                return False
            
            logger.debug("依赖包检查完成")
            return True
            
        except Exception as e:
            logger.error(f"依赖包检查失败: {e}")
            return False
    
    async def _preload_modules(self) -> bool:
        """预加载模块"""
        try:
            # 预加载核心模块，减少运行时延迟
            modules_to_preload = [
                'local_agent.api.routes',
                'local_agent.api.server',
                'local_agent.websocket.client',
                'local_agent.core.application'
            ]
            
            for module_path in modules_to_preload:
                try:
                    __import__(module_path)
                    logger.debug(f"预加载模块: {module_path}")
                except Exception as e:
                    logger.warning(f"预加载模块失败 {module_path}: {e}")
            
            # 等待异步初始化完成
            await asyncio.sleep(0.1)
            
            logger.debug("模块预加载完成")
            return True
            
        except Exception as e:
            logger.error(f"模块预加载失败: {e}")
            return False
    
    def get_init_status(self) -> Dict[str, Any]:
        """获取初始化状态"""
        return {
            'initialized': self.initialized,
            'config_valid': self._validate_config(),
            'dependencies_ok': self._check_dependencies(),
            'environment_setup': True  # 环境设置总是成功的
        }


# 全局初始化器实例
_initializer: ApplicationInitializer = None


def get_initializer() -> ApplicationInitializer:
    """获取全局初始化器实例"""
    global _initializer
    if _initializer is None:
        _initializer = ApplicationInitializer()
    return _initializer


async def initialize_application() -> bool:
    """初始化应用"""
    initializer = get_initializer()
    return await initializer.initialize()


def get_application_status() -> Dict[str, Any]:
    """获取应用状态"""
    initializer = get_initializer()
    return initializer.get_init_status()