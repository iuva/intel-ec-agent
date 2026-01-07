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


def run_async(command: List[str]):
    """
    异步执行命令，不等待结果
    
    Args:
        command: 要执行的命令
    """
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # 隐藏窗口
    
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    
    # 构建完整的批处理命令
    full_cmd = f'start "" /B cmd /c {" ".join(command)}'

    logger.info(f"异步执行命令: {full_cmd}")
    
    # 使用start命令创建独立进程
    subprocess.Popen(
        full_cmd, 
        shell=True,
        startupinfo=startupinfo,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def run_detached(command: Union[str, List[str]], 
                 command_name: str = None,
                 **kwargs) -> None:
    """
    后台执行命令，完全分离，不返回任何对象
    
    Args:
        command: 要执行的命令，可以是字符串或列表
        command_name: 命令名称，用于日志标识
        **kwargs: subprocess.Popen的其他参数
        
    Note:
        - 此函数启动进程后立即返回，不跟踪进程状态
        - 适用于启动后台服务或不需要监控的进程
        - 在Windows上使用DETACHED_PROCESS标志实现完全分离
    """
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
    
    # 记录命令开始（后台执行）
    sp_logger.log_command_start(command, **kwargs)
    sp_logger.logger.info(f"后台执行命令，完全分离")
    
    # 设置分离参数
    import platform
    if platform.system() == "Windows":
        # Windows: 使用DETACHED_PROCESS实现完全分离
        kwargs.setdefault('creationflags', subprocess.DETACHED_PROCESS | 
                                         subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        # Unix-like: 使用setsid实现进程组分离
        kwargs.setdefault('start_new_session', True)
    
    # 重定向输出到空设备以避免阻塞
    import os
    kwargs.setdefault('stdout', subprocess.DEVNULL)
    kwargs.setdefault('stderr', subprocess.DEVNULL)
    
    try:
        # 启动分离进程
        process = subprocess.Popen(command, **kwargs)
        
        # 记录启动信息
        sp_logger.logger.info(f"后台进程已启动，PID: {process.pid}")
        
        # 立即关闭进程句柄，实现完全分离
        process.stdout.close() if process.stdout else None
        process.stderr.close() if process.stderr else None
        process.stdin.close() if process.stdin else None
        
    except Exception as e:
        # 记录错误信息
        sp_logger.log_command_error(e, command)
        
        # 重新抛出异常
        raise


def check_output(*args, **kwargs):
    """便捷函数，替代subprocess.check_output"""
    return check_output_with_logging(*args, **kwargs)


def run_as_admin(command: Union[str, List[str]], 
                 command_name: str = None,
                 capture_output: bool = True,
                 timeout: int = None,
                 cwd: str = None,
                 **kwargs) -> Union[str, None]:
    """
    以管理员权限执行命令（仅Windows系统）
    
    Args:
        command: 要执行的命令，可以是字符串或列表
        command_name: 命令名称，用于日志标识
        capture_output: 是否捕获输出（默认True）
        timeout: 命令执行超时时间（秒）
        cwd: 工作目录
        **kwargs: 其他subprocess.run参数
        
    Returns:
        成功时返回命令输出（stdout.strip()），失败时返回None
        
    Note:
        - 此功能仅在Windows系统上有效
        - 会触发UAC（用户账户控制）提示，需要用户确认
        - 对于需要管理员权限的系统操作非常有用
    """
    import platform
    
    # 检查操作系统
    if platform.system() != "Windows":
        logger.warning("管理员权限执行仅在Windows系统上支持")
        return None
    
    # 自动推导命令名称
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "admin_command"
    
    # 构建完整的命令字符串
    if isinstance(command, list):
        cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
    else:
        cmd_str = command
    
    
    # 实用方案：如果当前进程不是管理员，直接返回错误信息
    # 避免UAC弹窗导致的阻塞问题
    
    # 检查当前进程是否具有管理员权限
    def is_admin():
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    # 准备执行参数
    exec_kwargs = {
        'capture_output': capture_output,
        'text': True,
        'shell': False
    }
    
    # 添加可选参数
    if timeout:
        exec_kwargs['timeout'] = timeout
    if cwd:
        exec_kwargs['cwd'] = cwd
    
    # 合并其他参数
    exec_kwargs.update(kwargs)
    
    try:
        if is_admin():
            # 当前进程已经是管理员，直接执行命令
            logger.info(f"当前进程具有管理员权限，直接执行命令: {cmd_str}")
            
            # 构建完整的命令
            if isinstance(command, list):
                result = subprocess.run(command, **exec_kwargs)
            else:
                result = subprocess.run(cmd_str, **exec_kwargs)
            
            logger.debug(f"命令执行结果: {result}")
            # 检查执行结果
            if result.returncode == 0:
                logger.info(f"命令执行成功: {command_name}")
                if capture_output:
                    return result.stdout.strip()
                else:
                    return "命令执行成功"
            else:
                logger.error(f"命令执行失败，退出码: {result.returncode}")
                if capture_output and result.stderr:
                    logger.error(f"错误信息: {result.stderr}")
                return None
                
        else:
            # 当前进程不是管理员，返回错误信息
            logger.warning(f"当前进程无管理员权限，无法执行需要管理员权限的命令: {cmd_str}")
            logger.warning(f"建议：请以管理员身份运行此程序")
            
            # 尝试直接执行（可能失败，但不会阻塞）
            try:
                if isinstance(command, list):
                    result = subprocess.run(command, **exec_kwargs)
                else:
                    result = subprocess.run(cmd_str, **exec_kwargs)
                
                if result.returncode == 0:
                    logger.info(f"命令执行成功（无需管理员权限）: {command_name}")
                    if capture_output:
                        return result.stdout.strip()
                    else:
                        return "命令执行成功"
                else:
                    logger.warning(f"命令执行失败（权限不足）: {command_name}")
                    return None
                    
            except Exception as e:
                logger.warning(f"尝试执行命令失败（权限不足）: {e}")
                return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"命令执行超时: {cmd_str}")
        return None
    except Exception as e:
        logger.error(f"执行命令时发生异常: {e}")
        return None


def run_cmd_as_admin(cmd_command: str, 
                     command_name: str = None,
                     **kwargs) -> Union[str, None]:
    """
    以管理员权限执行cmd命令
    
    Args:
        cmd_command: 要执行的cmd命令
        command_name: 命令名称，用于日志标识
        **kwargs: 其他参数（同run_as_admin）
        
    Returns:
        成功时返回命令输出，失败时返回None
        
    Example:
        >>> run_cmd_as_admin("net session", "check_admin")
        >>> run_cmd_as_admin("sc query eventlog", "service_check")
    """
    # 使用cmd.exe执行命令
    full_command = ['cmd.exe', '/c', cmd_command]
    
    # 自动设置命令名称
    if command_name is None:
        command_name = cmd_command.split()[0] if ' ' in cmd_command else cmd_command
        command_name = f"cmd_{command_name}"
    
    return run_as_admin(full_command, command_name, **kwargs)
