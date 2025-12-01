#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双进程互监控保活机制
实现两个进程互相监控
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
    """双进程互监控守护类"""
    
    def __init__(self, process_a_config: Dict, process_b_config: Dict):
        self.logger = get_logger(__name__)
        
        # 进程配置
        self.process_a = process_a_config
        self.process_b = process_b_config
        
        # 进程实例
        self._proc_a: Optional[subprocess.Popen] = None
        self._proc_b: Optional[subprocess.Popen] = None
        
        # 状态管理
        self._is_running = False
        self._monitoring_tasks = []
        
        # 线程管理
        self._monitor_thread: Optional[threading.Thread] = None
        self._health_check_thread: Optional[threading.Thread] = None
        self._stop_monitoring = False
        self._stop_health_check = False
        
        # 互监控配置
        self.check_interval = 5  # 互监控检查间隔(秒)
        self.restart_delay = 2    # 重启延迟(秒)
        self.max_restarts_per_hour = 10  # 每小时最大重启次数
        
        # 更新协调配置
        self._update_in_progress = False  # 更新进行中标志
        self._update_lock = asyncio.Lock()  # 更新锁
        self.update_check_interval = 30  # 更新检查间隔(秒)
        
        # 统计信息
        self._restart_history = []
        self._last_check_time = datetime.now()
        
        self.logger.info("双进程互监控守护初始化完成")
    
    async def start(self) -> bool:
        """启动双进程互监控"""
        try:
            self.logger.info("启动双进程互监控守护...")
            
            # 清理可能存在的旧进程
            await self._cleanup_orphaned_processes()
            
            # 启动进程A
            if not await self._start_process_a():
                self.logger.error("启动进程A失败")
                return False
            
            # 短暂延迟后启动进程B
            await asyncio.sleep(1)
            
            # 启动进程B
            if not await self._start_process_b():
                self.logger.error("启动进程B失败")
                await self._stop_process_a()
                return False
            
            # 启动互监控任务
            self._is_running = True
            self._monitoring_tasks = [
                asyncio.create_task(self._monitor_process_a()),
                asyncio.create_task(self._monitor_process_b()),
                asyncio.create_task(self._health_check_loop()),
                asyncio.create_task(self._update_coordination_loop())  # 添加更新协调循环
            ]
            
            self.logger.info("双进程互监控守护启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"启动双进程互监控失败: {e}")
            return False
    
    async def stop(self) -> bool:
        """停止双进程互监控"""
        try:
            self.logger.info("停止双进程互监控守护...")
            
            self._is_running = False
            
            # 取消监控任务
            for task in self._monitoring_tasks:
                if not task.done():
                    task.cancel()
            
            # 等待任务完成
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
            
            # 停止进程
            await self._stop_process_a()
            await self._stop_process_b()
            
            self.logger.info("双进程互监控守护已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止双进程互监控失败: {e}")
            return False
    
    async def _start_process_a(self) -> bool:
        """启动进程A"""
        try:
            self.logger.info("启动进程A...")
            
            self._proc_a = subprocess.Popen(
                [sys.executable, self.process_a['executable']],
                cwd=self.process_a['working_dir'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # 等待进程启动
            await asyncio.sleep(2)
            
            # 验证进程是否正常启动
            if self._proc_a.poll() is not None:
                self.logger.error("进程A启动后立即退出")
                return False
            
            self.logger.info(f"进程A启动成功 (PID: {self._proc_a.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"启动进程A失败: {e}")
            return False
    
    async def _start_process_b(self) -> bool:
        """启动进程B"""
        try:
            self.logger.info("启动进程B...")
            
            self._proc_b = subprocess.Popen(
                [sys.executable, self.process_b['executable']],
                cwd=self.process_b['working_dir'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            # 等待进程启动
            await asyncio.sleep(2)
            
            # 验证进程是否正常启动
            if self._proc_b.poll() is not None:
                self.logger.error("进程B启动后立即退出")
                return False
            
            self.logger.info(f"进程B启动成功 (PID: {self._proc_b.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"启动进程B失败: {e}")
            return False
    
    async def _monitor_process_a(self):
        """监控进程A（由进程B执行）"""
        while self._is_running:
            try:
                # 检查是否暂停监控
                if getattr(self, '_monitoring_paused', False):
                    await asyncio.sleep(self.check_interval)
                    continue
                
                # 检查进程A状态
                if not await self._check_process_alive(self._proc_a, "A"):
                    self.logger.warning("进程A异常，准备重启...")
                    
                    # 等待重启延迟
                    await asyncio.sleep(self.restart_delay)
                    
                    # 重启进程A
                    if not await self._restart_process_a():
                        self.logger.error("重启进程A失败")
                
                # 检查间隔
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"监控进程A异常: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _monitor_process_b(self):
        """监控进程B（由进程A执行）"""
        while self._is_running:
            try:
                # 检查是否暂停监控
                if getattr(self, '_monitoring_paused', False):
                    await asyncio.sleep(self.check_interval)
                    continue
                
                # 检查进程B状态
                if not await self._check_process_alive(self._proc_b, "B"):
                    self.logger.warning("进程B异常，准备重启...")
                    
                    # 等待重启延迟
                    await asyncio.sleep(self.restart_delay)
                    
                    # 重启进程B
                    if not await self._restart_process_b():
                        self.logger.error("重启进程B失败")
                
                # 检查间隔
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"监控进程B异常: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_process_alive(self, process: Optional[subprocess.Popen], process_name: str) -> bool:
        """检查进程是否存活"""
        if not process:
            return False
        
        try:
            # 检查进程状态
            if process.poll() is not None:
                self.logger.warning(f"进程{process_name}已退出，退出码: {process.returncode}")
                return False
            
            # 使用psutil进一步验证
            try:
                psutil_process = psutil.Process(process.pid)
                if not psutil_process.is_running():
                    self.logger.warning(f"进程{process_name} (PID: {process.pid}) 不存在")
                    return False
                
                # 检查进程状态
                status = psutil_process.status()
                if status == psutil.STATUS_ZOMBIE:
                    self.logger.warning(f"进程{process_name}处于僵尸状态")
                    return False
                
            except psutil.NoSuchProcess:
                self.logger.warning(f"进程{process_name} (PID: {process.pid}) 不存在")
                return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"检查进程{process_name}状态异常: {e}")
            return False
    
    async def _restart_process_a(self) -> bool:
        """重启进程A"""
        try:
            # 检查重启频率限制
            if not self._check_restart_limit():
                self.logger.error("重启频率过高，暂停重启进程A")
                return False
            
            # 停止旧进程
            await self._stop_process_a()
            
            # 启动新进程
            return await self._start_process_a()
            
        except Exception as e:
            self.logger.error(f"重启进程A失败: {e}")
            return False
    
    async def _restart_process_b(self) -> bool:
        """重启进程B"""
        try:
            # 检查重启频率限制
            if not self._check_restart_limit():
                self.logger.error("重启频率过高，暂停重启进程B")
                return False
            
            # 停止旧进程
            await self._stop_process_b()
            
            # 启动新进程
            return await self._start_process_b()
            
        except Exception as e:
            self.logger.error(f"重启进程B失败: {e}")
            return False
    
    async def _stop_process_a(self):
        """停止进程A"""
        if self._proc_a:
            try:
                self.logger.info("停止进程A...")
                
                # 优雅终止
                self._proc_a.terminate()
                
                # 等待进程退出
                for _ in range(5):
                    if self._proc_a.poll() is not None:
                        break
                    await asyncio.sleep(1)
                
                # 强制终止（如果必要）
                if self._proc_a.poll() is None:
                    self._proc_a.kill()
                
                self.logger.info("进程A已停止")
                
            except Exception as e:
                self.logger.warning(f"停止进程A异常: {e}")
            finally:
                self._proc_a = None
    
    async def _stop_process_b(self):
        """停止进程B"""
        if self._proc_b:
            try:
                self.logger.info("停止进程B...")
                
                # 优雅终止
                self._proc_b.terminate()
                
                # 等待进程退出
                for _ in range(5):
                    if self._proc_b.poll() is not None:
                        break
                    await asyncio.sleep(1)
                
                # 强制终止（如果必要）
                if self._proc_b.poll() is None:
                    self._proc_b.kill()
                
                self.logger.info("进程B已停止")
                
            except Exception as e:
                self.logger.warning(f"停止进程B异常: {e}")
            finally:
                self._proc_b = None
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._is_running:
            try:
                # 检查两个进程的健康状态
                health_status = await self._perform_health_check()
                
                if not health_status['healthy']:
                    self.logger.warning("健康检查失败，可能需要干预")
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"健康检查循环异常: {e}")
                await asyncio.sleep(30)
    
    async def _perform_health_check(self) -> Dict:
        """执行健康检查"""
        health_status = {
            'healthy': True,
            'timestamp': datetime.now().isoformat(),
            'process_a': {'alive': False, 'pid': None},
            'process_b': {'alive': False, 'pid': None}
        }
        
        try:
            # 检查进程A
            if self._proc_a and await self._check_process_alive(self._proc_a, "A"):
                health_status['process_a']['alive'] = True
                health_status['process_a']['pid'] = self._proc_a.pid
            else:
                health_status['healthy'] = False
            
            # 检查进程B
            if self._proc_b and await self._check_process_alive(self._proc_b, "B"):
                health_status['process_b']['alive'] = True
                health_status['process_b']['pid'] = self._proc_b.pid
            else:
                health_status['healthy'] = False
            
        except Exception as e:
            self.logger.error(f"执行健康检查异常: {e}")
            health_status['healthy'] = False
        
        return health_status
    
    def _check_restart_limit(self) -> bool:
        """检查重启频率限制"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # 统计过去一小时内的重启次数
        recent_restarts = [rt for rt in self._restart_history if rt > hour_ago]
        
        if len(recent_restarts) >= self.max_restarts_per_hour:
            self.logger.error(f"重启频率过高: {len(recent_restarts)}次/小时")
            return False
        
        # 记录本次重启
        self._restart_history.append(now)
        
        # 清理过期的重启记录（保留最近24小时）
        day_ago = now - timedelta(hours=24)
        self._restart_history = [rt for rt in self._restart_history if rt > day_ago]
        
        return True
    
    async def _cleanup_orphaned_processes(self):
        """清理孤儿进程"""
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
                    
                    # 检查进程名或命令行是否匹配
                    proc_info = proc.info
                    cmdline = proc_info.get('cmdline', [])
                    
                    for process_name in process_names:
                        if (proc_info['name'] and process_name.lower() in proc_info['name'].lower()) or \
                           (cmdline and any(process_name.lower() in str(arg).lower() for arg in cmdline)):
                            
                            self.logger.warning(f"发现孤儿进程 PID: {proc.pid}，正在清理...")
                            proc.terminate()
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        except Exception as e:
            self.logger.warning(f"清理孤儿进程异常: {e}")
    
    def get_status(self) -> Dict:
        """获取守护状态"""
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
        """更新协调循环 - 检测更新状态并协调双进程行为"""
        while self._is_running:
            try:
                # 检查是否有更新进行中
                if await self._check_update_in_progress():
                    async with self._update_lock:
                        if not self._update_in_progress:
                            self.logger.info("检测到更新进行中，暂停双进程保活机制")
                            self._update_in_progress = True
                            
                            # 暂停进程监控（但不停止进程）
                            await self._pause_monitoring()
                else:
                    async with self._update_lock:
                        if self._update_in_progress:
                            self.logger.info("更新完成，恢复双进程保活机制")
                            self._update_in_progress = False
                            
                            # 恢复进程监控
                            await self._resume_monitoring()
                
                # 更新检查间隔
                await asyncio.sleep(self.update_check_interval)
                
            except Exception as e:
                self.logger.error(f"更新协调循环异常: {e}")
                await asyncio.sleep(self.update_check_interval)
    
    async def _check_update_in_progress(self) -> bool:
        """检查是否有更新进行中"""
        try:
            # 检查VERSION文件是否存在更新标记
            version_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "VERSION")
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    # 如果VERSION文件包含更新标记或临时版本号
                    if content.startswith("updating_") or ".tmp" in content:
                        return True
            
            # 检查是否有更新相关的临时文件
            temp_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp")
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    if file.startswith("update_") or file.endswith(".tmp"):
                        return True
            
            # 检查是否有更新进程在运行
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmdline = ' '.join(proc.info['cmdline']).lower() if proc.info['cmdline'] else ''
                    if 'update' in cmdline and 'installer' in cmdline:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return False
            
        except Exception as e:
            self.logger.warning(f"检查更新状态异常: {e}")
            return False
    
    async def _pause_monitoring(self):
        """暂停进程监控"""
        try:
            # 设置暂停标志，监控循环会检测此标志
            self._monitoring_paused = True
            self.logger.info("双进程监控已暂停")
            
            # 记录当前进程状态
            self._pre_update_state = self.get_status()
            
        except Exception as e:
            self.logger.error(f"暂停监控异常: {e}")
    
    async def _resume_monitoring(self):
        """恢复进程监控"""
        try:
            # 清除暂停标志
            self._monitoring_paused = False
            self.logger.info("双进程监控已恢复")
            
            # 检查进程状态，必要时重启
            await self._check_and_restart_after_update()
            
        except Exception as e:
            self.logger.error(f"恢复监控异常: {e}")
    
    async def _check_and_restart_after_update(self):
        """更新后检查并重启进程"""
        try:
            current_status = self.get_status()
            pre_update_state = getattr(self, '_pre_update_state', {})
            
            # 检查进程A是否需要重启
            if not current_status['process_a']['alive'] and pre_update_state.get('process_a', {}).get('alive', False):
                self.logger.info("更新后进程A异常，尝试重启")
                await self._restart_process_a()
            
            # 检查进程B是否需要重启
            if not current_status['process_b']['alive'] and pre_update_state.get('process_b', {}).get('alive', False):
                self.logger.info("更新后进程B异常，尝试重启")
                await self._restart_process_b()
            
            # 清理更新前状态
            if hasattr(self, '_pre_update_state'):
                delattr(self, '_pre_update_state')
                
        except Exception as e:
            self.logger.error(f"更新后检查异常: {e}")
    
    def pause_for_update(self):
        """暂停监控以进行更新"""
        try:
            self.logger.info("双进程保活机制：暂停监控")
            
            # 设置更新进行中标志
            self._update_in_progress = True
            
            # 停止健康检查
            if self._health_check_thread and self._health_check_thread.is_alive():
                self._stop_health_check = True
                self._health_check_thread.join(timeout=5)
                self.logger.info("健康检查线程已停止")
            
            # 停止进程监控
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._stop_monitoring = True
                self._monitor_thread.join(timeout=5)
                self.logger.info("进程监控线程已停止")
            
            self.logger.info("双进程保活监控已暂停")
            
        except Exception as e:
            self.logger.error(f"暂停监控失败: {str(e)}")
            # 确保标志被设置
            self._update_in_progress = True
    
    def resume_after_update(self):
        """更新完成后恢复监控"""
        try:
            self.logger.info("双进程保活机制：恢复监控")
            
            # 清除更新进行中标志
            self._update_in_progress = False
            
            # 重新启动健康检查线程
            if not self._health_check_thread or not self._health_check_thread.is_alive():
                self._stop_health_check = False
                self._health_check_thread = threading.Thread(
                    target=self._health_check_worker,
                    daemon=True
                )
                self._health_check_thread.start()
                self.logger.info("健康检查线程已重新启动")
            
            # 重新启动进程监控线程
            if not self._monitor_thread or not self._monitor_thread.is_alive():
                self._stop_monitoring = False
                self._monitor_thread = threading.Thread(
                    target=self._monitor_worker,
                    daemon=True
                )
                self._monitor_thread.start()
                self.logger.info("进程监控线程已重新启动")
            
            self.logger.info("双进程保活监控已恢复")
            
        except Exception as e:
            self.logger.error(f"恢复监控失败: {str(e)}")
            # 确保标志被清除
            self._update_in_progress = False
    
    def is_update_in_progress(self) -> bool:
        """检查是否正在进行更新"""
        return self._update_in_progress


def create_dual_process_guardian(process_a_config: Dict, process_b_config: Dict) -> DualProcessGuardian:
    """创建双进程互监控守护实例"""
    return DualProcessGuardian(process_a_config, process_b_config)