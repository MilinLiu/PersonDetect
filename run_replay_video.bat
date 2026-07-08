@echo off
setlocal
cd /d "%~dp0"
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%CD%\.tmp"
set "YOLO_CONFIG_DIR=%CD%\.tmp"
set "MPLCONFIGDIR=%CD%\.tmp\matplotlib"

if "%~1"=="" (
  echo Usage:
  echo   run_replay_video.bat "C:\path\to\video.mp4"
  echo.
  echo You can also drag a video file onto this bat file.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" tools\replay_video.py "%~1" --real-time --output "replay_outputs\result.mp4"
pause
