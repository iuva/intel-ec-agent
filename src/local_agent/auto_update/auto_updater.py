#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自更新管理器
支持同步和异步调用，集成下载、MD5校验、备份和批处理执行功能
"""

import sys
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from ..logger import get_logger

# 导入工具类
from local_agent.utils.file_downloader import FileDownloader
from local_agent.utils.verify_md5 import calculate_md5
from local_agent.utils.http_client import http_client
from local_agent.utils.file_utils import FileUtils


class AutoUpdater:
    """自更新管理器类"""
    
    def __init__(self):
        """初始化自更新管理器"""
        self.logger = get_logger()
        
        # 使用路径工具类获取路径
        from ..utils.path_utils import get_root_path, get_current_executable_path
        
        self.scripts_dir = get_root_path()
        self.current_exe_path = get_current_executable_path()
        
        # 批处理文件路径
        self.batch_file = self.scripts_dir / "automatic_update.bat"
        
        # 下载器实例
        self.downloader = FileDownloader()
        
        # 更新状态
        self.update_status = {
            'stage': 'idle',
            'progress': 0,
            'message': '',
            'error': None
        }
    
    def _update_progress(self, stage: str, progress: int, message: str = ''):
        """更新进度状态"""
        self.update_status = {
            'stage': stage,
            'progress': progress,
            'message': message,
            'error': None
        }
        self.logger.info(f"[{stage}] {progress}% - {message}")
    
    def _update_error(self, stage: str, error: str):
        """更新错误状态"""
        self.update_status = {
            'stage': stage,
            'progress': 0,
            'message': '',
            'error': error
        }
        self.logger.error(f"[{stage}] 错误: {error}")
    
    async def _download_file(self, url: str, save_path: Path) -> bool:
        """异步下载文件"""
        try:
            self._update_progress('downloading', 0, '开始下载更新文件')
            
            success = await self.downloader.download(url, str(save_path))
            
            if success:
                self._update_progress('downloading', 100, '下载完成')
                return True
            else:
                self._update_error('downloading', '文件下载失败')
                return False
                
        except Exception as e:
            self._update_error('downloading', f'下载异常: {str(e)}')
            return False
    
    def _verify_md5(self, file_path: Path, expected_md5: str) -> bool:
        """验证文件MD5校验和"""
        try:
            self._update_progress('verifying', 0, '开始校验文件完整性')
            
            if not file_path.exists():
                self._update_error('verifying', '文件不存在')
                return False
            
            actual_md5 = calculate_md5(str(file_path))
            
            if actual_md5.lower() == expected_md5.lower():
                self._update_progress('verifying', 100, f'文件完整性校验通过: 期望{expected_md5}, 实际{actual_md5}')
                return True
            else:
                self._update_error('verifying', f'MD5校验失败: 期望{expected_md5}, 实际{actual_md5}')
                return False
                
        except Exception as e:
            self._update_error('verifying', f'校验异常: {str(e)}')
            return False
    
    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """创建文件备份"""
        try:
            self._update_progress('backup', 0, '开始创建备份')
            
            if not file_path.exists():
                self._update_error('backup', '要备份的文件不存在')
                return None
            
            # 创建备份目录
            backup_dir = file_path.parent / 'backup'
            backup_dir.mkdir(exist_ok=True)
            
            # 生成带时间戳的备份文件名
            import time
            timestamp = int(time.time())
            backup_name = f"{file_path.name}.backup.{timestamp}"
            backup_path = backup_dir / backup_name
            
            # 复制文件
            shutil.copy2(str(file_path), str(backup_path))
            
            if backup_path.exists():
                self._update_progress('backup', 100, f'备份创建成功: {backup_path}')
                return backup_path
            else:
                self._update_error('backup', '备份文件创建失败')
                return None
                
        except Exception as e:
            self._update_error('backup', f'备份异常: {str(e)}')
            return None
    
    def _execute_batch_file(self, new_exe_path: Path, backup_path: Path) -> bool:
        """执行批处理文件进行更新"""
        try:
            self._update_progress('executing', 0, '准备执行更新脚本')
            
            FileUtils.extract_file_from_scripts('automatic_update.bat', overwrite=True)
            
            if not self.batch_file.exists():
                self._update_error('executing', f'批处理文件不存在: {self.batch_file}')
                return False
            
            if not new_exe_path.exists():
                self._update_error('executing', f'新版本文件不存在: {new_exe_path}')
                return False
            
            # 构建批处理参数
            # 参数格式: 服务名(空) 新exe路径 旧exe路径 备份目录
            service_name = "LocalAgentService"
            old_exe_path = self.current_exe_path
            # 备份目录始终使用exe同级目录下的backup文件夹
            backup_dir = old_exe_path.parent / 'backup'
            
            # 构建命令
            import subprocess
            cmd = [
                str(self.batch_file),
                service_name,
                str(new_exe_path),
                str(old_exe_path),
                str(backup_dir)
            ]
            
            self.logger.info(f"执行批处理命令: {' '.join(cmd)}")
            
            # 以独立进程方式启动批处理，确保批处理脚本能独立于当前进程运行
            # 使用CREATE_NEW_PROCESS_GROUP和DETACHED_PROCESS标志
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 隐藏窗口
            
            # 使用CREATE_NEW_PROCESS_GROUP确保批处理进程独立
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            
            # 启动批处理进程，确保其完全独立于当前进程
            # 使用start命令创建完全独立的进程
            import subprocess
            
            # 构建完整的批处理命令
            full_cmd = f'start "" /B cmd /c "{" ".join(cmd)}"'
            
            # 使用start命令创建独立进程
            subprocess.Popen(
                full_cmd, 
                shell=True,
                startupinfo=startupinfo,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # 给批处理进程更多执行时间，确保更新脚本能完全执行
            import time
            time.sleep(25)
            
            self._update_progress('executing', 100, '更新脚本已启动，进程即将终止')
            
            # 注意：这里不会等待批处理完成，因为批处理会杀死当前进程
            # 使用start命令确保批处理进程完全独立，不受当前进程终止影响
            return True
            
        except Exception as e:
            self._update_error('executing', f'执行批处理异常: {str(e)}')
            return False
    
    async def perform_update(self, expected_md5: str, download_url: str) -> Dict[str, Any]:
        import time
        from local_agent.core.persistent_storage import set_persistent_data
        try:
            self._update_progress('starting', 0, '开始自更新流程')
            
            # 构建完整下载URL
            full_download_url = http_client._build_file_url(download_url)
            
            # 1. 下载更新文件 - 下载到exe所在目录，避免权限问题
            # 判断是否为打包环境
            if getattr(sys, 'frozen', False):
                # 打包环境：使用exe所在目录
                exe_dir = Path(sys.executable).parent
            else:
                # 开发环境：使用项目根目录
                exe_dir = Path(__file__).parent.parent.parent.parent
            
            update_dir = exe_dir / 'updates'
            update_dir.mkdir(exist_ok=True)
            
            new_exe_path = update_dir / 'local_agent_new.exe'
            
            if not await self._download_file(full_download_url, new_exe_path):
                # 存储更新失败时间
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', '文件下载失败', 'update_status')
                self.logger.info(f"已记录下载失败时间: {current_time}")
                return {'success': False, 'error': '下载失败'}
            
            # 2. 校验MD5
            if not self._verify_md5(new_exe_path, expected_md5):
                # 存储更新失败时间
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', 'MD5校验失败', 'update_status')
                self.logger.info(f"已记录MD5校验失败时间: {current_time}")
                return {'success': False, 'error': 'MD5校验失败'}
            
            # 3. 创建备份
            backup_path = self._create_backup(self.current_exe_path)
            if not backup_path:
                # 存储更新失败时间
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', '备份创建失败', 'update_status')
                self.logger.info(f"已记录备份失败时间: {current_time}")
                return {'success': False, 'error': '备份创建失败'}
            
            # 4. 执行批处理更新
            if not self._execute_batch_file(new_exe_path, backup_path):
                # 存储更新失败时间
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', '批处理执行失败', 'update_status')
                self.logger.info(f"已记录批处理执行失败时间: {current_time}")
                return {'success': False, 'error': '批处理执行失败'}
            
            # 更新成功，但进程即将被杀死
            return {
                'success': True,
                'message': '更新流程已启动，进程即将终止',
                'new_exe_path': str(new_exe_path),
                'backup_path': str(backup_path)
            }
            
        except Exception as e:
            self._update_error('unknown', f'更新流程异常: {str(e)}')
            # 存储更新异常时间
            current_time = time.time()
            set_persistent_data('last_update_failure_time', current_time, 'update_status')
            set_persistent_data('last_update_error', str(e), 'update_status')
            self.logger.info(f"已记录更新异常时间: {current_time}")
            return {'success': False, 'error': str(e)}
    
    def perform_update_sync(self, expected_md5: str, download_url: str) -> Dict[str, Any]:
        """同步执行自更新流程"""
        # 在同步环境中运行异步函数
        try:
            # 检查是否已经存在事件循环
            try:
                loop = asyncio.get_event_loop()
                # 如果已经存在事件循环，使用run_coroutine_threadsafe
                if loop.is_running():
                    # 在已经运行的事件循环中，我们需要使用不同的策略
                    # 这里我们创建一个新的事件循环来运行异步任务
                    import threading
                    
                    result = None
                    exception = None
                    
                    def run_in_thread():
                        nonlocal result, exception
                        try:
                            # 创建新的事件循环
                            self.logger.info("创建新的事件循环以运行异步任务")
                            import asyncio as async_lib
                            new_loop = async_lib.new_event_loop()
                            async_lib.set_event_loop(new_loop)
                            result = new_loop.run_until_complete(self.perform_update(expected_md5, download_url))
                        except Exception as e:
                            exception = e
                        finally:
                            if 'new_loop' in locals() and new_loop:
                                new_loop.close()
                    
                    # 在新线程中运行
                    thread = threading.Thread(target=run_in_thread)
                    thread.start()
                    thread.join()
                    
                    if exception:
                        raise exception
                    return result
                else:
                    # 使用现有的事件循环
                    self.logger.info("使用已存在的事件循环运行异步任务")
                    return loop.run_until_complete(self.perform_update(expected_md5, download_url))
            except RuntimeError:
                # 没有事件循环，创建新的
                return asyncio.run(self.perform_update(expected_md5, download_url))
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def check_update(self, download_url: str) -> Dict[str, Any]:
        """检查更新（异步）"""
        try:
            # 这里可以实现版本检查逻辑
            # 目前简单返回可更新状态
            return {
                'success': True,
                'update_available': True,
                'message': '可以执行更新'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# 便捷函数
def perform_update_async(expected_md5: str, download_url: str) -> Dict[str, Any]:
    """异步执行自更新的便捷函数"""
    updater = AutoUpdater()
    return asyncio.run(updater.perform_update(expected_md5, download_url))


def perform_update_sync(expected_md5: str, download_url: str) -> Dict[str, Any]:
    """同步执行自更新的便捷函数"""
    updater = AutoUpdater()
    return updater.perform_update_sync(expected_md5, download_url)