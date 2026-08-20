"""web/baseline_voice.py — 判据 9 的量尺：专业模式输出逐字节冻结。

判据 9（`specs/004-warm-voice/spec.md`）要求：warm 口吻上线后，切回专业模式
必须**逐字节等于** spec 创建时的输出。本脚本就是那把尺子——先冻结，后动刀
（plan.md §0：先量尺，后动刀）。

为什么先做这个（plan.md §0 施工铁律 1）：warm 是新增分支，理论上不碰
`interpreter.py`。但"理论上不碰"不是断言，宪法第一条要求可复现命令。有了
fixture，任何一次改动碰出字节漂移，本脚本立即退出码 1。

领土（宪法第五条，plan.md §0.1 / D-236b）：本文件在 `web/` 下而非 `probes/`
——`probes/` 是审查轨独占写、优化轨禁改。审查轨若要纳入自己的闸门清单，
直接调用本脚本即可（接口就是命令行退出码），不需要改本文件。

用法：
    <py> web\\baseline_voice.py --freeze       # 冻结基线（M0 一次性）
    <py> web\\baseline_voice.py                # 比对，漂移则退出码 1
    <py> web\\baseline_voice.py --self-check   # 阳性对照：篡改一字须被抓到
    <py> web\\baseline_voice.py --freeze-dom   # 冻结前端专业分支渲染快照
其中 <py> = .venv\\Scripts\\python.exe

闸门纪律（PHASE.md）：失败退出 1、成功退出 0，且带阳性对照——
「永远返回 0 的闸门等于没有闸门」（U-08 教训）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "src"))

BASELINE_DIR = os.path.join(_ROOT, "web", "baselines")
BASELINE = os.path.join(BASELINE_DIR, "voice_baseline.json")
DOM_BASELINE = os.path.join(BASELINE_DIR, "pro_render_baseline.json")


# ---------------------------------------------------------------------------
# 固定输入集（T0.1）：覆盖每个产出 interpretation 的代码路径
#
# 选样原则：每个 interpret_* 函数的每条分支各至少一例，且含"有提问/无提问"
# 两态——判据 1（首节回应提问）只在有提问时才有意义，warm 改动最可能在
# 这条分支上碰坏专业输出。
# ---------------------------------------------------------------------------
BAZI_BASE = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女"}

CASES: tuple[dict, ...] = (
    # 八字 day：spec §「我自己重跑了诊断样例」用的就是这一组，
    # 保持一致以便与 spec 的实测记录交叉核对
    {"id": "bazi.day.q_love", "kind": "bazi",
     "payload": dict(BAZI_BASE, question="感情运怎么样？")},
    {"id": "bazi.day.q_career", "kind": "bazi",
     "payload": dict(BAZI_BASE, question="事业运如何？")},
    {"id": "bazi.day.no_q", "kind": "bazi", "payload": dict(BAZI_BASE)},
    {"id": "bazi.day.q_unmatched", "kind": "bazi",
     "payload": dict(BAZI_BASE, question="我该养猫还是养狗？")},
    {"id": "bazi.life", "kind": "bazi",
     "payload": dict(BAZI_BASE, scope="life", question="一生大运如何？")},
    {"id": "bazi.range", "kind": "bazi",
     "payload": dict(BAZI_BASE, scope="range", range_start="2026-08-19",
                     range_end="2026-08-23", question="这几天顺不顺？")},
    {"id": "bazi.male.day", "kind": "bazi",
     "payload": {"year": 1990, "month": 5, "day": 15, "hour": 10,
                 "gender": "男", "question": "财运怎么样？"}},
    # 六爻：判据 8 的当前状态（拒答原文）就冻在这里
    {"id": "liuyao.coins.q", "kind": "liuyao",
     "payload": {"method": "coins", "seed": 42, "question": "这事能成吗？"}},
    {"id": "liuyao.coins.no_q", "kind": "liuyao",
     "payload": {"method": "coins", "seed": 42}},
    {"id": "liuyao.time.q", "kind": "liuyao",
     "payload": {"method": "time", "year": 2026, "month": 8, "day": 16,
                 "hour": 10, "question": "适合搬家吗？"}},
    # 塔罗：3 张牌阵（含 position）与单张快速入口
    {"id": "tarot.spread3", "kind": "tarot",
     "payload": {"seed": 42, "n": 3, "question": "最近的感情走向？"}},
    {"id": "tarot.draw1", "kind": "tarot_draw",
     "payload": {"seed": 42, "n": 1, "question": "今天运气如何？"}},
    # research：有命中 / 拒答两分支（判据 15 引文逐字节不变）
    {"id": "research.hit", "kind": "ask",
     "payload": {"q": "潛龍勿用", "max_addresses": 2}},
    {"id": "research.wuwei", "kind": "ask",
     "payload": {"q": "無爲", "max_addresses": 2}},
)


def _clean_history(max_id_before: int) -> None:
    """/api/bazi 会写 history.db（D-039 授权）——自测须清理本次新增行。

    L-22 教训：写端点自测不得污染真实库。
    """
    from guji import history as history_db

    for rec in history_db.list_records(limit=50):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])


def collect() -> dict:
    """跑固定输入集，抽出每例的 interpretation 全量快照（纯读，不改产品代码）。"""
    from fastapi.testclient import TestClient

    from guji import history as history_db
    from web.app import app

    client = TestClient(app)
    rows = history_db.list_records(limit=1)
    max_id_before = rows[0]["id"] if rows else 0

    out: dict = {}
    for case in CASES:
        kind, payload = case["kind"], case["payload"]
        if kind == "bazi":
            resp = client.post("/api/bazi", json=payload)
        elif kind == "liuyao":
            resp = client.post("/api/liuyao", json=payload)
        elif kind == "tarot":
            resp = client.post("/api/tarot", json=payload)
        elif kind == "tarot_draw":
            resp = client.post("/api/tarot/draw", json=payload)
        elif kind == "ask":
            resp = client.post("/api/ask", json=payload)
        else:
            raise AssertionError(f"unknown kind {kind}")
        assert resp.status_code == 200, (case["id"], resp.status_code,
                                        resp.text[:200])
        body = resp.json()
        interp = body.get("interpretation")
        # research 拒答时 interpretation 可能为 None——那也是要冻结的状态
        out[case["id"]] = {
            "interpretation": interp,
            # 判据 15：引文与出处逐字节不变。citations 在 interpretation 里，
            # 但 evidence 是独立字段（R118a-03 修的就是它的 citation），一并冻。
            "evidence_citations": [e.get("citation")
                                   for e in (body.get("evidence") or [])],
        }
    _clean_history(max_id_before)
    return out


def _digest(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def freeze() -> int:
    os.makedirs(BASELINE_DIR, exist_ok=True)
    data = collect()
    doc = {
        "_note": ("判据 9 基线：专业模式输出逐字节快照。由 "
                  "web/baseline_voice.py --freeze 生成，勿手改。"
                  "漂移即 warm 改动碰坏了专业输出。"),
        "_frozen_at_commit": os.environ.get("BASELINE_COMMIT", "see git log"),
        "cases": data,
        "sha256": _digest(data),
    }
    with open(BASELINE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"frozen {len(data)} cases -> {os.path.relpath(BASELINE, _ROOT)}")
    print(f"sha256 = {doc['sha256']}")
    return 0


def _load() -> dict:
    if not os.path.exists(BASELINE):
        print("baseline_voice FAIL: 基线不存在，先跑 --freeze", file=sys.stderr)
        raise SystemExit(1)
    with open(BASELINE, encoding="utf-8") as f:
        return json.load(f)


def _diff_case(cid: str, want, got) -> list[str]:
    """逐字段找出漂移点，报告要能直接定位——不只说"不相等"。"""
    problems: list[str] = []
    if want == got:
        return problems
    wi = (want or {}).get("interpretation") or {}
    gi = (got or {}).get("interpretation") or {}
    if wi.get("text") != gi.get("text"):
        wt, gt = wi.get("text") or "", gi.get("text") or ""
        at = next((i for i in range(min(len(wt), len(gt))) if wt[i] != gt[i]),
                  min(len(wt), len(gt)))
        problems.append(
            f"{cid}: interpretation.text 漂移 @char {at}\n"
            f"      基线: {wt[max(0, at - 30):at + 40]!r}\n"
            f"      现在: {gt[max(0, at - 30):at + 40]!r}")
    ws = [s.get("title") for s in (wi.get("sections") or [])]
    gs = [s.get("title") for s in (gi.get("sections") or [])]
    if ws != gs:
        problems.append(f"{cid}: sections 标题序列变化\n"
                        f"      基线: {ws}\n      现在: {gs}")
    else:
        for i, (a, b) in enumerate(zip(wi.get("sections") or [],
                                       gi.get("sections") or [])):
            if a.get("lines") != b.get("lines"):
                problems.append(f"{cid}: sections[{i}]«{a.get('title')}» "
                                f"行内容变化\n      基线: {a.get('lines')}\n"
                                f"      现在: {b.get('lines')}")
    if wi.get("citations") != gi.get("citations"):
        problems.append(f"{cid}: citations 漂移（判据 15 引文必须逐字节不变）")
    for key in ("ok", "kind", "engine", "basis", "disclaimer"):
        if wi.get(key) != gi.get(key):
            problems.append(f"{cid}: interpretation.{key} 漂移: "
                            f"{wi.get(key)!r} -> {gi.get(key)!r}")
    if (want or {}).get("evidence_citations") != (got or {}).get("evidence_citations"):
        problems.append(f"{cid}: evidence[].citation 漂移"
                        f"（判据 15 / R118a-03 回归）")
    if not problems:
        problems.append(f"{cid}: 快照不等但未定位到具体字段（结构变化？）")
    return problems


def verify(current: dict | None = None) -> tuple[int, list[str]]:
    doc = _load()
    want = doc["cases"]
    got = current if current is not None else collect()
    problems: list[str] = []
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    if missing:
        problems.append(f"用例缺失（基线有、现在跑不出）: {missing}")
    if extra:
        problems.append(f"用例新增（未登记进基线）: {extra}")
    for cid in sorted(set(want) & set(got)):
        problems.extend(_diff_case(cid, want[cid], got[cid]))
    return (1 if problems else 0), problems


def self_check() -> int:
    """阳性对照：把基线里的一个字改掉，verify 必须抓到。

    没有阳性对照的闸门等于没有闸门（宪法第三条偏离 4）。
    """
    doc = _load()
    cases = json.loads(json.dumps(doc["cases"], ensure_ascii=False))
    cid = "bazi.day.q_love"
    text = (cases[cid]["interpretation"] or {}).get("text") or ""
    if not text:
        print("self-check FAIL: 样例 text 为空，无法做阳性对照", file=sys.stderr)
        return 1
    # 篡改一个字符（把第一个「四」换成「肆」，或退化为改首字）
    idx = text.find("四")
    mutated = (text[:idx] + "肆" + text[idx + 1:]) if idx >= 0 \
        else ("X" + text[1:])
    cases[cid]["interpretation"]["text"] = mutated
    code, problems = verify(current=cases)
    if code == 0:
        print("self-check FAIL: 篡改一字后 verify 仍返回 0 —— 闸门是假的",
              file=sys.stderr)
        return 1
    hit = any("interpretation.text 漂移" in p for p in problems)
    print("self-check PASS: 篡改一字被抓到"
          + ("（且定位到 text 漂移）" if hit else "（但未定位到 text）"))
    return 0 if hit else 1


def freeze_dom() -> int:
    """T0.3：前端专业分支渲染快照（判据 9 的「渲染层未变」辅证）。

    只抓结构指纹（节点计数 + 关键文本），不抓像素——像素受字体/DPI 影响，
    不是可复现断言。真浏览器点击行为由审查轨 probe_ui_smoke 负责，本函数
    只留一份 warm 上线前的专业渲染形态，供 M1 之后比对「pro 分支没被改」。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("freeze-dom SKIP-ENV: playwright 未安装", file=sys.stderr)
        return 2
    import socket
    import subprocess
    import time

    port = 8207          # 避开 8123（用户查看）与 8199（审查轨 probe）
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([_ROOT, os.path.join(_ROOT, "src")])
    env["PYTHONIOENCODING"] = "utf-8"
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(90):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(1)
        else:
            print("freeze-dom SKIP-ENV: 服务未就绪", file=sys.stderr)
            return 2
        snap: dict = {}
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(2500)
            # 排盘（专业分支的主战场）
            page.fill("#year", str(BAZI_BASE["year"]))
            page.fill("#month", str(BAZI_BASE["month"]))
            page.fill("#day", str(BAZI_BASE["day"]))
            page.fill("#hour", str(BAZI_BASE["hour"]))
            page.select_option("#gender", BAZI_BASE["gender"])
            page.fill("#question", "感情运怎么样？")
            page.click("#submit")
            page.wait_for_function(
                "() => { const n = document.getElementById('result');"
                " return n && n.textContent.length > 500; }", timeout=90000)
            snap["bazi.result"] = _dom_fingerprint(page, "#result")
            for view, btn, out in (("liuyao", "#lySubmit", "#lyResult"),
                                   ("tarot", "#trSubmit", "#trResult")):
                page.click(f'.func-card[data-view="{view}"]')
                page.wait_for_timeout(200)
                page.click(btn)
                page.wait_for_function(
                    "id => { const n = document.querySelector(id);"
                    " return n && n.textContent.length > 200; }",
                    arg=out, timeout=60000)
                snap[f"{view}.result"] = _dom_fingerprint(page, out)
            browser.close()
        os.makedirs(BASELINE_DIR, exist_ok=True)
        with open(DOM_BASELINE, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"_note": "专业模式渲染结构指纹（判据 9 辅证）；"
                                "由 --freeze-dom 生成",
                       "views": snap}, f, ensure_ascii=False,
                      indent=1, sort_keys=True)
            f.write("\n")
        print(f"frozen {len(snap)} views -> "
              f"{os.path.relpath(DOM_BASELINE, _ROOT)}")
        for k, v in sorted(snap.items()):
            print(f"  {k}: {v['chars']} chars, {v['nodes']} nodes, "
                  f"strong_depth={v['strong_depth']}")
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()


