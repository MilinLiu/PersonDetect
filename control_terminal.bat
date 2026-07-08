@echo off
cd /d "%~dp0"
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%CD%\.tmp"
set "YOLO_CONFIG_DIR=%CD%\.tmp"
set "MPLCONFIGDIR=%CD%\.tmp\matplotlib"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\control_terminal.py" %*
) else (
  python "tools\control_terminal.py" %*
)
