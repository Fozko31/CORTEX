@echo off
REM ============================================================================
REM CORTEX Windows Service Installer (NSSM-based)
REM ============================================================================
REM
REM Installs cortex_watchdog.py as a Windows service that:
REM   - Starts automatically on Windows boot
REM   - Restarts on crash (NSSM handles this independently of the watchdog)
REM
REM REQUIREMENTS:
REM   1. NSSM installed: https://nssm.cc/download
REM      Place nssm.exe in C:\tools\nssm\ or update NSSM_PATH below
REM   2. Run this script as Administrator
REM
REM PURPOSE:
REM   For commercial desktop users who want CORTEX to start on boot.
REM   NOT needed for Fly.io deployment (use restart.policy="always" in fly.toml).
REM
REM ============================================================================

SET SERVICE_NAME=CORTEXWatchdog
SET NSSM_PATH=C:\tools\nssm\nssm.exe
SET CORTEX_DIR=%~dp0..
SET PYTHON_EXE=python
SET WATCHDOG_SCRIPT=%CORTEX_DIR%\cortex_watchdog.py

REM Check NSSM exists
IF NOT EXIST "%NSSM_PATH%" (
    echo ERROR: NSSM not found at %NSSM_PATH%
    echo Download from https://nssm.cc/download and place nssm.exe at %NSSM_PATH%
    exit /b 1
)

REM Check running as admin
net session >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: This script must be run as Administrator.
    exit /b 1
)

echo Installing CORTEX Watchdog as Windows service...
echo   Service name: %SERVICE_NAME%
echo   Python:       %PYTHON_EXE%
echo   Script:       %WATCHDOG_SCRIPT%
echo   Working dir:  %CORTEX_DIR%

REM Remove existing service if present
"%NSSM_PATH%" stop %SERVICE_NAME% 2>nul
"%NSSM_PATH%" remove %SERVICE_NAME% confirm 2>nul

REM Install new service
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_EXE%" "%WATCHDOG_SCRIPT%"
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%CORTEX_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "CORTEX Watchdog"
"%NSSM_PATH%" set %SERVICE_NAME% Description "CORTEX AI process monitor — auto-restarts run_ui.py on crash"
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%CORTEX_DIR%\usr\memory\cortex_main\watchdog_service.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%CORTEX_DIR%\usr\memory\cortex_main\watchdog_service_err.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760

REM Start the service
"%NSSM_PATH%" start %SERVICE_NAME%

echo.
echo CORTEX Watchdog service installed and started.
echo To uninstall: nssm remove CORTEXWatchdog confirm
echo To stop:      nssm stop CORTEXWatchdog
echo To check:     nssm status CORTEXWatchdog
