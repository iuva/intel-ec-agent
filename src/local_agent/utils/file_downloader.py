#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件下载器工具
支持同步和异步下载，包含断点续传、认证token处理、进度回调等功能
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable

import requests

# 检查是否作为独立脚本运行
if __name__ == "__main__":
    # 作为独立脚本运行时，添加项目路径到sys.path
    import os
    import sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# 导入项目全局组件
try:
    from ..logger import get_logger
    from local_agent.core.global_cache import cache
    from local_agent.core.constants import AUTHORIZATION_CACHE_KEY
except ImportError:
    # 作为独立脚本运行时，使用简单的日志实现
    import logging
    def get_logger(name=None):
        logger = logging.getLogger(name or "file_downloader")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    # 简单的缓存实现
    class SimpleCache:
        def __init__(self):
            self._data = {}
        
        def get(self, key, default=None):
            return self._data.get(key, default)
        
        def set(self, key, value):
            self._data[key] = value
    
    cache = SimpleCache()
    AUTHORIZATION_CACHE_KEY = "authorization_token"


class FileDownloader:
    """文件下载工具类，支持断点续传"""
    
    def __init__(self, 
                 chunk_size: int = 8192,
                 max_retries: int = 3,
                 timeout: int = 300):
        """
        初始化下载器
        
        Args:
            chunk_size: 下载块大小（字节）
            max_retries: 最大重试次数
            timeout: 下载超时时间（秒）
        """
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.logger = get_logger()
    
    async def download(self, 
                     url: str, 
                     save_path: str,
                     progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        下载文件（支持断点续传）
        
        Args:
            url: 下载链接
            save_path: 保存位置
            progress_callback: 进度回调函数（可选）
            
        Returns:
            bool: 下载是否成功
        """
        # 检查是否安装了aiohttp，如果没有则回退到同步下载
        try:
            import aiohttp
        except ImportError:
            self.logger.warning("aiohttp未安装，回退到同步下载")
            return self.download_sync(url, save_path, progress_callback)
        
        path = Path(save_path)

        self.logger.info(f"开始下载文件: {url} -> {save_path}")
        
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 断点续传：获取已下载的文件大小
        downloaded_size = 0
        if path.exists():
            downloaded_size = path.stat().st_size
            self.logger.info(f"发现已下载文件，继续下载: {downloaded_size} bytes")
        
        # 设置请求头（支持断点续传和认证）
        headers = {}
        
        # 添加认证token
        auth_token = cache.get(AUTHORIZATION_CACHE_KEY)
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        # 断点续传
        if downloaded_size > 0:
            headers['Range'] = f'bytes={downloaded_size}-'
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"开始下载: {url}")
                self.logger.info(f"保存到: {save_path}")
                self.logger.info(f"请求头信息: {headers}")
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(url, headers=headers) as response:
                        
                        if response.status not in (200, 206):
                            raise Exception(f"HTTP {response.status}: {response.reason}")
                        
                        # 获取文件总大小
                        content_length = response.headers.get('content-length')
                        total_size = int(content_length) + downloaded_size if content_length else None
                        
                        self.logger.info(f"文件大小: {self._format_size(total_size) if total_size else '未知'}")
                        
                        # 打开文件（追加模式支持断点续传）
                        mode = 'ab' if downloaded_size > 0 else 'wb'
                        with open(path, mode) as f:
                            start_time = time.time()
                            downloaded = downloaded_size
                            last_log_time = start_time
                            
                            async for chunk in response.content.iter_chunked(self.chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # 进度显示（每10秒输出一次，减少日志密度）
                                current_time = time.time()
                                if current_time - last_log_time >= 10:
                                    speed = self._calculate_speed(downloaded, start_time)
                                    progress = self._format_progress(downloaded, total_size)
                                    self.logger.info(f"下载进度: {progress} - 速度: {speed}")
                                    last_log_time = current_time
                                
                                # 调用进度回调
                                if progress_callback and total_size:
                                    progress_callback(downloaded, total_size)
                        
                        # 下载完成
                        final_size = path.stat().st_size
                        total_time = time.time() - start_time
                        speed = self._format_speed(final_size, total_time)
                        
                        self.logger.info(f"下载完成: {self._format_size(final_size)} - 耗时: {total_time:.1f}s - 平均速度: {speed}")
                        return True
                        
            except Exception as e:
                self.logger.error(f"下载失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.info(f"等待 {wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"下载失败，达到最大重试次数")
                    return False
        
        return False
    
    def _format_size(self, size_bytes: Optional[int]) -> str:
        """格式化文件大小"""
        if size_bytes is None:
            return "未知"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _calculate_speed(self, downloaded: int, start_time: float) -> str:
        """计算下载速度"""
        elapsed = time.time() - start_time
        if elapsed > 0:
            speed = downloaded / elapsed
            return self._format_speed(speed, 1)
        return "0 B/s"
    
    def _format_speed(self, bytes_per_sec: float, time_sec: float = 1) -> str:
        """格式化速度"""
        # 防止除零错误
        if time_sec <= 0:
            return "0 B/s"
        
        speed = bytes_per_sec / time_sec
        for unit in ['B/s', 'KB/s', 'MB/s']:
            if speed < 1024.0:
                return f"{speed:.1f} {unit}"
            speed /= 1024.0
        return f"{speed:.1f} GB/s"
    
    def _format_progress(self, downloaded: int, total_size: Optional[int]) -> str:
        """格式化进度显示"""
        if total_size and total_size > 0:
            percent = (downloaded / total_size) * 100
            return f"{percent:.1f}% ({self._format_size(downloaded)}/{self._format_size(total_size)})"
        else:
            return f"{self._format_size(downloaded)}"
    
    def download_sync(self, 
                     url: str, 
                     save_path: str,
                     progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        同步下载文件（支持断点续传）
        
        Args:
            url: 下载链接
            save_path: 保存位置
            progress_callback: 进度回调函数（可选）
            
        Returns:
            bool: 下载是否成功
        """
        path = Path(save_path)

        self.logger.info(f"开始同步下载文件: {url} -> {save_path}")
        
        # 确保目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 断点续传：获取已下载的文件大小
        downloaded_size = 0
        if path.exists():
            downloaded_size = path.stat().st_size
            self.logger.info(f"发现已下载文件，继续下载: {downloaded_size} bytes")
        
        # 设置请求头（支持断点续传和认证）
        headers = {}
        
        # 添加认证token
        auth_token = cache.get(AUTHORIZATION_CACHE_KEY)
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        # 断点续传
        if downloaded_size > 0:
            headers['Range'] = f'bytes={downloaded_size}-'
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"开始同步下载: {url}")
                self.logger.info(f"保存到: {save_path}")
                self.logger.info(f"请求头信息: {headers}")
                
                # 使用requests进行同步下载
                response = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
                
                if response.status_code not in (200, 206):
                    raise Exception(f"HTTP {response.status_code}: {response.reason}")
                
                # 获取文件总大小
                content_length = response.headers.get('content-length')
                total_size = int(content_length) + downloaded_size if content_length else None
                
                self.logger.info(f"文件大小: {self._format_size(total_size) if total_size else '未知'}")
                
                # 打开文件（追加模式支持断点续传）
                mode = 'ab' if downloaded_size > 0 else 'wb'
                with open(path, mode) as f:
                    start_time = time.time()
                    downloaded = downloaded_size
                    last_log_time = start_time
                    
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:  # 过滤掉keep-alive的chunk
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 进度显示（每10秒输出一次，减少日志密度）
                            current_time = time.time()
                            if current_time - last_log_time >= 10:
                                speed = self._calculate_speed(downloaded, start_time)
                                progress = self._format_progress(downloaded, total_size)
                                self.logger.info(f"下载进度: {progress} - 速度: {speed}")
                                last_log_time = current_time
                            
                            # 调用进度回调
                            if progress_callback and total_size:
                                progress_callback(downloaded, total_size)
                
                # 下载完成
                final_size = path.stat().st_size
                total_time = time.time() - start_time
                speed = self._format_speed(final_size, total_time)
                
                self.logger.info(f"同步下载完成: {self._format_size(final_size)} - 耗时: {total_time:.1f}s - 平均速度: {speed}")
                return True
                
            except Exception as e:
                self.logger.error(f"同步下载失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.info(f"等待 {wait_time}s 后重试...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"同步下载失败，达到最大重试次数")
                    return False
        
        return False


