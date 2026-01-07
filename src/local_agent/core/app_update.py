from .global_cache import cache, get_agent_status, set_agent_status
from ..utils.version_utils import get_app_version, is_newer_version
from local_agent.utils.http_client import http_post
from ..logger import get_logger
from local_agent.core.ek import EK
from local_agent.core.dmr import DMR
from ..utils.timer_utils import set_timeout
from .constants import HARDWARE_INFO_TASK_ID, APP_UPDATE_CACHE_KEY

logger = get_logger(__name__)



def update_app():
    """
    更新应用程序
    """
    update_info = cache.get(APP_UPDATE_CACHE_KEY, {})
    if len(update_info) == 0:
        return
    
    agent_state = get_agent_status()
    
    is_test = agent_state.get('test', False)
    is_sut = agent_state.get('sut', False)
    is_vnc = agent_state.get('vnc', False)

    if not is_test and not is_sut and not is_vnc:
        # 停止websocket
        from ..utils.websocket_sync_utils import stop_websocket_sync
        stop_websocket_sync()
        # 遍历更新信息

        import time
        for name, message in update_info.items():

            version = message.get('conf_ver', '')
            url = message.get('conf_url', '')
            md5 = message.get('conf_md5', '')
            if name == 'agent':
                
                from local_agent.core.persistent_storage import set_persistent_data
                current_version = get_app_version(False)
                agent_is_new = is_newer_version(version, current_version)
                if agent_is_new:
                    logger.info('agent 需要更新')
                    report_version('agent', version, 1)
                                  
                    try:
                        # 延迟导入以避免循环依赖
                        from local_agent.auto_update.auto_updater import AutoUpdater
                        updater = AutoUpdater()
                        # 异步执行更新操作
                        result = updater.perform_update_sync(
                            expected_md5=md5,
                            download_url=url
                        )

                        # 如果程序走到了这里，说明更新脚本并没有杀死当前进程，更新操作失败
                        if not result.get('success', False):
                            # 对更新失败的结果进行持久化存储
                            error_message = result.get('error', '未知错误')
                            logger.error(f"更新失败: {error_message}")
                            
                            # 存储更新失败时间
                            set_persistent_data('last_update_failure_time', current_time, 'update_status')
                            set_persistent_data('last_update_error', error_message, 'update_status')
                            logger.info(f"已记录更新失败时间: {current_time}")
                            report_version('agent', version, 3)
                        
                    except Exception as e:
                        logger.error(f"更新操作异常: {e}")
                        current_time = time.time()
                        set_persistent_data('last_update_failure_time', current_time, 'update_status')
                        set_persistent_data('last_update_error', str(e), 'update_status')
                        logger.info(f"已记录更新异常时间: {current_time}")
                        report_version('agent', version, 3)

            if name == 'ek':
                ek_is_new = is_newer_version(version, EK.version())
                if ek_is_new:
                    logger.info('Execution Kit 需要更新')
                    report_version('ek', version, 1)
                    EK.update(url)

                    # 采用重新获取版本进行比对的方式进行判断是否更新成功
                    res = is_newer_version(version, EK.version())

                    if res:
                        report_version('ek', version, 3)
                    else:
                        report_version('ek', version, 2)
                                
                # 更新结束，启动websocket
                from ..utils.websocket_sync_utils import start_websocket_sync
                start_websocket_sync(True)

            if name == 'dmr_config':
                dmr_is_new = is_newer_version(version, DMR.version())
                if dmr_is_new:
                    logger.info('dmr_config 需要更新')
                    report_version('dmr_config', version, 1)
                    DMR.update(url)
                    # 采用重新获取版本进行比对的方式进行判断是否更新成功
                    res = is_newer_version(version, DMR.version())

                    if res:
                        report_version('dmr_config', version, 3)
                    else:
                        report_version('dmr_config', version, 2)
                        # 更新成功，重新获取硬件信息
                        
                        get_hardware_info()


def get_hardware_info():
    """
    获取硬件信息
    """
    logger.info("获取硬件信息-开始调用")
    set_agent_status(sut=True)
    DMR.get_hardware_info()
    logger.info("获取硬件信息-调用结束")
    # 添加定时任务，15分钟后再次执行
    task_id = set_timeout(900, get_hardware_info)
    # 缓存定时任务id
    cache.set(HARDWARE_INFO_TASK_ID, task_id)


def report_version(name: str, version: str, state: int):
    current_version = get_app_version(False)
    data = {
        "app_name": name,
        "app_ver": version,
        "biz_state": state,
        "agent_ver": current_version
    }

    http_post(url = '/host/agent/ota/update-status', data = data)




