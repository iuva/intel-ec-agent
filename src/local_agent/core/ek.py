"""
    EK related encapsulation - Use project unified logging system to record subprocess execution
"""
import shutil
import psutil
import os
from ..utils.subprocess_utils import run_con_or_none
from ..logger import get_logger
from ..utils.python_utils import PythonUtils
from ..utils.path_utils import PathUtils
from local_agent.utils.http_client import http_client
import sys
import subprocess

logger = get_logger(__name__)

ek_base_path = 'ek/Scripts/'
ek_python = ek_base_path + 'python.exe'
ek_com = ek_base_path + 'ek.exe'

class EK:
    """EK [command encapsulation] class - [automatically records sub] process execution log"""

    @staticmethod
    def env_check():
        """
        Check if EK exists
        """
        # Test if the virtual environment python is available
        is_python_ok = run_con_or_none(
            [ek_python, '--version'],
            command_name='ek_python_version',
            capture_output=True,
            text=True,
            timeout=100  # 10 second timeout
        )
        
        if is_python_ok:
            logger.error('Execution Kit virtual environment python is available')
            return

        # Try to delete the relative path ek directory
        if os.path.exists('ek'):
            EK.force_stop_ek_processes()
            shutil.rmtree('ek')

        python = PythonUtils.get_python_executable()

        run_con_or_none(
            [python, '-m', 'venv', 'ek'],
            command_name='ek_version',
            capture_output=True,
            text=True,
            timeout=100  # 10 second timeout
        )

    
    @staticmethod
    def version():
        """
        Call system command ek version
        
        If the response indicates that the ek command is not found, the method returns None
        Otherwise, the method returns the original response string from ek version
        
        Returns:
            str | None: Output of ek version command, returns None if command does not exist
        """
        # Use enhanced subprocess execution tool to automatically record execution process and results
        return run_con_or_none(
            [ek_com, 'version'],
            command_name='ek_version',
            capture_output=True,
            text=True,
            timeout=100  # 10 second timeout
        )

    @staticmethod
    def update(url: str):
        """
        Update EK
        """
        update_url = http_client._build_file_url(url)
        if update_url:
            EK.force_stop_ek_processes()
            # Delay import to avoid circular dependency
            from local_agent.utils.whl_updater import update_from_whl_sync
            resunt = update_from_whl_sync(update_url, ek_python)
            if resunt.get('success', False):
                logger.info('Execution Kit update successful')
            else:
                logger.error(f'Execution Kit update failed: {resunt.get("error", "Unknown error")}')
            return resunt.get('success', False)

    @staticmethod
    def force_stop_ek_processes():
        """[Force] stop [all processes based on] ek [virtual environment]"""
        
        ek_python_path = os.path.abspath(ek_python)
        
        if not os.path.exists(ek_python_path):
            logger.info("ek virtual environment does not exist, no processes to stop")
            return 0
        
        stopped_count = 0
        ek_python_path = os.path.normcase(ek_python_path)
        
        logger.info(f"🚨 Force stopping all processes based on ek virtual environment...")
        
        # Collect all processes that need to be stopped
        processes_to_stop = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                if (proc.info['exe'] and 
                    ek_python_path in os.path.normcase(proc.info['exe']) and
                    proc.info['pid'] != os.getpid()):
                    processes_to_stop.append(proc)
            except:
                continue
        
        if not processes_to_stop:
            logger.info("✅ No ek processes found that need to be stopped")
            return 0
        
        logger.info(f"Found {len(processes_to_stop)} processes that need to be stopped")
        
        # Force stop all processes
        for proc in processes_to_stop:
            try:
                if proc.is_running():
                    logger.info(f"🔫 Force stopping PID={proc.pid}: {proc.info['cmdline']}")
                    proc.kill()  # Direct kill, no attempt to terminate
                    stopped_count += 1
            except:
                continue
        
        # Additional safety: use system command to confirm again
        if sys.platform == "win32":
            try:
                subprocess.run(['taskkill', '/IM', 'python.exe', '/F'], 
                            capture_output=True, timeout=10)
            except:
                pass
        
        logger.info(f"✅ Force stopped {stopped_count} ek virtual environment processes")
        return stopped_count



    @staticmethod
    def start_test(tc_id: str, cycle_name: str, user_name: str):
        """
        Start test
        """
        # Use enhanced subprocess execution tool to automatically record execution process and results
        return run_con_or_none(
            [ek_com, 'launch', tc_id, cycle_name, f'"{user_name}"'],
            command_name='ek_start',
            capture_output=True,
            text=True,
            timeout=100  # 50 second timeout
        )
    

    @staticmethod
    def test_kill():
        """
        Terminate test
        """
        root_path = PathUtils.get_root_path()

        # Use enhanced subprocess execution tool to automatically record execution process and results
        return run_con_or_none(
            ['cmd', '/c', 'echo', 'y', '|', f'{root_path}/{ek_com}', 'kill', '--all'],
            command_name='ek_kill',
            capture_output=True,
            text=True,
            timeout=100  # 10 second timeout
        )
            