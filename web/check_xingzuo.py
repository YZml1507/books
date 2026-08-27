"""web/check_xingzuo.py — 004 M2 判据 10/11 的量尺（R188b）。

判据 10（可追溯性）：12 宫每条的引文锚点在 corpus.db 对应页**逐字命中**。
判据 11（确定性）：同一日期两次调用 /api/xingzuo 响应逐字节相等；
                  12 宫 × 同一天全量输出逐字节可复现。

闸门纪律（PHASE.md）：失败退出 1、成功退出 0，带阳性对照——
--self-check 注入一条假锚点，必须被抓到。

用法（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe web\\check_xingzuo.py
    .\\.venv\\Scripts\\python.exe web\\check_xingzuo.py --self-check
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "src"))

FIXTURE = os.path.join(_ROOT, "web", "baselines", "xingzuo_fixture.json")


def _load_fixture() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)["signs"]


def check_anchors(fixture: dict, conn: sqlite3.Connection) -> list[str]:
    """判据 10：逐条锚点在对应 unit.text 中逐字命中。"""
    problems: list[str] = []
    for sign, a in fixture.items():
        row = conn.execute(
            "SELECT text FROM unit WHERE work_id=? AND page_anchor=?",
            (a["work_id"], a["page_anchor"])).fetchone()
        if row is None:
            problems.append(f"{sign}: 页不存在 {a['work_id']}@{a['page_anchor']}")
        elif a["needle"] not in row[0]:
            problems.append(f"{sign}: needle 未逐字命中 "
                            f"{a['work_id']}@{a['page_anchor']} :: {a['needle']!r}")
    return problems


def check_deterministic() -> list[str]:
    """判据 11：同日两次调用逐字节相等；12 宫齐全。"""
    from fastapi.testclient import TestClient

    from web.app import app

    client = TestClient(app)
    r1 = client.get("/api/xingzuo?date=2026-08-20")
    r2 = client.get("/api/xingzuo?date=2026-08-20")
    problems: list[str] = []
    if r1.status_code != 200:
        problems.append(f"/api/xingzuo 状态码 {r1.status_code}")
        return problems
    if r1.json() != r2.json():
        problems.append("判据 11：同日两次调用响应不等（违反确定性）")
    j = r1.json()
    signs = j.get("signs") or []
    if len(signs) != 12:
        problems.append(f"12 宫不全：{len(signs)}")
    today = [s for s in signs if s.get("is_today")]
    if len(today) != 1:
        problems.append(f"今日值宫应恰有 1 个，实际 {len(today)}")
    # 模块级确定性（不经 HTTP）
    from guji.xingzuo import daily_horoscope
    if daily_horoscope("丁卯") != daily_horoscope("丁卯"):
        problems.append("模块级 daily_horoscope 非确定")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照：注入假锚点必须被抓到")
    args = ap.parse_args()

    fixture = _load_fixture()
    conn = sqlite3.connect(os.path.join(_ROOT, "data", "index", "corpus.db"))

    if args.self_check:
        bad = dict(fixture)
        bad["白羊"] = dict(bad["白羊"], needle="不存在的锚点XYZ")
        problems = check_anchors(bad, conn)
        if not problems:
            print("self-check FAIL: 假锚点未被抓到", file=sys.stderr)
            return 1
        print(f"self-check PASS: 假锚点被抓到（{len(problems)} 条）")
        return 0

    p10 = check_anchors(fixture, conn)
    p11 = check_deterministic()
    allp = p10 + p11
    if allp:
        print("check_xingzuo FAIL:", file=sys.stderr)
        for p in allp:
            print(" -", p, file=sys.stderr)
        return 1
    print(f"check_xingzuo PASS: 判据 10（{len(fixture)} 锚点逐字命中）+ "
          f"判据 11（确定性）全部达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