def _dom_fingerprint(page, selector: str) -> dict:
    return page.evaluate(
        """sel => {
             const n = document.querySelector(sel);
             if (!n) return null;
             const depth = el => el.querySelectorAll('strong strong strong').length ? 3
                              : el.querySelectorAll('strong strong').length ? 2
                              : el.querySelectorAll('strong').length ? 1 : 0;
             const txt = n.textContent.trim();
             return {
               chars: txt.length,
               nodes: n.querySelectorAll('*').length,
               strong_depth: depth(n),
               comments: (function c(e){let k=0;e.childNodes.forEach(x=>{
                 if(x.nodeType===8)k++; if(x.childNodes)k+=c(x);});return k;})(n),
               h3: Array.from(n.querySelectorAll('h3')).map(x=>x.textContent.trim()),
               head: txt.slice(0, 160)
             };
           }""", selector)


def main() -> int:
    ap = argparse.ArgumentParser(prog="baseline_voice", description=__doc__)
    ap.add_argument("--freeze", action="store_true", help="冻结基线（M0 一次性）")
    ap.add_argument("--freeze-dom", action="store_true",
                    help="冻结前端专业渲染快照（T0.3）")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照：篡改一字须被抓到")
    opts = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if opts.freeze:
        return freeze()
    if opts.freeze_dom:
        return freeze_dom()
    if opts.self_check:
        return self_check()

    code, problems = verify()
    if code:
        print(f"baseline_voice FAIL: {len(problems)} 处漂移"
              f"（判据 9：专业模式必须逐字节不变）", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    doc = _load()
    print(f"baseline_voice PASS: {len(doc['cases'])} 个用例逐字节一致 "
          f"(sha256 {doc['sha256'][:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
