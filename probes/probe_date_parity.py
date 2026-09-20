"""probes/probe_date_parity.py — 前端 _hlDayOffset ↔ 后端 _hl_day_part
同口径钉扎（R229m）。

为什么需要这条闸门：日期词解析在 app.js 与 services.py 各实现一份
（前端翻黄历卡片、后端给小满喂事实），历史漂移已经咬过两次——
「明天」只被前端剥词没换算日期（R227b-fix）、「下周/本周/下周末/裸曜日/
晚字辈/『天』误映射成周一」成串漏网（R229e–i）。靠人肉记两边同步必漂。

做法：playwright 打开真实页面，page.evaluate 调浏览器里的 _hlDayOffset
（固定基准日 2026-09-19 周六）；python 侧直接调 web.services._hl_day_part
（now 同日），把返回的绝对日换成偏移天数比对。null ↔ 「今天」（off=None
即按显示日，默认今天=偏移0；后端显式返回今天）对齐口径。

退出码：0=全部一致，1=存在分歧（打印对照表），2=环境缺失。
"""
from __future__ import annotations

import datetime
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "web"))
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")

BASE = datetime.datetime(2026, 9, 19, 12, 0)   # 周六

# (问法, 期望偏移, 期望口头词前缀或 None)——期望与两端实现无关，人工标注。
CASES = [
    ("今天适合出行吗", 0), ("今日", 0), ("今晚约会", 0), ("今夜", 0),
    ("明天适合出行吗", 1), ("明日搬家", 1), ("明儿签约", 1), ("明晚约会", 1),
    ("后天能剪头发吗", 2), ("後天", 2), ("过两天出差", 2), ("后晚聚", 2),
    ("大后天考试", 3), ("大後天", 3),
    ("昨天干了啥", -1), ("昨晚睡得好", -1), ("前天出门了", -2), ("大前天", -3),
    ("下周三面试", 4), ("下週三面试", 4), ("下礼拜天搬家", 8), ("下周", 2),
    ("下周末出行", 7), ("下週末出行", 7),
    # R229y续：「下下X」——"下下周一"含"下周"，通配会截胡差整 7 天。
    ("下下周一签约", 9), ("下下周末聚餐", 14), ("下下礼拜天出去玩", 15),
    ("本周三搬家", -3), ("这周五约会", -1), ("这週五適合面試嗎", -1),
    ("本周日出行", 1), ("这周日", 1),
    ("周末搬家", 0),          # 今天周六 → 本周末=今天
    ("周日出行", 1), ("周天出行", 1), ("礼拜天签约", 1), ("星期天", 1),
    ("周五搬家", 6), ("星期一上班", 2), ("星期三看医生", 4),
    ("明天适合出行吗", 1),
    # R229z：公历绝对日期——前后端同一套就近口径（9/19 视角下 9/25 未过）。
    ("9月25号搬家", 6), ("10月1日结婚", 12), ("10-5出差", 16),
    ("25号面试", 6), ("下个月5号开业", 16), ("这个月30号签约", 11),
    ("月底签约", 11), ("9月1号那天", -18),
    ("跟对象吵架了", None),  # 无日期词 → null/今天
]

# R229z：节日/农历是后端单点真相（前端 _hlDayOffset 应返回 null，由
# /api/huangli/resolve_date 兜底——双轨不同解才是 bug）。这里钉后端偏移
# 且断言 js 必须 None。
PY_ONLY = [
    ("国庆节出游", 12), ("中秋節搬新家", 6), ("农历八月十五出行", 6),
    ("除夕那天在干嘛", -215), ("清明节扫墓", 198), ("母亲节送花", 232),
    ("腊八粥好喝吗", 118),
]

# 两实现都钉在同一语义上：返回的是「相对 BASE 的天数偏移」。
# 前端 _hlDayOffset 返回 null = 无日期词（按显示日走）；
# 后端无词返回 (today, "今天")。对齐：py null 等价 → 用 weekday 差比对。


