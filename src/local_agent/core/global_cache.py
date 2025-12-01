#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目全局缓存模块
专为跨模块数据共享设计，简单易用

使用示例：
1. 在websocket模块中存储数据：
   from src.local_agent.core.global_cache import cache
   cache.set("websocket:user:123", {"status": "connected", "data": {...}})

2. 在api模块中读取数据：
   from src.local_agent.core.global_cache import cache
   user_data = cache.get("websocket:user:123")

3. 在core模块中更新数据：
   from src.local_agent.core.global_cache import cache
   cache.update("websocket:user:123", {"last_activity": time.time()})
"""

import time
import threading
from typing import Any, Dict, Optional, Union
from collections import OrderedDict


class GlobalCache:
    """
    全局缓存类 - 专为跨模块数据共享设计
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        初始化全局缓存
        
        Args:
            max_size: 最大缓存项数量，默认1000
            default_ttl: 默认过期时间（秒），默认1小时
        """
        self._data: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._access_order = OrderedDict()  # 用于LRU淘汰
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None表示永久有效
            
        Returns:
            bool: 是否设置成功
        """
        with self._lock:
            # 清理过期项
            self._clean_expired()
            
            # 检查容量，必要时淘汰最久未使用的项
            if len(self._data) >= self._max_size and key not in self._data:
                self._evict_oldest()
            
            # 设置缓存项
            if ttl is not None:
                # 设置了TTL，计算过期时间
                expires_at = time.time() + ttl
            else:
                # 未设置TTL，永久有效
                expires_at = float('inf')  # 无限大，表示永不过期
            
            self._data[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            
            # 更新访问顺序
            if key in self._access_order:
                del self._access_order[key]
            self._access_order[key] = None
            
            return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值（如果键不存在或已过期）
            
        Returns:
            Any: 缓存值或默认值
        """
        with self._lock:
            if key not in self._data:
                return default
            
            item = self._data[key]
            
            # 检查是否过期（永久有效的项expires_at为inf，不会过期）
            if time.time() > item['expires_at']:
                del self._data[key]
                if key in self._access_order:
                    del self._access_order[key]
                return default
            
            # 更新访问时间
            if key in self._access_order:
                del self._access_order[key]
            self._access_order[key] = None
            
            return item['value']
    
    def has(self, key: str) -> bool:
        """
        检查键是否存在且未过期
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 键是否存在且有效
        """
        with self._lock:
            return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
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
        更新缓存项的部分字段（仅适用于字典类型的值）
        
        Args:
            key: 缓存键
            updates: 要更新的字段
            
        Returns:
            bool: 是否更新成功
        """
        with self._lock:
            current_value = self.get(key)
            if current_value is None or not isinstance(current_value, dict):
                return False
            
            # 更新字段
            current_value.update(updates)
            
            # 重新设置缓存（保持原有TTL）
            item = self._data[key]
            remaining_ttl = item['expires_at'] - time.time()
            if remaining_ttl > 0:
                return self.set(key, current_value, int(remaining_ttl))
            
            return False
    
    def keys(self) -> list:
        """
        获取所有有效缓存键
        
        Returns:
            list: 缓存键列表
        """
        with self._lock:
            self._clean_expired()
            return list(self._data.keys())
    
    def size(self) -> int:
        """
        获取当前缓存项数量
        
        Returns:
            int: 缓存项数量
        """
        with self._lock:
            self._clean_expired()
            return len(self._data)
    
    def clear(self) -> None:
        """
        清空所有缓存
        """
        with self._lock:
            self._data.clear()
            self._access_order.clear()
    
    def get_ttl(self, key: str) -> Optional[float]:
        """
        获取键的剩余过期时间
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[float]: 剩余秒数，永久有效返回float('inf')，键不存在返回None
        """
        with self._lock:
            if key not in self._data:
                return None
            
            item = self._data[key]
            
            # 永久有效的项
            if item['expires_at'] == float('inf'):
                return float('inf')
            
            remaining = item['expires_at'] - time.time()
            return max(0, remaining) if remaining > 0 else None
    
    def _clean_expired(self) -> None:
        """
        清理所有过期项（永久有效的项不会被清理）
        """
        current_time = time.time()
        expired_keys = []
        
        for key, item in self._data.items():
            # 永久有效的项expires_at为inf，不会过期
            if item['expires_at'] != float('inf') and current_time > item['expires_at']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._data[key]
            if key in self._access_order:
                del self._access_order[key]
    
    def _evict_oldest(self) -> None:
        """
        淘汰最久未使用的项
        """
        if self._access_order:
            oldest_key, _ = self._access_order.popitem(last=False)
            if oldest_key in self._data:
                del self._data[oldest_key]


# 创建全局缓存实例
_cache_instance = None
_cache_lock = threading.RLock()


def get_cache() -> GlobalCache:
    """
    获取全局缓存实例（单例模式）
    
    Returns:
        GlobalCache: 全局缓存实例
    """
    global _cache_instance
    with _cache_lock:
        if _cache_instance is None:
            _cache_instance = GlobalCache()
        return _cache_instance


# 提供便捷的全局实例
cache = get_cache()


# 便捷函数，可以直接导入使用
def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """便捷函数：设置缓存值"""
    return cache.set(key, value, ttl)


def get_cache_value(key: str, default: Any = None) -> Any:
    """便捷函数：获取缓存值"""
    return cache.get(key, default)


def has_cache(key: str) -> bool:
    """便捷函数：检查缓存是否存在"""
    return cache.has(key)


def delete_cache(key: str) -> bool:
    """便捷函数：删除缓存项"""
    return cache.delete(key)


def update_cache(key: str, updates: Dict[str, Any]) -> bool:
    """便捷函数：更新缓存项"""
    return cache.update(key, updates)


def clear_all_cache() -> None:
    """便捷函数：清空所有缓存"""
    cache.clear()


def get_cache_keys() -> list:
    """便捷函数：获取所有缓存键"""
    return cache.keys()


def get_cache_size() -> int:
    """便捷函数：获取缓存大小"""
    return cache.size()