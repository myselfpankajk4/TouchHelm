@echo off
title TouchHelm - Windows Desktop Controller
cd /d "%~dp0"
set "TOUCHHELM_PYTHON=%~dp0.venv\Scripts\python.exe"
rem Managed worktrees share the workspace runtime; all source stays in this folder.
if not exist "%TOUCHHELM_PYTHON%" if exist "%~dp0..\..\.venv\Scripts\python.exe" set "TOUCHHELM_PYTHON=%~dp0..\..\.venv\Scripts\python.exe"

echo ===================================================
echo             TOUCHHELM WINDOWS CONTROLLER
echo ===================================================

if not exist "%TOUCHHELM_PYTHON%" (
    echo [INFO] Setting up virtual environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
    echo [INFO] Installing dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)

"%TOUCHHELM_PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The workspace Python runtime is unavailable. Repair .venv and try again.
    exit /b 1
)
"%TOUCHHELM_PYTHON%" -c "import webview, cryptography" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing desktop dependencies...
    "%TOUCHHELM_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 exit /b 1
)

echo [INFO] Launching TouchHelm Host...
"%TOUCHHELM_PYTHON%" "%~dp0main.py" %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo TouchHelm exited with error code %ERRORLEVEL%.
    pause
)
