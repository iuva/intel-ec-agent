
from ..utils.subprocess_utils import run_as_admin
from ..logger import get_logger
from .global_cache import cache
from .constants import REALVNC_CACHE_KEY
import json
import os
from typing import List
from pydantic import BaseModel


logger = get_logger(__name__)

class VncInfo(BaseModel):
    """EK [result reporting request model]"""
    User: str
    Address: str
    Permissions: str

class VncRes(BaseModel):
    """VNC service [status result model]"""
    state: int # 0: Success, 1: Failure
    err_msg: str
    Processes: List[VncInfo]


class VNC:

    @staticmethod
    def is_connecting() -> bool:
        """
        Check if VNC connection exists
        """
        logger.debug("Check if VNC is connected")
        res = VNC.get_connect_list()
        return res.state == 0 and len(res.Processes) > 0



    @staticmethod
    def get_connect_list(flag: bool = True) -> VncRes:
        """
        Call system command vncserver -list
        Get currently connected VNC session list
        """
        
        logger.debug("VNC connection list")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="vncserver executable file not found", Processes=[])

        # [Use enhanced sub] process execution utility, [automatically records] execution [process and results]
        output = run_as_admin(
            [vnc_path, '-service', '-getconnections'],
            command_name='vncserver_-getconnections',
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )
        logger.debug(f"Execution result: {output}{type(output)}")

        # [Whether it is] JSON [format]
        try:
            connections = json.loads(output)
            logger.debug(f"Execution result: {connections}")

            return VncRes(state=0, err_msg="", Processes=connections)
        except Exception as e:
            # [Suspected] service [not] started
            VNC.start_vncserver()
            if flag:
                return VNC.get_connect_list(False)
            else:
                return VncRes(state=1, err_msg="Failed to get connection list", Processes=[])



    @staticmethod
    def check_vncserver_status(flag: bool = True) -> VncRes:
        """Check VNC service [status]"""

        logger.debug("Get VNC service status")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="vncserver executable file not found", Processes=[])
        
        # Service [whether] started
        
        output = run_as_admin(
            [vnc_path, '-service', '-status'],
            command_name='vncserver_-status',
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )

        if 'running' in output:
            return VncRes(state=0, err_msg="", Processes=[])
        else:
            # Try start service
            VNC.start_vncserver()
            if flag:
                VNC.check_vncserver_status(False)
            else:
                return VncRes(state=1, err_msg="Service not started", Processes=[])


    # Start VNC service
    @staticmethod
    def start_vncserver():
        """
        Call system command vncserver -service -start
        Start VNC service
        """
        logger.debug("Start VNC service")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="vncserver executable file not found", Processes=[])
        
        run_as_admin(
            [vnc_path, '-service', '-start', '-noconsole'],
            command_name='vncserver_-service_-start',
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )


    @staticmethod
    def get_vncserver_path() -> str:
        """
        Get vncserver executable file path
        """

        realvnc_path = cache.get(REALVNC_CACHE_KEY)
        if not realvnc_path:
            logger.debug("RealVNC path not configured, trying default path")

            possible_paths = [
                'C:\\Program Files\\RealVNC\\VNC Server\\vncserver.exe'
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    realvnc_path = path
                    break
            
        return realvnc_path

    @staticmethod
    def disconnect():
        """
        Disconnect all VNC connections
        """
        logger.debug("Disconnect all VNC connections")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="vncserver executable file not found", Processes=[])
        
        run_as_admin(
            [vnc_path, '-service', '-disconnect'],
            command_name='vncserver_-service_-disconnect',
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )
