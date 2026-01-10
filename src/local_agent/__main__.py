#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local agent application main entry - Dual-process HTTP message box version
Supports dual-process mechanism: Process A (user started) and Process B (system service)
"""

import asyncio
import sys
import os
import psutil
import ctypes
import platform
import threading
from pathlib import Path

# Import enhanced subprocess utility
from local_agent.utils.subprocess_utils import run_with_logging

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from local_agent.core.application import run_application
from local_agent.logger import get_logger, setup_global_logging, redirect_all_output
from local_agent.ui.message_api import run_message_api_service
from local_agent.ui.system_tray import start_system_tray
from local_agent.core.ek import EK

# Import file utility class
from local_agent.utils.file_utils import FileUtils


def extract_of_scripts(file_name: str, overwrite: bool = False):
    """Extract file from scripts directory to current directory (if needed)
    
    Args:
        file_name: File name
        overwrite: Whether to overwrite if file exists
    """
    return FileUtils.extract_file_from_scripts(file_name, overwrite)


def is_admin():
    """Check if running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def check_service_exists(service_name="LocalAgentService"):
    """Check if service exists and is running"""
    try:
        result = run_with_logging(
            ['sc', 'query', service_name], 
            command_name="check_windows_service",
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        # Not only check if service exists, but also check if it's running
        if result.returncode == 0:
            # Check if service status is RUNNING
            return "RUNNING" in result.stdout
        else:
            return False
    except:
        return False


def check_agent_process_running():
    """Check if agent process is running (enhanced version: exclude system service processes)"""
    try:
        import psutil
        current_pid = os.getpid()
        running_processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'ppid', 'create_time']):
            try:
                # Safely get process info, handle None values
                proc_info = proc.info
                proc_pid = proc_info.get('pid')
                proc_name = proc_info.get('name', '') or ''
                proc_name = str(proc_name).lower() if proc_name else ''
                proc_ppid = proc_info.get('ppid')  # Parent process ID
                proc_create_time = proc_info.get('create_time')  # Process start time
                
                # Skip current process
                if proc_pid == current_pid:
                    continue
                
                # Check if it's a local_agent process
                if proc_name and 'local_agent' in proc_name:
                    # Check if it's a system service process (parent process is service manager)
                    try:
                        parent_process = psutil.Process(proc_ppid)
                        parent_name = parent_process.name().lower()
                        service_processes = ['services.exe', 'svchost.exe', 'nssm.exe']
                        
                        # If it's a system service process, skip counting
                        if any(proc in parent_name for proc in service_processes):
                            continue
                    except:
                        pass
                    
                    # If it's a normal local_agent process, add to list
                    running_processes.append(proc_pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if running_processes:
            logger = get_logger(__name__)
            logger.info(f"[INFO] Detected {len(running_processes)} running local_agent processes (PIDs: {running_processes})")
            return True
        
        return False
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"[WARN] Error occurred while checking processes: {e}")
        return False


