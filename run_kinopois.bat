@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
echo [kinopois] Creating virtual environment...
py -m venv .venv
)

echo [kinopois] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [kinopois] Starting...
".venv\Scripts\python.exe" -m kinopois.cli %*
if errorlevel 1 goto :error

echo.
echo [kinopois] Done successfully.
pause
exit /b 0

:error
echo.
echo [kinopois] ERROR! Exit code: %errorlevel%
echo Press any key to close...
pause
exit /b %errorlevel%
