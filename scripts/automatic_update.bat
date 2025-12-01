@echo off
setlocal enabledelayedexpansion

REM ============================================
REM Auto Update Batch Script
REM Parameters:
REM   %1 - Service name (optional)
REM   %2 - New EXE file path
REM   %3 - Old EXE file path
REM   %4 - Backup directory path
REM ============================================

REM Set log file with simple timestamp
for /f "tokens=1-3 delims=/" %%a in ('date /t') do set date_str=%%a%%b%%c
for /f "tokens=1-2 delims=:" %%a in ('time /t') do set time_str=%%a%%b
set timestamp=%date_str%_%time_str%
set "LOG_FILE=%~dp0update_%timestamp%.log"

echo [%date% %time%] Start update script >> "%LOG_FILE%"

REM 1. Check parameter completeness
if "%~1"=="" (
    echo [ERROR] Missing service name parameter >> "%LOG_FILE%"
    exit /b 1
)
if "%~2"=="" (
    echo [ERROR] Missing new EXE file path parameter >> "%LOG_FILE%"
    exit /b 1
)
if "%~3"=="" (
    echo [ERROR] Missing old EXE file path parameter >> "%LOG_FILE%"
    exit /b 1
)
if "%~4"=="" (
    echo [ERROR] Missing backup directory path parameter >> "%LOG_FILE%"
    exit /b 1
)

REM 2. Check administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Administrator privileges required >> "%LOG_FILE%"
    exit /b 1
)

echo [INFO] Parameter validation passed >> "%LOG_FILE%"
echo Service name: %1 >> "%LOG_FILE%"
echo New EXE path: %2 >> "%LOG_FILE%"
echo Old EXE path: %3 >> "%LOG_FILE%"
echo Backup directory: %4 >> "%LOG_FILE%"

echo [DEBUG] Starting service processing... >> "%LOG_FILE%"

REM 3. Stop and delete service (if service name provided)
if not "%1"=="" (
    echo [INFO] Processing service %1... >> "%LOG_FILE%"
    
    REM Check if service exists
    sc query "%1" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Service %1 exists, stopping it... >> "%LOG_FILE%"
        
        REM Stop the service (try both net stop and sc stop)
        net stop "%1" >nul 2>&1
        timeout /t 2 /nobreak >nul
        sc stop "%1" >nul 2>&1
        timeout /t 1 /nobreak >nul
        
        echo [INFO] Service %1 stopped, deleting it... >> "%LOG_FILE%"
        
        REM Delete the service
        sc delete "%1" >nul 2>&1
        
        echo [INFO] Service %1 deleted successfully >> "%LOG_FILE%"
    ) else (
        echo [INFO] Service %1 does not exist, skipping service operations >> "%LOG_FILE%"
    )
)

echo [DEBUG] Service processing completed, continuing to process termination... >> "%LOG_FILE%"

REM 4. Kill all local_agent related processes
echo [INFO] Killing all local_agent processes... >> "%LOG_FILE%"

REM Compatibility handling: wait for confirmation regardless of process existence
set wait_count=0
set max_wait_seconds=20

:check_process_status
tasklist /fi "imagename eq local_agent.exe" /fo csv 2>nul | find /i "local_agent.exe" >nul
if %errorlevel% equ 0 (
    REM Process exists, need to terminate
    if !wait_count! equ 0 (
        echo [INFO] Found running local_agent processes, starting termination... >> "%LOG_FILE%"
        taskkill /f /im local_agent.exe >nul 2>&1
    ) else (
        echo [DEBUG] Process still running, waiting for termination !wait_count! of !max_wait_seconds!... >> "%LOG_FILE%"
    )
    
    set /a wait_count+=1
    if !wait_count! gtr !max_wait_seconds! (
        echo [WARNING] Process termination timeout after !max_wait_seconds! seconds, continuing update... >> "%LOG_FILE%"
        goto file_replacement
    ) else (
        timeout /t 1 /nobreak >nul
        goto check_process_status
    )
) else (
    REM Process does not exist
    if !wait_count! equ 0 (
        echo [INFO] No running local_agent processes found initially >> "%LOG_FILE%"
    ) else (
        echo [INFO] All local_agent processes terminated successfully after !wait_count! seconds >> "%LOG_FILE%"
    )
    
    REM Wait additional time to ensure process stability
    if !wait_count! lss 3 (
        echo [DEBUG] Waiting additional 3 seconds to ensure process stability... >> "%LOG_FILE%"
        set /a wait_count+=3
        timeout /t 3 /nobreak >nul
    )
    
    goto file_replacement
)

