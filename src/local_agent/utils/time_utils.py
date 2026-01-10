#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Time utility class
Provides various time-related utility functions
"""

import datetime
from typing import Optional


class TimeUtils:
    """[Time] utility class"""
    
    @staticmethod
    def get_seconds_to_next_target(target: str = '00:00:00') -> int:
        """
        Get how many seconds until the next specified time point
        
        Args:
            target: Target time string, format 'HH:MM:SS' or 'HH:MM', default '00:00:00'
            
        Returns:
            int: Seconds until next target time
            
        Raises:
            ValueError: If time format is incorrect or time value is invalid
            
        Example:
            >>> TimeUtils.get_seconds_to_next_target('12:00:00')
            3600  # If current time is 11:00:00, returns 3600 seconds (1 hour)
            >>> TimeUtils.get_seconds_to_next_target('09:30')
            5400  # If current time is 08:00:00, returns 5400 seconds (1.5 hours)
        """
        try:
            # [Parse target] time
            time_parts = target.split(':')
            
            if len(time_parts) == 2:
                # [Format]: HH:MM
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = 0
            elif len(time_parts) == 3:
                # [Format]: HH:MM:SS
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = int(time_parts[2])
            else:
                raise ValueError(f"Invalid time format: {target}, please use 'HH:MM:SS' or 'HH:MM' format")
            
            # Validate time [values]
            if not (0 <= hour <= 23):
                raise ValueError(f"Hour value must be in range 0-23: {hour}")
            if not (0 <= minute <= 59):
                raise ValueError(f"Minute value must be in range 0-59: {minute}")
            if not (0 <= second <= 59):
                raise ValueError(f"Second value must be in range 0-59: {second}")
            
            # Get [current] time
            now = datetime.datetime.now()
            
            # [Calculate today's] target [time]
            target_today = datetime.datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=minute,
                second=second
            )
            
            # [Calculate] time [difference]
            if target_today > now:
                # [Target] time [is today]
                time_delta = target_today - now
            else:
                # [Target] time [is before today], [calculate tomorrow's] target [time]
                target_tomorrow = target_today + datetime.timedelta(days=1)
                time_delta = target_tomorrow - now
            
            seconds_to_target = int(time_delta.total_seconds())
            
            return seconds_to_target
            
        except ValueError as e:
            # [Re-raise] validation error
            raise e
        except Exception as e:
            # [Other] exception, [return a] default [value]
            return 86400
    
    @staticmethod
    def get_seconds_to_next_midnight() -> int:
        """
        Get how many seconds until the next 0:00 (midnight)
        
        Returns:
            int: Seconds until next midnight
            
        Example:
            >>> TimeUtils.get_seconds_to_next_midnight()
            3600  # If current time is 23:00, returns 3600 seconds (1 hour)
        """
        return TimeUtils.get_seconds_to_next_target('00:00:00')
    
    @staticmethod
    def get_seconds_to_next_hour(hour: int = 0) -> int:
        """
        Get how many seconds until the next specified hour
        
        Args:
            hour: Target hour (0-23), default 0 (midnight)
            
        Returns:
            int: Seconds until next specified hour
            
        Raises:
            ValueError: If hour parameter is not in 0-23 range
            
        Example:
            >>> TimeUtils.get_seconds_to_next_hour(6)
            7200  # If current time is 4:00, returns 7200 seconds (2 hours)
        """
        if not 0 <= hour <= 23:
            raise ValueError("Hour parameter must be in range 0-23")
        
        try:
            # Get [current] time
            now = datetime.datetime.now()
            
            # [Calculate next specified] hour ['s] time
            next_target_hour = datetime.datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=hour,
                minute=0,
                second=0
            )
            
            # If [target] time [has passed], [then calculate next] day ['s]
            if next_target_hour <= now:
                next_target_hour += datetime.timedelta(days=1)
            
            # [Calculate] time [difference] (seconds)
            time_delta = next_target_hour - now
            seconds_to_target = int(time_delta.total_seconds())
            
            return seconds_to_target
            
        except Exception as e:
            # If [an] exception [occurs], [return a] default [value]
            return (24 - now.hour + hour) % 24 * 3600
    
    @staticmethod
    def format_seconds(seconds: int) -> str:
        """
        Format seconds into a human-readable time string
        
        Args:
            seconds: Number of seconds
            
        Returns:
            str: Formatted time string
            
        Example:
            >>> TimeUtils.format_seconds(3661)
            '1 hour 1 minute 1 second'
        """
        if seconds < 0:
            return "0 seconds"
        
        # [Calculate] hours, minutes, seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        # [Build formatted string]
        parts = []
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
        if secs > 0 or not parts:  # If no hours and minutes, at least show seconds
            parts.append(f"{secs} second{'s' if secs > 1 else ''}")
        
        return " ".join(parts)
    
    @staticmethod
    def is_midnight() -> bool:
        """
        Check if current time is midnight (0:00)
        
        Returns:
            bool: Returns True if it's midnight, otherwise False
            
        Example:
            >>> TimeUtils.is_midnight()
            False  # If current time is not 0:00
        """
        now = datetime.datetime.now()
        return now.hour == 0 and now.minute == 0 and now.second == 0

    @staticmethod
    def add_minutes_to_current(minutes: int) -> datetime.datetime:
        """
        Calculate time after adding specified minutes to current time
        
        Args:
            minutes: Minutes to add (can be negative, meaning subtract minutes)
            
        Returns:
            datetime.datetime: Calculated time object
            
        Example:
            >>> TimeUtils.add_minutes_to_current(30)
            datetime.datetime(2023, 10, 15, 14, 30, 0)  # If current time is 14:00:00
            >>> TimeUtils.add_minutes_to_current(-15)
            datetime.datetime(2023, 10, 15, 13, 45, 0)  # If current time is 14:00:00
        """
        if not minutes or minutes == 0:
            return None

        now = datetime.datetime.now()
        return now + datetime.timedelta(minutes=minutes)


# [Provide convenient] global functions
def get_seconds_to_next_target(target: str = '00:00:00') -> int:
    """Get [how many seconds until the next specified time point] ([convenient] function)"""
    return TimeUtils.get_seconds_to_next_target(target)


def get_seconds_to_next_midnight() -> int:
    """Get [how many seconds until the next] 0 [point] ([convenient] function)"""
    return TimeUtils.get_seconds_to_next_midnight()


def get_formatted_time_to_target(target: str = '00:00:00') -> str:
    """Get [formatted time string until the next specified time point] ([convenient] function)"""
    seconds = TimeUtils.get_seconds_to_next_target(target)
    return TimeUtils.format_seconds(seconds)


def get_formatted_time_to_midnight() -> str:
    """Get [formatted time string until the next] 0 [point] ([convenient] function)"""
    seconds = TimeUtils.get_seconds_to_next_midnight()
    return TimeUtils.format_seconds(seconds)


def add_minutes_to_current(minutes: int) -> datetime.datetime:
    """[Calculate time after adding specified minutes to current time] ([convenient] function)"""
    return TimeUtils.add_minutes_to_current(minutes)


if __name__ == "__main__":
    # Test [code]
    print("=== Time utility class test ===")
    
    # Test get [seconds to next specified] time [point]
    test_targets = ['00:00:00', '12:00:00', '18:30:00', '09:15', '23:59:59']
    
    for target in test_targets:
        try:
            seconds = TimeUtils.get_seconds_to_next_target(target)
            formatted = TimeUtils.format_seconds(seconds)
            print(f"Seconds until next {target}: {seconds} seconds ({formatted})")
        except ValueError as e:
            print(f"Error - target time {target}: {e}")
    
    # Test get [seconds to next] 0 [point] ([compatibility] test)
    seconds = TimeUtils.get_seconds_to_next_midnight()
    formatted = TimeUtils.format_seconds(seconds)
    print(f"Seconds until next 0:00: {seconds} seconds ({formatted})")
    
    # Test get [seconds to next] 6 [point]
    try:
        seconds_to_6am = TimeUtils.get_seconds_to_next_hour(6)
        formatted_6am = TimeUtils.format_seconds(seconds_to_6am)
        print(f"Seconds until next 6:00: {seconds_to_6am} seconds ({formatted_6am})")
    except ValueError as e:
        print(f"Error: {e}")
    
    # Test [if it's midnight]
    is_midnight = TimeUtils.is_midnight()
    print(f"Is it currently midnight: {'Yes' if is_midnight else 'No'}")
    
    # Test [convenient] functions
    print(f"Convenient function - until 12:00: {get_formatted_time_to_target('12:00:00')}")
    print(f"Convenient function - until 0:00: {get_formatted_time_to_midnight()}")
    
    # Test [add minutes] functionality
    print("\n=== Add minutes test ===")
    test_minutes = [30, 60, -15, 120, -30]
    for minutes in test_minutes:
        result = TimeUtils.add_minutes_to_current(minutes)
        print(f"Current time + {minutes} minutes = {result.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test [convenient] functions
    test_minutes = [45, -10]
    for minutes in test_minutes:
        result = add_minutes_to_current(minutes)
        print(f"Convenient function - current time + {minutes} minutes = {result.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test error time [formats]
    print("\n=== Error format test ===")
    invalid_targets = ['25:00:00', '12:60:00', '12:00:60', 'invalid', '12:00:00:00']
    
    for invalid_target in invalid_targets:
        try:
            seconds = TimeUtils.get_seconds_to_next_target(invalid_target)
            print(f"Target time {invalid_target}: {seconds} seconds")
        except ValueError as e:
            print(f"Target time {invalid_target}: {e}")
