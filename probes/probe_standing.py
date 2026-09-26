#!/usr/bin/env python3
"""probe_standing — 常驻孤儿检查器收编闸（TestClient 离线可跑）。

R2547：web/check_*.py 家族里 check_warm_voice / check_xingzuo /
check_async_ai 都是 TestClient 进程内跑（零外部服务依赖），
此前不在任何闸门——与 baseline_voice 同型「孤儿检查器」。
check_poster / check_plain_first 需浏览器，归 ui_smoke 不收。

用法即纪律：这些脚本判据漂移=真回归，不许靠改脚本过闸。
"""
import subprocess
import sys

CHECKS = [
    ("check_warm_voice", "web/check_warm_voice.py", 90),
    ("check_xingzuo", "web/check_xingzuo.py", 90),
    ("check_async_ai", "web/check_async_ai.py", 150),
]

fails = []
for name, script, tmo in CHECKS:
    try:
        r = subprocess.run([sys.executable, script],
                           capture_output=True, text=True, timeout=tmo)
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        ok = r.returncode == 0 and "PASS" in (r.stdout or "")
        print(("PASS " if ok else "FAIL ") + name
              + ("  " + tail[-1][:110] if tail else ""))
        if not ok:
            fails.append(name)
    except subprocess.TimeoutExpired:
        print(f"FAIL {name}  timeout>{tmo}s")
        fails.append(name)

print(f"\n{len(CHECKS)-len(fails)}/{len(CHECKS)} standing checks PASS")
sys.exit(1 if fails else 0)
