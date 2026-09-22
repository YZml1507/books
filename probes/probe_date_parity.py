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
    ("周末适合搬家吗", 0),
    ("周五搬家", 6), ("星期一上班", 2), ("星期三看医生", 4),
    ("明天适合出行吗", 1),
    # R229z：公历绝对日期——前后端同一套就近口径（9/19 视角下 9/25 未过）。
    ("9月25号搬家", 6), ("10月1日结婚", 12), ("10-5出差", 16),
    ("25号面试", 6), ("下个月5号开业", 16), ("这个月30号签约", 11),
    ("上个月5号出差", -45), ("月底签约", 11), ("9月1号那天", -18),
    ("去年9月10号领证", -374), ("明年10月1日结婚", 377),
    ("坐3号线去面试", None),   # 「号线/楼」邻接字防误命中
    ("月初发工资", 12), ("月底前交稿", 11),
    # R2349（R64-P1-4）：「年底」→当年 12/31 代表日（两端同口径）
    ("年底备孕合适吗", 103), ("年底拍婚纱照", 103),
    # 节/日后缀 ±：「9月25号前一天」「下个月5号前一天」
    ("9月25号前一天签约", 5), ("10月1日后搬家", 13), ("下个月5号前一天", 15),
    ("25号前一天面试", 5), ("月底前一天", 10),
    # R2355（R111-P2-2）：「下下个月」与下下周同病——内层「下个月」
    # 通配会截胡差整月。两侧同按「再下一月」锚。
    ("下下个月15号签约", 57), ("下下个月5号出差", 47),
    # R2355（R111-P1-3/P2-1）：4位年锚——前端一律交后端 resolve
    #（js=null）；后端按显式年解/越界不存在的如实不落。
    ("2027-02-29搬家", None), ("2101年3月1号开业", None),
    # R2355（R111-P1-2/P2-3）：说了但不存在的日子两侧同不落（星期八
    # 不在曜日表、32号超月界——不许静默按今天判）。
    ("星期八出行", None), ("32号开业", None),
    ("跟对象吵架了", None),  # 无日期词 → null/今天
    # R230a-6（R12-P3-3）：「日」字辈后端补认——「日后」不许命中「后日」。
    ("我后日去面试", 2), ("大前日搬家", -3), ("前日签约", -2),
    ("日后相处", None),
]

# R229z：节日/农历是后端单点真相（前端 _hlDayOffset 应返回 null，由
# /api/huangli/resolve_date 兜底——双轨不同解才是 bug）。这里钉后端偏移
# 且断言 js 必须 None。
PY_ONLY = [
    ("国庆节出游", 12), ("中秋節搬新家", 6), ("农历八月十五出行", 6),
    ("除夕那天在干嘛", 139), ("清明节扫墓", 198), ("母亲节送花", 232),
    ("腊八粥好喝吗", 118), ("前年中秋", -732), ("去年中秋", -348),
    ("去年农历八月十五", -348),
    # R2359：去年除夕=2025-01-28——旧期望 -215（2026-02-16）钉的是
    # 「农历年下标加 yoff」的错值，改为按发生日公历年过滤后的真值。
    ("去年除夕", -599), ("后年国庆", 743),
    # 节日前/后后缀
    ("中秋节前一天搬家", 5), ("国庆后签约", 13), ("春节前理发", 139),
    # R230a-3：双十一/光棍节/中元节/小年已进节日表（真命中）；
    # 「双十一月」仍不许命中「十一」。
    ("双十一买东西", 53), ("光棍节单身", 53),
    ("中元节祭祖", 331), ("小年大扫除", 133),
    ("双十一月搬家", None),
    # 农历月日（含裸正月/冬月/腊月与闰月——闰月按绝对就近）
    ("腊月廿三祭灶", 133), ("正月十五看灯", 154),
    ("闰六月十五结婚", -407), ("农历闰五月初一", 643),
    ("八月十五", None),       # 无前缀「八月十五」有歧义不猜农历
    ("腊月底办酒", 139), ("正月末回家", 169),
    ("五月初一上香", None),   # 「月初」不许吃掉「五月初一」的初
    # 节气（term_time 天文算法）；小满=吉祥物名/下大雪=天气，不许命中
    # R233v（R52-P0）：节气 UTC→CST 修正后的真值偏移（12/22、3/6）
    ("冬至吃饺子", 94), ("惊蛰理发", 168), ("驚蟄那天搬家", 168),
    ("立春后开工", 139), ("去年冬至", -272),
    ("小满觉得我好看吗", None), ("下大雪能出行吗", None),
    # R233v（R52）：法定假表 / 民俗节 / 三伏数九 / 周末周日语义
    ("国庆节后第一天上班", 19),
    # R2359（R115-P1-3）：放假表外不再回过期档——旧期望 -207
    #（2026-02-24 旧档复工日）作废；现为春节+1 回落语义 2027-02-07。
    ("春节后上班", 141), ("小长假去哪玩", 6),
    ("数九寒天", 94), ("二月二理发", 171), ("寒衣节回家", 51),
    # R2355：可解的显式 4 位年——js 仍 null（交后端），py 按该年锚定。
    ("2026年10月1日搬家", 12), ("2027年10月1日搬家", 377),
]

