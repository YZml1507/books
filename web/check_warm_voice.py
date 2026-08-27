"""web/check_warm_voice.py — 判据 1–8 的闸门（004 warm 文案层）。

判据来源 `specs/004-warm-voice/spec.md` §Success Criteria：

    1 首屏第一节是对提问的回应        5 同输入同输出（逐字节）
    2 一句话结论非空且 ≤20 字         6 吉凶断言/现实指令 = 0
    3 首屏术语出现次数 ≤3             7 免责含「仅供娱乐」且不压轴
    4 推导依据折叠且逐字不变          8 六爻对提问给描述性回应

领土（宪法第五条，plan §0.1 / D-236b）：本文件在 `web/` 下而非 `probes/`
——`probes/` 是审查轨独占写。审查轨要纳入闸门清单直接调用即可，
接口就是命令行退出码。

闸门纪律（PHASE.md，U-08 教训）：失败退出 1、成功退出 0，且**带阳性对照**
——`--self-check` 注入「你会脱单」等禁用词，必须被抓到。
「永远返回 0 的闸门等于没有闸门」。

用法：
    <py> web\\check_warm_voice.py               # 全量判据 1-8
    <py> web\\check_warm_voice.py --self-check  # 阳性对照
"""
from __future__ import annotations

import argparse
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# 禁用词表（判据 6，plan §3「上限：不许断命」）
#
# 三类：吉凶断言（把可能说成必然）、现实指令（替用户做决定）、
# 专业建议（医疗/投资/法律——宪法与产品责任双重禁止）。
# ---------------------------------------------------------------------------
BANNED_FATE = (
    "会脱单", "一定会", "必然", "命中注定", "必有贵人", "肯定能",
    "注定", "铁定", "百分百", "包你", "保证",
)
BANNED_IMPERATIVE = (
    "该分手", "该辞职", "该离婚", "赶紧买", "赶紧卖", "必须买", "必须卖",
    "去投资", "去borrow",
)
BANNED_PROFESSIONAL = (
    "治病", "吃药", "服药", "确诊", "包治", "股票代码", "抄底",
    "打官司必", "稳赚", "血本无归",
)
# R197b（specs/008-US1）：说教式第二人称句式——把判断权塞回用户手里时
# 带居高临下感（「你自己心里有数」实测令用户反感）。同类句式入库即被抓。
BANNED_CONDESCENDING = (
    "你自己心里有数", "你比盘清楚", "你比卦清楚", "你自己舒服最重要",
)
BANNED = (BANNED_FATE + BANNED_IMPERATIVE + BANNED_PROFESSIONAL
          + BANNED_CONDESCENDING)

# 术语表（判据 3）：首屏出现次数 ≤3。这些是**专业模式**的词汇，warm 层
# 应当已把它们白话化；括号里保留原词不计入（那是刻意保留的可检索性）。
TERMS = (
    "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官",
    "偏印", "正印", "纳音", "大运", "流年", "流日", "流时", "地支",
    "天干", "藏干", "咸池", "六冲", "六合", "三合", "半合", "相刑",
    "自刑", "相害", "建除", "二十八宿",
)

L0_MAX = 20


def _bracket_stripped(text: str) -> str:
    """去掉括号内内容后的文本。

    warm 层刻意在括号里保留原术语（「压力位（七杀）」）——那是为了可检索，
    不算"术语轰炸"。判据 3 数的是**括号外**的术语，否则会把设计当缺陷。
    """
    return re.sub(r"[（(][^）)]*[）)]", "", text)


def _first_screen(warm: dict) -> str:
    """首屏可见范围：L0 + reply + 能量卡 + badge（details 折叠在下方）。

    定义依据 spec US1「Independent Test：取结果区首屏可见范围内的文字」。
    details 的正文虽然在 DOM 里，但它在能量卡之后，首屏（一屏高度）看不到；
    真正的浏览器首屏由审查轨 probe_ui_smoke 侧量，这里量的是**结构上的**
    首屏段，两侧独立见证。
    """
    parts = [warm.get("one_liner") or ""]
    parts.extend(warm.get("reply") or [])
    ec = warm.get("energy_card") or {}
    parts.append(ec.get("element_note") or "")
    parts.extend(str(x) for x in (ec.get("keywords") or []))
    parts.append(warm.get("badge") or "")
    return "\n".join(parts)


