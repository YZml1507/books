"""web/check_plain_first.py — specs/005 判据 1–8 的自测闸门（优化轨 R185b）。

**与审查轨 `probes/probe_first_screen.py` 的关系**：那个是验收闸门，跑**一个**
用例（1998-07-20 女 + 感情运）。本文件是我方施工侧的自测，跑**五个**用例。

为什么必须多用例：R185b 的 L1 方案（按书组头平铺）在 7 书 / 8 书两案都通过
（+257 / +61px），我据此以为"书数越多越高、最坏 8 书还有余量"——直到测第三个
用例（6 书）才发现 **3,288px = 5 屏 FAIL**。组头文本在 375px 下换行、且那一案
白话段更长，高度**不随书数单调**。单案例验证正是让它漏过的原因（D-241b）。

判据（来源 `specs/005-plain-first/spec.md` §Success Criteria，R129a 订正口径）：

    1  一句话结论**相对提交后视口**的偏移 ∈ [0, 812]
    2  warm 结果区 ≤4 屏（≤3,248px），且**余量 ≥200px**（防边缘通过）
    3  默认可见最长文本块 ≤400 字
    4  古籍原文默认可见字数占结果区 ≤40%
    4b 折叠 vs 删除：DOM 里定位到的引文段数 == API 返回段数
    5  同一段古籍只渲染一次（.cite-body 数 == API 段数）
    6  折叠态下每段原文仍可从 textContent 取到
    7  折叠态下每条出处仍可从 textContent 取到
    8  展开后原文与 fixture 逐字节一致

复现命令：
    <py> web\\check_plain_first.py                # 五用例 × 8 判据
    <py> web\\check_plain_first.py --freeze       # 冻结 fixture（一次性）
    <py> web\\check_plain_first.py --self-check   # 阳性对照：篡改须被抓到
退出码：0 全绿；1 有未达标项；2 环境不可用。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BASELINE_DIR = os.path.join(_ROOT, "web", "baselines")
FIXTURE = os.path.join(BASELINE_DIR, "plain_first_fixture.json")

VIEWPORT = {"width": 375, "height": 812}
MAX_ONELINER_VP = 812        # 判据 1：相对视口，提交后无需滚动即可见
MAX_RESULT_PX = 812 * 4      # 判据 2：≤4 屏
MIN_MARGIN_PX = 200          # 判据 2 的余量下限（L1 曾以 −40/+61px 边缘失败）
MAX_BLOCK_CHARS = 400        # 判据 3
MAX_GUJI_SHARE = 40          # 判据 4

# 五个用例：覆盖 6/7/8 部书、有/无提问、不同提问主题。
# 书数不同很关键——L1 正是在 6 书那一案翻车的。
CASES = [
    ("c7_love", {"year": 1998, "month": 7, "day": 20, "hour": 14,
                 "gender": "女", "question": "感情运怎么样？"}),
    ("c8_love", {"year": 1990, "month": 5, "day": 15, "hour": 10,
                 "gender": "男", "question": "感情运怎么样？"}),
    ("c6_career", {"year": 1985, "month": 12, "day": 3, "hour": 6,
                   "gender": "女", "question": "事业运怎么样？",
                   # R211b：钉住问事日期——当日干支影响流日段行数（实测
                   # 08-23→3,039px / 08-24→3,114px），不钉则判据 2 跨日假漂移。
                   "ask_date": "2026-09-04"}),  # 2 行流日，实测最短文本（25 字）
    ("c6_health", {"year": 1976, "month": 9, "day": 9, "hour": 0,
                   "gender": "女", "question": "健康如何？"}),
    ("c8_noq", {"year": 1990, "month": 5, "day": 15, "hour": 10,
                "gender": "男"}),
]

# 度量脚本。**刻意与 probe_first_screen 的算法保持一致**（含 isHidden 的
# details/hidden/display/visibility/content-visibility 五支、textContent 定位），
# 这样我方自测绿而对方闸门红时，差异只可能来自用例而非算法。
MEASURE = r"""
([needle, gujiHeads, vh]) => {
  const r = document.getElementById('result');
  if (!r) return { error: 'no #result' };
  const norm = (s) => (s || '').replace(/\s+/g, '');
  const isHidden = (el, box) => {
    if (el.offsetParent === null) return true;
    if (box && box.height === 0) return true;
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      if (p.tagName === 'DETAILS' && !p.open) return true;
      if (p.hasAttribute && p.hasAttribute('hidden')) {
        if (getComputedStyle(p).display === 'none') return true;
      }
      const st = getComputedStyle(p);
      if (st.display === 'none' || st.visibility === 'hidden') return true;
      if (st.contentVisibility === 'hidden') return true;
    }
    return false;
  };
  let onel = null;
  const n = norm(needle);
  if (n) {
    let best = null;
    r.querySelectorAll('*').forEach(e => {
      if (e.children.length === 0 && norm(e.textContent).includes(n)) {
        const b = e.getBoundingClientRect();
        const y = Math.round(b.top + window.scrollY);
        if (best === null || y < best.y) {
          best = { y, y_viewport: Math.round(b.top), text: e.textContent.trim() };
        }
      }
    });
    onel = best;
  }
  let gujiChars = 0, gujiN = 0, gujiHidden = 0;
  const counted = new Set();
  gujiHeads.forEach(head => {
    const h = norm(head).slice(0, 22);
    if (!h) return;
    const hits = [];
    r.querySelectorAll('*').forEach(e => {
      if (!norm(e.textContent).includes(h)) return;
      let childHas = false;
      for (const c of e.querySelectorAll('*')) {
        if (norm(c.textContent).includes(h)) { childHas = true; break; }
      }
      if (!childHas) hits.push(e);
    });
    hits.forEach(e => {
      if (counted.has(e)) return;
      counted.add(e);
      gujiN += 1;
      const b = e.getBoundingClientRect();
      if (isHidden(e, b)) gujiHidden += 1;
      else gujiChars += (e.textContent || '').length;
    });
  });
  let worst = { chars: 0, head: '' };
  r.querySelectorAll('*').forEach(e => {
    if (e.children.length > 0) return;
    const b = e.getBoundingClientRect();
    if (isHidden(e, b)) return;
    const t = (e.textContent || '').trim();
    if (t.length > worst.chars) {
      worst = { chars: t.length, head: t.slice(0, 40).replace(/\n/g, ' ') };
    }
  });
  const rb = r.getBoundingClientRect();
  const ec = r.querySelector('.energy-card');
  return {
    result_h: Math.round(rb.height),
    result_chars: (r.innerText || '').trim().length,
    result_y_viewport: Math.round(rb.top),
    oneliner: onel,
    energy_vp: ec ? Math.round(ec.getBoundingClientRect().top) : null,
    guji: { n_found: gujiN, n_hidden: gujiHidden, visible_chars: gujiChars },
    worst_block: worst,
    n_cite_body: r.querySelectorAll('.cite-body').length,
    n_ev_item: r.querySelectorAll('.ev-item').length,
    textContent: (r.textContent || '').replace(/\s+/g, ''),
  };
}
"""

# 展开全部折叠层，取每段 .cite-body 的 textContent（判据 8 逐字节比对用）
EXPAND_ALL = r"""
() => {
  const r = document.getElementById('result');
  r.querySelectorAll('[hidden]').forEach(e => { e.hidden = false; });
  r.querySelectorAll('details').forEach(d => { d.open = true; });
  return Array.from(r.querySelectorAll('.cite-body'))
              .map(e => e.textContent);
}
"""


def free_port(p: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) != 0


def http_json(port: int, path: str, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
    conn.request("POST", path, body=json.dumps(body),
                 headers={"Content-Type": "application/json"})
    return json.loads(conn.getresponse().read())


class Server:
    """临时起一个 uvicorn，用完关掉；不抢占他人端口。"""

    def __init__(self, lo: int = 8600, hi: int = 8620):
        self.port = next((p for p in range(lo, hi) if free_port(p)), None)
        self.proc = None

    def __enter__(self):
        if self.port is None:
            raise RuntimeError("无空闲端口")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([_ROOT, os.path.join(_ROOT, "src")])
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "web.app:app", "--host",
             "127.0.0.1", "--port", str(self.port), "--log-level", "warning"],
            cwd=_ROOT, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)
        for _ in range(120):
            try:
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
                c.request("GET", "/api/health")
                if c.getresponse().status == 200:
                    return self
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("服务未就绪")

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _submit(page, port: int, payload: dict):
    page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
    page.wait_for_timeout(1200)
    page.click(".func-card[data-view='bazi']")
    page.wait_for_selector("#view-bazi.active", timeout=5000)
    for k in ("year", "month", "day", "hour"):
        page.fill(f"#{k}", str(payload[k]))
    page.select_option("#gender", payload["gender"])
    if payload.get("question"):
        page.fill("#question", payload["question"])
    # R211b：钉住 ask_date——流日段行数随当日干支与四柱的冲合刑害变化
    # （2026-08-23 己巳日 2 行 3,039px → 08-24 庚午日 3 行 3,114px，
    # c6_career 余量 134px<200 假 FAIL）。固定问事日期让判据 2 可复现。
    if payload.get("ask_date"):
        page.evaluate(
            "() => { const d = document.querySelector('#baziAdvanced');"
            " if (d && !d.open) d.open = true; }")
        page.fill("#ask_date", str(payload["ask_date"]))
    page.click("#submit")
    for _ in range(60):
        page.wait_for_timeout(400)
        if len((page.inner_text("#result") or "").strip()) > 80:
            break
    page.wait_for_timeout(700)


def collect(inject_break: str | None = None) -> dict:
    """跑五个用例，返回 {case_id: {api..., dom...}}。"""
    from playwright.sync_api import sync_playwright

    # R219b（P0-4）：/api/bazi 不再写 history.db（历史记录功能整体删除），
    # 原 hist0 基线 + finally 清理段随之移除。
    out: dict = {}
    try:
        with Server() as srv, sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_context(viewport=VIEWPORT).new_page()
            for cid, payload in CASES:
                api = http_json(srv.port, "/api/bazi", payload)
                warm = api.get("warm") or {}
                ev = api.get("evidence") or []
                _submit(page, srv.port, payload)
                if inject_break == "delete":
                    # 阳性对照：真删掉两段原文（模拟"折叠退化成删除"）
                    page.evaluate(
                        """() => { const b = document.querySelectorAll('.cite-body');
                             for (let i = 0; i < 2 && i < b.length; i++) b[i].remove(); }""")
                elif inject_break == "expand":
                    # 阳性对照：把古籍全部展开（模拟"没有折叠"）
                    page.evaluate(
                        """() => { document.querySelectorAll('#result [hidden]')
                             .forEach(e => { e.hidden = false; }); }""")
                m = page.evaluate(MEASURE, [warm.get("one_liner") or "",
                                            [(e.get("text") or "")[:40] for e in ev],
                                            VIEWPORT["height"]])
                bodies = page.evaluate(EXPAND_ALL)
                if inject_break == "byte" and bodies:
                    bodies[0] = bodies[0][:-1] + "X"
                out[cid] = {
                    "one_liner": warm.get("one_liner") or "",
                    "n_evidence": len(ev),
                    "citations": [e.get("citation") or "" for e in ev],
                    "texts": [e.get("text") or "" for e in ev],
                    "why": [e.get("why") or "" for e in ev],
                    "dom": m,
                    "expanded": bodies,
                }
            browser.close()
    finally:
        pass                        # R219b（P0-4）：无 history 需要清理
    return out


def freeze() -> int:
    data = collect()
    payload = {
        "_note": "specs/005 判据 6/7/8 的逐字节 fixture；由 --freeze 生成。"
                 "五个用例覆盖 6/7/8 部书与有/无提问——单用例正是 L1 漏过的原因。",
        "cases": {cid: {"one_liner": d["one_liner"],
                        "n_evidence": d["n_evidence"],
                        "citations": d["citations"],
                        "texts": d["texts"],
                        "why": d["why"]}
                  for cid, d in data.items()},
    }
    os.makedirs(BASELINE_DIR, exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"frozen {len(data)} cases -> {os.path.relpath(FIXTURE, _ROOT)}")
    for cid, d in data.items():
        print(f"  {cid}: {d['n_evidence']} 段，"
              f"{sum(len(t) for t in d['texts']):,} 字")
    return 0


def _load() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def judge(data: dict, fixture: dict) -> list[str]:
    """逐用例判 8 条。返回未达标描述列表。"""
    problems: list[str] = []
    for cid, d in data.items():
        m = d["dom"]
        tag = f"[{cid}]"
        n_api = d["n_evidence"]
        # 判据 1
        onel = m.get("oneliner")
        if not onel:
            problems.append(f"{tag} 判据 1：DOM 里找不到 one_liner 文本")
        else:
            vp = onel["y_viewport"]
            if not 0 <= vp <= MAX_ONELINER_VP:
                problems.append(
                    f"{tag} 判据 1：一句话结论相对视口 {vp:,}px，"
                    f"要求 0–{MAX_ONELINER_VP}px（提交后无需滚动即可见）")
        # 判据 2（含余量）
        margin = MAX_RESULT_PX - m["result_h"]
        if m["result_h"] > MAX_RESULT_PX:
            problems.append(f"{tag} 判据 2：结果区 {m['result_h']:,}px "
                            f"> {MAX_RESULT_PX}px（4 屏）")
        elif margin < MIN_MARGIN_PX:
            problems.append(
                f"{tag} 判据 2 余量不足：{m['result_h']:,}px 余 {margin}px "
                f"< {MIN_MARGIN_PX}px。边缘通过在别的用例上就会翻车"
                f"（L1 方案在 6 书用例实测 −40px，D-241b）")
        # 判据 3
        if m["worst_block"]["chars"] > MAX_BLOCK_CHARS:
            problems.append(f"{tag} 判据 3：可见最长块 "
                            f"{m['worst_block']['chars']:,} 字 "
                            f"> {MAX_BLOCK_CHARS}（{m['worst_block']['head']!r}）")
        # 判据 4
        share = m["guji"]["visible_chars"] * 100 // max(1, m["result_chars"])
        if share > MAX_GUJI_SHARE:
            problems.append(f"{tag} 判据 4：古籍可见占比 {share}% "
                            f"> {MAX_GUJI_SHARE}%")
        # 判据 4b：折叠不是删除
        if m["guji"]["n_found"] < n_api:
            problems.append(
                f"{tag} 判据 4b：DOM 只定位到 {m['guji']['n_found']} 段，"
                f"API 返回 {n_api} 段——缺的是**被删除**而非被折叠"
                f"（宪法第三条）")
        # 判据 5：同段只渲染一次
        if m["n_cite_body"] != n_api:
            problems.append(f"{tag} 判据 5：.cite-body {m['n_cite_body']} 个 "
                            f"≠ API {n_api} 段（重复或缺失渲染）")
        if m["n_ev_item"]:
            problems.append(f"{tag} 判据 5：warm 模式仍有 {m['n_ev_item']} 个 "
                            f".ev-item（旧的平铺渲染没被移除）")
        # 判据 6/7：折叠态可核验
        full = m["textContent"]
        want = fixture["cases"].get(cid)
        if not want:
            problems.append(f"{tag} fixture 缺该用例（需重新 --freeze）")
            continue
        miss_t = [t[:24] for t in want["texts"]
                  if t and t.replace(" ", "").replace("\n", "")[:40]
                  .replace("\u3000", "") not in full.replace("\u3000", "")]
        if miss_t:
            problems.append(f"{tag} 判据 6：{len(miss_t)} 段原文取不到 {miss_t}")
        miss_c = [c for c in want["citations"]
                  if c and c.replace(" ", "") not in full]
        if miss_c:
            problems.append(f"{tag} 判据 7：{len(miss_c)} 条出处取不到 {miss_c}")
        # 判据 8：展开后每段原文逐字节等于 fixture。
        #
        # ⚠ 按**多重集**比对，不按下标——渲染是按书分组的，同一部书的段落被
        #   收拢到一起，DOM 顺序因此与 API 顺序不同。判据 8 要求的是「每段原文
        #   逐字节一致」（内容不被改写/截断），不是「顺序与 API 相同」。
        #   用下标比会把**分组**误报成**内容漂移**（本闸门第一版实测踩过：
        #   报「长度 1245 vs 887」，其实两段都在、只是位置不同）。
        #   多重集比对同样能抓住截断、改标点、丢段、重复段。
        got = d["expanded"]
        if len(got) != len(want["texts"]):
            problems.append(f"{tag} 判据 8：展开得到 {len(got)} 段，"
                            f"fixture {len(want['texts'])} 段")
        elif sorted(got) != sorted(want["texts"]):
            extra = [g[:24] for g in got if g not in want["texts"]]
            lost = [w[:24] for w in want["texts"] if w not in got]
            problems.append(
                f"{tag} 判据 8：展开内容与 fixture 不一致"
                f"（DOM 独有 {len(extra)} 段 {extra[:2]}；"
                f"fixture 独有 {len(lost)} 段 {lost[:2]}）")
    return problems


def report(data: dict) -> None:
    print(f"\n{'用例':<11}{'段':>3}{'书':>3}{'高度':>7}{'余量':>6}"
          f"{'L0视口':>8}{'能量卡':>7}{'古籍%':>6}{'最长':>6}"
          f"{'定位/折叠':>10}{'cite_body':>10}")
    for cid, d in data.items():
        m = d["dom"]
        share = m["guji"]["visible_chars"] * 100 // max(1, m["result_chars"])
        nb = len({c.split(" @")[0] for c in d["citations"]})
        onel = m.get("oneliner") or {}
        print(f"{cid:<11}{d['n_evidence']:>3}{nb:>3}{m['result_h']:>7,}"
              f"{MAX_RESULT_PX - m['result_h']:>6}"
              f"{onel.get('y_viewport', 0):>8,}{m['energy_vp'] or 0:>7,}"
              f"{share:>6}{m['worst_block']['chars']:>6}"
              f"{m['guji']['n_found']:>5}/{m['guji']['n_hidden']:<4}"
              f"{m['n_cite_body']:>10}")


def verify() -> int:
    if not os.path.exists(FIXTURE):
        print(f"check_plain_first SKIP-ENV: 缺 fixture，先跑 --freeze",
              file=sys.stderr)
        return 2
    data = collect()
    report(data)
    problems = judge(data, _load())
    if problems:
        print(f"\ncheck_plain_first FAIL: {len(problems)} 项未达标",
              file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print(f"\ncheck_plain_first PASS: {len(data)} 个用例 × 判据 1–8 全达标")
    return 0


def self_check() -> int:
    """阳性对照（宪法第三条偏离 4：没有阳性对照的闸门等于没有闸门）。

    三种注入各须被对应判据抓到：
      delete → 判据 4b/5/6（折叠退化成删除）
      expand → 判据 2/3/4（没有折叠）
      byte   → 判据 8（展开内容被改一字）
    """
    if not os.path.exists(FIXTURE):
        print("self-check SKIP-ENV: 缺 fixture", file=sys.stderr)
        return 2
    fixture = _load()
    ok = True
    for inject, want_keys in (("delete", ("判据 4b", "判据 5", "判据 6")),
                              ("expand", ("判据 2", "判据 3", "判据 4")),
                              ("byte", ("判据 8",))):
        problems = judge(collect(inject_break=inject), fixture)
        hit = [k for k in want_keys
               if any(k in p for p in problems)]
        good = bool(hit)
        print(f"  注入 {inject:<7} → {len(problems)} 项报错；"
              f"命中 {hit or '（无）'}　{'✅' if good else '❌'}")
        if not good:
            ok = False
            for p in problems[:4]:
                print(f"      {p}")
    if not ok:
        print("self-check FAIL: 有注入未被抓到——闸门失效", file=sys.stderr)
        return 1
    print("self-check PASS: 三种注入全部被对应判据抓到")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="check_plain_first", description=__doc__)
    ap.add_argument("--freeze", action="store_true", help="冻结 fixture（一次性）")
    ap.add_argument("--self-check", action="store_true", help="阳性对照")
    opts = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        import playwright.sync_api          # noqa: F401
    except ImportError:
        print("check_plain_first SKIP-ENV: playwright 未安装", file=sys.stderr)
        return 2
    if opts.freeze:
        return freeze()
    if opts.self_check:
        return self_check()
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