def install_service_via_nssm():
    """Install system service using NSSM"""
    logger = get_logger(__name__)
    
    try:
        # Get current executable path
        exe_path = sys.executable
        working_dir = Path(exe_path).parent
        
        # First try to automatically extract nssm.exe
        extract_success, extract_message = extract_of_scripts('nssm.exe')

        # Extract automatic update batch file
        extract_of_scripts('automatic_update.bat', overwrite=True)
        
        # Find nssm.exe - use relative path to ensure cross-platform compatibility
        nssm_path = None
        
        # Priority: search current directory (extracted nssm.exe)
        current_nssm = working_dir / 'nssm.exe'
        if current_nssm.exists():
            nssm_path = str(current_nssm)
            logger.info(f"[INFO] Using nssm.exe from current directory: {nssm_path}")
        else:
            # If current directory doesn't have it, try other locations
            possible_paths = [
                working_dir / 'scripts' / 'nssm.exe',
                working_dir.parent / 'nssm.exe',
                working_dir.parent / 'scripts' / 'nssm.exe',
                Path('C:') / 'Windows' / 'System32' / 'nssm.exe'
            ]
            
            for path in possible_paths:
                if path.exists():
                    nssm_path = str(path)
                    logger.info(f"[INFO] Using nssm.exe from alternative path: {nssm_path}")
                    break
        
        if not nssm_path:
            return False, "NSSM tool not found, please ensure that nssm.exe is in the scripts directory or system PATH"
        
        service_name = "LocalAgentService"
        
        # Install service
        result = run_with_logging(
            [nssm_path, 'install', service_name, exe_path],
            command_name="nssm_install_service",
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        if result.returncode != 0:
            return False, f"Service installation failed: {result.stderr}"
        
        # Configure service parameters
        run_with_logging([nssm_path, 'set', service_name, 'Description', 'agent - automatic keep-alive'], 
                        command_name="nssm_set_description", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'DisplayName', 'agent'], 
                        command_name="nssm_set_displayname", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'Start', 'SERVICE_AUTO_START'], 
                        command_name="nssm_set_startup", timeout=10)
        run_with_logging([nssm_path, 'set', service_name, 'AppDirectory', str(working_dir)], 
                        command_name="nssm_set_workingdir", timeout=10)
        
        # Start service
        run_with_logging([nssm_path, 'start', service_name], 
                        command_name="nssm_start_service", timeout=10)
        
        return True, "Service installation successful"
        
    except Exception as e:
        return False, f"Service installation exception: {str(e)}"


def auto_register_service():
    """Automatically register system service"""
    logger = get_logger(__name__)

    exe_path = sys.executable
    if 'python.exe' in exe_path:
        logger.warning("[INFO] Running in development environment, skipping automatic service registration")
        return False
    
    if not is_admin():
        logger.warning("[WARN] Not running with administrator privileges, skipping automatic service registration")
        return False
    
    if check_service_exists():
        logger.info("[INFO] System service already exists, no need to register again")
        return True
    
    logger.info("[INFO] Detected administrator privileges, starting automatic system service registration...")
    
    success, message = install_service_via_nssm()
    
    if success:
        logger.info("[INFO] " + message)
        logger.info("[INFO] Service registered as system service, will run automatically on system startup")
        return True
    else:
        logger.warning("[WARN] Service registration failed: " + message)
        logger.info("[INFO] Will run in normal mode, recommend running installation script manually for service registration")
        return False


