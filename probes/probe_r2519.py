#!/usr/bin/env python3
"""R2519 — 深度收尾：daily personal 行动尾 + 起名两步实用行。

- services.daily 的 personal.line 挂 TEN_GOD_ACTION 适合项
  （首页大卡从「是什么日」到「能干什么」）。
- warm_qiming 定名前两步实用行（念三遍+查谐音歧义）。
"""
import re
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "src")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


_svc = open("web/services.py", encoding="utf-8").read()
from src.guji import voice  # noqa: E402

# --- 1. personal.line 挂行动尾（源码形状 + 活函数实证）---
ck("personal.action_src",
   re.search(r"TEN_GOD_ACTION\.get\(_god\)[\s\S]{0,400}适合",
             _svc) is not None)
# 真跑 daily() 拿 personal 行（bday 触发 personal 分支）
from web import services  # noqa: E402
_r = services.daily(None, "2001-05-20")
_p = (_r.get("personal") or {})
ck("personal.line_action",
   "适合" in (_p.get("line") or ""))
_god = _p.get("god")
if _god:
    _act = voice.TEN_GOD_ACTION.get(_god)
    ck("personal.action_from_table",
       _act is not None and _act[0] in (_p.get("line") or ""))

# --- 2. 起名两步行 ---
_out = {"five_elements": {"missing": ["水"], "weak": []},
        "full_names": [{"full_name": "测试名", "elements": ["水"],
                        "form": "double", "origin": "楚辞",
                        "story": "x" * 30}],
        "one_liner": "x", "bazi": {}}
_w = voice.warm_qiming(_out, "林", "女")
ck("qm.two_steps",
   any("连着姓大声念三遍" in l and "谐音歧义" in l
       for l in _w["reply"]))
ck("qm.cap5", len(_w["reply"]) <= 5)
# 空名单不挂两步行（语法不成立）
_w2 = voice.warm_qiming({"full_names": [], "five_elements": {}}, "", "")
ck("qm.empty_no_step",
   not any("念三遍" in l for l in _w2["reply"]))

print(f"\n{len(PASS)} checks, {len(FAIL)} failed: {FAIL}")
sys.exit(1 if FAIL else 0)
