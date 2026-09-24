@echo off
rem Bazi web UI launcher — silent start (no console popups).
rem pythonw runs web_launcher.py headlessly: it kills stale instances,
rem starts uvicorn, opens the browser, and auto-stops when the browser closes.
rem The .bat itself exits immediately so no window lingers.
rem ROOT is this script's own directory (portable; was a hardcoded user path).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
rem R2349w（R93-P2-8）：.venv 缺失时原来只有一个 OS 弹框，log 里
rem 什么都没有——先校验再静默启动，缺了就明说建环境。
if not exist "%PYW%" (
  echo 没找到 .venv 环境——请先按 README 用国内镜像安装依赖（python -m venv .venv ^&^& pip install -r requirements-ci.txt playwright==1.63.0）
  pause
  exit /b 1
)
start "" "%PYW%" "%ROOT%\web_launcher.py"
exit /b 0
