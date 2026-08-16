@echo off
rem Bazi web UI launcher — silent start (no console popups).
rem pythonw runs web_launcher.py headlessly: it kills stale instances,
rem starts uvicorn, opens the browser, and auto-stops when the browser closes.
rem The .bat itself exits immediately so no window lingers.
rem ROOT is this script's own directory (portable; was a hardcoded user path).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
start "" "%PYW%" "%ROOT%\web_launcher.py"
exit /b 0
