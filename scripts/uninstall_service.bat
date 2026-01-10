@echo off
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
