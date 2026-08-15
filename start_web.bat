@echo off
rem Bazi web UI launcher — silent start (no console popups).
rem pythonw runs web_launcher.py headlessly: it kills stale instances,
rem starts uvicorn, opens the browser, and auto-stops when the browser closes.
rem The .bat itself exits immediately so no window lingers.
set "ROOT=C:\Users\Lenovo\Desktop\projects\books"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
start "" "%PYW%" "%ROOT%\web_launcher.py"
exit /b 0
