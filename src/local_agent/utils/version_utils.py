#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version management utility class
Provides version number extraction, comparison and retrieval functions, supports version management after packaging as exe
"""

import os
import sys
import re
import time
from pathlib import Path
from typing import Optional, Tuple
from ..logger import get_logger

logger = get_logger(__name__)



class VersionUtils:
    """Version number utility class"""
    
    # Version number regular expression patterns
    VERSION_PATTERNS = [
        # Format 1: "ExecutionKit 0.0.1" or "DMR Configuration Schema Tool v0.1.0"
        r'(?:v|V)?(\d+)\.(\d+)\.(\d+)',
        # Format 2: "V0.0.4"
        r'(?:v|V)?(\d+)\.(\d+)',
        # Format 3: Pure number version "1.0" or "1.0.0"
        r'(\d+)(?:\.(\d+))?(?:\.(\d+))?',
        # Format 4: Version with prefix "version 1.2.3"
        r'(?:version|Version|v|V)\s*(\d+)\.(\d+)\.(\d+)',
    ]
    
    @staticmethod
    def extract_version(version_string: str) -> Optional[Tuple[int, int, int]]:
        """
        Extract version number from string
        
        Args:
            version_string: String containing version number
            
        Returns:
            Optional[Tuple[int, int, int]]: Version number tuple (major, minor, patch), returns None if extraction fails
        """
        if not version_string or not isinstance(version_string, str):
            return None
        
        # Clean string, remove extra spaces
        cleaned_string = version_string.strip()
        
        # Try various version number patterns
        for pattern in VersionUtils.VERSION_PATTERNS:
            match = re.search(pattern, cleaned_string)
            if match:
                groups = match.groups()
                
                # Process different formats based on matched group count
                if len(groups) >= 3 and groups[2] is not None:
                    # Format: x.y.z
                    try:
                        major = int(groups[0])
                        minor = int(groups[1])
                        patch = int(groups[2])
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
                
                elif len(groups) >= 2 and groups[1] is not None:
                    # Format: x.y
                    try:
                        major = int(groups[0])
                        minor = int(groups[1])
                        patch = 0  # Default patch version to 0
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
                
                elif len(groups) >= 1 and groups[0] is not None:
                    # Format: x
                    try:
                        major = int(groups[0])
                        minor = 0  # Default minor version to 0
                        patch = 0  # Default patch version to 0
                        return major, minor, patch
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    @staticmethod
    def is_newer_version(new_version_str: str, old_version_str: str) -> bool:
        """
        Compare two version numbers to determine if new_version_str is newer than old_version_str
        
        Args:
            new_version_str: New version string
            old_version_str: Old version string
            
        Returns:
            bool: True means new_version_str is newer, False means not newer version or comparison failed
        """
        logger.info(f"Comparing versions: {new_version_str} vs {old_version_str}")
        
        # Extract version numbers
        new_version = VersionUtils.extract_version(new_version_str)
        old_version = VersionUtils.extract_version(old_version_str)
        
        # Record extracted version numbers
        logger.info(f"Extracted versions: new={new_version}, old={old_version}")
        
        # No new version, return False
        if new_version is None:
            return False
        
        # No old version, return True
        if old_version is None:
            return True
        
        # Compare major version numbers
        if new_version[0] > old_version[0]:
            return True
        elif new_version[0] < old_version[0]:
            return False
        
        # Major version same, compare minor version numbers
        if new_version[1] > old_version[1]:
            return True
        elif new_version[1] < old_version[1]:
            return False
        
        # Major and minor versions same, compare patch version numbers
        if new_version[2] > old_version[2]:
            return True
        
        # All version numbers same, not an update version
        return False
    
    @staticmethod
    def compare_versions(version1_str: str, version2_str: str) -> int:
        """
        Compare two version numbers
        
        Args:
            version1_str: First version string
            version2_str: Second version string
            
        Returns:
            int: 1 means version1 > version2, -1 means version1 < version2, 0 means equal
        """
        version1 = VersionUtils.extract_version(version1_str)
        version2 = VersionUtils.extract_version(version2_str)
        
        if version1 is None or version2 is None:
            return 0  # Return equal when unable to compare
        
        # Compare major version numbers
        if version1[0] > version2[0]:
            return 1
        elif version1[0] < version2[0]:
            return -1
        
        # Major version same, compare minor version numbers
        if version1[1] > version2[1]:
            return 1
        elif version1[1] < version2[1]:
            return -1
        
        # Major and minor versions same, compare patch version numbers
        if version1[2] > version2[2]:
            return 1
        elif version1[2] < version2[2]:
            return -1
        
        # All version numbers same
        return 0
    
    @staticmethod
    def format_version(version_tuple: Tuple[int, int, int]) -> str:
        """
        Format version number tuple to string
        
        Args:
            version_tuple: Version number tuple (major, minor, patch)
            
        Returns:
            str: Formatted version string
        """
        if len(version_tuple) >= 3:
            return f"{version_tuple[0]}.{version_tuple[1]}.{version_tuple[2]}"
        elif len(version_tuple) >= 2:
            return f"{version_tuple[0]}.{version_tuple[1]}"
        else:
            return str(version_tuple[0])


# Convenient functions
def extract_version(version_string: str) -> Optional[Tuple[int, int, int]]:
    """Extract version number from string"""
    return VersionUtils.extract_version(version_string)


def is_newer_version(new_version_str: str, old_version_str: str) -> bool:
    """Compare two version numbers to determine if new_version_str is newer than old_version_str"""
    return VersionUtils.is_newer_version(new_version_str, old_version_str)


def compare_versions(version1_str: str, version2_str: str) -> int:
    """Compare two version numbers"""
    return VersionUtils.compare_versions(version1_str, version2_str)


def format_version(version_tuple: Tuple[int, int, int]) -> str:
    """Format version number tuple to string"""
    return VersionUtils.format_version(version_tuple)


class AppVersionManager:
    """Application version manager - optimized version management strategy"""
    
    def __init__(self):
        self._cached_version = None
        self._version_source = None  # Record version source
        self._version_timestamp = None  # Record version retrieval time
        self._exe_file_hash = None  # Record exe file hash for detecting file changes
    
    def get_app_version(self, is_cache: bool = True) -> str:
        """
        Get application version - fixed version reading strategy (solves issue of version number not updating after update)
        
        Fixed priority strategy (ensures new version can be read after update):
        1. File system VERSION file (exe same directory, updated version)
        2. Runtime environment version (packaged exe version information)
        3. VERSION file in packaged resources (old version from packaging time)
        4. Default version
        
        Returns:
            str: Version number string
        """
        # Check if cache needs to be cleared (detect file changes)
        if is_cache and self._cached_version and self._should_clear_cache():
            logger.info("[Version Management] Detected file changes, clearing cache")
            self._cached_version = None
            self._version_source = None
            self._version_timestamp = None
            self._exe_file_hash = None
        
        # If cached version exists, return directly
        if is_cache and self._cached_version:
            return self._cached_version
        
        # Record version retrieval start time
        start_time = time.time()
        
        # Fixed version retrieval priority strategy (file system first)
        version_sources = [
            ("File system (exe same directory)", self._get_version_from_filesystem),
            ("Runtime environment", self._get_version_from_runtime),
            ("Packaged resources", self._get_version_from_package_resource),
            ("Default version", lambda: "1.0.0")
        ]
        
        version = None
        source_name = "Unknown"
        
        for source_name, get_method in version_sources:
            try:
                version = get_method()
                if version and self._validate_version_format(version):
                    # Record version source and timestamp
                    self._version_source = source_name
                    self._version_timestamp = time.time()
                    
                    # Cache version
                    self._cached_version = version
                    
                    # Record retrieval time
                    elapsed_time = time.time() - start_time
                    
                    logger.info(f"[Version Management] Successfully obtained version from {source_name}: {version} (time: {elapsed_time:.3f}s)")
                    return version
                    
            except Exception as e:
                logger.debug(f"[Version Management] Failed to obtain version from {source_name}: {str(e)}")
        
        # If all methods fail, use default version
        if not version:
            version = "1.0.0"
            source_name = "Default version"
            self._version_source = source_name
            self._version_timestamp = time.time()
            self._cached_version = version
            
            elapsed_time = time.time() - start_time
            logger.warning(f"[Version Management] Using {source_name}: {version} (time: {elapsed_time:.3f}s)")
        
        return version
    
    def _get_version_from_runtime(self) -> Optional[str]:
        """
        Get version information from runtime environment (optimal solution)
        
        Strategy:
        1. Check version information in exe file properties
        2. Check VERSION file in exe same directory (updated version)
        3. Check version information embedded in exe
        
        Returns:
            Optional[str]: Version number string
        """
        try:
            is_frozen = getattr(sys, 'frozen', False)
            
            if is_frozen:
                # Packaged environment: optimal strategy
                
                # Method 1: Check exe file attribute version information
                version = self._get_version_from_exe_properties()
                if version:
                    logger.debug("[Version Management] Successfully obtained version from exe properties")
                    return version
                
                # Method 2: Check VERSION file in exe same directory (updated version)
                exe_dir = Path(sys.executable).parent
                version_file = exe_dir / "VERSION"
                if version_file.exists():
                    with open(version_file, 'r', encoding='utf-8') as f:
                        version = f.read().strip()
                        if self._validate_version_format(version):
                            logger.debug("[Version Management] Successfully obtained version from exe directory VERSION file")
                            return version
                
                # Method 3: Check version information embedded in exe
                version = self._get_version_from_exe_embedded()
                if version:
                    logger.debug("[Version Management] Successfully obtained version from exe embedded data")
                    return version
            
            else:
                # Development environment: directly read project root directory VERSION file
                project_root = self._get_project_root()
                if project_root:
                    version_file = project_root / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[Version Management] Successfully obtained version from project VERSION file in development environment")
                                return version
            
        except Exception as e:
            logger.debug(f"[Version Management] Failed to obtain version from runtime environment: {str(e)}")
        
        return None
    
    def _get_version_from_filesystem(self) -> Optional[str]:
        """
        Get version information from file system (highest priority - fixes issue of reading version after update)
        
        Fixed strategy (ensures new version can be read after update):
        1. Priority check VERSION file in exe same directory (updated version)
        2. Check VERSION file in parent directory of exe location directory (development environment)
        3. Check VERSION file in temporary extraction directory (packaged resources)
        
        Returns:
            Optional[str]: Version number string
        """
        try:
            is_frozen = getattr(sys, 'frozen', False)
            
            # Method 1: Priority check VERSION file in exe same directory (updated version)
            # This is the most critical step to ensure updated program can read new version
            exe_dir = Path(sys.executable).parent
            version_file = exe_dir / "VERSION"
            if version_file.exists():
                with open(version_file, 'r', encoding='utf-8') as f:
                    version = f.read().strip()
                    if self._validate_version_format(version):
                        logger.debug(f"[Version Management] Successfully obtained version from exe directory VERSION file: {version}")
                        return version
            
            # Method 2: Check VERSION file in parent directory of exe location directory (development environment)
            # For development environment, check project root directory
            if not is_frozen:
                project_root = self._get_project_root()
                if project_root:
                    version_file = project_root / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[Version Management] Successfully obtained version from project root VERSION file")
                                return version
            
            # Method 3: Check VERSION file in temporary extraction directory (packaged resources)
            # This is the lowest priority because it's the old version from packaging time
            if is_frozen and hasattr(sys, '_MEIPASS'):
                temp_dir = Path(sys._MEIPASS)
                version_file = temp_dir / "VERSION"
                if version_file.exists():
                    with open(version_file, 'r', encoding='utf-8') as f:
                        version = f.read().strip()
                        if self._validate_version_format(version):
                            logger.debug("[Version Management] Successfully obtained version from temporary extraction directory VERSION file")
                            return version
            
        except Exception as e:
            logger.debug(f"[Version Management] Failed to obtain version from filesystem: {str(e)}")
        
        return None
    
    def _get_version_from_exe_properties(self) -> Optional[str]:
        """
        Get version information from exe file properties
        
        Strategy:
        1. Use win32api to get file version information (Windows system)
        2. Parse exe file version resources
        
        Returns:
            Optional[str]: Version number string
        """
        try:
            if sys.platform == "win32":
                import win32api
                import win32con
                
                exe_path = sys.executable
                
                # Get file version information
                info = win32api.GetFileVersionInfo(exe_path, "\\")
                
                # Extract version number
                ms = info.get('FileVersionMS', 0)
                ls = info.get('FileVersionLS', 0)
                
                if ms > 0 or ls > 0:
                    # Convert version number to string format
                    version_major = (ms >> 16) & 0xFFFF
                    version_minor = ms & 0xFFFF
                    version_build = (ls >> 16) & 0xFFFF
                    version_revision = ls & 0xFFFF
                    
                    version = f"V{version_major}.{version_minor}.{version_build}"
                    if self._validate_version_format(version):
                        logger.debug("[Version Management] Successfully obtained version from exe properties")
                        return version
            
        except ImportError:
            logger.debug("[Version Management] win32api module not available, skipping exe property version retrieval")
        except Exception as e:
            logger.debug(f"[Version Management] Failed to obtain version from exe properties: {str(e)}")
        
        return None
    
    def _get_version_from_exe_embedded(self) -> Optional[str]:
        """
        Get version from version information embedded in exe
        
        Strategy:
        1. Check if exe contains version metadata
        2. Parse exe version resource strings
        
        Returns:
            Optional[str]: Version number string
        """
        try:
            # Method 1: Check exe version resource strings
            if sys.platform == "win32":
                import win32api
                
                exe_path = sys.executable
                
                # Get file version information strings
                version_info = win32api.GetFileVersionInfo(exe_path, "\\StringFileInfo\\")
                
                if version_info:
                    # Try to get version information from string table
                    for lang_charset in version_info:
                        string_table = version_info[lang_charset]
                        if 'ProductVersion' in string_table:
                            version = string_table['ProductVersion']
                            if self._validate_version_format(version):
                                logger.debug("[Version Management] Successfully obtained version from exe internal version resources")
                                return version
                        elif 'FileVersion' in string_table:
                            version = string_table['FileVersion']
                            if self._validate_version_format(version):
                                logger.debug("[Version Management] Successfully obtained version from exe internal file version")
                                return version
            
        except ImportError:
            logger.debug("[Version Management] win32api module not available, skipping exe internal version retrieval")
        except Exception as e:
            logger.debug(f"[Version Management] Failed to obtain version from exe embedded data: {str(e)}")
        
        return None
    
    def _get_version_from_package_resource(self) -> Optional[str]:
        """Get version information from packaged resources"""
        try:
            # Check if packaged as exe
            if getattr(sys, 'frozen', False):
                # Packaged environment: Try to read VERSION file from temporary extraction directory
                if hasattr(sys, '_MEIPASS'):
                    temp_dir = Path(sys._MEIPASS)
                    version_file = temp_dir / "VERSION"
                    if version_file.exists():
                        with open(version_file, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                            if self._validate_version_format(version):
                                logger.debug("[Version Management] Successfully read VERSION file from package resources")
                                return version
        except Exception as e:
            logger.debug(f"[Version Management] Failed to obtain version from package resources: {str(e)}")
        
        return None
    
    def _should_clear_cache(self) -> bool:
        """
        Check if cache needs to be cleared (detect if exe file has changed)
        
        Returns:
            bool: True means cache needs to be cleared, False means no need
        """
        try:
            # Only check file changes in packaged environment
            if not getattr(sys, 'frozen', False):
                return False
            
            # Get current exe file path
            exe_path = Path(sys.executable)
            if not exe_path.exists():
                return False
            
            # Calculate current exe file hash
            current_hash = self._get_exe_file_hash(exe_path)
            
            # If it's the first retrieval, record hash value
            if self._exe_file_hash is None:
                self._exe_file_hash = current_hash
                return False
            
            # Compare hash values, if different then file has been updated
            if current_hash != self._exe_file_hash:
                logger.info(f"[Version Management] Detected exe file changes, old hash: {self._exe_file_hash}, new hash: {current_hash}")
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"[Version Management] Failed to check cache clearing conditions: {str(e)}")
            return False
    
    def _get_exe_file_hash(self, file_path: Path) -> str:
        """
        Calculate exe file hash (use file size and modification time as simple hash)
        
        Args:
            file_path: File path
            
        Returns:
            str: File hash value
        """
        try:
            stat = file_path.stat()
            # Use file size and modification time as hash value
            return f"{stat.st_size}_{stat.st_mtime}"
        except Exception as e:
            logger.debug(f"[Version Management] Failed to calculate file hash: {str(e)}")
            return "unknown"
    
    def _get_version_from_setup(self) -> Optional[str]:
        """Get version information from setup.py"""
        try:
            # Get project root directory
            project_root = self._get_project_root()
            if not project_root:
                return None
            
            setup_file = project_root / "setup.py"
            if setup_file.exists():
                with open(setup_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Simple regex matching version number
                    match = re.search(r"version\s*=\s*['\"]([^'\"]+)['\"]", content)
                    if match:
                        version = match.group(1)
                        if self._validate_version_format(version):
                            return version
            
        except Exception as e:
            logger.warning(f"Failed to obtain version from setup.py: {str(e)}")
        
        return None
    
    def _get_project_root(self) -> Optional[Path]:
        """Get project root directory"""
        try:
            # Check if packaged as exe
            is_frozen = getattr(sys, 'frozen', False)
            
            if is_frozen:
                # When packaged as exe, return executable file directory
                return Path(sys.executable).parent
            else:
                # Development environment, return parent directory of current file directory
                # Because current file path is: f:\testPc\dragTest\src\local_agent\utils\version_utils.py
                # Need to return to: f:\testPc\dragTest
                current_file = Path(__file__).resolve()
                return current_file.parent.parent.parent.parent
                
        except Exception as e:
            logger.warning(f"Failed to obtain project root directory: {str(e)}")
            return None
    
    def _validate_version_format(self, version: str) -> bool:
        """Validate version number format"""
        if not version or not isinstance(version, str):
            return False
        
        # Simple version number format validation (x.y.z or x.y)
        pattern = r'^\d+(\.\d+)*$'
        return bool(re.match(pattern, version.strip()))
    
    def get_version_info(self) -> dict:
        """Get detailed version information"""
        version = self.get_app_version()
        
        # Get packaging information
        is_frozen = getattr(sys, 'frozen', False)
        build_type = "Packaged version" if is_frozen else "Development version"
        
        return {
            "version": version,
            "build_type": build_type,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "executable_path": sys.executable if is_frozen else "Development environment"
        }


# Create global instance
_app_version_manager = AppVersionManager()


def get_app_version(is_cache: bool = True) -> str:
    """Get application version"""
    return _app_version_manager.get_app_version(is_cache)


def get_version_info() -> dict:
    """Get detailed version information"""
    return _app_version_manager.get_version_info()