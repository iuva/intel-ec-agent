#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化存储模块
提供全局通用的持久化存储功能，支持跨进程、跨重启的数据持久化

主要特性：
1. 文件系统持久化存储
2. 自动数据序列化/反序列化
3. 数据版本管理和迁移
4. 原子性操作保证
5. 自动备份和恢复

使用场景：
- 更新失败时间记录
- 应用配置持久化
- 运行状态保存
- 跨重启数据共享
"""

import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union
import shutil

from ..logger import get_logger


class PersistentStorage:
    """
    持久化存储管理器 - 提供全局通用的持久化存储功能
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        初始化持久化存储
        
        Args:
            storage_dir: 存储目录路径，None时使用默认目录
        """
        self.logger = get_logger(__name__)
        
        # 确定存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # 默认存储目录：项目根目录下的 .persistent_data
            project_root = self._get_project_root()
            self.storage_dir = project_root / ".persistent_data"
        
        # 确保存储目录存在
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 线程锁，确保并发安全
        self._lock = threading.RLock()
        
        # 内存缓存，提高读取性能
        self._memory_cache: Dict[str, Any] = {}
        
        # 存储文件路径
        self._storage_file = self.storage_dir / "data.json"
        self._backup_file = self.storage_dir / "data_backup.json"
        
        self.logger.info(f"持久化存储初始化完成，存储目录: {self.storage_dir}")
    
    def _get_project_root(self) -> Path:
        """获取项目根目录"""
        try:
            # 检查是否打包为exe
            if getattr(sys, 'frozen', False):
                # 打包为exe时，返回可执行文件所在目录
                return Path(sys.executable).parent
            else:
                # 开发环境，返回当前文件所在目录的父目录的父目录
                current_file = Path(__file__).resolve()
                return current_file.parent.parent.parent.parent
        except Exception:
            # 保底方案：使用当前工作目录
            return Path.cwd()
    
    def set(self, key: str, value: Any, namespace: str = "default") -> bool:
        """
        设置持久化数据
        
        Args:
            key: 数据键
            value: 数据值（支持JSON序列化的类型）
            namespace: 命名空间，用于数据分类
            
        Returns:
            bool: 是否设置成功
        """
        with self._lock:
            try:
                # 读取现有数据
                data = self._load_data()
                
                # 确保命名空间存在
                if namespace not in data:
                    data[namespace] = {}
                
                # 设置数据
                data[namespace][key] = {
                    'value': value,
                    'timestamp': time.time(),
                    'datetime': datetime.now().isoformat()
                }
                
                # 保存数据
                success = self._save_data(data)
                
                if success:
                    # 更新内存缓存
                    cache_key = f"{namespace}:{key}"
                    self._memory_cache[cache_key] = data[namespace][key]
                    self.logger.debug(f"持久化存储设置成功: {namespace}.{key}")
                
                return success
                
            except Exception as e:
                self.logger.error(f"持久化存储设置失败: {namespace}.{key}, 错误: {str(e)}")
                return False
    
    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        """
        获取持久化数据
        
        Args:
            key: 数据键
            namespace: 命名空间
            default: 默认值
            
        Returns:
            Any: 数据值或默认值
        """
        with self._lock:
            try:
                # 检查内存缓存
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return self._memory_cache[cache_key]['value']
                
                # 读取文件数据
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    value_data = data[namespace][key]
                    
                    # 更新内存缓存
                    self._memory_cache[cache_key] = value_data
                    
                    return value_data['value']
                
                return default
                
            except Exception as e:
                self.logger.error(f"持久化存储获取失败: {namespace}.{key}, 错误: {str(e)}")
                return default
    
    def get_with_metadata(self, key: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """
        获取持久化数据及其元数据
        
        Args:
            key: 数据键
            namespace: 命名空间
            
        Returns:
            Optional[Dict]: 包含数据和元信息的字典，None表示不存在
        """
        with self._lock:
            try:
                # 检查内存缓存
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return self._memory_cache[cache_key]
                
                # 读取文件数据
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    value_data = data[namespace][key]
                    
                    # 更新内存缓存
                    self._memory_cache[cache_key] = value_data
                    
                    return value_data
                
                return None
                
            except Exception as e:
                self.logger.error(f"持久化存储获取元数据失败: {namespace}.{key}, 错误: {str(e)}")
                return None
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        """
        删除持久化数据
        
        Args:
            key: 数据键
            namespace: 命名空间
            
        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            try:
                # 读取现有数据
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    # 删除数据
                    del data[namespace][key]
                    
                    # 如果命名空间为空，删除命名空间
                    if not data[namespace]:
                        del data[namespace]
                    
                    # 保存数据
                    success = self._save_data(data)
                    
                    # 清理内存缓存
                    cache_key = f"{namespace}:{key}"
                    if cache_key in self._memory_cache:
                        del self._memory_cache[cache_key]
                    
                    if success:
                        self.logger.debug(f"持久化存储删除成功: {namespace}.{key}")
                    
                    return success
                
                return True  # 数据不存在，视为删除成功
                
            except Exception as e:
                self.logger.error(f"持久化存储删除失败: {namespace}.{key}, 错误: {str(e)}")
                return False
    
    def exists(self, key: str, namespace: str = "default") -> bool:
        """
        检查数据是否存在
        
        Args:
            key: 数据键
            namespace: 命名空间
            
        Returns:
            bool: 数据是否存在
        """
        with self._lock:
            try:
                # 检查内存缓存
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return True
                
                # 读取文件数据
                data = self._load_data()
                
                return namespace in data and key in data[namespace]
                
            except Exception:
                return False
    
    def list_keys(self, namespace: str = "default") -> list:
        """
        列出命名空间中的所有键
        
        Args:
            namespace: 命名空间
            
        Returns:
            list: 键列表
        """
        with self._lock:
            try:
                data = self._load_data()
                
                if namespace in data:
                    return list(data[namespace].keys())
                
                return []
                
            except Exception as e:
                self.logger.error(f"持久化存储列出键失败: {namespace}, 错误: {str(e)}")
                return []
    
    def list_namespaces(self) -> list:
        """
        列出所有命名空间
        
        Returns:
            list: 命名空间列表
        """
        with self._lock:
            try:
                data = self._load_data()
                return list(data.keys())
                
            except Exception as e:
                self.logger.error(f"持久化存储列出命名空间失败, 错误: {str(e)}")
                return []
    
    def clear_namespace(self, namespace: str = "default") -> bool:
        """
        清空命名空间中的所有数据
        
        Args:
            namespace: 命名空间
            
        Returns:
            bool: 是否清空成功
        """
        with self._lock:
            try:
                data = self._load_data()
                
                if namespace in data:
                    # 清空命名空间
                    data[namespace] = {}
                    
                    # 保存数据
                    success = self._save_data(data)
                    
                    # 清理内存缓存
                    keys_to_remove = [k for k in self._memory_cache.keys() if k.startswith(f"{namespace}:")]
                    for key in keys_to_remove:
                        del self._memory_cache[key]
                    
                    if success:
                        self.logger.debug(f"持久化存储清空命名空间成功: {namespace}")
                    
                    return success
                
                return True  # 命名空间不存在，视为清空成功
                
            except Exception as e:
                self.logger.error(f"持久化存储清空命名空间失败: {namespace}, 错误: {str(e)}")
                return False
    
    def _load_data(self) -> Dict[str, Any]:
        """
        加载持久化数据
        
        Returns:
            Dict: 持久化数据
        """
        try:
            if self._storage_file.exists():
                with open(self._storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 验证数据结构
                if isinstance(data, dict):
                    return data
                else:
                    self.logger.warning("持久化存储文件格式错误，使用默认数据")
                    return {}
            else:
                # 文件不存在，返回空数据
                return {}
                
        except Exception as e:
            self.logger.warning(f"持久化存储加载失败，使用默认数据，错误: {str(e)}")
            
            # 尝试从备份文件恢复
            if self._backup_file.exists():
                try:
                    with open(self._backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, dict):
                        # 恢复备份文件
                        self._save_data(data)
                        self.logger.info("持久化存储从备份文件恢复成功")
                        return data
                except Exception:
                    pass
            
            return {}
    
    def _save_data(self, data: Dict[str, Any]) -> bool:
        """
        保存持久化数据
        
        Args:
            data: 要保存的数据
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 创建备份
            if self._storage_file.exists():
                shutil.copy2(self._storage_file, self._backup_file)
            
            # 写入临时文件
            temp_file = self._storage_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 原子性替换文件
            shutil.move(temp_file, self._storage_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"持久化存储保存失败，错误: {str(e)}")
            return False


# 创建全局实例
_persistent_storage = PersistentStorage()


def get_persistent_storage() -> PersistentStorage:
    """获取全局持久化存储实例"""
    return _persistent_storage


def set_persistent_data(key: str, value: Any, namespace: str = "default") -> bool:
    """设置持久化数据（便捷函数）"""
    return _persistent_storage.set(key, value, namespace)


def get_persistent_data(key: str, namespace: str = "default", default: Any = None) -> Any:
    """获取持久化数据（便捷函数）"""
    return _persistent_storage.get(key, namespace, default)


def delete_persistent_data(key: str, namespace: str = "default") -> bool:
    """删除持久化数据（便捷函数）"""
    return _persistent_storage.delete(key, namespace)


# 导入sys模块
import sys