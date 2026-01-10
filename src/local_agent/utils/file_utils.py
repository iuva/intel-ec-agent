#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File operation utility class
Provides common operations like file extraction, copying, etc.
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Tuple
from local_agent.logger import get_logger


class FileUtils:
    """File operation utility class"""
    
    @staticmethod
    def extract_file_from_scripts(file_name: str, overwrite: bool = False) -> Tuple[bool, str]:
        """
        Extract file from scripts directory to current directory
        
        Args:
            file_name: File name
            overwrite: Whether to overwrite if file exists
            
        Returns:
            (success status, message)
        """
        try:
            # Get current exe path
            exe_path = sys.executable
            working_dir = Path(exe_path).parent
            
            # Check if file already exists in current directory
            target_path = working_dir / file_name
            if target_path.exists() and not overwrite:
                return True, f"{file_name} already exists, skipping extraction"
            
            # Check if running in packaged environment
            # PyInstaller will extract data files to temporary directory
            if hasattr(sys, '_MEIPASS'):
                # In packaged environment, copy from temporary directory
                temp_dir = Path(sys._MEIPASS)
                source_file = temp_dir / 'scripts' / file_name
                
                if source_file.exists():
                    # Copy file to current directory
                    shutil.copy2(source_file, target_path)
                    logger = get_logger(__name__)
                    logger.info(f"[INFO] File extracted to: {target_path}")
                    return True, f"{file_name} extraction successful"
                else:
                    return False, f"{file_name} not found in packaged environment"
            else:
                # Non-packaged environment, try to copy from project directory
                project_root = Path(__file__).parent.parent.parent
                source_file = project_root / 'scripts' / file_name
                
                if source_file.exists():
                    shutil.copy2(source_file, target_path)
                    logger = get_logger(__name__)
                    logger.info(f"[INFO] File copied to: {target_path}")
                    return True, f"{file_name} copy successful"
                else:
                    return False, f"{file_name} not found in project directory"
                    
        except Exception as e:
            return False, f"{file_name} extraction failed: {str(e)}"
    
    @staticmethod
    def extract_multiple_files(file_names: list, overwrite: bool = False) -> Tuple[bool, list]:
        """
        Batch extract multiple files
        
        Args:
            file_names: List of file names
            overwrite: Whether to overwrite if files exist
            
        Returns:
            (Overall success status, detailed results list)
        """
        results = []
        all_success = True
        
        for file_name in file_names:
            success, message = FileUtils.extract_file_from_scripts(file_name, overwrite)
            results.append({
                'file_name': file_name,
                'success': success,
                'message': message
            })
            if not success:
                all_success = False
        
        return all_success, results