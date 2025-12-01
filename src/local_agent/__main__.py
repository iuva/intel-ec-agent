#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地代理应用主入口 - 增强版
支持自动服务注册和保活机制
"""

import asyncio
import sys
import os
import subprocess
import time
import psutil
import shutil
import ctypes
import platform
from pathlib import Path

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from local_agent.core.application import run_application
from local_agent.logger import get_logger, setup_global_logging, redirect_all_output


# 导入文件工具类
from local_agent.utils.file_utils import FileUtils

def extract_of_scripts(file_name: str, overwrite: bool = False):
    """从scripts 目录解压文件到当前目录（如果需要）
    
    Args:
        file_name: 文件名
        overwrite: 如果文件存在是否覆盖
    """
    return FileUtils.extract_file_from_scripts(file_name, overwrite)


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def check_service_exists(service_name="LocalAgentService"):
    """检查服务是否已存在且运行中"""
    try:
        result = subprocess.run(
            ['sc', 'query', service_name], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        # 不仅要检查服务是否存在，还要检查是否运行中
        if result.returncode == 0:
            # 检查服务状态是否为RUNNING
            return "RUNNING" in result.stdout
        else:
            return False
    except:
        return False


def check_agent_process_running():
    """检查代理进程是否正在运行（增强版：排除系统服务进程）"""
    try:
        import psutil
        current_pid = os.getpid()
        running_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'ppid', 'create_time']):
            try:
                # 安全获取进程信息，处理None值
                proc_info = proc.info
                proc_pid = proc_info.get('pid')
                proc_name = proc_info.get('name', '') or ''
                proc_name = str(proc_name).lower() if proc_name else ''
                proc_ppid = proc_info.get('ppid')  # 父进程ID
                proc_create_time = proc_info.get('create_time')  # 进程启动时间
                
                # 跳过当前进程
                if proc_pid == current_pid:
                    continue
                
                # 检查是否为local_agent进程
                if proc_name and 'local_agent' in proc_name:
                    # 检查是否为系统服务进程（父进程是服务管理器）
                    try:
                        parent_process = psutil.Process(proc_ppid)
                        parent_name = parent_process.name().lower()
                        service_processes = ['services.exe', 'svchost.exe', 'nssm.exe']
                        
                        # 如果是系统服务进程，跳过不计数
                        if any(proc in parent_name for proc in service_processes):
                            continue
                    except:
                        pass
                    
                    # 如果是普通local_agent进程，添加到列表
                    running_processes.append(proc_pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if running_processes:
            logger = get_logger(__name__)
            logger.info(f"[INFO] 检测到{len(running_processes)}个正在运行的local_agent进程 (PIDs: {running_processes})")
            return True
        
        return False
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"[WARN] 检查进程运行时出错: {e}")
        return False


def install_service_via_nssm():
    """使用NSSM安装系统服务"""
    logger = get_logger(__name__)
    
    try:
        # 获取当前exe路径
        exe_path = sys.executable
        working_dir = Path(exe_path).parent
        
        # 首先尝试自动解压nssm.exe
        extract_success, extract_message = extract_of_scripts('nssm.exe')

        # 解压自更新批处理文件
        extract_of_scripts('automatic_update.bat', overwrite=True)
        
        # 查找nssm.exe - 使用相对路径，确保跨平台兼容性
        nssm_path = None
        
        # 优先查找当前目录（解压后的nssm.exe）
        current_nssm = working_dir / 'nssm.exe'
        if current_nssm.exists():
            nssm_path = str(current_nssm)
            logger.info(f"[INFO] 使用当前目录的nssm.exe: {nssm_path}")
        else:
            # 如果当前目录没有，尝试其他位置
            possible_paths = [
                working_dir / 'scripts' / 'nssm.exe',
                working_dir.parent / 'nssm.exe',
                working_dir.parent / 'scripts' / 'nssm.exe',
                Path('C:') / 'Windows' / 'System32' / 'nssm.exe'
            ]
            
            for path in possible_paths:
                if path.exists():
                    nssm_path = str(path)
                    logger.info(f"[INFO] 使用备用路径的nssm.exe: {nssm_path}")
                    break
        
        if not nssm_path:
            return False, "NSSM工具未找到，请确保nssm.exe在scripts目录或系统PATH中"
        
        service_name = "LocalAgentService"
        
        # 安装服务
        result = subprocess.run(
            [nssm_path, 'install', service_name, exe_path],
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        if result.returncode != 0:
            return False, f"服务安装失败: {result.stderr}"
        
        # 配置服务参数
        subprocess.run([nssm_path, 'set', service_name, 'Description', '本地代理服务 - 自动保活'], timeout=10)
        subprocess.run([nssm_path, 'set', service_name, 'DisplayName', '本地代理服务'], timeout=10)
        subprocess.run([nssm_path, 'set', service_name, 'Start', 'SERVICE_AUTO_START'], timeout=10)
        subprocess.run([nssm_path, 'set', service_name, 'AppDirectory', str(working_dir)], timeout=10)
        
        # 启动服务
        subprocess.run([nssm_path, 'start', service_name], timeout=10)
        
        return True, "服务安装成功"
        
    except Exception as e:
        return False, f"服务安装异常: {str(e)}"


def auto_register_service():
    """自动注册系统服务"""
    logger = get_logger(__name__)
    
    if not is_admin():
        logger.warning("[WARN] 未以管理员权限运行，跳过自动服务注册")
        return False
    
    if check_service_exists():
        logger.info("[INFO] 系统服务已存在，无需重复注册")
        return True
    
    logger.info("[INFO] 检测到管理员权限，开始自动注册系统服务...")
    
    success, message = install_service_via_nssm()
    
    if success:
        logger.info("[INFO] " + message)
        logger.info("[INFO] 服务已注册为系统服务，将在系统启动时自动运行")
        return True
    else:
        logger.warning("[WARN] 服务注册失败: " + message)
        logger.info("[INFO] 将以普通模式运行，建议手动运行安装脚本进行服务注册")
        return False


def check_if_service_mode():
    """检查是否以服务模式运行 - 增强版本（修复更新后服务检测问题）"""
    try:
        # 获取logger实例
        logger = get_logger(__name__)
        
        # 关键修复：在更新后场景下，优先检查Windows服务是否实际存在
        # 如果服务已被删除，即使其他检测方法返回True，也应该返回False
        if platform.system() == "Windows":
            try:
                # 检查Windows服务是否实际存在且运行中
                service_exists = check_service_exists()
                if not service_exists:
                    logger.info("[INFO] Windows服务不存在或未运行，强制返回普通模式")
                    return False
            except Exception as e:
                logger.warning(f"[WARN] 检查Windows服务状态失败: {e}")
        
        # 方法1：检查父进程是否为服务管理器（最可靠的检测）
        try:
            parent = psutil.Process(os.getppid())
            parent_name = parent.name().lower()
            service_processes = ['services.exe', 'svchost.exe', 'nssm.exe', 'winlogon.exe']
            
            # 如果父进程是服务管理器，直接认为是服务模式
            if any(proc in parent_name for proc in service_processes):
                logger.info(f"[INFO] 检测到服务管理器父进程: {parent_name}")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        # 方法2：检查系统服务环境变量（服务模式的标准检测）
        if os.environ.get('SERVICE_NAME') == 'local_agent':
            logger.info("[INFO] 检测到系统服务环境变量")
            return True
        
        # 方法3：检查环境变量（自定义服务模式标志）
        service_env = os.environ.get('LOCAL_AGENT_SERVICE_MODE', '')
        if service_env == 'true':
            logger.info("[INFO] 检测到自定义服务模式环境变量")
            return True
            
        # 方法4：检查命令行参数是否包含服务相关标志
        cmdline = ' '.join(sys.argv).lower()
        service_flags = ['--service', '-s', '/service']
        if any(flag in cmdline for flag in service_flags):
            logger.info("[INFO] 检测到服务模式命令行参数")
            return True
        
        # 方法5：检查是否由Windows服务管理器启动
        # 服务模式通常没有可见的控制台窗口
        if platform.system() == "Windows":
            try:
                console_window = ctypes.windll.kernel32.GetConsoleWindow()
                # 如果控制台窗口不可见，且不是由用户交互启动，可能是服务模式
                if console_window and ctypes.windll.user32.IsWindowVisible(console_window) == 0:
                    # 进一步验证：检查是否由服务管理器启动
                    try:
                        parent = psutil.Process(os.getppid())
                        parent_name = parent.name().lower()
                        if any(proc in parent_name for proc in ['services.exe', 'svchost.exe']):
                            logger.info(f"[INFO] 检测到服务模式特征: 隐藏窗口 + 服务管理器父进程")
                            return True
                    except:
                        pass
            except:
                pass
        
        # 方法6：检查当前进程是否由系统服务启动（新增的关键检测）
        # 当系统服务启动进程时，进程的某些特征会不同
        if platform.system() == "Windows":
            try:
                # 检查进程令牌信息，服务进程通常有特定的权限
                import ctypes.wintypes
                
                # 获取当前进程令牌
                token_handle = ctypes.wintypes.HANDLE()
                if ctypes.windll.advapi32.OpenProcessToken(
                    ctypes.windll.kernel32.GetCurrentProcess(), 
                    0x0008,  # TOKEN_QUERY
                    ctypes.byref(token_handle)
                ):
                    # 检查令牌类型
                    token_type = ctypes.wintypes.DWORD()
                    token_type_size = ctypes.wintypes.DWORD()
                    
                    if ctypes.windll.advapi32.GetTokenInformation(
                        token_handle,
                        1,  # TokenType
                        ctypes.byref(token_type),
                        ctypes.sizeof(token_type),
                        ctypes.byref(token_type_size)
                    ):
                        # 如果令牌类型为TokenImpersonation，可能是服务进程
                        if token_type.value == 2:  # TokenImpersonation
                            logger.info("[INFO] 检测到服务进程令牌特征")
                            ctypes.windll.kernel32.CloseHandle(token_handle)
                            return True
                    
                    ctypes.windll.kernel32.CloseHandle(token_handle)
            except:
                pass
        
        # 方法7：检查当前进程是否在服务会话中运行（Windows服务特定会话）
        if platform.system() == "Windows":
            try:
                # 获取当前进程的会话ID
                process_id = ctypes.windll.kernel32.GetCurrentProcessId()
                session_id = ctypes.wintypes.DWORD()
                
                if ctypes.windll.kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
                    # 服务进程通常在会话0中运行（非交互式会话）
                    if session_id.value == 0:
                        logger.info("[INFO] 检测到服务会话特征（会话0）")
                        return True
            except:
                pass
        
        # 方法8：检查是否通过服务控制管理器启动
        # 当进程由SCM启动时，会有特定的启动上下文
        if platform.system() == "Windows":
            try:
                # 检查当前进程是否在服务上下文中运行
                # 通过检查进程是否具有服务特定的安全标识符
                import win32ts  # 需要pywin32
                
                # 获取当前会话信息
                session_id = win32ts.WTSGetActiveConsoleSessionId()
                # 如果当前进程不在控制台会话中，可能是服务进程
                current_session = win32ts.ProcessIdToSessionId(os.getpid())
                if current_session != session_id:
                    logger.info("[INFO] 检测到非控制台会话特征")
                    return True
            except:
                # 如果pywin32不可用，跳过此检测
                pass
        
        # 默认情况下，返回False，确保服务注册逻辑能够正常工作
        # 只有在明确检测到服务模式特征时才返回True
        logger.info("[INFO] 未检测到服务模式特征，将以普通模式运行")
        return False
        
    except Exception as e:
        # 发生异常时，为了安全起见返回False，确保服务注册逻辑能够执行
        logger = get_logger(__name__)
        logger.warning(f"[WARN] 服务模式检测异常: {e}")
        return False


def hide_console_window():
    """隐藏控制台窗口（仅Windows系统）"""
    if platform.system() == "Windows":
        try:
            # 获取控制台窗口句柄
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                # 隐藏窗口
                ctypes.windll.user32.ShowWindow(console_window, 0)  # 0 = SW_HIDE
                return True
        except Exception as e:
            # 隐藏窗口失败不影响程序运行
            pass
    return False

def main():
    """主函数 - 增强版"""
    
    # 解析命令行参数（先解析参数，避免影响多进程检测）
    import argparse
    parser = argparse.ArgumentParser(description='本地代理应用')
    parser.add_argument('mode', nargs='?', default='normal', help='运行模式: normal 或 debug')
    args = parser.parse_args()
    
    # 确定是否为debug模式（安全处理None值）
    debug_mode = False
    if args.mode and hasattr(args.mode, 'lower'):
        debug_mode = args.mode.lower() == 'debug'
    
    # 初始化统一日志系统，传入debug参数
    setup_global_logging(debug=debug_mode)
    redirect_all_output()
    
    logger = get_logger(__name__)
    
    # 非调试模式下隐藏控制台窗口
    if not debug_mode and platform.system() == "Windows":
        if hide_console_window():
            logger.info("[INFO] 控制台窗口已隐藏")
        else:
            logger.info("[INFO] 控制台窗口隐藏失败，继续运行")
    
    # 多进程检测和修复 - 防止重复启动（在日志初始化后执行）
    try:
        current_pid = os.getpid()
        existing_processes = []
        
        # 记录当前进程的启动时间（用于排除新启动的进程）
        # 添加时间容差，解决精度问题
        current_process_start_time = psutil.Process(current_pid).create_time()
        # 添加1秒的容差，避免时间精度问题导致的误判
        current_process_start_time_with_tolerance = current_process_start_time - 1.0
        
        # 第一次检测：立即检测
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "ppid", "create_time"]):
            try:
                # 安全获取进程信息，处理None值
                proc_info = proc.info
                proc_pid = proc_info.get("pid")
                proc_name = proc_info.get("name", "") or ""
                proc_exe = proc_info.get("exe", "") or ""
                proc_cmdline = proc_info.get("cmdline", []) or []
                proc_ppid = proc_info.get("ppid")  # 父进程ID
                proc_create_time = proc_info.get("create_time")  # 进程启动时间
                
                # 跳过当前进程
                if proc_pid == current_pid:
                    continue
                
                # 跳过当前进程的子进程（避免误判）
                if proc_ppid == current_pid:
                    continue
                
                # 跳过在当前进程之后启动的进程（可能是子进程或相关进程）
                # 使用容差时间，避免时间精度问题
                if proc_create_time and proc_create_time > current_process_start_time_with_tolerance:
                    continue
                
                # 跳过当前进程的父进程
                if proc_pid == os.getppid():
                    continue
                
                # 特殊处理：跳过由当前进程启动的EXE进程
                # 当Python脚本启动EXE时，EXE进程的父进程是当前进程的父进程
                # 需要检查进程启动时间和命令行参数来识别这种关系
                if (proc_ppid == os.getppid() and 
                    proc_create_time and proc_create_time >= current_process_start_time and
                    proc_cmdline and any("local_agent" in str(arg) for arg in proc_cmdline)):
                    continue
                
                # 确保字符串类型，避免NoneType错误
                proc_name = str(proc_name).lower() if proc_name else ""
                proc_exe = str(proc_exe).lower() if proc_exe else ""
                
                # 更精确的匹配逻辑：检查进程名称、可执行文件路径和命令行参数
                is_local_agent_process = False
                
                # 检查进程名称（精确匹配）
                if proc_name and "local_agent" in proc_name:
                    # 进一步验证：确保不是其他包含"local_agent"字符串的进程
                    if "local_agent" in proc_name and not any(exclude in proc_name for exclude in ['python', 'editor', 'ide']):
                        is_local_agent_process = True
                
                # 检查可执行文件路径（精确匹配）
                elif proc_exe and "local_agent" in proc_exe:
                    # 进一步验证：确保是可执行文件路径，不是临时文件或缓存文件
                    if proc_exe.endswith('.exe') and 'temp' not in proc_exe.lower() and 'cache' not in proc_exe.lower():
                        is_local_agent_process = True
                
                # 检查命令行参数（最精确的匹配）
                elif proc_cmdline:
                    cmdline_str = ' '.join(str(arg) for arg in proc_cmdline).lower()
                    
                    # 精确匹配条件：
                    # 1. 必须包含local_agent
                    # 2. 不能包含python（避免误判Python解释器）
                    # 3. 必须包含.exe（确保是可执行文件）
                    # 4. 不能包含.log（避免误判日志查看器）
                    # 5. 不能包含test、debug等开发相关关键词
                    # 6. 检查是否在dist目录下运行（打包后的位置）
                    # 7. 关键修复：必须包含完整的可执行文件路径，避免误判
                    if ("local_agent" in cmdline_str and 
                        not "python" in cmdline_str and 
                        ".exe" in cmdline_str and
                        not ".log" in cmdline_str and
                        not any(exclude in cmdline_str for exclude in ['test', 'debug', 'dev', 'ide', 'editor']) and
                        ('dist' in cmdline_str or 'local_agent.exe' in cmdline_str) and
                        # 关键修复：确保是可执行文件路径，而不是其他包含local_agent的文件
                        any(arg.endswith('local_agent.exe') for arg in proc_cmdline if isinstance(arg, str))):
                        is_local_agent_process = True
                
                # 如果是local_agent进程
                if is_local_agent_process:
                    existing_processes.append(proc_pid)
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 如果有其他local_agent进程在运行
        if len(existing_processes) > 0:
            logger.info(f"[INFO] 检测到 {len(existing_processes)} 个其他local_agent进程")
            
            # 检查当前是否以服务模式运行
            is_service_mode = check_if_service_mode()
            
            if is_service_mode:
                logger.info("[INFO] 当前为服务模式，允许与其他进程共存")
                logger.info("[INFO] 这是为了确保服务模式下的稳定运行")
            else:
                # 关键优化：在非服务模式下，检查其他进程是否正在运行FastAPI服务
                # 如果其他进程正在运行服务，则当前进程退出
                # 如果其他进程没有运行服务，则当前进程继续运行
                
                try:
                    # 检查其他进程是否正在运行FastAPI服务（端口8001）
                    import socket
                    
                    # 尝试连接FastAPI端口，如果连接成功说明服务正在运行
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)  # 2秒超时
                    result = sock.connect_ex(('127.0.0.1', 8001))
                    sock.close()
                    
                    if result == 0:
                        logger.info("[INFO] 检测到FastAPI服务正在运行，当前进程将退出")
                        logger.info("[INFO] 这是为了避免端口冲突和资源竞争")
                        sys.exit(0)
                    else:
                        logger.info("[INFO] FastAPI服务未运行，当前进程将继续启动服务")
                        
                except Exception as e:
                    logger.warning(f"[WARN] 端口检测失败: {e}")
                    logger.warning("[WARN] 为避免重复启动，当前进程将退出")
                    sys.exit(0)
        
        # 第二次检测：等待一段时间后再次检测（处理进程启动延迟）
        time.sleep(2)
        existing_processes_second = []
        
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "ppid", "create_time"]):
            try:
                # 安全获取进程信息，处理None值
                proc_info = proc.info
                proc_pid = proc_info.get("pid")
                proc_name = proc_info.get("name", "") or ""
                proc_exe = proc_info.get("exe", "") or ""
                proc_cmdline = proc_info.get("cmdline", []) or []
                proc_ppid = proc_info.get("ppid")  # 父进程ID
                proc_create_time = proc_info.get("create_time")  # 进程启动时间
                
                # 跳过当前进程
                if proc_pid == current_pid:
                    continue
                
                # 跳过当前进程的子进程（避免误判）
                if proc_ppid == current_pid:
                    continue
                
                # 跳过在当前进程之后启动的进程（可能是子进程或相关进程）
                # 使用容差时间，避免时间精度问题
                if proc_create_time and proc_create_time > current_process_start_time_with_tolerance:
                    continue
                
                # 跳过当前进程的父进程
                if proc_pid == os.getppid():
                    continue
                
                # 特殊处理：跳过由当前进程启动的EXE进程
                # 当Python脚本启动EXE时，EXE进程的父进程是当前进程的父进程
                # 需要检查进程启动时间和命令行参数来识别这种关系
                if (proc_ppid == os.getppid() and 
                    proc_create_time and proc_create_time >= current_process_start_time and
                    proc_cmdline and any("local_agent" in str(arg) for arg in proc_cmdline)):
                    continue
                
                # 确保字符串类型，避免NoneType错误
                proc_name = str(proc_name).lower() if proc_name else ""
                proc_exe = str(proc_exe).lower() if proc_exe else ""
                
                # 更精确的匹配逻辑
                is_local_agent_process = False
                
                if proc_name and "local_agent" in proc_name:
                    is_local_agent_process = True
                elif proc_exe and "local_agent" in proc_exe:
                    is_local_agent_process = True
                elif proc_cmdline:
                    cmdline_str = ' '.join(str(arg) for arg in proc_cmdline).lower()
                    # 更精确的匹配：检查是否包含local_agent且不包含python（避免误判Python解释器进程）
                    # 同时检查是否包含.exe扩展名，确保是编译后的可执行文件
                    # 排除包含.log文件路径的情况（避免误判打开日志文件的进程）
                    # 关键修复：确保是可执行文件路径，而不是其他包含local_agent的文件
                    if ("local_agent" in cmdline_str and 
                        not "python" in cmdline_str and 
                        ".exe" in cmdline_str and
                        not ".log" in cmdline_str and
                        # 关键修复：确保是可执行文件路径，而不是其他包含local_agent的文件
                        any(arg.endswith('local_agent.exe') for arg in proc_cmdline if isinstance(arg, str))):
                        is_local_agent_process = True
                
                if is_local_agent_process:
                    existing_processes_second.append(proc_pid)
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 第二次检测：如果发现新进程，根据服务模式决定是否退出
        if len(existing_processes_second) > len(existing_processes):
            logger.info(f"[INFO] 第二次检测发现 {len(existing_processes_second)} 个其他local_agent进程")
            
            # 再次检查服务模式状态
            is_service_mode = check_if_service_mode()
            
            if not is_service_mode:
                logger.warning(f"[WARN] 非服务模式下检测到新增进程，当前进程将退出")
                sys.exit(0)
            else:
                logger.info("[INFO] 服务模式下允许进程共存，继续运行")
            
    except Exception as e:
        logger.warning(f"[WARN] 多进程检测失败: {e}")
        # 即使检测失败，也继续运行程序
    
    try:
        # 检测运行模式
        is_service_mode = check_if_service_mode()
        
        if not is_service_mode:
            logger.info("[INFO] 启动本地代理应用...")
            
            # 无论是否安装服务，都先尝试自动解压nssm.exe
            extract_success, extract_message = extract_of_scripts('nssm.exe')

            # 解压自更新批处理文件
            extract_of_scripts('automatic_update.bat', overwrite=True)
            
            if extract_success:
                logger.info("[INFO] " + extract_message)
            else:
                logger.info("[INFO] " + extract_message)
            
            # 非服务模式下尝试自动注册服务
            service_registered = auto_register_service()
            
            if service_registered:
                logger.info("[INFO] 服务已注册，应用将在后台作为系统服务运行")
                logger.info("[INFO] 您可以关闭此窗口，服务将继续在后台运行")
                
                # 服务注册成功后，当前进程应该退出
                # 让系统服务管理器启动新的服务进程
                logger.info("[INFO] 服务注册成功，当前进程将退出，系统服务将在后台自动启动")
                logger.info("[INFO] 请等待系统服务启动完成...")
                
                # 等待一段时间，确保服务注册信息已写入系统
                time.sleep(3)
                
                # 检查服务是否已启动
                if check_service_exists():
                    logger.info("[INFO] 系统服务已启动，当前进程退出")
                else:
                    logger.info("[INFO] 系统服务注册完成，当前进程退出")
                
                # 关键修复：在退出前设置服务模式环境变量
                # 确保系统服务管理器启动的新进程能够正确识别为服务模式
                os.environ['LOCAL_AGENT_SERVICE_MODE'] = 'true'
                
                # 关键修复：添加明确的退出标志，避免无限循环
                logger.info("[INFO] 设置服务模式环境变量，确保新进程正确识别")
                
                # 正常退出当前进程
                sys.exit(0)
            else:
                logger.info("[INFO] 服务注册失败或已存在，将以普通模式运行...")
        else:
            logger.info("[INFO] 系统服务模式运行中，跳过服务注册检测...")
        
        # 运行应用主逻辑 - 只有在服务注册失败或已处于服务模式时才启动应用
        logger.info(f"[INFO] 启动应用核心功能... (debug模式: {debug_mode})")
        asyncio.run(run_application(debug=debug_mode))
        
        logger.info("[INFO] 本地代理应用已正常退出")
        
    except KeyboardInterrupt:
        logger.info("[INFO] 收到中断信号，应用正在退出...")
    except Exception as e:
        logger.error("[ERROR] 应用运行异常: " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()