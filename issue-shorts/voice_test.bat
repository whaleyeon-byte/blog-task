@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m shorts.voice_test
echo.
pause
