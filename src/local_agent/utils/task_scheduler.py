#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows Task Scheduler Configuration Module
Used to configure Process A auto-start on system boot
"""

import os
import sys
import subprocess
from ..logger import get_logger
from pathlib import Path
from typing import Dict, Any, Optional
from .path_utils import get_current_executable_path, get_root_path

logger = get_logger()


class TaskScheduler:
    """Windows Task Scheduler Configuration Class"""
    
    def __init__(self, task_name: str = "LocalAgentUI"):
        self.task_name = task_name
        logger.debug(f"TaskScheduler 初始化")
        self.exe_path = get_current_executable_path()
        self.working_dir = get_root_path()

    
    def check_task_status(self) -> Dict[str, Any]:
        """Check task scheduler status"""
        try:
            cmd = f"Get-ScheduledTask -TaskName '{self.task_name}' | Select-Object State, TaskName, TaskPath | ConvertTo-Json"
            result = subprocess.run(["powershell", "-Command", cmd], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                task_info = json.loads(result.stdout)
                return {
                    "exists": True,
                    "state": task_info.get("State", "Unknown"),
                    "task_name": task_info.get("TaskName", ""),
                    "task_path": task_info.get("TaskPath", "")
                }
            else:
                return {"exists": False}
                
        except Exception as e:
            logger.warning(f"Failed to check task scheduler status: {e}")
            return {"exists": False, "error": str(e)}
    
    def create_task(self) -> bool:
        """Create task scheduler"""
        try:
            if not self.exe_path.exists():
                logger.error(f"Executable file does not exist: {self.exe_path}")
                return False
            
            # PowerShell command to create task scheduler
            ps_script = f"""
$TaskName = "{self.task_name}"
$ExePath = "{self.exe_path}"
$WorkingDir = "{self.working_dir}"

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {{
    Write-Output "Task already exists, deleting old task first"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}}

# Create task action (default is UI mode)
$Action = New-ScheduledTaskAction -Execute $ExePath -WorkingDirectory $WorkingDir

# Create trigger (start on user logon with 10-minute delay)
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Delay = "PT10M"  # 10-minute delay, wait for system stability

# Create task settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Settings.RestartCount = 3  # Retry 3 times on failure
$Settings.RestartInterval = "PT1M"  # Retry interval 1 minute

# Create task principal (current user with administrator privileges)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest

# Register task
$Task = Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Local Agent UI Process Auto-start"

if ($Task) {{
    Write-Output "Task created successfully"
    # Enable task
    Enable-ScheduledTask -TaskName $TaskName
    Write-Output "Task enabled"
}} else {{
    Write-Error "Task creation failed"
    exit 1
}}
"""
            
            result = subprocess.run(["powershell", "-Command", ps_script], 
                                  capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                logger.info(f"Task scheduler created successfully: {self.task_name}")
                return True
            else:
                logger.error(f"Task scheduler creation failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Exception creating task scheduler: {e}")
            return False
    
    def repair_task(self) -> bool:
        """Repair task scheduler"""
        try:
            # Delete existing task first
            delete_cmd = f"Unregister-ScheduledTask -TaskName '{self.task_name}' -Confirm:$false -ErrorAction SilentlyContinue"
            subprocess.run(["powershell", "-Command", delete_cmd], 
                         capture_output=True, timeout=30)
            
            # Recreate the task
            return self.create_task()
            
        except Exception as e:
            logger.error(f"Failed to repair task scheduler: {e}")
            return False
    
    def verify_task_execution(self) -> bool:
        """Verify if task scheduler can execute normally"""
        try:
            # Test task execution (don't wait for completion)
            cmd = f"Start-ScheduledTask -TaskName '{self.task_name}'; Start-Sleep -Seconds 2; Stop-ScheduledTask -TaskName '{self.task_name}'"
            result = subprocess.run(["powershell", "-Command", cmd], 
                                  capture_output=True, text=True, timeout=10)
            
            return result.returncode == 0
            
        except Exception as e:
            logger.warning(f"Failed to verify task execution: {e}")
            return False
    
    def configure_auto_start(self) -> bool:
        """Configure auto-start on boot (main entry method)"""
        logger.info("Starting configuration of Process A auto-start...")
        
        # Check task status
        task_status = self.check_task_status()
        
        if not task_status["exists"]:
            logger.info("Task scheduler does not exist, starting creation...")
            return self.create_task()
        
        # Check if task status is normal
        state = task_status.get("state", "")
        if state not in ["Ready", "Running"]:
            logger.warning(f"Task status abnormal: {state}, starting repair...")
            return self.repair_task()
        
        # Verify if task can execute
        if not self.verify_task_execution():
            logger.warning("Task execution verification failed, starting repair...")
            return self.repair_task()
        
        logger.info("Task scheduler configuration normal, no action needed")
        return True


def configure_ui_auto_start() -> bool:
    """Configure UI process auto-start (external call interface)"""
    try:
        scheduler = TaskScheduler()
        return scheduler.configure_auto_start()
    except Exception as e:
        logger.error(f"Failed to configure UI process auto-start: {e}")
        return False


if __name__ == "__main__":
    
    scheduler = TaskScheduler()
    print("检查任务状态:", scheduler.check_task_status())
    print("配置自启动:", scheduler.configure_auto_start())
