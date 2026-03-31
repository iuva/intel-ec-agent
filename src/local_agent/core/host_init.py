#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import winreg
import socket 
from dataclasses import dataclass

from ..config import get_config
from ..logger import get_logger
from ..core.global_cache import cache, set_agent_status, get_agent_status_by_key, set_init_config, get_init_config
from .constants import LOCAL_INFO_CACHE_KEY, HARDWARE_INFO_TASK_ID, HARDWARE_INFO_CYCLE_TASK_ID
from .ek import EK
from .dmr import DMR
from ..utils.version_utils import get_app_version, is_newer_version
from local_agent.utils.http_client import http_get, http_client, http_post
from ..utils.environment import Environment
from ..core.auth import update_token

# Delay import to avoid loop dependency
# from local_agent.utils.whl_updater import update_from_whl_sync
from ..utils.message_tool import show_message_box
from ..utils.python_utils import PythonUtils  # Import PythonUtils class
from ..utils.timer_utils import set_timeout, clear_timeout, set_interval
from .vnc import VNC
from .app_update import report_version
from .tray_api import get_username


@dataclass
class LocalHostInfo:
    """Local host info data class"""
    mg_id: str
    username: str
    host_ip: str
    
    def to_dict(self):
        """Convert object to dictionary for JSON serialization"""
        return {
            "mg_id": self.mg_id,
            "username": self.username,
            "host_ip": self.host_ip
        }


