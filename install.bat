@echo off
setlocal EnableExtensions
title FingerCam - Install
cd /d "%~dp0"

echo ============================================
echo   FingerCam - Installation
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 goto :try_python

py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3.12"
    goto :have_python
)

py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3.11"
    goto :have_python
)

py -3.10 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3.10"
    goto :have_python
)

py -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY=py"
    goto :have_python
)

:try_python
python -c "import sys" >nul 2>nul
if errorlevel 1 goto :no_python
set "PY=python"

:have_python
%PY% -c "import sys; print('Using Python', sys.version.split()[0])"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [1/3] Creating a private environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :venv_failed
) else (
    echo.
    echo [1/3] Reusing the existing .venv ...
)

echo.
echo [2/3] Updating pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo [3/3] Installing dependencies (this can take a few minutes) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
echo ============================================
echo   Installation finished successfully!
echo.
echo   Double-click run.bat to start FingerCam.
echo ============================================
echo.
pause
exit /b 0

:no_python
echo.
echo [ERROR] Python was not found.
echo.
echo Install Python 3.12 (64-bit) from:
echo   https://www.python.org/downloads/windows/
echo During setup, tick "Add python.exe to PATH".
echo Then run install.bat again.
echo.
pause
exit /b 1

:venv_failed
echo.
echo [ERROR] Could not create the .venv folder.
echo Make sure you have write permission in this folder.
echo.
pause
exit /b 1

:pip_failed
echo.
echo [ERROR] Could not install the Python packages.
echo.
echo Try these steps:
echo   1. Install Python 3.12 (64-bit) from python.org.
echo   2. Delete the .venv folder.
echo   3. Run install.bat again.
echo   4. If you are behind a proxy, configure pip first.
echo.
pause
exit /b 1
