@echo off
setlocal
cd /d "%~dp0"
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%CD%\.tmp"
set "YOLO_CONFIG_DIR=%CD%\.tmp"
set "MPLCONFIGDIR=%CD%\.tmp\matplotlib"
if exist "configs\home_gate.local.yaml" (
  set "MONITOR_CONFIG=configs\home_gate.local.yaml"
)
".venv\Scripts\python.exe" persondetectandfield.py
