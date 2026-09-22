"""probe_contract.py — 前后端字段名契约闸门（审查轨 R118a，D-127a）。

**为什么存在**：后端自测（当时 `web/app.py --selftest` 130 条断言，现 `web/selftest.py` 268 条）全部是后端 TestClient
断言——它们只检查*后端返回了什么*，从不检查*前端读了什么*。三处字段名漂移
（`j.llm_out` / `j.items` / `j.addresses`）就是这么漏过 130 条断言的：后端返回
`llm` / `records` / `evidence`，前端读另一个名字，结果区永远空白，而自测全绿。

**做法**（静态提取 + 真实响应比对，不靠人工维护清单）：
  1. 从前端 JS 载体切出每个 handler 块（R178b 后是 `web/static/app.js`，
     重构前是 `index.html` 的 <script> 区，两种布局都支持）；
  2. 块内定位 `await resp.json()` 的接收变量（`j`），追踪它派生的对象变量
     （`const ben = j.ben || {}`）与迭代变量（`j.hits.forEach((h, i) =>`）；
  3. 收集这些变量上的**每一个字段名读取**，记录 文件:行号；
  4. 用固定参数对同一个端点发真实请求，逐个字段名在真实响应里查存在性。

**三类判定**（严重级判定权在审查轨，此处只给可复验的机器判据）：
  * HARD  —— 字段不存在且**该行没有 `||` 兜底** → 前端拿到 undefined，
            结果区空白或抛 TypeError。卡闸门（退出码 1）。
  * TYPE  —— 字段存在但值是 **object**，而前端把它整个塞进 `esc(...)`。
            JS `String({a:1})` === `"[object Object]"`，页面渲染出这个字面量，
            属"数据显示错误"，卡闸门。
            注意 **array 不同**：`String(["宜","忌"])` === `"宜,忌"`，逗号拼接
            可读但丢结构 → 归 SOFT（体验瑕疵，进 OPTIMIZE_BACKLOG）。
            这条区分是实测 JS 语义，不是偏好——用同一档会误报为卡闸门缺陷。
  * SOFT  —— 字段不存在但同行有 `||` 兜底（永远走兜底分支），或 array 被
            esc() 逗号拼接 → 不卡闸门，进 OPTIMIZE_BACKLOG。
  * SKIP  —— 列表为空导致元素字段无法判定。fixture 有责任让列表非空；
            仍为空则显式报 SKIP，不假装通过（宪法第一条：跑不出来就当它是错的）。

**写端点污染纪律（L-22）**：本 probe 会 POST /api/bazi（history.db）与
POST /api/favorites（knowledge.db）以便让 records/favorites 列表非空。两者
在退出前按 id 删除本轮新增行，并复验行数回到基线。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_contract.py
退出码：0 全绿；1 有 HARD/TYPE；2 probe 自身无法判定（SKIP 或 fixture 失败）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 注意不要把 ROOT/web 加进 sys.path：R178b 起 web 是**包**（有 __init__.py），
# app.py 用 `from . import deps, errors` 相对导入。把 web/ 本身加进 sys.path
# 会让 `import app` 以顶层模块身份加载 → ImportError: attempted relative
# import with no known parent package。必须以 `web.app` 形式导入。
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Windows 控制台默认 GBK，报告含大量中日韩原文 —— 强制 UTF-8，否则实测输出
# 在终端里变成乱码，"实测原文"就不可复验了（宪法第一条）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# R228z：同进程加载 web.app，宿主的 BOOKS_LLM_API_KEY 会直接渗进来——
# 探针必须离线（跟 selftest.run() 同一口径），否则契约读点会被 LLM
# 慢调用拖到超时/挂死。
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")

STATIC = os.path.join(ROOT, "web", "static")
# R178b 把内联 JS 拆到 app.js。优先扫 app.js，回落 index.html（兼容重构前后）。
# 找不到任何前端 JS 时必须报错退出而不是"0 个读取点全部存在"——那是假通过。
_CANDIDATES = [os.path.join(STATIC, "app.js"),
               os.path.join(STATIC, "index.html")]
FRONTEND_JS = next((p for p in _CANDIDATES if os.path.exists(p)), None)
INDEX_HTML = FRONTEND_JS       # 报告里沿用旧名，值随载体变化


def load_app():
    """导入 FastAPI 应用，兼容 R178b 前后两种布局。

    R178b 后：web 是包，`from web.app import app`（若只暴露工厂则调 create_app）。
    R178b 前：web/app.py 是顶层脚本，`from app import app`。
    """
    try:
        mod = __import__("web.app", fromlist=["app", "create_app"])
    except ImportError:
        sys.path.insert(0, os.path.join(ROOT, "web"))
        mod = __import__("app", fromlist=["app", "create_app"])
    if hasattr(mod, "app"):
        return mod.app
    if hasattr(mod, "create_app"):
        return mod.create_app()
    raise RuntimeError("web.app 既无 app 也无 create_app")

# ---------------------------------------------------------------------------
# fixtures：端点 -> 一次能产出"非空列表"的固定请求（可命令复验）
# ---------------------------------------------------------------------------
FIXTURES: dict[str, dict] = {
    "/api/daily":             {"method": "GET"},
    "/api/external/fortune":  {"method": "GET", "network": True},
    "/api/external/news":     {"method": "GET", "params": {"refresh": 1},
                               "network": True},
    "/api/search":            {"method": "GET", "params": {"q": "潛龍勿用"}},
    "/api/research":          {"method": "GET", "params": {"q": "無爲",
                                                           "max_addresses": 2}},
    "/api/addr":              {"method": "GET", "params": {"scheme": "zhouyi",
                                                           "gua": 1}},
    "/api/compare":           {"method": "GET", "params": {"gua": 28,
                                                           "yao": "九二"}},
    "/api/works":             {"method": "GET"},
    "/api/user/prefs":        {"method": "GET"},
    "/api/huangli":           {"method": "GET", "params": {"year": 2026,
                                                           "month": 8, "day": 19}},
    # R229z：节日/农历日期解析兜底端点（前端 _hlDayOffset 解不动时调用）。
    "/api/huangli/resolve_date": {"method": "GET",
                                  "params": {"q": "中秋节搬家"}},
    # R231a：备份导出端点——空库也返回 version/exported_at/records 三键，
    # 读点可判定（前端只读 j.exported_at / j.records）。
    "/api/paipan/history/export_json": {"method": "GET"},
    # R2353（R110-P1-1）：触屏/微信下 CSV 走 fetch→text() 展示式
    # 导出——响应是 text/csv 不是 JSON，probe 只验「端点活着+非空」，
    # 不钉字段（前端用 r.text() 不读 JSON 键）。
    "/api/paipan/history/export": {"method": "GET", "text": True},
    # R231a：导入回灌——fixture 发空 records 数组（0 写入、无副作用），
    # 只为让 j.imported 读点可判定；真实写入路径由 import_rows 收敛逻辑
    # 与 ui_smoke 纪律约束（探针不造有副作用的写）。
    "POST /api/paipan/history/import": {"method": "POST",
                                        "json": {"records": []}},
    # R2349l（R73-P1-7/P1-12）：星座速配 + 塔罗图鉴收集端点。
    "/api/xzmatch":          {"method": "GET",
                              "params": {"a": "白羊", "b": "射手"}},
    "/api/paipan/tarot_collection": {"method": "GET"},
    "POST /api/bazi":    {"method": "POST", "json": {
        "year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
        "calendar_type": "solar", "scope": "day", "use_llm": False}},
    "POST /api/liuyao":    {"method": "POST", "json": {
        "method": "time", "seed": 42, "year": 1990, "month": 5, "day": 15,
        "hour": 10}},
    "POST /api/qiming":    {"method": "POST", "json": {
        "surname": "李", "year": 1990, "month": 5, "day": 15, "hour": 12,
        "gender": "男"}},
    # R228o：生辰换成实测能算出 dayun_hits 的（原 1990-5-15 男 hits 为空，
    # d.index/pillar/year_start 读点全是 skip-empty 假通过）。
    "POST /api/taohua":    {"method": "POST", "json": {
        "year": 1995, "month": 8, "day": 8, "hour": 10, "gender": "男"}},
    "POST /api/hehun":    {"method": "POST", "json": {
        "a_year": 1990, "a_month": 5, "a_day": 15, "a_hour": 10,
        "a_gender": "男", "b_year": 1992, "b_month": 7, "b_day": 20,
        "b_hour": 14, "b_gender": "女"}},
    "POST /api/tarot/draw":    {"method": "POST", "json": {"seed": 42, "n": 1}},
    "/api/xingzuo":           {"method": "GET", "params": {"date": "2026-08-20"}},
    # 前端只发 {topic}（实测 422）。契约 probe 用**合法请求体**取真实成功响应，
    # 前端请求体本身的不匹配由 probe_ui_smoke.py 点击后现形，两者分工不重叠。
    # R228s续6：带真实证据（引文须是 KR1a0001 folded_notes 体的子序列，
    # 否则 verify() 永久报 stale 污染后续闸门）+ topic——R228s 起
    # thread_id 缺席时后端真开 thread 行，PATH resolver 回读此响应的
    # thread_id 作路径参数，claims.evidence.* 读点从此可判定（原 SKIP=5）。
    "POST /api/threads":    {"method": "POST", "json": {
        "kind": "refusal", "claim": "probe_contract 契约探针占位",
        "method": "probe_contract", "topic": "probe_contract 契约线程",
        "evidence": [{"work_id": "KR1a0001",
                      "file": "KR1a0001_001.txt",
                      "quote": "潛龍勿用",
                      "scheme": "zhouyi", "addr1": 1,
                      "addr2": "初九", "role": "supports"}]},
        "cleanup": "derived"},
    # R228o：同 URL 按方法分键——postJSON() 绑定的变量归 "POST /api/x"，
    # api() 绑定的归 "/api/x"。/api/threads 两侧都被前端读（POST 创建回包 +
    # GET 列表项），此前列表读点全被拿到 POST 响应上判成假 HARD。
    "/api/threads":           {"method": "GET"},

    # ── R120a 补齐（R178b 新增/前端新接线的端点）──────────────
    # 上一轮这 8 个端点无 fixture → 报 SKIP。SKIP 让 probe 返回退出码 2
    # （不假装通过），但覆盖是残缺的：前端在这些 handler 里读的字段没被验证。
    "/api/concept":           {"method": "GET", "params": {"q": "無爲"}},
    # R228o：原组合 KR5c0057×KR5c0126+無爲 的 shared_addresses 实测为空，
    # 前端 s.addr/s.works 读点只能 SKIP=假通过。换成实测有命中的组合。
    "/api/compare_works":     {"method": "GET", "params": {
        "work_a": "KR1a0001", "work_b": "KR1a0006", "q": "乾"}},
    "/api/bookstudy/structure": {"method": "GET", "params": {
        "work_id": "KR1a0001"}},
    "/api/bookstudy/chapter": {"method": "GET", "params": {
        "work_id": "KR1a0001", "scheme": "zhouyi", "addr1": 1}},
    "/api/bookstudy/summary": {"method": "GET", "params": {
        "work_id": "KR1a0001"}},
    "POST /api/tarot":    {"method": "POST", "json": {"seed": 42, "n": 3}},
    # R228a：排盘历史台账端点（phFetch 包装器原来不在抽取正则会漏判，
    # j.items 被误记到 /api/bazi 头上报假 HARD——先把端点接进来）
    "/api/paipan/history":    {"method": "GET", "params": {"limit": 50}},
    # R228g：`.then(function (v)` 回调变量的归属端点。LLM 关闭时这两个
    # 端点都回 {}（实测），读到的字段全部按 CONDITIONAL_FIELDS 判级——
    # 这正好把「降级时响应必须为空对象」变成了契约钉扎。
    "POST /api/chat":    {"method": "POST", "json": {
        "session_id": "probe_contract", "message": "今天适合出行吗",
        "facts": []}},
    "POST /api/qiming/review":    {"method": "POST", "json": {
        "names": ["李沐阳", "李芷若"], "facts": ["五行缺木"]}},
    # R228g：/api/user/prefs POST、/api/favorites POST/DELETE 是「有意保留的
    # 死写端点」——app.js:4233 注明 R219b 撤了 UI 接线但路由零删除，将来
    # 按需恢复。前端无调用 → 无读点可判定，不造 fixture 假装覆盖。

    # 路径参数端点：URL 由 probe 侧动态解析（见 PATH_FIXTURES）
    "/api/threads/":          {"method": "PATH", "resolve": "thread_id"},
    "/api/paipan/history/":   {"method": "PATH", "resolve": "paipan_id"},
    # R228o：/api/ai/{tid} 轮询——LLM 关闭时永远没有真实任务（旧探针读点
    # 不可见，现在 nofix/SKIP 会把缺 fixture 如实透出）。直接往端点读的同
    # 一份内存 store 里放一条 done 任务，拿真实 200 响应。
    "/api/ai/":               {"method": "AI_TASK"},
    # R228o 收尾：纯 GET 公开端点补齐——键即 url（前端 app.js 读点全在这
    # 几张响应上；补上让「路由↔钉扎」覆盖表全绿）。
    "/api/health":            {"method": "GET"},
    "/api/stats":             {"method": "GET"},
    "/api/widget":            {"method": "GET"},
    # /api/share/{type}/{id}：无列表端点可解 id——spec.url 显式钉一个
    # selftest 同款真实请求（bazi/1）。
    "/api/share/":            {"method": "GET", "url": "/api/share/bazi/1"},
}

# 只在 `if (!resp.ok)` 错误分支读取的字段（FastAPI 错误体固定为 detail）
ERROR_BRANCH_FIELDS = {"detail"}

# 「条件存在」字段：只在错误/降级分支出现，成功响应里本就没有，前端用三元或
# if 做存在性探测。这类读取**不是**契约漂移——判据是它出现在条件判断里而不是
# 被当数据渲染。实测来源：`/api/external/news` 的 `error` 键只在整通道异常时
# 才返回（见 services 的 except 分支），成功时缺席是正确设计。
# 实测确认（`<py> -c` 打真实请求，见 D-137a）：`error` 是**带内拒绝键**——
# 这些端点在拒绝/未命中时返回 HTTP **200** + `{"error": "..."}`，而不是 4xx。
# 来源：`src/guji/bookstudy.py:43/49/119/127/143/167/172`、
# `src/guji/research.py:275/299/301`、`web/services.py:858`。
# 实测：compare_works 无命中词 → 200 keys=['error']；bookstudy NULL-scheme →
# 200 keys=['error']。前端 `if (j.error)` 正是**正确**的处理方式，判 HARD 是误报。
CONDITIONAL_FIELDS = {
    "/api/external/news": {"error"},
    "/api/external/fortune": {"error"},
    "/api/compare_works": {"error"},
    "/api/concept": {"error"},
    "/api/bookstudy/structure": {"error"},
    "/api/bookstudy/chapter": {"error"},
    "/api/bookstudy/summary": {"error"},
    # R191b 补记（B-014 异步化，D-251b；审查轨领土，按 D-250b 先例显式标注）：
    # `ai_task_id` 只在 LLM 功能开启（web/llm_config.json enabled 且未设
    # BOOKS_LLM_DISABLE）时返回；关闭时键缺席是**判据 11 的要求**（响应与
    # 「LLM 从未存在」逐字节一致）。前端 pollAiPolish 首行 `if (!taskId) return`
    # 对缺席做了显式保护——缺席即「无 AI 段落」，不是漂移。
    # 实测：DISABLE=1 下四端点 keys 无 ai_task_id（web/check_async_ai.py 判据 11）；
    # 开启时键在且 /api/ai/{id} 可轮询（判据 9/10）。
    "/api/bazi": {"ai_task_id",
                  # R233c（A9）：hour_known 只在 hour_known===False 时才回
                  # （时辰留空的盘）；前端 `=== false` 正是对缺席的探测。
                  "hour_known"},
    "/api/taohua": {"ai_task_id"},
    "/api/hehun": {"ai_task_id"},
    "/api/qiming": {"ai_task_id",
                    # R233j（R46-P1）：one_liner 只在 copy_bank 池非空时回；
                    # 前端 `if (j.one_liner)` 是对缺席的探测。
                    "one_liner"},
    # R228g：chat/qiming.review 的 *_task_id 只在 LLM 开启时返回（DISABLE 下
    # 响应实测为 {}，见 fixtures 注释）；前端 `if (!j.chat_task_id)` 正是对
    # 缺席的正确探测。
    "/api/chat": {"chat_task_id",
                  # R2355（R111-P2-6）：rate_limited 只在每 sid 每分钟
                  # 超限那次返回——前端 `if (j.rate_limited)` 是对缺席
                  # 的探测（限流≠关停分流用）。
                  "rate_limited"},
    "/api/qiming/review": {"review_task_id"},
    # R228x：/api/huangli 双形态——单日返回 yi/ji/…，带 affair+days 返回
    # good_days 列表。同 URL 同方法两种响应形状，fixture 只能钉单日形态；
    # 前端对 good_days 有 Array.isArray 守卫 → 条件存在字段，不算漂移。
    "/api/huangli": {"good_days", "good_days.date", "good_days.yi",
                     "good_days.ji", "count", "terms", "affair", "start",
                     "days",
                     # R229z续21（R9 审计修复）：conflict（宜忌相冲词）只在
                     # 非空时返回；year_note 只在干支年双口径错位日返回——
                     # 前端 Array.isArray/if 守卫即正确探测。
                     "conflict", "year_note",
                     # R2349n（R77）：conflict_family（同义族对冲）同 conflict
                     # 口径——只在非空时返回。
                     "conflict_family",
                     # R233w：term_today 只在交节日返回（day_flags 同理，
                     # 空时不回）；shensha.linri 恒在（dict 子键，守卫读法）。
                     "day_flags", "term_today", "term_today.name",
                     "term_today.time"},
    # R2349t（R87-P2-1）：disabled 只在 BOOKS_PAIPAN_HISTORY_DISABLE
    # 开启时返回——探针跑非禁用态所以响应里本就没有；前端
    # `if (j.disabled)` 正是对缺席的探测。
    "/api/paipan/history": {"disabled"},
}

# 出处字段：缺失时**即使有 `||''` 兜底也判 HARD**。
# 依据宪法第三条「引用与生成分离」——`||''` 让页面不报错，但把出处静默渲染成
# 空串，等于展示无出处的古籍原文，这正是本项目最不能出的错。
PROVENANCE_FIELDS = {"citation", "disclosure"}


# ---------------------------------------------------------------------------
# 1. 静态提取：handler 块 -> 变量绑定 -> 字段读取点
# ---------------------------------------------------------------------------
def script_region(text: str, path: str) -> tuple[list[str], int]:
    """取出前端 JS 正文与其 1-based 行号基准。

    R178b 之前 JS 内联在 index.html 的 <script> 区；之后整体搬到 app.js，
    此时整个文件就是 JS，无需切分。两种布局都要支持，否则 probe 会在重构后
    因为找不到 <script> 而崩掉（或更糟：静默扫到 0 个读取点报"全部通过"）。
    """
    lines = text.splitlines()
    if path.endswith(".js"):
        return lines, 1
    start = next(i for i, l in enumerate(lines) if l.strip() == "<script>")
    end = next(i for i, l in enumerate(lines) if l.strip() == "</script>")
    return lines[start + 1:end], start + 2   # 返回 1-based 行号基准


def split_blocks(lines: list[str], base: int) -> list[dict]:
    """按顶格（col 0）起始 / 顶格 `}`|`});` 结束切分 handler 块。

    R178b 后 app.js 的形态是一批顶格 `async function doX() {`，块内调用共享的
    `api()` / `postJSON()` 包装器；重构前是 `$('#id').addEventListener(...)`
    内联 `fetch()`。两种都要能切出来——只认 `fetch(` 会在重构后抽到 1 个块、
    0 个读取点，然后报"全部通过"，那是假通过（实测踩过，见 D-136a）。
    """
    blocks, i, n = [], 0, len(lines)
    while i < n:
        l = lines[i]
        if l and not l[0].isspace() and not l.lstrip().startswith("//") \
                and not l.lstrip().startswith("*") \
                and l.rstrip().endswith("{"):
            j = i + 1
            while j < n and not re.match(r"^\}\)?;?\s*$", lines[j]):
                j += 1
            blocks.append({"start": base + i, "lines": lines[i:j + 1]})
            i = j + 1
        else:
            i += 1
    def has_call(b):
        body = "\n".join(b["lines"])
        return ("fetch(" in body or API_CALL_RE.search(body)
                or API_PREFIX_RE.search(body))
    for b in blocks:
        b["has_call"] = has_call(b)
    return blocks        # R228g：不再过滤——render 层 callee 也需要本体


FETCH_RE = re.compile(r"fetch\(\s*['\"`](/api/[A-Za-z0-9_/]*)")
# R178b 起前端统一走 `api(path)` / `postJSON(path, payload)` 包装器，
# 不再逐处裸调 fetch。两种写法都要认，否则 probe 抽不到任何 URL。
API_CALL_RE = re.compile(
    r"(?:api|postJSON|phFetch)\(\s*['\"`](/api/[A-Za-z0-9_/{}]*)")
# 变量拼接的 URL：api('/api/history/' + encodeURIComponent(rid))
API_PREFIX_RE = re.compile(r"(?:api|postJSON|phFetch)\(\s*['\"`](/api/[A-Za-z0-9_/]*?)/?['\"`]\s*\+")
# R178b 前：const j = await resp.json()
# R178b 后：const j = await api('/api/x')  /  const j = await postJSON(...)
# R228a：phFetch（排盘历史台账包装器）同样产生 JSON 变量绑定
# R228g：var|let 声明同样绑定（doXingzuo 用 `var j = await api(...)`，
# 旧正则只认 const——星座 handler 的 j.* 读取原来整段裸奔）
JSON_VAR_RE = re.compile(
    r"(?:const|let|var)\s+(\w+)\s*=\s*await\s+(?:(\w+)\.json\(\)|api\(|postJSON\(|phFetch\()")
# R228g：`r = await fetch(...)` 的 Response 变量也记 URL——后面的
# `j = await r.json()` 才能把 JSON 读点归到真实端点而不是块内首个 URL
RESP_VAR_RE = re.compile(
    r'(?:const|let|var)\s+(\w+)\s*=\s*await\s+fetch\(\s*[\'"`]([^\'"`]+)')
# R228g：`.then(function (v) {` 链式回调参数也绑定为响应根；归属 URL 向前
# 扫同一链式调用上最近的 api()/postJSON()/fetch(（写死的归因规则：没有
# fixture 的端点不绑——绑了只会造 SKIP，读点维持不可见与旧版同）
THEN_JSON_RE = re.compile(r"\.then\(\s*function\s*\((\w+)\)\s*\{")
# R228g：render 层参数传递——`buildX(j)` 把已绑定的响应变量传给
# `function buildX(p)`，callee 体内 `p.field` 及派生变量读取按 caller 的
# URL/路径记账。只匹配单参简单调用（保守，不猜实参表达式）。
# R233a（R40-B3）：此前只有「标识符单实参」调用被解析——
# `renderCiteTree(j.citations)`（成员表达式实参）与
# `renderWarm(j.warm, j.interpretation, ev)`（多实参）整块落在盲区，
# helper 体内字段读点零钉扎。扩成：形参表全捕获 + 实参逐个
# （标识符或根标识符+成员链，如 j.citations）按位置注入种子。
FN_DEF_RE = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(\s*([^)]*)")
CALLSITE_RE = re.compile(
    r"(?<![\w.])\b(\w+)\s*\(\s*"
    r"((?:\w+(?:\.\w+)*\s*,\s*)*\w+(?:\.\w+)*)\s*\)")
ARG_RE = re.compile(r"^(\w+)((?:\.\w+)*)$")
# const ben = j.ben || {}   /   const a = j.a_bazi, b = j.b_bazi;
OBJ_BIND_RE = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(\w+)\.(\w+)"
                         r"(?:\s*\|\|\s*\{\})?")
# j.hits.forEach((h, i) => / (j.items||[]).forEach(it => / j.items.slice(0,5).forEach(item =>
# R228o：不只 forEach——map/filter/find 回调同样是元素读点（tarot
# draws / xingzuo signs / paipan items 的字段访问此前全盲区）。
ELEM_RE = re.compile(r"\(?\s*(\w+)\.(\w+)\s*(?:\|\|\s*\[\]\s*)?\)?"
                     r"(?:\.\w+\([^)]*\))*\.(?:forEach|map|filter|find)"
                     r"\(\s*(?:function\s*)?\(?\s*(\w+)")
# R228o：单级数组变量迭代（var arr = j.items.slice()…; arr.forEach(x=>)）。
# 元素路径 = 父变量自己的数组路径，不再追加字段。
ELEM_SOLO_RE = re.compile(
    r"(?<![\w.])(\w+)\s*\.(?:forEach|map|filter|find)"
    r"\(\s*(?:function\s*)?\(?\s*(\w+)")


def field_reads(block: dict,
                seeds: dict | None = None,
                seed_urls: dict | None = None
                ) -> tuple[dict, list[dict], list[str], dict, list[str]]:
    """返回 (绑定表, 读取点, fetch URL 表, 变量→url 表, 无fixture的URL表)。
    绑定表值为 ('root'|'obj'|'elem', path)。

    seeds/seed_urls（R228g render 层）：调用方把实参绑定注入 callee 形参，
    callee 块没有自己的 api() 调用（urls 为空）也照常扫描。"""
    # R228o 续：同名变量可多次绑定（j 先 phFetch('/api/x') 后
    # postJSON('/api/y')；ln 先后迭代两个数组）。绑定表保留行序历史
    # [(off, kind, path, url)]，读点取「绑定行 ≤ 读点行」的最后一条——
    # 这才是 JS 真实的影子语义（旧实现存终值，elem 派生被后绑定污染）。
    binds: dict[str, list] = {k: [(-1, v[0], v[1],
                                  (seed_urls or {}).get(k, ""))]
                              for k, v in (seeds or {}).items()}
    var_urls: dict[str, str] = {}
    reads: list[dict] = []
    urls: list[str] = []
    nofix: list[str] = []
    resp_urls: dict[str, str] = {}
    for off, line in enumerate(block["lines"]):
        for rx in (FETCH_RE, API_CALL_RE, API_PREFIX_RE):
            m = rx.search(line)
            if m:
                urls.append(m.group(1))
                break
        m = JSON_VAR_RE.search(line)
        if m:
            # 变量 → 它自己那次 api() 调用的 URL（多 URL 块里各读点归各自端点，
            # R188b：loadDaily 同块调 /api/daily 与 /api/xingzuo，旧逻辑把
            # 两个变量的读取全算到 urls[0] 头上，造成假 HARD）。
            # R228o：url 直接钉在绑定元组第 4 位——变量若在后面再被绑定成
            # 另一端点（同块 j 先 phFetch 后 postJSON），前面派生出的 it/elem
            # 变量拿到的仍是绑定时刻的归属，不会被后绑定污染。
            mu = API_CALL_RE.search(line) or API_PREFIX_RE.search(line)
            _u = ""
            if mu:
                # postJSON/fetch POST 归 "POST <url>" 键——同 URL
                # 的 GET/POST 响应契约分离判定（/api/threads 实证）。
                _u = mu.group(1)
                if "postJSON" in line or re.search(
                        r"""method\s*[:=]\s*['"]POST""", line):
                    _u = "POST " + _u
            elif m.group(2):
                # `j = await r.json()`：归属 = r 那次 fetch 的 URL
                _u = resp_urls.get(m.group(2), "")
            binds.setdefault(m.group(1), []).append((off, "root", [], _u))
            if _u:
                var_urls[m.group(1)] = _u
        mr = RESP_VAR_RE.search(line)
        if mr:
            _ru = mr.group(2)
            if re.search(r"""method\s*[:=]\s*['"]POST""", line):
                _ru = "POST " + _ru
            resp_urls[mr.group(1)] = _ru
        # R228g：`.then(function (v) {` 回调参数 → 响应根
        for mt in THEN_JSON_RE.finditer(line):
            v = mt.group(1)
            if v in binds:
                continue
            u = None
            for k in range(off, -1, -1):
                _ln = block["lines"][k]
                mu = (API_CALL_RE.search(_ln)
                      or API_PREFIX_RE.search(_ln)
                      or FETCH_RE.search(_ln))
                if mu:
                    u = mu.group(1)
                    if "postJSON" in _ln or re.search(
                            r"""method\s*[:=]\s*['"]POST""", _ln):
                        u = "POST " + u
                    break
            if u is not None and u not in FIXTURES and u not in nofix:
                # R228o：URL 拿到但无 fixture——透出给调用方记 SKIP，
                # 新端点缺 fixture 不再静默通过（exit 2 如实不确定）。
                nofix.append(u)
            if u is None or u not in FIXTURES:
                continue        # 归属不明的端点不绑
            binds.setdefault(v, []).append((off, "root", [], u))
            var_urls[v] = u
    if not urls and not seeds:
        return binds, reads, urls, var_urls, nofix
    # callee 块没有自己的 api() 调用——读点 URL 回落到种子实参的归属
    fallback_url = urls[0] if urls else next(iter(var_urls.values()), "")
    # 迭代 / 派生变量绑定（多趟：派生变量可再派生）
    for _ in range(3):
        for _ei, line in enumerate(block["lines"]):
            for m in ELEM_RE.finditer(line):
                parent, field, var = m.groups()
                # 同名回调变量可复用（ln 先 forEach reply 后 forEach
                # lines）——历史列表按行序追加，读点归属按行序正确切分。
                ph = [b for b in (binds.get(parent) or []) if b[0] <= _ei]
                if ph:
                    pb = ph[-1]
                    nv = (_ei, "elem", pb[2] + [field], pb[3])
                    if nv not in binds.setdefault(var, []):
                        binds[var].append(nv)
            for m in ELEM_SOLO_RE.finditer(line):
                parent, var = m.groups()
                ph = [b for b in (binds.get(parent) or []) if b[0] <= _ei]
                if ph:
                    pb = ph[-1]
                    nv = (_ei, "elem", pb[2], pb[3])
                    if nv not in binds.setdefault(var, []):
                        binds[var].append(nv)
            for m in OBJ_BIND_RE.finditer(line):
                var, parent, field = m.groups()
                ph = [b for b in (binds.get(parent) or []) if b[0] <= _ei]
                if ph and var != parent:
                    pb = ph[-1]
                    nv = (_ei, "obj", pb[2] + [field], pb[3])
                    if nv not in binds.setdefault(var, []):
                        binds[var].append(nv)
    # 字段读取点
    for off, line in enumerate(block["lines"]):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for var, hist in binds.items():
            # R228g：读点先于绑定行 = 同名影子变量（catch (e) 里的 e.message
            # 撞上后面的 var e = await r.json()）——不计数，防假 HARD。
            live = [b for b in hist if b[0] <= off]
            if not live:
                continue
            bind_off, kind, path, bind_url = live[-1]
            for m in re.finditer(r"(?<![\w.])" + re.escape(var) + r"\.(\w+)", line):
                field = m.group(1)
                if field in ("forEach", "length", "slice", "map", "join",
                             "filter", "push"):
                    continue
                if field in binds:            # 派生变量自己的名字，跳过
                    pass
                tail = line[m.end():]
                soft = "||" in tail
                esc_whole = bool(re.search(
                    r"esc\(\s*" + re.escape(var) + r"\." + field
                    + r"\s*(?:\|\|[^)]*)?\)", line))
                reads.append({
                    "var": var, "kind": kind, "path": path + [field],
                    "field": field, "line_no": block["start"] + off,
                    "src": stripped[:110], "soft": soft, "esc_whole": esc_whole,
                    # 读点归属：优先变量绑定时刻的 URL，回落块内首个 URL
                    #（R188b），callee 块再落到种子实参的归属（R228g）
                    "url": bind_url or var_urls.get(var) or fallback_url,
                })
    kept = [r for r in reads if r["field"] not in ERROR_BRANCH_FIELDS]
    return binds, kept, urls, var_urls, nofix


# ── 有意不钉扎的路由登记表（R228o route↔fixture 覆盖闸）─────────────
# 新端点要么进 FIXTURES 要么进这里并写明理由——不入表 = probe FAIL。
UNPINNED_ROUTES = {
    ("POST", "/api/ask"):        "R228l 裁决为有意保留僵尸端点（UI 接线已撤，"
                                 "删除待用户）——不造 fixture 假装覆盖",
    ("POST", "/api/user/prefs"): "同上：死写端点（R228l 台账）",
    ("POST", "/api/favorites"):  "写端点——R230z 起由起名♡/合婚存这对接线，"
                                 "探针只读纪律不造写请求（ui_smoke "
                                 "btn:hehun.savepair 已真点验证）",
    ("DELETE", "/api/favorites/{fid}"): "同上——写端点；R230z 起由心水名单"
                                 " × 摘除接线（真机路径同 ui_smoke savepair）",
    ("DELETE", "/api/favorites"): "R2349（R65-P1-2）：「忘掉我的数据」全清"
                                 "端点——真机路径由 wipe 钮两段式覆盖",
    ("DELETE", "/api/paipan/history"): "同上——「忘掉我的数据」整表清",

    ("DELETE", "/api/paipan/history/{rid}"): "删除写端点——探针只读纪律"
                                 "（R230k 起写路径由 ui_smoke btn:history.delete"
                                 " 两段式真删覆盖；此前注释误称已由建删回环"
                                 " 覆盖——selftest 在 DISABLE 态跑根本测不到）",
}


# ---------------------------------------------------------------------------
# 2. 真实响应 + 路径判定
# ---------------------------------------------------------------------------
def resolve(body, kind: str, path: list[str]):
    """沿 path 走真实响应。返回 (status, value)。
    status: 'ok' | 'missing' | 'skip-empty'"""
    cur = body
    for i, seg in enumerate(path):
        if isinstance(cur, list):
            if not cur:
                return "skip-empty", None
            # R233b（R40-B3 连带）：列表段不再只按 [0] 判——首个剩余路径
            # 可判定的元素为准。例：warm.details[0].basis=[] 而
            # details[2].basis 有 7 条，旧实现把全部 d.basis 读点记
            # skip-empty → SKIP；真稀疏（全元素都缺）仍如实 SKIP。
            for el in cur[:16]:
                st, val = resolve(el, kind, path[i:])
                if st == "ok":
                    return st, val
            cur = cur[0]
        if not isinstance(cur, dict):
            return "missing", None
        if seg not in cur:
            return "missing", None
        cur = cur[seg]
    if kind == "elem" and isinstance(cur, list):
        return ("skip-empty", None) if not cur else ("ok", cur[0])
    return "ok", cur


def main() -> int:
    from fastapi.testclient import TestClient
    from guji import history as history_db
    from guji import knowledge as kb_mod

    if FRONTEND_JS is None:
        print(f"probe_contract FAIL-ENV: 在 {STATIC} 找不到 app.js 或 index.html"
              f"——前端载体改名了？probe 必须先能找到代码才能判定"
              f"（0 个读取点 ≠ 通过）")
        return 2

    _app = load_app()
    client = TestClient(_app)
    # R228a：排盘历史台账也受写端点污染纪律约束——seed 的 POST /api/bazi
    # 会 save_async 落一行，退出前必须把增量行删掉，基线在这里先记。
    from guji import paipan_history as _ph_db
    _ph_baseline = (0 if _ph_db.disabled()
                    else _ph_db.list_records(limit=200)["total"])
    text = open(FRONTEND_JS, encoding="utf-8").read()
    lines, base = script_region(text, FRONTEND_JS)
    all_blocks = split_blocks(lines, base)
    blocks = [b for b in all_blocks if b["has_call"]]
    src_name = os.path.basename(FRONTEND_JS)
    print(f"前端载体：{src_name}（{os.path.getsize(FRONTEND_JS)}B）")
    if not blocks:
        print(f"probe_contract FAIL-ENV: 在 {src_name} 里切不出任何含 fetch 的 "
              f"handler 块。可能是代码风格变了（如改用箭头函数顶层缩进），"
              f"probe 的块切分需同步更新——静默报 0 是假通过。")
        return 2

    # ── R228o：路由↔fixture 覆盖闸——新端点不被钉扎时 fail-loud ──
    _route_tbl = []
    for _r in _app.routes:
        _inner = getattr(_r, "original_router", None)
        _route_tbl += list(_inner.routes if _inner is not None else [_r])
    _uncov = []
    _path_keys = [k for k in FIXTURES if k.endswith("/")]
    for _r in _route_tbl:
        _p = getattr(_r, "path", "")
        if not _p.startswith("/api"):
            continue
        _ms = sorted((getattr(_r, "methods", None) or set())
                     - {"HEAD", "OPTIONS"})
        for _m in _ms:
            if (_m, _p) in UNPINNED_ROUTES:
                continue
            _key = f"{_m} {_p}" if _m in ("POST", "PUT", "DELETE") else _p
            if _key in FIXTURES or _p in FIXTURES:
                continue
            # 路径参数端点：存在以「<前缀>/」为键的 fixture（PATH/AI_TASK）
            if any(_p.startswith(k) for k in _path_keys):
                continue
            _uncov.append(f"{_m} {_p}")
    if _uncov:
        print("probe_contract FAIL: 以下路由未钉扎（进 FIXTURES 或 "
              "UNPINNED_ROUTES 写明理由）：")
        for _u in sorted(_uncov):
            print("  -", _u)
        return 1

    # ── 写端点污染基线（L-22）──────────────────────────────
    # ⚠ 从这里开始到 finally 之间的一切都必须在 try 内：本 probe 开发期实测
    # 踩过——中途异常退出（contentless fts5 的 DELETE 报错）让 4 条占位行留在
    # 了 knowledge.db 里。清理只写在成功路径上，等于没有清理。
    hist_baseline = history_db.count()
    kb_path = os.path.join(ROOT, "data", "index", "knowledge.db")
    created_derived: list[int] = []
    created_threads: list[int] = []   # R228s续6：fixture 自动开的线程也要回收
    fav_id = None
    seed_bazi = client.post("/api/bazi", json=FIXTURES["POST /api/bazi"]["json"])
    assert seed_bazi.status_code == 200, seed_bazi.text[:200]
    # R228o：台账落盘是 save_async——探针不等它 flush 就去 GET
    # /api/paipan/history 会拿到空列表（读点全 skip-empty = 假通过）。
    # 轮询到种子行可见为止，最多 3s。
    for _ in range(30):
        if _ph_db.disabled() or \
                _ph_db.list_records(limit=200)["total"] > _ph_baseline:
            break
        time.sleep(0.1)
    # R228l：/api/history 端点已删（R219b）——记账升级为行为断言：
    # POST /api/bazi 不得向 history.db 落行， pinning 删除语义不复活。
    assert history_db.count() == hist_baseline, (
        "POST /api/bazi 写入了 history.db——R219b 的删除语义被破坏")
    # save_async 是守护线程：GET /api/paipan/history 要等它落库才有 items，
    # 短轮询最多 ~3s；等不到就由 resolve 如实报 skip-empty（不假装通过）。
    for _w in range(30):
        if client.get("/api/paipan/history", params={"limit": 5}
                      ).json().get("items"):
            break
        time.sleep(0.1)
    fav = client.post("/api/favorites", json={"type": "bazi",
                                              "ref_id": "probe_contract",
                                              "title": "probe_contract 占位收藏"})
    if fav.status_code == 200:
        fav_id = fav.json().get("id")

    cache: dict[str, object] = {}

    def fetch(url: str):
        if url in cache:
            return cache[url]
        fx = FIXTURES.get(url)
        url_real = (fx.get("url") if isinstance(fx, dict) and fx.get("url")
                    else (url[5:] if url.startswith("POST ") else url))
        if fx is None:
            cache[url] = ("nofixture", None)
            return cache[url]
        if fx["method"] == "AI_TASK":
            from guji import llm_polish as _lp
            tid = "probe_contract_task"
            with _lp._tasks_lock:
                _lp._tasks[tid] = {"status": "done",
                                   "text": "probe 契约桩任务",
                                   "created": time.monotonic()}
            r = client.get(f"{url_real}{tid}")
            cache[url] = (("ok", r.json()) if r.status_code == 200
                          else ("http", (r.status_code, r.text[:160])))
            return cache[url]
        if fx["method"] == "PATH":
            # 路径参数端点：先取一个真实存在的 id，再打具体 URL。
            # 取不到 id 就诚实报 SKIP，不编一个假 id 去打 404（那会把
            # "端点契约"测成"404 错误体契约"，是另一回事）。
            if fx["resolve"] == "thread_id":
                # R228s续6：先确保契约线程 fixture 已执行，直接用回包
                # thread_id——列表排序（updated_at）不保证新建线程在首位。
                fetch("POST /api/threads")
                st, body = cache.get("POST /api/threads", (None, None))
                if st == "ok" and isinstance(body, dict)                         and body.get("thread_id"):
                    rid = body["thread_id"]
                else:
                    lst = client.get("/api/threads").json().get("threads") or []
                    rid = (lst[0].get("id") if lst else None)
            elif fx["resolve"] == "paipan_id":
                # save_async 守护线程落行有毫秒级延迟——短轮询等它落库，
                # 等不到就诚实报「无可用 id」而不是编假 id 打 404
                lst = []
                for _w in range(30):
                    lst = client.get("/api/paipan/history",
                                     params={"limit": 5}).json().get("items") or []
                    if lst:
                        break
                    time.sleep(0.1)
                rid = (lst[0].get("id") if lst else None)
            else:
                rid = None   # 未登记的 resolver：诚实报 SKIP
            if rid is None:
                cache[url] = ("http", (0, f"{url} 无可用 id（列表为空），"
                                          f"无法构造路径参数请求"))
                return cache[url]
            r = client.get(f"{url.rstrip('/')}/{rid}")
            cache[url] = (("ok", r.json()) if r.status_code == 200
                          else ("http", (r.status_code, r.text[:160])))
            return cache[url]
        if fx["method"] == "GET":
            r = client.get(url_real, params=fx.get("params"))
        else:
            r = client.post(url_real, json=fx.get("json"))
        if r.status_code != 200:
            cache[url] = ("http", (r.status_code, r.text[:160]))
            return cache[url]
        # R2353：text/csv 等非 JSON 端点（展示式导出）——声明 text:True
        # 的 fixture 只验「200+非空文本」，前端走 r.text() 本无字段
        # 读点可钉。
        if fx.get("text"):
            cache[url] = ("ok", {"__text__": r.text})
            return cache[url]
        body = r.json()
        if fx.get("cleanup") == "derived" and isinstance(body, dict):
            did = body.get("derived_id")
            if did:
                created_derived.append(int(did))
            _tid = body.get("thread_id")
            if _tid:
                created_threads.append(int(_tid))
        cache[url] = ("ok", body)
        return cache[url]

    hard: list[dict] = []
    type_bad: list[dict] = []
    soft: list[dict] = []
    skipped: list[dict] = []
    checked = 0
    seen_reads: set[tuple] = set()

    try:
        checked = scan(blocks, fetch, hard, type_bad, soft, skipped,
                       seen_reads, all_blocks=all_blocks)
    finally:
        cleaned, hist_after = cleanup(history_db, kb_mod, kb_path,
                                     hist_baseline, created_derived, fav_id,
                                     created_threads)
        # R228a：paipan_history.db 增量清理（独立轻量库，同纪律）
        _ph_after = _ph_baseline
        try:
            if not _ph_db.disabled():
                _extra = (_ph_db.list_records(limit=200)["total"]
                          - _ph_baseline)
                if _extra > 0:
                    for _r in _ph_db.list_records(limit=200)["items"][:_extra]:
                        if _ph_db.delete_record(_r["id"]):
                            cleaned.append(f"paipan_history#{_r['id']}")
                _ph_after = _ph_db.list_records(limit=200)["total"]
        except Exception as _exc:                    # noqa: BLE001
            cleaned.append(f"⚠ paipan_history 清理未完成：{_exc}")
        print(f"清理: {', '.join(cleaned) or '无'}；"
              f"history 行数 {hist_baseline} -> {hist_after}；"
              f"paipan_history 行数 {_ph_baseline} -> {_ph_after}")

    # ── 报告 ──────────────────────────────────────────────
    def show(tag, items):
        print(f"\n{tag} ({len(items)})")
        for r in items:
            path = ".".join(["j"] + r["path"][:-1] + [r["field"]]) if r["path"] \
                else r["field"]
            extra = ""
            if "value_type" in r:
                extra = (f"  实测值类型={r['value_type']} 渲染为 "
                         f"{r['renders_as']}  {r['value_preview']}")
            if r.get("note"):
                extra += f"  ⚠ {r['note']}"
            print(f"  {src_name}:{r['line_no']}  {r.get('url', '-')}  读 {path}"
                  f"{extra}\n      源码: {r['src']}")

    print(f"probe_contract: {len(blocks)} 个含 fetch 的 handler 块，"
          f"{checked} 个字段读取点")
    if hard:
        show("HARD 字段不存在且无 || 兜底（前端拿到 undefined）", hard)
    if type_bad:
        show("TYPE 字段是 object 却整个塞进 esc() → 页面渲染 [object Object]",
             type_bad)
    if soft:
        show("SOFT 有 || 兜底 / array 被 esc() 逗号拼接（不卡闸门）", soft)
    if skipped:
        show("SKIP 无法判定（列表为空 / 无 fixture / 端点非 200）", skipped)
    assert hist_after == hist_baseline, ("history.db 未清理干净",
                                         hist_baseline, hist_after)

    if hard or type_bad:
        print(f"\nprobe_contract FAIL: HARD={len(hard)} TYPE={len(type_bad)} "
              f"SOFT={len(soft)} SKIP={len(skipped)}")
        return 1
    if skipped:
        print(f"\nprobe_contract INCONCLUSIVE: SKIP={len(skipped)}"
              f"（fixture 未能让列表非空，按宪法第一条不算通过）")
        return 2
    print(f"\nprobe_contract PASS: {checked} 个字段读取点全部在真实响应中存在"
          f"（SOFT={len(soft)}）")
    return 0


def cleanup(history_db, kb_mod, kb_path, hist_baseline, created_derived,
            fav_id, created_threads=()):
    """删除本轮写入的行并返回 (清理清单, 清理后 history 行数)。

    必须可在异常路径上调用（见 main 的 try/finally）。本身不抛异常——
    清理阶段再抛会掩盖真正的失败原因。
    """
    cleaned: list[str] = []
    try:
        n_extra = history_db.count() - hist_baseline
        if n_extra > 0:
            for r in history_db.list_records(200)[:n_extra]:
                if history_db.delete_record(r["id"]):
                    cleaned.append(f"history#{r['id']}")
        with kb_mod.KnowledgeBase(kb_path) as kb:
            for did in created_derived:
                # derived_fts 是 contentless fts5：只能用 'delete' 命令形式撤回
                # （照 web/app.py --selftest threads.post+readback+cleanup 先例）
                row = kb.db.execute("SELECT claim FROM derived WHERE id=?",
                                    (did,)).fetchone()
                if row is not None:
                    from guji.variants import fold, segment_cjk
                    kb.db.execute(
                        "INSERT INTO derived_fts(derived_fts,rowid,seg) "
                        "VALUES('delete',?,?)",
                        (did, segment_cjk(fold(row["claim"]))))
                kb.db.execute("DELETE FROM evidence WHERE derived_id=?", (did,))
                kb.db.execute("DELETE FROM derived WHERE id=?", (did,))
                cleaned.append(f"derived#{did}")
            if fav_id is not None:
                kb.remove_favorite(int(fav_id))
                cleaned.append(f"favorite#{fav_id}")
            for t in created_threads:          # R228s续6
                kb.db.execute("DELETE FROM turn WHERE thread_id=?", (t,))
                kb.db.execute("DELETE FROM thread WHERE id=?", (t,))
                cleaned.append(f"thread#{t}")
            kb.db.commit()
    except Exception as exc:                      # noqa: BLE001
        cleaned.append(f"⚠ 清理未完成：{type(exc).__name__}: {exc}")
    return cleaned, history_db.count()


def scan(blocks, fetch, hard, type_bad, soft, skipped, seen_reads,
         all_blocks=None) -> int:
    # R228g：callee 名→(块, 首形参)。render 层（build*/render* 之类）不含
    # fetch 调用，只有在 caller 把响应变量传进来时才产生可判定读点。
    fnmap = {}
    for cb in (all_blocks or []):
        fm = FN_DEF_RE.match(cb["lines"][0])
        if fm and fm.group(2) is not None:
            # R233a：形参全表（按位与实参配对）
            fnmap[fm.group(1)] = (cb, [p.strip() for p in
                                       fm.group(2).split(",") if p.strip()])

    checked = 0
    for b in blocks:
        binds, reads, urls, var_urls, nofix = field_reads(b)
        for nu in nofix:
            skipped.append({"line_no": b["start"], "src": f"no fixture for {nu}",
                            "path": [], "field": "-"})
        # R228g：render 层——caller 块里 `fn(arg)` 且 arg 已绑定 → 以 arg 的
        # (kind,path,url) 为种子在 callee 体内重跑 field_reads，callee 内
        # 派生变量（const paipan = j.paipan）随种子链一并归因。
        for off_c, line in enumerate(b["lines"]):
            for cm in CALLSITE_RE.finditer(line):
                fn = cm.group(1)
                if fn not in fnmap:
                    continue
                cal_blk, params = fnmap[fn]
                if not params:
                    continue
                seeds: dict[str, tuple] = {}
                seed_urls: dict[str, str] = {}
                for param, arg in zip(params, cm.group(2).split(",")):
                    arg = arg.strip()
                    if not param or arg == fn:
                        continue
                    am = ARG_RE.match(arg)
                    if not am:
                        continue        # 表达式实参不猜（保守照旧）
                    root, tail = am.groups()
                    if root not in binds:
                        continue        # 实参根未绑响应变量——不是本端点的数据
                    # R228o 续：种子取实参在**调用行**生效的绑定版本——
                    # 同块 j 再绑定不会污染此前 buildX(j) 的归因。
                    live = [bv for bv in binds[root] if bv[0] <= off_c]
                    if not live:
                        continue
                    _bo, _kind, _path, _burl = live[-1]
                    if tail:
                        # 成员链实参 j.citations：种子带路径下钻，
                        # callee 里 h.field 读点按 citations[0].field 判定
                        _path = _path + [s for s in tail.split(".") if s]
                        _kind = "obj" if _kind != "elem" else "elem"
                    seeds[param] = (_kind, _path)
                    seed_urls[param] = _burl or (urls[0] if urls else "")
                if not seeds:
                    continue
                _cb, creads, _cu, _cv, _cn = field_reads(
                    cal_blk, seeds=seeds, seed_urls=seed_urls)
                reads += creads
        if not reads:
            continue
        # 按读点各自的 URL 取响应（R188b：多 URL 块各归各端点）
        bodies: dict[str, tuple] = {}
        for url in {r.get("url") for r in reads} | {urls[0]}:
            state, body = fetch(url)
            if state != "ok":
                bodies[url] = (state, body)
            else:
                bodies[url] = ("ok", body)
        for rd in reads:
            url = rd.get("url") or urls[0]
            state, body = bodies.get(url, ("nofixture", None))
            if state == "nofixture":
                skipped.append({"line_no": b["start"], "src": f"no fixture for {url}",
                                "path": [], "field": "-"})
                continue
            if state == "http":
                code, snippet = body            # type: ignore[misc]
                skipped.append({"line_no": b["start"],
                                "src": f"{url} -> HTTP {code} {snippet}",
                                "path": [], "field": "-"})
                continue
            # 同一行同一字段可能被同一 handler 内多个变量别名重复命中，去重后
            # 计数才等于"真实读取点数"（数字必须可复验，宪法第一条）
            key = (rd["line_no"], tuple(rd["path"]), rd["soft"], rd["esc_whole"])
            if key in seen_reads:
                continue
            seen_reads.add(key)
            checked += 1
            # R2353：text:True fixture——响应不是 JSON（CSV 展示式导出），
            # r.ok/r.text/r.status 是 Response 成员而非 JSON 字段，读点
            # 不参与契约判定；端点活性由 fixture 的 200+非空钉过。
            if isinstance(FIXTURES.get(url), dict) and \
                    FIXTURES[url].get("text"):
                continue
            status, value = resolve(body, rd["kind"], rd["path"])
            rd["url"] = url
            if status == "missing":
                # R228r：CONDITIONAL_FIELDS 以裸 url 为键，而 R228o 起绑定 url
                # 可能带 "POST " 方法前缀（同 url 的 GET/POST 分键）——查表前剥掉。
                _ukey = url[5:] if url.startswith("POST ") else url
                if rd["field"] in CONDITIONAL_FIELDS.get(_ukey, set()):
                    rd["note"] = "条件存在字段（只在错误/降级分支返回），非漂移"
                    soft.append(rd)
                elif rd["field"] in PROVENANCE_FIELDS:
                    rd["note"] = "出处字段缺失（宪法第三条）：|| 兜底把出处静默渲染成空串"
                    hard.append(rd)
                else:
                    (soft if rd["soft"] else hard).append(rd)
            elif status == "skip-empty":
                skipped.append(rd)
            elif rd["esc_whole"] and isinstance(value, (dict, list)):
                rd["value_type"] = type(value).__name__
                rd["value_preview"] = json.dumps(value, ensure_ascii=False)[:90]
                # dict -> "[object Object]"（渲染错误，卡闸门）
                # list -> "a,b,c"（可读但丢结构，体验瑕疵，不卡闸门）
                rd["renders_as"] = ("[object Object]" if isinstance(value, dict)
                                    else "逗号拼接")
                (type_bad if isinstance(value, dict) else soft).append(rd)
    return checked


if __name__ == "__main__":
    sys.exit(main())
