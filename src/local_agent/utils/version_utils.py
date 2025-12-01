#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本管理工具类
提供版本号提取、比较和获取功能，支持打包为exe后的版本管理
"""

import os
import sys
import re
import time
from pathlib import Path
from typing import Optional, Tuple, List
from ..logger import get_logger

logger = get_logger(__name__)



class VersionUtils:
    """版本号工具类"""
    
    # 版本号正则表达式模式
    VERSION_PATTERNS = [
        # 格式1: "ExecutionKit 0.0.1" 或 "DMR Configuration Schema Tool v0.1.0"
        r'(?:v|V)?(\d+)\.(\d+)\.(\d+)',
        # 格式2: "V0.0.4"
        r'(?:v|V)?(\d+)\.(\d+)',
        # 格式3: 纯数字版本 "1.0" 或 "1.0.0"
        r'(\d+)(?:\.(\d+))?(?:\.(\d+))?',
        # 格式4: 带前缀的版本 "version 1.2.3"
        r'(?:version|Version|v|V)\s*(\d+)\.(\d+)\.(\d+)',
    ]
    
    @staticmethod
    def extract_version(version_string: str) -> Optional[Tuple[int, int, int]]:
        """
        从字符串中提取版本号
        
        Args:
            version_string: 包含版本号的字符串
            
        Returns:
            Optional[Tuple[int, int, int]]: 版本号元组 (主版本, 次版本, 修订版本)，如果提取失败返回None
        """
        if not version_string or not isinstance(version_string, str):
            return None
        
        # 清理字符串，移除多余空格
        cleaned_string = version_string.strip()
        
        # 尝试各种版本号模式
        for pattern in VersionUtils.VERSION_PATTERNS:
            match = re.search(pattern, cleaned_string)
            if match:
                groups = match.groups()
                
                # 根据匹配到的组数处理不同格式
                if len(groups) >= 3 and groups[2] is not None:
                    # 格式: x.y.z
                    try:
                        major = int(groups[0])
                        minor = int(groups[1])
                        patch = int(groups[2])
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
                
                elif len(groups) >= 2 and groups[1] is not None:
                    # 格式: x.y
                    try:
                        major = int(groups[0])
                        minor = int(groups[1])
                        patch = 0  # 默认修订版本为0
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
                
                elif len(groups) >= 1 and groups[0] is not None:
                    # 格式: x
                    try:
                        major = int(groups[0])
                        minor = 0  # 默认次版本为0
                        patch = 0  # 默认修订版本为0
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    @staticmethod
    def is_newer_version(new_version_str: str, old_version_str: str) -> bool:
        """
        比较两个版本号，判断new_version_str是否比old_version_str更新
        
        Args:
            new_version_str: 新版本字符串
            old_version_str: 旧版本字符串
            
        Returns:
            bool: True表示new_version_str更新，False表示不是更新版本或比较失败
        """
        logger.info(f"比较版本号: {new_version_str} vs {old_version_str}")
        
        # 提取版本号
        new_version = VersionUtils.extract_version(new_version_str)
        old_version = VersionUtils.extract_version(old_version_str)
        
        # 记录提取到的版本号
        logger.info(f"提取到的版本号: new={new_version}, old={old_version}")
        
        # 没有新版本，返回False
        if new_version is None:
            return False
        
        # 没有旧版本，返回True
        if old_version is None:
            return True
        
        # 比较主版本号
        if new_version[0] > old_version[0]:
            return True
        elif new_version[0] < old_version[0]:
            return False
        
        # 主版本相同，比较次版本号
        if new_version[1] > old_version[1]:
            return True
        elif new_version[1] < old_version[1]:
            return False
        
        # 主次版本相同，比较修订版本号
        if new_version[2] > old_version[2]:
            return True
        
        # 所有版本号都相同，不是更新版本
        return False
    
    @staticmethod
    def compare_versions(version1_str: str, version2_str: str) -> int:
        """
        比较两个版本号
        
        Args:
            version1_str: 第一个版本字符串
            version2_str: 第二个版本字符串
            
        Returns:
            int: 1表示version1 > version2, -1表示version1 < version2, 0表示相等
        """
        version1 = VersionUtils.extract_version(version1_str)
        version2 = VersionUtils.extract_version(version2_str)
        
        if version1 is None or version2 is None:
            return 0  # 无法比较时返回相等
        
        # 比较主版本号
        if version1[0] > version2[0]:
            return 1
        elif version1[0] < version2[0]:
            return -1
        
        # 主版本相同，比较次版本号
        if version1[1] > version2[1]:
            return 1
        elif version1[1] < version2[1]:
            return -1
        
        # 主次版本相同，比较修订版本号
        if version1[2] > version2[2]:
            return 1
        elif version1[2] < version2[2]:
            return -1
        
        # 所有版本号都相同
        return 0
    
    @staticmethod
    def format_version(version_tuple: Tuple[int, int, int]) -> str:
        """
        格式化版本号元组为字符串
        
        Args:
            version_tuple: 版本号元组 (主版本, 次版本, 修订版本)
            
        Returns:
            str: 格式化后的版本字符串
        """
        if len(version_tuple) >= 3:
            return f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"
        elif len(version_tuple) >= 2:
            return f"{version_tuple[0]}.{version_tuple[1]}"
        else:
            return str(version_tuple[0])


# 便捷函数
def extract_version(version_string: str) -> Optional[Tuple[int, int, int]]:
    """从字符串中提取版本号"""
    return VersionUtils.extract_version(version_string)


def is_newer_version(new_version_str: str, old_version_str: str) -> bool:
    """比较两个版本号，判断new_version_str是否比old_version_str更新"""
    return VersionUtils.is_newer_version(new_version_str, old_version_str)


def compare_versions(version1_str: str, version2_str: str) -> int:
    """比较两个版本号"""
    return VersionUtils.compare_versions(version1_str, version2_str)


def format_version(version_tuple: Tuple[int, int, int]) -> str:
    """格式化版本号元组为字符串"""
    return VersionUtils.format_version(version_tuple)


class AppVersionManager:
    """应用程序版本管理器 - 优化版本管理策略"""
    
    def __init__(self):
        self._cached_version = None
        self._version_source = None  # 记录版本来源
        self._version_timestamp = None  # 记录版本获取时间
        self._exe_file_hash = None  # 记录exe文件哈希，用于检测文件变化
    
    def get_app_version(self, is_cache: bool = True) -> str:
        """
        获取应用程序版本 - 修复版本读取策略（解决更新后版本号未更新问题）
        
        修复后的优先级策略（确保更新后能读取新版本）：
        1. 文件系统VERSION文件（exe同级目录，更新后版本）
        2. 运行时环境版本（打包后exe的版本信息）
        3. 打包资源中的VERSION文件（打包时的旧版本）
        4. 默认版本
        
        Returns:
            str: 版本号字符串
        """
        # 检查是否需要清除缓存（检测文件变化）
        if is_cache and self._cached_version and self._should_clear_cache():
            logger.info("[版本管理] 检测到文件变化，清除缓存")
            self._cached_version = None
            self._version_source = None
            self._version_timestamp = None
            self._exe_file_hash = None
        
        # 如果已有缓存版本，直接返回
        if is_cache and self._cached_version:
            return self._cached_version
        
        # 记录版本获取开始时间
        start_time = time.time()
        
        # 修复后的版本获取优先级策略（文件系统优先）
        version_sources = [
            ("文件系统（exe同级目录）", self._get_version_from_filesystem),
            ("运行时环境", self._get_version_from_runtime),
            ("打包资源", self._get_version_from_package_resource),
            ("默认版本", lambda: "1.0.0")
        ]
        
        version = None
        source_name = "未知"
        
        for source_name, get_method in version_sources:
            try:
                version = get_method()
                if version and self._validate_version_format(version):
                    # 记录版本来源和时间戳
                    self._version_source = source_name
                    self._version_timestamp = time.time()
                    
                    # 缓存版本
                    self._cached_version = version
                    
                    # 记录获取耗时
                    elapsed_time = time.time() - start_time
                    
                    logger.info(f"[版本管理] 从{source_name}获取版本成功: {version} (耗时: {elapsed_time:.3f}s)")
                    return version
                    
            except Exception as e:
                logger.debug(f"[版本管理] 从{source_name}获取版本失败: {str(e)}")
        
        # 如果所有方法都失败，使用默认版本
        if not version:
            version = "1.0.0"
            source_name = "默认版本"
            self._version_source = source_name
            self._version_timestamp = time.time()
            self._cached_version = version
            
            elapsed_time = time.time() - start_time
            logger.warning(f"[版本管理] 使用{source_name}: {version} (耗时: {elapsed_time:.3f}s)")
        
        return version
    
    def _get_version_from_runtime(self) -> Optional[str]:
        """
        从运行时环境获取版本信息（最优方案）
        
        策略：
        1. 检查exe文件属性中的版本信息
        2. 检查exe同级目录的VERSION文件（更新后版本）
        3. 检查exe内部嵌入的版本信息
        
        Returns:
            Optional[str]: 版本号字符串
        """
        try:
            is_frozen = getattr(sys, 'frozen', False)
            
            if is_frozen:
                # 打包环境：最优策略
                
                # 方法1: 检查exe文件属性版本信息
                version = self._get_version_from_exe_properties()
                if version:
                    logger.debug("[版本管理] 从exe文件属性获取版本成功")
                    return version
                
                # 方法2: 检查exe同级目录的VERSION文件（更新后版本）
                exe_dir = Path(sys.executable).parent
                version_file = exe_dir / "VERSION"
                if version_file.exists():
                    with open(version_file, 'r', encoding='utf-8') as f:
                        version = f.read().strip()
                        if self._validate_version_format(version):
                            logger.debug("[版本管理] 从exe同级目录VERSION文件获取版本成功")
                            return version
                
                # 方法3: 检查exe内部嵌入的版本信息
                version = self._get_version_from_exe_embedded()
                if version:
                    logger.debug("[版本管理] 从exe内部嵌入版本获取成功")
                    return version
            
            else:
                # 开发环境：直接读取项目根目录VERSION文件
                project_root = self._get_project_root()
                if project_root:
                    version_file = project_root / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[版本管理] 开发环境从项目VERSION文件获取版本成功")
                                return version
            
        except Exception as e:
            logger.debug(f"[版本管理] 从运行时环境获取版本失败: {str(e)}")
        
        return None
    
    def _get_version_from_filesystem(self) -> Optional[str]:
        """
        从文件系统获取版本信息（最高优先级 - 修复更新后版本读取问题）
        
        修复后的策略（确保更新后能读取新版本）：
        1. 优先检查exe同级目录的VERSION文件（更新后版本）
        2. 检查exe所在目录的上级目录的VERSION文件（开发环境）
        3. 检查临时解压目录的VERSION文件（打包资源）
        
        Returns:
            Optional[str]: 版本号字符串
        """
        try:
            is_frozen = getattr(sys, 'frozen', False)
            
            # 方法1: 优先检查exe同级目录的VERSION文件（更新后版本）
            # 这是最关键的一步，确保更新后的程序能读取新版本
            exe_dir = Path(sys.executable).parent
            version_file = exe_dir / "VERSION"
            if version_file.exists():
                with open(version_file, 'r', encoding='utf-8') as f:
                    version = f.read().strip()
                    if self._validate_version_format(version):
                        logger.debug(f"[版本管理] 从exe同级目录VERSION文件获取版本成功: {version}")
                        return version
            
            # 方法2: 检查exe所在目录的上级目录的VERSION文件（开发环境）
            # 对于开发环境，检查项目根目录
            if not is_frozen:
                project_root = self._get_project_root()
                if project_root:
                    version_file = project_root / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[版本管理] 从项目根目录VERSION文件获取版本成功")
                                return version
            
            # 方法3: 检查临时解压目录的VERSION文件（打包资源）
            # 这是最低优先级，因为这是打包时的旧版本
            if is_frozen and hasattr(sys, '_MEIPASS'):
                temp_dir = Path(sys._MEIPASS)
                version_file = temp_dir / "VERSION"
                if version_file.exists():
                    with open(version_file, 'r', encoding='utf-8') as f:
                        version = f.read().strip()
                        if self._validate_version_format(version):
                            logger.debug("[版本管理] 从临时解压目录VERSION文件获取版本成功")
                            return version
            
        except Exception as e:
            logger.debug(f"[版本管理] 从文件系统获取版本失败: {str(e)}")
        
        return None
    
    def _get_version_from_exe_properties(self) -> Optional[str]:
        """
        从exe文件属性中获取版本信息
        
        策略：
        1. 使用win32api获取文件版本信息（Windows系统）
        2. 解析exe文件的版本资源
        
        Returns:
            Optional[str]: 版本号字符串
        """
        try:
            if sys.platform == "win32":
                import win32api
                import win32con
                
                exe_path = sys.executable
                
                # 获取文件版本信息
                info = win32api.GetFileVersionInfo(exe_path, "\\")
                
                # 提取版本号
                ms = info.get('FileVersionMS', 0)
                ls = info.get('FileVersionLS', 0)
                
                if ms > 0 or ls > 0:
                    # 将版本号转换为字符串格式
                    version_major = (ms >> 16) & 0xFFFF
                    version_minor = ms & 0xFFFF
                    version_build = (ls >> 16) & 0xFFFF
                    version_revision = ls & 0xFFFF
                    
                    version = f"V{version_major}.{version_minor}.{version_build}"
                    if self._validate_version_format(version):
                        logger.debug("[版本管理] 从exe文件属性获取版本成功")
                        return version
            
        except ImportError:
            logger.debug("[版本管理] win32api模块不可用，跳过exe属性版本获取")
        except Exception as e:
            logger.debug(f"[版本管理] 从exe文件属性获取版本失败: {str(e)}")
        
        return None
    
    def _get_version_from_exe_embedded(self) -> Optional[str]:
        """
        从exe内部嵌入的版本信息获取版本
        
        策略：
        1. 检查exe内部是否包含版本元数据
        2. 解析exe的版本资源字符串
        
        Returns:
            Optional[str]: 版本号字符串
        """
        try:
            # 方法1: 检查exe的版本资源字符串
            if sys.platform == "win32":
                import win32api
                
                exe_path = sys.executable
                
                # 获取文件版本信息字符串
                version_info = win32api.GetFileVersionInfo(exe_path, "\\StringFileInfo\\")
                
                if version_info:
                    # 尝试从字符串表获取版本信息
                    for lang_charset in version_info:
                        string_table = version_info[lang_charset]
                        if 'ProductVersion' in string_table:
                            version = string_table['ProductVersion']
                            if self._validate_version_format(version):
                                logger.debug("[版本管理] 从exe内部版本资源获取版本成功")
                                return version
                        elif 'FileVersion' in string_table:
                            version = string_table['FileVersion']
                            if self._validate_version_format(version):
                                logger.debug("[版本管理] 从exe内部文件版本获取版本成功")
                                return version
            
        except ImportError:
            logger.debug("[版本管理] win32api模块不可用，跳过exe内部版本获取")
        except Exception as e:
            logger.debug(f"[版本管理] 从exe内部嵌入版本获取失败: {str(e)}")
        
        return None
    
    def _get_version_from_package_resource(self) -> Optional[str]:
        """从打包资源中获取版本信息"""
        try:
            # 检查是否打包为exe
            if getattr(sys, 'frozen', False):
                # 打包环境：尝试从临时解压目录读取VERSION文件
                if hasattr(sys, '_MEIPASS'):
                    temp_dir = Path(sys._MEIPASS)
                    version_file = temp_dir / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[版本管理] 从打包资源中读取VERSION文件成功")
                                return version
        except Exception as e:
            logger.debug(f"[版本管理] 从打包资源获取版本失败: {str(e)}")
        
        return None
    
    def _should_clear_cache(self) -> bool:
        """
        检查是否需要清除缓存（检测exe文件是否发生变化）
        
        Returns:
            bool: True表示需要清除缓存，False表示不需要
        """
        try:
            # 只在打包环境中检查文件变化
            if not getattr(sys, 'frozen', False):
                return False
            
            # 获取当前exe文件路径
            exe_path = Path(sys.executable)
            if not exe_path.exists():
                return False
            
            # 计算当前exe文件的哈希值
            current_hash = self._get_exe_file_hash(exe_path)
            
            # 如果是第一次获取，记录哈希值
            if self._exe_file_hash is None:
                self._exe_file_hash = current_hash
                return False
            
            # 比较哈希值，如果不同则文件已更新
            if current_hash != self._exe_file_hash:
                logger.info(f"[版本管理] 检测到exe文件变化，旧哈希: {self._exe_file_hash}, 新哈希: {current_hash}")
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"[版本管理] 检查缓存清除条件失败: {str(e)}")
            return False
    
    def _get_exe_file_hash(self, file_path: Path) -> str:
        """
        计算exe文件的哈希值（使用文件大小和修改时间作为简单哈希）
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 文件哈希值
        """
        try:
            stat = file_path.stat()
            # 使用文件大小和修改时间作为哈希值
            return f"{stat.st_size}_{stat.st_mtime}"
        except Exception as e:
            logger.debug(f"[版本管理] 计算文件哈希失败: {str(e)}")
            return "unknown"
    
    def _get_version_from_setup(self) -> Optional[str]:
        """从setup.py获取版本信息"""
        try:
            # 获取项目根目录
            project_root = self._get_project_root()
            if not project_root:
                return None
            
            setup_file = project_root / "setup.py"
            if setup_file.exists():
                with open(setup_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 简单的正则匹配版本号
                    match = re.search(r"version\s*=\s*['\"]([^'\"]+)['\"]", content)
                    if match:
                        version = match.group(1)
                        if self._validate_version_format(version):
                            return version
            
        except Exception as e:
            logger.warning(f"从setup.py获取版本失败: {str(e)}")
        
        return None
    
    def _get_project_root(self) -> Optional[Path]:
        """获取项目根目录"""
        try:
            # 检查是否打包为exe
            is_frozen = getattr(sys, 'frozen', False)
            
            if is_frozen:
                # 打包为exe时，返回可执行文件所在目录
                return Path(sys.executable).parent
            else:
                # 开发环境，返回当前文件所在目录的父目录的父目录的父目录
                # 因为当前文件路径是: f:\testPc\dragTest\src\local_agent\utils\version_utils.py
                # 需要返回到: f:\testPc\dragTest
                current_file = Path(__file__).resolve()
                return current_file.parent.parent.parent.parent
                
        except Exception as e:
            logger.warning(f"获取项目根目录失败: {str(e)}")
            return None
    
    def _validate_version_format(self, version: str) -> bool:
        """验证版本号格式"""
        if not version or not isinstance(version, str):
            return False
        
        # 简单的版本号格式验证（x.y.z 或 x.y）
        pattern = r'^\d+(\.\d+)*$'
        return bool(re.match(pattern, version.strip()))
    
    def get_version_info(self) -> dict:
        """获取详细的版本信息"""
        version = self.get_app_version()
        
        # 获取打包信息
        is_frozen = getattr(sys, 'frozen', False)
        build_type = "打包版本" if is_frozen else "开发版本"
        
        return {
            "version": version,
            "build_type": build_type,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "executable_path": sys.executable if is_frozen else "开发环境"
        }


# 创建全局实例
_app_version_manager = AppVersionManager()


def get_app_version(is_cache: bool = True) -> str:
    """获取应用程序版本"""
    return _app_version_manager.get_app_version(is_cache)


def get_version_info() -> dict:
    """获取详细的版本信息"""
    return _app_version_manager.get_version_info()