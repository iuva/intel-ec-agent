
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
    """EK结果汇报请求模型"""
    User: str
    Address: str
    Permissions: str

class VncRes(BaseModel):
    """VNC服务状态结果模型"""
    state: int # 0: 成功, 1: 失败
    err_msg: str
    Processes: List[VncInfo]


class VNC:

    @staticmethod
    def is_connecting() -> bool:
        """
        检查是否有 VNC 连接
        """
        logger.debug("是否有vnc连接")
        res = VNC.get_connect_list()
        return res.state == 0 and len(res.Processes) > 0



    @staticmethod
    def get_connect_list(flag: bool = True) -> VncRes:
        """
        调用系统命令 vncserver -list
        获取当前连接的 VNC 会话列表
        """
        
        logger.debug("vnc连接列表")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="未找到 vncserver 可执行文件", Processes=[])

        # 使用增强的子进程执行工具，自动记录执行过程和结果
        output = run_as_admin(
            [vnc_path, '-service', '-getconnections'],
            command_name='vncserver_-getconnections',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
        logger.debug(f"执行结果：{output}{type(output)}")

        # 是否为json格式
        try:
            connections = json.loads(output)
            logger.debug(f"执行结果：{connections}")

            return VncRes(state=0, err_msg="", Processes=connections)
        except Exception as e:
            # 疑似服务没启动
            VNC.start_vncserver()
            if flag:
                return VNC.get_connect_list(False)
            else:
                return VncRes(state=1, err_msg="获取连接列表失败", Processes=[])



    @staticmethod
    def check_vncserver_status(flag: bool = True) -> VncRes:
        """检查 VNC 服务状态"""

        logger.debug("获取vnc服务状态")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="未找到 vncserver 可执行文件", Processes=[])
        
        # 服务是否启动
        
        output = run_as_admin(
            [vnc_path, '-service', '-status'],
            command_name='vncserver_-status',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )

        if 'running' in output:
            return VncRes(state=0, err_msg="", Processes=[])
        else:
            # 尝试启动服务
            VNC.start_vncserver()
            if flag:
                VNC.check_vncserver_status(False)
            else:
                return VncRes(state=1, err_msg="服务未启动", Processes=[])


    # 启动vnc服务
    @staticmethod
    def start_vncserver():
        """
        调用系统命令 vncserver -service -start
        启动 VNC 服务
        """
        logger.debug("启动vnc服务")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="未找到 vncserver 可执行文件", Processes=[])
        
        run_as_admin(
            [vnc_path, '-service', '-start', '-noconsole'],
            command_name='vncserver_-service_-start',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )


    @staticmethod
    def get_vncserver_path() -> str:
        """
        获取 vncserver 可执行文件路径
        """

        realvnc_path = cache.get(REALVNC_CACHE_KEY)
        if not realvnc_path:
            logger.debug("RealVNC 路径未配置，尝试默认路径")

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
        断开所有 vnc 连接
        """
        logger.debug("断开所有 vnc 连接")
        vnc_path = VNC.get_vncserver_path()
        if not vnc_path:
            return VncRes(state=1, err_msg="未找到 vncserver 可执行文件", Processes=[])
        
        run_as_admin(
            [vnc_path, '-service', '-disconnect'],
            command_name='vncserver_-service_-disconnect',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
