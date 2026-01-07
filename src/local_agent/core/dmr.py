"""
    DMR 相关封装 - 使用项目统一日志系统记录子进程执行
"""
from ..utils.subprocess_utils import run_con_or_none, run_async
from ..logger import get_logger
from ..utils.python_utils import PythonUtils
from local_agent.utils.http_client import http_client

logger = get_logger(__name__)

dmr_com = 'dmr-config'


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
            [dmr_com, '-v'],
            command_name='dmr-config_-v',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )



    @staticmethod
    def update(url: str):
        """
        更新dmr
        """
        update_url = http_client._build_file_url(url)
        if update_url:
            python = PythonUtils.get_python_executable()

            # 延迟导入以避免循环依赖
            from local_agent.utils.whl_updater import update_from_whl_sync
            
            resunt = update_from_whl_sync(update_url, python)
            if resunt.get('success', False):
                logger.info('dmr_config 更新成功')
            else:
                logger.error(f'dmr_config 更新失败: {resunt.get("error", "未知错误")}')
            return resunt.get('success', False)

    

    @staticmethod
    def get_hardware_info():
        """
        调用系统命令 dmr-config sut
        获取硬件信息
        异步执行，不等待结果
        """

        # 直接使用dmr_com，它已经是相对路径
        run_async([dmr_com, 'sut'])
        
