#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process guardian module - Implements keep-alive mechanism
Provides multi-level monitoring, automatic recovery, and resource management functionality
"""

import asyncio
import os
import psutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..logger import get_logger


class ProcessGuardian:
    """Process guardian class - Implements top-tier keep-alive mechanism"""
    
    def __init__(self, process_name: str, executable_path: str, working_dir: str):
        self.logger = get_logger(__name__)
        
        # basicConfiguration
        self.process_name = process_name
        self.executable_path = executable_path
        self.working_dir = working_dir
        
        # Statusmanagement
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False
        self._start_time: Optional[datetime] = None
        self._restart_count = 0
        self._last_health_check = datetime.now()
        
        # Keep-alive configuration
        self.max_restarts_per_hour = 5  # Maximum restarts per hour
        self.health_check_interval = 15  # Health check interval (seconds)
        self.restart_delay = 3  # Restart delay (seconds)
        self.max_memory_mb = 500  # Maximum memory limit (MB)
        
        # Monitoring data
        self._restart_history: List[datetime] = []
        self._health_stats: Dict[str, any] = {
            'memory_usage': [],
            'cpu_usage': [],
            'response_time': []
        }
        
        self.logger.info(f"Process guardian initialized - target process: {process_name}")
    
    async def start(self) -> bool:
        """Start process guardian"""
        try:
            self.logger.info("Starting process guardian...")
            
            # Start target process
            if not await self._start_target_process():
                return False
            
            # Start monitoring tasks
            self._is_running = True
            asyncio.create_task(self._monitoring_loop())
            asyncio.create_task(self._health_check_loop())
            asyncio.create_task(self._resource_optimization_loop())
            
            self.logger.info("Process guardian started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Process guardian startup failed: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop process guardian"""
        try:
            self.logger.info("Stopping process guardian...")
            self._is_running = False
            
            # Gracefully stop target process
            if self._process:
                try:
                    # Send termination signal
                    self._process.terminate()
                    
                    # Wait for process to exit
                    for _ in range(10):  # Wait up to 10 seconds
                        if self._process.poll() is not None:
                            break
                        await asyncio.sleep(1)
                    
                    # If process still not exited, force terminate
                    if self._process.poll() is None:
                        self._process.kill()
                        
                except Exception as e:
                    self.logger.warning(f"Exception occurred while stopping process: {e}")
            
            self.logger.info("Process guardian has stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Stop process guardian failed: {e}")
            return False
    
    async def _start_target_process(self) -> bool:
        """Start target process"""
        try:
            # Check restart frequency limit
            if not self._check_restart_limit():
                self.logger.error("Restart frequency too high, pausing restart")
                return False
            
            # Clean up old process (if exists)
            await self._cleanup_orphaned_processes()
            
            # Start new process
            self._process = subprocess.Popen(
                [sys.executable, self.executable_path],
                cwd=self.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            self._start_time = datetime.now()
            self._restart_count += 1
            self._restart_history.append(datetime.now())
            
            # Start output monitoring
            asyncio.create_task(self._monitor_process_output())
            
            self.logger.info(f"Target process started successfully (PID: {self._process.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"Start target process failed: {e}")
            return False
    
    async def _monitoring_loop(self):
        """Process monitoring loop"""
        while self._is_running:
            try:
                # Check process status
                if self._process and self._process.poll() is not None:
                    self.logger.warning("Target process has exited, preparing to restart...")
                    
                    # Wait for a period of time before restart
                    await asyncio.sleep(self.restart_delay)
                    
                    # Restart process
                    if not await self._start_target_process():
                        self.logger.error("Restart target process failed")
                        break
                
                # Check resource usage
                await self._check_resource_usage()
                
                # Check every 5 seconds
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop exception: {e}")
                await asyncio.sleep(5)
    
    async def _health_check_loop(self):
        """Health check loop"""
        while self._is_running:
            try:
                # Execute health check
                health_status = await self._perform_health_check()
                
                if not health_status['healthy']:
                    self.logger.warning("Health check failed, preparing to recover...")
                    await self._recover_from_failure()
                
                # Update last check time
                self._last_health_check = datetime.now()
                
                # Check every 30 seconds
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Health check loop exception: {e}")
                await asyncio.sleep(30)
    
    async def _resource_optimization_loop(self):
        """Resource optimization loop"""
        while self._is_running:
            try:
                # Optimize memory usage
                await self._optimize_memory_usage()
                
                # Clean up temporary files
                await self._cleanup_temporary_files()
                
                # Execute optimization every 60 seconds
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Resource optimization loop exception: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_check(self) -> Dict[str, any]:
        """Execute health check"""
        health_status = {
            'healthy': True,
            'details': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check process status
            if not self._process or self._process.poll() is not None:
                health_status['healthy'] = False
                health_status['details']['process'] = 'not_running'
                return health_status
            
            # Check API interface response
            api_healthy = await self._check_api_health()
            health_status['details']['api'] = api_healthy
            if not api_healthy:
                health_status['healthy'] = False
            
            # Check memory usage
            memory_info = await self._get_memory_usage()
            health_status['details']['memory'] = memory_info
            if memory_info['percent'] > 80:  # Memory usage exceeds 80%
                health_status['healthy'] = False
            
            # Check response time
            response_time = await self._measure_response_time()
            health_status['details']['response_time'] = response_time
            if response_time > 5000:  # Response time exceeds 5 seconds
                health_status['healthy'] = False
            
        except Exception as e:
            self.logger.error(f"Health check exception: {e}")
            health_status['healthy'] = False
            health_status['details']['error'] = str(e)
        
        return health_status
    
    async def _check_api_health(self) -> bool:
        """Check API interface health status"""
        try:
            import aiohttp
            
            # Get API port from configuration
            api_host = self.config.get('api_host', 'localhost')
            api_port = self.config.get('api_port', 8000)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://{api_host}:{api_port}/health', timeout=10) as response:
                    return response.status == 200
        except:
            return False
    
    async def _get_memory_usage(self) -> Dict[str, float]:
        """Get memory usage"""
        try:
            if self._process:
                process = psutil.Process(self._process.pid)
                memory_info = process.memory_info()
                
                return {
                    'rss_mb': memory_info.rss / 1024 / 1024,
                    'percent': process.memory_percent()
                }
        except:
            pass
        
        return {'rss_mb': 0, 'percent': 0}
    
    async def _measure_response_time(self) -> float:
        """Measure API response time"""
        try:
            import aiohttp
            import time
            
            # Get API port from configuration
            api_host = self.config.get('api_host', 'localhost')
            api_port = self.config.get('api_port', 8000)
            
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://{api_host}:{api_port}/health', timeout=5) as response:
                    if response.status == 200:
                        return (time.time() - start_time) * 1000  # Convert to milliseconds
        except:
            pass
        
        return float('inf')  # Return infinity to indicate failure
    
    async def _recover_from_failure(self):
        """Recover from failure"""
        try:
            self.logger.info("Executing fault recovery process...")
            
            # 1. Gracefully stop current process
            await self.stop()
            
            # 2. Clean up resources
            await self._cleanup_resources()
            
            # 3. Wait for recovery cooldown
            await asyncio.sleep(self.restart_delay)
            
            # 4. Restart
            await self._start_target_process()
            
            self.logger.info("Fault recovery completed")
            
        except Exception as e:
            self.logger.error(f"Fault recovery failed: {e}")
    
    def _check_restart_limit(self) -> bool:
        """Check restart frequency limit"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # Count restart times in the past hour
        recent_restarts = [rt for rt in self._restart_history if rt > hour_ago]
        
        if len(recent_restarts) >= self.max_restarts_per_hour:
            self.logger.error(f"Restart frequency too high: {len(recent_restarts)} times/hour")
            return False
        
        return True
    
    async def _cleanup_orphaned_processes(self):
        """Clean up orphaned processes"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Find orphaned processes with the same name
                    if (proc.info['name'] and 
                        self.process_name.lower() in proc.info['name'].lower() and
                        proc.pid != os.getpid() and
                        (not self._process or proc.pid != self._process.pid)):
                        
                        self.logger.warning(f"Found orphaned process PID: {proc.pid}, cleaning up...")
                        proc.terminate()
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        except Exception as e:
            self.logger.warning(f"Exception occurred while cleaning up orphaned processes: {e}")
    
    async def _check_resource_usage(self):
        """Check resource usage"""
        try:
            if self._process:
                process = psutil.Process(self._process.pid)
                
                # Check memory usage
                memory_mb = process.memory_info().rss / 1024 / 1024
                if memory_mb > self.max_memory_mb:
                    self.logger.warning(f"Memory usage too high: {memory_mb:.1f}MB, exceeds limit {self.max_memory_mb}MB")
                    
                    # Trigger memory optimization
                    await self._optimize_memory_usage()
                
                # Check CPU usage
                cpu_percent = process.cpu_percent()
                if cpu_percent > 80:  # CPU usage exceeds 80%
                    self.logger.warning(f"CPU usage too high: {cpu_percent}%")
                    
        except Exception as e:
            self.logger.warning(f"Exception occurred while checking resource usage: {e}")
    
    async def _optimize_memory_usage(self):
        """Optimize memory usage"""
        try:
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clean up cache
            import sys
            if hasattr(sys, 'getobjects'):
                # Clean up loop references
                gc.collect(2)  # Deep cleanup
            
            self.logger.debug("Memory optimization completed")
            
        except Exception as e:
            self.logger.warning(f"Memory optimization exception: {e}")
    
    async def _cleanup_temporary_files(self):
        """Clean up temporary files"""
        try:
            import tempfile
            import glob
            
            # Clean up old files in temporary directory
            temp_dir = tempfile.gettempdir()
            pattern = os.path.join(temp_dir, f"{self.process_name}_*")
            
            for temp_file in glob.glob(pattern):
                try:
                    if os.path.isfile(temp_file):
                        # Only delete files older than 1 hour
                        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(temp_file))
                        if file_age.total_seconds() > 3600:
                            os.remove(temp_file)
                            self.logger.debug(f"Cleaning up temporary file: {temp_file}")
                except:
                    pass
                    
        except Exception as e:
            self.logger.warning(f"Exception occurred while cleaning up temporary files: {e}")
    
    async def _cleanup_resources(self):
        """Clean up resources"""
        await self._cleanup_temporary_files()
        await self._cleanup_orphaned_processes()
    
    async def _monitor_process_output(self):
        """Monitor process output"""
        if not self._process:
            return
        
        try:
            # Monitor standard output
            if self._process.stdout:
                for line in iter(self._process.stdout.readline, b''):
                    if line:
                        self.logger.info(f"[Process Output] {line.decode().strip()}")
            
            # Monitor standard error
            if self._process.stderr:
                for line in iter(self._process.stderr.readline, b''):
                    if line:
                        self.logger.error(f"[Process Error] {line.decode().strip()}")
                        
        except Exception as e:
            self.logger.warning(f"Exception occurred while monitoring process output: {e}")
    
    def get_status(self) -> Dict[str, any]:
        """Get guardian status"""
        return {
            'running': self._is_running,
            'process_pid': self._process.pid if self._process else None,
            'restart_count': self._restart_count,
            'start_time': self._start_time.isoformat() if self._start_time else None,
            'uptime': (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        }


def create_process_guardian(process_name: str, executable_path: str, working_dir: str) -> ProcessGuardian:
    """Create process guardian instance"""
    return ProcessGuardian(process_name, executable_path, working_dir)