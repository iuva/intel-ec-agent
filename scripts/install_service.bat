@echo off
chcp 65001 >nul

echo ========================================
echo  Local Agent Service Installation Script
echo ========================================

set SERVICE_NAME=LocalAgentService
set EXE_PATH=F:\testPc\dragTest\dist\local_agent.exe
set WORKING_DIR=F:\testPc\dragTest\dist

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
