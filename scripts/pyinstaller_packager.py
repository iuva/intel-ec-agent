#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller Packaging Script - Package application as single exe file
Support NSSM service installation
Use project unified logging system
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

# Add src directory to PythonPath
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))# Simplify importing project unified logging system
from local_agent import get_module_logger
from local_agent.utils.verify_md5 import calculate_md5


# Automatically initialize logging system and get logger
logger = get_module_logger()


def install_dependencies():
    """Install PyInstaller dependencies"""
    logger.info("📦 Installing PyInstaller dependencies...")
    
    try:
        # Check if PyInstaller is already installed
        import PyInstaller
        logger.info("✅ PyInstaller is already installed")
    except ImportError:
        logger.info("📥 Installing PyInstaller...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
        logger.info("✅ PyInstaller installation completed")
    
    # Install UPX (optional, for executable compression)
    try:
        subprocess.run(['upx', '--version'], capture_output=True)
        logger.info("✅ UPX is already installed")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.info("ℹ️  UPX not installed, executable will not be compressed (optional)")


def save_md5_checksum(exe_path, checksum_file_name="local_agent_md5.txt"):
    """
    Save MD5 checksum to file
    
    Args:
        exe_path: EXE file path
        checksum_file_name: checksum file name
        
    Returns:
        str: checksum file path
    """
    # Calculate MD5
    md5_value = calculate_md5(exe_path)
    
    # Create checksum file path
    checksum_file_path = exe_path.parent / checksum_file_name
    
    # Write checksum (simplified format: only MD5 value)
    with open(checksum_file_path, 'w', encoding='utf-8') as f:
        f.write(f"{md5_value}")
    
    logger.info(f"✅ MD5 checksum saved: {checksum_file_path}")
    logger.info(f"🔢 MD5 value: {md5_value}")
    
    return checksum_file_path


def embed_version_info(exe_path):
    """
    Embed version information into exe file
    
    Strategy:
    1. Read VERSION file content
    2. Use pywin32 to set exe file version information
    3. Ensure version information matches packaging version
    """
    try:
        import win32api
        import win32con
        
        project_root = Path(__file__).parent.parent
        version_file = project_root / 'VERSION'
        
        if not version_file.exists():
            logger.warning("⚠️  VERSION file not found, skipping version embedding")
            return
        
        # Read version information
        with open(version_file, 'r', encoding='utf-8') as f:
            version_str = f.read().strip()
        
        # Parse version number (format: VX.Y.Z)
        if version_str.startswith('V'):
            version_parts = version_str[1:].split('.')
            if len(version_parts) >= 3:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                build = int(version_parts[2])
                revision = int(version_parts[3]) if len(version_parts) > 3 else 0
                
                # Set file version information
                version_info = {
                    'FileVersion': f"{major}.{minor}.{build}.{revision}",
                    'ProductVersion': f"{major}.{minor}.{build}.{revision}",
                    'FileDescription': 'Local Agent Service - Provides API interface and WebSocket connection',
                    'ProductName': 'Local Agent Service',
                    'CompanyName': 'Local Agent',
                    'LegalCopyright': 'Copyright © 2024 Local Agent',
                    'InternalName': 'local_agent.exe',
                    'OriginalFilename': 'local_agent.exe'
                }
                
                # Use win32api to set version information
                win32api.SetFileVersionInfo(
                    str(exe_path),
                    version_info['FileVersion'],
                    version_info['ProductVersion'],
                    version_info['FileDescription'],
                    version_info['ProductName'],
                    version_info['CompanyName'],
                    version_info['LegalCopyright'],
                    version_info['InternalName'],
                    version_info['OriginalFilename']
                )
                
                logger.info(f"✅ Version information embedded successfully: {version_str}")
                return
        
        logger.warning(f"⚠️  Invalid version format: {version_str}, skipping version embedding")
        
    except ImportError:
        logger.warning("⚠️  pywin32 module not available, skipping version embedding")
    except Exception as e:
        logger.warning(f"⚠️  Version embedding failed: {str(e)}")


def build_exe():
    """Build exe file"""
    logger.info("🔨 Starting exe file build...")
    
    project_root = Path(__file__).parent.parent
    dist_dir = project_root / 'dist'
    build_dir = project_root / 'build'
    
    # Clean previous build files (using safer cleanup strategy)
    try:
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        if build_dir.exists():
            shutil.rmtree(build_dir)
    except PermissionError as e:
        logger.warning(f"⚠️  Failed to clean build directories (files may be locked), attempting to skip cleanup: {str(e)}")
        logger.info("ℹ️  Will attempt to build on existing directories")
    except Exception as e:
        logger.warning(f"⚠️  Failed to clean build directories: {str(e)}")
        logger.info("ℹ️  Will attempt to build on existing directories")
    
    # Check if required data files exist
    add_data_args = []
    
    # Add existing files
    if (project_root / 'requirements.txt').exists():
        add_data_args.append('--add-data=requirements.txt;.')
    
    # Add VERSION file to packaging resources (critical: ensure version info is bound to exe)
    if (project_root / 'VERSION').exists():
        add_data_args.append('--add-data=VERSION;.')
        logger.info("✅ Added VERSION file to packaging resources")
    
    if (project_root / 'scripts').exists():
        add_data_args.append('--add-data=scripts;scripts')
    
    # Execute PyInstaller build
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=local_agent',
        '--onefile',  # Package as single exe file
        '--console',  # Show console window (for debugging)
        *add_data_args,  # Dynamically add data files
        '--hidden-import=local_agent',
        '--hidden-import=local_agent.api',
        '--hidden-import=local_agent.core',
        '--hidden-import=local_agent.websocket',
        '--hidden-import=local_agent.keep_alive',  # New keep-alive module
        '--hidden-import=local_agent.ui',  # New UI module
        '--additional-hooks-dir=hooks',  # Add custom hook directory
        '--hidden-import=tkinter',  # Critical: Add Tkinter support
        '--hidden-import=_tkinter',  # Critical: Add Tkinter low-level support
        '--hidden-import=fastapi',
        '--hidden-import=uvicorn',
        '--hidden-import=websockets',
        '--hidden-import=psutil',
        '--hidden-import=pywin32',
        '--hidden-import=requests',  # Health check required
        '--hidden-import=threading',  # Keep-alive mechanism required
        '--hidden-import=time',  # Keep-alive mechanism required
        '--hidden-import=subprocess',  # Keep-alive mechanism required
        '--clean',  # Clean cache
        '--noconfirm',  # No confirmation for overwrite
        os.path.abspath('src/local_agent/__main__.py')
    ]
    
    logger.info(f"🚀 Executing build command: {' '.join(cmd)}")
    
    # Use more robust way to handle output, avoid encoding issues
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=False)
    
    if result.returncode == 0:
        logger.info("✅ exe file build successful")
        
        # Check generated files
        exe_path = dist_dir / 'local_agent.exe'
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024 * 1024)  # MB
            logger.info(f"📁 Generated file: {exe_path}")
            logger.info(f"📊 File size: {file_size:.2f} MB")
            
            # Embed version information
            embed_version_info(exe_path)
            
            # Calculate and save MD5 checksum
            md5_file_path = save_md5_checksum(exe_path)
            
            return exe_path
        else:
            raise FileNotFoundError(f"exe file not generated: {exe_path}")
    else:
        logger.error(f"❌ Build failed:")
        # Try to decode output, show raw bytes if decoding fails
        try:
            stdout = result.stdout.decode('utf-8', errors='ignore')
            stderr = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"STDOUT: {stdout}")
            logger.error(f"STDERR: {stderr}")
        except:
            logger.error("Unable to decode output, may be encoding issue")
        raise RuntimeError("PyInstaller build failed")


