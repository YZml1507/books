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
# R230c（R17-P3-1）：POSIX 下 .venv/bin/python——此前固定 Windows 布局，
# POSIX 上 venv 明明存在却报「venv python 不存在」。
PY = (os.path.join(ROOT, ".venv", "Scripts", "python.exe")
      if os.name == "nt"
      else os.path.join(ROOT, ".venv", "bin", "python"))
PORT = 8123
URL = f"http://127.0.0.1:{PORT}"
# R2349w（R93-P1-2）：CREATE_NO_WINDOW 是 Windows 专属 flag——POSIX 下
# subprocess.run 直接 ValueError 被 _run 吞掉，连接监控全盲、
# NEVER_SEEN_GRACE 会杀掉正在服务的服务器。POSIX 归 0。
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# R2349w（R93-P2-10）：60s 太短——浏览器 keep-alive 池空闲回收 socket
# 时 ESTABLISHED 清零会误杀在线服务。放宽到 300s。
SHUTDOWN_GRACE = 300         # 浏览器退出后，无连接持续多久（秒）判定关闭
NEVER_SEEN_GRACE = 600       # R229x：启动后始终无任何连接的兜底关服时长
POLL_INTERVAL = 5            # 轮询间隔（秒）
LOG = os.path.join(ROOT, "logs", "web_launcher.log")


def log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        # R229x：监控循环浏览器在线时每 5s 写一行（≈43KB/h）——
        # 超 256KB 截尾留 64KB，与 paipan_history._log 同规。
        if os.path.exists(LOG) and os.path.getsize(LOG) > 256 * 1024:
            with open(LOG, "rb") as rf:
                rf.seek(-64 * 1024, os.SEEK_END)
                tail = rf.read()
            with open(LOG, "wb") as wf:
                wf.write(tail)
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


def _local_port(parts: list[str]) -> str:
    """netstat -ano 行的本地地址端口（精确比对——`:8123` 子串会误伤
    :81230–81239 的监听者）。"""
    if len(parts) < 2:
        return ""
    return parts[1].rsplit(":", 1)[-1]


def kill_stale() -> None:
    """杀掉占用 PORT 的旧进程（含上次残留的 uvicorn）。

    R230c（R17-P1-9）：taskkill 前校验映像名——不验属主会把碰巧监听 8123
    的无关服务强杀。非 Windows（无 netstat/taskkill）时空转（同前，属
    既有平台假设）。"""
    for line in _run(["netstat", "-ano"]).splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and "LISTENING" in line and \
                _local_port(parts) == str(PORT):
            pid = parts[-1]
            if pid.isdigit():
                img = _run(["tasklist", "/fi", f"PID eq {pid}",
                            "/fo", "csv"]).lower()
                if "python" in img or "uvicorn" in img:
                    _run(["taskkill", "/f", "/pid", pid])
                    log(f"killed stale pid {pid} on :{PORT}")
                else:
                    log(f":{PORT} 被非 python 进程 pid={pid} 占用，不杀——"
                        f"起服务会失败，请换端口或手动释放")


def port_ready(timeout: int = 30) -> bool:
    """等我们的服务就绪。

    R230c（R17-P1-9）：此前只测 TCP 可连——外来进程占着 8123 时 connect
    即 True，浏览器被指向别人的服务。加身份探针：GET / 必须回我们的
    index（含本应用特征标记）。"""
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1) as s:
                s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
                head = s.recv(65536)
                # 本应用首页/健康端点特征：HTML 里带 小满/古籍 标记或
                # manifest 链——拿不到就继续等（服务可能还在起）。
                if (b"\xe5\xb0\x8f\xe6\bb\xa1" in head   # 小满
                        or b"manifest.json" in head
                        or b"books" in head.lower()):
                    return True
                log(f":{PORT} 有监听但响应不像本应用，继续等")
                time.sleep(1)
        except OSError:
            time.sleep(1)
    return False


