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
    
    # UPX is REQUIRED for executable compression
    _find_upx_dir()  # Will raise RuntimeError if UPX not found


def _find_upx_dir() -> str:
    """
    Find UPX binary directory. UPX is required for build.
    
    Search order:
    1. System PATH
    2. ec_neusoft_agent/tools/upx/
    
    Returns:
        str: Directory containing upx.exe
        
    Raises:
        RuntimeError: If UPX is not found
    """
    # Check PATH
    upx_path = shutil.which('upx')
    if upx_path:
        result = subprocess.run([upx_path, '--version'], capture_output=True)
        if result.returncode == 0:
            logger.info(f"✅ UPX found in PATH: {upx_path}")
            return str(Path(upx_path).parent)
    
    # Check local tools directory
    local_upx = Path(__file__).parent.parent / 'tools' / 'upx' / 'upx.exe'
    if local_upx.exists():
        result = subprocess.run([str(local_upx), '--version'], capture_output=True)
        if result.returncode == 0:
            logger.info(f"✅ UPX found locally: {local_upx}")
            return str(local_upx.parent)
    
    raise RuntimeError(
        "UPX not found. UPX is required for build. "
        "Install UPX and add to PATH, or place upx.exe in ec_neusoft_agent/tools/upx/"
    )


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
    
    # 检查 spec 文件是否存在
    spec_file = project_root / 'local_agent.spec'
    if not spec_file.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_file}")

    # UPX is REQUIRED for executable compression
    upx_dir = _find_upx_dir()
    logger.info(f"📦 UPX compression enabled: {upx_dir}")

    # Execute PyInstaller build via spec file
    # spec 中统一维护 entry/pathex/datas/hookspath/hiddenimports/excludes 等配置
    # （已改为基于 spec 自身位置的相对路径，跨机器可复用）。
    # 这里只保留全局运行控制参数 —— upx-dir/clean/noconfirm 在 spec 模式下同样生效。
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        str(spec_file),
        f'--upx-dir={upx_dir}',
        '--clean',  # Clean cache
        '--noconfirm',  # No confirmation for overwrite
    ]

    logger.info(f"🚀 Executing build command: {' '.join(cmd)}")

    # Sanitize environment before running PyInstaller.
    # A stray PYTHONPATH pointing at user-site (Windows Store Python quirk) will
    # cause PyInstaller's dependency analyzer to pull in every package installed
    # in user-site (Pillow-with-AVIF, cryptography, mypy, watchfiles, bcrypt,
    # Pythonwin/MFC, etc.), nearly doubling the exe size (~22MB -> ~41MB).
    # Force PyInstaller to only see the current venv's site-packages.
    build_env = os.environ.copy()
    stripped_path = build_env.pop("PYTHONPATH", None)
    if stripped_path:
        logger.info(f"🧹 Stripped PYTHONPATH from build env (was: {stripped_path})")
    build_env["PYTHONNOUSERSITE"] = "1"

    # Use more robust way to handle output, avoid encoding issues
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=False, env=build_env)
    
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

:: 基于脚本自身位置解析相对路径，并做绝对化规范化
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "EXE_PATH=%PROJECT_ROOT%\\dist\\local_agent.exe"
set "WORKING_DIR=%PROJECT_ROOT%\\dist"

:: 检查打包产物是否存在
if not exist "%EXE_PATH%" (
    echo ❌ 未找到 local_agent.exe，请先执行打包: python scripts/pyinstaller_packager.py
    echo 📁 期望位置: %EXE_PATH%
    pause
    exit /b 1
)

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