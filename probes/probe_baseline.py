#!/usr/bin/env python3
"""probe_baseline — 把 baseline_voice 逐字节基线纳入常驻回归闸门。

R2545：R2529-2544 的解读层改进让 pro 输出漂移 16 处，积累多轮无人
发现——baseline_voice.py 是离线脚本不在 selftest/探针族里。
本探针只做一件事：跑 baseline_voice --check 并透传结果。
**有意的解读文案变更**先跑 `web/baseline_voice.py --freeze` 再提交。
"""
import subprocess
import sys

r = subprocess.run(
    [sys.executable, "web/baseline_voice.py"],
    capture_output=True, text=True, timeout=180)
out = (r.stdout or "") + (r.stderr or "")
ok = r.returncode == 0 and "PASS" in out
print(out.strip().splitlines()[-1] if out.strip() else "(no output)")
print("PASS probe_baseline" if ok else "FAIL probe_baseline")
sys.exit(0 if ok else 1)