def _all_prose(warm: dict) -> str:
    """warm 层自己生成的全部文案（不含引文原文与依据链）。

    citations 是古籍原文、details[].basis 是 interpreter 原样搬运的推导链
    ——两者都**不是** warm 写的，不能拿禁用词表去查它们（古籍里出现
    「必」字很正常）。判据 6 约束的是本项目生成的文案。
    """
    parts = [warm.get("one_liner") or "", warm.get("badge") or ""]
    parts.extend(warm.get("reply") or [])
    ec = warm.get("energy_card") or {}
    parts.append(ec.get("element_note") or "")
    parts.extend(ec.get("basis") or [])
    for d in warm.get("details") or []:
        parts.append(d.get("title") or "")
        parts.extend(d.get("lines") or [])
    return "\n".join(parts)


def _cases():
    """固定输入集：与 baseline_voice 的用例对齐（同一批输入两个角度量）。"""
    from fastapi.testclient import TestClient

    from web.app import app

    client = TestClient(app)
    base = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女"}
    out = []
    for q in ("感情运怎么样？", "事业运如何？", "财运怎么样？", "考研能上吗？",
              "身体状态如何？", "我该养猫还是养狗？", None):
        payload = dict(base)
        if q:
            payload["question"] = q
        r = client.post("/api/bazi", json=payload)
        assert r.status_code == 200, (q, r.status_code, r.text[:200])
        out.append((f"bazi.q={q!r}", q, r.json()))
    for q in ("这事能成吗？", None):
        payload = {"method": "coins", "seed": 42}
        if q:
            payload["question"] = q
        r = client.post("/api/liuyao", json=payload)
        assert r.status_code == 200, (q, r.status_code)
        out.append((f"liuyao.q={q!r}", q, r.json()))
    r = client.post("/api/tarot", json={"seed": 42, "n": 3,
                                       "question": "最近的感情走向？"})
    assert r.status_code == 200
    out.append(("tarot.spread3", "最近的感情走向？", r.json()))
    return client, out


# R219b（P0-4）：_clean_history 随历史记录功能删除（/api/bazi 不再写 history.db）。


