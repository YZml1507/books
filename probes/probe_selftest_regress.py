"""probe_selftest_regress.py — 断言集只增不减的闸门（审查轨 R120a，D-139a）。

**为什么存在（宪法第二条红线第 2 项）**：「为了让数字变好而放宽任何验收闸门」
是绝对红线。重构是最容易悄悄放宽断言的时机——把一条难通过的 `check(...)`
删掉，自测依然"全绿"，而且行数变化被淹没在几千行 diff 里。

`web/selftest.py` 的输出末尾会列出全部通过的 check 名字。本 probe 把这份
**名字集合**与基线快照比对：

  * 少了任何一个名字 → FAIL（断言被删/改名，必须解释）
  * 只增不减 → PASS，并把新基线写回快照

基线快照存 `probes/selftest_baseline.json`（审查轨独占 probes/，与优化轨
无冲突）。首次运行会创建它。

**这不是"数行数"**：行数会因重构自然变化，名字集合不会。删一条断言必然
少一个名字，改名也会被抓到（旧名消失），两者都需要人为解释。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_selftest_regress.py
退出码：0 = 只增不减；1 = 有断言消失；2 = 拿不到 check 名单（无法判定）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "probes", "selftest_baseline.json")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# `web self-test PASS (138 checks): search, search.layer, ...`
LINE_RE = re.compile(r"web self-test PASS \((\d+) checks\):\s*(.+)")


def run_selftest() -> tuple[int, list[str], str]:
    """跑自测，返回 (声明的 check 数, check 名字列表, 原始末行)。"""
    candidates = [
        [sys.executable, os.path.join(ROOT, "web", "selftest.py")],
        [sys.executable, os.path.join(ROOT, "web", "app.py"), "--selftest"],
    ]
    last = ""
    for cmd in candidates:
        if not os.path.exists(cmd[1]):
            continue
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join(
            [ROOT, os.path.join(ROOT, "src")])
        # R228u：① 强制离线——宿主 env 注入 BOOKS_LLM_API_KEY 时子进程会
        #   往外网真打 LLM（实测 pending 撞上限+整轮挂死）；② 加超时兜底——
        #   subprocess.run 无 timeout 会让一次挂死变成 probe 永久挂死。
        env["BOOKS_LLM_DISABLE"] = "1"
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", cwd=ROOT,
                               env=env, timeout=600)
        except subprocess.TimeoutExpired:
            last = f"{' '.join(cmd)} TIMEOUT(600s)"
            continue
        out = (r.stdout or "") + (r.stderr or "")
        for line in out.split("\n"):
            m = LINE_RE.search(line)
            if m:
                names = [x.strip() for x in m.group(2).split(",") if x.strip()]
                return int(m.group(1)), names, line.strip()
        last = f"{' '.join(cmd)} exit={r.returncode}"
    return -1, [], last


def main() -> int:
    declared, names, raw = run_selftest()
    if declared < 0 or not names:
        print(f"probe_selftest_regress FAIL-ENV: 拿不到 check 名单（{raw}）。"
              f"自测入口或输出格式变了——无法判定断言是否被删，"
              f"按宪法第一条不算通过。")
        return 2

    print(f"自测声明 {declared} 条 check，解析出 {len(names)} 个名字")
    if declared != len(names):
        print(f"⚠ 声明数与名字数不一致（{declared} vs {len(names)}）——"
              f"可能有名字含逗号，判据以名字集合为准")

    cur = set(names)
    if len(cur) != len(names):
        dups = [n for n in names if names.count(n) > 1]
        print(f"⚠ 有重名 check：{sorted(set(dups))}")

    if not os.path.exists(BASELINE):
        json.dump({"checks": sorted(cur)}, open(BASELINE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"首次运行：已建立基线 {os.path.basename(BASELINE)}"
              f"（{len(cur)} 条）。下次运行起即可检测断言被删。")
        return 0

    snap = json.load(open(BASELINE, encoding="utf-8"))
    base = set(snap["checks"])
    # 已审核的改名：{旧名: 新名}。只有审查轨实测确认「新断言不弱于旧断言」
    # 后才准登记（宪法第二条红线第 2 项——改名不得成为放宽的掩护）。
    renames = snap.get("renames", {})
    accounted = {old for old, new in renames.items() if new in cur}
    missing = sorted(base - cur - accounted)
    added = sorted(cur - base)
    if accounted:
        print("已审核改名（旧名消失但有等价或更强的新断言接管）：")
        for old in sorted(accounted):
            print(f"  {old} → {renames[old]}")

    print(f"基线 {len(base)} 条 → 当前 {len(cur)} 条"
          f"（新增 {len(added)}、消失 {len(missing)}）")
    if added:
        print(f"\n新增断言（好事，自动纳入基线）：\n  {', '.join(added)}")
    if missing:
        print(f"\n❌ 消失的断言（{len(missing)} 条）：\n  {', '.join(missing)}")
        print("\nprobe_selftest_regress FAIL: 断言集变小了。"
              "宪法第二条红线第 2 项：为了让数字变好而放宽验收闸门是绝对红线。"
              "若是改名或合并，需在 TASK_LEDGER 说明新旧对应关系，"
              "再手工更新 probes/selftest_baseline.json。")
        return 1

    snap["checks"] = sorted(cur | accounted)   # 保留旧名，改名记录才有意义
    json.dump(snap, open(BASELINE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nprobe_selftest_regress PASS: 断言只增不减"
          f"（{len(base)} → {len(cur)}，已审核改名 {len(accounted)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
