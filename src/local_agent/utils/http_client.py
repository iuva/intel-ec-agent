#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network request encapsulation
Singleton pattern, supports automatic URL concatenation and token management

Usage examples:
1. Basic usage:
   from src.local_agent.core.http_client import http_client
   result = http_client.get("/api/users", isToken=True)

2. Request with data:
   data = {"name": "Zhang San", "age": 25}
   result = http_client.post("/api/users", data=data, isToken=True)

3. Full URL request:
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
    Network request client
    Singleton pattern, supports automatic URL concatenation and token management
    """
    
    def __init__(self):
        """Initialize HTTP client"""
        self.config = get_config()
        self.logger = get_logger(__name__)
        
        # Get basic URL configuration
        self.base_url = self.config.get('http_base_url', '')
        self.timeout = self.config.get('http_timeout', 30)
        
        # Create session object
        self.session = requests.Session()
        
        # Set up default request headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': f'LocalAgent/1.0.0'
        })
        
        self.logger.info(f"HTTP client initialized, base URL: {self.base_url}")
    
    def _build_file_url(self, url: str) -> str:
        """Build complete download URL
        
        Args:
            url: Download URL, which may be a complete URL or relative path
            
        Returns:
            str: Complete download URL
        """
        # Handle empty URL
        if not url:
            return None

        # If already a complete URL, return directly
        if url.startswith(('http://', 'https://')):
            return url
        
        # Use HTTPClient's URL construction logic
        # If URL is a filename, build complete path
        if '/' not in url and '.' in url:
            # Assume it's a filename, build complete API path
            return self._build_url(f"/host/file/{url}")
        else:
            # Use HTTPClient's URL construction
            return self._build_url(url)


    def _build_url(self, url: str) -> str:
        """
        Build complete URL
        
        Args:
            url: Request URL, if it starts with http:// or https://, use it directly, otherwise concatenate with base URL
            
        Returns:
            str: Complete URL
        """
        if url.startswith(('http://', 'https://')):
            # Already a complete URL, return directly
            return url
        
        if self.base_url:
            # Concatenate basic URL, ensure correct path separator handling
            base = self.base_url.rstrip('/')
            path = url.lstrip('/')
            
            # Check if path already contains API path from basic URL to avoid duplication
            base_api_path = '/api/v1'
            if base.endswith(base_api_path) and path.startswith(base_api_path.lstrip('/')):
                # If path already contains API path, remove duplicate part
                path = path[len(base_api_path.lstrip('/')):].lstrip('/')
            
            return f"{base}/{path}"
        else:
            # No basic URL configured, return original URL (may be incomplete path)
            self.logger.warning(f"Base URL not configured, using relative path: {url}")
            return url
    
    def _get_token(self) -> Optional[str]:
        """
        Get token from global cache
        
        Returns:
            Optional[str]: Token value, returns None if not found
        """
        token = cache.get(AUTHORIZATION_CACHE_KEY)
        if token:
            self.logger.debug("Token obtained from cache")
            return token
        else:
            self.logger.warning(f"Token {AUTHORIZATION_CACHE_KEY} not found in cache")
            return None
    
    def _build_headers(self, is_token: bool = True, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Build request headers
        
        Args:
            is_token: Whether to include token
            headers: Custom request headers
            
        Returns:
            Dict[str, str]: Request headers dictionary
        """
        # Copy default request headers
        request_headers = self.session.headers.copy()
        
        # Add token
        if is_token:
            token = self._get_token()
            if token:
                request_headers['Authorization'] = f'Bearer {token}'
        
        # Add custom request headers
        if headers:
            request_headers.update(headers)
        
        return request_headers
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle response
        
        Args:
            response: Response object
            
        Returns:
            Dict[str, Any]: Response data
        """
        try:
            # Try to parse JSON response
            if response.headers.get('Content-Type', '').startswith('application/json'):
                result = response.json()
            else:
                result = {
                    'text': response.text,
                    'content': response.content
                }
        except (json.JSONDecodeError, ValueError):
            # Non-JSON response
            result = {
                'text': response.text,
                'content': response.content
            }
        
        # Build standard response format
        return {
            'status_code': response.status_code,
            'success': 200 <= response.status_code < 300,
            'data': result,
            'headers': dict(response.headers),
            'url': response.url
        }
    
    def _handle_auth_refresh(self) -> bool:
        """
        Handle authentication refresh logic
        
        Returns:
            bool: Whether token refresh was successful
        """
        self.logger.info("Detected token invalid or expired, starting token refresh...")
        
        # Delay import to avoid circular import issues
        from ..core.auth import refresh_token, auth_token
        
        # First try to refresh token
        refresh_result = refresh_token()
        if refresh_result:
            self.logger.info("Token refresh successful")
            return True
        
        # If refresh fails, try to re-obtain token
        self.logger.warning("Token refresh failed, attempting to re-obtain token...")
        auth_result = auth_token()
        if auth_result:
            self.logger.info("Token re-obtained successfully")
            return True
        
        self.logger.error("Token refresh and re-obtain both failed, authentication invalid")
        return False
    
    def _request(self, method: str, url: str, data: Optional[Any] = None, 
                 is_token: bool = True, headers: Optional[Dict[str, str]] = None, 
                 **kwargs) -> Dict[str, Any]:
        """
        Execute HTTP request with automatic authentication refresh
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: Request URL
            data: Request data
            is_token: Whether to include token
            headers: Custom request headers
            **kwargs: Other request parameters
            
        Returns:
            Dict[str, Any]: Response data
        """
        # Check if token is required but not present
        if is_token and not cache.get(AUTHORIZATION_CACHE_KEY):
            self.logger.warning("Token required but not found in cache, attempting to obtain token...")
            if not self._handle_auth_refresh():
                return {
                    'status_code': 401,
                    'success': False,
                    'data': {
                        'error': 'Authentication failed, unable to obtain valid token',
                        'code': 401
                    },
                    'url': url
                }
        
        # Build complete URL
        full_url = self._build_url(url)
        
        # Build request headers
        request_headers = self._build_headers(is_token, headers)
        
        # Prepare request parameters
        request_kwargs = {
            'timeout': kwargs.pop('timeout', self.timeout),
            'headers': request_headers
        }
        
        # Handle request data
        if data is not None:
            if request_headers.get('Content-Type') == 'application/json':
                request_kwargs['json'] = data
            else:
                request_kwargs['data'] = data
        
        # Add other parameters (exclude internally used parameters)
        # Only pass parameters supported by requests library
        supported_kwargs = {}
        for key, value in kwargs.items():
            # Exclude internal parameters, only pass requests-supported parameters
            if key not in ['is_token']:
                supported_kwargs[key] = value
        
        request_kwargs.update(supported_kwargs)
        
        self.logger.debug(f"Sending {method} request: {full_url}")
        
        try:
            # Send request
            response = self.session.request(method, full_url, **request_kwargs)

            # Response info
            self.logger.debug(f"Request URL: {full_url}\nRequest body: {data}\nRequest headers: {request_headers}\nResponse info: {response.text}")

            # Handle response
            result = self._handle_response(response)
            
            # Check if it's a 401 error, if so try to refresh token and retry
            if result['status_code'] == 401 and is_token:
                self.logger.warning("Request returned 401 error, token may be expired, attempting to refresh token...")
                
                if self._handle_auth_refresh():
                    # Rebuild request headers (using new token)
                    request_headers = self._build_headers(is_token, headers)
                    request_kwargs['headers'] = request_headers
                    
                    self.logger.info("Token refresh successful, resending request...")
                    
                    # Resend request
                    response = self.session.request(method, full_url, **request_kwargs)
                    result = self._handle_response(response)
                    
                    if result['success']:
                        self.logger.info("Retry request successful")
                    else:
                        self.logger.error("Retry request failed")
                else:
                    self.logger.error("Token refresh failed, unable to retry request")
            
            if result['success']:
                self.logger.debug(f"{method} request successful: {full_url}")
            else:
                self.logger.warning(f"{method} request failed: {full_url}, status code: {response.status_code}")
            
            return result
            
        except requests.exceptions.Timeout:
            self.logger.error(f"{method} request timeout: {full_url}")
            
            # Infinite retry logic: Wait 2 minutes after timeout and request again
            import time
            retry_delay = 120  # 2 minutes
            
            while True:
                self.logger.warning(f"Request timeout, waiting for {retry_delay} seconds before retry: {full_url}")
                time.sleep(retry_delay)
                
                try:
                    self.logger.info(f"Starting retry request: {full_url}")
                    
                    response = self.session.request(method, full_url, **request_kwargs)
                    
                    # Handle response
                    result = self._handle_response(response)
                    
                    # If request succeeds, return result
                    if result['success']:
                        self.logger.info(f"Retry request successful: {full_url}")
                        return result
                    
                    # If request fails but not timeout, return error
                    if result.get('status_code') != 408:
                        self.logger.warning(f"Retry request failed (non-timeout error): {full_url}")
                        return result
                    
                    # If it's timeout error, continue retry loop
                    self.logger.error(f"Retry request still timeout: {full_url}")
                    
                except requests.exceptions.Timeout:
                    # Still timeout during retry, continue loop
                    self.logger.error(f"Retry request timeout: {full_url}")
                    continue
                    
                except Exception as e:
                    # Other exceptions, return error
                    self.logger.error(f"Retry request exception: {full_url}, error: {e}")
                    return {
                        'status_code': 500,
                        'success': False,
                        'data': {'error': f'Retry request exception: {str(e)}'},
                        'url': full_url
                    }
            
        except requests.exceptions.ConnectionError:
            self.logger.error(f"{method} connection error: {full_url}")
            return {
                'status_code': 503,
                'success': False,
                'data': {'error': 'Connection error'},
                'url': full_url
            }
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"{method} request exception: {full_url}, error: {e}")
            return {
                'status_code': 500,
                'success': False,
                'data': {'error': f'Request exception: {str(e)}'},
                'url': full_url
            }
    
    def get(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        GET request
        
        Args:
            url: Request URL
            data: Query parameters (will be converted to URL parameters)
            is_token: Whether to include token
            headers: Custom request headers
            **kwargs: Other request parameters
            
        Returns:
            Dict[str, Any]: Response data
        """
        # For GET request, data as query parameters
        if data is not None:
            kwargs['params'] = data
        
        return self._request('GET', url, is_token=is_token, headers=headers, **kwargs)
    
    def post(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
             headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        POST request
        
        Args:
            url: Request URL
            data: Request body data
            is_token: Whether to include token
            headers: Custom request headers
            **kwargs: Other request parameters
            
        Returns:
            Dict[str, Any]: Response data
        """
        return self._request('POST', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def put(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        PUT request
        
        Args:
            url: Request URL
            data: Request body data
            is_token: Whether to include token
            headers: Custom request headers
            **kwargs: Other request parameters
            
        Returns:
            Dict[str, Any]: Response data
        """
        return self._request('PUT', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def delete(self, url: str, data: Optional[Any] = None, is_token: bool = True, 
               headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
        """
        DELETE request
        
        Args:
            url: Request URL
            data: Request body data
            is_token: Whether to include token
            headers: Custom request headers
            **kwargs: Other request parameters
            
        Returns:
            Dict[str, Any]: Response data
        """
        return self._request('DELETE', url, data=data, is_token=is_token, headers=headers, **kwargs)
    
    def set_base_url(self, base_url: str) -> None:
        """
        Set base URL
        
        Args:
            base_url: Base URL
        """
        self.base_url = base_url.rstrip('/') + '/'  # Ensure ends with slash
        self.logger.info(f"Set base URL: {self.base_url}")
    
    def set_timeout(self, timeout: int) -> None:
        """
        Set request timeout
        
        Args:
            timeout: Timeout in seconds
        """
        self.timeout = timeout
        self.logger.info(f"Set request timeout: {timeout} seconds")
    
    def set_default_headers(self, headers: Dict[str, str]) -> None:
        """
        Set default request headers
        
        Args:
            headers: Headers dictionary
        """
        self.session.headers.update(headers)
        self.logger.info(f"Updated default headers")
    
    def close(self) -> None:
        """Close HTTP session"""
        self.session.close()
        self.logger.info("HTTP session closed")


# Singleton pattern implementation
_http_client_instance = None
_http_client_lock = threading.RLock()


def get_http_client() -> HttpClient:
    """
    Get HTTP client instance (singleton pattern)
    
    Returns:
        HttpClient: HTTP client instance
    """
    global _http_client_instance
    with _http_client_lock:
        if _http_client_instance is None:
            _http_client_instance = HttpClient()
        return _http_client_instance


# Provide convenient global instance
http_client = get_http_client()


# Convenience functions that can be directly imported and used
def http_get(url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Convenience function: GET request"""
    return http_client.get(url, data, is_token, headers, **kwargs)


def http_post(url: str, data: Optional[Any] = None, is_token: bool = True, 
             headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Convenience function: POST request"""
    return http_client.post(url, data, is_token, headers, **kwargs)


def http_put(url: str, data: Optional[Any] = None, is_token: bool = True, 
            headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Convenience function: PUT request"""
    return http_client.put(url, data, is_token, headers, **kwargs)


def http_delete(url: str, data: Optional[Any] = None, is_token: bool = False, 
               headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Any]:
    """Convenience function: DELETE request"""
    return http_client.delete(url, data, is_token, headers, **kwargs)


def set_http_base_url(base_url: str) -> None:
    """Convenience function: set base URL"""
    http_client.set_base_url(base_url)


def set_http_timeout(timeout: int) -> None:
    """Convenience function: set timeout"""
    http_client.set_timeout(timeout)


def close_http_client() -> None:
    """Convenience function: close HTTP client"""
    http_client.close()