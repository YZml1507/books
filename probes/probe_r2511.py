#!/usr/bin/env python3
"""R2511 回归钉扎——services.py 编排层三轮审查修复。

钉扎项：
  1. date.下星期X        —— 「下星期三」解到下个周三（+7），不再落本周
  2. date.下下星期X      —— 「下下星期三」解到+14
  3. date.下星期末       —— 下周末六
  4. date.上星期/下周/礼拜 不变 —— 旧词形零回归
  5. llm.queued_truthful —— chat 任务 started 在拿到会话锁后打标
  6. llm.gc_pending      —— pending 行超 2×TTL 照收（防 _MAX_PENDING 泄漏停摆）
  7. llm.base_exc        —— _run 捕获 BaseException（不留 pending 泄漏源）
  8. paipan.slot_release —— Thread.start() 失败释放信号量槽
  9. knowledge.cn_anchor —— daily_cache purge 锚 UTC+8 而非服务器本地日
"""
from __future__ import annotations

import os
import re
import sys
import time

os.environ.setdefault("BOOKS_PAIPAN_HISTORY_DISABLE", "1")
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from datetime import datetime  # noqa: E402

passed = failed = 0


def check(name, cond, note=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name} {note}")
    else:
        failed += 1
        print(f"FAIL {name} {note}")


from web.services import _hl_day_part  # noqa: E402

NOW = datetime(2026, 9, 23)   # 周三

# --- 1-4. 星期词簇 -----------------------------------------------------------
d, _ = _hl_day_part("下星期三", NOW)
check("date.下星期三", d.date().isoformat() == "2026-09-30",
      f"→ {d.date()}（+7，非本周）")
d, _ = _hl_day_part("下下星期三", NOW)
check("date.下下星期三", d.date().isoformat() == "2026-10-07",
      f"→ {d.date()}（+14）")
d, _ = _hl_day_part("下星期日", NOW)
check("date.下星期日", d.date().isoformat() == "2026-10-04",
      f"→ {d.date()}")
d, _ = _hl_day_part("下星期末", NOW)
check("date.下星期末", d.date().isoformat() == "2026-10-03",
      f"→ {d.date()}（下周六）")
d, _ = _hl_day_part("上星期三", NOW)
check("date.上星期三", d.date().isoformat() == "2026-09-16",
      f"→ {d.date()}（不变）")
d, _ = _hl_day_part("下周三", NOW)
check("date.下周三", d.date().isoformat() == "2026-09-30",
      f"→ {d.date()}（不变）")
d, _ = _hl_day_part("星期三", NOW)
check("date.裸星期三", d.date().isoformat() == "2026-09-23",
      f"→ {d.date()}（裸词本周口径不变）")

# --- 5. queued 如实 -----------------------------------------------------------
LLM = open(os.path.join(ROOT, "src/guji/llm_polish.py"),
           encoding="utf-8").read()
_check_chat = re.search(r"def chat\(.*?\n(.*?)\n\s*with _chat_lock",
                        LLM, re.S)
check("llm.queued_truthful",
      "_task_started" in LLM and
      re.search(r"with _session_lock\(session_id\):\s*\n\s*"
                r"# [^\n]*\n(?:\s*#[^\n]*\n)*\s*"
                r"if _task_started is not None:", LLM),
      "started 在 _session_lock 内打标")
check("llm.queued_caller", "_task_started=_mark_started" in LLM,
      "spawn_chat_task 传回调")

# --- 6. pending 超龄照收（功能实测） ---------------------------------------------
sys.path.insert(0, os.path.join(ROOT, "src"))
from guji import llm_polish  # noqa: E402

with llm_polish._tasks_lock:
    llm_polish._tasks.clear()
    # 塞一行 20 分钟前的 pending（泄漏态）
    llm_polish._tasks["stale-pending"] = {
        "status": "pending", "text": None,
        "created": time.monotonic() - (llm_polish._TASK_TTL_S * 3)}
    # 一行 1 分钟前的 pending（正常排队态——不许收）
    llm_polish._tasks["fresh-pending"] = {
        "status": "pending", "text": None,
        "created": time.monotonic() - 60}
    llm_polish._gc_tasks()
    got_stale = "stale-pending" in llm_polish._tasks
    got_fresh = "fresh-pending" in llm_polish._tasks
    llm_polish._tasks.clear()
check("llm.gc_pending", not got_stale and got_fresh,
      f"stale收={not got_stale} fresh保={got_fresh}")

# --- 7. BaseException 防泄漏 ---------------------------------------------------
_run_blocks = re.findall(r"def _run\(\) -> None:(.*?)"
                         r"threading\.Thread\(target=_run", LLM, re.S)
be = sum(1 for b in _run_blocks if "except BaseException" in b)
check("llm.base_exc", len(_run_blocks) >= 2 and be == len(_run_blocks),
      f"{be}/{len(_run_blocks)} _run 用 BaseException")

# --- 8. 信号量槽释放 -------------------------------------------------------------
PH = open(os.path.join(ROOT, "src/guji/paipan_history.py"),
          encoding="utf-8").read()
_start = re.search(r"try:\s*\n\s*threading\.Thread\(target=_work.*?"
                   r"except Exception:\s*\n(?:\s*#[^\n]*\n)*\s*"
                   r"_SAVE_SLOTS\.release\(\)", PH, re.S)
check("paipan.slot_release", bool(_start),
      "start() 失败 release 槽位")

# --- 9. UTC+8 锚 ------------------------------------------------------------------
KN = open(os.path.join(ROOT, "src/guji/knowledge.py"),
          encoding="utf-8").read()
_purge = re.search(r"def set_daily_cache.*?(?=def |\Z)", KN, re.S)
_code = "\n".join(l for l in (_purge.group(0) if _purge else "")
                  .splitlines() if not l.lstrip().startswith("#"))
check("knowledge.cn_anchor",
      _purge and "datetime.utcnow() + _td(hours=8)" in _code
      and "_d.today()" not in _code,
      "purge/窗口锚 UTC+8")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