def _py_off(msg: str):
    from web import services
    dt, _spoken = services._hl_day_part(msg, BASE)
    # 后端无日期词时返回今天——无法区分「显式今天」与「默认今天」，
    # 这里按词面判断：消息里根本没日期词时按 null 比。
    return dt, _spoken


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probe_date_parity SKIP-ENV: playwright 未安装")
        return 2

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), 0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("probe_date_parity SKIP-ENV: 服务起不来")
            return 2

        from web import services  # noqa: F401 — 先确认 import 没问题
        diffs = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(1200)
            for q, exp in CASES:
                js = page.evaluate(
                    "(q) => _hlDayOffset(q, new Date(2026, 8, 19, 12))", q)
                # python 侧：绝对日期 → 偏移
                from web import services as _s
                dt, sp = _s._hl_day_part(q, BASE)
                py_off = (dt.date() - BASE.date()).days
                # 对齐口径：JS null = 无词按今天；py 无词返回今天（off=0 且
                # spoken='今天'）。「无词」判据：spoken 不是任何日期原词。
                has_word = sp != "今天" or any(
                    k in q for k in ("今天", "今日", "今晚", "今夜"))
                py_val = py_off if has_word else None
                ok = (js == py_val)
                exp_mark = "" if exp is None or js == exp else f" 期望{exp}"
                status = "OK " if ok else "DIFF"
                if not ok:
                    diffs.append(q)
                print(f"  [{status}] {q!r:>24}  js={js}  py={py_val}"
                      f"（{sp} → {dt.date()}）{exp_mark}")
            # R229z：节日/农历是后端单点真相——前端必须返回 null（交给
            # resolve_date 端点），本地若解出则是双轨分叉。
            for q, exp in PY_ONLY:
                js = page.evaluate(
                    "(q) => _hlDayOffset(q, new Date(2026, 8, 19, 12))", q)
                from web import services as _s2
                dt, sp = _s2._hl_day_part(q, BASE)
                py_off = (dt.date() - BASE.date()).days
                ok = (js is None and py_off == exp)
                status = "OK " if ok else "DIFF"
                if not ok:
                    diffs.append(f"{q}(js={js},py={py_off})")
                print(f"  [{status}] {q!r:>24}  js={js}  py={py_off}"
                      f"（{sp} → {dt.date()}）")
            browser.close()

        if diffs:
            print(f"\nprobe_date_parity FAIL: {len(diffs)} 条分歧: {diffs}")
            return 1
        print(f"\nprobe_date_parity PASS: {len(CASES)}+{len(PY_ONLY)} 条问法偏移一致")

        # ── R229q：事项词别名表前后端同构钉扎 ──────────────────────
        # 前端 HL_SCENE_ALIAS ↔ 后端 _CHAT_SCENE_TERMS 各存一份，R229q
        # 前已实测漂移（搬家/种花/许愿 值表不一致 → 同一问题卡面与聊天
        # 事实给不同判定）。规则：JS 键 ⊆ py 键；同键值集合相等；
        # py 非自映射键（terms != [k]）必须出现在 JS。
        from web import services as _sv
        py_alias = _sv._CHAT_SCENE_TERMS
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(800)
            js_alias = page.evaluate("() => HL_SCENE_ALIAS")
            js_t2s = page.evaluate("() => _T2S")
            browser.close()
        # R229q：_T2S 繁简映射表也是前后端各存一份——同一钉扎。
        t2s_diff = [k for k, v in js_t2s.items()
                    if _sv._T2S.get(k) != v] + \
                   [k for k in _sv._T2S if k not in js_t2s]
        if t2s_diff:
            print("probe_date_parity FAIL: _T2S 表分歧: "
                  + ",".join(t2s_diff[:20]))
            return 1
        bad = []
        for k, vs in js_alias.items():
            if k not in py_alias:
                bad.append(f"JS 独有键 {k}")
            elif set(vs) != set(py_alias[k]):
                bad.append(f"{k}: js={vs} py={py_alias[k]}")
        for k, vs in py_alias.items():
            if vs != [k] and k not in js_alias:
                bad.append(f"py 非自映射键缺席 JS：{k}→{vs}")
        if bad:
            print("\nprobe_date_parity FAIL: 别名表分歧: "
                  + "; ".join(bad[:12]))
            return 1
        print(f"probe_date_parity alias PASS: {len(js_alias)} 键前后端同构")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