def create_nssm_service_script(exe_path):
    """Create NSSM service installation script"""
    logger.info("📝 Creating NSSM service installation script...")
    
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / 'scripts'
    
    # Service installation script
    install_script = scripts_dir / 'install_service.bat'
    install_content = f'''@echo off
chcp 65001 >nul

echo ========================================
echo  Local Agent Service Installation Script
echo ========================================

set SERVICE_NAME=LocalAgentService
set EXE_PATH={exe_path}
set WORKING_DIR={exe_path.parent}

:: Check if NSSM is available
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ NSSM not found. Please download and install NSSM first
    echo 📥 Download: https://nssm.cc/download
    echo 📁 Place nssm.exe in system PATH or current directory
    pause
    exit /b 1
)

:: Check if service already exists
nssm status %SERVICE_NAME% >nul 2>&1
if %errorlevel% == 0 (
    echo ⚠️  Service %SERVICE_NAME% already exists
    echo ❓ Reinstall? (y/n)
    set /p choice=
    if /i not "%choice%"=="y" (
        echo Installation canceled
        pause
        exit /b 0
    )
    
    echo 🔄 Stopping and removing existing service...
    nssm stop %SERVICE_NAME%
    nssm remove %SERVICE_NAME% confirm
)

:: Install service
echo 📥 Installing service %SERVICE_NAME%...
nssm install %SERVICE_NAME% "%EXE_PATH%"

:: Configure service parameters
nssm set %SERVICE_NAME% Description "Local Agent Service - Provides API interface and WebSocket connection"
nssm set %SERVICE_NAME% DisplayName "Local Agent Service"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppDirectory "%WORKING_DIR%"
nssm set %SERVICE_NAME% AppStdout "%WORKING_DIR%\service.log"
nssm set %SERVICE_NAME% AppStderr "%WORKING_DIR%\service_error.log"

:: Start service
echo 🚀 Starting service...
nssm start %SERVICE_NAME%

:: Check service status
timeout /t 3 >nul
echo 📊 Service status:
nssm status %SERVICE_NAME%

echo.
echo ✅ Service installation completed!
echo 📁 Service directory: %WORKING_DIR%
echo 📄 Log file: %WORKING_DIR%\service.log
echo.
echo 💡 Management commands:
echo   Start service: nssm start %SERVICE_NAME%
echo   Stop service: nssm stop %SERVICE_NAME%
echo   Restart service: nssm restart %SERVICE_NAME%
echo   Uninstall service: nssm remove %SERVICE_NAME%

pause
'''
    
    with open(install_script, 'w', encoding='utf-8') as f:
        f.write(install_content)
    
    logger.info(f"✅ Service installation script: {install_script}")
    
    # Service uninstallation script
    uninstall_script = scripts_dir / 'uninstall_service.bat'
    uninstall_content = f'''@echo off
chcp 65001 >nul

echo ========================================
echo  Local Agent Service Uninstallation Script
echo ========================================

set SERVICE_NAME=LocalAgentService

:: Check if service exists
nssm status %SERVICE_NAME% >nul 2>&1
if %errorlevel% neq 0 (
    echo ℹ️  Service %SERVICE_NAME% does not exist
    pause
    exit /b 0
)

echo ⚠️  About to uninstall service %SERVICE_NAME%
echo ❓ Confirm uninstallation? (y/n)
set /p choice=

if /i not "%choice%"=="y" (
    echo Uninstallation canceled
    pause
    exit /b 0
)

echo 🔄 Stopping and uninstalling service...
nssm stop %SERVICE_NAME%
nssm remove %SERVICE_NAME% confirm

echo ✅ Service uninstallation completed
pause
'''
    
    with open(uninstall_script, 'w', encoding='utf-8') as f:
        f.write(uninstall_content)
    
    logger.info(f"✅ Service uninstallation script: {uninstall_script}")
    
    return install_script, uninstall_script


