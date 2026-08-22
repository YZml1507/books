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

**R132a（审查轨）两处重钉**：
  * news.refresh（B-018）：原用例把「外网有新闻条目」当产品判据，本网络下
    永远不可能全绿（curl 直连/代理均 000，同网 HN 200——环境问题，非代码
    回归；git stash -u 干净 HEAD 复跑同一条 FAIL）。拆成两层：
    (a) btn:news.refresh.endpoint —— 产品行为层，离线可判：点击后真的请求了
        /api/external/news，容器出现合法终态（有条目**或**设计的「暂无新闻」
        降级文案），零 console.error；
    (b) env:news.content_reachable —— 外网内容层：可达时断言有条目并报数；
        不可达时打印 SKIP 说明，**不再 FAIL**。用例不删除，只不再拿天气当闸门。
  * ai.polish 两用例（specs/006 T2.3，D-145a 只断行为不钉内部命名）：
    ai.block.renders_with_ai —— LLM 可用时排盘结果区出现 .ai-polish 区块且
    标注（AI 生成/仅供娱乐）常显；ai.block.separate_from_citations —— AI 区块
    与古籍引文区（.cite-body）互不嵌套、类名不复用。为让「LLM 可用」在闸门
    里可复现，本 probe 起一个**本地 mock OpenAI 兼容端点**（stdlib http.server，
    零外网、零新依赖），经 BOOKS_LLM_BASE_URL 注入被测服务。mock 起不来时两
    用例转 SKIP（如实标注），不假装测过。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_ui_smoke.py
可选：--headed 看真实点击过程；--port N 换端口；--keep 保留 logs/ 截图。
退出码：0 全绿；1 有用例失败；2 环境不可用（chromium 未装 / 服务起不来）。
截图与失败详情：logs/ui_smoke/
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src"), os.path.join(ROOT, "web")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 端口策略（R120a 实测修正）：8199 曾被**另一条轨**占用——修复轨 merge audit
# 后拿到了本 probe，会自己跑，于是两轨撞同一个固定端口。固定端口在双轨模型下
# 必然偶发冲突，而冲突时本 probe 只能报 SKIP-ENV（退出码 2），闸门变成"有时
# 跑不了"。修法是自动挑一个空闲端口，而不是 taskkill 别人的进程
# （8123 是修复窗口肉眼查看的页面，taskkill 跨分支也拦不住）。
PORT_CANDIDATES = list(range(8199, 8220))
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
# 内部字段名不得上屏（specs/003 判据 14）。
# **R124a 教训**：本 probe 曾 36/36 全绿，却漏了 `ten_gods` / `five_elements` /
# `day_luck` / `relations` 四个裸键名直接显示在排盘结果区首屏——因为当时只检查
# 「容器非空 + 无 [object Object] + 无失败文案」，没检查"内容是不是人话"。
# 用户看到程序变量名和看到 [object Object] 一样廉价，判据却看不见。
INTERNAL_KEYS = ["ten_gods", "five_elements", "day_luck", "relations",
                 "day_ganzhi", "day_master_rel", "peach_zhi", "hit_pillars",
                 "hongluan_pillar", "tianxi_pillar", "day_wx_sheng",
                 "peach_same", "dayun_hits", "moving_lines", "gua_number",
                 "upright_kw", "reversed_kw", "skipped_chars"]
ACTION_TIMEOUT_MS = 4000   # 短超时：标签坏了会导致成片元素不可见，30s×N 跑不完

