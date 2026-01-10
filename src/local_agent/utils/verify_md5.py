#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MD5 integrity verification script
Used to verify EXE file integrity, ensuring files have not been tampered with
"""

import hashlib

def calculate_md5(file_path):
    """
    Calculate MD5 hash value of file
    
    Args:
        file_path: File path
        
    Returns:
        str: File's MD5 hash value (32-bit hexadecimal string)
    """
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        # Read file in chunks to avoid memory overflow for large files
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    
    return md5_hash.hexdigest()