:file_replacement

REM 5. Backup old file (handled by Python process manager)
echo [INFO] Skipping backup - handled by Python process manager >> "%LOG_FILE%"

REM 6. Replace file (with retry mechanism and timeout)
echo [INFO] Starting file replacement... >> "%LOG_FILE%"
echo [DEBUG] Source file: %2 >> "%LOG_FILE%"
echo [DEBUG] Target file: %3 >> "%LOG_FILE%"

REM Check if source file exists and is accessible
if not exist "%2" (
    echo [ERROR] New file does not exist: %2 >> "%LOG_FILE%"
    goto rollback
)

REM Check file sizes for debugging
echo [DEBUG] Checking file sizes... >> "%LOG_FILE%"
for %%F in ("%2") do set "source_size=%%~zF"
for %%F in ("%3") do set "target_size=%%~zF"
echo [DEBUG] Source file size: !source_size! bytes >> "%LOG_FILE%"
echo [DEBUG] Target file size: !target_size! bytes >> "%LOG_FILE%"

set retry_count=0
set max_retries=3
:replace_file
if exist "%2" (
    set /a attempt_num=retry_count+1
    echo [DEBUG] Attempting file copy attempt !attempt_num! of !max_retries!... >> "%LOG_FILE%"
    
    REM Use timeout mechanism for copy command
    timeout /t 5 /nobreak >nul
    copy /y "%2" "%3" >nul 2>&1
    
    if %errorlevel% equ 0 (
        echo [INFO] File replacement successful >> "%LOG_FILE%"
        
        REM Verify file replacement by checking file size
        timeout /t 1 /nobreak >nul
        if exist "%3" (
            for %%F in ("%3") do set "new_target_size=%%~zF"
            echo [DEBUG] New target file size: !new_target_size! bytes >> "%LOG_FILE%"
            
            REM Compare file sizes to ensure copy was complete
            if "!new_target_size!"=="!source_size!" (
                echo [INFO] File replacement verified size match >> "%LOG_FILE%"
                goto start_new_process
            ) else (
                echo [ERROR] File size mismatch after copy expected !source_size! actual !new_target_size! >> "%LOG_FILE%"
                goto rollback
            )
        ) else (
            echo [ERROR] Target file does not exist after copy >> "%LOG_FILE%"
            goto rollback
        )
    ) else (
        set /a retry_count=retry_count+1
        if !retry_count! lss !max_retries! (
            echo [WARNING] File copy failed errorlevel %errorlevel% waiting to retry !retry_count! of !max_retries!... >> "%LOG_FILE%"
            timeout /t 2 /nobreak >nul
            goto replace_file
        ) else (
            echo [ERROR] File replacement failed after !max_retries! attempts executing rollback >> "%LOG_FILE%"
            goto rollback
        )
    )
) else (
    echo [ERROR] New file disappeared during retry: %2 >> "%LOG_FILE%"
    goto rollback
)

REM 7. Start new process
:start_new_process
echo [INFO] Starting new process... >> "%LOG_FILE%"

REM Verify the target executable exists before starting
if not exist "%3" (
    echo [ERROR] Target executable does not exist: %3 >> "%LOG_FILE%"
    goto rollback
)

