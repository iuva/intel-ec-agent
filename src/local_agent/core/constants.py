"""
缓存的 key 常量定义
"""
# token 缓存 key
AUTHORIZATION_CACHE_KEY = "Authorization"
# 鉴权信息缓存 key
AUTH_INFO_CACHE_KEY = "auth_info"
# 本机信息缓存 key
LOCAL_INFO_CACHE_KEY = "local_info"

# python 地址信息缓存 key
PYTHON_CACHE_KEY = "python_path"

# realvnc 地址信息缓存 key
REALVNC_CACHE_KEY = "realvnc_path"

# agent 更新失败的时间
AGENT_UPDATE_FAILED_TIME = "agent_update_failed_time"

# 硬件信息获取定时任务id
HARDWARE_INFO_TASK_ID = "hardware_info_task_id"

# 硬件信息上报定时任务id
HARDWARE_INFO_UPLOAD_TASK_ID = "hardware_info_upload_task_id"

# agent 状态key  
# 内容标准：{"test": bool, 是否正在测试
# "vnc": bool, 是否正在 vnc 连接
# "sut": bool, 是否正在获取硬件信息
# "use": bool, 是否正在使用（用于判断测试是否还在进行）
# "pre": bool, 是否正在准备测试（用于判断是否需要等待）
# }
AGENT_STATUS_CACHE_KEY = "agent_status_cache_key"

# dmr 硬件信息缓存 key
DMR_INFO_CACHE_KEY = "dmr_info_cache_key"

# app 更新相关的缓存 key
APP_UPDATE_CACHE_KEY = "app_update_cache_key"

# ek 测试信息缓存 key
EK_TEST_INFO_CACHE_KEY = "ek_test_info_cache_key"
