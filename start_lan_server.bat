@echo off
REM ==============================================================================
REM Thamarayyath Employee Portal -- Windows Batch Launcher
REM Double-click to launch production WSGI server on LAN
REM ==============================================================================

cd /d "%~dp0"
title Thamarayyath Employee Portal - LAN Server

echo ======================================================================
echo   THAMARAYYATH EMPLOYEE PORTAL -- WORKSTATION LAN LAUNCHER
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment not found in .venv\
    pause
    exit /b 1
)

echo [1/2] Checking database migrations...
.venv\Scripts\python.exe manage.py migrate --noinput
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Migration check failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Starting Waitress WSGI Server on 0.0.0.0:8000 ...
echo Local access: http://127.0.0.1:8000/
echo Network access: Accessible from other PCs via this workstation's LAN IP.
echo.
echo Press Ctrl+C in this window to stop the server.
echo ======================================================================

.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 --threads=8 --channel-timeout=120 config.wsgi:application

pause
