#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Persistent storage module
Provides global persistent storage functionality, supports cross-process, cross-restart data persistence

Main features:
1. File system persistent storage
2. Automatic data serialization/deserialization
3. Data version management and migration
4. Atomic operation guarantee
5. Automatic backup and recovery

Usage scenarios:
- Update failure time records
- Application configuration persistence
- Runtime state saving
- Cross-restart data sharing
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
    Persistent storage manager - Provides global persistent storage functionality
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize persistent storage
        
        Args:
            storage_dir: Storage directory path, uses default directory when None
        """
        self.logger = get_logger(__name__)
        
        # [Determine storage] directory
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # Default [storage] directory: .persistent_data [under project] root [directory]
            project_root = self._get_project_root()
            self.storage_dir = project_root / ".persistent_data"
        
        # [Ensure] storage [directory] exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread [lock], [ensure concurrent safety]
        self._lock = threading.RLock()
        
        # [Memory] cache, [improve read performance]
        self._memory_cache: Dict[str, Any] = {}
        
        # [Storage] file path
        self._storage_file = self.storage_dir / "data.json"
        self._backup_file = self.storage_dir / "data_backup.json"
        
        self.logger.info(f"Persistent storage initialized, storage directory: {self.storage_dir}")
    
    def _get_project_root(self) -> Path:
        """Get project [root directory]"""
        try:
            # Check [if packaged as] exe
            if getattr(sys, 'frozen', False):
                # [Packaged as] exe [when], [return executable] file [location] directory
                return Path(sys.executable).parent
            else:
                # [Development] environment, [return current] file [location] directory [[parent]] directory [[parent]] directory
                current_file = Path(__file__).resolve()
                return current_file.parent.parent.parent.parent
        except Exception:
            # [Fallback solution]: [use current working] directory
            return Path.cwd()
    
    def set(self, key: str, value: Any, namespace: str = "default") -> bool:
        """
        Set persistent data
        
        Args:
            key: Data key
            value: Data value (supports JSON serializable types)
            namespace: Namespace, used for data classification
            
        Returns:
            bool: Whether setting was successful
        """
        with self._lock:
            try:
                # [Read existing data]
                data = self._load_data()
                
                # [Ensure namespace exists]
                if namespace not in data:
                    data[namespace] = {}
                
                # Setup [data]
                data[namespace][key] = {
                    'value': value,
                    'timestamp': time.time(),
                    'datetime': datetime.now().isoformat()
                }
                
                # Save [data]
                success = self._save_data(data)
                
                if success:
                    # Update [memory] cache
                    cache_key = f"{namespace}:{key}"
                    self._memory_cache[cache_key] = data[namespace][key]
                    self.logger.debug(f"Persistent storage set successful: {namespace}.{key}")
                
                return success
                
            except Exception as e:
                self.logger.error(f"Persistent storage set failed: {namespace}.{key}, error: {str(e)}")
                return False
    
    def get(self, key: str, namespace: str = "default", default: Any = None) -> Any:
        """
        Get persistent data
        
        Args:
            key: Data key
            namespace: Namespace
            default: Default value
            
        Returns:
            Any: Data value or default value
        """
        with self._lock:
            try:
                # Check [memory] cache
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return self._memory_cache[cache_key]['value']
                
                # [Read] file [data]
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    value_data = data[namespace][key]
                    
                    # Update [memory] cache
                    self._memory_cache[cache_key] = value_data
                    
                    return value_data['value']
                
                return default
                
            except Exception as e:
                self.logger.error(f"Persistent storage get failed: {namespace}.{key}, error: {str(e)}")
                return default
    
    def get_with_metadata(self, key: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        """
        Get persistent data and its metadata
        
        Args:
            key: Data key
            namespace: Namespace
            
        Returns:
            Optional[Dict]: Dictionary containing data and metadata, None means not exists
        """
        with self._lock:
            try:
                # Check [memory] cache
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return self._memory_cache[cache_key]
                
                # [Read] file [data]
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    value_data = data[namespace][key]
                    
                    # Update [memory] cache
                    self._memory_cache[cache_key] = value_data
                    
                    return value_data
                
                return None
                
            except Exception as e:
                self.logger.error(f"Persistent storage get metadata failed: {namespace}.{key}, error: {str(e)}")
                return None
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        """
        Delete persistent data
        
        Args:
            key: Data key
            namespace: Namespace
            
        Returns:
            bool: Whether deletion was successful
        """
        with self._lock:
            try:
                # [Read existing data]
                data = self._load_data()
                
                if namespace in data and key in data[namespace]:
                    # Delete [data]
                    del data[namespace][key]
                    
                    # If [[namespace] is empty], delete [namespace]
                    if not data[namespace]:
                        del data[namespace]
                    
                    # Save [data]
                    success = self._save_data(data)
                    
                    # [Clean memory] cache
                    cache_key = f"{namespace}:{key}"
                    if cache_key in self._memory_cache:
                        del self._memory_cache[cache_key]
                    
                    if success:
                        self.logger.debug(f"Persistent storage delete successful: {namespace}.{key}")
                    
                    return success
                
                return True  # Data does not exist, considered as delete success
                
            except Exception as e:
                self.logger.error(f"Persistent storage delete failed: {namespace}.{key}, error: {str(e)}")
                return False
    
    def exists(self, key: str, namespace: str = "default") -> bool:
        """
        Check if data exists
        
        Args:
            key: Data key
            namespace: Namespace
            
        Returns:
            bool: Whether data exists
        """
        with self._lock:
            try:
                # Check [memory] cache
                cache_key = f"{namespace}:{key}"
                if cache_key in self._memory_cache:
                    return True
                
                # [Read] file [data]
                data = self._load_data()
                
                return namespace in data and key in data[namespace]
                
            except Exception:
                return False
    
    def list_keys(self, namespace: str = "default") -> list:
        """
        List all keys in namespace
        
        Args:
            namespace: Namespace
            
        Returns:
            list: List of keys
        """
        with self._lock:
            try:
                data = self._load_data()
                
                if namespace in data:
                    return list(data[namespace].keys())
                
                return []
                
            except Exception as e:
                self.logger.error(f"Persistent storage list keys failed: {namespace}, error: {str(e)}")
                return []
    
    def list_namespaces(self) -> list:
        """
        List all namespaces
        
        Returns:
            list: List of namespaces
        """
        with self._lock:
            try:
                data = self._load_data()
                return list(data.keys())
                
            except Exception as e:
                self.logger.error(f"Persistent storage list namespaces failed, error: {str(e)}")
                return []
    
    def clear_namespace(self, namespace: str = "default") -> bool:
        """
        Clear all data in namespace
        
        Args:
            namespace: Namespace
            
        Returns:
            bool: Whether clearing was successful
        """
        with self._lock:
            try:
                data = self._load_data()
                
                if namespace in data:
                    # [Clear namespace]
                    data[namespace] = {}
                    
                    # Save [data]
                    success = self._save_data(data)
                    
                    # [Clean memory] cache
                    keys_to_remove = [k for k in self._memory_cache.keys() if k.startswith(f"{namespace}:")]
                    for key in keys_to_remove:
                        del self._memory_cache[key]
                    
                    if success:
                        self.logger.debug(f"Persistent storage clear namespace successful: {namespace}")
                    
                    return success
                
                return True  # Namespace does not exist, considered as clear success
                
            except Exception as e:
                self.logger.error(f"Persistent storage clear namespace failed: {namespace}, error: {str(e)}")
                return False
    
    def _load_data(self) -> Dict[str, Any]:
        """
        Load persistent data
        
        Returns:
            Dict: Persistent data
        """
        try:
            if self._storage_file.exists():
                with open(self._storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Validate [data structure]
                if isinstance(data, dict):
                    return data
                else:
                    self.logger.warning("Persistent storage file format error, using default data")
                    return {}
            else:
                # File [does not exist], [return empty data]
                return {}
                
        except Exception as e:
            self.logger.warning(f"Persistent storage load failed, using default data, error: {str(e)}")
            
            # Try [to restore from] backup file
            if self._backup_file.exists():
                try:
                    with open(self._backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, dict):
                        # [Restore] backup file
                        self._save_data(data)
                        self.logger.info("Persistent storage restored from backup file successfully")
                        return data
                except Exception:
                    pass
            
            return {}
    
    def _save_data(self, data: Dict[str, Any]) -> bool:
        """
        Save persistent data
        
        Args:
            data: Data to save
            
        Returns:
            bool: Whether saving was successful
        """
        try:
            # Create backup
            if self._storage_file.exists():
                shutil.copy2(self._storage_file, self._backup_file)
            
            # [Write to temporary] file
            temp_file = self._storage_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # [Atomically replace] file
            shutil.move(temp_file, self._storage_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Persistent storage save failed, error: {str(e)}")
            return False


# Create global instance
_persistent_storage = PersistentStorage()


def get_persistent_storage() -> PersistentStorage:
    """Get global [persistent storage instance]"""
    return _persistent_storage


def set_persistent_data(key: str, value: Any, namespace: str = "default") -> bool:
    """Set [persistent data] ([convenient] function)"""
    return _persistent_storage.set(key, value, namespace)


def get_persistent_data(key: str, namespace: str = "default", default: Any = None) -> Any:
    """Get [persistent data] ([convenient] function)"""
    return _persistent_storage.get(key, namespace, default)


def delete_persistent_data(key: str, namespace: str = "default") -> bool:
    """Delete [persistent data] ([convenient] function)"""
    return _persistent_storage.delete(key, namespace)


# [Import] sys module
import sys