"""
    DMR related encapsulation - Use project unified logging system to record subprocess execution
"""
from ..utils.subprocess_utils import run_con_or_none, run_async, run_as_admin
from ..logger import get_logger
from ..utils.python_utils import PythonUtils
from local_agent.utils.http_client import http_client
from ..config import get_config
import json
from local_agent.utils.http_client import http_get
import requests

api_host = get_config().get('message_api_url')

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

            # Kill the executing process of dmr-config. exe before updating
            DMR.kill_dmr()
            
            python = PythonUtils.get_python_executable()

            # Delay [import to avoid] loop dependency
            from local_agent.utils.whl_updater import update_from_whl_sync
            
            resunt = update_from_whl_sync(update_url, python)
            if resunt.get('success', False):
                logger.info('dmr_config update successful')
            else:
                logger.error(f'dmr_config update failed: {resunt.get("error", "Unknown error")}')
            return resunt.get('success', False), resunt.get("error", "Unknown error")

    @staticmethod
    def kill_dmr():
        """
        Call system command taskkill /f /im dmr-config.exe
        Kill the executing process of dmr-config. exe
        """
        # run_as_admin(
        #     ['taskkill', '/f', '/im', 'dmr-config.exe'],
        #     command_name='taskkill_dmr-config.exe',
        #     capture_output=True,
        #     text=True,
        #     timeout=100  # 10 second timeout
        # )
        http_get(
            url=f"{api_host}/kill_sut",
        )
    

    @staticmethod
    def get_hardware_info():
        """
        Call system command dmr-config sut
        Get hardware information
        Execute asynchronously, do not wait for results
        """

        # [Directly use] dmr_com, [it's already a relative] path
        # run_async([dmr_com, 'sut'])
        
        response = requests.get(f"{api_host}/get_sut", timeout=30)

        res = response.content
        logger.info(f"Response type: {type(res)}")
        
        # Convert bytes to string and then parse JSON
        res_str = res.decode('utf-8')
        
        # Parse JSON
        json_data = json.loads(res_str)
        
        return json_data.get('success')
        

    @staticmethod
    def status():
        """
        Call system command dmr-config -v
        
        If the response indicates dmr-config command not found, method returns None
        Otherwise method returns the original response string of dmr-config -v
        
        Returns:
            str | None: Output of dmr-config -v command, returns None if command does not exist
        """
        # [Use enhanced sub] process execution utility, [automatically record] execution [process and results]
        # return run_con_or_none(
        #     [dmr_com, 'status', '--json'],
        #     command_name='dmr-config_status',
        #     capture_output=True,
        #     text=True,
        #     timeout=100  # 10 second timeout
        # )


        response = requests.get(f"{api_host}/get_sut_status", timeout=30)
        res = response.content
        logger.info(f"Response type: {type(res)}")
        
        # Convert bytes to string and then parse JSON
        res_str = res.decode('utf-8')
        logger.info(f"Response content: {res_str}")
        
        # Parse JSON
        json_data = json.loads(res_str)
        logger.info(f"Parsed JSON type: {type(json_data)}")
        
        return json_data.get('user_choice')



    
    @staticmethod
    def is_running():
        """
        Check if DMR is running
        """
        res = DMR.status()
        if res:
            try:
                json_res = json.loads(res.strip())
                logger.info(f'DMR status JSON: {json_res}')
                isr = json_res.get('is_running', False)
                if isr:
                    progress = json_res.get('progress', {})
                    status = progress.get('status', '')
                    if status and not status == 'stuck':
                        return True
                    
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from dmr-config status: {res.strip()}")

            return False

