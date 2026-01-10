#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Authentication related implementation
"""
from ..logger import get_logger
from ..core.global_cache import cache
from .constants import LOCAL_INFO_CACHE_KEY, AUTHORIZATION_CACHE_KEY, AUTH_INFO_CACHE_KEY
from local_agent.utils.http_client import http_post

logger = get_logger(__name__)

def auth_token():
    """Get [authentication] token"""
    local_info = cache.get(LOCAL_INFO_CACHE_KEY)
    if not local_info:
        logger.error("Local info cache is empty, cannot obtain authentication token")
        return False

    # [Initiate network] request
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
        return False

    return True



def refresh_token():
    """[Refresh authentication] token"""
    auth_info = cache.get(AUTH_INFO_CACHE_KEY)
    if not auth_info:
        return False

    # [Initiate network] request
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
        auth_token = data.get('access_token')
        cache.set(AUTHORIZATION_CACHE_KEY, auth_token, ttl=data.get('expires_in'))
        cache.set(AUTH_INFO_CACHE_KEY, data)
    else:
        return False

    return True