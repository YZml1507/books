#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_sweep.py — R12：服务端直扫 /api/daily 文案池字符宇宙。

首页日卡文案全部来自 /api/daily（确定性：seed=日期）。
扫一个完整闰年周期（366 天）× 若干生日（覆盖 personal 行的
日主×日干白话池），递归抽取响应里所有字符串的 CJK 字符。
输出 /tmp/r12_daily_chars.txt（十六进制码点，逗号分隔）。
"""
import io
import json
import re
import sys
import datetime as dt

sys.path.insert(0, "/opt/books/app")
os_env = __import__("os").environ
os_env.setdefault("BOOKS_LLM_DISABLE", "1")
os_env.setdefault("BOOKS_PAIPAN_HISTORY_DISABLE", "1")

from fastapi.testclient import TestClient  # noqa: E402
from web.app import app  # noqa: E402

CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")

client = TestClient(app)
chars = set()
n = 0
lines_seen = set()
gods_seen = set()


def harvest(o):
    if isinstance(o, str):
        chars.update(CJK.findall(o))
    elif isinstance(o, dict):
        for v in o.values():
            harvest(v)
    elif isinstance(o, list):
        for v in o:
            harvest(v)


bdays = [None] + ["19%02d-%02d-15" % (90 + i, (i % 12) + 1) for i in range(12)]
d0 = dt.date(2024, 1, 1)          # 闰年，366 天
for i in range(366):
    d = d0 + dt.timedelta(days=i)
    for bd in bdays:
        params = {"date": d.isoformat()}
        if bd:
            params["bday"] = bd
        try:
            r = client.get("/api/daily", params=params)
            if r.status_code != 200:
                continue
            j = r.json()
        except Exception:
            continue
        n += 1
        harvest(j)
        p = (j.get("personal") or {})
        if p.get("line"):
            lines_seen.add(p["line"])
        if p.get("god"):
            gods_seen.add(p["god"])
    if i % 60 == 0:
        print("  …%s 累计 %d 字（%d 次请求）" % (d.isoformat(), len(chars), n))

print("### R12 /api/daily 文案池扫描")
print("  请求 %d 次，唯一 CJK 字符 %d" % (n, len(chars)))
print("  personal.line 去重 %d 条；personal.god 去重 %d 个"
      % (len(lines_seen), len(gods_seen)))
with io.open("/tmp/r12_daily_chars.txt", "w", encoding="utf-8") as f:
    f.write(",".join("%X" % ord(c) for c in sorted(chars)))
print("  已写 /tmp/r12_daily_chars.txt")
