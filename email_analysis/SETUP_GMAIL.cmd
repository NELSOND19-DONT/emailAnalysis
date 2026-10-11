@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call run_python.cmd -m venv .venv
  if errorlevel 1 goto failed
)
call run_python.cmd -m pip install -r requirements-gmail.txt
if errorlevel 1 goto failed
echo Gmail dependencies installed. Save your OAuth Desktop client JSON in private\gmail-client.json, then run START.cmd.
pause
exit /b 0
:failed
echo Setup failed. Check the error above.
pause
exit /b 1
