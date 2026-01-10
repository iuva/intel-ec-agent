#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subprocess execution utility class - Integrated with project unified logging system
Provides enhanced encapsulation of subprocess.run, automatically records execution process and results to project logs
"""

import subprocess
from typing import List, Union

# [Use] project [unified] logging system
from ..logger import get_logger

logger = get_logger(__name__)


class SubprocessLogger:
    """[Sub] process execution log [recorder]"""
    
    def __init__(self, command_name: str = "unknown"):
        """
        Initialize subprocess logger
        
        Args:
            command_name: Command name, used for log identification
        """
        self.command_name = command_name
        self.logger = logger
    
    def log_command_start(self, command: Union[str, List[str]], **kwargs) -> None:
        """[Record command start] execution"""
        # [Build command string for] logging
        if isinstance(command, list):
            cmd_str = ' '.join(command)
        else:
            cmd_str = command
        
        # [Record key] parameters
        log_info = f"Starting command execution: {cmd_str}"
        
        # [Add important] parameter info
        if 'cwd' in kwargs:
            log_info += f" | Working directory: {kwargs['cwd']}"
        if 'timeout' in kwargs:
            log_info += f" | Timeout: {kwargs['timeout']} seconds"
        if 'shell' in kwargs and kwargs['shell']:
            log_info += " | Using shell mode"
        
        self.logger.info(log_info)
    
    def log_command_result(self, result: subprocess.CompletedProcess, 
                          execution_time: float = None) -> None:
        """[Record command] execution [result]"""
        
        # [Build result] log
        result_info = f"Command execution completed - Exit code: {result.returncode}"
        
        if execution_time is not None:
            result_info += f" | Execution time: {execution_time:.2f} seconds"
        
        # [Determine log level based on] exit code
        if result.returncode == 0:
            self.logger.info(result_info)
        else:
            self.logger.warning(result_info)
        
        # [Record standard output] (if [there is content])
        if result.stdout and result.stdout.strip():
            # [Limit output length], [avoid] log [too large]
            stdout_content = result.stdout.strip()
            if len(stdout_content) > 1000:
                stdout_content = stdout_content[:1000] + "... [content too long, truncated]"
            
            self.logger.debug(f"Standard output: {stdout_content}")
        
        # [Record standard] error (if [there is content])
        if result.stderr and result.stderr.strip():
            stderr_content = result.stderr.strip()
            if len(stderr_content) > 1000:
                stderr_content = stderr_content[:1000] + "... [content too long, truncated]"
            
            # Error [output uses] warning [level]
            self.logger.warning(f"Standard error: {stderr_content}")
    
    def log_command_error(self, error: Exception, command: Union[str, List[str]]) -> None:
        """[Record command] execution error"""
        if isinstance(command, list):
            cmd_str = ' '.join(command)
        else:
            cmd_str = command
        
        error_msg = f"Command execution failed: {cmd_str} - Error: {str(error)}"
        self.logger.error(error_msg)


def run_with_logging(command: Union[str, List[str]], 
                    command_name: str = None,
                    **kwargs) -> subprocess.CompletedProcess:
    """
    Execute command and automatically record execution process and results to project logs
    
    Args:
        command: Command to execute, can be string or list
        command_name: Command name, used for log identification (default derived from command)
        **kwargs: Other parameters for subprocess.run
        
    Returns:
        subprocess.CompletedProcess: Command execution result
        
    Raises:
        subprocess.SubprocessError: Subprocess related errors
        Exception: Other execution exceptions
    """
    import time
    
    # [Automatically derive command name]
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "unknown_command"
    
    # Create log [recorder]
    sp_logger = SubprocessLogger(command_name)
    
    # [Record command start]
    sp_logger.log_command_start(command, **kwargs)
    
    start_time = time.time()
    
    try:
        # Execute [command]
        result = subprocess.run(command, **kwargs)
        
        execution_time = time.time() - start_time
        
        # [Record] execution [result]
        sp_logger.log_command_result(result, execution_time)
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        
        # [Record] error info
        sp_logger.log_command_error(e, command)
        
        # [Re-raise] exception
        raise

def run_con_or_none(command: Union[str, List[str]], 
                    command_name: str = None,
                    default_returncode: int = -1,
                    **kwargs):
    """
        Safely execute command and log, will not throw exceptions
    
    Args:
        command: Command to execute
        command_name: Command name
        default_returncode: Default return code when exception occurs
        **kwargs: Other parameters for subprocess.run
        
    Returns:
        On success, returns result content (stdout.strip())
        On failure, returns None
    """
    try:
        # [In] Windows system, [if] command [execution fails], try [using] shell=True
        import platform
        if platform.system() == "Windows":
            # [First] try: [not using] shell
            result = run_with_logging_safe(
                command,
                command_name,
                default_returncode,
                **kwargs
            )
            
            # If [first] try [fails] and [error] is "File [not found]", [then use] shell=True [to retry]
            if result.returncode != 0 and ("not found" in result.stderr.lower() or 
                                         "不是内部或外部命令" in result.stderr or
                                         "系统找不到指定的文件" in result.stderr or
                                         "is not recognized as an internal or external command" in result.stderr or
                                         "The system cannot find the file specified" in result.stderr):
                # [Use] shell=True [to retry]
                kwargs_with_shell = kwargs.copy()
                kwargs_with_shell['shell'] = True
                
                result = run_with_logging_safe(
                    command,
                    command_name + "_with_shell",
                    default_returncode,
                    **kwargs_with_shell
                )
        else:
            # [Non] Windows system [directly] execute
            result = run_with_logging_safe(
                command,
                command_name,
                default_returncode,
                **kwargs
            )
        
        # Check [if command] execution [succeeded]
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # [Command] execution [failed], check if [command] does not exist
            if "not found" in result.stderr.lower() or "不是内部或外部命令" in result.stderr or "is not recognized as an internal or external command" in result.stderr:
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
    Safely execute command and log, will not throw exceptions
    
    Args:
        command: Command to execute
        command_name: Command name
        default_returncode: Default return code when exception occurs
        **kwargs: Other parameters for subprocess.run
        
    Returns:
        subprocess.CompletedProcess: Always returns result object
    """
    import time
    
    # [Automatically derive command name]
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "unknown_command"
    
    # Create log [recorder]
    sp_logger = SubprocessLogger(command_name)
    
    # [Record command start]
    sp_logger.log_command_start(command, **kwargs)
    
    start_time = time.time()
    
    try:
        # Execute [command]
        result = subprocess.run(command, **kwargs)
        
        execution_time = time.time() - start_time
        
        # [Record] execution [result]
        sp_logger.log_command_result(result, execution_time)
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        
        # [Record] error info
        sp_logger.log_command_error(e, command)
        
        # [Return a simulated] CompletedProcess [object]
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
    Execute command and get output, automatically log
    
    Args:
        command: Command to execute
        command_name: Command name
        **kwargs: Other parameters for subprocess.run
        
    Returns:
        str: Command standard output
        
    Raises:
        subprocess.CalledProcessError: Command execution failed
    """
    # [Ensure capture output]
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    
    result = run_with_logging(command, command_name, **kwargs)
    
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    
    return result.stdout.strip()


# [Convenient] functions, [provide same interface as] subprocess.run
def run(*args, **kwargs):
    """[Convenient] function, [replacement for] subprocess.run"""
    return run_with_logging(*args, **kwargs)


def run_safe(*args, **kwargs):
    """[Convenient] function, [replacement for] subprocess.run [but will not throw exceptions]"""
    return run_with_logging_safe(*args, **kwargs)


def run_async(command: List[str]):
    """
    Execute command asynchronously, do not wait for result
    
    Args:
        command: Command to execute
    """
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # Hide window
    
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    
    # [Build complete batch command]
    full_cmd = f'start "" /B cmd /c {" ".join(command)}'

    logger.info(f"Asynchronous command execution: {full_cmd}")
    
    # [Use] start [command to] create [independent] process
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
    Execute command in background, fully detached, does not return any object
    
    Args:
        command: Command to execute, can be string or list
        command_name: Command name, used for log identification
        **kwargs: Other parameters for subprocess.Popen
        
    Note:
        - This function returns immediately after starting the process, does not track process status
        - Suitable for starting background services or processes that don't need monitoring
        - Uses DETACHED_PROCESS flag on Windows to achieve complete separation
    """
    # [Automatically derive command name]
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "unknown_command"
    
    # Create log [recorder]
    sp_logger = SubprocessLogger(command_name)
    
    # [Record command start] ([background] execution)
    sp_logger.log_command_start(command, **kwargs)
    sp_logger.logger.info(f"Background command execution, fully detached")
    
    # Setup [detached] parameters
    import platform
    if platform.system() == "Windows":
        # Windows: [Use] DETACHED_PROCESS [to achieve complete separation]
        kwargs.setdefault('creationflags', subprocess.DETACHED_PROCESS | 
                                         subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        # Unix-like: [Use] setsid [to achieve] process [group separation]
        kwargs.setdefault('start_new_session', True)
    
    # [Redirect output to null device to avoid blocking]
    import os
    kwargs.setdefault('stdout', subprocess.DEVNULL)
    kwargs.setdefault('stderr', subprocess.DEVNULL)
    
    try:
        # Start [detached] process
        process = subprocess.Popen(command, **kwargs)
        
        # [Record] start info
        sp_logger.logger.info(f"Background process started, PID: {process.pid}")
        
        # [Immediately close] process [handles], [achieve complete separation]
        process.stdout.close() if process.stdout else None
        process.stderr.close() if process.stderr else None
        process.stdin.close() if process.stdin else None
        
    except Exception as e:
        # [Record] error info
        sp_logger.log_command_error(e, command)
        
        # [Re-raise] exception
        raise


def check_output(*args, **kwargs):
    """[Convenient] function, [replacement for] subprocess.check_output"""
    return check_output_with_logging(*args, **kwargs)


def run_as_admin(command: Union[str, List[str]], 
                 command_name: str = None,
                 capture_output: bool = True,
                 timeout: int = None,
                 cwd: str = None,
                 **kwargs) -> Union[str, None]:
    """
    Execute command with administrator privileges (Windows system only)
    
    Args:
        command: Command to execute, can be string or list
        command_name: Command name, used for log identification
        capture_output: Whether to capture output (default True)
        timeout: Command execution timeout time (seconds)
        cwd: Working directory
        **kwargs: Other subprocess.run parameters
        
    Returns:
        On success, returns command output (stdout.strip()), on failure returns None
        
    Note:
        - This feature only works on Windows system
        - Will trigger UAC (User Account Control) prompt, requires user confirmation
        - Very useful for system operations requiring administrator privileges
    """
    import platform
    
    # Check [operating] system
    if platform.system() != "Windows":
        logger.warning("Administrator privileges execution only supported on Windows system")
        return None
    
    # [Automatically derive command name]
    if command_name is None:
        if isinstance(command, list) and len(command) > 0:
            command_name = command[0]
        elif isinstance(command, str):
            command_name = command.split()[0] if ' ' in command else command
        else:
            command_name = "admin_command"
    
    # [Build complete command string]
    if isinstance(command, list):
        cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
    else:
        cmd_str = command
    
    
    # [Practical solution]: If [current] process [is not] administrator, [directly return] error info
    # [Avoid] UAC [popup causing blocking issues]
    
    # Check [if current] process [has] administrator [permissions]
    def is_admin():
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    # [Prepare] execution parameters
    exec_kwargs = {
        'capture_output': capture_output,
        'text': True,
        'shell': False
    }
    
    # [Add optional] parameters
    if timeout:
        exec_kwargs['timeout'] = timeout
    if cwd:
        exec_kwargs['cwd'] = cwd
    
    # [Merge other] parameters
    exec_kwargs.update(kwargs)
    
    try:
        if is_admin():
            # [Current] process [already is] administrator, [directly] execute [command]
            logger.info(f"Current process has administrator privileges, executing command directly: {cmd_str}")
            
            # [Build complete command]
            if isinstance(command, list):
                result = subprocess.run(command, **exec_kwargs)
            else:
                result = subprocess.run(cmd_str, **exec_kwargs)
            
            logger.debug(f"Command execution result: {result}")
            # Check execution [result]
            if result.returncode == 0:
                logger.info(f"Command execution successful: {command_name}")
                if capture_output:
                    return result.stdout.strip()
                else:
                    return "Command execution successful"
            else:
                logger.error(f"Command execution failed, exit code: {result.returncode}")
                if capture_output and result.stderr:
                    logger.error(f"error info: {result.stderr}")
                return None
                
        else:
            # [Current] process [is not] administrator, [return] error info
            logger.warning(f"Current process does not have administrator privileges, cannot execute commands requiring administrator privileges: {cmd_str}")
            logger.warning(f"Recommendation: Please run this program as administrator")
            
            # Try [directly] execute ([may] fail, [but won't block])
            try:
                if isinstance(command, list):
                    result = subprocess.run(command, **exec_kwargs)
                else:
                    result = subprocess.run(cmd_str, **exec_kwargs)
                
                if result.returncode == 0:
                    logger.info(f"Command execution successful (no administrator privileges required): {command_name}")
                    if capture_output:
                        return result.stdout.strip()
                    else:
                        return "Command execution successful"
                else:
                    logger.warning(f"Command execution failed (insufficient permissions): {command_name}")
                    return None
                    
            except Exception as e:
                logger.warning(f"Attempt to execute command failed (insufficient permissions): {e}")
                return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"Command execution timeout: {cmd_str}")
        return None
    except Exception as e:
        logger.error(f"Exception occurred while executing command: {e}")
        return None


def run_cmd_as_admin(cmd_command: str, 
                     command_name: str = None,
                     **kwargs) -> Union[str, None]:
    """
    Execute cmd command with administrator privileges
    
    Args:
        cmd_command: cmd command to execute
        command_name: Command name, used for log identification
        **kwargs: Other parameters (same as run_as_admin)
        
    Returns:
        On success, returns command output, on failure returns None
        
    Example:
        >>> run_cmd_as_admin("net session", "check_admin")
        >>> run_cmd_as_admin("sc query eventlog", "service_check")
    """
    # [Use] cmd.exe [to execute] command
    full_command = ['cmd.exe', '/c', cmd_command]
    
    # [Automatically] setup [command name]
    if command_name is None:
        command_name = cmd_command.split()[0] if ' ' in cmd_command else cmd_command
        command_name = f"cmd_{command_name}"
    
    return run_as_admin(full_command, command_name, **kwargs)
