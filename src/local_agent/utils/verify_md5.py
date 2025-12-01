#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MD5完整性校验脚本
用于验证EXE文件的完整性，确保文件未被篡改
"""

import hashlib

def calculate_md5(file_path):
    """
    计算文件的MD5哈希值
    
    Args:
        file_path: 文件路径
        
    Returns:
        str: 文件的MD5哈希值（32位十六进制字符串）
    """
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        # 分块读取文件，避免大文件内存溢出
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    
    return md5_hash.hexdigest()

