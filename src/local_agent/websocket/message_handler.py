#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket message handler
Encapsulates all WebSocket message processing logic, implements unified management of message handlers
"""

import asyncio
from datetime import datetime
from typing import Dict, Any

from ..logger import get_logger
from .message_manager import message_manager
from .message_sender import send_message
from ..utils.subprocess_utils import run_with_logging_safe
from ..utils.message_tool import show_message_box
from ..core.global_cache import cache, get_agent_status, set_agent_status, set_ek_test_info, get_agent_status_by_key, get_ek_test_info
from ..core.constants import APP_UPDATE_CACHE_KEY
from ..core.app_update import update_app
from ..core.ek import EK
from ..core.vnc import VNC
from local_agent.utils.http_client import http_post


class WebSocketMessageHandler:
    """WebSocket message handler class"""
    
    def __init__(self, application):
        """
        Initialize message handler
        
        Args:
            application: Application instance for accessing application state and methods
        """
        self.application = application
        self.logger = get_logger(__name__)
        
    def register_all_handlers(self):
        """Register all message handlers"""
        self.logger.info("Registering WebSocket message handlers...")
        
        # Register ping message handler
        self._register_ping_handler()

        # Service-side timeout handling (when heartbeat is not received)
        self._register_timeout_handler()

        # Status update confirmation
        self._register_status_update_handler()

        # Command
        self._register_command_handler()

        # Notification
        self._register_notification_handler()
        
        # Register update related handlers
        self._register_update_handlers()

        # EK test related handlers
        self._register_ek_test_handlers()
    
    def _register_ping_handler(self):
        """Register ping message handler"""
        @message_manager.register_handler("heartbeat_ack", "Processing ping messages")
        async def handle_ping(message: Dict[str, Any]):
            """Handle ping message"""
            self.logger.debug("Received heartbeat response")
    

    def _register_timeout_handler(self):
        """Server informs heartbeat timeout"""
        @message_manager.register_handler("heartbeat_timeout_warning", "heartbeat timeout")
        async def handle_timeout(message: Dict[str, Any]):
            self.logger.debug("Server did not receive heartbeat info, sending one immediately")
            await send_message({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            })
    
    def _register_status_update_handler(self):
        """Status update callback"""
        @message_manager.register_handler("status_update_ack", "status update")
        async def status_update(message: Dict[str, Any]):
            self.logger.info("Received status update response")

    
    def _register_command_handler(self):
        """Command instructions"""
        @message_manager.register_handler("command", "Process restart instructions")
        async def handle_command(message: Dict[str, Any]):
            """Handle command"""
            command = message.get('command', '')
            command_id = message.get('command_id', '')
            result = run_with_logging_safe(
                [command],
                command_name='service',
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )
            isOk = result and result.returncode == 0
            
            await send_message({
                "type": "command_response",
                "command_id": command_id,
                "success": isOk,
                "error": result.stderr.strip() if not isOk else None,
                "result": result.stdout.strip() if isOk else None,
                "timestamp": datetime.now().isoformat()
            })
    
    def _register_notification_handler(self):
        """Register status query handler"""
        @message_manager.register_handler("status", "Process status query")
        async def handle_notification(message: Dict[str, Any]):
                show_message_box(
                    msg=message.get('content', ''),
                    title=message.get('title', ''),
                )




    def _register_ek_test_handlers(self):
        """Register EK test related handlers"""
        
        # VNC connection notification
        @message_manager.register_handler("connection_notification", "VNC connection notification")
        async def handle_connection_notification(message: Dict[str, Any]):
            """Handle VNC connection notification"""
            # Check if already in test state
            if get_agent_status_by_key('use'):
                self.logger.warning("Already in test state, ignoring this message")
                return

            set_agent_status(use=True)
            set_agent_status(pre=True)
            details = message['details']

            log_id = self.logger.start_log_replica(replica_name = details['tc_id'])
            self.logger.debug(f'start_log_replica, log_id: {log_id}')

            details['host_id'] = message['host_id']
            details['log_id'] = log_id
            
            self.logger.debug(f'ek test info, data: {details}')
            set_ek_test_info(details)
            # Start EK test status tracking in background without blocking
            task = asyncio.create_task(ek_status_tracking())
            self.ek_tracking_tasks.add(task)
            task.add_done_callback(self.ek_tracking_tasks.discard)
        
        def stop_ek_test():
            """Stop EK test"""
            EK.test_kill()
            VNC.disconnect()
            # Modify test status
            set_agent_status(use=False)
            set_agent_status(test=False)
            set_agent_status(vnc=False)
            log_id = get_ek_test_info()['log_id']
            self.logger.stop_log_replica(replica_id = log_id)
        
        
        # Release host notification host_offline_notification
        @message_manager.register_handler("host_offline_notification", "Host offline notification")
        async def handle_host_offline_notification(message: Dict[str, Any]):
            """Handle host offline notification"""
            stop_ek_test()

        # Track EK status tracking tasks
        self.ek_tracking_tasks = set()
        
        # EK status tracking
        async def ek_status_tracking():
            """
            Start EK test status tracking
            """
            from local_agent.logger import get_logger
            logger = get_logger()
            try:
                # Use global logger instance to avoid dependency on self
                logger.info("Start EK test status tracking")
                while True:
                    status = get_agent_status()
                        
                    """Check VNC connection status"""
                    if not status['use']:
                        return

                    is_con = VNC.is_connecting()
                    if status['vnc'] != is_con:
                        res = http_post(url='/host/agent/vnc/report', data={'vnc_state': 1 if is_con else 2})
                        set_agent_status(vnc = is_con)
                        res_data = res.get('data', {})
                        code = res_data.get('code', 0)
                        if code == 53016:
                            stop_ek_test()
                            return

                    if status['pre']:
                        if is_con:
                            # Start EK test
                            test_info = get_ek_test_info()
                            response = http_post(
                                url=f"http://127.0.0.1:8001/test_start",
                                data=test_info
                            )
                            # EK.start_test(test_info['tc_id'], test_info['cycle_name'], test_info['user_name'])
                            set_agent_status(pre = False)
                    elif not status['test']:
                        if not is_con:
                            set_agent_status(use = False)
                            # Execute update compensation
                            log_id = get_ek_test_info()['log_id']
                            logger.stop_log_replica(replica_id = log_id)
                            update_app()
                            return

                    # Rest 10 seconds
                    await asyncio.sleep(10)
                    
            except asyncio.CancelledError:
                logger.info("Main loop task cancelled")
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                # Avoid recursive calls, record error but do not restart
                logger.warning("Main loop error occurred, but avoiding recursion by not restarting application")
        




    def _register_update_handlers(self):
        """Register self-update related handlers"""
        
        # Register self-update instruction handler (compatible with old version)
        @message_manager.register_handler("ota_deploy", "Software Update")
        async def handle_update(message: Dict[str, Any]):
            """Handle software update instruction"""


            name = message.get('conf_name', '')

            # Priority feedback, indicating received update notification
            await send_message({
                "type": "ota_deploy_response",
                "conf_name": name,
                "conf_ver": message['conf_ver']
            })

            if not name:
                self.logger.error("Update instruction missing software name")
                return
            
            # New version info into cache
            update_info = cache.get(APP_UPDATE_CACHE_KEY, {})
            update_info.update({name: message})
            cache.set(APP_UPDATE_CACHE_KEY, update_info)

            # Whether meets update conditions
            agent_state = get_agent_status()
            
            is_test = agent_state.get('test', False)
            is_sut = agent_state.get('sut', False)
            is_vnc = agent_state.get('vnc', False)

            if not is_test and not is_sut and not is_vnc:
                update_app()
            # If not meeting update conditions, do not process immediately, will trigger update when test ends, hardware info collection ends
            # Test end means: test case executed and submitted completely, and VNC disconnected


    
    def get_handler_count(self) -> int:
        """Get number of registered handlers"""
        return message_manager.get_handler_count()


# Create global message handler instance
_message_handler = None


def get_message_handler(application=None) -> WebSocketMessageHandler:
    """
    Get message handler instance
    
    Args:
        application: Application instance, required for first call
        
    Returns:
        WebSocketMessageHandler: Message handler instance
    """
    global _message_handler
    
    if _message_handler is None and application is not None:
        _message_handler = WebSocketMessageHandler(application)
    
    return _message_handler


def register_websocket_handlers(application):
    """
    Register WebSocket message handlers (convenient function)
    
    Args:
        application: Application instance
    """
    handler = get_message_handler(application)
    if handler:
        # Check if handlers already registered, avoid duplicate registration
        current_count = message_manager.get_handler_count()
        if current_count > 0:
            handler.logger.info(f"Detected {current_count} existing message handlers, skipping duplicate registration")
            return
        handler.register_all_handlers()
