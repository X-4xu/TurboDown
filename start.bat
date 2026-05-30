@echo off
chcp 65001 >nul 2>nul
title TurboDown - Download Manager
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║                                                          ║
echo  ║     ⬇  TurboDown - Download Manager v3.0.0              ║
echo  ║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━             ║
echo  ║     Ultra-Fast Multi-Threaded Download Accelerator       ║
echo  ║                                                          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM Navigate to script directory (works from any location)
cd /d "%~dp0"

REM ── Check Python ──────────────────────────────────────────
echo  [1/3] Checking Python installation...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Please install Python 3.10+ from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [OK] Found %%v

REM ── Check Dependencies ────────────────────────────────────
echo  [2/3] Checking dependencies...
python -c "import customtkinter" >nul 2>nul
if %errorlevel% neq 0 (
    echo  [INFO] Installing required packages (first time only)...
    echo.
    pip install -r requirements.txt
    echo.
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to install dependencies.
        echo  Try running: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo  [OK] All packages installed successfully.
) else (
    echo  [OK] All dependencies are ready.
)

REM ── Launch Application ────────────────────────────────────
echo  [3/3] Launching TurboDown...
echo.
echo  ┌──────────────────────────────────────────────────────┐
echo  │  TurboDown is starting...                            │
echo  │  The app will appear in a moment.                    │
echo  │  This window will close automatically.               │
echo  │                                                      │
echo  │  Tip: TurboDown minimizes to the system tray.        │
echo  │  Look for the icon near the clock.                   │
echo  └──────────────────────────────────────────────────────┘
echo.

REM Launch without console window (pythonw), fallback to python
start "" pythonw "%~dp0app.py" 2>nul
if %errorlevel% neq 0 (
    start "" python "%~dp0app.py"
)

REM Auto-close after 3 seconds
timeout /t 3 /nobreak >nul
exit
