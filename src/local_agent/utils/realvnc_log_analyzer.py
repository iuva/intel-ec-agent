"""
RealVNC日志分析工具类
用于分析RealVNC的连接日志，提供连接状态和连接时间信息

创建时间: 2025-01-20
版本: 1.0.0
"""

import os
import re
import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path


class RealVNCLogAnalyzer:
    """RealVNC日志分析工具类"""
    
    def __init__(self, log_dir: Optional[str] = None):
        """
        初始化RealVNC日志分析器
        
        Args:
            log_dir: RealVNC日志目录路径，如果为None则使用默认路径
        """
        self.log_dir = log_dir or self._get_default_log_dir()
        self._connection_patterns = [
            # 连接成功模式
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Cc]onnect.*[Ss]uccess',
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Cc]onnection.*[Ee]stablished',
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Cc]onnected.*to',
            
            # 断开连接模式
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Dd]isconnect',
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Cc]onnection.*[Cc]losed',
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*[Ll]ost.*[Cc]onnection',
            
            # 通用时间戳模式
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
        ]
    
    def _get_default_log_dir(self) -> str:
        """
        获取默认的RealVNC日志目录
        
        Returns:
            RealVNC日志目录路径
        """
        # Windows系统下的常见RealVNC日志位置
        possible_paths = [
            # RealVNC Viewer日志
            os.path.join(os.environ.get('APPDATA', ''), 'RealVNC', 'vncviewer.log'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'RealVNC', 'Logs'),
            
            # RealVNC Server日志
            os.path.join(os.environ.get('PROGRAMDATA', ''), 'RealVNC', 'Logs'),
            'C:\\Program Files\\RealVNC\\VNC Server\\Logs',
            'C:\\Program Files\\RealVNC\\VNC Viewer\\Logs',
            
            # 用户目录下的日志
            os.path.join(os.path.expanduser('~'), '.vnc'),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path if os.path.isdir(path) else os.path.dirname(path)
        
        # 如果找不到现有目录，返回最常见的路径
        return os.path.join(os.environ.get('APPDATA', ''), 'RealVNC')
    
    def _find_log_files(self) -> List[str]:
        """
        查找RealVNC日志文件
        
        Returns:
            日志文件路径列表
        """
        log_files = []
        
        if os.path.isfile(self.log_dir):
            # 如果log_dir是文件路径
            log_files.append(self.log_dir)
        elif os.path.isdir(self.log_dir):
            # 如果是目录，查找所有可能的日志文件
            for root, dirs, files in os.walk(self.log_dir):
                for file in files:
                    if file.lower().endswith(('.log', '.txt')) or 'vnc' in file.lower():
                        log_files.append(os.path.join(root, file))
        
        return log_files
    
    def _parse_log_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        解析日志文件，提取连接事件
        
        Args:
            file_path: 日志文件路径
            
        Returns:
            连接事件列表，包含时间戳和事件类型
        """
        events = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 首先尝试匹配时间戳
                    timestamp_match = None
                    timestamp_patterns = [
                        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
                        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})',
                        r'(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})'
                    ]
                    
                    for pattern in timestamp_patterns:
                        match = re.search(pattern, line)
                        if match:
                            timestamp_match = match.group(1)
                            break
                    
                    if timestamp_match:
                        event_type = 'unknown'
                        
                        # 判断事件类型
                        if re.search(r'[Cc]onnect.*[Ss]uccess|[Cc]onnection.*[Ee]stablished|[Cc]onnected.*[Tt]o', line, re.IGNORECASE):
                            event_type = 'connect'
                        elif re.search(r'[Dd]isconnect|[Cc]onnection.*[Cc]losed|[Ll]ost.*[Cc]onnection', line, re.IGNORECASE):
                            event_type = 'disconnect'
                        
                        # 只有当确定是连接或断开事件时才记录
                        if event_type != 'unknown':
                            events.append({
                                'timestamp': timestamp_match,
                                'event_type': event_type,
                                'line': line,
                                'file': file_path,
                                'line_number': line_num
                            })
        except Exception as e:
            print(f"解析日志文件 {file_path} 时出错: {e}")
        
        return events
    
    def get_last_connection_time(self) -> Optional[datetime.datetime]:
        """
        获取最后一次连接成功的时间
        
        Returns:
            最后一次连接成功的时间，如果未找到则返回None
        """
        all_events = self._get_all_events()
        
        # 过滤出连接成功的事件并按时间排序
        connect_events = [
            event for event in all_events 
            if event['event_type'] == 'connect'
        ]
        
        if not connect_events:
            return None
        
        # 按时间戳排序，获取最新的连接事件
        connect_events.sort(key=lambda x: x['timestamp'], reverse=True)
        latest_event = connect_events[0]
        
        # 解析时间戳
        try:
            # 尝试多种时间格式
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y/%m/%d %H:%M:%S',
                '%d-%m-%Y %H:%M:%S',
                '%d/%m/%Y %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    return datetime.datetime.strptime(latest_event['timestamp'], fmt)
                except ValueError:
                    continue
        except Exception as e:
            print(f"解析时间戳失败: {e}")
        
        return None
    
    def is_last_connection_disconnected(self) -> bool:
        """
        检查最后一次连接是否断开
        
        Returns:
            True表示最后一次连接已断开，False表示连接仍然保持或无法确定
        """
        all_events = self._get_all_events()
        
        if not all_events:
            return False  # 没有连接记录，无法判断
        
        # 按时间戳排序所有事件
        all_events.sort(key=lambda x: x['timestamp'])
        
        # 找到最后一个连接事件
        last_connect_index = -1
        for i in range(len(all_events)-1, -1, -1):
            if all_events[i]['event_type'] == 'connect':
                last_connect_index = i
                break
        
        if last_connect_index == -1:
            return False  # 没有找到连接事件
        
        # 检查连接事件之后是否有断开事件
        for i in range(last_connect_index + 1, len(all_events)):
            if all_events[i]['event_type'] == 'disconnect':
                return True
        
        return False  # 连接事件之后没有断开事件
    
    def _get_all_events(self) -> List[Dict[str, str]]:
        """
        获取所有日志文件中的事件
        
        Returns:
            所有事件列表
        """
        all_events = []
        log_files = self._find_log_files()
        
        for log_file in log_files:
            events = self._parse_log_file(log_file)
            all_events.extend(events)
        
        return all_events
    
    def get_connection_statistics(self) -> Dict[str, any]:
        """
        获取连接统计信息
        
        Returns:
            连接统计信息字典
        """
        all_events = self._get_all_events()
        
        connect_count = len([e for e in all_events if e['event_type'] == 'connect'])
        disconnect_count = len([e for e in all_events if e['event_type'] == 'disconnect'])
        
        last_connect_time = self.get_last_connection_time()
        is_disconnected = self.is_last_connection_disconnected()
        
        return {
            'total_connections': connect_count,
            'total_disconnections': disconnect_count,
            'last_connection_time': last_connect_time.isoformat() if last_connect_time else None,
            'is_last_connection_disconnected': is_disconnected,
            'connection_balance': connect_count - disconnect_count,
            'log_files_found': len(self._find_log_files())
        }
    
    def get_recent_connections(self, count: int = 10) -> List[Dict[str, str]]:
        """
        获取最近的连接记录
        
        Args:
            count: 要获取的记录数量
            
        Returns:
            最近的连接记录列表
        """
        all_events = self._get_all_events()
        
        # 按时间戳排序，获取最新的记录
        all_events.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return all_events[:count]


def create_realvnc_log_analyzer(log_dir: Optional[str] = None) -> RealVNCLogAnalyzer:
    """
    创建RealVNC日志分析器实例的便捷函数
    
    Args:
        log_dir: RealVNC日志目录路径
        
    Returns:
        RealVNCLogAnalyzer实例
    """
    return RealVNCLogAnalyzer(log_dir)


# 使用示例
if __name__ == "__main__":
    # 创建分析器实例
    analyzer = RealVNCLogAnalyzer()
    
    # 获取最后一次连接时间
    last_connect = analyzer.get_last_connection_time()
    if last_connect:
        print(f"最后一次连接成功时间: {last_connect}")
    else:
        print("未找到连接记录")
    
    # 检查最后一次连接是否断开
    is_disconnected = analyzer.is_last_connection_disconnected()
    print(f"最后一次连接是否断开: {is_disconnected}")
    
    # 获取连接统计信息
    stats = analyzer.get_connection_statistics()
    print(f"连接统计: {stats}")
    
    # 获取最近的连接记录
    recent_connections = analyzer.get_recent_connections(5)
    print(f"最近的5条连接记录:")
    for conn in recent_connections:
        print(f"  {conn['timestamp']} - {conn['event_type']}")