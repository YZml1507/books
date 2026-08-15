"""web_launcher.py — 桌面入口：无弹窗启动 + 自动开浏览器 + 浏览器关闭后自动关服务。

用户需求（2026-08-15）：
  1. 点桌面图标不弹任何黑窗口/控制台弹窗；
  2. 启动后自动打开浏览器；
  3. 关闭浏览器后，服务自动关闭（不用手动去杀进程）。

实现（纯标准库，零新依赖）：
  * 由 pythonw.exe 运行本脚本（无控制台窗口）；子进程 uvicorn 用
    CREATE_NO_WINDOW 启动，同样不弹窗。
  * 启动前杀占用 8123 的旧实例（uvicorn 无热重载，避免旧代码残留）。
  * 端口就绪后用 webbrowser.open 打开浏览器。
  * 监控：记录曾与 8123 建立连接的浏览器进程 PID；当浏览器进程全部
    退出且端口无活跃连接持续 SHUTDOWN_GRACE 秒，判定"浏览器已关闭"，
    优雅终止 uvicorn 后退出。

日志写入 logs/web_launcher.log（pythonw 无 stdout，便于排查）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))   # 本文件在项目根，一层即可
# PyInstaller 单文件模式：exe 同目录才是项目根（data/、logs/ 都在那里）
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PORT = 8123
URL = f"http://127.0.0.1:{PORT}"
CREATE_NO_WINDOW = 0x08000000
SHUTDOWN_GRACE = 60          # 浏览器退出后，无连接持续多久（秒）判定关闭
POLL_INTERVAL = 5            # 轮询间隔（秒）
LOG = os.path.join(ROOT, "logs", "web_launcher.log")


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _run(args: list[str]) -> str:
    """无窗口运行命令，返回 stdout（GBK 解码容错）。"""
    try:
        out = subprocess.run(args, capture_output=True, timeout=15,
                             creationflags=CREATE_NO_WINDOW)
        return out.stdout.decode("gbk", "replace")
    except Exception:
        return ""


def kill_stale() -> None:
    """杀掉占用 PORT 的旧进程（含上次残留的 uvicorn）。"""
    for line in _run(["netstat", "-ano"]).splitlines():
        if f":{PORT}" in line and "LISTENING" in line:
            pid = line.strip().split()[-1]
            if pid.isdigit():
                _run(["taskkill", "/f", "/pid", pid])
                log(f"killed stale pid {pid} on :{PORT}")


def port_ready(timeout: int = 30) -> bool:
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def active_conns() -> set[str]:
    """与 PORT 建立过/保持着 ESTABLISHED 连接的进程 PID 集合（不含监听者）。"""
    pids: set[str] = set()
    for line in _run(["netstat", "-ano"]).splitlines():
        if f":{PORT}" in line and "ESTABLISHED" in line:
            parts = line.strip().split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
    return pids


def pid_alive(pid: str) -> bool:
    out = _run(["tasklist", "/FI", f"PID eq {pid}"])
    return pid in out


# 常见浏览器进程名（用于识别"浏览器还开着"→ 不关服务）
BROWSER_NAMES = {"chrome", "msedge", "firefox", "iexplore", "opera",
                 "brave", "360se", "qqbrowser", "sogouexplorer"}


def _pid_image(pid: str) -> str:
    """进程映像名（小写，去 .exe）。查不到返回 ''。"""
    for line in _run(["tasklist", "/FI", f"PID eq {pid}"]).splitlines():
        parts = line.split()
        if parts and parts[0].lower().endswith(".exe") and parts[1] == pid:
            return parts[0].lower()[:-4]
    return ""


def _is_browser_pid(pid: str) -> bool:
    img = _pid_image(pid)
    return img in BROWSER_NAMES


def _server_alive(server) -> bool:
    """server 是否还在运行。兼容 subprocess.Popen（.poll()）和 uvicorn.Server（.should_exit）。"""
    if hasattr(server, "poll"):
        return server.poll() is None
    return not getattr(server, "should_exit", False)


def _server_stop(server) -> None:
    """优雅停止 server。兼容 subprocess.Popen（.terminate/.wait/.kill）和 uvicorn.Server（.should_exit=True）。"""
    if hasattr(server, "should_exit"):
        server.should_exit = True
        return
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()


def _monitor(server, alive_fn=_server_alive, stop_fn=_server_stop) -> int:
    """监控循环：浏览器关闭判定（可单测——server/alive_fn/stop_fn/active_conns/pid_alive 可注入）。

    规则：曾见过浏览器连接（PID）。只有当「所有曾连接过的浏览器进程都已
    退出」且「无浏览器连接持续 GRACE 秒」才判定浏览器已关闭，随后终止
    server 并返回 0。非浏览器连接（健康检查/探测脚本）不参与判定、不重置
    计时——否则一个残留探测连接会让服务永不关闭。

    server 兼容两种类型：
      * subprocess.Popen（非 frozen 模式：子进程 uvicorn）
      * uvicorn.Server（frozen/PyInstaller 模式：in-process 线程）
    两种类型都通过 alive_fn/stop_fn 抽象，避免在监控循环里做类型分支。
    """
    seen_browsers: set[str] = set()
    last_active = time.time()
    while True:
        if not alive_fn(server):
            log("server exited; launcher exit")
            return 0
        conns = active_conns()
        browsers = {p for p in conns if _is_browser_pid(p)}
        if browsers:
            seen_browsers |= browsers
            last_active = time.time()
            log(f"browser conns={sorted(browsers)} seen={sorted(seen_browsers)}")
        elif seen_browsers:
            alive = [p for p in seen_browsers if pid_alive(p)]
            idle = time.time() - last_active
            log(f"no browser conns; browsers_alive={alive} idle={idle:.0f}s")
            if not alive and idle >= SHUTDOWN_GRACE:
                log(f"browser closed (no conns {SHUTDOWN_GRACE}s, seen={seen_browsers})")
                break
        time.sleep(POLL_INTERVAL)
    stop_fn(server)
    return 0


def main() -> int:
    log("=== launcher start ===")
    kill_stale()
    time.sleep(1)

    frozen = getattr(sys, "frozen", False)
    if frozen:
        # PyInstaller 单文件模式：没有独立 python.exe，用线程 in-process 跑 uvicorn。
        import threading
        import uvicorn
        config = uvicorn.Config(
            "web.app:app", host="127.0.0.1", port=PORT,
            log_level="error", access_log=False,
        )
        server_obj = uvicorn.Server(config)
        t = threading.Thread(target=server_obj.run, daemon=True)
        t.start()
        log("uvicorn in-process thread started")
        # 等端口就绪
        if not port_ready():
            log("server failed to become ready; shutting down")
            server_obj.should_exit = True
            return 1
        log("port ready; opening browser")
        try:
            webbrowser.open(URL)
        except Exception as exc:
            log(f"webbrowser.open failed: {exc}")
        # frozen 模式同样走 _monitor：监控浏览器连接，关闭后设 should_exit 退出
        return _monitor(server_obj)

    server = subprocess.Popen(
        [PY, "-m", "uvicorn", "web.app:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT,
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log(f"uvicorn pid={server.pid}")

    if not port_ready():
        log("server failed to become ready; shutting down")
        server.terminate()
        return 1
    log("port ready; opening browser")
    try:
        webbrowser.open(URL)
    except Exception as exc:  # noqa: BLE001 — 浏览器打开失败不影响服务可用
        log(f"webbrowser.open failed: {exc}")

    return _monitor(server)


if __name__ == "__main__":
    raise SystemExit(main())