def active_conns() -> set[str]:
    """与 PORT 建立过/保持着 ESTABLISHED 连接的进程 PID 集合（不含监听者）。
    只数本地地址端口==PORT 的行——对端恰好 :8123 的外网连接不算。"""
    pids: set[str] = set()
    for line in _run(["netstat", "-ano"]).splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and "ESTABLISHED" in line and \
                _local_port(parts) == str(PORT):
            if parts[-1].isdigit():
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
    另两条退出路径（R2349s/R85-P2-15 补登记）：saw_any——非白名单客户端
    连过又断开也关服（R229x）；NEVER_SEEN_GRACE=600——从未有连接时的兜底
    超时。

    server 兼容两种类型：
      * subprocess.Popen（非 frozen 模式：子进程 uvicorn）
      * uvicorn.Server（frozen/PyInstaller 模式：in-process 线程）
    两种类型都通过 alive_fn/stop_fn 抽象，避免在监控循环里做类型分支。
    """
    seen_browsers: set[str] = set()
    saw_any = False                 # R229x：任何连接都算用户在场——
                                    # 非白名单浏览器（Vivaldi/Arc 等）连上
                                    # 也计入，断开 GRACE 秒即关服（原实现
                                    # 名单外恒空 → uvicorn 常驻不回收）。
    last_active = time.time()
    started = last_active
    while True:
        if not alive_fn(server):
            log("server exited; launcher exit")
            return 0
        conns = active_conns()
        browsers = {p for p in conns if _is_browser_pid(p)}
        if conns:
            saw_any = True
            last_active = time.time()
            if browsers:
                seen_browsers |= browsers
                log(f"browser conns={sorted(browsers)} seen={sorted(seen_browsers)}")
        else:
            idle = time.time() - last_active
            if seen_browsers:
                alive = [p for p in seen_browsers if pid_alive(p)]
                log(f"no browser conns; browsers_alive={alive} idle={idle:.0f}s")
                if not alive and idle >= SHUTDOWN_GRACE:
                    log(f"browser closed (no conns {SHUTDOWN_GRACE}s, seen={seen_browsers})")
                    break
            elif saw_any and idle >= SHUTDOWN_GRACE:
                # 有连接但都不是白名单浏览器——用户大概率已关窗口离开
                log(f"non-whitelist client gone {SHUTDOWN_GRACE}s; shutting down")
                break
            elif not saw_any and time.time() - started >= NEVER_SEEN_GRACE:
                # 浏览器从未连上（自动打开失败/双击闪退）——别空挂到下次双击
                log(f"no client ever connected in {NEVER_SEEN_GRACE}s; shutting down")
                break
        time.sleep(POLL_INTERVAL)
    stop_fn(server)
    return 0


def main() -> int:
    # R2349w（R93-P1-2）：连接监控/kill_stale/pid_alive 全套依赖
    # netstat/tasklist/taskkill——POSIX 下拿不到连接数据，浏览器监控
    # 全盲，最终靠兜底误杀活服务。本入口是 Windows 桌面专用，POSIX
    # 直接明说并指向正确启动方式，别假装能跑。
    if os.name != "nt":
        log("web_launcher 是 Windows 桌面入口——POSIX 请直接跑："
            "uvicorn web.app:app --host 127.0.0.1 --port 8123")
        print("web_launcher 是 Windows 桌面入口。POSIX 请直接跑：\n"
              "  uvicorn web.app:app --host 127.0.0.1 --port 8123")
        return 2
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

    # R229x：失败路径全部落日志——pythonw 下双击零反馈，log 是唯一的
    # 排查窗口（原来 .venv 缺失/Popen 抛错时只留一行 start）。
    if not os.path.exists(PY):
        log(f"venv python 不存在：{PY}（请先按 README 建 .venv 装依赖）")
        return 1
    try:
        server = subprocess.Popen(
            [PY, "-m", "uvicorn", "web.app:app",
             "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT,
            # creationflags 仅 Windows 支持；POSIX 传 0（本脚本目标是
            # Windows 桌面，但保护一下免得开发机上跑直接崩）
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        log(f"uvicorn 启动失败：{type(exc).__name__}: {exc}")
        return 1
    log(f"uvicorn pid={server.pid}")

    if not port_ready():
        log(f"server failed to become ready on :{PORT} in 30s; "
            f"check venv/deps, shutting down")
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
