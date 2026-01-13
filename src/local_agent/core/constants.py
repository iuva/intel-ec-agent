"""
Cache key constant definitions
"""
# token Cache key
AUTHORIZATION_CACHE_KEY = "Authorization"
# [Authentication] info cache key
AUTH_INFO_CACHE_KEY = "auth_info"
# [Local machine] info cache key
LOCAL_INFO_CACHE_KEY = "local_info"

# python address info cache key
PYTHON_CACHE_KEY = "python_path"

# realvnc address info cache key
REALVNC_CACHE_KEY = "realvnc_path"

# agent update failure [time]
AGENT_UPDATE_FAILED_TIME = "agent_update_failed_time"

# [Hardware] info get [scheduled task] id
HARDWARE_INFO_TASK_ID = "hardware_info_task_id"

# [Hardware] info [upload scheduled task] id
HARDWARE_INFO_UPLOAD_TASK_ID = "hardware_info_upload_task_id"

# agent status key  
# [Content standard]: {"test": bool, [whether currently] testing
# "vnc": bool, [whether currently] VNC connection
# "sut": bool, [whether currently] getting [hardware] info
# "use": bool, [whether currently in use] ([used to determine if] test [is still] in progress)
# "pre": bool, [whether currently preparing] test ([used to determine if need to] wait)
# }
AGENT_STATUS_CACHE_KEY = "agent_status_cache_key"

# dmr [hardware] info cache key
DMR_INFO_CACHE_KEY = "dmr_info_cache_key"

# app update [related] cache key
APP_UPDATE_CACHE_KEY = "app_update_cache_key"

# ek test info cache key
EK_TEST_INFO_CACHE_KEY = "ek_test_info_cache_key"

# Initialize configuration data
INIT_CONFIG_CACHE_KEY = "init_config_cache_key"

# Hardware information acquisition cycle task ID
HARDWARE_INFO_CYCLE_TASK_ID = "hardware_info_cycle_task_id"
