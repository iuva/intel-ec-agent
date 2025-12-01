#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志管理模块 - 全项目唯一日志出口
提供全项目统一的日志记录功能，支持：
- 文件和控制台输出
- 标准输出/错误重定向
- 第三方库日志捕获
- 日志轮转和归档
- 全项目统一日志出口
- 自动捕获所有输出

使用方式：
from local_agent.logger import get_logger
logger = get_logger(__name__)
logger.info("日志信息")
"""

import logging
import sys
import os
import io
from pathlib import Path
from typing import Optional, Dict, Any, List
from logging.handlers import RotatingFileHandler


class UnifiedLogger:
    """统一日志管理类 - 全项目唯一日志出口"""
    
    def __init__(self, name: str = "local_agent"):
        self.name = name
        self.logger = logging.getLogger(name)
        
        # 确保只初始化一次
        if not self.logger.handlers:
            self._setup_logger()
            
            # 只在主日志器初始化时执行重定向和第三方库捕获
            if name == "local_agent":
                self._redirect_stdout_stderr()
                self._capture_third_party_logs()
    
    def _setup_logger(self):
        """配置统一日志器 - 全项目统一出口"""
        # 设置默认配置值
        log_level = logging.INFO
        log_file = Path('logs/local_agent.log')
        log_max_size = 10 * 1024 * 1024  # 10MB
        log_backup_count = 5
        
        # 尝试从配置获取值（避免循环导入）
        try:
            from .config import get_config
            config = get_config()
            log_level = getattr(logging, config.get('log_level', 'INFO'))
            log_file = Path(config.get('log_file', 'logs/local_agent.log'))
            log_max_size = config.get('log_max_size', 10 * 1024 * 1024)
            log_backup_count = config.get('log_backup_count', 5)
        except ImportError:
            # 如果无法导入配置，使用默认值
            pass
        
        self.logger.setLevel(log_level)
        
        # 创建统一的格式化器 - 增强可读性，包含进程ID
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] %(name)s [PID:%(process)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 文件处理器 - 支持日志轮转
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=log_max_size,
            backupCount=log_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        
        # 控制台处理器 - 用于调试时查看输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        
        # 确保Windows环境下的编码兼容性
        if sys.platform == "win32":
            import locale
            try:
                # 尝试设置控制台编码为UTF-8
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8')
            except:
                pass
        
        # 添加处理器 - 文件和控制台
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # 防止日志传播到根日志器
        self.logger.propagate = False
    
    def _redirect_stdout_stderr(self):
        """重定向标准输出和错误输出到日志文件 - 全项目统一出口"""
        # 检查是否已经重定向过，避免重复重定向
        if hasattr(sys.stdout, '_is_logging_stream') or hasattr(sys.stderr, '_is_logging_stream'):
            return
        
        # 使用全局主日志器进行重定向，避免重复记录
        main_logger = logging.getLogger("local_agent")
        
        class LoggingStream:
            """将标准输出重定向到日志的流 - 全项目统一出口"""
            def __init__(self, level=logging.INFO, original_stream=None):
                self.level = level
                self._is_logging_stream = True  # 标记为日志流
                self.original_stream = original_stream  # 保留原始流
            
            def write(self, msg):
                if msg.strip():  # 忽略空消息
                    # 直接写入到原始流，不通过日志系统，避免递归调用
                    if self.original_stream:
                        self.original_stream.write(msg)
                        self.original_stream.flush()
                return len(msg)
            
            def flush(self):
                if self.original_stream:
                    self.original_stream.flush()
            
            def isatty(self):
                return False
            
            def fileno(self):
                # 返回原始流的文件描述符
                if self.original_stream and hasattr(self.original_stream, 'fileno'):
                    return self.original_stream.fileno()
                return -1
        
        # 重定向标准输出 - 保留原始控制台输出
        sys.stdout = LoggingStream(logging.INFO, sys.__stdout__)
        
        # 重定向标准错误 - 保留原始控制台输出
        sys.stderr = LoggingStream(logging.ERROR, sys.__stderr__)
    
    def _capture_third_party_logs(self):
        """捕获第三方库的日志输出 - 全项目统一出口"""
        # 设置默认日志级别
        log_level = logging.INFO
        
        # 尝试从配置获取值（避免循环导入）
        try:
            from .config import get_config
            config = get_config()
            log_level = getattr(logging, config.get('log_level', 'INFO'))
        except ImportError:
            # 如果无法导入配置，使用默认值
            pass
        
        # 设置根日志器级别
        logging.getLogger().setLevel(log_level)
        
        # 为常见第三方库设置日志级别 - 增强捕获范围
        third_party_loggers = [
            # Web框架相关
            'websockets', 'fastapi', 'uvicorn', 'starlette', 'flask', 'django',
            # 网络相关
            'asyncio', 'aiohttp', 'httpx', 'requests', 'urllib3', 'socketio',
            # 系统相关
            'psutil', 'win32', 'pywin32', 'wmi', 'pywintypes',
            # 数据库相关
            'sqlalchemy', 'aiosqlite', 'sqlite3', 'pymysql', 'psycopg2',
            # 序列化相关
            'json', 'pickle', 'yaml', 'toml',
            # 其他常用库
            'PIL', 'Pillow', 'numpy', 'pandas', 'matplotlib', 'opencv',
            # 日期时间相关
            'datetime', 'time', 'calendar',
            # 文件系统相关
            'os', 'sys', 'pathlib', 'shutil', 'glob'
        ]
        
        for logger_name in third_party_loggers:
            try:
                lib_logger = logging.getLogger(logger_name)
                lib_logger.setLevel(log_level)
                # 防止第三方库日志传播到根日志器
                lib_logger.propagate = False
                
                # 清除现有处理器，避免重复输出
                for handler in lib_logger.handlers[:]:
                    lib_logger.removeHandler(handler)
                    
                # 添加项目统一处理器
                for handler in self.logger.handlers:
                    lib_logger.addHandler(handler)
                    
            except Exception as e:
                # 捕获配置异常，不影响主流程
                self.logger.warning(f"配置第三方库日志器 {logger_name} 失败: {e}")
    
    def debug(self, msg: str, *args, **kwargs):
        """调试级别日志"""
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """信息级别日志"""
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """警告级别日志"""
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """错误级别日志"""
        self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """严重级别日志"""
        self.logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """异常日志"""
        self.logger.exception(msg, *args, **kwargs)
    
    def print(self, msg: str, *args, **kwargs):
        """兼容print语句的日志方法"""
        self.info(f"[PRINT] {msg}", *args, **kwargs)


# 全局日志实例管理
_global_loggers: Dict[str, UnifiedLogger] = {}
# 重定向状态标记
_redirected = False
# 全局初始化状态
_initialized = False


def get_logger(name: str = "local_agent") -> UnifiedLogger:
    """获取全局日志实例 - 全项目统一入口（自动初始化）"""
    # 自动初始化日志系统（如果尚未初始化）
    if not _initialized:
        _auto_setup_logging(True)
    
    if name not in _global_loggers:
        _global_loggers[name] = UnifiedLogger(name)
    return _global_loggers[name]


def _auto_setup_logging(debug=False):
    """自动初始化日志系统（内部使用）"""
    global _initialized
    
    if not _initialized:
        # 标记为已初始化，避免递归调用
        _initialized = True
        
        # 初始化主日志器（直接创建，不通过get_logger避免递归）
        if "local_agent" not in _global_loggers:
            # 在初始化时设置日志级别（如果是debug模式）
            if debug:
                # 临时修改全局配置以支持debug模式
                import os
                os.environ['LOG_LEVEL'] = 'DEBUG'
                
            main_logger = UnifiedLogger("local_agent")
            _global_loggers["local_agent"] = main_logger
        else:
            main_logger = _global_loggers["local_agent"]
        
        # 设置常见模块的日志器（直接创建，不通过get_logger）
        module_loggers = [
            'local_agent.api', 'local_agent.core', 'local_agent.websocket',
            'local_agent.config', 'local_agent.init',
            # 脚本模块
            'scripts.production_launcher', 'scripts.ultimate_keepalive',
            'scripts.pyinstaller_packager', 'scripts.portable_packager',
            # 测试模块
            'tests.test_application', 'tests.websocket_server'
        ]
        
        for module_name in module_loggers:
            if module_name not in _global_loggers:
                _global_loggers[module_name] = UnifiedLogger(module_name)
        
        main_logger.info("全局日志系统初始化完成")


def setup_global_logging(debug=False):
    """设置全局日志配置 - 应用启动时调用（兼容性函数）"""
    _auto_setup_logging(debug=debug)


def redirect_all_output():
    """重定向所有输出到日志 - 用于脚本和独立运行"""
    global _redirected
    
    # 避免重复重定向
    if _redirected:
        return
    
    main_logger = get_logger("local_agent")
    main_logger.info("开始重定向所有输出到日志系统")
    
    # 标记为重定向状态
    _redirected = True


def is_logging_initialized() -> bool:
    """检查日志系统是否已初始化"""
    return _initialized


def get_all_loggers() -> List[str]:
    """获取所有已注册的日志器名称"""
    return list(_global_loggers.keys())


def set_log_level(level: str):
    """动态设置全局日志级别"""
    try:
        log_level = getattr(logging, level.upper())
        
        # 更新所有已注册的日志器
        for logger_name, logger_instance in _global_loggers.items():
            logger_instance.logger.setLevel(log_level)
            
        # 更新根日志器
        logging.getLogger().setLevel(log_level)
        
        get_logger().info(f"全局日志级别已设置为: {level}")
        
    except AttributeError:
        get_logger().error(f"无效的日志级别: {level}")


def flush_all_logs():
    """刷新所有日志缓冲区"""
    for logger_instance in _global_loggers.values():
        for handler in logger_instance.logger.handlers:
            handler.flush()


# 便捷的全局日志函数
def log_debug(msg: str):
    """全局调试日志"""
    get_logger().debug(msg)

def log_info(msg: str):
    """全局信息日志"""
    get_logger().info(msg)

def log_warning(msg: str):
    """全局警告日志"""
    get_logger().warning(msg)

def log_error(msg: str):
    """全局错误日志"""
    get_logger().error(msg)

def log_critical(msg: str):
    """全局严重日志"""
    get_logger().critical(msg)


# 简化导入接口
def setup_logging():
    """简化日志设置函数 - 自动初始化并重定向输出"""
    _auto_setup_logging()
    redirect_all_output()
    return get_logger()


def get_module_logger(module_name: str = None):
    """获取模块日志器 - 自动推断模块名"""
    if module_name is None:
        # 自动推断调用者模块名
        import inspect
        frame = inspect.currentframe()
        try:
            # 获取调用者的模块名
            caller_frame = frame.f_back
            caller_module = caller_frame.f_globals.get('__name__', 'unknown')
            
            # 简化模块名
            if caller_module.startswith('src.'):
                module_name = caller_module[4:]  # 移除'src.'前缀
            elif caller_module.startswith('scripts.'):
                module_name = caller_module
            elif caller_module.startswith('tests.'):
                module_name = caller_module
            else:
                module_name = caller_module
                
        except Exception:
            module_name = 'unknown'
        finally:
            del frame
    
    return get_logger(module_name)