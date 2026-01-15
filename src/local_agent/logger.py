#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified log management module - Single log entry point for the entire project
Provides unified logging functionality for the entire project, supporting:
- File and console output
- Standard output/error redirection
- Third-party library log capture
- Log rotation and archiving
- Single log entry point for the entire project
- Automatic capture of all output

Usage:
from local_agent.logger import get_logger
logger = get_logger(__name__)
logger.info("Log info")
"""

import logging
import sys
import os
import io
import threading
import time
import inspect
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from logging.handlers import RotatingFileHandler


class DynamicModuleFormatter(logging.Formatter):
    """自定义Formatter，动态获取调用者文件名和行号"""
    
    def format(self, record):
        # 动态设置文件名和行号
        if not hasattr(record, 'file_info') or record.file_info == 'unknown':
            record.file_info = self._get_caller_file_info(record)
        return super().format(record)
    
    def _get_caller_file_info(self, record):
        """动态获取调用者文件名和行号"""
        try:
            # 使用更简单的方法：直接获取调用栈
            stack = inspect.stack()
            
            # 跳过前几层（当前方法、logging模块等）
            for frame_info in stack[3:]:  # 跳过前3层：当前方法、format方法、logging调用
                frame = frame_info.frame
                
                # 获取文件名和行号
                filename = frame.f_code.co_filename
                lineno = frame_info.lineno
                
                # 获取模块名
                module_name = frame.f_globals.get('__name__', 'unknown')
                
                # 跳过logging模块和当前模块
                if module_name.startswith('logging') or module_name == __name__:
                    continue
                
                # 提取文件名（去掉路径，只保留文件名）
                if '/' in filename:
                    filename = filename.split('/')[-1]
                elif '\\' in filename:
                    filename = filename.split('\\')[-1]
                
                # 如果是Python文件，去掉.py扩展名
                if filename.endswith('.py'):
                    filename = filename[:-3]
                
                # 组合模块名和文件名
                module_part = ''
                if '.' in module_name:
                    # 提取模块路径的最后一部分
                    module_parts = module_name.split('.')
                    if len(module_parts) > 1:
                        # 取最后两级模块名
                        module_part = '.'.join(module_parts[-2:]) + '.' if len(module_parts) > 2 else module_parts[-1] + '.'
                
                return f"{module_part}{filename}:{lineno}"
                
        except Exception as e:
            # 如果出错，返回默认信息
            pass
        
        return 'unknown'


class UnifiedLogger:
    """Unified log management class - Single log entry point for the entire project"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, name: str = "local_agent"):
        """全局单例模式，确保只有一个logger实例"""
        global _global_logger_instance
        
        with cls._lock:
            if _global_logger_instance is None:
                _global_logger_instance = super().__new__(cls)
                _global_logger_instance._initialized = False
            return _global_logger_instance
    
    def __init__(self, name: str = "local_agent"):
        """初始化全局唯一的logger实例"""
        if not hasattr(self, '_initialized') or not self._initialized:
            with self._lock:
                if not hasattr(self, '_initialized') or not self._initialized:
                    self.name = "local_agent"  # 固定名称，避免重复创建
                    self.logger = logging.getLogger("local_agent")
                    
                    # Log replica management
                    self.replica_handlers: Dict[str, logging.Handler] = {}  # Active replica handlers
                    self.replica_counter = 0  # Replica counter for unique IDs
                    self.replica_lock = threading.RLock()  # Thread lock for replica operations
                    
                    # Ensure initialization only once
                    if not self.logger.handlers:
                        self._setup_logger()
                        self._redirect_stdout_stderr()
                        self._capture_third_party_logs()
                    
                    self._initialized = True
    
    def _setup_logger(self):
        """Configure unified logger - Single entry point for the entire project"""
        # Set default configuration values
        log_level = logging.INFO
        log_file = Path('logs/local_agent.log')
        log_max_size = 10 * 1024 * 1024  # 10MB
        log_backup_count = 5
        
        # Try to get values from configuration (avoid circular import)
        try:
            from .config import get_config
            config = get_config()
            log_level = getattr(logging, config.get('log_level', 'INFO'))
            log_file = Path(config.get('log_file', 'logs/local_agent.log'))
            log_max_size = config.get('log_max_size', 10 * 1024 * 1024)
            log_backup_count = config.get('log_backup_count', 5)
        except ImportError:
            # If unable to import configuration, use default values
            pass
        
        self.logger.setLevel(log_level)
        
        # Create unified formatter - enhance readability, include process ID
        formatter = DynamicModuleFormatter(
            '%(asctime)s [%(levelname)-8s] %(file_info)s [PID:%(process)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # File handler - support log rotation
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=log_max_size,
            backupCount=log_backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        
        # Console handler - for viewing output during debug
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        
        # Ensure encoding compatibility in Windows environment
        if sys.platform == "win32":
            import locale
            try:
                # Try to set console encoding to UTF-8
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8')
            except:
                pass
        
        # Add handlers - file and console
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Prevent log propagation to root logger
        # self.logger.propagate = False
    
    def _redirect_stdout_stderr(self):
        """Redirect standard output and error output to log file - Single entry point for the entire project"""
        # Check if already redirected to avoid duplicate redirection
        if hasattr(sys.stdout, '_is_logging_stream') or hasattr(sys.stderr, '_is_logging_stream'):
            return
        
        # Use global main logger for redirection to avoid duplicate logging
        main_logger = logging.getLogger("local_agent")
        
        class LoggingStream:
            """Stream that redirects standard output to log - Single entry point for the entire project"""
            def __init__(self, level=logging.INFO, original_stream=None):
                self.level = level
                self._is_logging_stream = True  # Mark as logging stream
                self.original_stream = original_stream  # Keep original stream
            
            def write(self, msg):
                if msg.strip():  # Ignore empty messages
                    # Write directly to original stream, bypassing log system to avoid recursive calls
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
                # Return original stream's file descriptor
                if self.original_stream and hasattr(self.original_stream, 'fileno'):
                    return self.original_stream.fileno()
                return -1
        
        # Redirect standard output - preserve original console output
        sys.stdout = LoggingStream(logging.INFO, sys.__stdout__)
        
        # Redirect standard error - preserve original console output
        sys.stderr = LoggingStream(logging.ERROR, sys.__stderr__)
    
    def _capture_third_party_logs(self):
        """Capture third-party library log output - unified project-wide exit"""
        # Setup default log level
        log_level = logging.INFO
        
        # Try to get values from configuration (avoid circular import)
        try:
            from .config import get_config
            config = get_config()
            log_level = getattr(logging, config.get('log_level', 'INFO'))
        except ImportError:
            # If unable to import configuration, use default values
            pass
        
        # Setup root logger level
        logging.getLogger().setLevel(log_level)
        
        # Setup log levels for common third-party libraries - enhance capture scope
        third_party_loggers = [
            # Web framework related
            'websockets', 'fastapi', 'uvicorn', 'starlette', 'flask', 'django',
            # Network related
            'asyncio', 'aiohttp', 'httpx', 'requests', 'urllib3', 'socketio',
            # System related
            'psutil', 'win32', 'pywin32', 'wmi', 'pywintypes',
            # Database related
            'sqlalchemy', 'aiosqlite', 'sqlite3', 'pymysql', 'psycopg2',
            # Serialization related
            'json', 'pickle', 'yaml', 'toml',
            # Other common libraries
            'PIL', 'Pillow', 'numpy', 'pandas', 'matplotlib', 'opencv',
            # DateTime related
            'datetime', 'time', 'calendar',
            # FileSystem related
            'os', 'sys', 'pathlib', 'shutil', 'glob'
        ]
        
        for logger_name in third_party_loggers:
            try:
                lib_logger = logging.getLogger(logger_name)
                lib_logger.setLevel(log_level)
                # Prevent third-party library logs from propagating to root logger
                lib_logger.propagate = False
                
                # Clear existing handlers to avoid duplicate output
                for handler in lib_logger.handlers[:]:
                    lib_logger.removeHandler(handler)
                    
                # Add project unified handlers
                for handler in self.logger.handlers:
                    lib_logger.addHandler(handler)
                    
            except Exception as e:
                # Capture configuration exceptions, don't affect main flow
                self.logger.warning(f"Configuring third-party logger {logger_name} failed: {e}")
    
    def debug(self, msg: str, *args, **kwargs):
        """Debug level log"""
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Info level log"""
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Warning level log"""
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Error level log"""
        self.logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Critical level log"""
        self.logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Exception log"""
        self.logger.exception(msg, *args, **kwargs)
    
    def print(self, msg: str, *args, **kwargs):
        """Log method compatible with print statement"""
        self.info(f"[PRINT] {msg}", *args, **kwargs)


    # Log replica management methods
    
    def start_log_replica(self, replica_name: str = None, 
                         replica_dir: str = "logs/replicas",
                         max_size: int = 10 * 1024 * 1024,
                         backup_count: int = 10,
                         level: Union[str, int] = logging.DEBUG) -> str:
        """
        Start a log replica - creates a separate log file for specific logging needs
        
        Args:
            replica_name: Custom name for the replica (optional)
            replica_dir: Directory to store replica files
            max_size: Maximum file size in bytes (default: 10MB)
            backup_count: Number of backup files to keep
            level: Logging level for the replica
            
        Returns:
            Replica ID that can be used to stop the replica
        """
        try:
            with self.replica_lock:
                # Generate unique replica ID
                self.replica_counter += 1
                timestamp = int(time.time())
                replica_id = f"replica_{timestamp}_{self.replica_counter:03d}"
                
                # Create replica file name
                if replica_name:
                    filename = f"{replica_name}_{replica_id}.log"
                else:
                    filename = f"{replica_id}.log"
                
                replica_file = Path(replica_dir) / filename
                
                # Ensure directory exists
                replica_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Create replica handler
                replica_handler = RotatingFileHandler(
                    replica_file,
                    maxBytes=max_size,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                
                # Set log level
                if isinstance(level, str):
                    level = getattr(logging, level.upper())
                replica_handler.setLevel(level)
                
                # Use same formatter as main logger for consistency
                if self.logger.handlers:
                    replica_handler.setFormatter(self.logger.handlers[0].formatter)
                else:
                    # Fallback formatter
                    formatter = logging.Formatter(
                        '%(asctime)s [%(levelname)-8s] %(name)s [PID:%(process)d] - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S'
                    )
                    replica_handler.setFormatter(formatter)
                
                # 关键修改：将handler添加到所有现有的UnifiedLogger实例
                # 由于propagate=False，需要直接添加到每个logger实例才能捕获日志
                for logger_instance in _global_loggers.values():
                    logger_instance.logger.addHandler(replica_handler)
                
                # Store handler for later removal
                self.replica_handlers[replica_id] = replica_handler
                
                # Log replica creation using print to avoid recursion
                print(f"Log replica started: {replica_id} -> {replica_file}")
                print(f"Replica will capture ALL logs from the entire application")
                
                return replica_id
        except Exception as e:
            # Log error using print to avoid recursion
            print(f"Error starting log replica: {e}")
            raise
    
    def stop_log_replica(self, replica_id: str):
        """
        Stop a specific log replica
        
        Args:
            replica_id: The replica ID returned by start_log_replica
        """
        try:
            with self.replica_lock:
                if replica_id in self.replica_handlers:
                    handler = self.replica_handlers[replica_id]
                    
                    # 关键修改：从所有UnifiedLogger实例中移除handler
                    for logger_instance in _global_loggers.values():
                        logger_instance.logger.removeHandler(handler)
                    
                    # Close and flush handler
                    handler.flush()
                    handler.close()
                    
                    # Remove from active replicas
                    del self.replica_handlers[replica_id]
                    
                    # Log replica stop using print to avoid recursion
                    print(f"Log replica stopped: {replica_id}")
                    print(f"Replica no longer captures logs")
                else:
                    print(f"Log replica not found: {replica_id}")
        except Exception as e:
            # Log error using print to avoid recursion
            print(f"Error stopping log replica: {e}")
            raise
    
    def stop_all_replicas(self):
        """Stop all active log replicas"""
        with self.replica_lock:
            replica_ids = list(self.replica_handlers.keys())
            for replica_id in replica_ids:
                self.stop_log_replica(replica_id)
    
    def get_active_replicas(self) -> List[str]:
        """Get list of active replica IDs"""
        with self.replica_lock:
            return list(self.replica_handlers.keys())
    
    def is_replica_active(self, replica_id: str) -> bool:
        """Check if a specific replica is active"""
        with self.replica_lock:
            return replica_id in self.replica_handlers
    
    def get_latest_replica_file(self, replica_dir: str = "logs/replicas") -> Optional[str]:
        """
        Get the file path of the latest replica log file based on creation time
        
        Args:
            replica_dir: Directory to search for replica files
            
        Returns:
            Path to the latest replica file, or None if no replica files found
        """
        try:
            replica_path = Path(replica_dir)
            
            # Check if directory exists
            if not replica_path.exists() or not replica_path.is_dir():
                return None
            
            # Find all replica log files
            replica_files = list(replica_path.glob("*.log"))
            
            if not replica_files:
                return None
            
            # Sort files by creation time (newest first)
            replica_files_with_time = []
            for file_path in replica_files:
                try:
                    # Get file creation time
                    creation_time = file_path.stat().st_ctime
                    replica_files_with_time.append((creation_time, file_path))
                except (OSError, IOError):
                    # Skip files that can't be accessed
                    continue
            
            # Sort by creation time (descending - newest first)
            replica_files_with_time.sort(key=lambda x: x[0], reverse=True)
            
            if replica_files_with_time:
                # Return the absolute path of the newest file
                return str(replica_files_with_time[0][1].resolve())
            else:
                return None
                
        except Exception as e:
            # Log error but don't crash
            self.logger.warning(f"Error getting latest replica file: {e}")
            return None


# Global logger instance management
_global_loggers: Dict[str, UnifiedLogger] = {}
_global_logger_instance = None  # 全局唯一的logger实例
# Redirection status marker
_redirected = False
# Global initialization status
_initialized = False


def get_logger(name: str = "local_agent") -> UnifiedLogger:
    """Get global logger instance - unified project-wide entry (automatic initialization)"""
    # Automatically initialize logging system (if not yet initialized)
    if not _initialized:
        _auto_setup_logging(True)
    
    # 返回全局唯一的logger实例，忽略name参数
    global _global_logger_instance
    if _global_logger_instance is None:
        _global_logger_instance = UnifiedLogger(name)
    
    return _global_logger_instance


def _auto_setup_logging(debug=False):
    """Automatically initialize logging system (internal use)"""
    global _initialized
    
    if not _initialized:
        # Mark as initialized to avoid recursive calls
        _initialized = True
        
        # Initialize main logger (direct creation, avoid recursion through get_logger)
        if "local_agent" not in _global_loggers:
            # Setup log level during initialization (if in debug mode)
            if debug:
                # Temporarily modify global configuration to support debug mode
                import os
                os.environ['LOG_LEVEL'] = 'DEBUG'
                
            main_logger = UnifiedLogger("local_agent")
            _global_loggers["local_agent"] = main_logger
        else:
            main_logger = _global_loggers["local_agent"]
        
        # Setup loggers for common modules (direct creation, avoid recursion through get_logger)
        module_loggers = [
            'local_agent.api', 'local_agent.core', 'local_agent.websocket',
            'local_agent.config', 'local_agent.init',
            # Script modules
            'scripts.production_launcher', 'scripts.ultimate_keepalive',
            'scripts.pyinstaller_packager', 'scripts.portable_packager',
            # Test modules
            'tests.test_application', 'tests.websocket_server'
        ]
        
        for module_name in module_loggers:
            if module_name not in _global_loggers:
                _global_loggers[module_name] = UnifiedLogger(module_name)
        
        main_logger.info("Global logging system initialized")


def setup_global_logging(debug=False):
    """Set global logging configuration - called when application starts (compatibility function)"""
    _auto_setup_logging(debug=debug)


def redirect_all_output():
    """Redirect all output to log - used for scripts and standalone execution"""
    global _redirected
    
    # Avoid duplicate redirection
    if _redirected:
        return
    
    main_logger = get_logger("local_agent")
    main_logger.info("Starting redirecting all output to logging system")
    
    # Mark as redirected status
    _redirected = True


def is_logging_initialized() -> bool:
    """Check if logging system has been initialized"""
    return _initialized


def get_all_loggers() -> List[str]:
    """Get all registered logger names"""
    return list(_global_loggers.keys())


def set_log_level(level: str):
    """Dynamically set global logging level"""
    try:
        log_level = getattr(logging, level.upper())
        
        # Update all registered loggers
        for logger_name, logger_instance in _global_loggers.items():
            logger_instance.logger.setLevel(log_level)
            
        # Update root logger
        logging.getLogger().setLevel(log_level)
        
        get_logger().info(f"Global logging level set to: {level}")
        
    except AttributeError:
        get_logger().error(f"Invalid logging level: {level}")


def flush_all_logs():
    """Flush all log buffers"""
    for logger_instance in _global_loggers.values():
        for handler in logger_instance.logger.handlers:
            handler.flush()


# Convenient global log functions
def log_debug(msg: str):
    """Global debug log"""
    get_logger().debug(msg)

def log_info(msg: str):
    """Global info log"""
    get_logger().info(msg)

def log_warning(msg: str):
    """Global warning log"""
    get_logger().warning(msg)

def log_error(msg: str):
    """Global error log"""
    get_logger().error(msg)

def log_critical(msg: str):
    """Global critical log"""
    get_logger().critical(msg)


# Simplified import interface
def setup_logging():
    """Simplified logging setup function - automatic initialization and output redirection"""
    _auto_setup_logging()
    redirect_all_output()
    return get_logger()


def get_module_logger(module_name: str = None):
    """Get module logger - automatically infer module name"""
    if module_name is None:
        # Automatically infer caller module name
        import inspect
        frame = inspect.currentframe()
        try:
            # Get caller's module name
            caller_frame = frame.f_back
            caller_module = caller_frame.f_globals.get('__name__', 'unknown')
            
            # Simplify module name
            if caller_module.startswith('src.'):
                module_name = caller_module[4:]  # Remove 'src.' prefix
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


# Log replica convenience functions
def start_log_replica(replica_name: str = None, 
                     replica_dir: str = "logs/replicas",
                     max_size: int = 10 * 1024 * 1024,
                     backup_count: int = 3,
                     level: Union[str, int] = logging.INFO) -> str:
    """
    Start a log replica using the main logger
    
    Args:
        replica_name: Custom name for the replica (optional)
        replica_dir: Directory to store replica files
        max_size: Maximum file size in bytes (default: 10MB)
        backup_count: Number of backup files to keep
        level: Logging level for the replica
        
    Returns:
        Replica ID that can be used to stop the replica
    """
    return get_logger().start_log_replica(replica_name, replica_dir, max_size, backup_count, level)


def stop_log_replica(replica_id: str):
    """Stop a specific log replica using the main logger"""
    get_logger().stop_log_replica(replica_id)


def stop_all_replicas():
    """Stop all active log replicas using the main logger"""
    get_logger().stop_all_replicas()


def get_active_replicas() -> List[str]:
    """Get list of active replica IDs from the main logger"""
    return get_logger().get_active_replicas()


def is_replica_active(replica_id: str) -> bool:
    """Check if a specific replica is active using the main logger"""
    return get_logger().is_replica_active(replica_id)


def get_latest_replica_file(replica_dir: str = "logs/replicas") -> Optional[str]:
    """
    Get the file path of the latest replica log file using the main logger
    
    Args:
        replica_dir: Directory to search for replica files
        
    Returns:
        Path to the latest replica file, or None if no replica files found
    """
    return get_logger().get_latest_replica_file(replica_dir)