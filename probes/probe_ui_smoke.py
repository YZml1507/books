"""probe_ui_smoke.py — 真浏览器 UI 冒烟闸门（审查轨 R118a，D-128a）。

**为什么存在**：`web/app.py --selftest` 的 130 条断言全是后端 TestClient 断言，
对前端零覆盖。这正是「按钮全坏了自测却全绿」的成因：`index.html` 里 49 处把
`$()` 函数当对象访问（`$.rq.value`），是**运行时** TypeError——只有真的加载页面、
真的点按钮才会现形，任何后端断言都看不见。

**做法**：
  1. 用 uvicorn 在**显式 --port 8199** 起真服务（不碰 8123，修复窗口正在肉眼
     看那个端口；也绝不调用 web_launcher.kill_stale()，它会 taskkill 8123）；
  2. playwright chromium 真加载 `/`，全程挂 console / pageerror 监听；
  3. 逐个用例：切到目标视图 → 点按钮 → 等结果容器出现内容 →
     断言（a）容器非空且非"…中"占位、（b）本次点击期间零 console.error、
     零未捕获异常；
  4. 标签页用例：点标签 → 断言对应面板真的 display 可见（切换生效）。

**判据设计（为什么不只看 console）**：`index.html` 每个 handler 都是
`try{...}catch(ex){ r.innerHTML = '失败：'+ex.message }`——TypeError 被 catch 吞掉，
console 干净。所以容器内容必须**同时**排除失败文案（"失败"/"不可用"），
否则"页面显示计算失败"会被判成通过。这是本 probe 唯一能自欺的地方，已封住。

**污染纪律（L-22）**：八字排盘会写 history.db。probe 记录基线行数，退出前删除
本轮新增行并复验回到基线，删不干净则整体判失败。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_ui_smoke.py
可选：--headed 看真实点击过程；--port N 换端口；--keep 保留 logs/ 截图。
退出码：0 全绿；1 有用例失败；2 环境不可用（chromium 未装 / 服务起不来）。
截图与失败详情：logs/ui_smoke/
"""
from __future__ import annotations

import http.client
import os
import re
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src"), os.path.join(ROOT, "web")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = 8199          # 显式端口，绝不用 8123（修复窗口的肉眼查看页面）
CASE_BUDGET_S = 25.0  # 单用例等结果预算；bge 首次加载已由 prewarm 摊掉
LOGDIR = os.path.join(ROOT, "logs", "ui_smoke")
PLACEHOLDER_RE = re.compile(r"^\s*(检索中|研究中|定位中|比对中|加载中|创建中|"
                            r"摇卦中|查询中|起名中|测算中|抽牌中|计算中|刷新中)…?\s*$")
# 失败文案只在 `.no-evidence` 元素里出现（index.html 全部 handler 的 catch 分支
# 与空结果分支都渲染成 `<div class="no-evidence">…`）。
# **不要**在整个容器文本里搜"不可用"之类的词——古籍原文里就有"前六時干辰入墓
# 亦不可用"，全文搜会把正常渲染判成失败（本 probe 第一版实测踩过，已修正）。
FAILURE_RE = re.compile(r"失败|不可用|无命中|无发现|暂无")
# JS `String({..})` 的字面量。出现即渲染错误：前端把 object 塞进了 esc()。
OBJECT_LITERAL = "[object Object]"
ACTION_TIMEOUT_MS = 4000   # 短超时：标签坏了会导致成片元素不可见，30s×N 跑不完

