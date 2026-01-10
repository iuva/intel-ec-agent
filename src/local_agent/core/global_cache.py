#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Project global cache module
Designed for cross-module data sharing, simple and easy to use

Usage examples:
1. Store data in websocket module:
   from src.local_agent.core.global_cache import cache
   cache.set("websocket:user:123", {"status": "connected", "data": {...}})

2. Read data in api module:
   from src.local_agent.core.global_cache import cache
   user_data = cache.get("websocket:user:123")

3. Update data in core module:
   from src.local_agent.core.global_cache import cache
   cache.update("websocket:user:123", {"last_activity": time.time()})
"""

import time
import threading
from typing import Any, Dict, Optional, Union
from collections import OrderedDict
from .constants import DMR_INFO_CACHE_KEY, HARDWARE_INFO_UPLOAD_TASK_ID, AGENT_STATUS_CACHE_KEY, EK_TEST_INFO_CACHE_KEY

class GlobalCache:
    """
    Global cache class - Designed for cross-module data sharing
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        Initialize global cache
        
        Args:
            max_size: Maximum number of cache items, default 1000
            default_ttl: Default expiration time (seconds), default 1 hour
        """
        self._data: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._access_order = OrderedDict()  # Used for LRU eviction
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Cache value
            ttl: Expiration time (seconds), None means permanent validity
            
        Returns:
            bool: Whether setting was successful
        """
        with self._lock:
            # [Clean expired items]
            self._clean_expired()
            
            # Check [capacity], [evict least recently used item if necessary]
            if len(self._data) >= self._max_size and key not in self._data:
                self._evict_oldest()
            
            # Setup cache [item]
            if ttl is not None:
                # Setup [TTL], [calculate expiration] time
                expires_at = time.time() + ttl
            else:
                # [Not] setup TTL, [permanent] valid
                expires_at = float('inf')  # Infinity, means never expires
            
            self._data[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            
            # Update [access order]
            if key in self._access_order:
                del self._access_order[key]
            self._access_order[key] = None
            
            return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get cache value
        
        Args:
            key: Cache key
            default: Default value (if key does not exist or has expired)
            
        Returns:
            Any: Cache value or default value
        """
        with self._lock:
            if key not in self._data:
                return default
            
            item = self._data[key]
            
            # Check [if expired] ([permanent] valid [items] expires_at [is] inf, [will not expire])
            if time.time() > item['expires_at']:
                del self._data[key]
                if key in self._access_order:
                    del self._access_order[key]
                return default
            
            # Update [access] time
            if key in self._access_order:
                del self._access_order[key]
            self._access_order[key] = None
            
            return item['value']
    
    def has(self, key: str) -> bool:
        """
        Check if key exists and has not expired
        
        Args:
            key: Cache key
            
        Returns:
            bool: Whether key exists and is valid
        """
        with self._lock:
            return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """
        Delete cache item
        
        Args:
            key: Cache key
            
        Returns:
            bool: Whether deletion was successful
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                if key in self._access_order:
                    del self._access_order[key]
                return True
            return False
    
    def update(self, key: str, updates: Dict[str, Any]) -> bool:
        """
        Update partial fields of cache item (only applicable to dictionary type values)
        
        Args:
            key: Cache key
            updates: Fields to update
            
        Returns:
            bool: Whether update was successful
        """
        with self._lock:
            current_value = self.get(key)
            if current_value is None or not isinstance(current_value, dict):
                return False
            
            # Update [fields]
            current_value.update(updates)
            
            # [Re]setup cache ([maintain original] TTL)
            item = self._data[key]
            remaining_ttl = item['expires_at'] - time.time()
            if remaining_ttl > 0:
                return self.set(key, current_value, int(remaining_ttl))
            
            return False
    
    def keys(self) -> list:
        """
        Get all valid cache keys
        
        Returns:
            list: List of cache keys
        """
        with self._lock:
            self._clean_expired()
            return list(self._data.keys())
    
    def size(self) -> int:
        """
        Get current number of cache items
        
        Returns:
            int: Number of cache items
        """
        with self._lock:
            self._clean_expired()
            return len(self._data)
    
    def clear(self) -> None:
        """
        Clear all cache
        """
        with self._lock:
            self._data.clear()
            self._access_order.clear()
    
    def get_ttl(self, key: str) -> Optional[float]:
        """
        Get remaining expiration time for key
        
        Args:
            key: Cache key
            
        Returns:
            Optional[float]: Remaining seconds, returns float('inf') for permanent validity, returns None if key does not exist
        """
        with self._lock:
            if key not in self._data:
                return None
            
            item = self._data[key]
            
            # [Permanent] valid [items]
            if item['expires_at'] == float('inf'):
                return float('inf')
            
            remaining = item['expires_at'] - time.time()
            return max(0, remaining) if remaining > 0 else None
    
    def _clean_expired(self) -> None:
        """
        Clean all expired items (permanently valid items will not be cleaned)
        """
        current_time = time.time()
        expired_keys = []
        
        for key, item in self._data.items():
            # [Permanent] valid [items] expires_at [is] inf, [will not expire]
            if item['expires_at'] != float('inf') and current_time > item['expires_at']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._data[key]
            if key in self._access_order:
                del self._access_order[key]
    
    def _evict_oldest(self) -> None:
        """
        Evict least recently used item
        """
        if self._access_order:
            oldest_key, _ = self._access_order.popitem(last=False)
            if oldest_key in self._data:
                del self._data[oldest_key]


# Create global cache instance
_cache_instance = None
_cache_lock = threading.RLock()


def get_cache() -> GlobalCache:
    """
    Get global cache instance (singleton pattern)
    
    Returns:
        GlobalCache: Global cache instance
    """
    global _cache_instance
    with _cache_lock:
        if _cache_instance is None:
            _cache_instance = GlobalCache()
        return _cache_instance


# [Provide convenient] global instance
cache = get_cache()


# [Convenient] functions, [can be imported and used directly]
def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """[Convenient] function: set cache [value]"""
    return cache.set(key, value, ttl)

def get_cache_value(key: str, default: Any = None) -> Any:
    """[Convenient] function: get cache [value]"""
    return cache.get(key, default)

def has_cache(key: str) -> bool:
    """[Convenient] function: check cache [if exists]"""
    return cache.has(key)

def delete_cache(key: str) -> bool:
    """[Convenient] function: delete cache [item]"""
    return cache.delete(key)

def update_cache(key: str, updates: Dict[str, Any]) -> bool:
    """[Convenient] function: update cache [item]"""
    return cache.update(key, updates)

def clear_all_cache() -> None:
    """[Convenient] function: [clear all] cache"""
    cache.clear()

def get_cache_keys() -> list:
    """[Convenient] function: get [all] cache [keys]"""
    return cache.keys()

def get_cache_size() -> int:
    """[Convenient] function: get cache [size]"""
    return cache.size()

def get_dmr_info() -> Dict[str, Any]:
    """[Convenient] function: get dmr [hardware] info"""
    return cache.get(DMR_INFO_CACHE_KEY, {})

def set_dmr_info(info: Dict[str, Any]) -> None:
    """[Convenient] function: set dmr [hardware] info"""
    cache.set(DMR_INFO_CACHE_KEY, info)

def get_dmr_upload_task_id() -> Optional[str]:
    """[Convenient] function: get [hardware] info [upload scheduled task] id"""
    return cache.get(HARDWARE_INFO_UPLOAD_TASK_ID, None)

def set_dmr_upload_task_id(task_id: str) -> None:
    """[Convenient] function: set [hardware] info [upload scheduled task] id"""
    cache.set(HARDWARE_INFO_UPLOAD_TASK_ID, task_id)

def get_agent_status_by_key(key: str) -> bool:
    """[Convenient] function: get agent [status]"""
    return cache.get(AGENT_STATUS_CACHE_KEY, {"test": False, "vnc": False, "sut": False, "use": False, "pre": False}).get(key, False)

def get_agent_status() -> Dict[str, bool]:
    """[Convenient] function: get agent [status]"""
    return cache.get(AGENT_STATUS_CACHE_KEY, {"test": False, "vnc": False, "sut": False, "use": False, "pre": False})

def set_agent_status(test: bool = None, vnc: bool = None, sut: bool = None, use: bool = None, pre: bool = None) -> None:
    """[Convenient] function: set agent [status]"""
    status = get_agent_status()
    if test is not None:
        status["test"] = test
    if vnc is not None:
        status["vnc"] = vnc
    if sut is not None:
        status["sut"] = sut
    if use is not None:
        status["use"] = use
    if pre is not None:
        status["pre"] = pre
    cache.set(AGENT_STATUS_CACHE_KEY, status)

def get_ek_test_info() -> Dict[str, Any]:
    """[Convenient] function: get ek [test] info"""
    return cache.get(EK_TEST_INFO_CACHE_KEY, {})

def set_ek_test_info(info: Dict[str, Any]) -> None:
    """[Convenient] function: set ek [test] info"""
    cache.set(EK_TEST_INFO_CACHE_KEY, info)