# R2349（R64-P0-A）：周末口径在「周六 BASE」下两侧碰巧一致（都判今天），
# 周日/周一的分歧被钉死的基准日遮住——补周日基线（已是周末→今天）
# 与周一基线（→下周六）。两端都钉同一期望。
BASE_SUN = datetime.datetime(2026, 9, 20, 12)   # 周日
CASES_SUN = [
    ("周末搬家", 0), ("这周末出行", 0), ("周日出行", 0),
    ("周天出行", 0), ("周末适合搬家吗", 0),
]
BASE_MON = datetime.datetime(2026, 9, 21, 12)   # 周一
# R2359（R115-P1-1）：跨年锚点组——BASE 钉在 9 月的盲区：1 月~除夕窗里
# 农历年=公历年-1，「今年/明年+农历节」此前整体差一太阳年，除夕再叠加。
# 节日/农历是后端单点真相（js 必须 null），只钉 py 偏移。
BASE_JAN = datetime.datetime(2026, 1, 15, 12)   # 1 月窗（农历年=2025）
PYONLY_JAN = [
    ("今年春节", 33), ("去年春节", -351), ("明年春节", 387),
    ("今年中秋", 253), ("明年正月初一", 387), ("今年国庆", 259),
]
BASE_DEC = datetime.datetime(2026, 12, 20, 12)  # 年末窗
PYONLY_DEC = [
    ("明年除夕", 47), ("去年除夕", -691), ("前年除夕", -1045),
    ("后年除夕", 401), ("2027年春节", 48), ("2027年除夕", 47),
    ("2027年立春", 46), ("2027年中秋", 269), ("2027年国庆节", 285),
    ("农历新年", 48), ("去年腊月底", -691),
]
BASE_FEB = datetime.datetime(2027, 2, 1, 12)    # 数九段内
PYONLY_FEB = [("数九", -41)]
CASES_MON = [
    ("周末搬家", 5), ("周一上班", 0), ("这周三看医生", 2),
    # R2349q（R82-P0-1）：上周-族此前全落「本周同曜日」未来日——
    # 周一基准：上周一=9/14(-7) 上周三=9/16(-5) 上周六=9/19(-2)
    # 上周末=9/19(-2) 上个月=8/1(-51)。
    ("上周六签约", -2), ("上週六簽約", -2), ("上礼拜三剪头发", -5),
    ("上星期一看病", -7), ("上周末出去玩", -2), ("上个周末聚餐", -2),
    ("上周面试", -7), ("上个月搬家", -51), ("上個月搬家", -51),
    ("上月开业", -51),
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
                # exp=None → 要求后端也当无日期词（spoken 落「今天」）
                _py_hit = (py_off == exp) if exp is not None \
                    else (sp == "今天")
                ok = (js is None and _py_hit)
                status = "OK " if ok else "DIFF"
                if not ok:
                    diffs.append(f"{q}(js={js},py={py_off})")
                print(f"  [{status}] {q!r:>24}  js={js}  py={py_off}"
                      f"（{sp} → {dt.date()}）")
            # R2349：周日/周一基线复扫——周末/曜日语义在不同 BASE 下
            # 有分歧面（R64-P0-A 实测周日问「周末」前端 +6 后端 0）。
            for base_tag, bdt, cases in (
                    ("SUN", BASE_SUN, CASES_SUN), ("MON", BASE_MON, CASES_MON)):
                for q, exp in cases:
                    js = page.evaluate(
                        "(q) => _hlDayOffset(q, new Date(%d, %d, %d, 12))"
                        % (bdt.year, bdt.month - 1, bdt.day), q)
                    dt, sp = _s._hl_day_part(q, bdt)
                    py_off = (dt.date() - bdt.date()).days
                    ok = (js == py_off) and (exp is None or js == exp)
                    status = "OK " if ok else "DIFF"
                    if not ok:
                        diffs.append(f"[{base_tag}]{q}(js={js},py={py_off})")
                    print(f"  [{status}] [{base_tag}] {q!r:>18}  js={js}"
                          f"  py={py_off}（{sp} → {dt.date()}）期望{exp}")
            # R2359：跨年锚点 py-only 组（节日/农历/显式年 js 一律 null）。
            for base_tag, bdt, cases in (
                    ("JAN", BASE_JAN, PYONLY_JAN),
                    ("DEC", BASE_DEC, PYONLY_DEC),
                    ("FEB", BASE_FEB, PYONLY_FEB)):
                for q, exp in cases:
                    js = page.evaluate(
                        "(q) => _hlDayOffset(q, new Date(%d, %d, %d, 12))"
                        % (bdt.year, bdt.month - 1, bdt.day), q)
                    dt, sp = _s._hl_day_part(q, bdt)
                    py_off = (dt.date() - bdt.date()).days
                    ok = (js is None) and (py_off == exp)
                    status = "OK " if ok else "DIFF"
                    if not ok:
                        diffs.append(
                            f"[{base_tag}]{q}(js={js},py={py_off},期望{exp})")
                    print(f"  [{status}] [{base_tag}] {q!r:>18}  js={js}"
                          f"  py={py_off}（{sp} → {dt.date()}）期望{exp}")
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

        # ── R2400（R141-P1-2）：宜忌同义族表前后端同构钉扎 ──────────
        # 前端 _HL_FAMILIES ↔ 后端 _TERM_FAMILIES 各存一份；R2400 后端
        # 扩族（营造+平整/功名+出官谒贵/新增丧葬族）时前端静默漂移，
        # 全年 32 场景 356 场景日判定分裂。钉集合级同构（顺序不比）。
        from guji import huangli as _hl
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(800)
            js_fams = page.evaluate("() => _HL_FAMILIES")
            browser.close()
        py_fams = [sorted(f) for f in _hl._TERM_FAMILIES]
        js_fams_s = sorted(tuple(f) for f in (sorted(x) for x in js_fams))
        py_fams_s = sorted(tuple(f) for f in py_fams)
        if js_fams_s != py_fams_s:
            only_js = [f for f in js_fams_s if f not in py_fams_s]
            only_py = [f for f in py_fams_s if f not in js_fams_s]
            print("probe_date_parity FAIL: 宜忌族表分歧 "
                  f"JS独有={only_js[:4]} PY独有={only_py[:4]}")
            return 1
        print(f"probe_date_parity family PASS: {len(js_fams_s)} 族前后端同构")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
