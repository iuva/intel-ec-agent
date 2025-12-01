#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
鉴权相关实现
"""
from ..logger import get_logger
from ..core.global_cache import cache
from .constants import LOCAL_INFO_CACHE_KEY, AUTHORIZATION_CACHE_KEY, AUTH_INFO_CACHE_KEY
from local_agent.utils.http_client import http_post

logger = get_logger(__name__)

def auth_token():
    """获取鉴权token"""
    local_info = cache.get(LOCAL_INFO_CACHE_KEY)
    if not local_info:
        logger.error("本地信息缓存为空，无法获取鉴权token")
        return None

    # 发起网络请求
    res = http_post(
        url="/auth/device/login",
        data=local_info.to_dict(),
        is_token=False
    )

    body = res.get('data')

    code = body.get('code')
    if code == 200:
        data = body.get('data')
        auth_token = data.get('token')
        cache.set(AUTHORIZATION_CACHE_KEY, auth_token, ttl=data.get('expires_in'))
        cache.set(AUTH_INFO_CACHE_KEY, data)

    else:
        return None

    return "ok"



def refresh_token():
    """刷新鉴权token"""
    auth_info = cache.get(AUTH_INFO_CACHE_KEY)
    if not auth_info:
        return None

    # 发起网络请求
    res = http_post(
        url="/auth/refresh",
        data={
            "refresh_token": auth_info.get('refresh_token')
        },
        is_token=False
    )

    body = res.get('data')

    code = body.get('code')
    if code == 200:
        data = body.get('data')
        auth_token = data.get('token')
        cache.set(AUTHORIZATION_CACHE_KEY, auth_token, ttl=data.get('expires_in'))
        cache.set(AUTH_INFO_CACHE_KEY, data)
    else:
        return None

    return "ok"