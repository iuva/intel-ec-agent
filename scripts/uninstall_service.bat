@echo off
chcp 65001 >nul

echo ========================================
echo  本地代理服务卸载脚本
echo ========================================

set SERVICE_NAME=LocalAgentService

:: 检查服务是否存在
nssm status %SERVICE_NAME% >nul 2>&1
if %errorlevel% neq 0 (
    echo ℹ️  服务 %SERVICE_NAME% 不存在
    pause
    exit /b 0
)

echo ⚠️  即将卸载服务 %SERVICE_NAME%
echo ❓ 确认卸载？(y/n)
set /p choice=

if /i not "%choice%"=="y" (
    echo 取消卸载
    pause
    exit /b 0
)

echo 🔄 停止并卸载服务...
nssm stop %SERVICE_NAME%
nssm remove %SERVICE_NAME% confirm

echo ✅ 服务卸载完成
pause
