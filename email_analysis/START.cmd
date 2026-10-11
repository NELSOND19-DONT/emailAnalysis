@echo off
cd /d "%~dp0"
call run_python.cmd app.py
if errorlevel 1 pause
