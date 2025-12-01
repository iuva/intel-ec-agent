"""
    ek 相关封装 - 使用项目统一日志系统记录子进程执行
"""
import subprocess
from ..utils.subprocess_utils import run_con_or_none
from ..logger import get_logger

logger = get_logger(__name__)


class EK:
    """EK 命令封装类 - 自动记录子进程执行日志"""
    
    @staticmethod
    def version():
        """
        调用系统命令 ek version
        
        如果响应为找不到 ek 命令，方法返回 None
        否则方法返回 ek version 的响应原字符串
        
        Returns:
            str | None: ek version 命令的输出，如果命令不存在则返回 None
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            ['ek', 'version'],
            command_name='ek_version',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )

    @staticmethod
    def update_check(url: str):
        """
        调用系统命令 ek update <url>
        
        如果响应为找不到 ek 命令，方法返回 None
        否则方法返回 ek update 的响应原字符串
        
        Returns:
            str | None: ek update 命令的输出，如果命令不存在则返回 None
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            ['ek', 'update', url],
            command_name='ek_update',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
            