# ---------------------------------------------------------------------------
# 用例表：(名字, 视图, 按钮选择器, 结果容器选择器, 视图内先切的标签)
# 覆盖 index.html 全部 15 个提交按钮 + 9 个 rtab + 3 个 rsec2 子标签。
# ---------------------------------------------------------------------------
BUTTON_CASES = [
    # name,            view,      tab(data-rsec 值或 None), button,        result
    ("bazi",           "bazi",    None,            "#submit",        "#result"),
    ("news.refresh",   "bazi",    None,            "#newsRefresh",   "#newsList"),
    ("search",         "read",    "rsec-search",   "#searchBtn",     "#searchResult"),
    ("research",       "read",    "rsec-research", "#researchBtn",   "#researchResult"),
    ("addr",           "read",    "rsec-addr",     "#addrBtn",       "#addrResult"),
    ("compare",        "read",    "rsec-compare",  "#compareBtn",    "#compareResult"),
    ("works",          "read",    "rsec-works",    "#worksBtn",      "#worksResult"),
    ("threads",        "read",    "rsec-threads",  "#threadBtn",     "#threadResult"),
    ("compare_works",  "read",    "rsec-cw",       "#cwBtn",         "#cwResult"),
    ("concept",        "read",    "rsec-concept",  "#conceptBtn",    "#conceptResult"),
    ("liuyao",         "liuyao",  None,            "#lySubmit",      "#lyResult"),
    ("huangli",        "huangli", None,            "#hlSubmit",      "#hlResult"),
    ("qiming",         "qiming",  None,            "#qmSubmit",      "#qmResult"),
    ("taohua",         "taohua",  None,            "#thSubmit",      "#thResult"),
    ("tarot",          "tarot",   None,            "#trSubmit",      "#trResult"),
    ("hehun",          "hehun",   None,            "#hhSubmit",      "#hhResult"),
]

# 点按钮前需要填的输入（用固定值 → 固定结果，可命令复验）
FILL = {
    "search":        {"#rq": "潛龍勿用"},
    "research":      {"#rq2": "無爲", "#rmax": "2"},
    "addr":          {"#aguan": "1"},
    "compare":       {"#cgua": "28", "#cyao": "九二"},
    "threads":       {"#tq": "probe_ui_smoke 线程"},
    "compare_works": {"#cwa": "KR5c0057", "#cwb": "KR5c0126", "#cwq": "無爲"},
    "concept":       {"#cq": "無爲"},
}

# 标签切换用例：点 .rtab[data-rsec=X] 后 #X 必须可见
TAB_CASES = [c[2] for c in BUTTON_CASES if c[2]] + [
    "rsec-bookstudy",
]
SUBTAB_CASES = ["bs-structure", "bs-chapter", "bs-summary"]


