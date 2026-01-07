#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络请求封装
单例模式，支持自动URL拼接和token管理

使用示例：
1. 基本使用：
   from src.local_agent.core.http_client import http_client
   result = http_client.get("/api/users", isToken=True)

2. 带数据请求：
   data = {"name": "张三", "age": 25}
   result = http_client.post("/api/users", data=data, isToken=True)

3. 完整URL请求：
   result = http_client.get("https://api.example.com/data")
"""

import requests
import json
import threading
from typing import Optional, Dict, Any, Union
from urllib.parse import urljoin

from ..core.global_cache import cache
from ..config import get_config
from ..logger import get_logger
from ..core.constants import AUTHORIZATION_CACHE_KEY


class HttpClient:
    """
    网络请求客户端
    单例模式，支持自动URL拼接和token管理
    """
    
    def __init__(self):
        """初始化HTTP客户端"""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # 获取基础URL配置
        self.base_url = self.config.get('http_base_url', '')
        self.timeout = self.config.get('http_timeout', 30)
        
        # 创建会话对象
        self.session = requests.Session()
        
        # 设置默认请求头
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': f'LocalAgent/1.0.0'
        })
        
        self.logger.info(f"HTTP客户端初始化完成，基础URL: {self.base_url}")
    
    def _build_file_url(self, url: str) -> str:
        """构建完整下载URL
        
        Args:
            url: 下载URL，可能是完整URL或相对路径
            
        Returns:
            str: 完整下载URL
        """
        # 处理空URL
        if not url:
            return None

        # 如果已经是完整URL，直接返回
        if url.startswith(('http://', 'https://')):
            return url
        
        # 使用HTTP客户端的URL构建逻辑
        # 如果URL是文件名，构建完整路径
        if '/' not in url and '.' in url:
            # 假设是文件名，构建完整API路径
            return self._build_url(f"/host/file/{url}")
        else:
            # 使用HTTP客户端的URL构建
            return self._build_url(url)


    def _build_url(self, url: str) -> str:
        """
        构建完整URL
        
        Args:
            url: 请求URL，如果以http://或https://开头则直接使用，否则拼接基础URL
            
        Returns:
            str: 完整URL
        """
        if url.startswith(('http://', 'https://')):
            # 已经是完整URL，直接返回
            return url
        
        if self.base_url:
            # 拼接基础URL，确保正确处理路径分隔符
            base = self.base_url.rstrip('/')
            path = url.lstrip('/')
            
            # 检查路径是否已经包含基础URL中的API路径，避免重复
            base_api_path = '/api/v1'
            if base.endswith(base_api_path) and path.startswith(base_api_path.lstrip('/')):
                # 如果路径已经包含API路径，则移除重复部分
                path = path[len(base_api_path.lstrip('/')):].lstrip('/')
            
            return f"{base}/{path}"
        else:
            # 没有配置基础URL，返回原URL（可能是不完整的路径）
            self.logger.warning(f"未配置基础URL，使用相对路径: {url}")
            return url
    
    def _get_token(self) -> Optional[str]:
        """
        从全局缓存获取token
        
        Returns:
            Optional[str]: token值，如果不存在则返回None
        """
        token = cache.get(AUTHORIZATION_CACHE_KEY)
        if token:
            self.logger.debug("从缓存获取到token")
            return token
        else:
            self.logger.warning(f"缓存中未找到{AUTHORIZATION_CACHE_KEY} token")
            return None
    
    def _build_headers(self, is_token: bool = True, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        构建请求头
        
        Args:
            is_token: 是否携带token
            headers: 自定义请求头
            
        Returns:
            Dict[str, str]: 请求头字典
        """
        # 复制默认请求头
        request_headers = self.session.headers.copy()
        
        # 添加token
        if is_token:
            token = self._get_token()
            if token:
                request_headers['Authorization'] = f'Bearer {token}'
        
        # 添加自定义请求头
        if headers:
            request_headers.update(headers)
        
        return request_headers
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        处理响应
        
        Args:
            response: 响应对象
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        try:
            # 尝试解析JSON响应
            if response.headers.get('Content-Type', '').startswith('application/json'):
                result = response.json()
            else:
                result = {
                    'text': response.text,
                    'content': response.content
                }
        except (json.JSONDecodeError, ValueError):
            # 非JSON响应
            result = {
                'text': response.text,
                'content': response.content
            }
        
        # 构建标准响应格式
        return {
            'status_code': response.status_code,
            'success': 200 <= response.status_code < 300,
            'data': result,
            'headers': dict(response.headers),
            'url': response.url
        }
    
    def _handle_auth_refresh(self) -> bool:
        """
        处理鉴权刷新逻辑
        
        Returns:
            bool: 是否成功刷新token
        """
        self.logger.info("检测到token无效或过期，开始刷新token...")
        
        # 延迟导入以避免循环导入问题
        from ..core.auth import refresh_token, auth_token
        
        # 先尝试刷新token
        refresh_result = refresh_token()
        if refresh_result:
            self.logger.info("token刷新成功")
            return True
        
        # 如果刷新失败，尝试重新获取token
        self.logger.warning("token刷新失败，尝试重新获取token...")
        auth_result = auth_token()
        if auth_result:
            self.logger.info("token重新获取成功")
            return True
        
        self.logger.error("token刷新和重新获取均失败，鉴权无效")
        return False
    
    def _request(self, method: str, url: str, data: Optional[Any] = None, 
                 is_token: bool = True, headers: Optional[Dict[str, str]] = None, 
                 **kwargs) -> Dict[str, Any]:
        """
        执行HTTP请求，支持自动鉴权刷新
        
        Args:
            method: HTTP方法（GET, POST, PUT, DELETE等）
            url: 请求URL
            data: 请求数据
            is_token: 是否携带token
            headers: 自定义请求头
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        # 检查是否需要携带token但token不存在
        if is_token and not cache.get(AUTHORIZATION_CACHE_KEY):
            self.logger.warning("请求需要token但缓存中不存在，尝试获取token...")
            if not self._handle_auth_refresh():
                return {
                    'status_code': 401,
                    'success': False,
                    'data': {
                        'error': '鉴权失败，无法获取有效token',
                        'code': 401
                    },
                    'url': url
                }
        
        # 构建完整URL
        full_url = self._build_url(url)
        
        # 构建请求头
        request_headers = self._build_headers(is_token, headers)
        
        # 准备请求参数
        request_kwargs = {
            'timeout': kwargs.pop('timeout', self.timeout),
            'headers': request_headers
        }
        
        # 处理请求数据
        if data is not None:
            if request_headers.get('Content-Type') == 'application/json':
                request_kwargs['json'] = data
            else:
                request_kwargs['data'] = data
        
        # 添加其他参数（排除内部使用的参数）
        # 只传递requests库支持的参数
        supported_kwargs = {}
        for key, value in kwargs.items():
            # 排除内部参数，只传递requests支持的参数
            if key not in ['is_token']:
                supported_kwargs[key] = value
        
        request_kwargs.update(supported_kwargs)
        
        self.logger.debug(f"发送{method}请求: {full_url}")
        
        try:
            # 发送请求
            response = self.session.request(method, full_url, **request_kwargs)

            # 响应信息
            self.logger.debug(f"请求地址：{full_url}\n请求体：{data}\n请求头：{request_headers}\n响应信息：{response.text}")

            # 处理响应
            result = self._handle_response(response)
            
            # 检查是否为401错误，如果是则尝试刷新token并重试
            if result['status_code'] == 401 and is_token:
                self.logger.warning("请求返回401错误，token可能已过期，尝试刷新token...")
                
                if self._handle_auth_refresh():
                    # 重新构建请求头（使用新的token）
                    request_headers = self._build_headers(is_token, headers)
                    request_kwargs['headers'] = request_headers
                    
                    self.logger.info("token刷新成功，重新发送请求...")
                    
                    # 重新发送请求
                    response = self.session.request(method, full_url, **request_kwargs)
                    result = self._handle_response(response)
                    
                    if result['success']:
                        self.logger.info("重新请求成功")
                    else:
                        self.logger.error("重新请求失败")
                else:
                    self.logger.error("token刷新失败，无法重新请求")
            
            if result['success']:
                self.logger.debug(f"{method}请求成功: {full_url}")
            else:
                self.logger.warning(f"{method}请求失败: {full_url}, 状态码: {response.status_code}")
            
            return result
            
        except requests.exceptions.Timeout:
            self.logger.error(f"{method}请求超时: {full_url}")
            
            # 无限重试逻辑：超时后等待2分钟再次请求
            import time
            retry_delay = 120  # 2分钟
            
            while True:
                self.logger.warning(f"请求超时，等待{retry_delay}秒后重试: {full_url}")
                time.sleep(retry_delay)
                
                try:
                    self.logger.info(f"开始重试请求: {full_url}")
                    
                    response = self.session.request(method, full_url, **request_kwargs)
                    
                    # 处理响应
                    result = self._handle_response(response, method, full_url)
                    
                    # 如果请求成功，返回结果
                    if result['success']:
                        self.logger.info(f"重试请求成功: {full_url}")
                        return result
                    
                    # 如果请求失败但不是超时，返回错误
                    if result.get('status_code') != 408:
                        self.logger.warning(f"重试请求失败（非超时错误）: {full_url}")
                        return result
                    
                    # 如果是超时错误，继续重试循环
                    self.logger.error(f"重试请求仍然超时: {full_url}")
                    
                except requests.exceptions.Timeout:
                    # 重试时仍然超时，继续循环
                    self.logger.error(f"重试请求超时: {full_url}")
                    continue
                    
                except Exception as e:
                    # 其他异常，返回错误
                    self.logger.error(f"重试请求异常: {full_url}, 错误: {e}")
                    return {
                        'status_code': 500,
                        'success': False,
                        'data': {'error': f'重试请求异常: {str(e)}'},
                        'url': full_url
                    }
            
        except requests.exceptions.ConnectionError:
            self.logger.error(f"{method}连接错误: {full_url}")
            return {
                'status_code': 503,
                'success': False,
                'data': {'error': '连接错误'},
                'url': full_url
            }
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"{method}请求异常: {full_url}, 错误: {e}")
            return {
                'status_code': 500,
                'success': False,
                'data': {'error': f'请求异常: {str(e)}'},
                'url': full_url
            }
    
    def get(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        GET请求
        
        Args:
            url: 请求URL
            data: 查询参数（将转换为URL参数）
            is_token: 是否携带token
            headers: 自定义请求头
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        # 对于GET请求，data作为查询参数
        if data is not None:
            kwargs['params'] = data
        
        return self._request('GET', url, is_token=is_token, headers=headers, **kwargs)
    
    def post(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
             headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        POST请求
        
        Args:
            url: 请求URL
            data: 请求体数据
            is_token: 是否携带token
            headers: 自定义请求头
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        return self._request('POST', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def put(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        PUT请求
        
        Args:
            url: 请求URL
            data: 请求体数据
            is_token: 是否携带token
            headers: 自定义请求头
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        return self._request('PUT', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def delete(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
               headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        DELETE请求
        
        Args:
            url: 请求URL
            data: 请求体数据
            is_token: 是否携带token
            headers: 自定义请求头
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        return self._request('DELETE', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def set_base_url(self, base_url: str) -> None:
        """
        设置基础URL
        
        Args:
            base_url: 基础URL
        """
        self.base_url = base_url.rstrip('/') + '/'  # 确保以斜杠结尾
        self.logger.info(f"设置基础URL: {self.base_url}")
    
    def set_timeout(self, timeout: int) -> None:
        """
        设置请求超时时间
        
        Args:
            timeout: 超时时间（秒）
        """
        self.timeout = timeout
        self.logger.info(f"设置请求超时: {timeout}秒")
    
    def set_default_headers(self, headers: Dict[str, str]) -> None:
        """
        设置默认请求头
        
        Args:
            headers: 请求头字典
        """
        self.session.headers.update(headers)
        self.logger.info(f"更新默认请求头")
    
    def close(self) -> None:
        """关闭HTTP会话"""
        self.session.close()
        self.logger.info("HTTP会话已关闭")


# 单例模式实现
_http_client_instance = None
_http_client_lock = threading.RLock()


def get_http_client() -> HttpClient:
    """
    获取HTTP客户端实例（单例模式）
    
    Returns:
        HttpClient: HTTP客户端实例
    """
    global _http_client_instance
    with _http_client_lock:
        if _http_client_instance is None:
            _http_client_instance = HttpClient()
        return _http_client_instance


# 提供便捷的全局实例
http_client = get_http_client()


# 便捷函数，可以直接导入使用
def http_get(url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """便捷函数：GET请求"""
    return http_client.get(url, data, is_token, headers, **kwargs)


def http_post(url: str, data: Optional[Any] = None, is_token: bool = True, 
             headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """便捷函数：POST请求"""
    return http_client.post(url, data, is_token, headers, **kwargs)


def http_put(url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """便捷函数：PUT请求"""
    return http_client.put(url, data, is_token, headers, **kwargs)


def http_delete(url: str, data: Optional[Any] = None, is_token: bool = False, 
               headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """便捷函数：DELETE请求"""
    return http_client.delete(url, data, is_token, headers, **kwargs)


def set_http_base_url(base_url: str) -> None:
    """便捷函数：设置基础URL"""
    http_client.set_base_url(base_url)


def set_http_timeout(timeout: int) -> None:
    """便捷函数：设置超时时间"""
    http_client.set_timeout(timeout)


def close_http_client() -> None:
    """便捷函数：关闭HTTP客户端"""
    http_client.close()