async def download_file_async(url: str, save_path: str) -> bool:
    """
    便捷函数：异步下载文件
    
    Args:
        url: 下载链接
        save_path: 保存位置
        
    Returns:
        bool: 下载是否成功
    """
    downloader = FileDownloader()
    return await downloader.download(url, save_path)


def download_file_sync(url: str, save_path: str) -> bool:
    """
    便捷函数：同步下载文件
    
    Args:
        url: 下载链接
        save_path: 保存位置
        
    Returns:
        bool: 下载是否成功
    """
    downloader = FileDownloader()
    return downloader.download_sync(url, save_path)


def main():
    """命令行入口"""
    logger = get_logger()
    
    # 支持同步/异步模式选择
    sync_mode = False
    args = sys.argv[1:]
    
    if len(args) >= 1 and args[0] == "--sync":
        sync_mode = True
        args = args[1:]
    
    if len(args) != 2:
        logger.error("用法: python file_downloader.py [--sync] <下载链接> <保存路径>")
        logger.error("示例: python file_downloader.py https://example.com/file.zip ./downloads/file.zip")
        logger.error("示例(同步模式): python file_downloader.py --sync https://example.com/file.zip ./downloads/file.zip")
        sys.exit(1)
    
    url = args[0]
    save_path = args[1]
    
    mode_text = "同步" if sync_mode else "异步"
    logger.info(f"文件下载工具启动 ({mode_text}模式)")
    logger.info(f"下载链接: {url}")
    logger.info(f"保存位置: {save_path}")
    logger.info("-" * 50)
    
    # 运行下载
    if sync_mode:
        success = download_file_sync(url, save_path)
    else:
        success = asyncio.run(download_file_async(url, save_path))
    
    if success:
        logger.info("下载成功！")
        sys.exit(0)
    else:
        logger.error("下载失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()