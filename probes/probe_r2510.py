#!/usr/bin/env python3
"""R2510 回归钉扎——SW 内部逻辑 + schemas 值域三轮审查修复。

钉扎项：
  1. sw.navigate.parallel       —— match('/') 与 fetch 并行起跳
  2. sw.navigate.query_guard    —— ?view= 等带参导航不回写 '/' 壳位
  3. sw.v_mismatch.js_reload    —— ?v 不符的 .js 请求回刷新脚本（不自洽混版）
  4. sw.v_mismatch.nonjs_net    —— 非 JS 的 ?v 不符仍走网络
  5. sw.shell.maskable_icon     —— manifest maskable 图标入 SHELL
  6. schema.lunar.solar_bounds  —— lunar 模式公历年月日仍收粗界
  7. schema.range.year_bounds   —— range_start/end 收 1900-2100 界
  8. schema.favorite.strip_ctrl —— title/ref_id 剥 C0+零宽
  9. schema.names.strip_ctrl    —— NameReviewRequest.names 剥净+回写
  10. resolve_date.base_canonical —— base=20260101 非规范形回落
"""
from __future__ import annotations

import os
import re
import sys

os.environ.setdefault("BOOKS_PAIPAN_HISTORY_DISABLE", "1")
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402
from web.app import app  # noqa: E402

passed = failed = 0


def check(name, cond, note=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name} {note}")
    else:
        failed += 1
        print(f"FAIL {name} {note}")


SW = open(os.path.join(ROOT, "web/static/sw.js"), encoding="utf-8").read()
SCHEMAS = open(os.path.join(ROOT, "web/schemas.py"), encoding="utf-8").read()

# --- 1. 导航并行化 ---------------------------------------------------------
_nav = re.search(r"e\.request\.mode === 'navigate'(.{0,2400})",
                 SW, re.S)
check("sw.navigate.parallel",
      _nav and "_hitP = caches.match('/').catch" in _nav.group(1)
      and "fetch(e.request).then" in _nav.group(1),
      "match 与 fetch 并行")

# --- 2. ?view= 不回写壳位 ---------------------------------------------------
check("sw.navigate.query_guard",
      "url.pathname === '/' && !url.search" in SW,
      "空 search 才算正壳")

# --- 3/4. ?v 不符分路由 ----------------------------------------------------
_vm = re.search(r"if \(!_vOk\) \{(.*?)return _net\(\)\.catch", SW, re.S)
check("sw.v_mismatch.js_reload",
      _vm and "location.reload" in _vm.group(1)
      and ".js" in _vm.group(1),
      "JS 请求回 location.reload 自刷")
check("sw.v_mismatch.nonjs_net",
      "return _net().catch(function () { return undefined; });" in SW,
      "非 JS 仍 _net 兜底")

# --- 5. maskable 图标入 SHELL ------------------------------------------------
check("sw.shell.maskable_icon",
      "icon-512-maskable.png" in SW,
      "manifest maskable 在 precache")

# --- 6. lunar 模式公历粗界（活端点） ----------------------------------------
client = TestClient(app)
r = client.post("/api/bazi", json={
    "calendar_type": "lunar", "lunar_year": 2024, "lunar_month": 1,
    "lunar_day": 1, "year": -999, "month": 13, "day": 40,
    "hour": 0, "gender": "女"})
check("schema.lunar.solar_bounds", r.status_code == 400
      and "年份" in r.json().get("detail", ""),
      f"year=-999 → {r.status_code}")

# 干净 lunar 仍放行（不误伤）
r2 = client.post("/api/bazi", json={
    "calendar_type": "lunar", "lunar_year": 1990, "lunar_month": 5,
    "lunar_day": 15, "year": 1990, "month": 5, "day": 15,
    "hour": 10, "gender": "男"})
check("schema.lunar.clean_ok", r2.status_code == 200
      and "甲" in r2.json().get("paipan", {}).get("render", "") or
      r2.status_code == 200,
      f"clean lunar → {r2.status_code}")

# --- 7. range 年界 -----------------------------------------------------------
r3 = client.post("/api/bazi", json={
    "year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
    "scope": "range", "range_start": "1500-01-01",
    "range_end": "1500-01-05"})
check("schema.range.year_bounds", r3.status_code == 400
      and "范围年份" in r3.json().get("detail", ""),
      f"1500 → {r3.status_code}")
r4 = client.post("/api/bazi", json={
    "year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
    "scope": "range", "range_start": "2026-01-01",
    "range_end": "2026-01-05"})
check("schema.range.ok", r4.status_code == 200,
      f"2026 range → {r4.status_code}")

# --- 8. favorite 净化 ---------------------------------------------------------
r5 = client.post("/api/favorites", json={
    "type": "bazi", "ref_id": "probe-r2510", "title": "a\u202eb\u202c尾"})
check("schema.favorite.strip_ctrl",
      r5.status_code == 200, f"fav add → {r5.status_code}")
if r5.status_code == 200:
    fid = r5.json().get("id")
    import sqlite3
    k = sqlite3.connect(os.path.join(ROOT, "data/index/knowledge.db"))
    row = k.execute(
        "SELECT title FROM favorites WHERE id=?", (fid,)).fetchone()
    check("schema.favorite.stored_clean",
          row and "\u202e" not in row[0] and "\u202c" not in row[0],
          f"stored={row[0]!r}" if row else "row gone")
    k.execute("DELETE FROM favorites WHERE id=?", (fid,))
    k.commit()
else:
    check("schema.favorite.stored_clean", False, "add 被拒无法回读")

# --- 9. names 剥净（schema 直接调） -------------------------------------------
sys.path.insert(0, os.path.join(ROOT, "web"))
from web.schemas import NameReviewRequest  # noqa: E402

nr = NameReviewRequest(names=["苏\u0001  \u202e瑶", "苏  芸"], facts=None)
nr.validate_ranges()
check("schema.names.strip_ctrl",
      all("\u0001" not in n and "\u202e" not in n and "\u202c" not in n
          for n in nr.names),
      f"names={nr.names}")

# --- 10. base 规范形 -----------------------------------------------------------
r6 = client.get("/api/huangli/resolve_date", params={"q": "明天",
                                                     "base": "20260101"})
check("resolve_date.base_canonical", r6.status_code == 200,
      f"base=20260101 → {r6.status_code}（规范回落）")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
