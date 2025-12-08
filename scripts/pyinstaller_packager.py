#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller打包脚本 - 将应用打包为单个exe文件
支持NSSM服务安装
使用项目统一日志系统
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))# 简化导入项目统一日志系统
from local_agent import get_module_logger
from local_agent.utils.verify_md5 import calculate_md5


# 自动初始化日志系统并获取日志器
logger = get_module_logger()


def install_dependencies():
    """安装PyInstaller依赖"""
    logger.info("📦 安装PyInstaller依赖...")
    
    try:
        # 检查是否已安装PyInstaller
        import PyInstaller
        logger.info("✅ PyInstaller已安装")
    except ImportError:
        logger.info("📥 安装PyInstaller...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)
        logger.info("✅ PyInstaller安装完成")
    
    # 安装UPX（可选，用于压缩可执行文件）
    try:
        subprocess.run(['upx', '--version'], capture_output=True)
        logger.info("✅ UPX已安装")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.info("ℹ️  UPX未安装，可执行文件将不会压缩（可选）")


def save_md5_checksum(exe_path, checksum_file_name="local_agent_md5.txt"):
    """
    保存MD5校验和到文件
    
    Args:
        exe_path: EXE文件路径
        checksum_file_name: 校验文件名
        
    Returns:
        str: 校验文件路径
    """
    # 计算MD5
    md5_value = calculate_md5(exe_path)
    
    # 创建校验文件路径
    checksum_file_path = exe_path.parent / checksum_file_name
    
    # 写入校验和（简化格式：仅包含MD5值）
    with open(checksum_file_path, 'w', encoding='utf-8') as f:
        f.write(f"{md5_value}")
    
    logger.info(f"✅ MD5校验和已保存: {checksum_file_path}")
    logger.info(f"🔢 MD5值: {md5_value}")
    
    return checksum_file_path


def embed_version_info(exe_path):
    """
    向exe文件嵌入版本信息
    
    策略：
    1. 读取VERSION文件内容
    2. 使用pywin32设置exe文件版本信息
    3. 确保版本信息与打包版本一致
    """
    try:
        import win32api
        import win32con
        
        project_root = Path(__file__).parent.parent
        version_file = project_root / 'VERSION'
        
        if not version_file.exists():
            logger.warning("⚠️  VERSION文件不存在，跳过版本信息嵌入")
            return
        
        # 读取版本信息
        with open(version_file, 'r', encoding='utf-8') as f:
            version_str = f.read().strip()
        
        # 解析版本号（格式：VX.Y.Z）
        if version_str.startswith('V'):
            version_parts = version_str[1:].split('.')
            if len(version_parts) >= 3:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                build = int(version_parts[2])
                revision = int(version_parts[3]) if len(version_parts) > 3 else 0
                
                # 设置文件版本信息
                version_info = {
                    'FileVersion': f"{major}.{minor}.{build}.{revision}",
                    'ProductVersion': f"{major}.{minor}.{build}.{revision}",
                    'FileDescription': '本地代理服务 - 提供API接口和WebSocket连接',
                    'ProductName': 'Local Agent Service',
                    'CompanyName': 'Local Agent',
                    'LegalCopyright': 'Copyright © 2024 Local Agent',
                    'InternalName': 'local_agent.exe',
                    'OriginalFilename': 'local_agent.exe'
                }
                
                # 使用win32api设置版本信息
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
                
                logger.info(f"✅ 成功嵌入版本信息: {version_str}")
                return
        
        logger.warning(f"⚠️  版本格式无效: {version_str}，跳过版本信息嵌入")
        
    except ImportError:
        logger.warning("⚠️  pywin32模块不可用，跳过版本信息嵌入")
    except Exception as e:
        logger.warning(f"⚠️  版本信息嵌入失败: {str(e)}")


def build_exe():
    """构建exe文件"""
    logger.info("🔨 开始构建exe文件...")
    
    project_root = Path(__file__).parent.parent
    dist_dir = project_root / 'dist'
    build_dir = project_root / 'build'
    
    # 清理之前的构建文件（使用更安全的清理策略）
    try:
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        if build_dir.exists():
            shutil.rmtree(build_dir)
    except PermissionError as e:
        logger.warning(f"⚠️  清理构建目录失败（文件可能被锁定），尝试跳过清理: {str(e)}")
        logger.info("ℹ️  将尝试在现有目录基础上构建")
    except Exception as e:
        logger.warning(f"⚠️  清理构建目录失败: {str(e)}")
        logger.info("ℹ️  将尝试在现有目录基础上构建")
    
    # 检查需要添加的数据文件是否存在
    add_data_args = []
    
    # 添加实际存在的文件
    if (project_root / 'requirements.txt').exists():
        add_data_args.append('--add-data=requirements.txt;.')
    
    # 添加VERSION文件到打包资源（关键：确保版本信息与exe绑定）
    if (project_root / 'VERSION').exists():
        add_data_args.append('--add-data=VERSION;.')
        logger.info("✅ 将VERSION文件添加到打包资源")
    
    if (project_root / 'scripts').exists():
        add_data_args.append('--add-data=scripts;scripts')
    
    # 执行PyInstaller构建
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=local_agent',
        '--onefile',  # 打包为单个exe文件
        '--console',  # 显示控制台窗口（便于调试）
        *add_data_args,  # 动态添加数据文件
        '--hidden-import=local_agent',
        '--hidden-import=local_agent.api',
        '--hidden-import=local_agent.core',
        '--hidden-import=local_agent.websocket',
        '--hidden-import=local_agent.keep_alive',  # 新增保活模块
        '--hidden-import=local_agent.ui',  # 新增UI模块
        '--hidden-import=local_agent.ui.message_box',  # 新增消息框模块
        '--hidden-import=local_agent.ui.message_proxy',  # 新增消息框代理模块
        '--hidden-import=local_agent.ui.gui_message_handler',  # 新增GUI消息处理器模块
        '--hidden-import=local_agent.ui.message_pipe_client',  # 新增管道客户端模块
        '--additional-hooks-dir=hooks',  # 添加自定义hook目录
        '--hidden-import=tkinter',  # 关键：添加Tkinter支持
        '--hidden-import=_tkinter',  # 关键：添加Tkinter底层支持
        '--hidden-import=fastapi',
        '--hidden-import=uvicorn',
        '--hidden-import=websockets',
        '--hidden-import=psutil',
        '--hidden-import=pywin32',
        '--hidden-import=requests',  # 健康检查需要
        '--hidden-import=threading',  # 保活机制需要
        '--hidden-import=time',  # 保活机制需要
        '--hidden-import=subprocess',  # 保活机制需要
        '--clean',  # 清理缓存
        '--noconfirm',  # 不确认覆盖
        os.path.abspath('src/local_agent/__main__.py')
    ]
    
    logger.info(f"🚀 执行构建命令: {' '.join(cmd)}")
    
    # 使用更健壮的方式处理输出，避免编码问题
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=False)
    
    if result.returncode == 0:
        logger.info("✅ exe文件构建成功")
        
        # 检查生成的文件
        exe_path = dist_dir / 'local_agent.exe'
        if exe_path.exists():
            file_size = exe_path.stat().st_size / (1024 * 1024)  # MB
            logger.info(f"📁 生成文件: {exe_path}")
            logger.info(f"📊 文件大小: {file_size:.2f} MB")
            
            # 嵌入版本信息
            embed_version_info(exe_path)
            
            # 计算并保存MD5校验和
            md5_file_path = save_md5_checksum(exe_path)
            
            return exe_path
        else:
            raise FileNotFoundError(f"exe文件未生成: {exe_path}")
    else:
        logger.error(f"❌ 构建失败:")
        # 尝试解码输出，如果失败则显示原始字节
        try:
            stdout = result.stdout.decode('utf-8', errors='ignore')
            stderr = result.stderr.decode('utf-8', errors='ignore')
            logger.error(f"STDOUT: {stdout}")
            logger.error(f"STDERR: {stderr}")
        except:
            logger.error("无法解码输出，可能是编码问题")
        raise RuntimeError("PyInstaller构建失败")