class HostInit:
    """Host initialization class"""
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.logger.info("Host initialization starting")

        # TryStart VNC Service
        vnc_res = VNC.start_vncserver()
        while vnc_res.state != 0:
            show_message_box(
                msg=f"VNC service start failed: {vnc_res.err_msg}",
                title="Initialization failed",
                confirm_text="Retry"
            )
            vnc_res = VNC.start_vncserver()
            

        # python Initialize
        PythonUtils.get_python_check()

        # Wait for message API service to be healthy (HTTP 200 response)
        import time
        import requests
        
        message_api_url = self.config.get('message_api_url') + "/health"
        
        while True:
            try:
                response = requests.get(message_api_url, timeout=5)
                if response.status_code == 200:
                    self.logger.info("Message API service is healthy, continuing...")
                    break
                else:
                    self.logger.warning(f"Message API service returned status {response.status_code}, waiting...")
            except Exception as e:
                self.logger.warning(f"Message API service not available: {e}, waiting...")
            
            # Wait 30 seconds before next check
            time.sleep(30)

        # Get host info and encapsulate into object
        # Unified username identification mechanism to avoid conflicts caused by inconsistent usernames in service mode
        username = get_username()
        
        local_info = LocalHostInfo(
            mg_id=self.get_machine_guid(),
            username=username,
            host_ip=self.get_ip_address()
        )
        
        # Store host info in cache
        cache.set(LOCAL_INFO_CACHE_KEY, local_info)

        # Update token every 23.8 hours
        set_interval(23.8 * 60 * 60, update_token)

        self.init_config()

        # Version verification, only check when running as exe
        # if not Environment.is_development():
        self.check_versions()

        # Timed get hardware info
        self.timing_hardware_info(start=True)

        
        # res = http_post(url="/host/agent/hardware/report", data = {'name': 'dmr_config_schema', 'type': '0', 'dmr_config': {'revision': '0.1.1', 'mainboard': {'plt_meta_data': {'platform': 'OKS_DMR', 'label_plt_cfg': None}, 'board': {'board_meta_data': {'board_name': 'JohnsonCity1SPCRP', 'uxi_topology': '1S', 'host_name': None, 'host_ip': None}, 'baseboard': [], 'lsio': {'usb_disc_installed': False, 'network_installed': False, 'nvme_installed': False, 'keyboard_installed': False, 'mouse_installed': False}, 'peripheral': {'itp_installed': False, 'usb_dbc_installed': False, 'controlbox_installed': False, 'flash_programmer_installed': False, 'display_installed': False, 'jumpers': []}}, 'misc': {'installed_os': [], 'bmc_version': None, 'bmc_ip': None, 'cpld_version': None}}, 'hsio': [{'hsio': {'hsio_meta_data': {'cxl_por': 'unknown', 'cxl_installed_num': 0, 'cxl_installed_tpye': None, 'cxl_mixed_device_type': False, 'cxl_switch': 'unknown', 'didvid_list': []}, 'slot': []}}], 'memory': [{'memory': {'memory_meta_data': {'dimm_type': 'RDIMM', 'platform_type': 'GNRSP', 'memory_por_id': {'value': 'Unknown Config'}, 'total_memory_size': {'value': 0}, 'mixed_dimm': {'is_mixed': True, 'common_info': '', 'special_info': ''}}, 'channel': []}}], 'security': {'security': {'Tpm': [], 'CoinBattery': []}}, 'soc': [{'soc': {'meta_data': {'soc_name': {'value': None}, 'soc_id': None, 'cpu_id': None, 'chop_type': 'UCC', 'stepping': None, 'qdf': None}, 'soc_feature': {'sgx': None, 'mktme': False, 'tdx': False, 'vab': False, 'cpu_attestation': False, 'mini_dpe': False, 'sstpp': False, 'ras_level': None, 'memory_channel': None, 'ddr5_freq': None, 'mrdimm_freq': None}, 'comp_die': [], 'io_die': []}}]}})
        
        # from ..utils.websocket_sync_utils import start_websocket_sync
        # start_websocket_sync(True)

    def init_config(self):
        """
        Initialize configuration
        """
        init_res = http_get(url="/host/agent/init")
        init_data = init_res.get('data', {})
        init_code = init_data.get('code', 0)

        config_data = {}
        if str(init_code) == '200':
            conf_data = init_data.get('data', {})
            configs = conf_data.get('configs', [])
            for config in configs:
                key = config.get('conf_key', '')
                config_data[key] = config
        
        self.logger.info(f"Initialize config: {config_data}")

        # Cache initialize config
        set_init_config(config_data)



    def get_hardware_info(self):
        """
        Get hardware information, if no hardware information is received within 15 minutes, automatically call again
        """
        self.logger.info("Obtained hardware info")
        
        # If not in test, prioritize stopping websocket to ensure no test execution during hardware info retrieval
        if not get_agent_status_by_key('test'):
            from ..utils.websocket_sync_utils import stop_websocket_sync
            stop_websocket_sync()
            
            set_agent_status(sut=True)
            if not DMR.is_running():
                import time
                DMR.kill_dmr()
                time.sleep(10)
                
                while not DMR.get_hardware_info():
                    show_message_box(
                        msg=f"The dmr config program was not found. Please install it manually and try again",
                        title="Initialization failed",
                        confirm_text="Retry"
                    )

                self.logger.info("Obtained hardware info - call completed")

        old_task_id = cache.get(HARDWARE_INFO_TASK_ID)

        # Add timed task, execute again after 15 minutes
        task_id = set_timeout(30, self.get_hardware_info)
        # Cache timed task id
        cache.set(HARDWARE_INFO_TASK_ID, task_id)

        if old_task_id:
            clear_timeout(old_task_id)


    def timing_hardware_info(self, start=False):
        """
        Timed hardware information retrieval
        """

        # Check version when not starting
        if not start:
            self.check_versions()

        # Get hardware info
        self.get_hardware_info()
        
        self.init_config()

        init_config = get_init_config()
        hardware_info_cycle = init_config.get('agent_init_hw', {})
        cycle_second = int(hardware_info_cycle.get('conf_val', 24 * 60))

        if cycle_second < 3 * 60:
            cycle_second = 3 * 60

        # Execute again at 00:00 every day
        task_id = set_timeout(cycle_second * 60, self.timing_hardware_info)
        # Cache timed task id
        cache.set(HARDWARE_INFO_CYCLE_TASK_ID, task_id)


    def check_versions(self):
        """
        Check ek and kw versions
        """
        # Get current software version
        current_version = get_app_version(False)
        
        self.logger.info(f"Current software version: {current_version}")

        # Get latest version info from service
        versionInfo = None


        while True:
            try:
                res = http_get(url="/host/agent/ota/latest")

                res_data = res.get('data', {})
                code = res_data.get('code', 0)

                self.logger.info(f"Version info obtained result: {res_data}")
                if code != 200:

                    result = show_message_box(
                        msg=f"Failed to retrieve the latest available version from the server!",
                        title="Network anomaly",
                        confirm_text="Retry"
                    )


                    self.logger.info("User chose to retry, re-obtaining version info")
                    continue
                else:
                    arr = res_data.get('data')

                    versionInfo = {item['conf_name']: item for item in arr}
                    break
            
            except Exception as e:
                self.logger.error(f"Obtained version info exception: {e}")
                result = show_message_box(
                    msg=f"Failed to retrieve the latest available version from the server!",
                    title="Network anomaly",
                    confirm_text="Retry"
                )

                self.logger.info("User chose to retry, re-obtaining version info")
                continue

        self.logger.info(f"Latest version info: {versionInfo}")

        # Check if current software version is the latest
        agentVersion = versionInfo.get('agent')

        # Check if agent version is not None
        if agentVersion and agentVersion.get('conf_ver'):

            # Check if there are update failure records within 10 minutes to prevent infinite loop
            import time
            from local_agent.core.persistent_storage import get_persistent_data, set_persistent_data
            
            # Get last update failure time
            last_update_failure_time = get_persistent_data('last_update_failure_time', 'update_status', 0)
            
            if last_update_failure_time > 0:
                self.logger.info(f"Last update failure time: {time.ctime(last_update_failure_time)}")
                report_version('agent', agentVersion.get('conf_ver'), 3)

            # Calculate time difference (seconds)
            current_time = time.time()
            time_diff = current_time - last_update_failure_time
            
            # If there are update failure records within 10 minutes, do not proceed with update
            if last_update_failure_time == 0 or time_diff > 600:
                # Version comparison
                agent_new_ver = agentVersion.get('conf_ver')
                agent_is_new = is_newer_version(agent_new_ver, current_version)

                if agent_is_new:
                    self.logger.info('Agent needs update')
                    report_version('agent', agent_new_ver, 1)
                    
                    try:
                        # Execute update operation asynchronously

                        from local_agent.auto_update.auto_updater import AutoUpdater
                        updater = AutoUpdater()
                        # Execute update operation asynchronously
                        result = updater.perform_update_sync(
                            expected_md5=agentVersion.get('conf_md5'),
                            download_url=agentVersion.get('conf_url')
                        )

                        # If the program reaches here, it means the update script didn't kill the current process, update operation failed
                        if not result.get('success', False):
                            # Persist update failure result
                            error_message = result.get('error', 'Unknown error')
                            self.logger.error(f"Update failed: {error_message}")
                            
                            # Store update failure time
                            set_persistent_data('last_update_failure_time', current_time, 'update_status')
                            set_persistent_data('last_update_error', error_message, 'update_status')
                            self.logger.info(f"Recorded update failure time: {current_time}")
                            report_version('agent', agent_new_ver, 3)
                        
                    except Exception as e:
                        self.logger.error(f"Update operation exception: {e}")
                        current_time = time.time()
                        set_persistent_data('last_update_failure_time', current_time, 'update_status')
                        set_persistent_data('last_update_error', str(e), 'update_status')
                        self.logger.info(f"Recorded update exception time: {current_time}")
                        report_version('agent', agent_new_ver, 3)
                else:
                    report_version('agent', current_version, 2)

        # Check if EK needs update
        ekVersion = versionInfo.get('ek')
        EK.env_check()
        if ekVersion:
            ek_new_version = ekVersion.get('conf_ver')
            ek_is_new = is_newer_version(ek_new_version, EK.version())
            if ek_is_new:
                self.logger.info('Execution Kit needs update')
                report_version('ek', ek_new_version, 1)
                EK.update(ekVersion.get('conf_url', None))

                # Check if update succeeded by comparing versions again
                res = is_newer_version(ek_new_version, EK.version())

                if res:
                    report_version('ek', ek_new_version, 3)
                else:
                    report_version('ek', ek_new_version, 2)
                    
        else:
            self.logger.warning('Unable to obtain Execution Kit version info')

        # Check if DMR needs update
        dmrVersion = versionInfo.get('dmr_config')
        if dmrVersion:
            dmr_new_version = dmrVersion.get('conf_ver')
            dmr_is_new = is_newer_version(dmr_new_version, DMR.version())
            if dmr_is_new:
                self.logger.info('dmr_config needs update')
                report_version('dmr_config', dmr_new_version, 1)
                DMR.update(dmrVersion.get('conf_url', None))
                # Check if update succeeded by comparing versions again
                res = is_newer_version(dmr_new_version, DMR.version())

                if res:
                    report_version('dmr_config', dmr_new_version, 3)
                else:
                    report_version('dmr_config', dmr_new_version, 2)
        else:
            self.logger.warning('Unable to obtain dmr_config version info')


    """
    Get host environment - Windows compatible version
    """
    def get_ip_address(self):
        """Get local IPv4 address"""
        try:
            # Create socket connection to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public IP address and port, no actual connection needed
            # This just helps the system select the appropriate network interface
            s.connect(('8.8.8.8', 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except Exception as e:
            self.logger.error(f"Obtain IP address failed: {str(e)}")
            # If unable to determine, return local loopback address
            return '127.0.0.1'

    


    def get_machine_guid(self):
        """
        Get MachineGuid from Windows system.
        """
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    "SOFTWARE\\Microsoft\\Cryptography",
                                    0, winreg.KEY_READ)
            try:
                value, regtype = winreg.QueryValueEx(key, "MachineGuid")
                return value
            finally:
                winreg.CloseKey(key)

        except FileNotFoundError:
            self.logger.error("MachineGuid not found in registry.")
            return None
        except PermissionError:
            self.logger.error("Permission denied accessing registry. Try running as administrator.")
            return "N/A (Error reading file)" # To match previous output
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            return None


