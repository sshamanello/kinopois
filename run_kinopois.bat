@echo off
setlocal

REM Run from this script directory
cd /d "%~dp0"

REM Create venv if missing
if not exist ".venv\Scripts\python.exe" (
  echo [kinopois] Creating virtual environment...
  py -m venv .venv
)

REM Install/update dependencies
echo [kinopois] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt

REM Run app (pass all args through)
echo [kinopois] Starting...
".venv\Scripts\python.exe" -m kinopois.cli %*

endlocal
