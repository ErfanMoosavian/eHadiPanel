@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [INFO] محیط برنامه هنوز نصب نشده است؛ در حال اجرای نصب خودکار...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)
start "" "venv\Scripts\pythonw.exe" "main.py"
