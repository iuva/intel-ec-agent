@echo off
chcp 65001 >nul

echo ========================================
echo  本地代理服务安装脚本
echo ========================================

set SERVICE_NAME=LocalAgentService
set EXE_PATH=F:\testPc\dragTest\dist\local_agent.exe
set WORKING_DIR=F:\testPc\dragTest\dist

:: 检查NSSM是否可用
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ NSSM未找到，请先下载并安装NSSM
    echo 📥 下载地址: https://nssm.cc/download
    echo 📁 将nssm.exe放入系统PATH或当前目录
    pause
    exit /b 1
)

:: 检查服务是否已存在
nssm status %SERVICE_NAME% >nul 2>&1
if %errorlevel% == 0 (
    echo ⚠️  服务 %SERVICE_NAME% 已存在
    echo ❓ 是否重新安装？(y/n)
    set /p choice=
    if /i not "%choice%"=="y" (
        echo 取消安装
        pause
        exit /b 0
    )
    
    echo 🔄 停止并删除现有服务...
    nssm stop %SERVICE_NAME%
    nssm remove %SERVICE_NAME% confirm
)

:: 安装服务
echo 📥 安装服务 %SERVICE_NAME%...
nssm install %SERVICE_NAME% "%EXE_PATH%"

:: 配置服务参数
nssm set %SERVICE_NAME% Description "本地代理服务 - 提供API接口和WebSocket连接"
nssm set %SERVICE_NAME% DisplayName "本地代理服务"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppDirectory "%WORKING_DIR%"
nssm set %SERVICE_NAME% AppStdout "%WORKING_DIR%\service.log"
nssm set %SERVICE_NAME% AppStderr "%WORKING_DIR%\service_error.log"

:: 启动服务
echo 🚀 启动服务...
nssm start %SERVICE_NAME%

:: 检查服务状态
timeout /t 3 >nul
echo 📊 服务状态:
nssm status %SERVICE_NAME%

echo.
echo ✅ 服务安装完成！
echo 📁 服务目录: %WORKING_DIR%
echo 📄 日志文件: %WORKING_DIR%\service.log
echo.
echo 💡 管理命令:
echo   启动服务: nssm start %SERVICE_NAME%
echo   停止服务: nssm stop %SERVICE_NAME%
echo   重启服务: nssm restart %SERVICE_NAME%
echo   卸载服务: nssm remove %SERVICE_NAME%

pause
