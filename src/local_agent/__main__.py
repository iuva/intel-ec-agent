#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地代理应用主入口 - 双进程HTTP消息框版本
支持双进程机制：A进程（用户启动）和B进程（系统服务）
"""

import asyncio
import sys
import os
import psutil
import ctypes
import platform
import threading
from pathlib import Path

# 导入增强的子进程工具
from local_agent.utils.subprocess_utils import run_with_logging

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from local_agent.core.application import run_application
from local_agent.logger import get_logger, setup_global_logging, redirect_all_output
from local_agent.ui.message_api import run_message_api_service
from local_agent.ui.system_tray import start_system_tray
from local_agent.core.ek import EK

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
        result = run_with_logging(
            ['sc', 'query', service_name], 
            command_name="check_windows_service",
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
        result = run_with_logging(
            [nssm_path, 'install', service_name, exe_path],
            command_name="nssm_install_service",
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        if result.returncode != 0:
            return False, f"服务安装失败: {result.stderr}"
        
        # 配置服务参数
        run_with_logging([nssm_path, 'set', service_name, 'Description', 'agent - 自动保活'], 
                        command_name="nssm_set_description", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'DisplayName', 'agent'], 
                        command_name="nssm_set_displayname", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'Start', 'SERVICE_AUTO_START'], 
                        command_name="nssm_set_startup", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'AppDirectory', str(working_dir)], 
                        command_name="nssm_set_workingdir", timeout=10)
        
        # 启动服务
        run_with_logging([nssm_path, 'start', service_name], 
                        command_name="nssm_start_service", timeout=10)
        
        return True, "服务安装成功"
        
    except Exception as e:
        return False, f"服务安装异常: {str(e)}"


def auto_register_service():
    """自动注册系统服务"""
    logger = get_logger(__name__)

    exe_path = sys.executable
    if 'python.exe' in exe_path:
        logger.warning("[INFO] 开发环境运行，跳过自动服务注册")
        return False
    
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


def run_a_process():
    """运行A进程（用户启动的进程）"""
    logger = get_logger(__name__)
    logger.info("[INFO] 启动A进程（用户进程）...")
    
    # 启动系统托盘
    tray = start_system_tray("agent")
    
    # 启动FastAPI服务
    async def run_api():
        await run_message_api_service(port=8001)
    
    # 在主事件循环中启动FastAPI服务
    import asyncio
    
    # 创建新的事件循环用于FastAPI服务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 在后台线程中运行FastAPI服务
    def start_fastapi():
        try:
            loop.run_until_complete(run_api())
        except Exception as e:
            logger.error(f"[ERROR] FastAPI服务启动失败: {e}")
    
    api_thread = threading.Thread(target=start_fastapi, daemon=True)
    api_thread.start()
    
    # 等待FastAPI服务启动
    import socket
    import time
    max_retries = 30
    for i in range(max_retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 8001))
            sock.close()
            
            if result == 0:
                logger.info("[INFO] FastAPI服务启动成功，端口8001已就绪")
                break
            else:
                if i == max_retries - 1:
                    logger.error("[ERROR] FastAPI服务启动失败，端口8001未就绪")
                else:
                    time.sleep(0.5)
        except Exception as e:
            logger.warning(f"[WARN] 端口检测失败: {e}")
            time.sleep(0.5)
    
    logger.info("[INFO] A进程启动完成：系统托盘和FastAPI服务已启动")
    logger.info("[INFO] 消息框API服务地址: http://127.0.0.1:8001")
    logger.info("[INFO] A进程将在后台运行，为系统服务提供消息框支持")
    
    # 保持进程运行，但隐藏控制台窗口
    try:
        # 非调试模式下隐藏控制台窗口
        if not any('debug' in arg.lower() for arg in sys.argv) and platform.system() == "Windows":
            hide_console_window()
            logger.info("[INFO] 控制台窗口已隐藏")
        
        # 保持进程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[INFO] A进程收到中断信号，正在退出...")
    except Exception as e:
        logger.error(f"[ERROR] A进程运行异常: {e}")


def run_b_process():
    """运行B进程（系统服务进程）"""
    logger = get_logger(__name__)
    logger.info("[INFO] 启动B进程（系统服务进程）...")
    
    # 运行应用主逻辑
    try:
        # 检测是否为调试模式
        debug_mode = False
        if len(sys.argv) > 1 and sys.argv[1].lower() == 'debug':
            debug_mode = True
        
        logger.info(f"[INFO] 启动应用核心功能... (debug模式: {debug_mode})")
        asyncio.run(run_application(debug=debug_mode))
        
        logger.info("[INFO] B进程已正常退出")
        
    except KeyboardInterrupt:
        logger.info("[INFO] B进程收到中断信号，正在退出...")
    except Exception as e:
        logger.error(f"[ERROR] B进程运行异常: {e}")
        sys.exit(1)


def main():
    """主函数 - 双进程版本"""
    
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='agent')
    parser.add_argument('mode', nargs='?', default='normal', help='运行模式: normal 或 debug')
    args = parser.parse_args()
    
    # 确定是否为debug模式
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
    
    # 多进程检测和修复 - 防止重复启动
    try:
        current_pid = os.getpid()
        existing_processes = []
        
        # 记录当前进程的启动时间
        current_process_start_time = psutil.Process(current_pid).create_time()
        current_process_start_time_with_tolerance = current_process_start_time - 1.0
        
        # 检测其他local_agent进程
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "ppid", "create_time"]):
            try:
                proc_info = proc.info
                proc_pid = proc_info.get("pid")
                proc_name = proc_info.get("name", "") or ""
                proc_exe = proc_info.get("exe", "") or ""
                proc_cmdline = proc_info.get("cmdline", []) or []
                proc_ppid = proc_info.get("ppid")
                proc_create_time = proc_info.get("create_time")
                
                # 跳过当前进程
                if proc_pid == current_pid:
                    continue
                
                # 跳过当前进程的子进程
                if proc_ppid == current_pid:
                    continue
                
                # 跳过在当前进程之后启动的进程
                if proc_create_time and proc_create_time > current_process_start_time_with_tolerance:
                    continue
                
                # 跳过当前进程的父进程
                if proc_pid == os.getppid():
                    continue
                
                # 检查是否为local_agent进程
                is_local_agent_process = False
                
                if proc_name and "local_agent" in proc_name:
                    is_local_agent_process = True
                elif proc_exe and "local_agent" in proc_exe:
                    is_local_agent_process = True
                elif proc_cmdline:
                    cmdline_str = ' '.join(str(arg) for arg in proc_cmdline).lower()
                    if ("local_agent" in cmdline_str and 
                        not "python" in cmdline_str and 
                        ".exe" in cmdline_str and
                        not ".log" in cmdline_str and
                        any(arg.endswith('local_agent.exe') for arg in proc_cmdline if isinstance(arg, str))):
                        is_local_agent_process = True
                
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
                logger.info("[INFO] 当前为服务模式（B进程），允许与A进程共存")
                # B进程（服务模式）可以与A进程共存
            else:
                # A进程（用户模式）需要检查FastAPI服务是否正在运行
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(('127.0.0.1', 8001))
                    sock.close()
                    
                    if result == 0:
                        logger.info("[INFO] 检测到FastAPI服务正在运行（已有A进程在运行），当前A进程将退出")
                        logger.info("[INFO] 提示：系统服务（B进程）将自动启动，无需重复运行")
                        sys.exit(0)
                    else:
                        logger.info("[INFO] FastAPI服务未运行，当前A进程将继续启动服务")
                        
                except Exception as e:
                    logger.warning(f"[WARN] 端口检测失败: {e}")
                    logger.warning("[WARN] 为避免重复启动，当前A进程将退出")
                    sys.exit(0)
        
    except Exception as e:
        logger.warning(f"[WARN] 多进程检测失败: {e}")
    
    try:
        # 检测运行模式
        is_service_mode = check_if_service_mode()
        
        if not is_service_mode:
            logger.info("[INFO] 检测到用户启动模式，启动A进程（用户进程）...")
            
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
                logger.info("[INFO] 系统服务注册成功！")
                logger.info("[INFO] 服务将在系统后台自动运行（B进程）")
                logger.info("[INFO] 当前进程将作为A进程运行，提供消息框支持")
                
            else:
                logger.info("[INFO] 系统服务注册失败或已存在")
                logger.info("[INFO] 当前进程将作为A进程运行，但系统服务可能无法自动启动")
            
            # 无论服务注册是否成功，都启动A进程
            logger.info("[INFO] 启动A进程（用户进程）...")
            run_a_process()
            
        else:
            logger.info("[INFO] 检测到系统服务模式，启动B进程（系统服务进程）...")
            logger.info("[INFO] B进程将运行核心业务逻辑")
            logger.info("[INFO] 消息框功能将通过A进程的FastAPI服务提供")
            
            # 服务模式下运行B进程
            run_b_process()
        
    except KeyboardInterrupt:
        logger.info("[INFO] 收到中断信号，应用正在退出...")
    except Exception as e:
        logger.error("[ERROR] 应用运行异常: " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()