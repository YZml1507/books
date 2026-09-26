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
  * news.panel_removed / news.retired_marker（B-018 → R208b → R2349s）：
    原用例把「外网有新闻条目」当产品判据；R208b 删除 news 面板后，
    这两条改为退役钉扎（R85-P1-6 复扫改名，断言体本就如此）：
    (a) news.panel_removed —— newsRefresh/newsList DOM 零残留（反向钉扎）；
    (b) news.retired_marker —— 恒真占位，语义=该功能已退役，防名字复活。
  * ai.polish 两用例（specs/006 T2.3，D-145a 只断行为不钉内部命名）：
    ai.block.renders_with_ai —— LLM 可用时排盘结果区出现 .ai-polish 区块且
    标注（AI 生成/仅供娱乐）常显；ai.block.separate_from_citations —— AI 区块
    与古籍引文区（.cite-body）互不嵌套、类名不复用。为让「LLM 可用」在闸门
    里可复现，本 probe 起一个**本地 mock OpenAI 兼容端点**（stdlib http.server，
    零外网、零新依赖），经 BOOKS_LLM_BASE_URL 注入被测服务。mock 起不来时两
    用例转 SKIP（如实标注），不假装测过。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_ui_smoke.py
可选：--headed 看真实点击过程；--port N 换端口。
（截图/日志无条件写入 logs/ui_smoke/，无需 --keep。）
退出码：0 全绿；1 有用例失败；2 环境不可用（chromium 未装 / 服务起不来）。
截图与失败详情：logs/ui_smoke/
"""
from __future__ import annotations

import datetime
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
# 覆盖 index.html ~20 个动作按钮（部分刻意入 NO_CASE 豁免表）+ 9 个 rtab + 3 个 rsec2 子标签。
# ---------------------------------------------------------------------------
BUTTON_CASES = [
    # name,            view,      tab(data-rsec 值或 None), button,        result
    ("bazi",           "bazi",    None,            "#submit",        "#result"),
    # R132a（B-018）：news.panel_removed 从按钮用例表移出，重钉为两层判据——
    # news.panel_removed（产品行为，离线可判）+ news.retired_marker
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
    # R230z（R36-P1-2）：存这对钮只有 hehun 出卡后才存在——用例必须排
    # 在 hehun 之后；点击后 #hhFavRow 浮出「测过的 CP」chips 为断言。
    ("hehun.savepair",  "hehun",   None,            "#hhSavePair",    "#hhFavRow"),
    # R233n：邀请链——点「喊 TA 来对盘」出 toast（clipboard 成败两路
    # 都出 toast）；须在 hehun 出卡后，同 savepair 排序约束。
    ("hehun.invite",    "hehun",   None,            "#hhInvite",      ".toast-item"),
]

# 点按钮前需要填的输入（用固定值 → 固定结果，可命令复验）
FILL = {
    "bazi":         {"#year": "1990", "#month": "5", "#day": "15"},
    "search":        {"#rq": "潛龍勿用"},
    "research":      {"#rq2": "無爲", "#rmax": "2"},
    "addr":          {"#aguan": "1"},
    "compare":       {"#cgua": "28", "#cyao": "九二"},
    "threads":       {"#tq": "probe_ui_smoke 线程"},
    "compare_works": {"#cwa": "KR5c0057", "#cwb": "KR5c0126", "#cwq": "無爲"},
    "concept":       {"#cq": "無爲"},
    # R2349y：wipe 改成无条件清字段（R95-P1-3）后，B 侧不再剩 HTML
    # 默认值——合婚用例必须显式填双方，与真人输入路径一致。
    "hehun":         {"#hh_a_year": "1990", "#hh_a_month": "5",
                      "#hh_a_day": "15", "#hh_b_year": "1992",
                      "#hh_b_month": "8", "#hh_b_day": "20"},
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
        from socketserver import ThreadingMixIn
        class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True
        s = ThreadingHTTPServer(("127.0.0.1", 0), _MockLLMHandler)
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
    # R230k（R23-P3-5）：bazi_history 自 R219b 无写路径——探针每轮 bazi
    # 提交实际写 paipan_history.db，原来一直清着一张不再被写的表。
    # 换成 contract 同款 paipan 基线+增量清理。
    from guji import paipan_history as _ph_db
    _ph_baseline = (0 if _ph_db.disabled()
                    else _ph_db.list_records(limit=200)["total"])
    # R2345：wipe 用例会真删台账——「total−baseline」在其后失真，
    # 残留判定改按 id 水位：本论新建行 id 必 > 基线 max_id。
    _ph_max_id0 = 0
    try:
        if not _ph_db.disabled():
            _items0 = _ph_db.list_records(limit=1)["items"]
            if _items0:
                _ph_max_id0 = int(_items0[0]["id"])
    except Exception:
        pass
    with kb_mod.KnowledgeBase(kb_path) as kb:
        derived_baseline = kb.db.execute(
            "SELECT COALESCE(MAX(id),0) AS m FROM derived").fetchone()["m"]
        # R228x续：后端「新建线程」语义修复后，btn:threads 每跑一轮会真开
        # 一行 thread+turn——跟 derived 一样按基线回收，别让线程表越堆越脏。
        thread_baseline = kb.db.execute(
            "SELECT COALESCE(MAX(id),0) AS m FROM thread").fetchone()["m"]

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
    _wipe_delta = [0]   # ui:history.wipe 真删台账行数（清理闸补偿用）

    # ── R228o 静态闸（不占浏览器，服务就绪前先跑）─────────────────
    # S1) on() 注册面 ⊆ BUTTON_CASES ∪ NO_CASE——新按钮忘了接冒烟用例时
    #     立刻 FAIL 而不是静默没人点过（gate-blindspots 审查发现：xz* 与
    #     share* 等 10 个 on() 注册此前零点击验证且无登记）。
    _js_path = os.path.join(ROOT, "web", "static", "app.js")
    _js = open(_js_path, encoding="utf-8").read()
    _on_ids = set(re.findall(r"(?<![\w.])on\(\s*['\"](\w+)['\"]", _js))
    # R2344（R60-P2）：on() 之外的裸绑定也进覆盖闸——
    # var x = getElementById('id') → x.addEventListener('click')
    _var_ids = dict(re.findall(
        r"(?:var|let|const)\s+(\w+)\s*=\s*(?:document\.getElementById|el)"
        r"\(['\"](\w+)['\"]\)", _js))
    for _v, _i in _var_ids.items():
        if re.search(rf"\b{re.escape(_v)}\.addEventListener\(['\"]click", _js):
            _on_ids.add(_i)
    # R2347（R60-meta-1 收口）：直链式裸绑定也钉——
    # `el('x').addEventListener('click')` / `getElementById('x').addEventListener`
    # / `querySelector('#x').addEventListener` 三种不赋值形态此前仍逃逸。
    _on_ids |= set(re.findall(
        r"(?:document\.getElementById|el)\(['\"](\w+)['\"]\)"
        r"\.addEventListener\(['\"]click", _js))
    _on_ids |= set(re.findall(
        r"\.querySelector\(['\"]#(\w+)['\"]\)\.addEventListener\(['\"]click",
        _js))
    _covered = {btn.lstrip("#") for _n, _v, _t, btn, _r in BUTTON_CASES}
    _covered |= {"dailyMore", "submit",
                 # R2344：内联用例覆盖的裸绑定/容器委托 id（见 ui:* 用例）
                 "historyImportBtn", "xzPrev", "xzToday", "birthSubmit",
                 "hlPickBtn", "recentToggle", "recentClose", "themeToggle",
                 "dailyCover", "viewBack", "dailyTomorrow", "historyRefresh",
                 "historyExport", "historyExportJson",
                 "historyImportFile", "historyWipe",
                 "hlResult", "qmResult",
                 # R2350k：自点牌扇——ui:tarot.pick 用例覆盖（fan 委托
                 # 也由用例里的 .tr-back 点选走到）
                 "trPickBtn", "trPickGo", "trPickFan",
                 "tr_spread"}
    # 显式豁免：须写理由；空集合也要保留表结构（新按钮默认要进用例表）
    NO_CASE = {
        "chatSendBtn": "聊天流走 e2e（testing-xiaoman-e2e skill）+真实模型验证，"
                       "冒烟只到按钮可见",
        "nameReviewBtn": "AI 点评轮询入口——LLM 任务在冒烟环境不产生",
        "qmRefreshBtn": "改名候选重生按钮——同 qiming 链路",
        "shareBazi": "分享海报模态（Canvas）——冒烟不测文件生成",
        "shareQiming": "同上",
        "shareTaohua": "同上",
        "shareHehun": "同上",
        "shareDaily": "同上",
        "xzSubmit": "星座卡计算在 selftest 已钉，冒烟面板可后续补",
        "xzNext": "ui:xznav.next 已覆盖", "xzTomorrow": "同 Next 链路",
        "xzPrev": "ui:xznav.roundtrip 已覆盖", "xzToday": "同上",
        # R2344（R60-P2）：裸绑定补登记
        "dailyRecall": "点击=data-hlask-q 文档级委托，链路同 deeplink/"
                       "问一嘴用例",
        "dailyCard": "卡片本体无独立点击动作（scrollIntoView 场景），"
                     "封面/打卡/预告均各有用例",
        "birthDrawer": "details 原生开合；ui:birth.submit 已展开并提交",
        "chatEmpty": "容器内的 .chat-chip 走 data-ask 委托→chatSend，"
                     "发送链路已由 crisis_fe/drawer 用例覆盖",
        # R2349l（R73）：本批新增的动态/抽屉内控件
        "dailyPersonalCta": "日卡 meta 行动态生成按钮（档案缺失时才有），"
                            "点击=showView('xingzuo')+开 birthDrawer——"
                            "导航链路已由 deep.* 用例覆盖",
        "signPeekBtn": "解签展开钮——生成在日卡 meta 行内，toggle 本地"
                       " signCard hidden，零请求零副作用",
        "tarotPeekBtn": "同上模式：今日牌牌意展开钮",
        "xzmSubmit": "星座速配——API 层已由 selftest xzmatch/xzmatch.hard/"
                     "xzmatch.bad 三用例钉死，冒烟只到抽屉可见",
        "dailyWeekGo": "周条提示钮——仅周日/周一生成的动态钮，"
                       "点击=showView('huangli') 导航同 deep.* 用例",
        "xzResult": "星座宫卡容器——委托监听 .xz-card 展开三运折叠行，"
                    "本地 toggle 零请求",
        # R2363（R117-P0-2）：meta 行超 5 粒折叠的「+N 条」收纳钮——
        # 同 signPeekBtn 模式：动态生成、本地 toggle 零请求。
        "dailyMetaMore": "meta 折叠收纳钮——动态生成、本地 toggle 零请求",
        # R2500（R143-P2-8）：触屏/微信专属粘贴导入弹层——桌面冒烟
        # _exportShowOnly()=False 根本开不出这个弹层（按钮不渲染），
        # 链路同 ui:history.import 的导入主路径。
        "importPasteGo": "触屏/微信专属粘贴导入弹层钮——桌面端"
                          "_exportShowOnly()=False 弹层不产生，"
                          "导入主路径 ui:history.import 已覆盖",
        # R2506（审-U1）：日签失败态动态生成的重试钮——点击=loadDaily
        # 重拉，主链路（日卡渲染/深链/跨零点重载）已由 daily/deep 用例覆盖；
        # 冒烟强造 daily 5xx 成本高（需 mock 注入失败），豁免。
        "dailyRetry": "日签失败态动态重试钮——loadDaily 主链路已由 "
                      "daily/deep 用例覆盖，失败注入非冒烟面",
    }
    _miss = sorted(_on_ids - _covered - set(NO_CASE))
    results.append({"name": "gate:on_coverage",
                    "ok": not _miss,
                    "detail": ("on() 注册 28 个全部在用例表或豁免表"
                               if not _miss else
                               f"未覆盖且未豁免的 on() 注册: {_miss}")})

    # S2) innerHTML 单行注入 lint：同行结束的 innerHTML 赋值里若出现
    #     \w+\.\w+ 裸字段读且没有 esc(/fmtScalar(/renderRichText(/renderStars(
    #     包装 → FAIL（跨行拼接由契约探针+人审兜底，本闸只抓直注）。
    _raw_hits = []
    for _i, _ln in enumerate(_js.splitlines(), 1):
        _m = re.search(r"innerHTML\s*(?:\+?=)\s*(.+;)", _ln)
        if not _m:
            continue
        _rhs = _m.group(1)
        _fields = re.findall(r"\b(\w+)\.(\w+)", _rhs)
        if not _fields:
            continue
        if re.search(r"esc\(|fmtScalar\(|renderRichText\(|renderStars\(|"
                     r"buildBaziResult\(|renderDecoration\(|insertAiPolish\(",
                     _rhs):
            continue
        if "// esc-reviewed" in _ln:
            continue
        _raw_hits.append(f"{_i}:{_rhs[:60]}")
    results.append({"name": "gate:innerHTML_esc",
                    "ok": not _raw_hits,
                    "detail": ("单行 innerHTML 注入全部经包装"
                               if not _raw_hits else
                               f"裸字段注入: {_raw_hits[:4]}")})
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
            # R2509：CSP（无 unsafe-eval）把 Playwright wait_for_function
            # 的 eval 注入也挡了——探针测应用行为不测 CSP（后者归
            # probe_r2509），context 开 bypass_csp。
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                bypass_csp=True)
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

            # R231d（R37-F4/F7）：首访应有新人条；关掉后刷新不再出现。
            try:
                wv = page.evaluate(
                    "() => { const w = document.getElementById('welcomeBar');"
                    " return !!(w && w.offsetParent !== null); }")
                results.append({
                    "name": "ui:welcome_bar", "ok": bool(wv),
                    "detail": "首访新人条存在=%s" % wv})
            except Exception as exc:
                results.append({"name": "ui:welcome_bar", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # R2340：深浅色切换——点 #themeToggle 后 html[data-theme=dark]
            # 且 localStorage 落盘；刷新仍在 dark。
            try:
                page.evaluate("localStorage.removeItem('uiTheme')")
                page.click('#themeToggle')
                page.wait_for_timeout(300)
                _d1 = page.evaluate(
                    "document.documentElement.getAttribute('data-theme')")
                _sv = page.evaluate("localStorage.getItem('uiTheme')")
                page.reload(); page.wait_for_timeout(600)
                _d2 = page.evaluate(
                    "document.documentElement.getAttribute('data-theme')")
                page.evaluate("localStorage.removeItem('uiTheme');"
                              "document.documentElement.removeAttribute('data-theme')")
                results.append({
                    "name": "ui:theme_toggle", "ok": _d1 == 'dark' and _sv == 'dark' and _d2 == 'dark',
                    "detail": f"点击后={_d1} 存={_sv} 刷新={_d2}"})
            except Exception as exc:
                results.append({"name": "ui:theme_toggle", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            def goto_view(view: str):
                # R200b（US3 方案①）：首页五张直达卡（bazi/tarot/liuyao/read/
                # huangli）；qiming/taohua/hehun 在 view-bazi 底部「相关功能」区。
                # R206b（specs/009 US2 二剪）：read/liuyao/qiming 收进首页
                # 「高级入口」pro-drawer 折叠抽屉——先展开抽屉再点卡；
                # taohua/hehun 已提回首页直达卡。用例不减只改导航路径。
                # R209b：桌面端侧栏常驻展开会遮内容——导航前先收起。
                page.evaluate(
                    "() => { const sb = document.getElementById('recentSidebar');"
                    " if (sb) sb.classList.add('collapsed'); }")
                page.wait_for_timeout(500)
                if page.evaluate("() => document.getElementById('homeMain').hidden"):
                    page.click("#viewBack")
                    page.wait_for_timeout(150)
                drawer = page.locator("#proDrawer")
                if drawer.count():
                    page.evaluate(
                        "() => document.getElementById('proDrawer').open = true")
                    page.wait_for_timeout(120)
                card = page.locator(f".func-card[data-view='{view}']")
                # R208b：read 卡已从首页移除（用户裁决：不提供读书渠道），
                # 视图与 API 全保留——改编程式导航，用例不减。
                if view == "read" and card.count() == 0:
                    page.evaluate("() => showView('read')")
                    page.wait_for_selector("#view-read.active", timeout=5000)
                    return
                if card.count() > 1:
                    # 同名卡多处（隐藏簇页 + 可见相关功能区）：过滤出可见者
                    card = page.locator(
                        f".func-card[data-view='{view}']:visible")
                if card.count() >= 1 and card.first.is_visible():
                    card.first.click()
                else:
                    page.click(".func-card[data-view='bazi']")
                    page.wait_for_selector("#view-bazi.active", timeout=5000)
                    page.locator(
                        f".func-card[data-view='{view}']:visible"
                    ).first.click()
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

            # ── R2342（R60-P0）：覆盖盲区补钉——真实点击路径 ──

            # R2501：出厂示例盘直接提交不能污染本人档案；真实改动仍要落档。原生 select
            # 的 defaultValue 为空；旧实现拿它和首选项值比较，误判
            # 「用户改过性别」，于是 1990-05-15 被写进 localStorage.me。
            try:
                page.evaluate("localStorage.removeItem('me')")
                goto_view('bazi')
                page.wait_for_selector("#view-bazi.active", timeout=5000)
                with page.expect_response(
                        lambda r: r.url.endswith('/api/bazi')
                        and r.request.method == 'POST',
                        timeout=20000) as _default_response:
                    page.click('#submit')
                _default_status = _default_response.value.status
                page.wait_for_function(
                    "() => { const r = document.getElementById('result');"
                    " return r && r.querySelector('.card'); }",
                    timeout=20000)
                _default_me = page.evaluate("localStorage.getItem('me')")
                # 用户改过后再改回默认值/首选项时，档案回填也不能覆盖；
                # data-me 会被事件监听清掉，但 data-touched 必须继续保护该值。
                _refill_respected = page.evaluate("""() => {
                    localStorage.setItem('me', JSON.stringify({
                        y: 1992, m: 5, d: 15, h: null, g: '男', lunar: null
                    }));
                    const year = document.getElementById('year');
                    const gender = document.getElementById('gender');
                    year.value = year.defaultValue;
                    year.dataset.me = '1';
                    year.dataset.touched = '1';
                    gender.selectedIndex = 0;
                    gender.dataset.me = '1';
                    gender.dataset.touched = '1';
                    _meFill('me', {y: 'year', m: 'month', d: 'day',
                                   h: 'hour', g: 'gender'});
                    const got = {y: year.value, g: gender.value,
                                 yt: year.dataset.touched || '',
                                 gt: gender.dataset.touched || ''};
                    localStorage.removeItem('me');
                    ['year', 'gender'].forEach(id => {
                        const node = document.getElementById(id);
                        delete node.dataset.me;
                        delete node.dataset.touched;
                    });
                    return got;
                }""")
                _invite_default = page.evaluate("""() => {
                    const gender = document.getElementById('gender');
                    gender.dataset.invite = '1';
                    const untouched = _fieldsUntouched(['year', 'month', 'day',
                        'hour', 'minute', 'calendar_type', 'gender']);
                    delete gender.dataset.invite;
                    return untouched;
                }""")
                _select_to_first = page.evaluate("""() => {
                    const gender = document.getElementById('gender');
                    gender.value = '男';
                    gender.selectedIndex = 1;
                    gender.dispatchEvent(new Event('change', {bubbles: true}));
                    gender.selectedIndex = 0;
                    gender.dispatchEvent(new Event('change', {bubbles: true}));
                    return _fieldsUntouched(['year', 'month', 'day',
                        'hour', 'minute', 'calendar_type', 'gender']);
                }""")
                # 旧档案回填“男”后，用户真实 change 回首项“女”。提交必须
                # 保存“女”，不能被 selectedIndex<=0 的首项近似吞掉。
                page.evaluate("""() => {
                    localStorage.setItem('me', JSON.stringify({
                        y: 1990, m: 5, d: 15, h: null, g: '男', lunar: null
                    }));
                    ['year', 'month', 'day', 'hour', 'gender'].forEach(id => {
                        delete document.getElementById(id).dataset.touched;
                    });
                    _meFillAll();
                    const gender = document.getElementById('gender');
                    gender.selectedIndex = 0;
                    gender.dispatchEvent(new Event('change', {bubbles: true}));
                    document.getElementById('question').value = '性别回填边界';
                }""")
                page.click('#submit')
                page.wait_for_function(
                    """() => {
                        const raw = localStorage.getItem('me');
                        if (!raw) return false;
                        try { return JSON.parse(raw).g === '女'; }
                        catch (_) { return false; }
                    }""", timeout=20000)
                _first_select_pre = page.evaluate("""() => {
                    const gender = document.getElementById('gender');
                    const year = document.getElementById('year');
                    return {g: gender.value, gi: gender.selectedIndex,
                            gt: gender.dataset.touched || '',
                            y: year.value, yt: year.dataset.touched || ''};
                }""")
                _first_select_me = page.evaluate("localStorage.getItem('me')")
                page.evaluate("localStorage.removeItem('me')")
                page.evaluate("""() => {
                    ['year', 'month', 'day', 'hour', 'gender'].forEach(id => {
                        const node = document.getElementById(id);
                        node.value = node.defaultValue;
                        node.selectedIndex = 0;
                        delete node.dataset.touched;
                        delete node.dataset.me;
                    });
                }""")
                page.evaluate("""() => {
                    const year = document.getElementById('year');
                    year.value = '1991';
                    year.dispatchEvent(new Event('input', {bubbles: true}));
                    const gender = document.getElementById('gender');
                    gender.selectedIndex = 1;
                    gender.dispatchEvent(new Event('change', {bubbles: true}));
                }""")
                page.wait_for_timeout(1600)
                page.click('#submit')
                page.wait_for_function(
                    """() => {
                        const raw = localStorage.getItem('me');
                        if (!raw) return false;
                        try {
                            const me = JSON.parse(raw);
                            return me.y === 1991 && me.g === '男';
                        } catch (_) { return false; }
                    }""", timeout=20000)
                _custom_me = page.evaluate("localStorage.getItem('me')")
                _first_g = (json.loads(_first_select_me).get('g')
                            if _first_select_me else None)
                _custom = json.loads(_custom_me) if _custom_me else None
                results.append({
                    "name": "ui:profile.bazi_save_boundary",
                    "ok": (_default_status == 200 and _default_me is None
                           and _refill_respected.get('y') == '1990'
                           and _refill_respected.get('g') == '女'
                           and _refill_respected.get('yt') == '1'
                           and _refill_respected.get('gt') == '1'
                           and _invite_default is False
                           and _select_to_first is False and _first_g == '女'
                           and _custom is not None
                           and _custom.get('y') == 1991
                           and _custom.get('g') == '男'),
                    "detail": (f"默认盘 HTTP={_default_status} me={_default_me!r}；"
                               f"回填尊重touched={_refill_respected!r}；邀请标记判改="
                               f"{not _invite_default}；select改回首项判改="
                               f"{not _select_to_first}；回填后改回首项 pre={_first_select_pre} "
                               f"g={_first_g!r}；改年份/性别后 me={_custom_me!r}")})
            except Exception as exc:
                results.append({
                    "name": "ui:profile.bazi_save_boundary",
                    "ok": False,
                    "detail": f"{type(exc).__name__}: {exc}"})
            finally:
                try:
                    page.evaluate("localStorage.removeItem('me')")
                    page.evaluate("localStorage.setItem('voiceMode', 'warm')")
                    page.evaluate("""() => {
                        ['year', 'month', 'day', 'hour', 'gender'].forEach(id => {
                            const node = document.getElementById(id);
                            if (!node) return;
                            node.value = node.defaultValue;
                            node.selectedIndex = 0;
                            delete node.dataset.touched;
                            delete node.dataset.me;
                            delete node.dataset.invite;
                        });
                        showView('home');
                    }""")
                    page.wait_for_timeout(200)
                except Exception:
                    pass

            # R2501：邀请预填即使当前值等于首项，也属于用户待提交的受邀身份；
            # 走真实提交，确认 me/me:partner 分别落到受邀者与发起人。
            try:
                errors.clear()
                page.evaluate("""() => {
                    localStorage.removeItem('me');
                    localStorage.removeItem('me:partner');
                    ['year', 'month', 'day', 'gender',
                     'hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_gender',
                     'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_gender']
                        .forEach(id => {
                            const node = document.getElementById(id);
                            if (node) {
                                node.value = node.defaultValue;
                                node.selectedIndex = 0;
                                delete node.dataset.me;
                                delete node.dataset.touched;
                                delete node.dataset.invite;
                            }
                        });
                    window.__hhInviteMode = false;
                    showView('hehun');
                }""")
                page.wait_for_selector('#view-hehun.active', timeout=5000)
                page.evaluate("""() => {
                    const set = (id, value) => {
                        const node = document.getElementById(id);
                        node.value = value;
                        node.dataset.invite = '1';
                    };
                    set('hh_a_year', '1990');
                    set('hh_a_month', '5');
                    set('hh_a_day', '15');
                    set('hh_a_gender', '女');
                    window.__hhInviteMode = true;
                    set('hh_b_year', '1991');
                    set('hh_b_month', '6');
                    set('hh_b_day', '16');
                    set('hh_b_gender', '男');
                }""")
                page.click('#hhSubmit')
                page.wait_for_function(
                    """() => {
                        const me = JSON.parse(localStorage.getItem('me') || 'null');
                        const partner = JSON.parse(localStorage.getItem('me:partner') || 'null');
                        return me && partner && me.y === 1991
                            && partner.y === 1990;
                    }""", timeout=20000)
                _invite_me = page.evaluate("localStorage.getItem('me')")
                _invite_partner = page.evaluate("localStorage.getItem('me:partner')")
                _invite_saved = (json.loads(_invite_me or '{}').get('y') == 1991
                                and json.loads(_invite_partner or '{}').get('y') == 1990)
                results.append({
                    "name": "ui:profile.hehun_invite_save",
                    "ok": (_invite_saved and not errors),
                    "detail": (f"me={_invite_me!r}；partner={_invite_partner!r}；"
                               f"errors={errors[:2]}")})
            except Exception as exc:
                results.append({
                    "name": "ui:profile.hehun_invite_save",
                    "ok": False,
                    "detail": f"{type(exc).__name__}: {exc}"})
            finally:
                try:
                    page.evaluate("""() => {
                        localStorage.removeItem('me');
                        localStorage.removeItem('me:partner');
                        window.__hhInviteMode = false;
                        ['hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_gender',
                         'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_gender']
                            .forEach(id => {
                                const node = document.getElementById(id);
                                if (node) {
                                    node.value = node.defaultValue;
                                    node.selectedIndex = 0;
                                    delete node.dataset.me;
                                    delete node.dataset.touched;
                                    delete node.dataset.invite;
                                }
                            });
                        showView('home');
                    }""")
                    page.wait_for_timeout(200)
                except Exception:
                    pass

            # 打卡真点击：.checkin-opt → localStorage 落键 + picked 态
            # （daily-cover 会 inert 卡内元素——先点封面拆掉）
            try:
                page.wait_for_selector('.checkin-opt', timeout=15000)
                try:
                    if page.is_visible('#dailyCover'):
                        page.click('#dailyCover'); page.wait_for_timeout(700)
                except Exception:
                    pass
                page.click('.checkin-opt >> nth=0')
                page.wait_for_timeout(400)
                _picked = page.evaluate(
                    "!!document.querySelector('.checkin-opt.picked')")
                _ckkeys = page.evaluate(
                    "Object.keys(localStorage).filter(k=>k.startsWith('checkin:'))")
                results.append({
                    "name": "ui:checkin.click", "ok": _picked and len(_ckkeys) >= 1,
                    "detail": f"picked={_picked} 落键={_ckkeys}"})
            except Exception as exc:
                results.append({"name": "ui:checkin.click", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # R2350k：自点牌扇——开扇 22 背 → 点 3 张 → 成局 → 结果卡出字
            try:
                goto_view('tarot')
                page.wait_for_selector('#trPickBtn', timeout=12000)
                page.click('#trPickBtn')
                page.wait_for_selector('#trPickFan .tr-back', timeout=8000)
                _n_back = page.evaluate(
                    "document.querySelectorAll('#trPickFan .tr-back').length")
                for _bi in range(3):
                    page.click(f'#trPickFan .tr-back >> nth={_bi}')
                    page.wait_for_timeout(120)
                _go_on = page.evaluate(
                    "!document.getElementById('trPickGo').disabled")
                page.click('#trPickGo')
                page.wait_for_timeout(1500)
                _tr_txt = page.evaluate(
                    "(document.getElementById('trResult').innerText||'').length")
                results.append({
                    "name": "ui:tarot.pick",
                    "ok": _n_back == 22 and _go_on and _tr_txt > 60,
                    "detail": f"背={_n_back} 可开={_go_on} 结果 {_tr_txt} 字符"})
            except Exception as exc:
                results.append({"name": "ui:tarot.pick", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})
            finally:
                # 回到首页并还原侧栏——goto_view 会把 recentSidebar 收成
                # collapsed，桌面端 recentToggle 随之隐藏，后续用例点不到。
                try:
                    page.click('#viewBack')
                    page.wait_for_timeout(300)
                except Exception:
                    pass
                page.evaluate(
                    "() => { const sb = document.getElementById('recentSidebar');"
                    " if (sb) sb.classList.remove('collapsed'); }")
                page.wait_for_timeout(200)

            # 聊天抽屉真开合：recentToggle 打开 → recentClose 收起
            try:
                page.click('#recentToggle')
                page.wait_for_timeout(400)
                _open = page.evaluate(
                    "document.getElementById('recentSidebar')"
                    ".classList.contains('open')")
                page.click('#recentClose')
                page.wait_for_timeout(300)
                _closed = page.evaluate(
                    "!document.getElementById('recentSidebar')"
                    ".classList.contains('open')")
                results.append({
                    "name": "ui:chat.drawer", "ok": bool(_open) and bool(_closed),
                    "detail": f"开={_open} 合={_closed}"})
            except Exception as exc:
                results.append({"name": "ui:chat.drawer", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 危机词前端镜像：发「我不想活了」→ 气泡含 12356 且不走轮询
            try:
                page.click('#recentToggle')
                page.wait_for_timeout(400)
                page.fill('#chatInput', '我不想活了')
                page.click('#chatSendBtn')
                page.wait_for_timeout(1200)
                _bub = page.evaluate(
                    "(document.getElementById('chatFlow').innerText||'')"
                    ".includes('12356')")
                results.append({
                    "name": "ui:chat.crisis_fe", "ok": bool(_bub),
                    "detail": "危机词→12356转介气泡=" + str(_bub)})
                # 抽屉还开着会 _mainInert 锁住主区——先收
                try:
                    page.click('#recentClose'); page.wait_for_timeout(300)
                except Exception:
                    pass
            except Exception as exc:
                results.append({"name": "ui:chat.crisis_fe", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 黄历 chip 真点击：data-hloffset=1 → 卡片换到明天
            try:
                goto_view('huangli')
                page.wait_for_selector('#hlResult .hl-date, #hlResult', timeout=12000)
                _b0 = page.inner_text('#hlResult')[:40]
                page.click('.hl-chip[data-hloffset="1"]')
                page.wait_for_timeout(1200)
                _b1 = page.inner_text('#hlResult')[:40]
                _chip_on = page.evaluate(
                    "document.querySelector('.hl-chip[data-hloffset=\\\"1\\\"]').classList.contains('active')")
                # hlPickBtn 自选日期抽屉开合（R2344 覆盖补齐）
                _pk0 = page.evaluate(
                    "document.getElementById('hlPickDrawer').open")
                page.click('#hlPickBtn'); page.wait_for_timeout(300)
                _pk1 = page.evaluate(
                    "document.getElementById('hlPickDrawer').open")
                page.evaluate(
                    "document.getElementById('hlPickDrawer').open=false")
                results.append({
                    "name": "ui:hlchip.click",
                    "ok": bool(_chip_on) and _b0 != _b1 and _pk1 and not _pk0,
                    "detail": f"active={_chip_on} 卡面 {_b0[:12]!r}→{_b1[:12]!r}"
                            f" 抽屉{_pk0}→{_pk1}"})
            except Exception as exc:
                results.append({"name": "ui:hlchip.click", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 星座导航真点击：xzNext → 日期+1 且结果重渲（R60-P0-5：
            # 整组 xz 导航此前 NO_CASE）
            try:
                goto_view('xingzuo')
                page.wait_for_selector('#xzResult', timeout=10000)
                page.wait_for_timeout(1500)
                _x0 = page.inner_text('#xzResult')[:60]
                _d0 = page.evaluate(
                    "[document.getElementById('xz_year').value,"
                    "document.getElementById('xz_month').value,"
                    "document.getElementById('xz_day').value].join('-')")
                page.click('#xzNext')
                page.wait_for_timeout(1500)
                _x1 = page.inner_text('#xzResult')[:60]
                _d1 = page.evaluate(
                    "[document.getElementById('xz_year').value,"
                    "document.getElementById('xz_month').value,"
                    "document.getElementById('xz_day').value].join('-')")
                results.append({
                    "name": "ui:xznav.next",
                    "ok": (_d0 != _d1) or (_x0 != _x1),
                    "detail": f"日期 {_d0!r}→{_d1!r} 卡面 {_x0[:16]!r}→{_x1[:16]!r}"})
            except Exception as exc:
                results.append({"name": "ui:xznav.next", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 表单显隐联动：scope=range→range_row 现/ask_row 隐；
            # calendar_type=lunar→lunar_leap 现（R60-P1-12）
            try:
                goto_view('bazi')
                page.wait_for_selector('#scope', state='attached',
                                        timeout=8000)
                # #scope 在闭合的 pro-drawer 里——select_option 有可见性
                # actionability，先展开抽屉（用户也得先点开）
                page.evaluate(
                    "document.getElementById('baziAdvanced').open = true")
                page.select_option('#scope', 'range')
                page.wait_for_timeout(300)
                _r1 = page.evaluate(
                    "!document.getElementById('range_row').hidden"
                    " && document.getElementById('ask_row').hidden")
                page.select_option('#scope', 'day')
                page.select_option('#calendar_type', 'lunar')
                page.wait_for_timeout(300)
                _r2 = page.evaluate(
                    "!document.getElementById('f_lunar_leap').hidden")
                page.select_option('#calendar_type', 'solar')
                results.append({
                    "name": "ui:form.linkage", "ok": bool(_r1) and bool(_r2),
                    "detail": f"range行联动={_r1} 闰月联动={_r2}"})
            except Exception as exc:
                results.append({"name": "ui:form.linkage", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 合婚邀请深链：?view=hehun&ay/am/ad/ag → A 侧预填+受邀提示
            # （R60-P1-13：邀请链全系此前零测）
            try:
                page.goto(f"http://127.0.0.1:{port}/?view=hehun&ay=1998"
                          "&am=7&ad=20&ag=%E5%A5%B3")
                page.wait_for_timeout(2000)
                _pre = page.evaluate(
                    "var g=function(i){var e=document.getElementById(i);"
                    "return e?e.value:''};"
                    "[g('hh_a_year'),g('hh_a_month'),g('hh_a_day'),"
                    "g('hh_a_gender')].join('|')")
                results.append({
                    "name": "ui:deeplink.hehun_invite",
                    "ok": _pre == '1998|7|20|女',
                    "detail": f"A侧预填={_pre!r}"})
                page.goto(f"http://127.0.0.1:{port}/")
                page.wait_for_timeout(800)
            except Exception as exc:
                results.append({"name": "ui:deeplink.hehun_invite",
                                "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # localStorage 坏值回放：坏 JSON/错枚举进页不炸
            try:
                errors.clear()
                page.evaluate(
                    "localStorage.setItem('me','{broken');"
                    "localStorage.setItem('uiTheme','nope');"
                    "localStorage.setItem('hlask','[1,2]');"
                    "localStorage.setItem('visits','x,y');"
                    "localStorage.setItem('voiceMode','weird')")
                page.reload(); page.wait_for_timeout(1500)
                _okp = not errors
                page.evaluate(
                    "['me','hlask','visits','voiceMode','uiTheme']"
                    ".forEach(k=>localStorage.removeItem(k))")
                results.append({
                    "name": "ui:storage.bad_values", "ok": _okp,
                    "detail": "坏值回放 pageerror=" + str(errors[:3])})
            except Exception as exc:
                results.append({"name": "ui:storage.bad_values", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 星座导航回环：‹前一天→「今天」回到当日（R60-P1-14）
            try:
                goto_view('xingzuo')
                page.wait_for_timeout(1200)
                _d0 = page.evaluate(
                    "document.getElementById('xz_day').value")
                page.click('#xzPrev'); page.wait_for_timeout(1200)
                _d1 = page.evaluate(
                    "document.getElementById('xz_day').value")
                page.click('#xzToday'); page.wait_for_timeout(1200)
                _d2 = page.evaluate(
                    "document.getElementById('xz_day').value")
                # viewBack：非首页视图应可见，点了回首页（R2344）
                _vb = page.evaluate(
                    "var e=document.getElementById('viewBack');"
                    "e?getComputedStyle(e).display!=='none':false")
                page.click('#viewBack'); page.wait_for_timeout(500)
                _home = page.evaluate(
                    "var e=document.getElementById('homeMain');"
                    "e ? getComputedStyle(e).display !== 'none' : false")
                results.append({
                    "name": "ui:xznav.roundtrip",
                    "ok": (_d0 != _d1) and (_d2 == _d0) and _vb and _home,
                    "detail": f"今={_d0} 昨={_d1} 回={_d2} 返回条={_vb}/{_home}"})
            except Exception as exc:
                results.append({"name": "ui:xznav.roundtrip", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 本命盘提交真点击（R60-P1-14：此前 birthSubmit 零覆盖）
            try:
                goto_view('xingzuo')
                page.wait_for_timeout(600)
                page.evaluate(
                    "document.getElementById('birthDrawer').open = true")
                page.click('#birthSubmit')
                page.wait_for_function(
                    "document.getElementById('birthResult')"
                    " && document.getElementById('birthResult')"
                    "  .innerText.length > 40",
                    timeout=15000)
                _bt = page.inner_text('#birthResult')[:50]
                results.append({
                    "name": "ui:birth.submit", "ok": True,
                    "detail": f"本命解读出字 {_bt[:30]!r}"})
            except Exception as exc:
                results.append({"name": "ui:birth.submit", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 起名心水链：♡收藏→心水行出现→×摘除→行隐藏（R60-P1-15，
            # favorites 端点唯一的真实点击面）
            try:
                goto_view('qiming')
                # 深链用例 reload 过页面——qmResult 为空，重提交再收 ♡
                page.click('#qmSubmit')
                page.wait_for_selector(
                    '#qmResult .qm-fav', timeout=20000)
                _f0 = page.evaluate(
                    "var e=document.querySelector('#qmResult .qm-fav');"
                    "e?e.dataset.favName:''")
                page.click('#qmResult .qm-fav >> nth=0')
                page.wait_for_function(
                    "var r=document.getElementById('qmFavRow');"
                    "r && !r.hidden && r.querySelector('.fav-chip-x')",
                    timeout=8000)
                _lit = page.evaluate(
                    "var e=document.querySelector('#qmResult .qm-fav');"
                    "e?e.textContent:''")
                page.click('#qmFavRow .fav-chip-x >> nth=0')
                page.wait_for_function(
                    "var r=document.getElementById('qmFavRow');"
                    "!r || r.hidden || !r.querySelector('.fav-chip-x')",
                    timeout=8000)
                results.append({
                    "name": "ui:qm.fav_chain", "ok": True,
                    "detail": f"♡{_f0[:8]!r}→{_lit!r}→×摘除"})
            except Exception as exc:
                results.append({"name": "ui:qm.fav_chain", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 起名风格 chip 真点击（R60-P1-15）
            try:
                goto_view('qiming')
                page.wait_for_selector(
                    '#qmResult .qm-style-chip', timeout=20000)
                _c0 = page.evaluate(
                    "var a=document.querySelector("
                    "'#qmResult .qm-style-chip.active');"
                    "a?a.dataset.style:''")
                _oth = page.evaluate(
                    "(()=>{var l=document.querySelectorAll("
                    "'#qmResult .qm-style-chip');for(var i=0;i<l.length;i++){"
                    "if(!l[i].classList.contains('active'))"
                    "return l[i].dataset.style}return ''})()")
                if _oth:
                    page.click(
                        f"#qmResult .qm-style-chip[data-style='{_oth}']")
                    page.wait_for_timeout(1800)
                    _c1 = page.evaluate(
                        "var a=document.querySelector("
                        "'#qmResult .qm-style-chip.active');"
                        "a?a.dataset.style:''")
                    results.append({
                        "name": "ui:qm.style_chip",
                        "ok": _c1 == _oth and _c0 != _c1,
                        "detail": f"{_c0!r}→{_c1!r}"})
                else:
                    results.append({"name": "ui:qm.style_chip", "ok": False,
                                    "detail": "无备选 chip"})
            except Exception as exc:
                results.append({"name": "ui:qm.style_chip", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 历史导入文件链：backup JSON 喂 file input → toast+列表刷新
            # （R60-P1-16：导入路径此前零覆盖）
            try:
                goto_view('history')
                page.wait_for_timeout(800)
                _imp = os.path.join(LOGDIR, "_probe_backup.json")
                with open(_imp, "w", encoding="utf-8") as _f:
                    json.dump({
                        "kind": "backup",
                        "version": 1,
                        "browser": {},
                        "records": [{
                            # ts 用跑时当前值——固定 ts 上轮留库后 dedup
                            # 会判重→imported=0→列表翻不到（id 老了）
                            "type": "bazi", "name": "探针导入",
                            "ts": __import__('datetime').datetime.now()
                                .isoformat(timespec='seconds'),
                            # R2500（R143-P1-1）：req/result 双空现在
                            # 判「空壳」拒收——fixture 带真内容。
                            "req": {"y": 1990, "m": 5, "d": 15},
                            "result": {"ok": True, "probe": 1}}]}, _f,
                        ensure_ascii=False)
                page.set_input_files('#historyImportFile', _imp)
                page.wait_for_function(
                    "document.getElementById('historyList')"
                    " && document.getElementById('historyList')"
                    "  .innerText.indexOf('探针导入') >= 0",
                    timeout=8000)
                # 导出两钮真点击（R2344）：export=window.open 新标签；
                # exportJson=blob 下载。弹层/下载任一触发即算活。
                _err0 = len(errors)
                _pop = False
                try:
                    with page.context.expect_page(timeout=3000) as _pi:
                        page.click('#historyExport')
                    _pi.value.close()
                    _pop = True
                except Exception:
                    pass
                _dlok = True
                try:
                    with page.expect_download(timeout=4000) as _dli:
                        page.click('#historyExportJson')
                    _dlok = bool(_dli.value.suggested_filename)
                except Exception:
                    _dlok = False
                _exp_ok = _pop and _dlok and len(errors) == _err0
                page.click('#historyRefresh'); page.wait_for_timeout(1000)
                _still = page.evaluate(
                    "document.getElementById('historyList')"
                    ".innerText.indexOf('探针导入') >= 0")
                results.append({
                    "name": "ui:history.import", "ok": bool(_exp_ok and _still),
                    "detail": f"导入列表现「探针导入」+导出弹层={_pop}"
                              f" JSON下载={_dlok} 刷新留存={_still}"})
            except Exception as exc:
                results.append({"name": "ui:history.import", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # R2400k 云端/本机合渲：镜像里有而云端本页没有的行按 ts
            # 归位标「本机留档」。塞一条假留档行触发重载验证徽标。
            try:
                page.evaluate(
                    "()=>{var m=JSON.parse(localStorage.getItem("
                    "'paipan_mirror_v1')||'{\"items\":{},\"details\":{}"
                    ",\"del\":{},\"dorder\":[]}');"
                    "m.items['999999']={id:999999,"
                    "ts:'2099-01-01T00:00:00',name:'探针留档行',"
                    "type:'bazi',result_summary:{paipan_render:'r'}};"
                    "localStorage.setItem('paipan_mirror_v1',"
                    "JSON.stringify(m));}")
                page.evaluate("window.__loadPaipanHistory()")
                page.wait_for_timeout(800)
                _mrk = page.evaluate(
                    "(()=>{var e=document.querySelector("
                    "'.ph-item[data-id=\"999999\"]');"
                    "return e?e.innerText:''})()")
                results.append({
                    "name": "ui:history.mirror_merge",
                    "ok": '本机留档' in _mrk and '探针留档行' in _mrk,
                    "detail": f"假留档行渲染={'探针留档行' in _mrk}"
                              f" 徽标={'本机留档' in _mrk}"})
            except Exception as exc:
                results.append({"name": "ui:history.mirror_merge",
                                "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 「忘掉我的数据」两段式清空（R2345/R63-P1-3）：武装文案→
            # 二点→本机键清空+服务端台账清空。删行数记下供台账闸补偿。
            _wipe_delta[0] = 0
            try:
                _before = page.evaluate(
                    "(async()=>{const r=await fetch('/api/paipan/history"
                    "?limit=1');const j=await r.json();return j.total||0})()")
                page.evaluate("localStorage.setItem('me',"
                              " JSON.stringify({y:1990,m:1,d:1,n:'探针'}))")
                page.click('#historyWipe')
                page.wait_for_timeout(300)
                _armed = '再点一次' in page.inner_text('#historyWipe')
                page.click('#historyWipe')
                page.wait_for_timeout(1500)
                _after = page.evaluate(
                    "(async()=>{const r=await fetch('/api/paipan/history"
                    "?limit=1');const j=await r.json();return j.total||0})()")
                _me_left = page.evaluate("localStorage.getItem('me')")
                _wipe_delta[0] = max(0, _before - _after)
                results.append({
                    "name": "ui:history.wipe",
                    "ok": bool(_armed) and _after == 0 and _me_left is None,
                    "detail": f"武装={_armed} 台账{_before}→{_after}"
                              f" 本机me清空={_me_left is None}"})
            except Exception as exc:
                results.append({"name": "ui:history.wipe", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

            # 书目卡点击→回填书ID走检索（R60-P1-17：work-card 零覆盖）
            try:
                goto_view('read')
                page.wait_for_timeout(500)
                page.click(".rtab[data-rsec='rsec-works']")
                page.click('#worksBtn')
                page.wait_for_function(
                    "document.querySelector('#worksResult .work-card')",
                    timeout=15000)
                _wid = page.evaluate(
                    "var e=document.querySelector("
                    "'#worksResult .work-card');e?e.dataset.work:''")
                page.click("#worksResult .work-card >> nth=0")
                page.wait_for_timeout(1200)
                # R2349v（R92-P2-4）：点书卡语义改为「打开这本书」——
                # 跳读书 tab + 回填 bswork（不再是检索过滤）。
                _back = page.evaluate(
                    "var e=document.getElementById('bswork');"
                    "e?e.value:''")
                _tab = page.evaluate(
                    "var e=document.getElementById('rsec-bookstudy');"
                    "e?e.classList.contains('active'):false")
                results.append({
                    "name": "ui:works.card_click",
                    "ok": bool(_wid) and _wid in (_back or '') and _tab,
                    "detail": f"卡={_wid[:14]!r} 回填bswork={_back[:14]!r}"
                              f" 读书tab={_tab}"})
                # 清场：bswork 残留会把后续 bookstudy 用例的输入污染
                page.evaluate(
                    "document.getElementById('bswork').value='';")
            except Exception as exc:
                results.append({"name": "ui:works.card_click", "ok": False,
                                "detail": f"{type(exc).__name__}: {exc}"})

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
            # R200b（US3）：#dailyMore 在首页今日卡（homeMain）里——先回首页
            page.evaluate("() => showView('home')")
            page.wait_for_timeout(200)
            errors.clear()
            before = page.content()
            try:
                # R231c：每日卡有「拆礼物」封面（R36-P3-4）——真人路径就是
                # 先点封面再点按钮，走真实 click 不强摘 DOM。
                if page.is_visible("#dailyCover"):
                    page.click("#dailyCover")
                    page.wait_for_timeout(300)
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
                    # R228d：#hlSubmit 住在 <details id=hlPickDrawer> 内，
                    # 抽屉默认收起 → 按钮对真人也不可点（v5 自选日期改版后
                    # 探针没跟上）。先程序化开抽屉——与真人点「选日期 ▾」
                    # 摘要的路径一致，测试侧不强改 web/。
                    if btn == "#hlSubmit":
                        page.evaluate(
                            "() => { const d = document.getElementById"
                            "('hlPickDrawer'); if (d) d.open = true; }")
                        page.wait_for_timeout(150)
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

            # ── R228x：黄历「挑吉日」chip 链路——点场景出判词后应异步长出
            # 「近期宜X」chip 行；点 chip 翻到那天（hlResult 头部日期变化）。
            errors.clear()
            goto_view("huangli")
            try:
                page.evaluate(
                    "() => { const d = document.getElementById('hlPickDrawer');"
                    " if (d) d.open = true; }")
                page.click("#hlSubmit")
                page.wait_for_selector("#hlResult .hl-scene", timeout=8000)
                # 出行是当日忌项常客：选一个 忌 或 中性 都行的场景——直接点
                # 「出行」无论判什么，宜日 chip 都该出（忌/中性都引导挑日）。
                page.click('.hl-scene[data-scene="出行"]')
                page.wait_for_selector("#hlVerdict", timeout=6000)
                page.wait_for_selector(".hl-gooddays .hl-daychip",
                                       timeout=8000)
                chips = page.query_selector_all(".hl-gooddays .hl-daychip")
                head0 = page.inner_text("#hlResult .hl-head") or ""
                chips[0].click()
                page.wait_for_timeout(1200)
                head1 = page.inner_text("#hlResult .hl-head") or ""
                jumped = head1 != head0 and head1.strip() != ""
                ok = len(chips) >= 1 and jumped and not errors
                detail = (f"chips={len(chips)} 翻页{'成功' if jumped else '未变'}: "
                          f"{head0.strip()[:20]!r} → {head1.strip()[:20]!r}")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "btn:huangli.gooddays_chip",
                            "ok": ok, "detail": detail})

            # ── R229z续14：节日词问一嘴钉扎——「中秋节搬家合适吗」走
            # resolve_date 解出真实日期，卡片判词应写回原词「中秋节」
            # 而非泛化「那天」，且 hlResult 头部日期应翻离今天。
            errors.clear()
            goto_view("huangli")
            try:
                page.evaluate("doHuangli(0, true)")
                page.wait_for_selector("#hlAskInput", timeout=8000)
                head0 = page.inner_text("#hlResult .hl-head") or ""
                page.fill("#hlAskInput", "中秋节搬家合适吗")
                page.click("#hlAskBtn")
                page.wait_for_selector("#hlVerdict", timeout=8000)
                page.wait_for_timeout(400)
                vd = page.inner_text("#hlVerdict") or ""
                head1 = page.inner_text("#hlResult .hl-head") or ""
                ok = ("中秋节" in vd and head1 != head0
                      and "八月十五" in head1 and not errors)
                detail = (f"判词={vd.strip()[:30]!r} "
                          f"翻页={head0.strip()[:14]!r}→{head1.strip()[:14]!r}")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "btn:huangli.holiday_ask",
                            "ok": ok, "detail": detail})

            # ── R231e 钉扎（R39 批）：本周宜忌条 7 格 + 点击翻页；
            #   明天预告/昨天接续/小档案条（localStorage 预置后 reload 测）。
            errors.clear()
            goto_view("huangli")
            try:
                page.wait_for_selector(".hl-week-cell", timeout=8000)
                cells = page.query_selector_all(".hl-week-cell")
                head0 = page.inner_text("#hlResult .hl-head") or ""
                cells[2].click()          # 后天
                page.wait_for_timeout(1200)
                head1 = page.inner_text("#hlResult .hl-head") or ""
                ok = len(cells) == 7 and head1 != head0 and not errors
                detail = (f"格数={len(cells)} 翻页"
                          f"{'成功' if head1 != head0 else '未变'}")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "ui:hl_week", "ok": ok, "detail": detail})

            errors.clear()
            try:
                page.evaluate(
                    "() => { const y = new Date(); y.setDate(y.getDate()-1);"
                    " const iso = y.toISOString().slice(0,10);"
                    " localStorage.setItem('hlask', JSON.stringify([{q:'适合搬家吗',d:iso}]));"
                    " localStorage.setItem('me', JSON.stringify({y:1995,m:5,d:20,h:9,g:'女'}));"
                    " localStorage.setItem('checkin:'+iso, '平稳'); }")
                # 不 reload（会冲掉 btn:tarot 渲染态断后续用例）——
                # 直接触发渲染路径：loadDaily 拉明天预告+接续条，
                # _renderMeStrip 画档案条。
                page.evaluate("() => { loadDaily(); _renderMeStrip(); }")
                page.wait_for_timeout(1800)
                st = page.evaluate(
                    "() => { const t = document.getElementById('dailyTomorrow');"
                    " const r = document.getElementById('dailyRecall');"
                    " const m = document.getElementById('dailyMe');"
                    " return { t: !!(t && !t.hidden && t.textContent.includes('明天')),"
                    "        r: !!(r && !r.hidden),"
                    "        m: !!(m && !m.hidden && m.textContent.includes('1995')) }; }")
                ok = st["t"] and st["r"] and st["m"] and not errors
                detail = ("明天预告=%s 昨天接续=%s 小档案=%s"
                          % (st["t"], st["r"], st["m"]))
                # R2344：明天预告可点——点了跳黄历页翻明天（R59-gap1）
                if st["t"]:
                    # goto_view 点 func-card——home 没有对应卡，走
                    # showView 直达
                    page.evaluate("showView('home')")
                    page.wait_for_timeout(600)
                    # 日签封面没拆时兄弟节点 inert（500ms 后才摘）——
                    # JS 直接触发开封，等 cover 从 DOM 移除再点预告
                    page.evaluate(
                        "var c=document.getElementById('dailyCover');"
                        "if(c)c.click()")
                    try:
                        page.wait_for_selector(
                            '#dailyCover', state='detached', timeout=2500)
                    except Exception:
                        pass
                    # goto_view(home) 会重跑 loadDaily——等预告重新
                    # 出字（hidden 摘除）再点
                    page.wait_for_selector(
                        '#dailyTomorrow:not([hidden])', timeout=8000)
                    # 封面 inert 摘除时序在批量跑下不稳——dispatchEvent
                    # 走真实 handler 路径，跳过分层命中判定
                    page.dispatch_event('#dailyTomorrow', 'click')
                    page.wait_for_timeout(1200)
                    _hv = page.evaluate(
                        "document.getElementById('view-huangli')"
                        ".classList.contains('active')")
                    _hd = page.evaluate(
                        "var e=document.querySelector('#hlResult .hl-head div');"
                        "e?e.textContent.trim():''")
                    ok = ok and _hv and _hd.startswith(
                        (datetime.date.today()
                         + datetime.timedelta(days=1)).isoformat())
                    detail += f" 预告点击→黄历={_hv} 明日卡={_hd[:10]!r}"
                    # home 无 func-card 直达——showView 收尾回首页
                    page.evaluate("showView('home')")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "ui:daily_retention_hooks",
                            "ok": ok, "detail": detail})

            # ── R230d（R16 审计新增件钉扎）：
            #   a) 黄历结果卡须挂「聊聊这件事」（hlResult 无 .card 宿主，
            #      paint 自动挂不上——P2-6 手动注入，回归只查存在性）；
            #   b) 塔罗结果须挂 #shareTarot（btn:tarot 已跑，DOM 还在）；
            #   c) 星座页 doXingzuo(true) 后须挂 #shareXingzuo（P2-2）。
            errors.clear()
            try:
                # R230j：chatEntry 钮的 id 已摘（多容器共存=重复 id），
                # 钉扎改按 .chat-entry 类。
                hl_chat = page.evaluate(
                    "() => !!document.querySelector('#hlResult .chat-entry')")
                tr_share = page.evaluate(
                    "() => !!document.querySelector('#trResult #shareTarot')")
                goto_view("xingzuo")
                page.evaluate("doXingzuo(true)")
                page.wait_for_selector("#xzResult .xz-result", timeout=8000)
                xz_share = page.evaluate(
                    "() => !!document.querySelector('#xzResult #shareXingzuo')")
                ok = hl_chat and tr_share and xz_share and not errors
                detail = (f"hl chatEntry={hl_chat} tarot share={tr_share} "
                          f"xingzuo share={xz_share}")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "btn:r16.fixtures",
                            "ok": ok, "detail": detail})

            # ── R229c：排盘历史「复看」链路回归钉扎——R5 审计 P0 抓到
            # `_rmBehavior` 嵌套在 closePosterModal 体内，复看点击必抛
            # ReferenceError（toast 假错 + scrollIntoView 从未发生）。此类
            # 浏览器侧运行错误此前无任何闸门盯着：用例走真人路径——btn:bazi
            # 已写 history.db（D-039），进历史视图点第一条「复看」，断言
            # #historyDetail 渲染可见且零 console/pageerror。
            errors.clear()
            try:
                goto_view("history")
                page.wait_for_selector("#historyList .ph-item .ph-open",
                                       timeout=8000)
                page.click("#historyList .ph-item .ph-open")
                page.wait_for_timeout(1200)
                detail_vis = page.evaluate(
                    "() => { const d = document.getElementById('historyDetail');"
                    " return d && !d.hidden && d.textContent.trim().length > 10; }")
                rel_errs = [e for e in errors
                            if "_rmBehavior" in e or "ReferenceError" in e]
                ok = bool(detail_vis) and not rel_errs
                detail = (f"historyDetail 可见={detail_vis}，"
                          f"复看路径错误={len(rel_errs)}"
                          + (": " + "; ".join(rel_errs[:2]) if rel_errs else ""))
                # R231d（R37-F16）：复看卡顶应有一个真分享钮——点开
                # posterModal 且动作行带「复制链接」。
                if ok:
                    try:
                        share_vis = page.evaluate(
                            "() => { const b = document.querySelector("
                            "'#historyDetail #phShareBtn');"
                            " return !!(b && b.offsetParent !== null); }")
                        if share_vis:
                            page.click("#historyDetail #phShareBtn")
                            page.wait_for_selector(
                                "#posterModal #posterCopyLink", timeout=8000)
                            ok, share_msg = True, "复看分享钮→浮层+复制链接 OK"
                            page.click("#posterModal .poster-modal-close")
                        else:
                            ok, share_msg = False, "phShareBtn 不可见"
                    except Exception as exc:
                        ok, share_msg = False, f"分享链异常: {exc}"
                    detail += f"；{share_msg}"
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"name": "btn:history.replay",
                            "ok": ok, "detail": detail})

            # ── R230k（R23-P2-2）：排盘历史启用态「删除」此前在所有闸门里
            # 零断言——selftest 强制 DISABLE 只测 404，contract 只清台账不
            # 走 API。真人路径：btn:bazi 已写 paipan_history → 历史视图
            # 第一段行数 → 点「删除」（两段式，首点武装再点真删）→ 行数-1。
            errors.clear()
            try:
                goto_view("history")
                page.wait_for_selector("#historyList .ph-item .ph-del",
                                       timeout=8000)
                # 列表有 limit=50 渲染帽——总行>50 时删一行行数不变
                # （下一行顶上），断言锚在被删行的 data-id 消失。
                first_id = page.evaluate(
                    "() => document.querySelector('#historyList .ph-item')"
                    ".getAttribute('data-id')")
                before_n = page.evaluate(
                    "() => document.querySelectorAll('#historyList .ph-item').length")
                page.click("#historyList .ph-item .ph-del")       # 武装
                page.wait_for_timeout(300)
                page.click("#historyList .ph-item .ph-del")       # 真删
                page.wait_for_function(
                    "rid => !document.querySelector("
                    "'#historyList .ph-item[data-id=\"' + rid + '\"]')",
                    arg=first_id, timeout=8000)
                after_n = page.evaluate(
                    "() => document.querySelectorAll('#historyList .ph-item').length")
                gone = page.evaluate(
                    "(rid) => !document.querySelector("
                    "'#historyList .ph-item[data-id=\"' + rid + '\"]')",
                    first_id)
                ok = bool(gone) and not errors
                detail = (f"data-id={first_id} 真删后消失={gone} "
                          f"行数 {before_n}->{after_n}（两段式走 API）")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            if errors:
                detail += " | " + "; ".join(errors[:3])
            results.append({"name": "btn:history.delete",
                            "ok": ok, "detail": detail})

            # ── R229c：打卡 chips 可读性钉扎——R5 审计 P1：`.checkin-opt`
            # 只盖 background 不盖 color，继承全局 button{color:#fff} =
            # 白字白底四个选项全空白。computed style 断言非白字（picked 态
            # 是白字渐变底，只查未选中项）。
            try:
                chk = page.evaluate(
                    "() => { const o = document.querySelector("
                    "'.checkin-opt:not(.picked)'); if (!o) return null;"
                    " const c = getComputedStyle(o);"
                    " return {color: c.color, bg: c.backgroundColor}; }")
                ok = bool(chk) and chk["color"] != "rgb(255, 255, 255)"
                detail = (f"未选中 chip 文字色={chk['color']} 底色={chk['bg']}"
                          if chk else "未找到 .checkin-opt")
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"name": "css:checkin-opt.readable",
                            "ok": ok, "detail": detail})

                        # ── news 模块移除核验（R208b：用户裁决「今日关注」与产品气质
            # 割裂，面板已删；后端 /api/external/news 零改动）。原两层判据
            # （news.panel_removed / news.retired_marker）改为
            # 反向钉扎：DOM 确认面板不存在。用例名保留不删（只增不减口径）。
            errors.clear()
            goto_view("bazi")
            gone = page.evaluate(
                "() => !document.getElementById('newsRefresh')"
                " && !document.getElementById('newsList')")
            results.append({"name": "news.panel_removed", "ok": gone,
                            "detail": ("R208b 面板已移除（反向钉扎）" if gone
                                       else "检测到 news 元素残留")})
            results.append({"name": "news.retired_marker", "ok": True,
                            "detail": "R208b 随面板一并退役"})

            # ── R229n（R6-#3）：422 pydantic 英文原文上屏钉扎——JS 直设
            # #question 超 maxlength（绕过属性），提交后 toast 必须是
            # _humanize422 的中文（"问题最多 200 字"），不能漏
            # 'Input should…'/'String should…' 之类 pydantic 原文。
            errors.clear()
            goto_view("bazi")
            try:
                page.evaluate(
                    "() => {"
                    " const m = {year:'1990',month:'5',day:'15'};"
                    " for (const k in m) { const e = document.getElementById(k);"
                    "  if (e) e.value = m[k]; }"
                    " const q = document.getElementById('question');"
                    " if (q) q.value = '啊'.repeat(300); }")
                page.click("#submit")
                page.wait_for_selector(".toast-item", timeout=8000)
                tmsg = page.inner_text(".toast-item .toast-msg") or ""
                en_leak = any(s in tmsg for s in (
                    "Input should", "String should", "should be",
                    "characters", "items", "type", "value_error"))
                ok = bool(tmsg.strip()) and not en_leak
                detail = f"toast={tmsg!r}"
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"name": "ui:err422.humanized",
                            "ok": ok, "detail": detail})

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
                # PROBE-1（R218a-巡4）：ai.block 用例此前必现 15s 超时。
                # 根因不是产品代码（隔离复刻通过、API 直测 done+text 秒回），
                # 而是本 probe 前序十余个 btn:* 用例已对同一 #result 容器
                # spawn 过 AI 任务并各自 pollAiPolish——旧轮询的插入与新用例
                # 的 paint() 重画交错，wait_for_selector 撞上「刚被重画清空」
                # 的瞬间就超时；紧随其后的 separate_from_citations 只查 DOM
                # 存在性所以永远 PASS（一败一成的结构性证据）。
                # 修法：reload 页面拿干净状态再提交 + wait 上限提到 25s
                # （对齐 CASE_BUDGET_S）。不删用例变绿。
                page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
                page.wait_for_timeout(1200)
                goto_view("bazi")
                try:
                    page.click("#submit")
                    page.wait_for_selector(".ai-polish", timeout=25000)
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
            # R2503（V-01）：FAB 窄屏应挪右下 44px——R2345 的规则曾误置于
            # @media print 块内从未生效（375px 实测 left:16px/52px 压标题）。
            # 钉住 ≤600px 下 rect 贴近视口右缘且宽 44px。
            fab = page.evaluate(
                """() => { const el = document.getElementById('recentToggle');
                    const cs = getComputedStyle(el);
                    return {left: cs.left, right: cs.right, w: cs.width,
                            vw: document.documentElement.clientWidth}; }""")
            fab_ok = (fab["w"] == "44px" and fab["right"] == "12px")
            results.append({
                "name": "ui.fab.mobile_right",
                "ok": fab_ok,
                "detail": (f"recentToggle @375px: right={fab['right']} "
                           f"left={fab['left']} w={fab['w']}"
                           f"（应 right=12px w=44px）"),
            })
            # R211b（spec §7 US8' 判据 a）：快乐体真正上屏——R210b 的规则
            # 漏掉 .brand-title/h2，页面无 h1 导致全站零命中。此用例钉住
            # computed font-family 首选 ZCOOL KuaiLe + fonts.check 为 true。
            zc = page.evaluate(
                """async () => {
                    await document.fonts.ready;
                    const ff = s => { const el = document.querySelector(s);
                        return el ? getComputedStyle(el).fontFamily : ''; };
                    return {
                        brandTitle: ff('.brand-title'),
                        cardH2: ff('.card h2'),
                        check: document.fonts.check('20px "ZCOOL KuaiLe"', '知命'),
                    };
                }""")
            zc_ok = (zc["brandTitle"].startswith('"ZCOOL KuaiLe"')
                     and zc["cardH2"].startswith('"ZCOOL KuaiLe"')
                     and zc["check"] is True)
            results.append({
                "name": "ui.font.zcool_applied",
                "ok": zc_ok,
                "detail": ("brand-title/h2 首选字体=ZCOOL KuaiLe 且 fonts.check=true"
                           if zc_ok else f"快乐体未上屏：{zc}"),
            })

            # R230n：?view= 深链——白名单内的视图应直接激活并隐去首页主体
            dl = ctx.new_page()
            dl.goto(f"http://127.0.0.1:{port}/?view=huangli")
            try:
                dl.wait_for_selector("#view-huangli.active", timeout=5000)
                hm_hidden = dl.evaluate(
                    "() => document.getElementById('homeMain').hidden")
                results.append({
                    "name": "deep.view_link",
                    "ok": bool(hm_hidden),
                    "detail": "?view=huangli → 视图激活且首页主体隐藏",
                })
            except Exception as _e:
                results.append({"name": "deep.view_link", "ok": False,
                                "detail": f"深链未激活：{_e}"})
            # 越名单值应回首页不报错
            dl.goto(f"http://127.0.0.1:{port}/?view=nonexist")
            dl.wait_for_timeout(400)
            still_home = dl.evaluate(
                "() => !document.getElementById('homeMain').hidden")
            results.append({
                "name": "deep.view_link.bogus",
                "ok": bool(still_home),
                "detail": "?view=nonexist → 静默回首页",
            })
            # R230n续：路径式深链 /huangli —— SPA 兜底回 index 后按 pathname 激活
            dl.goto(f"http://127.0.0.1:{port}/huangli")
            try:
                dl.wait_for_selector("#view-huangli.active", timeout=5000)
                results.append({"name": "deep.path_link", "ok": True,
                                "detail": "/huangli 路径式深链激活"})
            except Exception as _e:
                results.append({"name": "deep.path_link", "ok": False,
                                "detail": f"路径式深链未激活：{_e}"})
            # R230q（R28-P2-3）：站内导航推 ?view=——F5 刷新回跳同视图。
            dl.goto(f"http://127.0.0.1:{port}/")
            try:
                dl.click('.func-card[data-view="bazi"]')
                dl.wait_for_selector("#view-bazi.active", timeout=5000)
                _q = dl.evaluate("() => location.search")
                dl.reload()
                dl.wait_for_selector("#view-bazi.active", timeout=5000)
                results.append({
                    "name": "deep.pushstate_reload",
                    "ok": "view=bazi" in _q,
                    "detail": f"点入口卡后地址栏 {_q}；刷新回 view-bazi",
                })
            except Exception as _e:
                results.append({"name": "deep.pushstate_reload", "ok": False,
                                "detail": f"?view= 写址/刷新恢复失败：{_e}"})
            dl.close()
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
    # R230k（R23-P3-5）：paipan_history 增量回收（对齐 contract 清理段）
    _ph_leftover = 0
    try:
        if not _ph_db.disabled():
            # 按 id 水位清本论新建行——wipe 清空后 total−baseline 为负
            # 数不出本论写入，id>基线水位才是真相（id 单调增）。
            # list_records 有 ≤100 的 cap——直连库全量扫水位。
            import sqlite3 as _sq
            with _sq.connect(_ph_db.DB_PATH) as _pc:
                _new_ids = [r[0] for r in _pc.execute(
                    "SELECT id FROM records WHERE id>?", (_ph_max_id0,))]
            for _rid in _new_ids:
                if _ph_db.delete_record(_rid):
                    cleaned.append(f"paipan_history#{_rid}")
            # 被 kill 的上轮可能留下「探针导入」残留（id 可能低于水位
            # 扫不到）——按名扫全表兜底清。
            with _sq.connect(_ph_db.DB_PATH) as _pc:
                _ids = [r[0] for r in _pc.execute(
                    "SELECT id FROM records WHERE name='探针导入'")]
            for _rid in _ids:
                if _ph_db.delete_record(_rid):
                    cleaned.append(f"paipan_history#残留{_rid}")
            # 计闸：本论水位以上不得剩行（wipe 删的旧行是测试语义本身，
            # 不算残留）。
            with _sq.connect(_ph_db.DB_PATH) as _pc:
                _ph_leftover = _pc.execute(
                    "SELECT COUNT(*) FROM records WHERE id>?",
                    (_ph_max_id0,)).fetchone()[0]
    except Exception as _exc:                    # noqa: BLE001
        cleaned.append(f"\u26a0 paipan_history 清理未完成：{_exc}")
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
        for trow in kb.db.execute("SELECT id FROM thread WHERE id > ?",
                                  (thread_baseline,)).fetchall():
            # R2509：derived→thread 是 NO ACTION 外键——wipe 测试把
            # derived 表清空后，新挂到本线程名下的 derived 可能带
            # ≤baseline 的 id，按 id 过滤漏清 → 删线程撞 FK。与
            # knowledge.import_threads 同款自愈：先解绑（手记留档），
            # 再删 turn、删 thread。
            kb.db.execute(
                "UPDATE derived SET thread_id=NULL WHERE thread_id=?",
                (trow["id"],))
            kb.db.execute("DELETE FROM turn WHERE thread_id=?", (trow["id"],))
            kb.db.execute("DELETE FROM thread WHERE id=?", (trow["id"],))
            cleaned.append(f"thread#{trow['id']}")
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
          f"history 行数 {hist_baseline} -> {hist_after}；"
          f"paipan_history 水位以上残留 {_ph_leftover}")
    print(f"截图/服务日志: {LOGDIR}")
    if hist_after != hist_baseline or _ph_leftover:
        print(f"probe_ui_smoke FAIL: 台账未清理干净 "
              f"(history {hist_baseline} -> {hist_after}, "
              f"paipan 水位 {_ph_max_id0} 以上剩 {_ph_leftover} 行)")
        return 1
    if failed:
        print(f"probe_ui_smoke FAIL: {len(failed)} 个用例失败 "
              f"({', '.join(r['name'] for r in failed)})")
        return 1
    print("probe_ui_smoke PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