# ---------------------------------------------------------------------------
# 用例表：(名字, 视图, 按钮选择器, 结果容器选择器, 视图内先切的标签)
# 覆盖 index.html 全部 15 个提交按钮 + 9 个 rtab + 3 个 rsec2 子标签。
# ---------------------------------------------------------------------------
BUTTON_CASES = [
    # name,            view,      tab(data-rsec 值或 None), button,        result
    ("bazi",           "bazi",    None,            "#submit",        "#result"),
    # R132a（B-018）：news.refresh 从按钮用例表移出，重钉为两层判据——
    # btn:news.refresh.endpoint（产品行为，离线可判）+ env:news.content_reachable
    # （外网内容，可达才断言）。见本文件 docstring 与下方专用块。
    # R122a：三个读书子标签的选择器**不再写死 data-rsec2 的值**，改为运行时
    # 从 DOM 读（见 discover_subtabs）。原因是 R120a/R179b 撞过一次协调事故：
    # R178b 把值从 bs-structure 改成驼峰 bsStructure，我在 R120a 跟着改了
    # probe；R179b 又把 HTML 改回 kebab 以迁就我 R119a 的旧 probe。
    # 两轨从相反方向各修一次，结果仍然对不上（6 个用例 TimeoutError）。
    # 教训：**probe 不该把对方的内部命名钉死成契约**——面板容器 id
    # （#bsStructure 等）才是稳定契约，标签值是实现细节，运行时发现即可。
    ("bookstudy.structure", "read", "rsec-bookstudy", "@subtab:0", "#bsStructure"),
    ("bookstudy.chapter",   "read", "rsec-bookstudy", "@subtab:1", "#bsChapter"),
    ("bookstudy.summary",   "read", "rsec-bookstudy", "@subtab:2", "#bsSummary"),
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
    # 读书三子功能：书 ID + scheme + 地址（固定值，实测 KR1a0001 卦1 有内容）
    "bookstudy.structure": {"#bswork": "KR1a0001"},
    "bookstudy.chapter":   {"#bswork": "KR1a0001", "#bsaddr1": "1"},
    "bookstudy.summary":   {"#bswork": "KR1a0001"},
}

# 标签切换用例：点 .rtab[data-rsec=X] 后 #X 必须可见。
# 从 HTML 实际存在的 data-rsec 值取，不写死——写死会在标签增减时静默漏测。
TAB_CASES = ["rsec-search", "rsec-research", "rsec-addr", "rsec-compare",
             "rsec-works", "rsec-threads", "rsec-bookstudy", "rsec-cw",
             "rsec-concept"]
# 子标签的 data-rsec2 值**运行时从 DOM 发现**，不写死（见 BUTTON_CASES 注释）。
# 写死会让 probe 把对方的内部命名钉成契约，两轨各改一次就对不上——R120a/R179b
# 实测撞过。这里只断言"有三个子标签且点了能 active"，不关心它们叫什么。
SUBTAB_EXPECTED_COUNT = 3