def create_nssm_service_script(exe_path):
    """创建NSSM服务安装脚本"""
    logger.info("📝 创建NSSM服务安装脚本...")
    
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / 'scripts'
    
    # 服务安装脚本
    install_script = scripts_dir / 'install_service.bat'
    install_content = f'''@echo off
chcp 65001 >nul

echo ========================================
echo  本地代理服务安装脚本
echo ========================================

set SERVICE_NAME=LocalAgentService
set EXE_PATH={exe_path}
set WORKING_DIR={exe_path.parent}

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
'''
    
    with open(install_script, 'w', encoding='utf-8') as f:
        f.write(install_content)
    
    logger.info(f"✅ 服务安装脚本: {install_script}")
    
    # 服务卸载脚本
    uninstall_script = scripts_dir / 'uninstall_service.bat'
    uninstall_content = f'''@echo off
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
'''
    
    with open(uninstall_script, 'w', encoding='utf-8') as f:
        f.write(uninstall_content)
    
    logger.info(f"✅ 服务卸载脚本: {uninstall_script}")
    
    return install_script, uninstall_script


def create_deployment_package(exe_path):
    """创建部署包"""
    logger.info("📦 创建部署包...")
    
    project_root = Path(__file__).parent.parent
    deployment_dir = project_root / 'deployment'
    
    if deployment_dir.exists():
        shutil.rmtree(deployment_dir)
    deployment_dir.mkdir(exist_ok=True)
    
    # 复制exe文件
    shutil.copy2(exe_path, deployment_dir / 'local_agent.exe')
    
    # 复制MD5校验文件
    md5_file = exe_path.parent / 'local_agent_md5.txt'
    if md5_file.exists():
        shutil.copy2(md5_file, deployment_dir / 'local_agent_md5.txt')
        logger.info("✅ MD5校验文件已添加到部署包")
    
    # 复制必要的配置文件
    if (project_root / 'requirements.txt').exists():
        shutil.copy2(project_root / 'requirements.txt', deployment_dir)
    
    # 复制服务脚本
    scripts_dir = project_root / 'scripts'
    if (scripts_dir / 'install_service.bat').exists():
        shutil.copy2(scripts_dir / 'install_service.bat', deployment_dir)
    if (scripts_dir / 'uninstall_service.bat').exists():
        shutil.copy2(scripts_dir / 'uninstall_service.bat', deployment_dir)
    
    # 创建README文件
    readme_content = '''# 本地代理服务部署包

## 文件说明
- `local_agent.exe`: 主程序可执行文件
- `local_agent_md5.txt`: MD5完整性校验文件
- `install_service.bat`: 服务安装脚本
- `uninstall_service.bat`: 服务卸载脚本
- `requirements.txt`: 依赖包列表

## 安装步骤

### 1. 安装NSSM
下载并安装NSSM工具：https://nssm.cc/download
将nssm.exe放入系统PATH或当前目录

### 2. 安装服务
以管理员身份运行 `install_service.bat`

### 3. 验证安装
服务安装完成后，可以通过以下方式验证：
- 打开服务管理器（services.msc），查看"本地代理服务"状态
- 访问 http://localhost:8000/health 检查健康状态

## 完整性校验

### MD5校验
使用以下命令验证EXE文件的完整性：

```bash
# Windows PowerShell
Get-FileHash -Algorithm MD5 local_agent.exe

# 或者使用certutil
certutil -hashfile local_agent.exe MD5
```

将计算出的MD5值与`local_agent.md5`文件中的值进行比较，确保文件未被篡改。

## 管理命令
- 启动服务: `nssm start LocalAgentService`
- 停止服务: `nssm stop LocalAgentService`
- 重启服务: `nssm restart LocalAgentService`
- 卸载服务: `nssm remove LocalAgentService`

## 日志文件
- 服务日志: 当前目录\service.log
- 错误日志: 当前目录\service_error.log
'''
    
    with open(deployment_dir / 'README.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    logger.info(f"✅ 部署包创建完成: {deployment_dir}")
    return deployment_dir


def main():
    """主函数"""
    logger.info("🚀 PyInstaller + NSSM 打包工具")
    logger.info("=" * 50)
    
    try:
        # 1. 安装依赖
        install_dependencies()
        
        # 2. 构建exe文件
        exe_path = build_exe()
        
        # 3. 创建服务脚本
        install_script, uninstall_script = create_nssm_service_script(exe_path)
        
        # 4. 创建部署包
        deployment_dir = create_deployment_package(exe_path)
        
        logger.info("\n🎉 打包完成！")
        logger.info("=" * 50)
        logger.info(f"📁 exe文件: {exe_path}")
        logger.info(f"📁 部署包: {deployment_dir}")
        logger.info(f"📄 安装脚本: {install_script}")
        logger.info(f"📄 卸载脚本: {uninstall_script}")
        logger.info("\n💡 下一步:")
        logger.info("   1. 以管理员身份运行 install_service.bat 安装服务")
        logger.info("   2. 验证服务是否正常运行")
        
    except Exception as e:
        logger.error(f"❌ 打包失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()