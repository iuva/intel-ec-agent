#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间工具类
提供各种时间相关的工具函数
"""

import datetime
from typing import Optional


class TimeUtils:
    """时间工具类"""
    
    @staticmethod
    def get_seconds_to_next_target(target: str = '00:00:00') -> int:
        """
        获取距离下一个指定时间点还有多少秒
        
        Args:
            target: 目标时间字符串，格式为'HH:MM:SS'或'HH:MM'，默认为'00:00:00'
            
        Returns:
            int: 距离下一个目标时间的秒数
            
        Raises:
            ValueError: 如果时间格式不正确或时间值无效
            
        Example:
            >>> TimeUtils.get_seconds_to_next_target('12:00:00')
            3600  # 如果现在是11:00:00，返回3600秒（1小时）
            >>> TimeUtils.get_seconds_to_next_target('09:30')
            5400  # 如果现在是08:00:00，返回5400秒（1.5小时）
        """
        try:
            # 解析目标时间
            time_parts = target.split(':')
            
            if len(time_parts) == 2:
                # 格式: HH:MM
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = 0
            elif len(time_parts) == 3:
                # 格式: HH:MM:SS
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = int(time_parts[2])
            else:
                raise ValueError(f"时间格式不正确: {target}，请使用'HH:MM:SS'或'HH:MM'格式")
            
            # 验证时间值
            if not (0 <= hour <= 23):
                raise ValueError(f"小时值必须在0-23范围内: {hour}")
            if not (0 <= minute <= 59):
                raise ValueError(f"分钟值必须在0-59范围内: {minute}")
            if not (0 <= second <= 59):
                raise ValueError(f"秒值必须在0-59范围内: {second}")
            
            # 获取当前时间
            now = datetime.datetime.now()
            
            # 计算今天的目标时间
            target_today = datetime.datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=minute,
                second=second
            )
            
            # 计算时间差
            if target_today > now:
                # 目标时间在今天
                time_delta = target_today - now
            else:
                # 目标时间在今天之前，计算明天的目标时间
                target_tomorrow = target_today + datetime.timedelta(days=1)
                time_delta = target_tomorrow - now
            
            seconds_to_target = int(time_delta.total_seconds())
            
            return seconds_to_target
            
        except ValueError as e:
            # 重新抛出验证错误
            raise e
        except Exception as e:
            # 其他异常，返回一个默认值
            return 86400
    
    @staticmethod
    def get_seconds_to_next_midnight() -> int:
        """
        获取距离下一个0点（午夜）还有多少秒
        
        Returns:
            int: 距离下一个0点的秒数
            
        Example:
            >>> TimeUtils.get_seconds_to_next_midnight()
            3600  # 如果现在是23:00，返回3600秒（1小时）
        """
        return TimeUtils.get_seconds_to_next_target('00:00:00')
    
    @staticmethod
    def get_seconds_to_next_hour(hour: int = 0) -> int:
        """
        获取距离下一个指定小时还有多少秒
        
        Args:
            hour: 目标小时（0-23），默认为0（午夜）
            
        Returns:
            int: 距离下一个指定小时的秒数
            
        Raises:
            ValueError: 如果小时参数不在0-23范围内
            
        Example:
            >>> TimeUtils.get_seconds_to_next_hour(6)
            7200  # 如果现在是4:00，返回7200秒（2小时）
        """
        if not 0 <= hour <= 23:
            raise ValueError("小时参数必须在0-23范围内")
        
        try:
            # 获取当前时间
            now = datetime.datetime.now()
            
            # 计算下一个指定小时的时间
            next_target_hour = datetime.datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=0,
                second=0
            )
            
            # 如果目标时间已经过去，则计算下一天的
            if next_target_hour <= now:
                next_target_hour += datetime.timedelta(days=1)
            
            # 计算时间差（秒）
            time_delta = next_target_hour - now
            seconds_to_target = int(time_delta.total_seconds())
            
            return seconds_to_target
            
        except Exception as e:
            # 如果出现异常，返回一个默认值
            return (24 - now.hour + hour) % 24 * 3600
    
    @staticmethod
    def format_seconds(seconds: int) -> str:
        """
        将秒数格式化为易读的时间字符串
        
        Args:
            seconds: 秒数
            
        Returns:
            str: 格式化的时间字符串
            
        Example:
            >>> TimeUtils.format_seconds(3661)
            '1小时1分钟1秒'
        """
        if seconds < 0:
            return "0秒"
        
        # 计算小时、分钟、秒
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        # 构建格式化字符串
        parts = []
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if secs > 0 or not parts:  # 如果没有小时和分钟，至少显示秒
            parts.append(f"{secs}秒")
        
        return "".join(parts)
    
    @staticmethod
    def is_midnight() -> bool:
        """
        判断当前是否是午夜（0点）
        
        Returns:
            bool: 如果是午夜返回True，否则返回False
            
        Example:
            >>> TimeUtils.is_midnight()
            False  # 如果当前不是0点
        """
        now = datetime.datetime.now()
        return now.hour == 0 and now.minute == 0 and now.second == 0

    @staticmethod
    def add_minutes_to_current(minutes: int) -> datetime.datetime:
        """
        计算当前时间加上指定分钟数后的时间
        
        Args:
            minutes: 要添加的分钟数（可以为负数，表示减去分钟数）
            
        Returns:
            datetime.datetime: 计算后的时间对象
            
        Example:
            >>> TimeUtils.add_minutes_to_current(30)
            datetime.datetime(2023, 10, 15, 14, 30, 0)  # 如果当前是14:00:00
            >>> TimeUtils.add_minutes_to_current(-15)
            datetime.datetime(2023, 10, 15, 13, 45, 0)  # 如果当前是14:00:00
        """
        if not minutes or minutes == 0:
            return None

        now = datetime.datetime.now()
        return now + datetime.timedelta(minutes=minutes)


# 提供便捷的全局函数
def get_seconds_to_next_target(target: str = '00:00:00') -> int:
    """获取距离下一个指定时间点还有多少秒（便捷函数）"""
    return TimeUtils.get_seconds_to_next_target(target)


def get_seconds_to_next_midnight() -> int:
    """获取距离下一个0点还有多少秒（便捷函数）"""
    return TimeUtils.get_seconds_to_next_midnight()


def get_formatted_time_to_target(target: str = '00:00:00') -> str:
    """获取距离下一个指定时间点的格式化时间字符串（便捷函数）"""
    seconds = TimeUtils.get_seconds_to_next_target(target)
    return TimeUtils.format_seconds(seconds)


def get_formatted_time_to_midnight() -> str:
    """获取距离下一个0点的格式化时间字符串（便捷函数）"""
    seconds = TimeUtils.get_seconds_to_next_midnight()
    return TimeUtils.format_seconds(seconds)


def add_minutes_to_current(minutes: int) -> datetime.datetime:
    """计算当前时间加上指定分钟数后的时间（便捷函数）"""
    return TimeUtils.add_minutes_to_current(minutes)


if __name__ == "__main__":
    # 测试代码
    print("=== 时间工具类测试 ===")
    
    # 测试获取距离下一个指定时间点的秒数
    test_targets = ['00:00:00', '12:00:00', '18:30:00', '09:15', '23:59:59']
    
    for target in test_targets:
        try:
            seconds = TimeUtils.get_seconds_to_next_target(target)
            formatted = TimeUtils.format_seconds(seconds)
            print(f"距离下一个{target}还有: {seconds}秒 ({formatted})")
        except ValueError as e:
            print(f"错误 - 目标时间{target}: {e}")
    
    # 测试获取距离下一个0点的秒数（兼容性测试）
    seconds = TimeUtils.get_seconds_to_next_midnight()
    formatted = TimeUtils.format_seconds(seconds)
    print(f"距离下一个0点还有: {seconds}秒 ({formatted})")
    
    # 测试获取距离下一个6点的秒数
    try:
        seconds_to_6am = TimeUtils.get_seconds_to_next_hour(6)
        formatted_6am = TimeUtils.format_seconds(seconds_to_6am)
        print(f"距离下一个6点还有: {seconds_to_6am}秒 ({formatted_6am})")
    except ValueError as e:
        print(f"错误: {e}")
    
    # 测试是否是午夜
    is_midnight = TimeUtils.is_midnight()
    print(f"当前是否是午夜: {'是' if is_midnight else '否'}")
    
    # 测试便捷函数
    print(f"便捷函数 - 距离12点: {get_formatted_time_to_target('12:00:00')}")
    print(f"便捷函数 - 距离0点: {get_formatted_time_to_midnight()}")
    
    # 测试添加分钟数功能
    print("\n=== 添加分钟数测试 ===")
    test_minutes = [30, 60, -15, 120, -30]
    for minutes in test_minutes:
        result = TimeUtils.add_minutes_to_current(minutes)
        print(f"当前时间 + {minutes}分钟 = {result.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试便捷函数
    test_minutes = [45, -10]
    for minutes in test_minutes:
        result = add_minutes_to_current(minutes)
        print(f"便捷函数 - 当前时间 + {minutes}分钟 = {result.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试错误时间格式
    print("\n=== 错误格式测试 ===")
    invalid_targets = ['25:00:00', '12:60:00', '12:00:60', 'invalid', '12:00:00:00']
    
    for invalid_target in invalid_targets:
        try:
            seconds = TimeUtils.get_seconds_to_next_target(invalid_target)
            print(f"目标时间{invalid_target}: {seconds}秒")
        except ValueError as e:
            print(f"目标时间{invalid_target}: {e}")
