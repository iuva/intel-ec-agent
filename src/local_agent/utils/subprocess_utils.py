#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
子进程执行工具类 - 集成项目统一日志系统
提供subprocess.run的增强封装，自动记录执行过程和结果到项目日志
"""

import subprocess
from typing import List, Union

# 使用项目统一日志系统
from ..logger import get_logger

logger = get_logger(__name__)


class SubprocessLogger:
    """子进程执行日志记录器"""
    
    def __init__(self, command_name: str = "unknown"):
        """
        初始化子进程日志记录器
        
        Args:
            command_name: 命令名称，用于日志标识
        """
        self.command_name = command_name
        self.logger = logger
    
    def log_command_start(self, command: Union[str, List[str]], **kwargs) -> None:
        """记录命令开始执行"""
        # 构建命令字符串用于日志
        if isinstance(command, list):
            cmd_str = ' '.join(command)
        else:
            cmd_str = command
        
        # 记录关键参数
        log_info = f"开始执行命令: {cmd_str}"
        
        # 添加重要参数信息
        if 'cwd' in kwargs:
            log_info += f" | 工作目录: {kwargs['cwd']}"
        if 'timeout' in kwargs:
            log_info += f" | 超时时间: {kwargs['timeout']}秒"
        if 'shell' in kwargs and kwargs['shell']:
            log_info += " | 使用shell模式"
        
        self.logger.info(log_info)
    
    def log_command_result(self, result: subprocess.CompletedProcess, 
                          execution_time: float = None) -> None:
        """记录命令执行结果"""
        
        # 构建结果日志
        result_info = f"命令执行完成 - 退出码: {result.returncode}"
        
        if execution_time is not None:
            result_info += f" | 执行时间: {execution_time:.2f}秒"
        
        # 根据退出码决定日志级别
        if result.returncode == 0:
            self.logger.info(result_info)
        else:
            self.logger.warning(result_info)
        
        # 记录标准输出（如果有内容）
        if result.stdout and result.stdout.strip():
            # 限制输出长度，避免日志过大
            stdout_content = result.stdout.strip()
            if len(stdout_content) > 1000:
                stdout_content = stdout_content[:1000] + "... [内容过长被截断]"
            
            self.logger.debug(f"标准输出: {stdout_content}")
        
        # 记录标准错误（如果有内容）
        if result.stderr and result.stderr.strip():
            stderr_content = result.stderr.strip()
            if len(stderr_content) > 1000:
                stderr_content = stderr_content[:1000] + "... [内容过长被截断]"
            
            # 错误输出使用警告级别
            self.logger.warning(f"标准错误: {stderr_content}")
    
    def log_command_error(self, error: Exception, command: Union[str, List[str]]) -> None:
        """记录命令执行错误"""
        if isinstance(command, list):
            cmd_str = ' '.join(command)
        else:
            cmd_str = command
        
        error_msg = f"命令执行失败: {cmd_str} - 错误: {str(error)}"
        self.logger.error(error_msg)


def run_with_logging(command: Union[str, List[str]], 
                    command_name: str = None,
                    **kwargs) -> subprocess.CompletedProcess:
    """
    执行命令并自动记录执行过程和结果到项目日志
    
    Args:
        command: 要执行的命令，可以是字符串或列表
        command_name: 命令名称，用于日志标识（默认从命令推导）
        **kwargs: subprocess.run的其他参数
        
    Returns:
        subprocess.CompletedProcess: 命令执行结果
        
    Raises:
        subprocess.SubprocessError: 子进程相关错误
        Exception: 其他执行异常
    """
    import time
    
    # 自动推导命令名称
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "unknown_command"
    
    # 创建日志记录器
    sp_logger = SubprocessLogger(command_name)
    
    # 记录命令开始
    sp_logger.log_command_start(command, **kwargs)
    
    start_time = time.time()
    
    try:
        # 执行命令
        result = subprocess.run(command, **kwargs)
        
        execution_time = time.time() - start_time
        
        # 记录执行结果
        sp_logger.log_command_result(result, execution_time)
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        
        # 记录错误信息
        sp_logger.log_command_error(e, command)
        
        # 重新抛出异常
        raise

def run_con_or_none(command: Union[str, List[str]], 
                    command_name: str = None,
                    default_returncode: int = -1,
                    **kwargs):
    """
        安全执行命令并记录日志，不会抛出异常
    
    Args:
        command: 要执行的命令
        command_name: 命令名称
        default_returncode: 异常时的默认返回码
        **kwargs: subprocess.run的其他参数
        
    Returns:
        成功时，返回结果内容（stdout.strip()）
        失败时，返回 None
    """
    try:
        # 在Windows系统中，如果命令执行失败，尝试使用shell=True
        import platform
        if platform.system() == "Windows":
            # 第一次尝试：不使用shell
            result = run_with_logging_safe(
                command,
                command_name,
                default_returncode,
                **kwargs
            )
            
            # 如果第一次尝试失败且错误是"文件未找到"，则使用shell=True重试
            if result.returncode != 0 and ("not found" in result.stderr.lower() or 
                                         "不是内部或外部命令" in result.stderr or
                                         "系统找不到指定的文件" in result.stderr):
                # 使用shell=True重试
                kwargs_with_shell = kwargs.copy()
                kwargs_with_shell['shell'] = True
                
                result = run_with_logging_safe(
                    command,
                    command_name + "_with_shell",
                    default_returncode,
                    **kwargs_with_shell
                )
        else:
            # 非Windows系统直接执行
            result = run_with_logging_safe(
                command,
                command_name,
                default_returncode,
                **kwargs
            )
        
        # 检查命令是否执行成功
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # 命令执行失败，检查是否是命令不存在
            if "not found" in result.stderr.lower() or "不是内部或外部命令" in result.stderr:
                return None
            else:
                return None
                
    except Exception as e:
        return None


def run_with_logging_safe(command: Union[str, List[str]], 
                         command_name: str = None,
                         default_returncode: int = -1,
                         **kwargs) -> subprocess.CompletedProcess:
    """
    安全执行命令并记录日志，不会抛出异常
    
    Args:
        command: 要执行的命令
        command_name: 命令名称
        default_returncode: 异常时的默认返回码
        **kwargs: subprocess.run的其他参数
        
    Returns:
        subprocess.CompletedProcess: 总是返回结果对象
    """
    import time
    
    # 自动推导命令名称
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "unknown_command"
    
    # 创建日志记录器
    sp_logger = SubprocessLogger(command_name)
    
    # 记录命令开始
    sp_logger.log_command_start(command, **kwargs)
    
    start_time = time.time()
    
    try:
        # 执行命令
        result = subprocess.run(command, **kwargs)
        
        execution_time = time.time() - start_time
        
        # 记录执行结果
        sp_logger.log_command_result(result, execution_time)
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        
        # 记录错误信息
        sp_logger.log_command_error(e, command)
        
        # 返回一个模拟的CompletedProcess对象
        return subprocess.CompletedProcess(
            args=command,
            returncode=default_returncode,
            stdout="",
            stderr=str(e)
        )


def check_output_with_logging(command: Union[str, List[str]],
                             command_name: str = None,
                             **kwargs) -> str:
    """
    执行命令并获取输出，自动记录日志
    
    Args:
        command: 要执行的命令
        command_name: 命令名称
        **kwargs: subprocess.run的其他参数
        
    Returns:
        str: 命令的标准输出
        
    Raises:
        subprocess.CalledProcessError: 命令执行失败
    """
    # 确保捕获输出
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    
    result = run_with_logging(command, command_name, **kwargs)
    
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    
    return result.stdout.strip()


# 便捷函数，提供与subprocess.run相同的接口
def run(*args, **kwargs):
    """便捷函数，替代subprocess.run"""
    return run_with_logging(*args, **kwargs)


def run_safe(*args, **kwargs):
    """便捷函数，替代subprocess.run但不会抛出异常"""
    return run_with_logging_safe(*args, **kwargs)


def check_output(*args, **kwargs):
    """便捷函数，替代subprocess.check_output"""
    return check_output_with_logging(*args, **kwargs)
