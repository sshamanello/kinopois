@echo off
REM Kinopois Daily Parser - Windows Task Scheduler Script
REM
REM One-time setup (run as Administrator in PowerShell):
REM   $action = New-ScheduledTaskAction -Execute "E:\code\kinopois\deploy\run-daily.bat"
REM   $trigger = New-ScheduledTaskTrigger -Daily -At "09:00AM"
REM   Register-ScheduledTask -TaskName "kinopois-daily" -Action $action -Trigger $trigger -RunLevel Highest

REM Go to project root (parent of deploy/)
cd /d "%~dp0.."

echo [%date% %time%] Starting kinopois... >> data\kinopois-cron.log 2>&1

call .venv\Scripts\activate.bat
kinopois run-pins --limit 200 >> data\kinopois-cron.log 2>&1

echo [%date% %time%] Done >> data\kinopois-cron.log 2>&1