def check_if_service_mode():
    """Check if running in service mode - enhanced version (fixes service detection issues after update)"""
    try:
        # Get logger instance
        logger = get_logger(__name__)
        
        # Critical fix: In post-update scenarios, prioritize checking if Windows service actually exists
        # If service has been deleted, even if other detection methods return True, should return False
        if platform.system() == "Windows":
            try:
                # Check if Windows service actually exists and is running
                service_exists = check_service_exists()
                if not service_exists:
                    logger.info("[INFO] Windows service does not exist or is not running, forcing return to normal mode")
                    return False
            except Exception as e:
                logger.warning(f"[WARN] Checking Windows service status failed: {e}")
        
        # Method 1: Check if parent process is service manager (most reliable detection)
        try:
            parent = psutil.Process(os.getppid())
            parent_name = parent.name().lower()
            service_processes = ['services.exe', 'svchost.exe', 'nssm.exe', 'winlogon.exe']
            
            # If parent process is service manager, directly consider it as service mode
            if any(proc in parent_name for proc in service_processes):
                logger.info(f"[INFO] Detected service manager parent process: {parent_name}")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        # Method 2: Check system service environment variable (standard service mode detection)
        if os.environ.get('SERVICE_NAME') == 'local_agent':
            logger.info("[INFO] Detected system service environment variable")
            return True
        
        # Method 3: Check environment variable (custom service mode flag)
        service_env = os.environ.get('LOCAL_AGENT_SERVICE_MODE', '')
        if service_env == 'true':
            logger.info("[INFO] Detected custom service mode environment variable")
            return True
            
        # Method 4: Check if command line parameters contain service-related flags
        cmdline = ' '.join(sys.argv).lower()
        service_flags = ['--service', '-s', '/service']
        if any(flag in cmdline for flag in service_flags):
            logger.info("[INFO] Detected service mode command line parameter")
            return True
        
        # Method 5: Check if started by Windows service manager
        # Service mode typically has no visible console window
        if platform.system() == "Windows":
            try:
                console_window = ctypes.windll.kernel32.GetConsoleWindow()
                # If console window is invisible and not started by user interaction, may be service mode
                if console_window and ctypes.windll.user32.IsWindowVisible(console_window) == 0:
                    # Further validate: check if started by service manager
                    try:
                        parent = psutil.Process(os.getppid())
                        parent_name = parent.name().lower()
                        if any(proc in parent_name for proc in ['services.exe', 'svchost.exe']):
                            logger.info(f"[INFO] Detected service mode feature: hidden window + service manager parent process")
                            return True
                    except:
                        pass
            except:
                pass
        
        # Method 6: Check if current process was started by system service (new key detection)
        # When system service starts process, some characteristics of the process will be different
        if platform.system() == "Windows":
            try:
                # Check process token info, service processes typically have specific permissions
                import ctypes.wintypes
                
                # Get current process token
                token_handle = ctypes.wintypes.HANDLE()
                if ctypes.windll.advapi32.OpenProcessToken(
                    ctypes.windll.kernel32.GetCurrentProcess(), 
                    0x0008,  # TOKEN_QUERY
                    ctypes.byref(token_handle)
                ):
                    # Check token type
                    token_type = ctypes.wintypes.DWORD()
                    token_type_size = ctypes.wintypes.DWORD()
                    
                    if ctypes.windll.advapi32.GetTokenInformation(
                        token_handle,
                        1,  # TokenType
                        ctypes.byref(token_type),
                        ctypes.sizeof(token_type),
                        ctypes.byref(token_type_size)
                    ):
                        # If token type is TokenImpersonation, may be service process
                        if token_type.value == 2:  # TokenImpersonation
                            logger.info("[INFO] Detected service process token feature")
                            ctypes.windll.kernel32.CloseHandle(token_handle)
                            return True
                    
                    ctypes.windll.kernel32.CloseHandle(token_handle)
            except:
                pass
        
        # Method 7: Check if current process is running in service session (Windows service specific session)
        if platform.system() == "Windows":
            try:
                # Get current process session ID
                process_id = ctypes.windll.kernel32.GetCurrentProcessId()
                session_id = ctypes.wintypes.DWORD()
                
                if ctypes.windll.kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
                    # Service processes typically run in Session 0 (non-interactive session)
                    if session_id.value == 0:
                        logger.info("[INFO] Detected service session feature (session 0)")
                        return True
            except:
                pass
        
        # Method 8: Check if started through service control manager
        # When process is started by SCM, there will be specific startup context
        if platform.system() == "Windows":
            try:
                # Check if current process is running in service context
                # By checking if process has service-specific security identifiers
                import win32ts  # Requires pywin32
                
                # Get current session info
                session_id = win32ts.WTSGetActiveConsoleSessionId()
                # If current process is not in console session, may be service process
                current_session = win32ts.ProcessIdToSessionId(os.getpid())
                if current_session != session_id:
                    logger.info("[INFO] Detected non-console session feature")
                    return True
            except:
                # If pywin32 is not available, skip this detection
                pass
        
        # By default, return False to ensure service registration logic works properly
        # Only return True when service mode features are explicitly detected
        logger.info("[INFO] No service mode features detected, will run in normal mode")
        return False
        
    except Exception as e:
        # When exception occurs, return False for safety to ensure service registration logic can execute
        logger = get_logger(__name__)
        logger.warning(f"[WARN] Service mode detection exception: {e}")
        return False


