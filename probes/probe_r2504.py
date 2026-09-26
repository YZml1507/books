"""probes/probe_r2504.py — R2504 批次修复回归闸。

钉扎本轮双 agent 深审后的七条修复（TestClient + 源码级钉扎，离线不打 LLM）：

后端（B 系，domain agent 发现）
 1. _hehun_score 年支六冲/六合漏计——year_zhi_rel 值域只有 '半合'，
    原读法让「年支减半」权项对冲/合恒 0；现从 clash/combine 推导。
 2. daily year_line 年号误标——立春前 ~35 天/年句首写日历年而干支
    是上一年；现用 _liunian 回吐的流年公历年。
 3. voice.py 7 处裸 date.today()——UTC 部署下北京 0–8 点 warm 盐/
    应期年比日签旧一天；现统一 _today_cn() 锚 UTC+8。
 4. taohua dayun_hits 只认年支桃花——与 hit_pillars 年+日双口径
    不一致（R2349s 漏改应期层）；现任一并集。

前端（A 系，frontend agent 发现，源码级钉扎；几何效果由
check_poster/ui_smoke 与人工截图复核）
 5. 塔罗 ≥5 张牌阵海报：补位明细行整片落进卡座被白卡盖住——
    lines 硬顶按有无 cards 分档 860/1260 + 兜底上提。
 6. 低配海报节日徽章 W 混入 1080 逻辑系，漂到 64% 宽——改钉逻辑系。
    （附带：卡高 420→400，卡底不再盖品牌水印行。）
 7. app_research.js：doThread 空主题早退不清 busy；12 处 API 失败
    裸 fail() 无重试钮——统一 failWithRetry。

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

    # ── 1. 合婚年支六冲/六合计入合拍指数 ──────────────────────
    from guji.hehun import Hehun
    from web.services import _hehun_score

    _kw = dict(year_zhi_a="午", year_zhi_b="子",
               day_gz_a="庚辰", day_gz_b="丁酉",
               day_wx_a="金", day_wx_b="火",
               day_wx_sheng=False, peach_a="卯", peach_b="酉",
               peach_same=False, day_zhi_rel="合",
               nayin_rel="相克", god_a_sees_b="正官", god_b_sees_a="正财")
    _base = _hehun_score(Hehun(clash=False, combine=False, **_kw))
    _clash = _hehun_score(Hehun(clash=True, combine=False, **_kw))
    _comb = _hehun_score(Hehun(clash=False, combine=True, **_kw))
    check("hehun 年支六冲 → 合拍指数降 ~9.6",
          8 <= (_base - _clash) <= 11,
          f"base={_base} clash={_clash} diff={_base - _clash}")
    check("hehun 年支六合 → 合拍指数升 ~10.8",
          9 <= (_comb - _base) <= 12,
          f"combine={_comb} diff={_comb - _base}")
    # 半合（year_zhi_rel）仍按原口径 +6 左右，不被推导覆盖
    _half = _hehun_score(Hehun(clash=False, combine=False,
                               year_zhi_rel="半合", **_kw))
    check("hehun 年支半合口径不变",
          5 <= (_half - _base) <= 7, f"half={_half} diff={_half - _base}")

    app = create_app()
    c = TestClient(app)
    # 端点级：冲对（1990 午 × 1996 子）实测 51（修前 61，六冲 -9.6 落分）
    r = c.post("/api/hehun", json={
        "a_year": 1990, "a_month": 5, "a_day": 15, "a_hour": 10,
        "a_gender": "女",
        "b_year": 1996, "b_month": 3, "b_day": 1, "b_hour": 10,
        "b_gender": "男"})
    j = r.json() if r.status_code == 200 else {}
    check("端点：子午冲对 match_score=51",
          j.get("match_score") == 51 and j.get("clash") is True,
          f"score={j.get('match_score')} clash={j.get('clash')}")

    # ── 2. daily year_line 用流年公历年 ───────────────────────
    r = c.get("/api/daily", params={"date": "2026-01-20",
                                    "bday": "1990-05-15"})
    j = r.json() if r.status_code == 200 else {}
    _yl = ((j.get("personal") or {}).get("year_line")) or ""
    check("立春前 year_line 年号=流年公历年（非日历年）",
          _yl.startswith("2025") and "乙巳" in _yl,
          f"year_line={_yl!r}")
    # 正例：立春后年号=日历年
    r = c.get("/api/daily", params={"date": "2026-06-01",
                                    "bday": "1990-05-15"})
    j = r.json() if r.status_code == 200 else {}
    _yl2 = ((j.get("personal") or {}).get("year_line")) or ""
    check("立春后 year_line 年号=日历年",
          _yl2.startswith("2026"), f"year_line={_yl2!r}")

    # ── 3. voice.py 不读裸时钟（全锚 UTC+8）──────────────────
    _vs = open(os.path.join(ROOT, "src", "guji", "voice.py"),
               encoding="utf-8").read()
    check("voice.py 无裸 .date.today() 调用",
          ".date.today()" not in _vs,
          f"count={_vs.count('.date.today()')}")
    check("voice.py 有 _today_cn 锚定函数",
          "def _today_cn" in _vs and "hours=8" in _vs)

    # ── 4. taohua dayun_hits 年+日双口径 ─────────────────────
    # 实证 fixture：1985-06-10 10:00 女 —— 年支丑→桃花午（无大运命中），
    # 日支辰→桃花酉 → 乙酉运（2014 起）仅经日支口径命中。
    r = c.post("/api/taohua", json={"year": 1985, "month": 6, "day": 10,
                                    "hour": 10, "gender": "女"})
    j = r.json() if r.status_code == 200 else {}
    _hits = j.get("dayun_hits") or []
    check("taohua 日支桃花大运应期入列",
          any(h.get("pillar") == "乙酉" and h.get("year_start") == 2014
              for h in _hits),
          f"dayun_hits={_hits}")

    # ── 5/6. app_poster.js 源码钉扎 ───────────────────────────
    _ps = open(os.path.join(ROOT, "web", "static", "app_poster.js"),
               encoding="utf-8").read()
    check("poster 明细行硬顶按卡片区分档",
          "_linesTop = (s.cards || []).length ? 860 : 1260" in _ps)
    check("poster 兜底上提防越硬顶",
          "cardY - 60 + lines.length * lh + 40 > _linesTop" in _ps)
    check("poster 徽章钉 1080 逻辑系",
          "s.badge, 1080 - 56" in _ps and "s.badge, W - 56" not in _ps)
    check("poster 卡高 400 不盖水印行",
          "cw = 250, ch = 400" in _ps)

    # ── 7. app_research.js 源码钉扎 ───────────────────────────
    _rs = open(os.path.join(ROOT, "web", "static", "app_research.js"),
               encoding="utf-8").read()
    check("research API 失败全走 failWithRetry",
          _rs.count("failWithRetry(") >= 12,
          f"count={_rs.count('failWithRetry(')}")
    check("doThread 空主题早退清 busy",
          "fail('threadResult', '先写个主题名" in _rs)

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