def free_port(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_health(port: int, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("GET", "/api/health")
            if c.getresponse().status == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    headed = "--headed" in sys.argv
    keep = "--keep" in sys.argv
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probe_ui_smoke SKIP-ENV: playwright 包未安装")
        return 2

    if not free_port(port):
        print(f"probe_ui_smoke SKIP-ENV: 端口 {port} 已被占用。"
              f"本 probe 绝不 taskkill（8123 是修复窗口的查看页面），"
              f"请换 --port 或先自行释放。")
        return 2

    os.makedirs(LOGDIR, exist_ok=True)
    from guji import history as history_db
    from guji import knowledge as kb_mod
    kb_path = os.path.join(ROOT, "data", "index", "knowledge.db")
    hist_baseline = history_db.count()
    with kb_mod.KnowledgeBase(kb_path) as kb:
        derived_baseline = kb.db.execute(
            "SELECT COALESCE(MAX(id),0) AS m FROM derived").fetchone()["m"]

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([ROOT, os.path.join(ROOT, "src"),
                                         os.path.join(ROOT, "web")])
    env["PYTHONIOENCODING"] = "utf-8"
    srv_log = open(os.path.join(LOGDIR, "server.log"), "w", encoding="utf-8")
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=os.path.join(ROOT, "web"), env=env,
        stdout=srv_log, stderr=subprocess.STDOUT)
    results: list[dict] = []
    try:
        if not wait_health(port):
            srv_log.flush()
            tail = open(os.path.join(LOGDIR, "server.log"),
                        encoding="utf-8", errors="replace").read()[-800:]
            print(f"probe_ui_smoke SKIP-ENV: 服务未在 90s 内就绪\n{tail}")
            return 2
        print(f"服务已就绪 http://127.0.0.1:{port}/  (uvicorn pid={srv.pid})")
        # 预热：/api/bazi 首请求会加载 bge 语义模型与向量缓存（web/app.py
        # 模块 docstring 明说"首请求可能较慢"）。不预热的话这段模型加载时间
        # 会算进第一个按钮用例的等待预算，把"慢"误判成"坏"。
        t0 = time.time()
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
            c.request("POST", "/api/bazi",
                      body=('{"year":1990,"month":5,"day":15,"hour":10,'
                            '"gender":"\\u7537","use_llm":false}'),
                      headers={"Content-Type": "application/json"})
            warm_status = c.getresponse().status
        except Exception as exc:
            warm_status = f"{type(exc).__name__}: {exc}"
        print(f"预热 /api/bazi -> {warm_status}  ({time.time() - t0:.1f}s)")

        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(headless=not headed)
            except Exception as exc:
                print(f"probe_ui_smoke SKIP-ENV: chromium 内核不可用：{exc}\n"
                      f"装内核：<venv>\\python.exe -m playwright install chromium")
                return 2
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.set_default_timeout(ACTION_TIMEOUT_MS)
            page = ctx.new_page()
            errors: list[str] = []
            api_calls: list[str] = []
            page.on("console", lambda m: errors.append(
                f"console.{m.type}: {m.text}") if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("request", lambda r: api_calls.append(r.url)
                    if "/api/" in r.url else None)

            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(1500)          # 首屏自动 fetch（daily/history/prefs）
            load_errors = list(errors)
            results.append({
                "name": "page.load", "ok": not load_errors,
                "detail": "; ".join(load_errors[:4]) or "首屏加载零 console.error",
            })

            def goto_view(view: str):
                page.click(f".func-card[data-view='{view}']")
                page.wait_for_selector(f"#view-{view}.active", timeout=5000)

            def force_show_rsec(sec: str) -> bool:
                """绕过坏掉的标签切换，直接让目标 .rsec 可见。

                为什么需要：`.rtab` 无事件绑定（R000a-03）使 8 个面板永不可见，
                面板内的按钮 playwright 判定 not visible 而**根本点不到**——
                那些按钮自身是好是坏就无法测量，缺陷清单会残缺，修复轨得分两
                轮才能拿到完整信息。本函数只在**测试侧**用 DOM 操作强制显示，
                **不修改 web/**（宪法第五条：审查轨对 web/ 只读），也不掩盖
                R000a-03——标签用例照原样点击、照原样判失败。
                """
                return page.evaluate(
                    """(sec) => {
                        const t = document.getElementById(sec);
                        if (!t) return false;
                        document.querySelectorAll('.rsec').forEach(
                            s => s.classList.remove('active'));
                        t.classList.add('active');
                        return true;
                    }""", sec)

            # ── 标签切换用例 ───────────────────────────────────
            goto_view("read")
            for sec in TAB_CASES:
                errors.clear()
                try:
                    page.click(f".rtab[data-rsec='{sec}']")
                    page.wait_for_timeout(250)
                    visible = page.is_visible(f"#{sec}")
                    ok = visible and not errors
                    detail = ("面板可见" if visible else f"点击后 #{sec} 仍不可见")
                    if errors:
                        detail += " | " + "; ".join(errors[:3])
                except Exception as exc:
                    ok, detail = False, f"{type(exc).__name__}: {exc}"
                results.append({"name": f"tab:{sec}", "ok": ok, "detail": detail})

            page.click(".rtab[data-rsec='rsec-bookstudy']")
            page.wait_for_timeout(250)
            for sub in SUBTAB_CASES:
                errors.clear()
                try:
                    page.click(f".rtab[data-rsec2='{sub}']")
                    page.wait_for_timeout(250)
                    active = page.eval_on_selector(
                        f".rtab[data-rsec2='{sub}']",
                        "el => el.classList.contains('active')")
                    ok = bool(active) and not errors
                    detail = ("子标签 active" if active
                              else f"点击后 {sub} 标签未 active（无切换逻辑）")
                    if errors:
                        detail += " | " + "; ".join(errors[:3])
                except Exception as exc:
                    ok, detail = False, f"{type(exc).__name__}: {exc}"
                results.append({"name": f"subtab:{sub}", "ok": ok, "detail": detail})

            # ── #dailyMore 用例（有按钮就必须有行为）────────────
            goto_view("bazi")
            errors.clear()
            before = page.content()
            try:
                page.click("#dailyMore")
                page.wait_for_timeout(600)
                changed = page.content() != before
                ok = changed and not errors
                detail = ("点击后 DOM 有变化" if changed
                          else "点击后 DOM 无任何变化（无事件处理器）")
                if errors:
                    detail += " | " + "; ".join(errors[:3])
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"name": "btn:dailyMore", "ok": ok, "detail": detail})

            # ── 按钮用例 ──────────────────────────────────────
            for name, view, tab, btn, res in BUTTON_CASES:
                errors.clear()
                forced = False
                try:
                    goto_view(view)
                    if tab:
                        page.click(f".rtab[data-rsec='{tab}']")
                        page.wait_for_timeout(200)
                        if not page.is_visible(f"#{tab}"):
                            # 标签切换坏了（R000a-03）→ 测试侧强制显示，
                            # 使本按钮自身可测。结论里显式标注，不含糊。
                            forced = force_show_rsec(tab)
                            page.wait_for_timeout(150)
                    for sel, val in FILL.get(name, {}).items():
                        page.fill(sel, val)
                    api_calls.clear()
                    page.click(btn)
                    # 等结果容器出现"非占位"内容。
                    # 早退判据（否则每个坏按钮都要白等满预算，整轮跑不完）：
                    # 点击后 2.5s 内既没发出任何 /api 请求、又已捕获到未捕获异常
                    # → 结论已定（handler 在 fetch 之前就抛了），立即判失败。
                    text, waited = "", 0.0
                    while waited < CASE_BUDGET_S:
                        page.wait_for_timeout(400)
                        waited += 0.4
                        text = (page.inner_text(res) or "").strip()
                        if text and not PLACEHOLDER_RE.match(text):
                            break
                        if waited >= 2.5 and not api_calls and errors:
                            break
                    # 失败文案只认 .no-evidence 元素内的文字（见 FAILURE_RE 注释）
                    no_ev = " ".join(
                        page.eval_on_selector_all(
                            f"{res} .no-evidence", "els => els.map(e => e.innerText)")
                        or [])
                    fail_hit = FAILURE_RE.search(no_ev)
                    obj_literal = OBJECT_LITERAL in (text or "")
                    ok = (bool(text) and not PLACEHOLDER_RE.match(text or "")
                          and not fail_hit and not obj_literal and not errors)
                    detail = f"容器 {len(text)} 字符: {text[:110]!r}"
                    if not text:
                        detail = ("结果容器点击后仍为空"
                                  + ("；且点击后零 /api 请求（handler 在 fetch "
                                     "之前就抛了）" if not api_calls else ""))
                    elif PLACEHOLDER_RE.match(text):
                        detail = (f"{CASE_BUDGET_S:.0f}s 后仍停在占位文案: "
                                  f"{text[:60]!r}")
                    elif fail_hit:
                        detail = (f".no-evidence 渲染失败文案（命中 "
                                  f"{fail_hit.group(0)!r}）: {no_ev[:140]!r}")
                    elif obj_literal:
                        k = text.find(OBJECT_LITERAL)
                        detail = (f"容器渲染出 [object Object] 字面量: "
                                  f"{text[max(0, k - 60):k + 30]!r}")
                    if errors:
                        detail += " | " + "; ".join(errors[:3])
                except Exception as exc:
                    ok, detail = False, f"{type(exc).__name__}: {exc}"
                if forced:
                    detail = ("[面板由测试侧强制显示——标签切换本身仍是"
                              "R000a-03 缺陷] " + detail)
                if not ok:
                    page.screenshot(path=os.path.join(LOGDIR, f"FAIL_{name}.png"),
                                    full_page=False)
                results.append({"name": f"btn:{name}", "ok": ok, "detail": detail})

            # ── DOM 结构完整性：模板标签必须正确闭合 ────────────
            # index.html:963 把 `</strong>` 写成 `</` + 变量，浏览器把
            # `</${esc(iv)}` 解析成注释，`<strong>` 永不闭合 → 逐条累积嵌套。
            # 判据：排盘结果区里 <strong> 的嵌套深度必须 ≤1，且不得出现
            # 由损坏标签产生的注释节点。这两条都是 DOM 事实，可复验。
            errors.clear()
            goto_view("bazi")
            try:
                page.click("#submit")
                page.wait_for_timeout(4000)
                depth = page.evaluate(
                    """() => {
                        let max = 0;
                        document.querySelectorAll('#result strong').forEach(el => {
                            let d = 0, p = el.parentElement;
                            while (p && p.id !== 'result') {
                                if (p.tagName === 'STRONG') d++;
                                p = p.parentElement;
                            }
                            if (d > max) max = d;
                        });
                        return max;
                    }""")
                comments = page.evaluate(
                    """() => {
                        const r = document.getElementById('result');
                        if (!r) return 0;
                        const it = document.createNodeIterator(
                            r, NodeFilter.SHOW_COMMENT);
                        let n = 0;
                        while (it.nextNode()) n++;
                        return n;
                    }""")
                ok = depth <= 1 and comments == 0
                detail = (f"#result 内 <strong> 最大嵌套层数={depth}（应 ≤1）、"
                          f"注释节点={comments}（应 =0）")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if not ok:
                page.screenshot(path=os.path.join(LOGDIR, "FAIL_dom_strong.png"))
            results.append({"name": "dom:bazi.strong-nesting", "ok": ok,
                            "detail": detail})

            # ── 375px 移动端视口：无横向滚动（OPTIMIZE 阶段的客观代理）──
            errors.clear()
            page.set_viewport_size({"width": 375, "height": 812})
            goto_view("bazi")
            page.wait_for_timeout(400)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - "
                "document.documentElement.clientWidth")
            page.screenshot(path=os.path.join(LOGDIR, "viewport_375.png"),
                            full_page=True)
            results.append({
                "name": "viewport.375.no-hscroll",
                "ok": overflow <= 0,
                "detail": f"横向溢出 {overflow}px（≤0 为通过）",
            })
            ctx.close()
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        srv_log.close()

    # ── 清理本轮写入（L-22）─────────────────────────────────
    cleaned = []
    n_extra = history_db.count() - hist_baseline
    if n_extra > 0:
        for rec in history_db.list_records(200)[:n_extra]:
            if history_db.delete_record(rec["id"]):
                cleaned.append(f"history#{rec['id']}")
    with kb_mod.KnowledgeBase(kb_path) as kb:
        rows = kb.db.execute("SELECT id, claim FROM derived WHERE id > ?",
                             (derived_baseline,)).fetchall()
        for row in rows:
            from guji.variants import fold, segment_cjk
            kb.db.execute("INSERT INTO derived_fts(derived_fts,rowid,seg) "
                          "VALUES('delete',?,?)",
                          (row["id"], segment_cjk(fold(row["claim"]))))
            kb.db.execute("DELETE FROM evidence WHERE derived_id=?", (row["id"],))
            kb.db.execute("DELETE FROM derived WHERE id=?", (row["id"],))
            cleaned.append(f"derived#{row['id']}")
        kb.db.commit()
    hist_after = history_db.count()

    # ── 报告 ──────────────────────────────────────────────
    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    print(f"\nprobe_ui_smoke: {len(results)} 个用例，PASS {len(passed)} / "
          f"FAIL {len(failed)}")
    for r in results:
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    print(f"\n清理: {', '.join(cleaned) or '无'}；"
          f"history 行数 {hist_baseline} -> {hist_after}")
    print(f"截图/服务日志: {LOGDIR}")
    if hist_after != hist_baseline:
        print(f"probe_ui_smoke FAIL: history.db 未清理干净 "
              f"({hist_baseline} -> {hist_after})")
        return 1
    if failed:
        print(f"probe_ui_smoke FAIL: {len(failed)} 个用例失败 "
              f"({', '.join(r['name'] for r in failed)})")
        return 1
    print("probe_ui_smoke PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
