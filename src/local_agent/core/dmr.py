"""
    DMR 相关封装 - 使用项目统一日志系统记录子进程执行
"""
import subprocess
from ..utils.subprocess_utils import run_con_or_none
from ..logger import get_logger

logger = get_logger(__name__)


class DMR:
    """DMR 命令封装类 - 自动记录子进程执行日志"""
    
    @staticmethod
    def version():
        """
        调用系统命令 dmr-config -v
        
        如果响应为找不到 dmr-config 命令，方法返回 None
        否则方法返回 dmr-config -v 的响应原字符串
        
        Returns:
            str | None: dmr-config -v 命令的输出，如果命令不存在则返回 None
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            ['dmr-config', '-v'],
            command_name='dmr-config_-v',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
    
    @staticmethod
    def get_hardware_info():
        """
        调用系统命令 dmr-config sut
        
        如果响应为找不到 dmr-config 命令，方法返回 None
        否则方法返回 dmr-config sut 的响应原字符串
        
        Returns:
            str | None: dmr-config sut 命令的输出，如果命令不存在则返回 None
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            ['dmr-config', 'sut'],
            command_name='dmr-config',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
