#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import winreg
import getpass
import socket 
from dataclasses import dataclass
from typing import Optional  # 添加Optional导入

from ..config import get_config
from ..logger import get_logger
from ..core.global_cache import cache
from .constants import LOCAL_INFO_CACHE_KEY, HARDWARE_INFO_TASK_ID
from .auth import auth_token
from local_agent.core.ek import EK
from local_agent.core.dmr import DMR
from ..utils.version_utils import get_app_version, get_version_info, is_newer_version
from local_agent.utils.http_client import http_get, http_client
from local_agent.utils.environment import Environment
# 延迟导入以避免循环依赖
# from local_agent.utils.whl_updater import update_from_whl_sync
from ..ui.message_proxy import show_message_box
from ..utils.python_utils import PythonUtils  # 导入PythonUtils类
from ..utils.timer_utils import set_timeout


@dataclass
class LocalHostInfo:
    """本地主机信息数据类"""
    mg_id: str
    username: str
    host_ip: str
    
    def to_dict(self):
        """将对象转换为字典，用于JSON序列化"""
        return {
            "mg_id": self.mg_id,
            "username": self.username,
            "host_ip": self.host_ip
        }


class HostInit:
    """主机初始化类"""
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.logger.info("主机初始化开始")


        # python 初始化
        PythonUtils.get_python_check()

        # 获取主机信息并封装到对象中
        # 统一用户名识别机制，避免服务模式下用户名不一致导致的冲突
        username = self._get_unified_username()
        
        local_info = LocalHostInfo(
            mg_id=self.get_machine_guid(),
            username=username,
            host_ip=self.get_ip_address()
        )
        
        # 将主机信息存入缓存
        cache.set(LOCAL_INFO_CACHE_KEY, local_info)

        # 版本核验，仅exe 运行时检查
        # if not Environment.is_development():
        self.check_versions()

        # 获取硬件信息
        # self.get_hardware_info()


    def get_hardware_info(self):
        """
        获取硬件信息, 如果15分钟还没有收到硬件信息，则自动重新调用
        """
        self.logger.info("获取硬件信息")
        DMR.get_hardware_info()
        # 添加定时任务，15分钟后再次执行
        task_id = set_timeout(60, self.get_hardware_info)
        # 缓存定时任务id
        cache.set(HARDWARE_INFO_TASK_ID, task_id)

        

    def check_versions(self):
        """
        检查 ek 和 kw 版本
        """
        # 获取软件当前版本
        current_version = get_app_version(False)
        
        self.logger.info(f"当前软件版本: {current_version}")

        # 从服务端查取最新版本信息
        versionInfo = None


        while True:
            try:
                res = http_get(url="/host/agent/ota/latest")

                res_data = res.get('data', {})
                code = res_data.get('code', 0)

                self.logger.info(f"版本信息获取结果：{res_data}")
                if code != 200:

                    result = show_message_box(
                        msg=f"从服务器获取最新可用版本失败，请检查网络环境后点击“确认”重试！",
                        title="Python环境初始化失败",
                        buttons=["确认"]
                    )


                    self.logger.info("用户选择重试，重新获取版本信息")
                    continue
                else:
                    arr = res_data.get('data')

                    versionInfo = {item['conf_name']: item for item in arr}
                    break
            
            except Exception as e:
                self.logger.error(f"获取版本信息发送异常: {e}")
                result = show_message_box(
                    msg=f"从服务器获取最新可用版本失败，请检查网络环境后点击“确认”重试！",
                    title="Python环境初始化失败",
                    buttons=["确认"]
                )

                self.logger.info("用户选择重试，重新获取版本信息")
                continue

        self.logger.info(f"最新版本信息: {versionInfo}")

        # 判断当前软件版本是否最新
        agentVersion = versionInfo.get('agent')

        # 检查agentVersion是否为None
        if agentVersion and agentVersion.get('conf_ver'):

            # 检查是否在10分钟内有更新失败记录，防止无限循环
            import time
            from local_agent.core.persistent_storage import get_persistent_data, set_persistent_data
            
            # 获取上次更新失败时间
            last_update_failure_time = get_persistent_data('last_update_failure_time', 'update_status', 0)
            
            if last_update_failure_time > 0:
                self.logger.info(f"上次更新失败时间: {time.ctime(last_update_failure_time)}")

            # 计算时间差（秒）
            current_time = time.time()
            time_diff = current_time - last_update_failure_time
            
            # 如果10分钟内有更新失败记录，则不进行更新
            if last_update_failure_time == 0 or time_diff > 600:
                # 版本比对
                agent_is_new = is_newer_version(agentVersion.get('conf_ver'), current_version)

                if agent_is_new:
                    self.logger.info('agent 需要更新')
                    
                    try:
                        # 延迟导入以避免循环依赖
                        from local_agent.auto_update.auto_updater import AutoUpdater
                        updater = AutoUpdater()
                        # 异步执行更新操作
                        result = updater.perform_update_sync(
                            'dc74e9c67a8bb6561cfb3efb9fdb55f3',
                            # expected_md5=agentVersion.get('conf_md5'),
                            download_url=agentVersion.get('conf_url')
                        )

                        # 如果程序走到了这里，说明更新脚本并没有杀死当前进程，更新操作失败
                        if not result.get('success', False):
                            # 对更新失败的结果进行持久化存储
                            error_message = result.get('error', '未知错误')
                            self.logger.error(f"更新失败: {error_message}")
                            
                            # 存储更新失败时间
                            set_persistent_data('last_update_failure_time', current_time, 'update_status')
                            set_persistent_data('last_update_error', error_message, 'update_status')
                            self.logger.info(f"已记录更新失败时间: {current_time}")
                        
                    except Exception as e:
                        self.logger.error(f"更新操作异常: {e}")
                        current_time = time.time()
                        set_persistent_data('last_update_failure_time', current_time, 'update_status')
                        set_persistent_data('last_update_error', str(e), 'update_status')
                        self.logger.info(f"已记录更新异常时间: {current_time}")


        # ek 是否需要更新
        ekVersion = versionInfo.get('ek')
        if ekVersion:
            ek_is_new = is_newer_version(ekVersion.get('conf_ver'), EK.version())
            if ek_is_new:
                self.logger.info('Execution Kit 需要更新')
                update_url = http_client._build_file_url(ekVersion.get('conf_url'))
                # 延迟导入以避免循环依赖
                from local_agent.utils.whl_updater import update_from_whl_sync
                resunt = update_from_whl_sync(update_url)
                if resunt.get('success', False):
                    self.logger.info('Execution Kit 更新成功')
                else:
                    self.logger.error(f'Execution Kit 更新失败: {resunt.get("error", "未知错误")}')
        else:
            self.logger.warning('无法获取Execution Kit版本信息')

        # dmr 是否需要更新
        dmrVersion = versionInfo.get('dmr_config')
        if dmrVersion:
            dmr_is_new = is_newer_version(dmrVersion.get('conf_ver'), DMR.version())
            if dmr_is_new:
                self.logger.info('dmr_config 需要更新')
                update_url = http_client._build_file_url(dmrVersion.get('conf_url'))
                # 延迟导入以避免循环依赖
                from local_agent.utils.whl_updater import update_from_whl_sync
                resunt = update_from_whl_sync(update_url)
                if resunt.get('success', False):
                    self.logger.info('dmr_config 更新成功')
                else:
                    self.logger.error(f'dmr_config 更新失败: {resunt.get("error", "未知错误")}')
        else:
            self.logger.warning('无法获取dmr_config版本信息')





    

    """
    获取主机环境 - Windows兼容版本
    """
    def get_ip_address(self):
        """获取本机IPv4地址"""
        try:
            # 创建socket连接来确定本机IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # 连接到一个公共IP地址和端口，不需要实际连接成功
            # 这只是为了让操作系统选择合适的网络接口
            s.connect(('8.8.8.8', 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except Exception as e:
            self.logger.error(f"获取IP地址失败: {str(e)}")
            # 如果无法确定，返回本地回环地址
            return '127.0.0.1'

    
    """
    获取主机唯一id
    """
    def _get_unified_username(self):
        """统一用户名识别机制，避免服务模式下用户名不一致导致的冲突"""
        try:
            # 方法1：检查是否以服务模式运行
            import os
            import sys
            
            # 检查环境变量和命令行参数判断服务模式
            service_env = os.environ.get('LOCAL_AGENT_SERVICE_MODE', '')
            cmdline = ' '.join(sys.argv).lower()
            service_flags = ['--service', '-s', '/service']
            
            is_service_mode = service_env == 'true' or any(flag in cmdline for flag in service_flags)
            
            if is_service_mode:
                # 服务模式下使用固定的用户名，避免冲突
                # 使用计算机名作为统一标识
                import socket
                computer_name = socket.gethostname()
                return f"{computer_name}$"  # 添加$符号表示系统账户
            else:
                # 非服务模式下使用当前登录用户名
                import getpass
                return getpass.getuser()
                
        except Exception as e:
            self.logger.error(f"统一用户名识别失败: {e}")
            # 失败时回退到默认方法
            import getpass
            return getpass.getuser()

    def get_machine_guid(self):
        """
        获取 Windows 系统的 MachineGuid。
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
            return "N/A (Error reading file)" #为了配合之前的输出
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            return None