def create_deployment_package(exe_path):
    """Create deployment package"""
    logger.info("📦 Creating deployment package...")
    
    project_root = Path(__file__).parent.parent
    deployment_dir = project_root / 'deployment'
    
    if deployment_dir.exists():
        shutil.rmtree(deployment_dir)
    deployment_dir.mkdir(exist_ok=True)
    
    # Copy exe file
    shutil.copy2(exe_path, deployment_dir / 'local_agent.exe')
    
    # Copy MD5 checksum file
    md5_file = exe_path.parent / 'local_agent_md5.txt'
    if md5_file.exists():
        shutil.copy2(md5_file, deployment_dir / 'local_agent_md5.txt')
        logger.info("✅ MD5 checksum file added to deployment package")
    
    # Copy necessary configuration files
    if (project_root / 'requirements.txt').exists():
        shutil.copy2(project_root / 'requirements.txt', deployment_dir)
    
    # Copy service scripts
    scripts_dir = project_root / 'scripts'
    if (scripts_dir / 'install_service.bat').exists():
        shutil.copy2(scripts_dir / 'install_service.bat', deployment_dir)
    if (scripts_dir / 'uninstall_service.bat').exists():
        shutil.copy2(scripts_dir / 'uninstall_service.bat', deployment_dir)
    
    # Create README file
    readme_content = '''# Local Agent Service Deployment Package

## File Description
- `local_agent.exe`: Main executable file
- `local_agent_md5.txt`: MD5 integrity checksum file
- `install_service.bat`: Service installation script
- `uninstall_service.bat`: Service uninstallation script
- `requirements.txt`: Dependency package list

## Installation Steps

### 1. Install NSSM
Download and install NSSM tool: https://nssm.cc/download
Place nssm.exe in system PATH or current directory

### 2. Install Service
Run `install_service.bat` as administrator

### 3. Verify Installation
After service installation, verify using:
- Open Services Manager (services.msc), check "Local Agent Service" status
- Visit http://localhost:8000/health to check health status

## Integrity Verification

### MD5 Checksum
Use following commands to verify EXE file integrity:

```bash
# Windows PowerShell
Get-FileHash -Algorithm MD5 local_agent.exe

# Or use certutil
certutil -hashfile local_agent.exe MD5
```

Compare calculated MD5 value with value in `local_agent.md5` file to ensure file integrity.

## Management Commands
- Start service: `nssm start LocalAgentService`
- Stop service: `nssm stop LocalAgentService`
- Restart service: `nssm restart LocalAgentService`
- Uninstall service: `nssm remove LocalAgentService`

## Log Files
- Service log: current directory\service.log
- Error log: current directory\service_error.log
'''
    
    with open(deployment_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    logger.info(f"✅ Deployment package created: {deployment_dir}")
    return deployment_dir


def main():
    """Main function"""
    logger.info("🚀 PyInstaller + NSSM Packaging Tool")
    logger.info("=" * 50)
    
    try:
        # 1. Install dependencies
        install_dependencies()
        
        # 2. Build exe file
        exe_path = build_exe()
        
        # 3. Create service scripts
        install_script, uninstall_script = create_nssm_service_script(exe_path)
        
        # 4. Create deployment package
        deployment_dir = create_deployment_package(exe_path)
        
        logger.info("\n🎉 Packaging completed!")
        logger.info("=" * 50)
        logger.info(f"📁 exe file: {exe_path}")
        logger.info(f"📁 deployment package: {deployment_dir}")
        logger.info(f"📄 installation script: {install_script}")
        logger.info(f"📄 uninstallation script: {uninstall_script}")
        logger.info("\n💡 Next steps:")
        logger.info("   1. Run install_service.bat as administrator to install service")
        logger.info("   2. Verify service is running correctly")
        
    except Exception as e:
        logger.error(f"❌ Packaging failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()