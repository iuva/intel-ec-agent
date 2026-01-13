#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-update manager
Supports synchronous and asynchronous calls, integrates download, MD5 verification, backup, and batch execution functionality
"""

import sys
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from ..logger import get_logger

# [Import] utility classes
from local_agent.utils.file_downloader import FileDownloader
from local_agent.utils.verify_md5 import calculate_md5
from local_agent.utils.http_client import http_client
from local_agent.utils.file_utils import FileUtils
from local_agent.core.tray_api import agent_update


class AutoUpdater:
    """[Auto] update management [manager] class"""
    
    def __init__(self):
        """Initialize [auto] update management [manager]"""
        self.logger = get_logger()
        
        # [Use] path utility class [to get] paths
        from ..utils.path_utils import get_root_path, get_current_executable_path
        
        self.scripts_dir = get_root_path()
        self.current_exe_path = get_current_executable_path()
        
        # [Batch] file path
        self.batch_file = self.scripts_dir / "automatic_update.bat"
        
        # Downloader [instance]
        self.downloader = FileDownloader()
        
        # Update status
        self.update_status = {
            'stage': 'idle',
            'progress': 0,
            'message': '',
            'error': None
        }
    
    def _update_progress(self, stage: str, progress: int, message: str = ''):
        """Update [progress status]"""
        self.update_status = {
            'stage': stage,
            'progress': progress,
            'message': message,
            'error': None
        }
        self.logger.info(f"[{stage}] {progress}% - {message}")
    
    def _update_error(self, stage: str, error: str):
        """Update error [status]"""
        self.update_status = {
            'stage': stage,
            'progress': 0,
            'message': '',
            'error': error
        }
        self.logger.error(f"[{stage}] Error: {error}")
    
    async def _download_file(self, url: str, save_path: Path) -> bool:
        """Asynchronous [download file]"""
        try:
            self._update_progress('downloading', 0, 'Starting download of update file')
            
            success = await self.downloader.download(url, str(save_path))
            
            if success:
                self._update_progress('downloading', 100, 'Download completed')
                return True
            else:
                self._update_error('downloading', 'File download failed')
                return False
                
        except Exception as e:
            self._update_error('downloading', f'Download exception: {str(e)}')
            return False
    
    def _verify_md5(self, file_path: Path, expected_md5: str) -> bool:
        """Validate [file] MD5 [checksum]"""
        try:
            self._update_progress('verifying', 0, 'Starting file integrity verification')
            
            if not file_path.exists():
                self._update_error('verifying', 'File does not exist')
                return False
            
            actual_md5 = calculate_md5(str(file_path))
            
            if actual_md5.lower() == expected_md5.lower():
                self._update_progress('verifying', 100, f'File integrity verification passed: expected {expected_md5}, actual {actual_md5}')
                return True
            else:
                self._update_error('verifying', f'MD5 verification failed: expected {expected_md5}, actual {actual_md5}')
                return False 
                
        except Exception as e:
            self._update_error('verifying', f'Verification exception: {str(e)}')
            return False
    
    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Create [file backup]"""
        try:
            self._update_progress('backup', 0, 'Starting backup creation')
            
            if not file_path.exists():
                self._update_error('backup', 'File to backup does not exist')
                return None
            
            # Create backup directory
            backup_dir = file_path.parent / 'backup'
            backup_dir.mkdir(exist_ok=True)
            
            # [Generate] timestamped [backup file name]
            import time
            timestamp = int(time.time())
            backup_name = f"{file_path.name}.backup.{timestamp}"
            backup_path = backup_dir / backup_name
            
            # [Copy] file
            shutil.copy2(str(file_path), str(backup_path))
            
            if backup_path.exists():
                self._update_progress('backup', 100, f'Backup created successfully: {backup_path}')
                return backup_path
            else:
                self._update_error('backup', 'Backup file creation failed')
                return None
                
        except Exception as e:
            self._update_error('backup', f'Backup exception: {str(e)}')
            return None
    
    def _execute_batch_file(self, new_exe_path: Path, backup_path: Path) -> bool:
        """Execute [batch file for] update"""
        try:
            self._update_progress('executing', 0, 'Preparing to execute update script')
            
            FileUtils.extract_file_from_scripts('automatic_update.bat', overwrite=True)
            
            if not self.batch_file.exists():
                self._update_error('executing', f'Batch file does not exist: {self.batch_file}')
                return False
            
            if not new_exe_path.exists():
                self._update_error('executing', f'New version file does not exist: {new_exe_path}')
                return False
            
            # [Build batch] parameters
            # Parameter [format]: Service [name] ([empty]) [new] exe path [old] exe path backup directory
            service_name = "LocalAgentService"
            old_exe_path = self.current_exe_path
            # Backup directory [always uses the] backup [folder under the same directory as the exe]
            backup_dir = old_exe_path.parent / 'backup'
            
            # [Build command]
            import subprocess
            cmd = [
                str(self.batch_file),
                service_name,
                str(new_exe_path),
                str(old_exe_path),
                str(backup_dir)
            ]
            
            self.logger.info(f"Executing batch command: {' '.join(cmd)}")

            agent_update(f'start "" /B cmd /c "{" ".join(cmd)}"')
            
            # [Give batch] process [more] execution time, [ensure] update [script can fully] execute
            import time
            time.sleep(25)
            
            self._update_progress('executing', 100, 'Update script started, process will terminate soon')
            
            # [Note]: [Will not] wait [for batch to] complete, [because batch] will kill current process
            # [Use] start [command to ensure batch] process [is completely independent], [not affected by current] process [termination]
            return True
            
        except Exception as e:
            self._update_error('executing', f'Batch execution exception: {str(e)}')
            return False
    
    async def perform_update(self, expected_md5: str, download_url: str) -> Dict[str, Any]:
        import time
        from local_agent.core.persistent_storage import set_persistent_data
        try:
            self._update_progress('starting', 0, 'Starting auto-update process')
            
            # [Build complete] download URL
            full_download_url = http_client._build_file_url(download_url)
            
            # 1. Download update file - Download [to] exe [directory to avoid] permission [issues]
            # [Determine if it's a packaged] environment
            if getattr(sys, 'frozen', False):
                # [Packaged] environment: [use] exe [directory]
                exe_dir = Path(sys.executable).parent
            else:
                # [Development] environment: [use] project [root directory]
                exe_dir = Path(__file__).parent.parent.parent.parent
            
            update_dir = exe_dir / 'updates'
            update_dir.mkdir(exist_ok=True)
            
            new_exe_path = update_dir / 'local_agent_new.exe'
            
            if not await self._download_file(full_download_url, new_exe_path):
                # [Store] update failure time
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', 'File download failed', 'update_status')
                self.logger.info(f"Recorded download failure time: {current_time}")
                return {'success': False, 'error': 'Download failed'}
            
            # 2. [Verify] MD5
            if not self._verify_md5(new_exe_path, expected_md5):
                # [Store] update failure time
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', 'MD5 verification failed', 'update_status')
                self.logger.info(f"Recorded MD5 verification failure time: {current_time}")
                return {'success': False, 'error': 'MD5 verification failed'}
            
            # 3. Create backup
            backup_path = self._create_backup(self.current_exe_path)
            if not backup_path:
                # [Store] update failure time
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', 'Backup creation failed', 'update_status')
                self.logger.info(f"Recorded backup failure time: {current_time}")
                return {'success': False, 'error': 'Backup creation failed'}
            
            # 4. Execute [batch] update
            if not self._execute_batch_file(new_exe_path, backup_path):
                # [Store] update failure time
                current_time = time.time()
                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                set_persistent_data('last_update_error', 'Batch execution failed', 'update_status')
                self.logger.info(f"Recorded batch execution failure time: {current_time}")
                return {'success': False, 'error': 'Batch execution failed'}
            
            # Update success, [but] process [will be killed soon]
            return {
                'success': True,
                'message': 'Update process started, process will terminate soon',
                'new_exe_path': str(new_exe_path),
                'backup_path': str(backup_path)
            }
            
        except Exception as e:
            self._update_error('unknown', f'Update process exception: {str(e)}')
            # [Store] update exception time
            current_time = time.time()
            set_persistent_data('last_update_failure_time', current_time, 'update_status')
            set_persistent_data('last_update_error', str(e), 'update_status')
            self.logger.info(f"Recorded update exception time: {current_time}")
            return {'success': False, 'error': str(e)}
    
    def perform_update_sync(self, expected_md5: str, download_url: str) -> Dict[str, Any]:
        """Synchronous execute [auto] update [process]"""
        # [Run] asynchronous function [in] synchronous environment
        try:
            # Check [if event] loop [already exists]
            try:
                loop = asyncio.get_event_loop()
                # If [event] loop [already exists], [use] run_coroutine_threadsafe
                if loop.is_running():
                    # [In a running event] loop, [we need to use a different strategy]
                    # [Here we] create [a new event] loop [to run] asynchronous [tasks]
                    import threading
                    
                    result = None
                    exception = None
                    
                    def run_in_thread():
                        nonlocal result, exception
                        try:
                            # Create [new event] loop
                            self.logger.info("Creating new event loop to run async task")
                            import asyncio as async_lib
                            new_loop = async_lib.new_event_loop()
                            async_lib.set_event_loop(new_loop)
                            result = new_loop.run_until_complete(self.perform_update(expected_md5, download_url))
                        except Exception as e:
                            exception = e
                        finally:
                            if 'new_loop' in locals() and new_loop:
                                new_loop.close()
                    
                    # [Run in new] thread
                    thread = threading.Thread(target=run_in_thread)
                    thread.start()
                    thread.join()
                    
                    if exception:
                        raise exception
                    return result
                else:
                    # [Use existing event] loop
                    self.logger.info("Using existing event loop to run async task")
                    return loop.run_until_complete(self.perform_update(expected_md5, download_url))
            except RuntimeError:
                # [No event] loop, create [new one]
                return asyncio.run(self.perform_update(expected_md5, download_url))
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def check_update(self, download_url: str) -> Dict[str, Any]:
        """Check update (asynchronous)"""
        try:
            # [Here can implement] version check [logic]
            # [Currently] simply [return] update status
            return {
                'success': True,
                'update_available': True,
                'message': 'Update can be performed'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# [Convenience] functions
def perform_update_async(expected_md5: str, download_url: str) -> Dict[str, Any]:
    """Asynchronous execute [auto] update [convenience] function"""
    updater = AutoUpdater()
    return asyncio.run(updater.perform_update(expected_md5, download_url))


def perform_update_sync(expected_md5: str, download_url: str) -> Dict[str, Any]:
    """Synchronous execute [auto] update [convenience] function"""
    updater = AutoUpdater()
    return updater.perform_update_sync(expected_md5, download_url)