class _MockLLMHandler(BaseHTTPRequestHandler):
    """OpenAI 兼容 /chat/completions 的最小实现（specs/006 T2.3 测试基建）。

    只服务本 probe 起的 127.0.0.1 实例：返回固定温柔文本 + 「仅供娱乐」，
    让被测服务的 ai_polish 真实走完 polish() 全链路（HTTP→解析→_sanitize），
    前端 renderAiPolish 拿到真值渲染。零外网、零新依赖。
    """

    def do_POST(self):  # noqa: N802  (BaseHTTPRequestHandler 命名)
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        body = json.dumps({
            "choices": [{"message": {"content":
                        "今天的盘面给你留了呼吸的空间，慢慢来，一切都有它的节奏。"
                        "仅供娱乐"}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):   # 静默：probe 输出只留判据行
        pass


def start_mock_llm() -> tuple | None:
    """起本地 mock 端点。返回 (server, port)；失败返回 None（调用方转 SKIP）。"""
    try:
        s = HTTPServer(("127.0.0.1", 0), _MockLLMHandler)
    except OSError:
        return None
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    return s, s.server_address[1]


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
    forced_port = None
    if "--port" in sys.argv:
        forced_port = int(sys.argv[sys.argv.index("--port") + 1])

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probe_ui_smoke SKIP-ENV: playwright 包未安装")
        return 2

    if forced_port is not None:
        if not free_port(forced_port):
            print(f"probe_ui_smoke SKIP-ENV: 显式指定的端口 {forced_port} 已被占用。"
                  f"本 probe 绝不 taskkill 占用者。")
            return 2
        port = forced_port
    else:
        port = next((p for p in PORT_CANDIDATES if free_port(p)), None)
        if port is None:
            print(f"probe_ui_smoke SKIP-ENV: {PORT_CANDIDATES[0]}–"
                  f"{PORT_CANDIDATES[-1]} 全部被占用，无空闲端口。"
                  f"本 probe 绝不 taskkill 占用者（8123 是修复窗口的查看页面）。")
            return 2
        if port != PORT_CANDIDATES[0]:
            print(f"端口 {PORT_CANDIDATES[0]} 被占用（很可能是修复轨在跑同一个"
                  f"probe），自动改用 {port}——不抢占别人的端口。")

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
    # R132a（T2.3）：起本地 mock LLM 端点并注入被测服务，让「LLM 可用时 AI
    # 区块渲染」成为离线可复现判据。mock 起不来 → 两用例转 SKIP，不装死。
    mock = start_mock_llm()
    if mock is not None:
        mock_srv, mock_port = mock
        env["BOOKS_LLM_API_KEY"] = "probe-ui-smoke-mock-key"
        env["BOOKS_LLM_BASE_URL"] = f"http://127.0.0.1:{mock_port}/v1"
        # 闸门惯例会全局导出 BOOKS_LLM_DISABLE=1；它若泄漏进被测服务，
        # mock 注入就被总开关废掉（D-245a：DISABLE 优先于一切配置）。
        # 本 probe 的 LLM 指向是 127.0.0.1 mock，零外呼，移除是安全的。
        env.pop("BOOKS_LLM_DISABLE", None)
        # R132a 实测坑：Windows 系统代理开启时（注册表 ProxyEnable=1，
        # 本机实测 127.0.0.1:7897），httpx trust_env 会拾取注册表代理，
        # 且**不尊重** IE 的 ProxyOverride 环节 → 发往 127.0.0.1 的 polish
        # 请求被路由进系统代理、拿到 502 空响应、静默降级成 None。
        # 显式 NO_PROXY 让子进程对 localhost 直连（只影响本子进程）。
        env["NO_PROXY"] = "127.0.0.1,localhost"
        env["no_proxy"] = "127.0.0.1,localhost"
        print(f"mock LLM 端点：http://127.0.0.1:{mock_port}/v1/chat/completions")
    else:
        mock_srv = None
        print("mock LLM 端点启动失败：ai.polish 两用例本轮转 SKIP")
    srv_log = open(os.path.join(LOGDIR, "server.log"), "w", encoding="utf-8")
    # R178b 起 web 是包（web/__init__.py + `from . import deps`），启动目标是
    # `web.app:app` 且工作目录必须是项目根；旧的 `app:app` + cwd=web/ 会因
    # 相对导入失败（ImportError: attempted relative import with no known
    # parent package）。两种布局都试，避免 probe 因布局演进而假报环境不可用。
    target = ("web.app:app" if os.path.exists(os.path.join(ROOT, "web", "__init__.py"))
              else "app:app")
    cwd = ROOT if target.startswith("web.") else os.path.join(ROOT, "web")
    print(f"启动目标：{target}（cwd={cwd}）")
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=cwd, env=env,
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
            # 当前口吻模式（R124a）：默认走产品自己的默认分支，不预设
            # localStorage——要测的正是"用户第一次打开看到什么"。
            voice_mode = page.evaluate(
                "() => { try { return localStorage.getItem('voiceMode')"
                " || 'warm'; } catch (e) { return 'warm'; } }")
            results.append({
                "name": "voice.default_mode", "ok": True,
                "detail": f"首次打开的口吻模式 = {voice_mode}"
                          f"（内部字段名判据只在 warm 下生效）",
            })
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
            if not page.is_visible("#rsec-bookstudy"):
                force_show_rsec("rsec-bookstudy")
                page.wait_for_timeout(150)
            # 运行时发现子标签的 data-rsec2 值（不写死对方的内部命名）
            subtabs = page.eval_on_selector_all(
                ".rtab[data-rsec2]",
                "els => els.map(e => e.dataset.rsec2)")
            results.append({
                "name": "subtab.discovery",
                "ok": len(subtabs) == SUBTAB_EXPECTED_COUNT,
                "detail": (f"发现 {len(subtabs)} 个子标签 {subtabs}"
                           f"（期望 {SUBTAB_EXPECTED_COUNT} 个）"),
            })
            for sub in subtabs:
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
                    # `@subtab:N` 占位符 → 运行时按序号取真实 data-rsec2 值。
                    # 见 BUTTON_CASES 注释：不把对方的内部命名写死成契约。
                    target_sel = btn
                    if btn.startswith("@subtab:"):
                        idx = int(btn.split(":", 1)[1])
                        if idx >= len(subtabs):
                            raise AssertionError(
                                f"子标签只发现 {len(subtabs)} 个，取不到第 {idx} 个"
                                f"（{subtabs}）")
                        target_sel = f".rtab[data-rsec2='{subtabs[idx]}']"
                    page.click(target_sel)
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
                    # 内部字段名（R124a）。只在 warm 模式判——专业模式按
                    # specs/004 判据 9 必须逐字节不变，不能因此报缺陷。
                    raw_keys = ([k for k in INTERNAL_KEYS if k in (text or "")]
                                if voice_mode == "warm" else [])
                    ok = (bool(text) and not PLACEHOLDER_RE.match(text or "")
                          and not fail_hit and not obj_literal and not raw_keys
                          and not errors)
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
                    elif raw_keys:
                        k = text.find(raw_keys[0])
                        detail = (f"warm 模式下暴露内部字段名 {raw_keys}"
                                  f"（specs/003 判据 14）: "
                                  f"…{text[max(0, k - 45):k + 45]!r}…")
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

            # ── news.refresh 两层判据（R132a，B-018）───────────────────
            # (a) 产品行为层（离线可判）：点击 → 真的请求 /api/external/news
            #     → 容器出现合法终态：新闻条目**或**设计内空态「暂无新闻」。
            errors.clear()
            api_calls.clear()
            goto_view("bazi")
            degrade_ok = False
            text = ""
            try:
                page.click("#newsRefresh")
                text, waited = "", 0.0
                while waited < CASE_BUDGET_S:
                    page.wait_for_timeout(400)
                    waited += 0.4
                    text = (page.inner_text("#newsList") or "").strip()
                    if text and not PLACEHOLDER_RE.match(text):
                        break
                no_ev = " ".join(page.eval_on_selector_all(
                    "#newsList .no-evidence",
                    "els => els.map(e => e.innerText)") or [])
                degrade_ok = "暂无新闻" in no_ev        # 设计内的空态文案
                fail_hit2 = FAILURE_RE.search(no_ev or "")
                endpoint_ok = any("/api/external/news" in u for u in api_calls)
                items_ok = (bool(text) and not degrade_ok and not fail_hit2
                            and not PLACEHOLDER_RE.match(text or ""))
                ok = (items_ok or degrade_ok) and endpoint_ok and not errors
                detail = (f"请求 /api/external/news={endpoint_ok}　"
                          f"容器 {len(text)} 字符: {text[:80]!r}")
                if errors:
                    detail += " | " + "; ".join(errors[:3])
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if not ok:
                page.screenshot(path=os.path.join(LOGDIR,
                                                  "FAIL_news_endpoint.png"))
            results.append({"name": "btn:news.refresh.endpoint", "ok": ok,
                            "detail": detail})
            # (b) 外网内容层：可达才断言有条目；不可达 → SKIP 不 FAIL。
            #     B-018：环境可达性不是产品判据——用例保留，不再拿天气当闸门。
            try:
                if degrade_ok or not text:
                    ok2 = True
                    detail2 = ("SKIP：外网内容不可达（B-018：本网络 curl 实测 "
                               "BBC/Solidot=000 而 HN=200）——产品行为层已单独"
                               "判定，此处不断言条目数")
                else:
                    n_items = page.eval_on_selector_all(
                        "#newsList .news-item", "els => els.length")
                    ok2 = n_items > 0
                    detail2 = f"外网可达：新闻条目 {n_items} 条"
            except Exception as exc:
                ok2, detail2 = False, f"{type(exc).__name__}: {exc}"
            results.append({"name": "env:news.content_reachable", "ok": ok2,
                            "detail": detail2})

            # ── AI 润色区块两用例（R132a，specs/006 T2.3）──────────────
            # mock LLM 已注入被测服务。D-145a：只断行为（区块出现、标注常显、
            # 与引文区分离），不钉内部命名以外的实现细节。
            if mock_srv is None:
                results.append({"name": "ai.block.renders_with_ai", "ok": True,
                                "detail": "SKIP：mock LLM 端点启动失败，本轮未测"})
                results.append({"name": "ai.block.separate_from_citations",
                                "ok": True,
                                "detail": "SKIP：mock LLM 端点启动失败，本轮未测"})
            else:
                errors.clear()
                goto_view("bazi")
                try:
                    page.click("#submit")
                    page.wait_for_selector(".ai-polish", timeout=15000)
                    page.wait_for_timeout(300)
                    ai_text = (page.inner_text(".ai-polish") or "").strip()
                    marked = ("AI 生成" in ai_text) and ("仅供娱乐" in ai_text)
                    ok3 = bool(ai_text) and marked and not errors
                    detail3 = (f".ai-polish 区块 {len(ai_text)} 字符，标注"
                               f"「AI 生成」「仅供娱乐」常显={marked}: "
                               f"{ai_text[:80]!r}")
                    if errors:
                        detail3 += " | " + "; ".join(errors[:3])
                except Exception as exc:
                    ok3, detail3 = False, f"{type(exc).__name__}: {exc}"
                if not ok3:
                    page.screenshot(path=os.path.join(LOGDIR, "FAIL_ai_block.png"))
                results.append({"name": "ai.block.renders_with_ai", "ok": ok3,
                                "detail": detail3})
                # 分离性：AI 容器与古籍引文容器互不嵌套、类名零复用
                try:
                    sep = page.evaluate("""() => {
                        const ai = document.querySelector('.ai-polish');
                        const cites = document.querySelectorAll('.cite-body');
                        if (!ai || !cites.length)
                            return {ai: !!ai, cites: cites.length,
                                    nested: false, same: []};
                        let nested = false;
                        cites.forEach(c => {
                            if (ai.contains(c) || c.contains(ai)) nested = true;
                        });
                        const shared = [];
                        ai.classList.forEach(cl => {
                            if (document.querySelector('.cite-body.' +
                                (window.CSS && CSS.escape ? CSS.escape(cl) : cl)))
                                shared.push(cl);
                        });
                        return {ai: true, cites: cites.length, nested, same: shared};
                    }""")
                    ok4 = (sep["ai"] and sep["cites"] > 0
                           and not sep["nested"] and not sep["same"])
                    detail4 = (f"AI 容器存在={sep['ai']}　引文容器 {sep['cites']} 个　"
                               f"互相嵌套={sep['nested']}　共享类名={sep['same']}")
                except Exception as exc:
                    ok4, detail4 = False, f"{type(exc).__name__}: {exc}"
                results.append({"name": "ai.block.separate_from_citations",
                                "ok": ok4, "detail": detail4})

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
        if mock_srv is not None:
            mock_srv.shutdown()

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