def run(inject: str | None = None) -> tuple[int, list[str]]:
    """跑判据 1–8。inject 非空时把它塞进 L0（阳性对照用）。"""
    client, cases = _cases()
    problems: list[str] = []

    for name, question, body in cases:
        warm = body.get("warm")
        if not isinstance(warm, dict):
            problems.append(f"[判据 1] {name}: 响应缺 warm 键")
            continue
        if inject:
            warm = dict(warm, one_liner=(warm.get("one_liner") or "") + inject)

        l0 = warm.get("one_liner") or ""
        # 判据 2
        if not l0:
            problems.append(f"[判据 2] {name}: one_liner 为空")
        elif len(l0) > L0_MAX:
            problems.append(f"[判据 2] {name}: one_liner {len(l0)} 字 > "
                            f"{L0_MAX}：{l0!r}")
        # 判据 1：首屏第一段就是回应，且有提问时须提到提问的主题
        reply = warm.get("reply") or []
        if not reply:
            problems.append(f"[判据 1] {name}: reply 为空")
        keys = list(warm)
        if keys and keys.index("one_liner") > keys.index("details"):
            problems.append(f"[判据 1] {name}: one_liner 排在 details 之后")
        if question and reply:
            topic_words = re.findall(r"[\u4e00-\u9fff]{2}", question)
            if not any(w in reply[0] or w in l0 for w in topic_words):
                problems.append(f"[判据 1] {name}: 首段未提到提问主题\n"
                                f"        提问 {question!r} / 首段 {reply[0]!r}")
        # 判据 3：首屏（括号外）术语 ≤3
        screen = _bracket_stripped(_first_screen(warm))
        hits = [t for t in TERMS if t in screen]
        n_terms = sum(screen.count(t) for t in TERMS)
        if n_terms > 3:
            problems.append(f"[判据 3] {name}: 首屏术语 {n_terms} 次 > 3 "
                            f"（命中 {hits}）")
        # 判据 4：依据在 basis 里（可折叠），且**逐字**取自 interpreter
        interp = body.get("interpretation") or {}
        pro_lines = "\n".join(
            "\n".join(s.get("lines") or [])
            for s in interp.get("sections") or [])
        for d in warm.get("details") or []:
            for b in d.get("basis") or []:
                frag = b.replace("依据：", "", 1)
                if frag and frag not in pro_lines:
                    problems.append(f"[判据 4] {name}: basis 被改写，"
                                    f"专业输出里找不到原文：{frag[:40]!r}")
        # 判据 6：禁用词
        prose = _all_prose(warm)
        for w in BANNED:
            if w in prose:
                problems.append(f"[判据 6] {name}: 命中禁用词 {w!r}")
        # 判据 7：免责含「仅供娱乐」且不压轴
        badge = warm.get("badge") or ""
        if "仅供娱乐" not in badge:
            problems.append(f"[判据 7] {name}: badge 未含「仅供娱乐」：{badge!r}")
        if keys and keys.index("badge") >= len(keys) - 1:
            problems.append(f"[判据 7] {name}: badge 是最后一个字段（压轴收尾）")
        if keys and "details" in keys and keys.index("badge") > keys.index("details"):
            problems.append(f"[判据 7] {name}: badge 排在 details 之后")
        # 判据 15（顺带）：citations 逐字节复用
        if warm.get("citations") != (interp.get("citations") or []):
            problems.append(f"[判据 15] {name}: citations 未逐字节复用 "
                            f"interpretation")

    # 判据 5：同输入同输出（两次请求逐字节相等）
    b1 = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                       "hour": 14, "gender": "女",
                                       "question": "感情运怎么样？"}).json()
    b2 = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                       "hour": 14, "gender": "女",
                                       "question": "感情运怎么样？"}).json()
    if b1.get("warm") != b2.get("warm"):
        problems.append("[判据 5] warm 非确定性：同输入两次输出不等")

    # 判据 8：六爻对提问给描述性回应，且专业分支原文仍在（判据 9 交叉验证）
    ly = client.post("/api/liuyao", json={"method": "coins", "seed": 42,
                                         "question": "这事能成吗？"}).json()
    lw = ly.get("warm") or {}
    lreply = " ".join(lw.get("reply") or [])
    if not lreply:
        problems.append("[判据 8] 六爻 warm reply 为空")
    else:
        if "不代为断事" in lreply:
            problems.append("[判据 8] 六爻 warm 仍在拒答（含「不代为断事」）")
        if "这事能成吗？" not in lreply:
            problems.append("[判据 8] 六爻 warm 未回应提问原文")
        if "卦" not in lreply:
            problems.append("[判据 8] 六爻 warm 未描述卦象坐标")
    pro = " ".join(" ".join(s.get("lines") or [])
                   for s in (ly.get("interpretation") or {}).get("sections") or [])
    if "不代为断事" not in pro:
        problems.append("[判据 9] 六爻**专业**分支原文被改动（应保持拒答原文）")

    return (1 if problems else 0), problems


def self_check() -> int:
    """阳性对照：注入禁用词与超长 L0，必须被抓到。"""
    code, problems = run(inject="，你会脱单的，一定会")
    banned_hit = any("[判据 6]" in p for p in problems)
    len_hit = any("[判据 2]" in p for p in problems)
    if code == 0:
        print("self-check FAIL: 注入禁用词后仍返回 0 —— 闸门是假的",
              file=sys.stderr)
        return 1
    if not banned_hit:
        print("self-check FAIL: 未抓到禁用词（判据 6 失效）", file=sys.stderr)
        for p in problems[:6]:
            print("  " + p, file=sys.stderr)
        return 1
    print(f"self-check PASS: 注入「你会脱单/一定会」被抓到 "
          f"（判据 6 命中{'，判据 2 超长也命中' if len_hit else ''}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="check_warm_voice", description=__doc__)
    ap.add_argument("--self-check", action="store_true", help="阳性对照")
    opts = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if opts.self_check:
        return self_check()

    code, problems = run()
    if code:
        print(f"check_warm_voice FAIL: {len(problems)} 处不达标", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("check_warm_voice PASS: 判据 1/2/3/4/5/6/7/8 全部达标 "
          "(10 个固定用例 × 8 条判据)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
