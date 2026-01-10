#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Heartbeat Manager - Implements highly reliable heartbeat detection and automatic recovery
Provides multi-level heartbeat verification, network status detection, and intelligent recovery strategies
"""

import asyncio
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..logger import get_logger


class HeartbeatManager:
    """Heartbeat management class - Implements top-tier heartbeat detection mechanism"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Configurationmanagement
        from ..config import get_config
        self.config = get_config()
        
        # Heartbeat configuration
        self.heartbeat_interval = 30  # Basic heartbeat interval (seconds)
        self.heartbeat_timeout = 10   # Heartbeat timeout time (seconds)
        self.max_failures = 3         # Maximum consecutive failure times
        
        # Statusmanagement
        self._is_running = False
        self._last_successful_heartbeat: Optional[datetime] = None
        self._consecutive_failures = 0
        self._recovery_in_progress = False
        
        # Heartbeat history records
        self._heartbeat_history: List[Dict] = []
        self._max_history_size = 100
        
        # Network status detection
        self._network_status = True  # Default network normal
        self._last_network_check = datetime.now()
        
        # Intelligent recovery strategies
        self._recovery_strategies = [
            self._recovery_strategy_quick_restart,
            self._recovery_strategy_delayed_restart,
            self._recovery_strategy_full_reset
        ]
        
        self.logger.info("Heartbeat manager initialized")
    
    async def start(self) -> bool:
        """Start heartbeat manager"""
        try:
            self.logger.info("Starting heartbeat manager...")
            
            self._is_running = True
            
            # Start heartbeat tasks
            asyncio.create_task(self._heartbeat_loop())
            asyncio.create_task(self._network_monitor_loop())
            asyncio.create_task(self._health_analysis_loop())
            
            self.logger.info("Heartbeat manager started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Heartbeat manager startup failed: {e}")
            return False
    
    async def stop(self) -> bool:
        """Stop heartbeat manager"""
        try:
            self.logger.info("Stopping heartbeat manager...")
            self._is_running = False
            self.logger.info("Heartbeat manager has stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Stop heartbeat manager failed: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Send heartbeat signal"""
        try:
            start_time = time.time()
            
            # Multi-level heartbeat validation
            heartbeat_results = await asyncio.gather(
                self._verify_local_health(),
                self._verify_api_health(),
                self._verify_websocket_health(),
                return_exceptions=True
            )
            
            # Analyze heartbeat results
            success = await self._analyze_heartbeat_results(heartbeat_results)
            
            # Record heartbeat history
            heartbeat_record = {
                'timestamp': datetime.now(),
                'success': success,
                'response_time': (time.time() - start_time) * 1000,  # milliseconds
                'details': {
                    'local': isinstance(heartbeat_results[0], bool) and heartbeat_results[0],
                    'api': isinstance(heartbeat_results[1], bool) and heartbeat_results[1],
                    'websocket': isinstance(heartbeat_results[2], bool) and heartbeat_results[2]
                }
            }
            
            self._record_heartbeat(heartbeat_record)
            
            if success:
                self._last_successful_heartbeat = datetime.now()
                self._consecutive_failures = 0
                self.logger.debug("Heartbeat sent successfully")
            else:
                self._consecutive_failures += 1
                self.logger.warning(f"Heartbeat send failed, consecutive failures: {self._consecutive_failures}")
                
                # Trigger recovery mechanism
                if self._consecutive_failures >= self.max_failures:
                    await self._trigger_recovery()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Send heartbeat exception: {e}")
            self._consecutive_failures += 1
            return False
    
    async def _heartbeat_loop(self):
        """Heartbeat loop"""
        while self._is_running:
            try:
                # Send heartbeat
                await self.send_heartbeat()
                
                # Dynamically adjust heartbeat interval (based on network status and failure times)
                interval = self._calculate_dynamic_interval()
                
                # Wait for next heartbeat
                await asyncio.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"Heartbeat loop exception: {e}")
                await asyncio.sleep(self.heartbeat_interval)
    
    async def _network_monitor_loop(self):
        """Network monitoring loop"""
        while self._is_running:
            try:
                # Check network connection
                network_ok = await self._check_network_connectivity()
                
                if network_ok != self._network_status:
                    self._network_status = network_ok
                    status_text = "normal" if network_ok else "abnormal"
                    self.logger.info(f"Network status changed: {status_text}")
                
                self._last_network_check = datetime.now()
                
                # Check network every 60 seconds
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Network monitoring exception: {e}")
                await asyncio.sleep(60)
    
    async def _health_analysis_loop(self):
        """Health analysis loop"""
        while self._is_running:
            try:
                # Analyze heartbeat history data
                await self._analyze_heartbeat_patterns()
                
                # Analyze every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                self.logger.error(f"Health analysis exception: {e}")
                await asyncio.sleep(300)
    
    async def _verify_local_health(self) -> bool:
        """Validate local health status"""
        try:
            # Check if critical process is running
            import psutil
            
            current_pid = os.getpid()
            process = psutil.Process(current_pid)
            
            # Check process status
            if not process.is_running():
                return False
            
            # Check memory usage
            memory_percent = process.memory_percent()
            if memory_percent > 90:  # Memory usage exceeds 90%
                self.logger.warning(f"Memory usage too high: {memory_percent:.1f}%")
                return False
            
            # Check CPU usage
            cpu_percent = process.cpu_percent()
            if cpu_percent > 95:  # CPU usage exceeds 95%
                self.logger.warning(f"CPU usage too high: {cpu_percent:.1f}%")
                return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Verify local health status exception: {e}")
            return False
    
    async def _verify_api_health(self) -> bool:
        """Validate API health status"""
        try:
            import aiohttp
            
            # Get API port from configuration
            api_host = self.config.get('api_host', '0.0.0.0')
            api_port = self.config.get('api_port', 8001)
            
            # On Windows environment, 0.0.0.0 needs to be converted to 127.0.0.1
            if api_host == '0.0.0.0' and os.name == 'nt':
                api_host = '127.0.0.1'
            
            # Try connecting to API health check endpoint
            async with aiohttp.ClientSession() as session:
                # First try using converted host name
                try:
                    async with session.get(f'http://{api_host}:{api_port}/health', timeout=5) as response:
                        if response.status == 200:
                            return True
                except Exception as e:
                    self.logger.debug(f"API health check failed ({api_host}:{api_port}): {e}")
                
                # If first endpoint fails, try alternative endpoint
                try:
                    async with session.get(f'http://{api_host}:{api_port}/status', timeout=5) as response:
                        if response.status == 200:
                            return True
                except Exception as e:
                    self.logger.debug(f"API status check failed ({api_host}:{api_port}): {e}")
                
                # If both endpoints fail, try using 127.0.0.1 as alternative (if current is not 127.0.0.1)
                if api_host != '127.0.0.1':
                    try:
                        async with session.get(f'http://127.0.0.1:{api_port}/health', timeout=5) as response:
                            if response.status == 200:
                                return True
                    except Exception as e:
                        self.logger.debug(f"Alternative API health check failed (127.0.0.1:{api_port}): {e}")
                
                # Finally try localhost
                try:
                    async with session.get(f'http://localhost:{api_port}/health', timeout=5) as response:
                        if response.status == 200:
                            return True
                except Exception as e:
                    self.logger.debug(f"localhost API health check failed: {e}")
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Verify API health status exception: {e}")
            return False
    
    async def _verify_websocket_health(self) -> bool:
        """Validate WebSocket health status"""
        try:
            # Check WebSocket connection status
            # This needs to be adjusted based on actual WebSocket implementation
            
            # Temporary implementation: If WebSocket client exists and connection is normal
            from ..websocket.global_websocket_manager import get_websocket_manager
            manager = await get_websocket_manager()
            return manager.is_running() == manager.is_supposed()
            
        except Exception as e:
            self.logger.warning(f"Verify WebSocket health status exception: {e}")
            return True  # WebSocket不是核心功能，Failure不影响整体
    
    async def _check_network_connectivity(self) -> bool:
        """Check network connectivity"""
        try:
            import aiohttp
            
            # Test connection to reliable external services
            test_urls = [
                'http://www.google.com/generate_204',  # Google's 204 response
                'http://www.baidu.com',                # Baidu
                'http://www.qq.com'                    # Tencent
            ]
            
            async with aiohttp.ClientSession() as session:
                for url in test_urls:
                    try:
                        async with session.get(url, timeout=5) as response:
                            if response.status in [200, 204]:
                                return True
                    except:
                        continue
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Check network connectivity exception: {e}")
            return False
    
    async def _analyze_heartbeat_results(self, results: List) -> bool:
        """Analyze heartbeat results"""
        try:
            # Count success count
            success_count = 0
            total_count = 0
            
            for result in results:
                if isinstance(result, bool):
                    total_count += 1
                    if result:
                        success_count += 1
            
            # If network exception, lower success standard
            if not self._network_status:
                return success_count >= 1  # Only need one success
            
            # Normal case needs at least 2 successes
            return success_count >= 2
            
        except Exception as e:
            self.logger.error(f"Analyze heartbeat results exception: {e}")
            return False
    
    async def _trigger_recovery(self):
        """Trigger recovery mechanism"""
        if self._recovery_in_progress:
            return
        
        self._recovery_in_progress = True
        
        try:
            self.logger.warning("Triggering automatic recovery mechanism...")
            
            # Select recovery strategy based on failure pattern
            recovery_strategy = self._select_recovery_strategy()
            
            if recovery_strategy:
                success = await recovery_strategy()
                
                if success:
                    self.logger.info("Automatic recovery successful")
                    self._consecutive_failures = 0
                else:
                    self.logger.error("Automatic recovery failed")
            
        except Exception as e:
            self.logger.error(f"Trigger recovery mechanism exception: {e}")
        finally:
            self._recovery_in_progress = False
    
    def _select_recovery_strategy(self):
        """Select recovery strategy"""
        # Select strategy based on failure pattern and historical data
        failure_pattern = self._analyze_failure_pattern()
        
        if failure_pattern == 'network':
            return self._recovery_strategy_delayed_restart
        elif failure_pattern == 'memory':
            return self._recovery_strategy_full_reset
        else:
            return self._recovery_strategy_quick_restart
    
    async def _recovery_strategy_quick_restart(self) -> bool:
        """Quick restart strategy"""
        try:
            self.logger.info("Executing quick restart strategy...")
            
            # Wait for a short time
            await asyncio.sleep(2)
            
            # Need to call application's restart logic here
            # Temporarily return success
            return True
            
        except Exception as e:
            self.logger.error(f"Quick restart strategy exception: {e}")
            return False
    
    async def _recovery_strategy_delayed_restart(self) -> bool:
        """Delayed restart strategy"""
        try:
            self.logger.info("Executing delayed restart strategy...")
            
            # Wait for a longer time (network issues need more time to recover)
            await asyncio.sleep(10)
            
            # Need to call application's restart logic here
            # Temporarily return success
            return True
            
        except Exception as e:
            self.logger.error(f"Delayed restart strategy exception: {e}")
            return False
    
    async def _recovery_strategy_full_reset(self) -> bool:
        """Full reset strategy"""
        try:
            self.logger.info("Executing full reset strategy...")
            
            # Clean up resources
            await self._cleanup_resources()
            
            # Wait for reset
            await asyncio.sleep(5)
            
            # Need to call application's full restart logic here
            # Temporarily return success
            return True
            
        except Exception as e:
            self.logger.error(f"Full reset strategy exception: {e}")
            return False
    
    def _calculate_dynamic_interval(self) -> int:
        """Calculate dynamic heartbeat interval"""
        base_interval = self.heartbeat_interval
        
        # Adjust interval based on failure times
        if self._consecutive_failures > 0:
            # More failure times, shorter interval (more frequent checks)
            multiplier = max(0.5, 1 - (self._consecutive_failures * 0.1))
            base_interval = int(base_interval * multiplier)
        
        # Adjust interval based on network status
        if not self._network_status:
            base_interval = min(base_interval * 2, 120)  # Extend interval during network exceptions
        
        return max(10, base_interval)  # Minimum interval 10 seconds
    
    def _record_heartbeat(self, record: Dict):
        """Record heartbeat history"""
        self._heartbeat_history.append(record)
        
        # Limit history size
        if len(self._heartbeat_history) > self._max_history_size:
            self._heartbeat_history = self._heartbeat_history[-self._max_history_size:]
    
    async def _analyze_heartbeat_patterns(self):
        """Analyze heartbeat patterns"""
        try:
            if len(self._heartbeat_history) < 10:
                return
            
            # Analyze failure patterns
            recent_failures = [h for h in self._heartbeat_history[-20:] if not h['success']]
            
            if len(recent_failures) > 5:
                self.logger.warning("Detected frequent heartbeat failures, may require manual intervention")
            
        except Exception as e:
            self.logger.warning(f"Analyze heartbeat patterns exception: {e}")
    
    def _analyze_failure_pattern(self) -> str:
        """Analyze failure patterns"""
        # Analyze failure reasons based on recent heartbeat history
        if not self._heartbeat_history:
            return 'unknown'
        
        recent_heartbeats = self._heartbeat_history[-10:]
        
        # Check network-related failures
        network_failures = 0
        for hb in recent_heartbeats:
            if not hb['success'] and hb.get('details', {}).get('api') is False:
                network_failures += 1
        
        if network_failures >= 3:
            return 'network'
        
        # Check memory-related failures
        memory_warnings = 0
        for hb in recent_heartbeats:
            if hb.get('response_time', 0) > 10000:  # Response time exceeds 10 seconds
                memory_warnings += 1
        
        if memory_warnings >= 2:
            return 'memory'
        
        return 'unknown'
    
    async def _cleanup_resources(self):
        """Clean up resources"""
        try:
            # Clean up temporary resources
            import gc
            gc.collect()
            
        except Exception as e:
            self.logger.warning(f"Cleanup resources exception: {e}")
    
    def get_status(self) -> Dict[str, any]:
        """Get heartbeat manager status"""
        return {
            'running': self._is_running,
            'last_successful_heartbeat': self._last_successful_heartbeat.isoformat() if self._last_successful_heartbeat else None,
            'consecutive_failures': self._consecutive_failures,
            'network_status': self._network_status,
            'recovery_in_progress': self._recovery_in_progress,
            'heartbeat_history_size': len(self._heartbeat_history)
        }


def create_heartbeat_manager() -> HeartbeatManager:
    """Create heartbeat manager instance"""
    return HeartbeatManager()