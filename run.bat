@echo off
title TouchHelm - Windows Desktop Controller
cd /d "%~dp0"

echo ===================================================
echo             TOUCHHELM WINDOWS CONTROLLER
echo ===================================================

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Setting up virtual environment...
    python -m venv .venv
    echo [INFO] Installing dependencies...
    .venv\Scripts\pip.exe install -r requirements.txt
)

echo [INFO] Launching TouchHelm Host...
.venv\Scripts\python.exe main.py %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo TouchHelm exited with error code %ERRORLEVEL%.
    pause
)
