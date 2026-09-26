#!/usr/bin/env python3
"""R2529 — 解读因果层钉扎（调研：深度解读骨架=分层气候+触发点）。

- 「针对」段裸（）修复：括号列「想看的是」targets 而非盘内 gods
  （life scope 无 ten_gods 时 gods 全空渲染成裸括号）。
- 大运走势加因果框架句（大运=十年气候，流年逐年加减）+「←眼下」
  标记当前步（按 year_start 含当前公历年判定，确定性）。
"""
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "src")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


_it = open("src/guji/interpreter.py", encoding="utf-8").read()

ck("it.targets_in_parens",
   "（想看的是{_tg}）" in _it and
   '_tg = "、".join(str(g) for g in targets if g)' in _it)
ck("it.climate_frame",
   "大运是十年的气候" in _it and "←眼下" in _it)
ck("it.cur_idx_year",
   "_now_y = datetime.now().year" in _it and
   'd["year_start"] <= _now_y < d["year_start"] + 10' in _it)

# 行为级：life scope 全链
from web.schemas import BaziRequest
from web import services
r = services.bazi(BaziRequest(
    year=1990, month=1, day=1, hour=12, gender="女",
    calendar="solar", scope="life", question="工作发展怎么样"))
secs = {s["title"]: s["lines"] for s in r["interpretation"]["sections"]}
dy = secs.get("大运走势", [])
ck("bh.climate_line_present",
   any("十年的气候" in l for l in dy))
_cur = [l for l in dy if "←眼下" in l and l.startswith("第 ")]
ck("bh.current_marked", len(_cur) == 1,
   _cur[0][:60] if _cur else "none")
# 1990 年生 2026 年 36 岁 → 应标在覆盖 2021-2031 的运上
ck("bh.marker_correct_pillar",
   _cur and ("2021 年起" in _cur[0] or "庚辰" in _cur[0]))
foc = secs.get("针对「工作发展怎么样」", [])
ck("bh.parens_show_targets",
   foc and "想看的是正官、七杀" in foc[0],
   (foc[0] if foc else "")[:80])
ck("bh.no_bare_parens",
   foc and "（）" not in foc[0])

# 有 ten_gods 的 day scope 不回归
r2 = services.bazi(BaziRequest(
    year=1990, month=1, day=1, hour=12, gender="女",
    calendar="solar", scope="day", question="今天适合面试吗"))
secs2 = {s["title"]: s["lines"] for s in r2["interpretation"]["sections"]}
ck("bh.day_scope_still_works",
   any("针对" in t for t in secs2))

print(f"\n{len(PASS)} pass, {len(FAIL)} fail")
sys.exit(1 if FAIL else 0)