REM Start the new process with proper error handling
start "" /b "%3"
if %errorlevel% equ 0 (
    echo [INFO] New process started successfully >> "%LOG_FILE%"
    
    REM Wait a moment and check if process is running
    timeout /t 2 /nobreak >nul
    tasklist /fi "imagename eq local_agent.exe" /fo csv 2>nul | find /i "local_agent.exe" >nul
    if %errorlevel% equ 0 (
        echo [INFO] New process is running successfully >> "%LOG_FILE%"
        echo [SUCCESS] Update completed successfully >> "%LOG_FILE%"
        exit /b 0
    ) else (
        echo [WARNING] New process started but not detected in tasklist >> "%LOG_FILE%"
        echo [SUCCESS] Update completed process may be running >> "%LOG_FILE%"
        exit /b 0
    )
) else (
    echo [ERROR] New process start failed errorlevel %errorlevel% >> "%LOG_FILE%"
    goto rollback
)

REM 8. Rollback mechanism
:rollback
echo [INFO] Executing rollback... >> "%LOG_FILE%"

REM Debug: Check backup directory contents
echo [DEBUG] Checking backup directory: %4 >> "%LOG_FILE%"
dir "%4" >> "%LOG_FILE%" 2>&1

REM Restore backup file with improved error handling
set backup_found=0

REM Method 1: Try exact file pattern matching
for /f "delims=" %%i in ('dir /b "%4\local_agent.exe.backup.*" 2^>nul') do (
    echo [DEBUG] Found backup file: %%i >> "%LOG_FILE%"
    copy "%4\%%i" "%3" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Rollback successful: %%i >> "%LOG_FILE%"
        set backup_found=1
        
        REM Verify the restored file
        if exist "%3" (
            for %%F in ("%3") do set "restored_size=%%~zF"
            echo [DEBUG] Restored file size: !restored_size! bytes >> "%LOG_FILE%"
            
            REM Try to start old version
            start "" /b "%3"
            if %errorlevel% equ 0 (
                echo [INFO] Old version started successfully >> "%LOG_FILE%"
            ) else (
                echo [WARNING] Old version start failed errorlevel %errorlevel% >> "%LOG_FILE%"
            )
            exit /b 1
        ) else (
            echo [ERROR] Restored file does not exist >> "%LOG_FILE%"
            exit /b 1
        )
    ) else (
        echo [ERROR] Copy failed for backup file: %%i >> "%LOG_FILE%"
    )
)

REM Method 2: If no files found with pattern, try alternative search
if !backup_found! equ 0 (
    echo [DEBUG] Trying alternative backup file search... >> "%LOG_FILE%"
    
    REM Check if backup directory exists
    if not exist "%4" (
        echo [ERROR] Backup directory does not exist: %4 >> "%LOG_FILE%"
        exit /b 1
    )
    
    REM Look for any backup files in the directory
    for /f "delims=" %%i in ('dir /b "%4" 2^>nul') do (
        echo "%%i" | findstr "backup" >nul
        if !errorlevel! equ 0 (
            echo [DEBUG] Found potential backup file: %%i >> "%LOG_FILE%"
            copy "%4\%%i" "%3" >nul 2>&1
            if %errorlevel% equ 0 (
                echo [INFO] Rollback successful: %%i >> "%LOG_FILE%"
                set backup_found=1
                
                REM Try to start old version
                start "" /b "%3"
                if %errorlevel% equ 0 (
                    echo [INFO] Old version started successfully >> "%LOG_FILE%"
                ) else (
                    echo [WARNING] Old version start failed >> "%LOG_FILE%"
                )
                exit /b 1
            )
        )
    )
)

if !backup_found! equ 0 (
    echo [ERROR] Rollback failed, no backup files available in %4 >> "%LOG_FILE%"
    echo [DEBUG] Backup directory contents: >> "%LOG_FILE%"
    dir "%4" >> "%LOG_FILE%" 2>&1
    exit /b 1
)