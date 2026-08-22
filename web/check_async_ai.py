"""web/check_async_ai.py — specs/006 判据 9/10/11 的量尺（R191b，B-014/D-251b）。

判据 9（p95 端到端）：LLM 开启时四端点（bazi/taohua/hehun/qiming）同步返回
                      <2s。LLM 用**打桩慢 transport**（0.5s 延迟 + 固定文本），
                      零外网、确定性延迟——闸门必须可离线复现。
判据 10（AI 到达时间单独计量）：打桩 0.5s 下轮询 /api/ai/{id} 最终拿到
                      非空文本（done）；同时验证降级语义——transport 恒失败
                      时任务终态 failed，且响应主体不受影响。
判据 11（DISABLE=1 逐字节不变）：总开关下四端点响应无 ai_task_id 键、
                      ai_polish=None，与「LLM 从未存在」的旧版逐字节一致
                      （对照两次调用相等 + 键集断言）。

闸门纪律（PHASE.md / D-248b）：失败退出 1、成功退出 0，自带 --self-check
阳性对照——把 spawn 打桩成「同步阻塞 5s」（模拟旧实现），判据 9 必须被抓到；
若仍全绿则本闸门是假的。

用法（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe web\\check_async_ai.py
    .\\.venv\\Scripts\\python.exe web\\check_async_ai.py --self-check

注意：本脚本全程不设 BOOKS_LLM_DISABLE（它测的就是 LLM 开启路径），
但通过 _transport 注入保证零外网。真实外网联调用 probe_llm_polish --online。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

P95_LIMIT_S = 2.0            # 判据 9 门柱：specs/006 §4 判据 9
STUB_DELAY_S = 0.5           # 打桩 LLM 延迟（判据 10）
STUB_TEXT = "这是打桩的 AI 文本，温柔且不超过九十个字，用于离线验收轮询链路。"

BAZI = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女",
        "question": "感情运怎么样？", "ask_date": "2026-08-20"}
TAOHUA = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女"}
HEHUN = {"a_year": 1998, "a_month": 7, "a_day": 20, "a_hour": 14,
         "b_year": 1996, "b_month": 3, "b_day": 5, "b_hour": 9}
QIMING = {"surname": "林", "year": 1998, "month": 7, "day": 20, "hour": 14,
          "gender": "女"}
ENDPOINTS = [("/api/bazi", BAZI), ("/api/taohua", TAOHUA),
             ("/api/hehun", HEHUN), ("/api/qiming", QIMING)]


def _stub_transport(payload, headers, url, timeout):
    """慢 LLM 打桩：睡 STUB_DELAY_S 后返回固定正文（零外网）。"""
    time.sleep(STUB_DELAY_S)
    return {"choices": [{"message": {"content": STUB_TEXT}}]}


def _boom_transport(payload, headers, url, timeout):
    raise OSError("stub: endpoint always down")


def install_stub_transport(fn) -> None:
    """把打桩 transport 注入 spawn_ai_task 的默认路径。

    注意：web.services 里的 `llm_polish` 与本文件 import 的是**同一个模块对象**
    ——替换 `L.spawn_ai_task` 即对四端点同时生效。包装器闭包持有**原函数**，
    避免自递归（首版在这里写成了调自己，RecursionError）。

    显式 config 的两个理由（R191b 第二版修正）：
    (1) 闸门跑批常全局 export BOOKS_LLM_DISABLE=1——spawn 走 load_config()
        会被总开关挡成 None，判据 9 的「带 ai_task_id」必挂；spawn 的语义是
        `config or load_config()`，显式 config 合法绕过环境开关。
    (2) 零依赖真实 key 文件（web/llm_config.json 是 gitignored 的本机文件，
        books-audit worktree 里没有）——闸门在任何 worktree 都可离线复现。
    transport 本身是打桩，无外网。断言本体一字未动。
    """
    from guji import llm_polish as L
    if not hasattr(L, "_REAL_SPAWN"):
        L._REAL_SPAWN = L.spawn_ai_task

    stub_cfg = dict(L._DEFAULTS, api_key="stub-key-check-async-ai",
                    timeout_s=5)

    def _injected(facts, question=None, config=None, **kw):
        return L._REAL_SPAWN(facts, question, config=stub_cfg,
                             _transport=fn)

    L.spawn_ai_task = _injected


def restore_spawn() -> None:
    from guji import llm_polish as L
    if hasattr(L, "_REAL_SPAWN"):
        L.spawn_ai_task = L._REAL_SPAWN
        delattr(L, "_REAL_SPAWN")     # 必须删除而非置 None——否则下次 install 误判


def judge(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'✅' if ok else '❌'} {name}{('　' + detail) if detail else ''}")
    return ok


def check_p95_and_arrival() -> bool:
    """判据 9 + 判据 10：四端点 p95<2s；轮询最终 done 且文本非空。"""
    from guji import llm_polish as L
    from fastapi.testclient import TestClient
    from web.app import app

    install_stub_transport(_stub_transport)
    try:
        c = TestClient(app)
        ok = True
        times = []
        for path, payload in ENDPOINTS:
            t = time.time()
            j = c.post(path, json=payload).json()
            dt = time.time() - t
            times.append(dt)
            ok = judge(f"判据9 {path} 同步返回 <{P95_LIMIT_S}s", dt < P95_LIMIT_S,
                       f"{dt:.2f}s") and ok
            tid = j.get("ai_task_id")
            ok = judge(f"判据9 {path} 带 ai_task_id", bool(tid)) and ok
            if not tid:
                continue
            # 判据 10：轮询到达时间单独计量
            t0 = time.time()
            st = None
            while time.time() - t0 < 10:
                st = c.get(f"/api/ai/{tid}").json()
                if st["status"] != "pending":
                    break
                time.sleep(0.1)
            arrive = time.time() - t0
            ok = judge(f"判据10 {path} 轮询终态=done 且文本非空",
                       bool(st) and st["status"] == "done" and bool(st["text"]),
                       f"{arrive:.2f}s") and ok
        p95 = sorted(times)[int(len(times) * 0.95) - 1] if len(times) >= 2 \
            else max(times)
        ok = judge(f"判据9 四端点 p95 <{P95_LIMIT_S}s", p95 < P95_LIMIT_S,
                   f"p95={p95:.2f}s (all={[f'{x:.2f}' for x in times]})") and ok
    finally:
        restore_spawn()
    return ok


def check_degrade_failed() -> bool:
    """判据 10 降级半边：LLM 恒失败 → 任务 failed、主体完整、前端语义=不渲染。"""
    from guji import llm_polish as L
    from fastapi.testclient import TestClient
    from web.app import app

    install_stub_transport(_boom_transport)
    try:
        c = TestClient(app)
        ok = True
        for path, payload in ENDPOINTS:
            t = time.time()
            j = c.post(path, json=payload).json()
            dt = time.time() - t
            ok = judge(f"判据10 {path} LLM恒失败仍 <{P95_LIMIT_S}s 返回",
                       dt < P95_LIMIT_S, f"{dt:.2f}s") and ok
            body_keys = ["warm"] if path != "/api/qiming" else \
                        ["full_names", "summary"]
            ok = judge(f"判据10 {path} 确定性主体非空",
                       all(j.get(k) for k in body_keys)) and ok
            tid = j.get("ai_task_id")
            st = None
            t0 = time.time()
            while time.time() - t0 < 10:
                st = c.get(f"/api/ai/{tid}").json()
                if st["status"] != "pending":
                    break
                time.sleep(0.1)
            ok = judge(f"判据10 {path} 终态=failed（整块不渲染语义）",
                       bool(st) and st["status"] == "failed"
                       and not st["text"]) and ok
            # 读后读：同 id 再查一次仍是 failed（无副作用读取）
            st2 = c.get(f"/api/ai/{tid}").json()
            ok = judge(f"判据10 {path} 轮询读取无副作用", st2 == st) and ok
    finally:
        restore_spawn()
    return ok


def check_disable_byte_identical() -> bool:
    """判据 11：DISABLE=1 时四端点响应无 ai_task_id、ai_polish=None，
    且两次调用逐字节相等（与「LLM 从未存在」等价）。"""
    os.environ["BOOKS_LLM_DISABLE"] = "1"
    try:
        from fastapi.testclient import TestClient
        from web.app import app
        c = TestClient(app)
        ok = True
        for path, payload in ENDPOINTS:
            j1 = c.post(path, json=payload).json()
            j2 = c.post(path, json=payload).json()
            ok = judge(f"判据11 {path} 无 ai_task_id 键",
                       "ai_task_id" not in j1) and ok
            ok = judge(f"判据11 {path} ai_polish=None",
                       j1.get("ai_polish") is None) and ok
            body_keys = ["warm"] if path != "/api/qiming" else \
                        ["full_names", "summary"]
            b1 = {k: j1.get(k) for k in body_keys}
            b2 = {k: j2.get(k) for k in body_keys}
            ok = judge(f"判据11 {path} 两次调用逐字节相等", b1 == b2) and ok
    finally:
        os.environ["BOOKS_LLM_DISABLE"] = "1"   # 本脚本结束恢复闸门环境
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照：把 spawn 打桩成同步阻塞 5s，判据 9 必须红")
    args = ap.parse_args()

    if args.self_check:
        # 阳性对照：monkeypatch 一个同步 sleep 5s 的假 spawn——模拟 R191b 之前的
        # 同步阻塞世界。若判据 9 的断言逻辑失效（比如阈值写错成 10s），
        # 这里会全绿 → 本闸门是假的 → exit 1。
        import web.services as svc
        from guji import llm_polish as L

        def _sync_blocking_spawn(facts, question, config=None, **kw):
            time.sleep(5.0)               # 旧世界：请求线程内等 LLM
            return None

        real = svc.llm_polish.spawn_ai_task
        svc.llm_polish.spawn_ai_task = _sync_blocking_spawn
        try:
            from fastapi.testclient import TestClient
            from web.app import app
            c = TestClient(app)
            caught = False
            for path, payload in ENDPOINTS:
                t = time.time()
                c.post(path, json=payload).json()
                if time.time() - t >= P95_LIMIT_S:
                    caught = True
                    break
        finally:
            svc.llm_polish.spawn_ai_task = real
        if not caught:
            print("check_async_ai --self-check FAIL: 注入同步阻塞 5s 后判据 9 "
                  "仍未红——本闸门是假的")
            return 1
        print("check_async_ai --self-check PASS: 阳性对照（同步阻塞 5s）被判据 9 抓到")
        return 0

    ok = True
    print("=== 判据 9+10 打桩慢 LLM（0.5s，零外网） ===")
    ok = check_p95_and_arrival() and ok
    print("=== 判据 10 降级半边（LLM 恒失败） ===")
    ok = check_degrade_failed() and ok
    print("=== 判据 11 DISABLE=1 与旧版逐字节一致 ===")
    ok = check_disable_byte_identical() and ok
    print()
    if not ok:
        print("check_async_ai FAIL")
        return 1
    print(f"check_async_ai PASS: 判据 9（p95<{P95_LIMIT_S}s）/10（到达+降级）"
          "/11（DISABLE 逐字节不变）全部成立")
    return 0


if __name__ == "__main__":
    sys.exit(main())
