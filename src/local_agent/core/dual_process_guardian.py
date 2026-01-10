#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual process mutual monitoring and keep-alive mechanism
Implements mutual monitoring between two processes
"""

import asyncio
import os
import psutil
import signal
import subprocess
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from ..logger import get_logger


class DualProcessGuardian:
    """[Dual] process [mutual monitoring guardian] class"""
    
    def __init__(self, process_a_config: Dict, process_b_config: Dict):
        self.logger = get_logger(__name__)
        
        # Process configuration
        self.process_a = process_a_config
        self.process_b = process_b_config
        
        # Process instance
        self._proc_a: Optional[subprocess.Popen] = None
        self._proc_b: Optional[subprocess.Popen] = None
        
        # Status management
        self._is_running = False
        self._monitoring_tasks = []
        
        # Thread management
        self._monitor_thread: Optional[threading.Thread] = None
        self._health_check_thread: Optional[threading.Thread] = None
        self._stop_monitoring = False
        self._stop_health_check = False
        
        # [Mutual monitoring] configuration
        self.check_interval = 5  # Mutual monitoring check interval (seconds)
        self.restart_delay = 2    # Restart delay (seconds)
        self.max_restarts_per_hour = 10  # Maximum restart times per hour
        
        # Update [coordination] configuration
        self._update_in_progress = False  # Update in progress flag
        self._update_lock = asyncio.Lock()  # Update lock
        self.update_check_interval = 30  # Update check interval (seconds)
        
        # [Statistical] info
        self._restart_history = []
        self._last_check_time = datetime.now()
        
        self.logger.info("Dual process mutual monitoring guardian initialized")
    
    async def start(self) -> bool:
        """Start [dual] process [mutual monitoring]"""
        try:
            self.logger.info("Starting dual process mutual monitoring guardian...")
            
            # [Clean up possible old] processes
            await self._cleanup_orphaned_processes()
            
            # Start process A
            if not await self._start_process_a():
                self.logger.error("Start process A failed")
                return False
            
            # [Brief] delay [before] start process B
            await asyncio.sleep(1)
            
            # Start process B
            if not await self._start_process_b():
                self.logger.error("Start process B failed")
                await self._stop_process_a()
                return False
            
            # Start [mutual monitoring tasks]
            self._is_running = True
            self._monitoring_tasks = [
                asyncio.create_task(self._monitor_process_a()),
                asyncio.create_task(self._monitor_process_b()),
                asyncio.create_task(self._health_check_loop()),
                asyncio.create_task(self._update_coordination_loop())  # Add update coordination loop
            ]
            
            self.logger.info("Dual process mutual monitoring guardian started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Start dual process mutual monitoring failed: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop [dual] process [mutual monitoring]"""
        try:
            self.logger.info("Stopping dual process mutual monitoring guardian...")
            
            self._is_running = False
            
            # [Cancel monitoring tasks]
            for task in self._monitoring_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait [for tasks to] complete
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
            
            # Stop processes
            await self._stop_process_a()
            await self._stop_process_b()
            
            self.logger.info("Dual process mutual monitoring guardian has stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Stop dual process mutual monitoring failed: {e}")
            return False
    
    async def _start_process_a(self) -> bool:
        """Start process A"""
        try:
            self.logger.info("Starting process A...")
            
            self._proc_a = subprocess.Popen(
                [sys.executable, self.process_a['executable']],
                cwd=self.process_a['working_dir'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # Wait for process start
            await asyncio.sleep(2)
            
            # Validate process [started normally]
            if self._proc_a.poll() is not None:
                self.logger.error("Process A exited immediately after startup")
                return False
            
            self.logger.info(f"Process A started successfully (PID: {self._proc_a.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"Start process A failed: {e}")
            return False
    
    async def _start_process_b(self) -> bool:
        """startprocessB"""
        try:
            self.logger.info("Starting process B...")
            
            self._proc_b = subprocess.Popen(
                [sys.executable, self.process_b['executable']],
                cwd=self.process_b['working_dir'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # WaitProcessStart
            await asyncio.sleep(2)
            
            # Validate process [started normally]
            if self._proc_b.poll() is not None:
                self.logger.error("Process B exited immediately after startup")
                return False
            
            self.logger.info(f"Process B started successfully (PID: {self._proc_b.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"Start process B failed: {e}")
            return False
    
    async def _monitor_process_a(self):
        """[Monitor] process A ([executed by] process B)"""
        while self._is_running:
            try:
                # Check [if monitoring is paused]
                if getattr(self, '_monitoring_paused', False):
                    await asyncio.sleep(self.check_interval)
                    continue
                
                # Check process A status
                if not await self._check_process_alive(self._proc_a, "A"):
                    self.logger.warning("Process A abnormal, preparing to restart...")
                    
                    # Wait restart delay
                    await asyncio.sleep(self.restart_delay)
                    
                    # Restart process A
                    if not await self._restart_process_a():
                        self.logger.error("Restart process A failed")
                
                # Check [interval]
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Monitor process A exception: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _monitor_process_b(self):
        """[Monitor] process B ([executed by] process A)"""
        while self._is_running:
            try:
                # Check [if monitoring is paused]
                if getattr(self, '_monitoring_paused', False):
                    await asyncio.sleep(self.check_interval)
                    continue
                
                # Check process B status
                if not await self._check_process_alive(self._proc_b, "B"):
                    self.logger.warning("Process B abnormal, preparing to restart...")
                    
                    # Wait restart delay
                    await asyncio.sleep(self.restart_delay)
                    
                    # Restart process B
                    if not await self._restart_process_b():
                        self.logger.error("Restart process B failed")
                
                # Check [interval]
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"Monitor process B exception: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_process_alive(self, process: Optional[subprocess.Popen], process_name: str) -> bool:
        """Check process [is alive]"""
        if not process:
            return False
        
        try:
            # Check process status
            if process.poll() is not None:
                self.logger.warning(f"Process {process_name} has exited, exit code: {process.returncode}")
                return False
            
            # [Use] psutil [for further] validation
            try:
                psutil_process = psutil.Process(process.pid)
                if not psutil_process.is_running():
                    self.logger.warning(f"Process {process_name} (PID: {process.pid}) does not exist")
                    return False
                
                # Check process status
                status = psutil_process.status()
                if status == psutil.STATUS_ZOMBIE:
                    self.logger.warning(f"Process {process_name} is in zombie state")
                    return False
                
            except psutil.NoSuchProcess:
                self.logger.warning(f"Process {process_name} (PID: {process.pid}) does not exist")
                return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Check process {process_name} status exception: {e}")
            return False
    
    async def _restart_process_a(self) -> bool:
        """Restart process A"""
        try:
            # Check restart [frequency limit]
            if not self._check_restart_limit():
                self.logger.error("Restart frequency too high, pausing restart of process A")
                return False
            
            # Stop [old] process
            await self._stop_process_a()
            
            # Start [new] process
            return await self._start_process_a()
            
        except Exception as e:
            self.logger.error(f"Restart process A failed: {e}")
            return False
    
    async def _restart_process_b(self) -> bool:
        """Restart process B"""
        try:
            # Check restart [frequency limit]
            if not self._check_restart_limit():
                self.logger.error("Restart frequency too high, pausing restart of process B")
                return False
            
            # Stop [old] process
            await self._stop_process_b()
            
            # Start [new] process
            return await self._start_process_b()
            
        except Exception as e:
            self.logger.error(f"Restart process B failed: {e}")
            return False
    
    async def _stop_process_a(self):
        """Stop process A"""
        if self._proc_a:
            try:
                self.logger.info("Stopping process A...")
                
                # [Graceful termination]
                self._proc_a.terminate()
                
                # Wait for process [exit]
                for _ in range(5):
                    if self._proc_a.poll() is not None:
                        break
                    await asyncio.sleep(1)
                
                # [Force termination] (if [necessary])
                if self._proc_a.poll() is None:
                    self._proc_a.kill()
                
                self.logger.info("Process A has stopped")
                
            except Exception as e:
                self.logger.warning(f"Stop process A exception: {e}")
            finally:
                self._proc_a = None
    
    async def _stop_process_b(self):
        """Stop process B"""
        if self._proc_b:
            try:
                self.logger.info("Stopping process B...")
                
                # [Graceful termination]
                self._proc_b.terminate()
                
                # Wait for process [exit]
                for _ in range(5):
                    if self._proc_b.poll() is not None:
                        break
                    await asyncio.sleep(1)
                
                # [Force termination] (if [necessary])
                if self._proc_b.poll() is None:
                    self._proc_b.kill()
                
                self.logger.info("Process B has stopped")
                
            except Exception as e:
                self.logger.warning(f"Stop process B exception: {e}")
            finally:
                self._proc_b = None
    
    async def _health_check_loop(self):
        """[Health] check [loop]"""
        while self._is_running:
            try:
                # Check [both] processes' [health] status
                health_status = await self._perform_health_check()
                
                if not health_status['healthy']:
                    self.logger.warning("Health check failed, may need intervention")
                
                # [Every] 30 seconds check [once]
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Health check loop exception: {e}")
                await asyncio.sleep(30)
    
    async def _perform_health_check(self) -> Dict:
        """Execute [health] check"""
        health_status = {
            'healthy': True,
            'timestamp': datetime.now().isoformat(),
            'process_a': {'alive': False, 'pid': None},
            'process_b': {'alive': False, 'pid': None}
        }
        
        try:
            # Check process A
            if self._proc_a and await self._check_process_alive(self._proc_a, "A"):
                health_status['process_a']['alive'] = True
                health_status['process_a']['pid'] = self._proc_a.pid
            else:
                health_status['healthy'] = False
            
            # Check process B
            if self._proc_b and await self._check_process_alive(self._proc_b, "B"):
                health_status['process_b']['alive'] = True
                health_status['process_b']['pid'] = self._proc_b.pid
            else:
                health_status['healthy'] = False
            
        except Exception as e:
            self.logger.error(f"Perform health check exception: {e}")
            health_status['healthy'] = False
        
        return health_status
    
    def _check_restart_limit(self) -> bool:
        """Check restart [frequency limit]"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # [Count restart times in the past] hour
        recent_restarts = [rt for rt in self._restart_history if rt > hour_ago]
        
        if len(recent_restarts) >= self.max_restarts_per_hour:
            self.logger.error(f"Restart frequency too high: {len(recent_restarts)} times/hour")
            return False
        
        # [Record this] restart
        self._restart_history.append(now)
        
        # [Clean up expired] restart [records] ([keep recent] 24 hours)
        day_ago = now - timedelta(hours=24)
        self._restart_history = [rt for rt in self._restart_history if rt > day_ago]
        
        return True
    
    async def _cleanup_orphaned_processes(self):
        """[Clean up orphaned] processes"""
        try:
            process_names = [
                self.process_a.get('name', 'process_a'),
                self.process_b.get('name', 'process_b')
            ]
            
            current_pid = os.getpid()
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.pid == current_pid:
                        continue
                    
                    # Check process [name or command line matches]
                    proc_info = proc.info
                    cmdline = proc_info.get('cmdline', [])
                    
                    for process_name in process_names:
                        if (proc_info['name'] and process_name.lower() in proc_info['name'].lower()) or \
                           (cmdline and any(process_name.lower() in str(arg).lower() for arg in cmdline)):
                            
                            self.logger.warning(f"Found orphaned process PID: {proc.pid}, cleaning up...")
                            proc.terminate()
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        except Exception as e:
            self.logger.warning(f"Cleanup orphaned processes exception: {e}")
    
    def get_status(self) -> Dict:
        """Get [guardian status]"""
        return {
            'running': self._is_running,
            'process_a': {
                'pid': self._proc_a.pid if self._proc_a else None,
                'alive': self._proc_a and self._proc_a.poll() is None
            },
            'process_b': {
                'pid': self._proc_b.pid if self._proc_b else None,
                'alive': self._proc_b and self._proc_b.poll() is None
            },
            'restart_count': len(self._restart_history)
        }


    async def _update_coordination_loop(self):
        """Update [coordination loop] - [Detect] update [status and coordinate dual] process [behavior]"""
        while self._is_running:
            try:
                # Check [if there is] update in progress
                if await self._check_update_in_progress():
                    async with self._update_lock:
                        if not self._update_in_progress:
                            self.logger.info("Update in progress detected, pausing dual process keep-alive mechanism")
                            self._update_in_progress = True
                            
                            # [Pause] process [monitoring] ([but do not] stop process)
                            await self._pause_monitoring()
                else:
                    async with self._update_lock:
                        if self._update_in_progress:
                            self.logger.info("Update completed, resuming dual process keep-alive mechanism")
                            self._update_in_progress = False
                            
                            # [Resume] process [monitoring]
                            await self._resume_monitoring()
                
                # Update check [interval]
                await asyncio.sleep(self.update_check_interval)
                
            except Exception as e:
                self.logger.error(f"Update coordination loop exception: {e}")
                await asyncio.sleep(self.update_check_interval)
    
    async def _check_update_in_progress(self) -> bool:
        """Check [if there is] update [in progress]"""
        try:
            # Check VERSION file [if there is] update [marker]
            version_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "VERSION")
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    # If VERSION file [contains] update [marker or temporary] version [number]
                    if content.startswith("updating_") or ".tmp" in content:
                        return True
            
            # Check [if there are] update [related temporary] files
            temp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp")
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    if file.startswith("update_") or file.endswith(".tmp"):
                        return True
            
            # Check [if there are] update processes [running]
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline']).lower() if proc.info['cmdline'] else ''
                    if 'update' in cmdline and 'installer' in cmdline:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Check update status exception: {e}")
            return False
    
    async def _pause_monitoring(self):
        """[Pause] process [monitoring]"""
        try:
            # Setup [pause flag], [monitoring] loop [will detect this flag]
            self._monitoring_paused = True
            self.logger.info("Dual process monitoring has been paused")
            
            # [Record current] process status
            self._pre_update_state = self.get_status()
            
        except Exception as e:
            self.logger.error(f"Pause monitoring exception: {e}")
    
    async def _resume_monitoring(self):
        """[Resume] process [monitoring]"""
        try:
            # [Clear pause flag]
            self._monitoring_paused = False
            self.logger.info("Dual process monitoring has been resumed")
            
            # Check process status, [restart if] necessary
            await self._check_and_restart_after_update()
            
        except Exception as e:
            self.logger.error(f"Resume monitoring exception: {e}")
    
    async def _check_and_restart_after_update(self):
        """Update [post] check [and] restart process"""
        try:
            current_status = self.get_status()
            pre_update_state = getattr(self, '_pre_update_state', {})
            
            # Check process A [if needs] restart
            if not current_status['process_a']['alive'] and pre_update_state.get('process_a', {}).get('alive', False):
                self.logger.info("Process A abnormal after update, attempting restart")
                await self._restart_process_a()
            
            # Check process B [if needs] restart
            if not current_status['process_b']['alive'] and pre_update_state.get('process_b', {}).get('alive', False):
                self.logger.info("Process B abnormal after update, attempting restart")
                await self._restart_process_b()
            
            # [Clean up] pre-update [status]
            if hasattr(self, '_pre_update_state'):
                delattr(self, '_pre_update_state')
                
        except Exception as e:
            self.logger.error(f"Post-update check exception: {e}")
    
    def pause_for_update(self):
        """[Pause monitoring to perform] update"""
        try:
            self.logger.info("Dual process keep-alive mechanism: Pausing monitoring")
            
            # Setup update in progress [flag]
            self._update_in_progress = True
            
            # Stop [health] check
            if self._health_check_thread and self._health_check_thread.is_alive():
                self._stop_health_check = True
                self._health_check_thread.join(timeout=5)
                self.logger.info("Health check thread has stopped")
            
            # Stop process [monitoring]
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._stop_monitoring = True
                self._monitor_thread.join(timeout=5)
                self.logger.info("Process monitoring thread has stopped")
            
            self.logger.info("Dual process keep-alive monitoring has been paused")
            
        except Exception as e:
            self.logger.error(f"Pause monitoring failed: {str(e)}")
            # [Ensure flag is] set up
            self._update_in_progress = True
    
    def resume_after_update(self):
        """Update [completed, resume monitoring]"""
        try:
            self.logger.info("Dual process keep-alive mechanism: Resuming monitoring")
            
            # [Clear] update in progress [flag]
            self._update_in_progress = False
            
            # [Restart] health [check thread]
            if not self._health_check_thread or not self._health_check_thread.is_alive():
                self._stop_health_check = False
                self._health_check_thread = threading.Thread(
                    target=self._health_check_worker,
                    daemon=True
                )
                self._health_check_thread.start()
                self.logger.info("Health check thread has been restarted")
            
            # [Restart] process [monitoring] thread
            if not self._monitor_thread or not self._monitor_thread.is_alive():
                self._stop_monitoring = False
                self._monitor_thread = threading.Thread(
                    target=self._monitor_worker,
                    daemon=True
                )
                self._monitor_thread.start()
                self.logger.info("Process monitoring thread has been restarted")
            
            self.logger.info("Dual process keep-alive monitoring has been resumed")
            
        except Exception as e:
            self.logger.error(f"Resume monitoring failed: {str(e)}")
            # [Ensure flag is cleared]
            self._update_in_progress = False
    
    def is_update_in_progress(self) -> bool:
        """Check [if update is in] progress"""
        return self._update_in_progress


def create_dual_process_guardian(process_a_config: Dict, process_b_config: Dict) -> DualProcessGuardian:
    """Create [dual] process [mutual monitoring guardian instance]"""
    return DualProcessGuardian(process_a_config, process_b_config)