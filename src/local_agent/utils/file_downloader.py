#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File downloader utility
Supports synchronous and asynchronous downloads, includes resumable downloads, authentication token handling, progress callbacks, etc.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable

import requests

# Check if running as standalone script
if __name__ == "__main__":
    # When running as standalone script, add project path to sys.path
    import os
    import sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Import project global components
try:
    from ..logger import get_logger
    from local_agent.core.global_cache import cache
    from local_agent.core.constants import AUTHORIZATION_CACHE_KEY
except ImportError:
    # When running as standalone script, use simple log implementation
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
    
    # Simple cache implementation
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
    """File download utility class, supports resumable downloads"""
    
    def __init__(self, 
                 chunk_size: int = 8192,
                 max_retries: int = 3,
                 timeout: int = 300):
        """
        Initialize downloader
        
        Args:
            chunk_size: Download chunk size (bytes)
            max_retries: Maximum retry attempts
            timeout: Download timeout (seconds)
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
        Download file (supports resumable download)
        
        Args:
            url: Download URL
            save_path: Save path
            progress_callback: Progress callback function (optional)
            
        Returns:
            bool: Whether download succeeded
        """
        # Check if aiohttp is installed, fallback to synchronous download if not
        try:
            import aiohttp
        except ImportError:
            self.logger.warning("aiohttp not installed, falling back to synchronous download")
            return self.download_sync(url, save_path, progress_callback)
        
        path = Path(save_path)

        self.logger.info(f"Starting file download: {url} -> {save_path}")
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Resumable download: get already downloaded file size
        downloaded_size = 0
        if path.exists():
            downloaded_size = path.stat().st_size
            self.logger.info(f"Found existing downloaded file, resuming download: {downloaded_size} bytes")
        
        # Setup request headers (support resumable download and authentication)
        headers = {}
        
        # Add authentication token
        auth_token = cache.get(AUTHORIZATION_CACHE_KEY)
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        # Resumable download
        if downloaded_size > 0:
            headers['Range'] = f'bytes={downloaded_size}-'
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Starting download: {url}")
                self.logger.info(f"Saving to: {save_path}")
                self.logger.info(f"Request headers: {headers}")
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.get(url, headers=headers) as response:
                        
                        if response.status not in (200, 206):
                            raise Exception(f"HTTP {response.status}: {response.reason}")
                        
                        # Get file total size
                        content_length = response.headers.get('content-length')
                        total_size = int(content_length) + downloaded_size if content_length else None
                        
                        self.logger.info(f"File size: {self._format_size(total_size) if total_size else 'Unknown'}")
                        
                        # Open file (append mode supports resumable download)
                        mode = 'ab' if downloaded_size > 0 else 'wb'
                        with open(path, mode) as f:
                            start_time = time.time()
                            downloaded = downloaded_size
                            last_log_time = start_time
                            
                            async for chunk in response.content.iter_chunked(self.chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Progress display (output every 10 seconds to reduce log density)
                                current_time = time.time()
                                if current_time - last_log_time >= 10:
                                    speed = self._calculate_speed(downloaded, start_time)
                                    progress = self._format_progress(downloaded, total_size)
                                    self.logger.info(f"Download progress: {progress} - Speed: {speed}")
                                    last_log_time = current_time
                                
                                # Call progress callback
                                if progress_callback and total_size:
                                    progress_callback(downloaded, total_size)
                        
                        # DownloadComplete
                        final_size = path.stat().st_size
                        total_time = time.time() - start_time
                        speed = self._format_speed(final_size, total_time)
                        
                        self.logger.info(f"Download completed: {self._format_size(final_size)} - Time: {total_time:.1f}s - Average speed: {speed}")
                        return True
                        
            except Exception as e:
                self.logger.error(f"Download failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.info(f"Waiting for {wait_time}s before retrying...")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Download failed, reached maximum retry attempts")
                    return False
        
        return False
    
    def _format_size(self, size_bytes: Optional[int]) -> str:
        """Format file size"""
        if size_bytes is None:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def _calculate_speed(self, downloaded: int, start_time: float) -> str:
        """Calculate download speed"""
        elapsed = time.time() - start_time
        if elapsed > 0:
            speed = downloaded / elapsed
            return self._format_speed(speed, 1)
        return "0 B/s"
    
    def _format_speed(self, bytes_per_sec: float, time_sec: float = 1) -> str:
        """Format speed"""
        # Prevent division by zero error
        if time_sec <= 0:
            return "0 B/s"
        
        speed = bytes_per_sec / time_sec
        for unit in ['B/s', 'KB/s', 'MB/s']:
            if speed < 1024.0:
                return f"{speed:.1f} {unit}"
            speed /= 1024.0
        return f"{speed:.1f} GB/s"
    
    def _format_progress(self, downloaded: int, total_size: Optional[int]) -> str:
        """Format progress display"""
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
        Synchronously download file (supports resumable download)
        
        Args:
            url: Download URL
            save_path: Save path
            progress_callback: Progress callback function (optional)
            
        Returns:
            bool: Whether download succeeded
        """
        path = Path(save_path)

        self.logger.info(f"Starting synchronous file download: {url} -> {save_path}")
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Resumable download: get already downloaded file size
        downloaded_size = 0
        if path.exists():
            downloaded_size = path.stat().st_size
            self.logger.info(f"Found existing downloaded file, resuming download: {downloaded_size} bytes")
        
        # Setup request headers (support resumable download and authentication)
        headers = {}
        
        # Add authentication token
        auth_token = cache.get(AUTHORIZATION_CACHE_KEY)
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        
        # Resumable download
        if downloaded_size > 0:
            headers['Range'] = f'bytes={downloaded_size}-'
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Starting synchronous download: {url}")
                self.logger.info(f"Saving to: {save_path}")
                self.logger.info(f"Request headers: {headers}")
                
                # Use requests for synchronous download
                response = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
                
                if response.status_code not in (200, 206):
                    raise Exception(f"HTTP {response.status_code}: {response.reason}")
                
                # Get file total size
                content_length = response.headers.get('content-length')
                total_size = int(content_length) + downloaded_size if content_length else None
                
                self.logger.info(f"File size: {self._format_size(total_size) if total_size else 'Unknown'}")
                
                # Open file (append mode supports resumable download)
                mode = 'ab' if downloaded_size > 0 else 'wb'
                with open(path, mode) as f:
                    start_time = time.time()
                    downloaded = downloaded_size
                    last_log_time = start_time
                    
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:  # Filter out keep-alive chunks
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Progress display (output every 10 seconds to reduce log density)
                            current_time = time.time()
                            if current_time - last_log_time >= 10:
                                speed = self._calculate_speed(downloaded, start_time)
                                progress = self._format_progress(downloaded, total_size)
                                self.logger.info(f"Download progress: {progress} - Speed: {speed}")
                                last_log_time = current_time
                            
                            # Call progress callback
                            if progress_callback and total_size:
                                progress_callback(downloaded, total_size)
                
                # DownloadComplete
                final_size = path.stat().st_size
                total_time = time.time() - start_time
                speed = self._format_speed(final_size, total_time)
                
                self.logger.info(f"Synchronous download completed: {self._format_size(final_size)} - Time: {total_time:.1f}s - Average speed: {speed}")
                return True
                
            except Exception as e:
                self.logger.error(f"Synchronous download failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.info(f"Waiting for {wait_time}s before retrying...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Synchronous download failed, reached maximum retry attempts")
                    return False
        
        return False


async def download_file_async(url: str, save_path: str) -> bool:
    """
    Convenience function: Asynchronously download file
    
    Args:
        url: Download URL
        save_path: Save path
        
    Returns:
        bool: Whether download succeeded
    """
    downloader = FileDownloader()
    return await downloader.download(url, save_path)


def download_file_sync(url: str, save_path: str) -> bool:
    """
    Convenience function: Synchronously download file
    
    Args:
        url: Download URL
        save_path: Save path
        
    Returns:
        bool: Whether download succeeded
    """
    downloader = FileDownloader()
    return downloader.download_sync(url, save_path)


def main():
    """Command line entry"""
    logger = get_logger()
    
    # Support synchronous/asynchronous mode selection
    sync_mode = False
    args = sys.argv[1:]
    
    if len(args) >= 1 and args[0] == "--sync":
        sync_mode = True
        args = args[1:]
    
    if len(args) != 2:
        logger.error("Usage: python file_downloader.py [--sync] <download_url> <save_path>")
        logger.error("Example: python file_downloader.py https://example.com/file.zip ./downloads/file.zip")
        logger.error("Example (sync mode): python file_downloader.py --sync https://example.com/file.zip ./downloads/file.zip")
        sys.exit(1)
    
    url = args[0]
    save_path = args[1]
    
    mode_text = "synchronous" if sync_mode else "asynchronous"
    logger.info(f"File download tool started ({mode_text} mode)")
    logger.info(f"Download URL: {url}")
    logger.info(f"Save path: {save_path}")
    logger.info("-" * 50)
    
    # Run download
    if sync_mode:
        success = download_file_sync(url, save_path)
    else:
        success = asyncio.run(download_file_async(url, save_path))
    
    if success:
        logger.info("Download successful!")
        sys.exit(0)
    else:
        logger.error("Download failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()