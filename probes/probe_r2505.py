"""probes/probe_r2505.py — R2505 批次修复回归闸。

钉扎本轮修复（TestClient + 源码级钉扎，离线不打 LLM）：

 1. LUNAR_INFO 表界外 IndexError 穿透成 500（C-1）——
    resolve_huangli_date 的农历闰月/月末解析把 ly 范围放宽到 ±3/±12
    个农历年，ly0 贴近 2100 时 leap_month/month_days 读到 LUNAR_INFO
    表外抛 IndexError（except ValueError 接不住）。base= 是用户可控
    ISO 日期且无范围校验 → /api/huangli/resolve_date 直连 500。
    现按表界 [1900, 2101) 钳定候选年集。
 2. ?view=xzm 速配分享深链落地自动展开速配抽屉（源码钉扎——
    落地承接/滚动由真实浏览器复核）。

退出码：0 全绿；1 有 FAIL；2 probe 自身出错。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  {detail}" if detail else ""))


def main() -> int:
    from fastapi.testclient import TestClient
    from web.app import create_app

    c = TestClient(create_app())

    # ── 1. 农历表界外日期词不再 500 ───────────────────────────
    # 复现样例（修前实测 500）：2099 base + 闰月词 → leap_month(2101)
    r = c.get("/api/huangli/resolve_date",
              params={"q": "农历闰六月十五", "base": "2099-06-15"})
    check("2099 base + 闰月词 → 非 5xx", r.status_code < 500,
          f"status={r.status_code}")
    # 2100 base + 腊月底 → month_days(2101)
    r = c.get("/api/huangli/resolve_date",
              params={"q": "腊月底", "base": "2100-12-01"})
    check("2100 base + 腊月底 → 非 5xx", r.status_code < 500,
          f"status={r.status_code}")
    # 表外 base（3000）——range 钳定后走空候选而非 IndexError
    r = c.get("/api/huangli/resolve_date",
              params={"q": "农历闰六月十五", "base": "3000-06-15"})
    check("表外 base=3000 → 非 5xx", r.status_code < 500,
          f"status={r.status_code}")
    # 低端：1900 base + 腊月底（ly0-3 会探到 1897，钳 1900 后不缠
    # 负下标回绕静默错数据）
    r = c.get("/api/huangli/resolve_date",
              params={"q": "腊月底", "base": "1900-12-01"})
    check("1900 base + 腊月底 → 非 5xx", r.status_code < 500,
          f"status={r.status_code}")
    # 正例功能不回归：2025 确有闰六月 → 可解出 2025-08-08
    r = c.get("/api/huangli/resolve_date",
              params={"q": "农历闰六月十五", "base": "2025-07-01"})
    _j = r.json() if r.status_code == 200 else {}
    check("正常年闰月词仍能解（2025 闰六月→08-08）",
          _j.get("date") == "2025-08-08",
          f"date={_j.get('date')}")
    r = c.get("/api/huangli/resolve_date",
              params={"q": "腊月底", "base": "2026-01-15"})
    _j = r.json() if r.status_code == 200 else {}
    check("腊月底正常年仍可解", bool(_j.get("date")),
          f"date={_j.get('date')}")

    # ── 2. xzm 深链承接（源码钉扎）────────────────────────────
    _js = open(os.path.join(ROOT, "web", "static", "app.js"),
               encoding="utf-8").read()
    check("xzm 别名自动展开速配抽屉",
          "_vpRaw === 'xzm'" in _js and "xzMatchDrawer" in _js
          and "_xd.open = true" in _js)

    # ── 汇总 ──────────────────────────────────────────────────
    _fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 50}\n{len(RESULTS)} checks, "
          f"{len(_fails)} failed")
    return 1 if _fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"probe 自身出错：{e!r}")
        sys.exit(2)
