"""
    ek 相关封装 - 使用项目统一日志系统记录子进程执行
"""
import shutil
import psutil
import os
from ..utils.subprocess_utils import run_con_or_none, run_as_admin
from ..logger import get_logger
from ..core.global_cache import cache
from ..utils.python_utils import PythonUtils
from local_agent.utils.http_client import http_client
import sys
import subprocess

logger = get_logger(__name__)

ek_base_path = 'ek/Scripts/'
ek_python = ek_base_path + 'python.exe'
ek_com = ek_base_path + 'ek.exe'

class EK:
    """EK 命令封装类 - 自动记录子进程执行日志"""

    @staticmethod
    def env_check():
        """
        检查 ek 是否存在
        """
        # 测试虚拟环境的python 是否可用
        is_python_ok = run_con_or_none(
            [ek_python, '--version'],
            command_name='ek_python_version',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
        
        if is_python_ok:
            logger.error('Execution Kit 虚拟环境python 可用')
            return

        # 尝试删除相对路径的 ek 目录
        if os.path.exists('ek'):
            EK.force_stop_ek_processes()
            shutil.rmtree('ek')

        python = PythonUtils.get_python_executable()

        run_con_or_none(
            [python, '-m', 'venv', 'ek'],
            command_name='ek_version',
            capture_output=True,
            text=True,
            timeout=100  # 10秒超时
        )

    
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
            [ek_com, 'version'],
            command_name='ek_version',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )

    @staticmethod
    def update(url: str):
        """
        更新ek
        """
        update_url = http_client._build_file_url(url)
        if update_url:
            EK.force_stop_ek_processes()
            # 延迟导入以避免循环依赖
            from local_agent.utils.whl_updater import update_from_whl_sync
            resunt = update_from_whl_sync(update_url, ek_python)
            if resunt.get('success', False):
                logger.info('Execution Kit 更新成功')
            else:
                logger.error(f'Execution Kit 更新失败: {resunt.get("error", "未知错误")}')
            return resunt.get('success', False)

    @staticmethod
    def force_stop_ek_processes():
        """强制停止基于ek虚拟环境的所有进程"""
        
        ek_python_path = os.path.abspath(ek_python)
        
        if not os.path.exists(ek_python_path):
            logger.info("ek虚拟环境不存在，无需停止进程")
            return 0
        
        stopped_count = 0
        ek_python_path = os.path.normcase(ek_python_path)
        
        logger.info(f"🚨 强制停止基于ek虚拟环境的所有进程...")
        
        # 收集所有需要停止的进程
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
            logger.info("✅ 没有找到需要停止的ek进程")
            return 0
        
        logger.info(f"找到 {len(processes_to_stop)} 个需要停止的进程")
        
        # 强制停止所有进程
        for proc in processes_to_stop:
            try:
                if proc.is_running():
                    logger.info(f"🔫 强制停止 PID={proc.pid}: {proc.info['cmdline']}")
                    proc.kill()  # 直接kill，不尝试terminate
                    stopped_count += 1
            except:
                continue
        
        # 额外保险：使用系统命令再次确认
        if sys.platform == "win32":
            try:
                subprocess.run(['taskkill', '/IM', 'python.exe', '/F'], 
                            capture_output=True, timeout=10)
            except:
                pass
        
        logger.info(f"✅ 已强制停止 {stopped_count} 个ek虚拟环境进程")
        return stopped_count



    @staticmethod
    def start_test(tc_id: str, cycle_name: str, user_name: str):
        """
        开始测试
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            [ek_com, 'launch', tc_id, cycle_name, f'"{user_name}"'],
            command_name='ek_start',
            capture_output=True,
            text=True,
            timeout=50  # 50秒超时
        )
    

    @staticmethod
    def test_kill():
        """
        终止测试
        """
        # 使用增强的子进程执行工具，自动记录执行过程和结果
        return run_con_or_none(
            ['cmd', '/c', 'echo', 'y', '|', ek_com, 'kill', '--all'],
            command_name='ek_kill',
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
            