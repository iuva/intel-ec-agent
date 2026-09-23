from .global_cache import get_agent_status,  cache, set_agent_status, set_dmr_info, get_agent_status_by_key, get_dmr_upload_task_id, get_dmr_info, set_dmr_upload_task_id
from ..utils.version_utils import get_app_version, is_newer_version
from local_agent.utils.http_client import http_post
from ..logger import get_logger
from .ek import EK
from .dmr import DMR
from ..utils.timer_utils import set_timeout, clear_timeout
from .constants import HARDWARE_INFO_TASK_ID, APP_UPDATE_CACHE_KEY

logger = get_logger(__name__)


def upload_dmr():
    """Report DMR hardware info"""
    logger.info("Called: upload_dmr")
    info = get_dmr_info()
    logger.info(f"DMR hardware info report: {info}")
    if info:

        # Clear hardware info reporting timed task to avoid duplicate reporting
        task_id = get_dmr_upload_task_id()
        if task_id:
            clear_timeout(task_id)
            set_dmr_upload_task_id("")

        # Hardware info reporting
        res = http_post(url="/host/agent/hardware/report", data=info)

        logger.info(f"Hardware info report result: {res}")

        res_data = res.get('data', {})
        res_code = res_data.get('code', 0)
        if res_code != 200:
            logger.error(f"Hardware info report failed: {res}")

            # Timed report again after 15 minutes
            tack_id = set_timeout(900, upload_dmr)
            set_dmr_upload_task_id(tack_id)

            # Stop WebSocket service
            from ..utils.websocket_sync_utils import stop_websocket_sync
            stop_websocket_sync()

            return False

        set_agent_status(sut=False)
        set_dmr_info(None)

        # Start WebSocket service
        if str(info.get('type')) == "0":
            from ..utils.websocket_sync_utils import start_websocket_sync
            start_websocket_sync(True)

        logger.info("Hardware info report successful")
        # Execute update compensation
        update_app()

    return True



def update_app():
    """
    Update application
    """
    update_info = cache.get(APP_UPDATE_CACHE_KEY, {})
    if len(update_info) == 0:
        return
    
    agent_state = get_agent_status()
    
    is_test = agent_state.get('test', False)
    is_sut = agent_state.get('sut', False)
    is_vnc = agent_state.get('vnc', False)

    if not is_test and not is_sut and not is_vnc:
        # Stop WebSocket
        from ..utils.websocket_sync_utils import stop_websocket_sync, start_websocket_sync
        stop_websocket_sync()

        import time
        try:
            for name in list(update_info.keys()):
                message = update_info[name]
                version = message.get('conf_ver', '')
                url = message.get('conf_url', '')
                md5 = message.get('conf_md5', '')
                if name == 'agent':

                    from local_agent.core.persistent_storage import set_persistent_data
                    current_version = get_app_version(False)
                    agent_is_new = is_newer_version(version, current_version)
                    if agent_is_new:
                        logger.info('Agent needs update')
                        report_version('agent', version, 1)

                        try:
                            from local_agent.auto_update.auto_updater import AutoUpdater
                            updater = AutoUpdater()
                            result = updater.perform_update_sync(
                                expected_md5=md5,
                                download_url=url
                            )

                            if not result.get('success', False):
                                error_message = result.get('error', 'Unknown error')
                                logger.error(f"Update failed: {error_message}")

                                current_time = time.time()
                                set_persistent_data('last_update_failure_time', current_time, 'update_status')
                                set_persistent_data('last_update_error', error_message, 'update_status')
                                logger.info(f"Recorded update failure time: {current_time}")
                                report_version('agent', version, 3)

                        except Exception as e:
                            logger.error(f"Update operation exception: {e}")
                            current_time = time.time()
                            set_persistent_data('last_update_failure_time', current_time, 'update_status')
                            set_persistent_data('last_update_error', str(e), 'update_status')
                            logger.info(f"Recorded update exception time: {current_time}")
                            report_version('agent', version, 3)
                    else:
                        logger.info(f"Agent version {current_version} >= server version {version}, skip update")

                elif name == 'ek':
                    ek_is_new = is_newer_version(version, EK.version())
                    if ek_is_new:
                        logger.info('Execution Kit needs update')
                        report_version('ek', version, 1)
                        EK.update(url)

                        res = is_newer_version(version, EK.version())

                        if res:
                            report_version('ek', version, 3)
                        else:
                            report_version('ek', version, 2)

                elif name == 'dmr_config':
                    dmr_is_new = is_newer_version(version, DMR.version())
                    if dmr_is_new:
                        logger.info('dmr_config needs update')
                        report_version('dmr_config', version, 1)
                        DMR.update(url)
                        res = is_newer_version(version, DMR.version())

                        if res:
                            report_version('dmr_config', version, 3)
                        else:
                            report_version('dmr_config', version, 2)
                            get_hardware_info()

                # Remove processed item from cache
                cached = cache.get(APP_UPDATE_CACHE_KEY, {})
                cached.pop(name, None)
                cache.set(APP_UPDATE_CACHE_KEY, cached)

        finally:
            # Always reconnect WS regardless of update outcome
            start_websocket_sync(True)

def get_hardware_info():
    """
    Get hardware information
    """
    logger.info("Obtained hardware info")

    # If not in test, prioritize stopping websocket to ensure no test execution during hardware info retrieval
    if not get_agent_status_by_key('test'):
        from ..utils.websocket_sync_utils import stop_websocket_sync
        stop_websocket_sync()

        set_agent_status(sut=True)
        if not DMR.is_running():
            import time
            DMR.kill_dmr()
            time.sleep(10)
            DMR.get_hardware_info()
            logger.info("Obtained hardware info - call completed")

    old_task_id = cache.get(HARDWARE_INFO_TASK_ID)

    # Add timed task, execute again after 15 minutes
    task_id = set_timeout(30, get_hardware_info)
    # Cache timed task id
    cache.set(HARDWARE_INFO_TASK_ID, task_id)

    if old_task_id:
        clear_timeout(old_task_id)





def report_version(name: str, version: str, state: int):
    current_version = get_app_version(False)
    data = {
        "app_name": name,
        "app_ver": version,
        "biz_state": state,
        "agent_ver": current_version
    }

    http_post(url = '/host/agent/ota/update-status', data = data)




