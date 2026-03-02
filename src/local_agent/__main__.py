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
import argparse
from pathlib import Path

# Import enhanced subprocess utility
from local_agent.utils.subprocess_utils import run_with_logging

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from local_agent.core.application import run_application
from local_agent.logger import get_logger, setup_global_logging, redirect_all_output
from local_agent.ui.message_api import run_message_api_service
from local_agent.ui.system_tray import start_system_tray
from local_agent.config import get_config

# Import file utility class
from local_agent.utils.file_utils import FileUtils


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Local Agent Application')
    
    # Add service mode parameter
    parser.add_argument('--service', '-s', 
                       action='store_true',
                       help='Run in service mode (Process B) - default is UI mode (Process A)')
    
    # Add debug mode parameter
    parser.add_argument('--debug', '-d', 
                       action='store_true',
                       help='Run in debug mode for local development - starts both A and B processes')
    
    return parser.parse_args()


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
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"[WARN] Error checking service status: {e}")
        return False


def check_service_startup_type(service_name="LocalAgentService"):
    """Check if service startup type is AUTO"""
    try:
        result = run_with_logging(
            ['sc', 'qc', service_name],
            command_name="check_service_startup_type",
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Check if startup type is AUTO
            return "AUTO_START" in result.stdout or "AUTO" in result.stdout
        else:
            return False
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"[WARN] Error checking service startup type: {e}")
        return False


def verify_and_repair_service():
    """Verify system service registration and startup type, repair if necessary"""
    logger = get_logger(__name__)
    service_name = "LocalAgentService"
    
    # Check if service exists
    if not check_service_exists(service_name):
        logger.error(f"[ERROR] System service {service_name} does not exist")
        logger.info("[INFO] Attempting to reinstall service...")
        
        # Stop and delete service if exists but in bad state
        try:
            run_with_logging(['sc', 'stop', service_name], timeout=30)
            run_with_logging(['sc', 'delete', service_name], timeout=30)
        except:
            pass
        
        # Reinstall service
        if install_service_via_nssm():
            logger.info("[INFO] Service reinstalled successfully")
            return True
        else:
            logger.error("[ERROR] Failed to reinstall service")
            return False
    
    # Check if startup type is AUTO
    if not check_service_startup_type(service_name):
        logger.warning(f"[WARN] Service {service_name} startup type is not AUTO")
        logger.info("[INFO] Setting service startup type to AUTO...")
        
        try:
            result = run_with_logging(
                ['sc', 'config', service_name, 'start=', 'auto'],
                timeout=30
            )
            if result.returncode == 0:
                logger.info("[INFO] Service startup type set to AUTO successfully")
                return True
            else:
                logger.error("[ERROR] Failed to set service startup type to AUTO")
                return False
        except Exception as e:
            logger.error(f"[ERROR] Error setting service startup type: {e}")
            return False
    
    logger.info("[INFO] System service verification passed")
    return True


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
        
        # Install service with --service parameter
        result = run_with_logging(
            [nssm_path, 'install', service_name, exe_path, '--service'],
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
    logger.info(f"[INFO] Message box API service address: {get_config().get('message_api_url')}")
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
    args = parse_arguments()
    
    # Determine if in debug mode
    debug_mode = args.debug if hasattr(args, 'debug') else False
    
    # Initialize unified logging system, pass debug parameter
    setup_global_logging(debug=debug_mode)
    redirect_all_output()
    
    logger = get_logger()
    
    # Log command line arguments
    logger.info(f"[INFO] Command line arguments: {sys.argv}")
    logger.info(f"[INFO] Parsed arguments: service={args.service}, debug={debug_mode}")
    
    # If debug mode, run both A and B processes
    if debug_mode:
        logger.info("[INFO] Starting in DEBUG mode - running both A and B processes")
        import threading
        
        def run_b_thread():
            """Run B process in separate thread"""
            run_b_process()
        
        # Start B process in a separate thread
        b_thread = threading.Thread(target=run_b_thread, name="BProcess", daemon=True)
        b_thread.start()
        
        # Run A process in main thread
        logger.info("[INFO] Starting A process in main thread...")
        run_a_process()
        
        # Wait for B thread to complete
        b_thread.join()
        return
    
    # Determine running mode based on command line arguments
    # Simple logic: if --service is specified, run in service mode, otherwise UI mode
    if args.service:
        logger.info("[INFO] Starting in service mode (Process B) based on --service argument")
        is_service_mode = True
    else:
        logger.info("[INFO] Starting in UI mode (Process A) - default mode")
        is_service_mode = False
    
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
        # Use the is_service_mode determined from command line arguments or auto-detection
        
        if not is_service_mode:
            logger.info("[INFO] Detected user startup mode, starting A process (user process)...")
            
            # Step 1: Verify and repair system service before starting A process
            logger.info("[INFO] Verifying system service registration and startup type...")
            if not verify_and_repair_service():
                logger.error("[ERROR] System service verification failed, A process cannot continue")
                logger.info("[INFO] Please check system service status manually and restart A process")
                sys.exit(1)
            
            # Step 1.5: Configure UI process auto-start via Windows Task Scheduler
            logger.info("[INFO] Configuring UI process auto-start via Windows Task Scheduler...")
            try:
                from local_agent.utils.task_scheduler import configure_ui_auto_start
                if configure_ui_auto_start():
                    logger.info("[INFO] UI process auto-start configuration completed successfully")
                else:
                    logger.warning("[WARN] UI process auto-start configuration failed, but continuing startup")
            except Exception as e:
                logger.warning(f"[WARN] Failed to configure UI process auto-start: {e}")
                logger.info("[INFO] Continuing startup despite auto-start configuration failure")
            
            # Step 2: Check if there's already a running A process with working 8001 port
            logger.info("[INFO] Checking for existing A process with working 8001 port...")
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex(('127.0.0.1', 8001))
                sock.close()
                
                if result == 0:
                    logger.info("[INFO] 8001 port is accessible, indicating A process is already running")
                    logger.info("[INFO] Current A process will exit to avoid duplication")
                    sys.exit(0)
                else:
                    logger.info("[INFO] 8001 port is not accessible, continuing with A process startup")
                    
            except Exception as e:
                logger.warning(f"[WARN] Port 8001 detection failed: {e}")
                logger.info("[INFO] Continuing with A process startup")
            
            # Step 3: Extract required files
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