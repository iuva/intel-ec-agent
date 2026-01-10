"""
    DMR related encapsulation - Use project unified logging system to record subprocess execution
"""
from ..utils.subprocess_utils import run_con_or_none, run_async
from ..logger import get_logger
from ..utils.python_utils import PythonUtils
from local_agent.utils.http_client import http_client

logger = get_logger(__name__)

dmr_com = 'dmr-config'


class DMR:
    """DMR [command encapsulation] class - [Automatically record sub] process execution log"""
    

    @staticmethod
    def version():
        """
        Call system command dmr-config -v
        
        If the response indicates dmr-config command not found, method returns None
        Otherwise method returns the original response string of dmr-config -v
        
        Returns:
            str | None: Output of dmr-config -v command, returns None if command does not exist
        """
        # [Use enhanced sub] process execution utility, [automatically record] execution [process and results]
        return run_con_or_none(
            [dmr_com, '-v'],
            command_name='dmr-config_-v',
            capture_output=True,
            text=True,
            timeout=100  # 10 second timeout
        )



    @staticmethod
    def update(url: str):
        """
        Update DMR
        """
        update_url = http_client._build_file_url(url)
        if update_url:
            python = PythonUtils.get_python_executable()

            # Delay [import to avoid] loop dependency
            from local_agent.utils.whl_updater import update_from_whl_sync
            
            resunt = update_from_whl_sync(update_url, python)
            if resunt.get('success', False):
                logger.info('dmr_config update successful')
            else:
                logger.error(f'dmr_config update failed: {resunt.get("error", "Unknown error")}')
            return resunt.get('success', False)

    

    @staticmethod
    def get_hardware_info():
        """
        Call system command dmr-config sut
        Get hardware information
        Execute asynchronously, do not wait for results
        """

        # [Directly use] dmr_com, [it's already a relative] path
        run_async([dmr_com, 'sut'])
        
