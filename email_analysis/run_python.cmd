@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto python
set "EMAIL_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%EMAIL_PYTHON%" goto bundled
echo Install Python 3.11 or newer from python.org with Tcl/Tk and the Python launcher.
exit /b 1
:venv
".venv\Scripts\python.exe" %*
exit /b %errorlevel%
:launcher
py -3 %*
exit /b %errorlevel%
:python
python %*
exit /b %errorlevel%
:bundled
"%EMAIL_PYTHON%" %*
exit /b %errorlevel%
