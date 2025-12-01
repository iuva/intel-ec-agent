#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件操作工具类
提供文件解压、复制等常用操作
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Tuple
from local_agent.logger import get_logger


class FileUtils:
    """文件操作工具类"""
    
    @staticmethod
    def extract_file_from_scripts(file_name: str, overwrite: bool = False) -> Tuple[bool, str]:
        """
        从scripts目录解压文件到当前目录
        
        Args:
            file_name: 文件名
            overwrite: 如果文件存在是否覆盖
            
        Returns:
            (成功状态, 消息)
        """
        try:
            # 获取当前exe路径
            exe_path = sys.executable
            working_dir = Path(exe_path).parent
            
            # 检查当前目录是否已有文件
            target_path = working_dir / file_name
            if target_path.exists() and not overwrite:
                return True, f"{file_name}已存在，跳过解压"
            
            # 检查是否在打包后的环境中运行
            # PyInstaller会将数据文件解压到临时目录
            if hasattr(sys, '_MEIPASS'):
                # 在打包环境中，从临时目录复制
                temp_dir = Path(sys._MEIPASS)
                source_file = temp_dir / 'scripts' / file_name
                
                if source_file.exists():
                    # 复制文件到当前目录
                    shutil.copy2(source_file, target_path)
                    logger = get_logger(__name__)
                    logger.info(f"[INFO] 已解压文件到: {target_path}")
                    return True, f"{file_name}解压成功"
                else:
                    return False, f"打包环境中未找到{file_name}"
            else:
                # 非打包环境，尝试从项目目录复制
                project_root = Path(__file__).parent.parent.parent
                source_file = project_root / 'scripts' / file_name
                
                if source_file.exists():
                    shutil.copy2(source_file, target_path)
                    logger = get_logger(__name__)
                    logger.info(f"[INFO] 已复制文件到: {target_path}")
                    return True, f"{file_name}复制成功"
                else:
                    return False, f"项目目录中未找到{file_name}"
                    
        except Exception as e:
            return False, f"{file_name}解压失败: {str(e)}"
    
    @staticmethod
    def extract_multiple_files(file_names: list, overwrite: bool = False) -> Tuple[bool, list]:
        """
        批量解压多个文件
        
        Args:
            file_names: 文件名列表
            overwrite: 如果文件存在是否覆盖
            
        Returns:
            (整体成功状态, 详细结果列表)
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