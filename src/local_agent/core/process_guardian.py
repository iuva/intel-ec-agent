#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
进程守护模块 - 实现保活机制
提供多层级监控、自动恢复和资源管理功能
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
    """进程守护类 - 实现顶尖保活机制"""
    
    def __init__(self, process_name: str, executable_path: str, working_dir: str):
        self.logger = get_logger(__name__)
        
        # 基础配置
        self.process_name = process_name
        self.executable_path = executable_path
        self.working_dir = working_dir
        
        # 状态管理
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False
        self._start_time: Optional[datetime] = None
        self._restart_count = 0
        self._last_health_check = datetime.now()
        
        # 保活配置
        self.max_restarts_per_hour = 5  # 每小时最大重启次数
        self.health_check_interval = 15  # 健康检查间隔(秒)
        self.restart_delay = 3  # 重启延迟(秒)
        self.max_memory_mb = 500  # 最大内存限制(MB)
        
        # 监控数据
        self._restart_history: List[datetime] = []
        self._health_stats: Dict[str, any] = {
            'memory_usage': [],
            'cpu_usage': [],
            'response_time': []
        }
        
        self.logger.info(f"进程守护初始化完成 - 目标进程: {process_name}")
    
    async def start(self) -> bool:
        """启动进程守护"""
        try:
            self.logger.info("启动进程守护...")
            
            # 启动目标进程
            if not await self._start_target_process():
                return False
            
            # 启动监控任务
            self._is_running = True
            asyncio.create_task(self._monitoring_loop())
            asyncio.create_task(self._health_check_loop())
            asyncio.create_task(self._resource_optimization_loop())
            
            self.logger.info("进程守护启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"进程守护启动失败: {e}")
            return False
    
    async def stop(self) -> bool:
        """停止进程守护"""
        try:
            self.logger.info("停止进程守护...")
            self._is_running = False
            
            # 优雅停止目标进程
            if self._process:
                try:
                    # 发送终止信号
                    self._process.terminate()
                    
                    # 等待进程退出
                    for _ in range(10):  # 最多等待10秒
                        if self._process.poll() is not None:
                            break
                        await asyncio.sleep(1)
                    
                    # 如果进程仍未退出，强制终止
                    if self._process.poll() is None:
                        self._process.kill()
                        
                except Exception as e:
                    self.logger.warning(f"停止进程时发生异常: {e}")
            
            self.logger.info("进程守护已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止进程守护失败: {e}")
            return False
    
    async def _start_target_process(self) -> bool:
        """启动目标进程"""
        try:
            # 检查重启频率限制
            if not self._check_restart_limit():
                self.logger.error("重启频率过高，暂停重启")
                return False
            
            # 清理旧进程（如果存在）
            await self._cleanup_orphaned_processes()
            
            # 启动新进程
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
            
            # 启动输出监控
            asyncio.create_task(self._monitor_process_output())
            
            self.logger.info(f"目标进程启动成功 (PID: {self._process.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"启动目标进程失败: {e}")
            return False
    
    async def _monitoring_loop(self):
        """进程监控循环"""
        while self._is_running:
            try:
                # 检查进程状态
                if self._process and self._process.poll() is not None:
                    self.logger.warning("目标进程已退出，准备重启...")
                    
                    # 等待一段时间后重启
                    await asyncio.sleep(self.restart_delay)
                    
                    # 重启进程
                    if not await self._start_target_process():
                        self.logger.error("重启目标进程失败")
                        break
                
                # 检查资源使用情况
                await self._check_resource_usage()
                
                # 每5秒检查一次
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(5)
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._is_running:
            try:
                # 执行健康检查
                health_status = await self._perform_health_check()
                
                if not health_status['healthy']:
                    self.logger.warning("健康检查失败，准备恢复...")
                    await self._recover_from_failure()
                
                # 更新最后检查时间
                self._last_health_check = datetime.now()
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"健康检查循环异常: {e}")
                await asyncio.sleep(30)
    
    async def _resource_optimization_loop(self):
        """资源优化循环"""
        while self._is_running:
            try:
                # 优化内存使用
                await self._optimize_memory_usage()
                
                # 清理临时文件
                await self._cleanup_temporary_files()
                
                # 每60秒执行一次优化
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"资源优化循环异常: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_check(self) -> Dict[str, any]:
        """执行健康检查"""
        health_status = {
            'healthy': True,
            'details': {},
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 检查进程状态
            if not self._process or self._process.poll() is not None:
                health_status['healthy'] = False
                health_status['details']['process'] = 'not_running'
                return health_status
            
            # 检查API接口响应
            api_healthy = await self._check_api_health()
            health_status['details']['api'] = api_healthy
            if not api_healthy:
                health_status['healthy'] = False
            
            # 检查内存使用
            memory_info = await self._get_memory_usage()
            health_status['details']['memory'] = memory_info
            if memory_info['percent'] > 80:  # 内存使用超过80%
                health_status['healthy'] = False
            
            # 检查响应时间
            response_time = await self._measure_response_time()
            health_status['details']['response_time'] = response_time
            if response_time > 5000:  # 响应时间超过5秒
                health_status['healthy'] = False
            
        except Exception as e:
            self.logger.error(f"健康检查异常: {e}")
            health_status['healthy'] = False
            health_status['details']['error'] = str(e)
        
        return health_status
    
    async def _check_api_health(self) -> bool:
        """检查API接口健康状态"""
        try:
            import aiohttp
            
            # 获取配置中的API端口
            api_host = self.config.get('api_host', 'localhost')
            api_port = self.config.get('api_port', 8000)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://{api_host}:{api_port}/health', timeout=10) as response:
                    return response.status == 200
        except:
            return False
    
    async def _get_memory_usage(self) -> Dict[str, float]:
        """获取内存使用情况"""
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
        """测量API响应时间"""
        try:
            import aiohttp
            import time
            
            # 获取配置中的API端口
            api_host = self.config.get('api_host', 'localhost')
            api_port = self.config.get('api_port', 8000)
            
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://{api_host}:{api_port}/health', timeout=5) as response:
                    if response.status == 200:
                        return (time.time() - start_time) * 1000  # 转换为毫秒
        except:
            pass
        
        return float('inf')  # 返回无限大表示失败
    
    async def _recover_from_failure(self):
        """从故障中恢复"""
        try:
            self.logger.info("执行故障恢复流程...")
            
            # 1. 优雅停止当前进程
            await self.stop()
            
            # 2. 清理资源
            await self._cleanup_resources()
            
            # 3. 等待恢复冷却
            await asyncio.sleep(self.restart_delay)
            
            # 4. 重新启动
            await self._start_target_process()
            
            self.logger.info("故障恢复完成")
            
        except Exception as e:
            self.logger.error(f"故障恢复失败: {e}")
    
    def _check_restart_limit(self) -> bool:
        """检查重启频率限制"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # 统计过去一小时内的重启次数
        recent_restarts = [rt for rt in self._restart_history if rt > hour_ago]
        
        if len(recent_restarts) >= self.max_restarts_per_hour:
            self.logger.error(f"重启频率过高: {len(recent_restarts)}次/小时")
            return False
        
        return True
    
    async def _cleanup_orphaned_processes(self):
        """清理孤儿进程"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # 查找同名的孤儿进程
                    if (proc.info['name'] and 
                        self.process_name.lower() in proc.info['name'].lower() and
                        proc.pid != os.getpid() and
                        (not self._process or proc.pid != self._process.pid)):
                        
                        self.logger.warning(f"发现孤儿进程 PID: {proc.pid}，正在清理...")
                        proc.terminate()
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        except Exception as e:
            self.logger.warning(f"清理孤儿进程时发生异常: {e}")
    
    async def _check_resource_usage(self):
        """检查资源使用情况"""
        try:
            if self._process:
                process = psutil.Process(self._process.pid)
                
                # 检查内存使用
                memory_mb = process.memory_info().rss / 1024 / 1024
                if memory_mb > self.max_memory_mb:
                    self.logger.warning(f"内存使用过高: {memory_mb:.1f}MB，超过限制 {self.max_memory_mb}MB")
                    
                    # 触发内存优化
                    await self._optimize_memory_usage()
                
                # 检查CPU使用
                cpu_percent = process.cpu_percent()
                if cpu_percent > 80:  # CPU使用超过80%
                    self.logger.warning(f"CPU使用过高: {cpu_percent}%")
                    
        except Exception as e:
            self.logger.warning(f"检查资源使用异常: {e}")
    
    async def _optimize_memory_usage(self):
        """优化内存使用"""
        try:
            # 强制垃圾回收
            import gc
            gc.collect()
            
            # 清理缓存
            import sys
            if hasattr(sys, 'getobjects'):
                # 清理循环引用
                gc.collect(2)  # 深度清理
            
            self.logger.debug("内存优化完成")
            
        except Exception as e:
            self.logger.warning(f"内存优化异常: {e}")
    
    async def _cleanup_temporary_files(self):
        """清理临时文件"""
        try:
            import tempfile
            import glob
            
            # 清理临时目录中的旧文件
            temp_dir = tempfile.gettempdir()
            pattern = os.path.join(temp_dir, f"{self.process_name}_*")
            
            for temp_file in glob.glob(pattern):
                try:
                    if os.path.isfile(temp_file):
                        # 只删除超过1小时的文件
                        file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(temp_file))
                        if file_age.total_seconds() > 3600:
                            os.remove(temp_file)
                            self.logger.debug(f"清理临时文件: {temp_file}")
                except:
                    pass
                    
        except Exception as e:
            self.logger.warning(f"清理临时文件异常: {e}")
    
    async def _cleanup_resources(self):
        """清理资源"""
        await self._cleanup_temporary_files()
        await self._cleanup_orphaned_processes()
    
    async def _monitor_process_output(self):
        """监控进程输出"""
        if not self._process:
            return
        
        try:
            # 监控标准输出
            if self._process.stdout:
                for line in iter(self._process.stdout.readline, b''):
                    if line:
                        self.logger.info(f"[进程输出] {line.decode().strip()}")
            
            # 监控标准错误
            if self._process.stderr:
                for line in iter(self._process.stderr.readline, b''):
                    if line:
                        self.logger.error(f"[进程错误] {line.decode().strip()}")
                        
        except Exception as e:
            self.logger.warning(f"监控进程输出异常: {e}")
    
    def get_status(self) -> Dict[str, any]:
        """获取守护状态"""
        return {
            'running': self._is_running,
            'process_pid': self._process.pid if self._process else None,
            'restart_count': self._restart_count,
            'start_time': self._start_time.isoformat() if self._start_time else None,
            'uptime': (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        }


def create_process_guardian(process_name: str, executable_path: str, working_dir: str) -> ProcessGuardian:
    """创建进程守护实例"""
    return ProcessGuardian(process_name, executable_path, working_dir)