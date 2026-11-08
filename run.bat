@echo off
setlocal EnableExtensions
title FingerCam
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ============================================
    echo   FingerCam is not installed yet.
    echo   Please double-click install.bat first.
    echo ============================================
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app.py %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo FingerCam stopped with exit code %CODE%.
    pause
)
exit /b %CODE%
