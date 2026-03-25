@echo off
echo.
echo ========================================
echo  CORTEX Restart
echo ========================================
echo.
echo Stopping existing CORTEX process...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000"') do (
    taskkill /f /pid %%a 2>nul
)
timeout /t 2 /nobreak >nul
echo.
echo Starting CORTEX...
cd /d C:\Users\Admin\CORTEX
start "CORTEX" cmd /k "python run_ui.py"
echo.
echo CORTEX starting at http://localhost:5000
echo (Select 'cortex' profile in Settings -> Agent)
echo.
