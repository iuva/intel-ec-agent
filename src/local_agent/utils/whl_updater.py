#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WHL package overlay update tool
Performs software overlay updates based on whl package URL, supports resumable downloads and error retry

Main features:
1. Download whl package file
2. Use pip for overlay installation
3. Support rollback mechanism
4. Complete logging

Usage example:
    from local_agent.utils.whl_updater import update_from_whl
    success = update_from_whl("https://example.com/package-1.0.0-py3-none-any.whl")
"""

import os
import sys
import time
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional, Tuple

# [Import] project global components
from ..logger import get_logger
# [Import enhanced subprocess utility]
from .subprocess_utils import run_with_logging
# Delay[Import to avoid loop dependency]
def _get_download_file():
    from .file_downloader import download_file_async
    return download_file_async

download_file = None  # DelayInitialize
from .python_utils import PythonUtils
from .path_utils import PathUtils


class WhlUpdater:
    """WHL package overlay update utility class"""
    
    def __init__(self):
        """Initialize updater"""
        self.logger = get_logger(__name__)
        self.temp_dir = PathUtils.get_root_path() / "whl_updates"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration parameter
        self.max_retries = 3
        self.timeout = 1200  # 20 minute timeout
        self.backup_enabled = True
        
        self.logger.info(f"WHL updater initialized, temporary directory: {self.temp_dir}")
    
    def _get_python_executable(self) -> Optional[str]:
        """
        Get Python executable path using Python utility class
        
        Returns:
            Optional[str]: Python executable file path, returns None if not found
        """
        try:
            python_path = PythonUtils.get_python_check()
            if python_path:
                self.logger.info(f"Python path obtained: {python_path}")
                return python_path
            else:
                self.logger.warning("No available Python path found")
                return None
        except Exception as e:
            self.logger.error(f"Failed to get Python path: {e}")
            return None
    
    async def _download_whl_file(self, whl_url: str) -> Optional[Path]:
        """
        Download whl package file
        
        Args:
            whl_url: whl package download URL
            version: Version number
            
        Returns:
            Optional[Path]: Downloaded whl file path, returns None if failed
        """
        try:
            # Extract filename from URL
            filename = whl_url.split('/')[-1]
            if not filename.endswith('.whl'):
                self.logger.error(f"URL format error, not a valid whl file: {whl_url}")
                return None
            
            # Save path
            save_path = self.temp_dir / filename
            
            self.logger.info(f"Starting whl package download: {whl_url}")
            self.logger.info(f"Saving to: {save_path}")
            
            # Delay load download function
            global download_file
            if download_file is None:
                download_file = _get_download_file()
            
            # Use project's unified file downloader
            success = await download_file(whl_url, str(save_path))
            
            if success and save_path.exists():
                file_size = save_path.stat().st_size
                self.logger.info(f"whl package download successful, file size: {self._format_size(file_size)}")
                
                # Validate WHL file integrity
                if not self._validate_whl_integrity(save_path):
                    self.logger.error("❌ WHL file integrity verification failed, file may be corrupted or incomplete")
                    # Delete corrupted file
                    try:
                        save_path.unlink()
                        self.logger.info("Corrupted WHL file deleted")
                    except Exception as e:
                        self.logger.error(f"Failed to delete corrupted file: {e}")
                    return None
                
                self.logger.info("✅ WHL file integrity verification passed")
                
                # After download complete, force rename based on WHL package internal info
                original_filename = save_path.name
                self.logger.info(f"Download completed, original filename: {original_filename}")
                self.logger.info("Executing forced rename (strict standard)...")
                
                # Read package info from WHL file for renaming
                package_info = self._extract_package_info_from_whl(save_path)
                if package_info and package_info.get('name') and package_info.get('version'):
                    package_name = package_info['name']
                    package_version = package_info['version']
                    
                    # Generate new filename
                    new_filename = f"{package_name}-{package_version}-py3-none-any.whl"
                    
                    self.logger.info(f"Extracted package info from WHL file: {package_name} {package_version}")
                    self.logger.info(f"Executing forced rename: {original_filename} -> {new_filename}")
                    
                    if new_filename != original_filename:
                        new_whl_path = self.temp_dir / new_filename
                        try:
                            # Ensure target file doesn't exist
                            if new_whl_path.exists():
                                new_whl_path.unlink()
                            
                            save_path.rename(new_whl_path)
                            self.logger.info(f"✅ File rename successful: {original_filename} -> {new_whl_path.name}")
                            save_path = new_whl_path
                        except Exception as rename_error:
                            self.logger.error(f"❌ File rename failed: {rename_error}")
                            # Record detailed error info for debugging
                            self.logger.debug(f"Rename failed details: source file={save_path}, target file={new_whl_path}")
                else:
                    self.logger.warning("⚠️ Unable to extract package info from WHL file, using original filename")
                
                # Record final filename
                final_filename = save_path.name
                self.logger.info(f"Final filename: {final_filename}")
                
                return save_path
            else:
                self.logger.error("whl package download failed")
                return None
                
        except Exception as e:
            self.logger.error(f"Error occurred during whl package download: {e}")
            return None
    
    def _install_whl_package(self, whl_path: Path, python_path: str) -> Tuple[bool, str]:
        """
        Install whl package using pip
        
        Args:
            whl_path: whl file path
            python_path: Python executable file path
            
        Returns:
            Tuple[bool, str]: (whether installation was successful, error message)
        """
        try:
            # Build pip install command (optimize network configuration)
            pip_command = [
                python_path, "-m", "pip", "install", 
                "--upgrade", "--force-reinstall",
                "--timeout", "120",  # Connection timeout 120 seconds
                "--retries", "5",     # Increase retry times
                "--default-timeout", "1200",  # Overall operation timeout 1200 seconds (20 minutes)
                "--no-cache-dir",     # Disable cache to avoid cache issues
                "--disable-pip-version-check",  # Disable version check to reduce network requests
                "-i", "https://intelpypi.intel.com/root/pypi/+simple/",
                str(whl_path)
            ]
            
            self.logger.info(f"Starting whl package installation: {whl_path.name}")
            self.logger.debug(f"Installation command: {' '.join(pip_command)}")
            
            # Execute pip install
            result = run_with_logging(
                pip_command,
                command_name="pip_install_whl",
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Record installation result
            if result.stdout:
                self.logger.info(f"pip installation output: {result.stdout.strip()}")
            
            # Check if there are warnings in stderr
            if result.stderr:
                stderr_content = result.stderr.strip()
                self.logger.warning(f"pip installation warning: {stderr_content}")
                
                # Check if contains "Ignoring invalid distribution" warning
                if "Ignoring invalid distribution" in stderr_content:
                    self.logger.warning("Invalid package distribution directory detected, attempting cleanup and reinstallation")
                    
                    # Try to cleanup invalid distributions
                    cleanup_success = self._cleanup_invalid_distributions(python_path)
                    if cleanup_success:
                        self.logger.info("Invalid distribution cleanup completed, retrying installation")
                        # Re-execute installation
                        result = run_with_logging(
                            pip_command,
                            command_name="pip_install_retry",
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                            encoding='utf-8',
                            errors='ignore'
                        )
            
            if result.returncode == 0:
                self.logger.info("whl package installation successful")
                return True, ""
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                self.logger.error(f"whl package installation failed: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error occurred during pip installation: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def _cleanup_invalid_distributions(self, python_path: str) -> bool:
        """
        Clean up invalid package distribution directories
        
        Args:
            python_path: Python executable file path
            
        Returns:
            bool: Whether cleanup was successful
        """
        try:
            # Use pip check command to check invalid distributions
            check_command = [python_path, "-m", "pip", "check"]
            result = run_with_logging(check_command, command_name="pip_check", capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.warning(f"Package environment issue detected: {result.stdout.strip()}")
                
                # Try to use pip cache purge to clean cache
                cache_command = [python_path, "-m", "pip", "cache", "purge"]
                cache_result = run_with_logging(cache_command, command_name="pip_cache_purge", capture_output=True, text=True)
                
                if cache_result.returncode == 0:
                    self.logger.info("pip cache cleanup successful")
                else:
                    self.logger.warning(f"pip cache cleanup failed: {cache_result.stderr.strip()}")
                
                # Clean up temporary package directories starting with ~
                temp_cleanup_success = self._cleanup_temp_package_dirs(python_path)
                if temp_cleanup_success:
                    self.logger.info("Temporary package directory cleanup completed")
                else:
                    self.logger.warning("Temporary package directory cleanup failed or not needed")
                
                return True
            
            self.logger.info("Package environment check normal")
            return True
            
        except Exception as e:
            self.logger.error(f"Error occurred while cleaning invalid distributions: {e}")
            return False

    def _cleanup_temp_package_dirs(self, python_path: str) -> bool:
        """
        Clean up temporary package directories starting with ~ and ending with .dist-info or .egg-info
        
        Args:
            python_path: Python executable file path
            
        Returns:
            bool: Whether cleanup was successful (True means successful or no cleanup needed, False means failed)
        """
        try:
            import os
            import shutil
            from pathlib import Path
            
            # Get Python installation directory
            python_dir = Path(python_path).parent
            site_packages_dir = python_dir / "lib" / "site-packages"
            
            if not site_packages_dir.exists():
                self.logger.warning(f"site-packages directory does not exist: {site_packages_dir}")
                return True  # No cleanup needed
            
            # Find directories starting with ~ and ending with .dist-info or .egg-info
            temp_dirs_to_remove = []
            for item in site_packages_dir.iterdir():
                if item.is_dir():
                    item_name = item.name
                    # Check if condition is met: starts with ~ and ends with .dist-info or .egg-info
                    if (item_name.startswith('~') and 
                        (item_name.endswith('.dist-info') or item_name.endswith('.egg-info'))):
                        temp_dirs_to_remove.append(item)
                        self.logger.info(f"Temporary package directory found: {item_name}")
            
            if not temp_dirs_to_remove:
                self.logger.info("No temporary package directories found for cleanup")
                return True  # No cleanup needed
            
            # Create backup directory
            backup_dir = site_packages_dir / "backup_temp_packages"
            backup_dir.mkdir(exist_ok=True)
            
            # Backup and delete temporary directories
            removed_count = 0
            for temp_dir in temp_dirs_to_remove:
                try:
                    # Move to backup directory
                    backup_path = backup_dir / temp_dir.name
                    shutil.move(str(temp_dir), str(backup_path))
                    self.logger.info(f"Temporary directory backed up and deleted: {temp_dir.name}")
                    removed_count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to delete temporary directory {temp_dir.name}: {e}")
            
            self.logger.info(f"Temporary package directory cleanup completed: cleaned {removed_count} directories")
            
            # If backup directory is empty, delete backup directory
            if not any(backup_dir.iterdir()):
                backup_dir.rmdir()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error occurred while cleaning temporary package directories: {e}")
            return False

    def _create_backup(self, package_name: str, python_path: str) -> bool:
        """
        Create current package backup
        
        Args:
            package_name: Package name
            python_path: Python executable file path
            
        Returns:
            bool: Whether backup was successful
        """
        if not self.backup_enabled:
            return True
            
        try:
            
            # Get current installed version
            freeze_command = [python_path, "-m", "pip", "freeze", "--all"]
            result = run_with_logging(freeze_command, command_name="pip_freeze", capture_output=True, text=True)
            
            if result.returncode == 0:
                # Find package info
                for line in result.stdout.strip().split('\n'):
                    if line.startswith(package_name + '=='):
                        version = line.split('==')[1]
                        backup_info = f"{package_name}=={version}"
                        
                        # Save backup info
                        backup_file = self.temp_dir / f"{package_name}_backup.txt"
                        with open(backup_file, 'w', encoding='utf-8') as f:
                            f.write(backup_info)
                        
                        self.logger.info(f"Backup created: {backup_info}")
                        return True
            
            self.logger.warning(f"Package {package_name} current installation info not found")
            return False
            
        except Exception as e:
            self.logger.error(f"Backup creation failed: {e}")
            return False
    
    def _rollback_package(self, package_name: str) -> bool:
        """
        Roll back package to backup version
        
        Args:
            package_name: Package name
            
        Returns:
            bool: Whether rollback was successful
        """
        try:
            python_path = self._get_python_executable()
            if not python_path:
                return False
            
            # Read backup info
            backup_file = self.temp_dir / f"{package_name}_backup.txt"
            if not backup_file.exists():
                self.logger.warning("Backup file not found, cannot rollback")
                return False
            
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_info = f.read().strip()
            
            # Execute rollback installation
            rollback_command = [python_path, "-m", "pip", "install", backup_info]
            result = run_with_logging(rollback_command, command_name="pip_rollback", capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Rollback successful: {backup_info}")
                return True
            else:
                self.logger.error(f"Rollback failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error occurred during rollback: {e}")
            return False
    
    def _is_valid_whl_filename(self, filename: str) -> bool:
        """
        Validate if WHL filename conforms to PEP 427 specification
        
        Args:
            filename: Filename
            
        Returns:
            bool: Whether it's valid
        """
        if not filename.endswith('.whl'):
            return False
        
        # Remove .whl suffix
        base_name = filename[:-4]
        parts = base_name.split('-')
        
        # Valid WHL filename should have at least 3 parts: package name-version-py tag-platform tag
        if len(parts) < 3:
            return False
        
        # Check if there's a version number (version numbers usually start with a digit)
        has_version = any(part and part[0].isdigit() for part in parts)
        
        # Check if there's a Python tag (contains 'py' or 'cp')
        has_python_tag = any('py' in part.lower() or 'cp' in part.lower() for part in parts)
        
        # Check if package name is a generic name (like 'package'), if so consider invalid
        package_name = parts[0]
        generic_package_names = ['package', 'test', 'temp', 'unknown', 'whl']
        has_generic_name = package_name.lower() in generic_package_names
        
        # Additional validation: check if package name conforms to PEP 427 specification
        is_valid_package_name = self._is_valid_package_name(package_name)
        
        return has_version and has_python_tag and not has_generic_name and is_valid_package_name
    
    def _extract_package_info_from_whl(self, whl_path: Path) -> Optional[dict]:
        """
        Extract package info (name, version, etc.) from WHL file
        
        Args:
            whl_path: WHL file path
            
        Returns:
            Optional[dict]: Dictionary containing package info, returns None if failed
        """
        try:
            import zipfile
            import tempfile
            import os
            
            # WHL files are essentially zip archives
            with zipfile.ZipFile(whl_path, 'r') as whl_zip:
                # Find metadata files - relax condition, look for all .dist-info and .egg-info directories
                metadata_files = []
                for filename in whl_zip.namelist():
                    # Match any .dist-info/METADATA or .egg-info/PKG-INFO file
                    if (filename.endswith('/METADATA') and '.dist-info' in filename) or \
                       (filename.endswith('/PKG-INFO') and '.egg-info' in filename):
                        metadata_files.append(filename)
                
                if not metadata_files:
                    self.logger.warning(f"Metadata file not found in WHL file: {whl_path}")
                    return None
                
                # Use first found metadata file
                metadata_file = metadata_files[0]
                self.logger.info(f"Metadata file found: {metadata_file}")
                
                # Extract metadata file content
                with whl_zip.open(metadata_file) as f:
                    metadata_content = f.read().decode('utf-8', errors='ignore')
                
                # Parse metadata
                package_info = {}
                for line in metadata_content.split('\n'):
                    line = line.strip()
                    if line.startswith('Name:'):
                        package_info['name'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        package_info['version'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Summary:'):
                        package_info['summary'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Author:'):
                        package_info['author'] = line.split(':', 1)[1].strip()
                    
                    # If package name and version are found, can exit early
                    if 'name' in package_info and 'version' in package_info:
                        break
                
                if 'name' in package_info and 'version' in package_info:
                    self.logger.info(f"Successfully extracted package info from WHL file: {package_info['name']} {package_info['version']}")
                    return package_info
                else:
                    self.logger.warning(f"Package info extraction from WHL file incomplete: {package_info}")
                    return None
                    
        except Exception as e:
            self.logger.warning(f"Error occurred during package info extraction from WHL file: {e}")
            return None
    
    def _extract_package_name(self, whl_filename: str) -> str:
        """
        Extract package name from whl filename
        
        Args:
            whl_filename: whl filename
            
        Returns:
            str: Package name
        """
        # whl filename format: package_name-version-py3-none-any.whl
        # Extract package name (part before first hyphen)
        base_name = whl_filename.replace('.whl', '')
        parts = base_name.split('-')
        
        # Package name is usually the part before the first hyphen
        # But some packages may have multiple hyphens, need to find where version number starts
        for i, part in enumerate(parts):
            # Version numbers usually start with a digit
            if part and part[0].isdigit():
                package_name = '-'.join(parts[:i])
                
                # Validate if package name conforms to PEP 427 specification
                # Package name can only contain letters, digits, underscores, dots and hyphens
                # Cannot start or end with hyphen, cannot have consecutive hyphens
                if self._is_valid_package_name(package_name):
                    return package_name.replace('_', '-')
                else:
                    # If package name doesn't conform to specification, try cleaning
                    cleaned_name = self._clean_package_name(package_name)
                    self.logger.warning(f"Package name '{package_name}' does not conform to specification, using cleaned name: '{cleaned_name}'")
                    return cleaned_name.replace('_', '-')
        
        # If version number not found, return first part
        return parts[0] if parts else "unknown"

    def _force_rename_whl_file(self, whl_path: Path, original_filename: str) -> Optional[Path]:
        """
        Force rename WHL file, generate PEP 427 compliant filename based on package info
        
        Args:
            whl_path: WHL file path
            original_filename: Original filename
            
        Returns:
            Optional[Path]: Renamed file path, returns None if failed
        """
        try:
            # Extract package info from WHL file
            package_info = self._extract_package_info_from_whl(whl_path)
            
            if package_info and 'name' in package_info and 'version' in package_info:
                # Use real package name and version extracted from WHL file
                package_name = package_info['name']
                version = package_info['version']
                
                # Validate if package name conforms to PEP 427 specification
                if not self._is_valid_package_name(package_name):
                    self.logger.warning(f"Package name '{package_name}' does not conform to PEP 427 specification, cleaning")
                    package_name = self._clean_package_name(package_name)
                    self.logger.info(f"Cleaned package name: {package_name}")
                
                # Generate PEP 427 compliant filename
                new_filename = self._generate_whl_filename(package_name, version)
                new_path = whl_path.parent / new_filename
                
                self.logger.info(f"Executing forced rename: {original_filename} -> {new_filename}")
                
                # Rename file
                whl_path.rename(new_path)
                self.logger.info(f"✅ File rename successful: {new_filename}")
                
                return new_path
            else:
                # If unable to extract package info, use alternative scheme
                self.logger.warning(f"Unable to extract package info from WHL file, using alternative rename scheme")
                
                # Extract package name from original filename
                package_name = self._extract_package_name(original_filename)
                
                # Validate and clean package name
                if not self._is_valid_package_name(package_name):
                    package_name = self._clean_package_name(package_name)
                    self.logger.info(f"Package name cleaned by alternative scheme: {package_name}")
                
                # Generate PEP 427 compliant alternative filename
                new_filename = self._generate_whl_filename(package_name, "0.0.1")
                new_path = whl_path.parent / new_filename
                
                self.logger.info(f"Executing alternative rename: {original_filename} -> {new_filename}")
                
                # Rename file
                whl_path.rename(new_path)
                self.logger.info(f"✅ File rename successful: {new_filename}")
                
                return new_path
                
        except Exception as e:
            self.logger.error(f"Forced WHL file rename failed: {e}")
            return None
    
    def _is_valid_package_name(self, package_name: str) -> bool:
        """
        Validate if package name conforms to PEP 427 specification
        
        Args:
            package_name: Package name
            
        Returns:
            bool: Whether it's valid
        """
        # Package name cannot be empty
        if not package_name:
            return False
        
        # Cannot start or end with hyphen
        if package_name.startswith('-') or package_name.endswith('-'):
            return False
        
        # Cannot have consecutive hyphens
        if '--' in package_name:
            return False
        
        # Can only contain letters, digits, underscores, dots and hyphens
        if not re.match(r'^[a-zA-Z0-9._-]+$', package_name):
            return False
        
        return True
    
    def _clean_package_name(self, package_name: str) -> str:
        """
        Clean up package name to conform to PEP 427 specification
        
        Args:
            package_name: Package name
            
        Returns:
            str: Cleaned package name
        """
        # Remove leading and trailing hyphens
        cleaned = package_name.strip('-') 
        
        # Replace consecutive hyphens with single hyphen
        cleaned = re.sub(r'-+', '-', cleaned)
        
        # Only keep letters, digits, underscores, dots and hyphens
        cleaned = re.sub(r'[^a-zA-Z0-9._-]', '', cleaned)
        
        # Again ensure not starting or ending with hyphen
        cleaned = cleaned.strip('-')
        
        # If cleaned name is empty, return default name
        if not cleaned:
            return "unknown_package"
        
        return cleaned
    
    def _generate_whl_filename(self, package_name: str, package_version: str) -> str:
        """
        Generate PEP 427 compliant WHL filename
        
        Args:
            package_name: Package name
            package_version: Package version
            
        Returns:
            str: Generated WHL filename
        """
        # [Generate standard] WHL file [name format]: {package}-{version}-py3-none-any.whl
        # [Note]: pip [regular expression] [^\-]+ [requires package name cannot contain hyphens]
        # [Convert hyphens in package name to underscores] to [ensure] pip [can parse correctly]
        clean_name = package_name.replace('-', '_')
        return f"{clean_name}-{package_version}-py3-none-any.whl"
    
    def _validate_whl_integrity(self, whl_path: Path) -> bool:
        """
        Validate WHL file integrity
        
        Args:
            whl_path: WHL file path
            
        Returns:
            bool: Whether file is complete and valid
        """
        try:
            if not whl_path.exists():
                self.logger.error(f"WHL file does not exist: {whl_path}")
                return False
            
            # Check file [size]
            file_size = whl_path.stat().st_size
            if file_size < 100:  # WHL files are usually at least a few hundred bytes
                self.logger.error(f"WHL file size abnormal: {file_size} bytes")
                return False
            
            # Check [if it's a] valid [ZIP file]
            import zipfile
            try:
                with zipfile.ZipFile(whl_path, 'r') as whl_zip:
                    # Check [if ZIP file is] corrupted
                    if whl_zip.testzip() is not None:
                        self.logger.error("WHL file ZIP structure corrupted")
                        return False
                    
                    # Check [if it contains necessary] file [structure]
                    file_list = whl_zip.namelist()
                    
                    # Check [if it contains] .dist-info directory
                    dist_info_files = [f for f in file_list if '.dist-info' in f]
                    if not dist_info_files:
                        self.logger.error("WHL file missing .dist-info directory")
                        return False
                    
                    # [Extract] .dist-info directory path
                    dist_info_dirs = set()
                    for file_path in dist_info_files:
                        # [Extract] directory [part], [example]: executionkit-0.0.2.dist-info/
                        dir_path = file_path.split('/')[0] + '/' if '/' in file_path else file_path.split('\\')[0] + '\\'
                        dist_info_dirs.add(dir_path)
                    
                    # Check [if it contains] METADATA file
                    metadata_found = False
                    for dist_dir in dist_info_dirs:
                        metadata_file = dist_dir + "METADATA"
                        if metadata_file in file_list:
                            # Validate METADATA file [content]
                            with whl_zip.open(metadata_file) as f:
                                metadata_content = f.read().decode('utf-8', errors='ignore')
                                if 'Name:' not in metadata_content or 'Version:' not in metadata_content:
                                    self.logger.error("METADATA file content incomplete")
                                    return False
                            metadata_found = True
                            break
                    
                    if not metadata_found:
                        self.logger.error("WHL file missing METADATA file")
                        return False
                    
                    # Check [if it contains package] directory
                    package_files = [f for f in file_list if '.dist-info' not in f and '__pycache__' not in f and not f.endswith('/')]
                    if not package_files:
                        self.logger.error("WHL file missing package files")
                        return False
                    
                    self.logger.debug(f"WHL file structure verification passed: {len(file_list)} files")
                    return True
                    
            except zipfile.BadZipFile:
                self.logger.error("WHL file is not a valid ZIP format")
                return False
            except Exception as e:
                self.logger.error(f"Error occurred while validating WHL file integrity: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"WHL file integrity validation failed: {e}")
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """[Format file size display]"""
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _cleanup_temp_files(self):
        """[Cleanup temporary files]"""
        try:
            if self.temp_dir.exists():
                # [Keep] backup files, delete [other temporary] files
                for item in self.temp_dir.iterdir():
                    if not item.name.endswith('_backup.txt'):
                        if item.is_file():
                            item.unlink()
                        else:
                            shutil.rmtree(item)
                
                self.logger.debug("Temporary file cleanup completed")
        except Exception as e:
            self.logger.warning(f"Error occurred while cleaning temporary files: {e}")
    
    async def update_from_whl(self, whl_url: str, python_path: str) -> bool:
        """
        Perform overlay update based on whl package URL
        
        Args:
            whl_url: whl package download URL
            python_path: Python executable path
            
        Returns:
            bool: Whether update was successful
        """
        self.logger.info(f"Starting WHL package update process, URL: {whl_url}")
        
        # Download whl [package]
        whl_path = await self._download_whl_file(whl_url)
        if not whl_path:
            self.logger.error("WHL package download failed")
            return False
        
        # [Extract package name]
        package_name = self._extract_package_name(whl_path.name)
        self.logger.info(f"Detected package name: {package_name}")
        
        # Create backup
        backup_created = self._create_backup(package_name, python_path)
        if not backup_created:
            self.logger.warning("Backup creation failed, continuing with update")
        
        # Execute [installation]
        success = False
        error_msg = ""
        
        for attempt in range(self.max_retries):
            self.logger.info(f"Attempting installation (attempt {attempt + 1}/{self.max_retries} times)")
            
            success, error_msg = self._install_whl_package(whl_path, python_path)
            
            if success:
                break
            else:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    self.logger.info(f"Installation failed, waiting for {wait_time} seconds before retry...")
                    time.sleep(wait_time)
        
        # [Process installation result]
        if success:
            self.logger.info("WHL package update successful")
            # [Cleanup temporary] files ([keep] backups)
            self._cleanup_temp_files()
            return True
        else:
            self.logger.error(f"WHL package update failed: {error_msg}")
            
            # Try [rollback]
            if backup_created:
                self.logger.info("Starting rollback to backup version")
                rollback_success = self._rollback_package(package_name)
                if rollback_success:
                    self.logger.info("Rollback successful")
                else:
                    self.logger.error("Rollback failed")
            
            return False


def update_from_whl_sync(whl_url: str, python_path: str) -> dict:
    """
    Convenience function: Perform overlay update based on whl package URL (synchronous interface)
    
    Args:
        whl_url: whl package download URL
        python_path: Python executable path
        
    Returns:
        dict: Update result, containing success and error fields
    """
    updater = WhlUpdater()
    
    # Synchronous version [of] update [logic]
    logger = get_logger()
    logger.info(f"Starting synchronous WHL package update process, URL: {whl_url}")
    
    try:
        # [Extract] file [name] from URL
        whl_filename = whl_url.split('/')[-1]
        if not whl_filename.endswith('.whl'):
            logger.error(f"URL format error, not a valid whl file: {whl_url}")
            return {"success": False, "error": f"URL format error, not a valid whl file: {whl_url}"}
        
        whl_path = updater.temp_dir / whl_filename
        
        # [Use] synchronous version [of] downloader
        from .file_downloader import download_file_sync
        download_success = download_file_sync(whl_url, str(whl_path))
        
        if not download_success:
            logger.error("WHL package download failed")
            return {"success": False, "error": "WHL package download failed"}
        
        logger.info(f"WHL package download completed: {whl_path}")
        
        # After download complete, [perform] WHL file [integrity] validation [and rename] check
        original_filename = whl_path.name
        logger.info(f"Download completed，Original filename: {original_filename}")
        
        # Validate WHL file [integrity]
        if not updater._validate_whl_integrity(whl_path):
            logger.error("❌ WHL file integrity verification failed，File may be corrupted or incomplete")
            # Delete [corrupted] file
            try:
                whl_path.unlink()
                logger.info("Corrupted WHL file deleted")
            except Exception as e:
                logger.error(f"Failed to delete corrupted file: {e}")
            return {"success": False, "error": "WHL file integrity verification failed, file may be corrupted or incomplete"}
        
        logger.info("✅ WHL file integrity verification passed")
        
        # [Force rename based on] WHL [package internal] info [strictly enforcing standards]
        logger.info(f"Original filename: {original_filename}")
        
        # [Read package] info from WHL file [for] renaming
        package_info = updater._extract_package_info_from_whl(whl_path)
        if package_info and package_info.get('name') and package_info.get('version'):
            package_name = package_info['name']
            package_version = package_info['version']
            
            # Validate [if package name conforms to] PEP 427 [specification]
            if not updater._is_valid_package_name(package_name):
                logger.warning(f"Package name '{package_name}' does not conform to PEP 427 specification, cleaning")
                package_name = updater._clean_package_name(package_name)
                logger.info(f"Cleaned package name: {package_name}")
            
            # [Generate PEP 427 compliant] file [name]
            new_filename = updater._generate_whl_filename(package_name, package_version)
            new_whl_path = updater.temp_dir / new_filename
            
            logger.info(f"Extracted package info from WHL file: {package_name} {package_version}")
            logger.info(f"Executing forced rename: {original_filename} -> {new_filename}")
            
            # Check [if target] file [already exists]
            if new_whl_path.exists():
                logger.warning(f"Target file already exists: {new_whl_path}")
                # Delete [existing] file
                try:
                    new_whl_path.unlink()
                    logger.info("Existing file deleted")
                except Exception as e:
                    logger.error(f"Failed to delete existing file: {e}")
            
            # Execute [rename]
            try:
                whl_path.rename(new_whl_path)
                logger.info(f"✅ File rename successful: {new_filename}")
                whl_path = new_whl_path
            except Exception as rename_error:
                logger.error(f"❌ File rename failed: {rename_error}")
                # [Record detailed] error info [for] debugging
                logger.debug(f"Rename failed details: source file={whl_path}, target file={new_whl_path}")
        else:
            logger.warning("⚠️ Unable to extract package info from WHL file, using original filename")
        
        # [Record final] file [name]
        final_filename = whl_path.name
        logger.info(f"Final filename: {final_filename}")
        
        # [Extract package name]
        package_name = updater._extract_package_name(whl_path.name)
        logger.info(f"Detected package name: {package_name}")
        
        # Create backup
        backup_created = updater._create_backup(package_name, python_path)
        if not backup_created:
            logger.warning("Backup creation failed, continuing with update")
        
        # Execute [installation]
        success = False
        error_msg = ""
        
        for attempt in range(updater.max_retries):
            logger.info(f"Attempting installation (attempt {attempt + 1}/{updater.max_retries} times)")
            
            success, error_msg = updater._install_whl_package(whl_path, python_path)
            
            if success:
                break
            else:
                if attempt < updater.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Installation failed, waiting for {wait_time} seconds before retry...")
                    import time
                    time.sleep(wait_time)
        
        # [Process installation result]
        if success:
            logger.info("WHL package update successful")
            # [Cleanup temporary] files ([keep] backups)
            # updater._cleanup_temp_files()
            return {"success": True, "error": ""}
        else:
            logger.error(f"WHL package update failed: {error_msg}")
            
            # Try [rollback]
            if backup_created:
                logger.info("Starting rollback to backup version")
                rollback_success = updater._rollback_package(package_name)
                if rollback_success:
                    logger.info("Rollback successful")
                else:
                    logger.error("Rollback failed")
            
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        logger.error(f"Error occurred during synchronous WHL package update: {e}")
        return {"success": False, "error": str(e)}


def update_from_whl(whl_url: str, python_path: str) -> bool:
    """
    Convenience function: Perform overlay update based on whl package URL (asynchronous interface, compatible with old versions)
    
    Args:
        whl_url: whl package download URL
        python_path: Python executable path
        
    Returns:
        bool: Whether update was successful
    """
    import asyncio
    updater = WhlUpdater()
    return asyncio.run(updater.update_from_whl(whl_url, python_path))