def hide_console_window():
    """Hide console window (Windows systems only)"""
    if platform.system() == "Windows":
        try:
            # Get console window handle
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                # Hide window
                ctypes.windll.user32.ShowWindow(console_window, 0)  # 0 = SW_HIDE
                return True
        except Exception as e:
            # Window hiding failure doesn't affect program execution
            pass
    return False


def run_a_process():
    """Run A process (user-started process)"""
    logger = get_logger(__name__)
    logger.info("[INFO] Starting A process (user process)...")
    
    # Start system tray
    tray = start_system_tray("agent")
    
    # Start FastAPI service
    async def run_api():
        await run_message_api_service(port=8001)
    
    # Start FastAPI service in main event loop
    import asyncio
    
    # Create new event loop for FastAPI service
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Run FastAPI service in background thread
    def start_fastapi():
        try:
            loop.run_until_complete(run_api())
        except Exception as e:
            logger.error(f"[ERROR] FastAPI service startup failed: {e}")
    
    api_thread = threading.Thread(target=start_fastapi, daemon=True)
    api_thread.start()
    
    # Wait for FastAPI service to start
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
                logger.info("[INFO] FastAPI service startup successful, port 8001 ready")
                break
            else:
                if i == max_retries - 1:
                    logger.error("[ERROR] FastAPI service startup failed, port 8001 not ready")
                else:
                    time.sleep(0.5)
        except Exception as e:
            logger.warning(f"[WARN] Port detection failed: {e}")
            time.sleep(0.5)
    
    logger.info("[INFO] A process startup completed: system tray and FastAPI service started")
    logger.info("[INFO] Message box API service address: http://127.0.0.1:8001")
    logger.info("[INFO] A process will run in background, providing message box support for system service")
    
    # Keep process running, but hide console window
    try:
        # Hide console window in non-debug mode
        if not any('debug' in arg.lower() for arg in sys.argv) and platform.system() == "Windows":
            hide_console_window()
            logger.info("[INFO] Console window hidden")
        
        # Keep process running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[INFO] A process received interrupt signal, exiting...")
    except Exception as e:
        logger.error(f"[ERROR] A process runtime exception: {e}")


def run_b_process():
    """Run B process (system service process)"""
    logger = get_logger(__name__)
    logger.info("[INFO] Starting B process (system service process)...")
    
    # Run application main logic
    try:
        # Detect if in debug mode
        debug_mode = False
        if len(sys.argv) > 1 and sys.argv[1].lower() == 'debug':
            debug_mode = True
        
        logger.info(f"[INFO] Starting application core functionality... (debug mode: {debug_mode})")
        asyncio.run(run_application(debug=debug_mode))
        
        logger.info("[INFO] B process exited normally")
        
    except KeyboardInterrupt:
        logger.info("[INFO] B process received interrupt signal, exiting...")
    except Exception as e:
        logger.error(f"[ERROR] B process runtime exception: {e}")
        sys.exit(1)


