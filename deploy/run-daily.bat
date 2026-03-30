@echo off
REM Kinopois Daily Parser - Windows Task Scheduler Script
REM Schedule: Every day at 09:00
REM Run: schtasks /create /tn "Kinopois Daily" /tr "path\to\run_kinopois.bat" /sc daily /st 09:00

cd /d "%~dp0"

echo [%date% %time%] Starting kinopois... >> data\kinopois-cron.log

REM Run with Docker
docker compose run --rm kinopois pins --limit 200 --sync-sheets >> data\kinopois-cron.log 2>&1

echo [%date% %time%] Done >> data\kinopois-cron.log