def main():
    """Main function - dual process version"""
    
    # Parse command line parameters
    import argparse
    parser = argparse.ArgumentParser(description='agent')
    parser.add_argument('mode', nargs='?', default='normal', help='Running mode: normal or debug')
    args = parser.parse_args()
    
    # Determine if in debug mode
    debug_mode = False
    if args.mode and hasattr(args.mode, 'lower'):
        debug_mode = args.mode.lower() == 'debug'
    
    # Initialize unified logging system, pass debug parameter
    setup_global_logging(debug=debug_mode)
    redirect_all_output()
    
    logger = get_logger(__name__)
    
    # Hide console window in non-debug mode
    if not debug_mode and platform.system() == "Windows":
        if hide_console_window():
            logger.info("[INFO] Console window hidden")
        else:
            logger.info("[INFO] Console window hiding failed, continuing to run")
    
    # Multi-process detection and repair - prevent duplicate startup
    try:
        current_pid = os.getpid()
        existing_processes = []
        
        # Record current process start time
        current_process_start_time = psutil.Process(current_pid).create_time()
        current_process_start_time_with_tolerance = current_process_start_time - 1.0
        
        # Detect other local_agent processes
        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "ppid", "create_time"]):
            try:
                proc_info = proc.info
                proc_pid = proc_info.get("pid")
                proc_name = proc_info.get("name", "") or ""
                proc_exe = proc_info.get("exe", "") or ""
                proc_cmdline = proc_info.get("cmdline", []) or []
                proc_ppid = proc_info.get("ppid")
                proc_create_time = proc_info.get("create_time")
                
                # Skip current process
                if proc_pid == current_pid:
                    continue
                
                # Skip current process's child processes
                if proc_ppid == current_pid:
                    continue
                
                # Skip processes started after current process
                if proc_create_time and proc_create_time > current_process_start_time_with_tolerance:
                    continue
                
                # Skip current process's parent process
                if proc_pid == os.getppid():
                    continue
                
                # Check if it's a local_agent process
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
        
        # If other local_agent processes are running
        if len(existing_processes) > 0:
            logger.info(f"[INFO] Detected {len(existing_processes)} other local_agent processes")
            
            # Check if currently running in service mode
            is_service_mode = check_if_service_mode()
            
            if is_service_mode:
                logger.info("[INFO] Currently in service mode (B process), allowing coexistence with A process")
                # B process (service mode) can coexist with A process
            else:
                # A process (user mode) needs to check if FastAPI service is running
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(('127.0.0.1', 8001))
                    sock.close()
                    
                    if result == 0:
                        logger.info("[INFO] Detected FastAPI service running (A process already running), current A process will exit")
                        logger.info("[INFO] Note: System service (B process) will start automatically, no need to run repeatedly")
                        sys.exit(0)
                    else:
                        logger.info("[INFO] FastAPI service not running, current A process will continue to start service")
                        
                except Exception as e:
                    logger.warning(f"[WARN] Port detection failed: {e}")
                    logger.warning("[WARN] To avoid duplicate startup, current A process will exit")
                    sys.exit(0)
        
    except Exception as e:
        logger.warning(f"[WARN] Multi-process detection failed: {e}")
    
    try:
        # Detect running mode
        is_service_mode = check_if_service_mode()
        
        if not is_service_mode:
            logger.info("[INFO] Detected user startup mode, starting A process (user process)...")
            
            # Regardless of whether service is installed, first try to automatically extract nssm.exe
            extract_success, extract_message = extract_of_scripts('nssm.exe')

            # Extract automatic update batch file
            extract_of_scripts('automatic_update.bat', overwrite=True)
            
            if extract_success:
                logger.info("[INFO] " + extract_message)
            else:
                logger.info("[INFO] " + extract_message)
            
            # In non-service mode, try automatic service registration
            service_registered = auto_register_service()
            
            if service_registered:
                logger.info("[INFO] System service registration successful!")
                logger.info("[INFO] Service will run automatically in system background (B process)")
                logger.info("[INFO] Current process will run as A process, providing message box support")
                
            else:
                logger.info("[INFO] System service registration failed or already exists")
                logger.info("[INFO] Current process will run as A process, but system service may not start automatically")
            
            # Regardless of service registration success, start A process
            logger.info("[INFO] Starting A process (user process)...")
            run_a_process()
            
        else:
            logger.info("[INFO] Detected system service mode, starting B process (system service process)...")
            logger.info("[INFO] B process will run core business logic")
            logger.info("[INFO] Message box functionality will be provided by A process's FastAPI service")
            
            # Run B process in service mode
            run_b_process()
        
    except KeyboardInterrupt:
        logger.info("[INFO] Received interrupt signal, application exiting...")
    except Exception as e:
        logger.error("[ERROR] Application runtime exception: " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()