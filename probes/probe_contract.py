"""probe_contract.py — 前后端字段名契约闸门（审查轨 R118a，D-127a）。

**为什么存在**：`web/app.py --selftest` 有 130 条断言，全部是后端 TestClient
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
    "/api/history":           {"method": "GET"},
    "/api/user/prefs":        {"method": "GET"},
    "/api/huangli":           {"method": "GET", "params": {"year": 2026,
                                                           "month": 8, "day": 19}},
    "/api/bazi":              {"method": "POST", "json": {
        "year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
        "calendar_type": "solar", "scope": "day", "use_llm": False}},
    "/api/liuyao":            {"method": "POST", "json": {
        "method": "time", "seed": 42, "year": 1990, "month": 5, "day": 15,
        "hour": 10}},
    "/api/qiming":            {"method": "POST", "json": {
        "surname": "李", "year": 1990, "month": 5, "day": 15, "hour": 12,
        "gender": "男"}},
    "/api/taohua":            {"method": "POST", "json": {
        "year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男"}},
    "/api/hehun":             {"method": "POST", "json": {
        "a_year": 1990, "a_month": 5, "a_day": 15, "a_hour": 10,
        "a_gender": "男", "b_year": 1992, "b_month": 7, "b_day": 20,
        "b_hour": 14, "b_gender": "女"}},
    "/api/tarot/draw":        {"method": "POST", "json": {"seed": 42, "n": 1}},
    # 前端只发 {topic}（实测 422）。契约 probe 用**合法请求体**取真实成功响应，
    # 前端请求体本身的不匹配由 probe_ui_smoke.py 点击后现形，两者分工不重叠。
    "/api/threads":           {"method": "POST", "json": {
        "kind": "refusal", "claim": "probe_contract 契约探针占位",
        "method": "probe_contract"}, "cleanup": "derived"},
    # ── R120a 补齐（R178b 新增/前端新接线的端点）──────────────
    # 上一轮这 8 个端点无 fixture → 报 SKIP。SKIP 让 probe 返回退出码 2
    # （不假装通过），但覆盖是残缺的：前端在这些 handler 里读的字段没被验证。
    "/api/concept":           {"method": "GET", "params": {"q": "無爲"}},
    "/api/compare_works":     {"method": "GET", "params": {
        "work_a": "KR5c0057", "work_b": "KR5c0126", "q": "無爲"}},
    "/api/bookstudy/structure": {"method": "GET", "params": {
        "work_id": "KR1a0001"}},
    "/api/bookstudy/chapter": {"method": "GET", "params": {
        "work_id": "KR1a0001", "scheme": "zhouyi", "addr1": 1}},
    "/api/bookstudy/summary": {"method": "GET", "params": {
        "work_id": "KR1a0001"}},
    "/api/tarot":             {"method": "POST", "json": {"seed": 42, "n": 3}},
    # 路径参数端点：URL 由 probe 侧动态解析（见 PATH_FIXTURES）
    "/api/threads/":          {"method": "PATH", "resolve": "thread_id"},
    "/api/history/":          {"method": "PATH", "resolve": "history_id"},
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
    return [b for b in blocks if has_call(b)]


FETCH_RE = re.compile(r"fetch\(\s*['\"`](/api/[A-Za-z0-9_/]*)")
# R178b 起前端统一走 `api(path)` / `postJSON(path, payload)` 包装器，
# 不再逐处裸调 fetch。两种写法都要认，否则 probe 抽不到任何 URL。
API_CALL_RE = re.compile(
    r"(?:api|postJSON)\(\s*['\"`](/api/[A-Za-z0-9_/{}]*)")
# 变量拼接的 URL：api('/api/history/' + encodeURIComponent(rid))
API_PREFIX_RE = re.compile(r"(?:api|postJSON)\(\s*['\"`](/api/[A-Za-z0-9_/]*?)/?['\"`]\s*\+")
# R178b 前：const j = await resp.json()
# R178b 后：const j = await api('/api/x')  /  const j = await postJSON(...)
JSON_VAR_RE = re.compile(
    r"const\s+(\w+)\s*=\s*await\s+(?:\w+\.json\(\)|api\(|postJSON\()")
# const ben = j.ben || {}   /   const a = j.a_bazi, b = j.b_bazi;
OBJ_BIND_RE = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(\w+)\.(\w+)"
                         r"(?:\s*\|\|\s*\{\})?")
# j.hits.forEach((h, i) => / (j.items||[]).forEach(it => / j.items.slice(0,5).forEach(item =>
ELEM_RE = re.compile(r"\(?\s*(\w+)\.(\w+)\s*(?:\|\|\s*\[\]\s*)?\)?"
                     r"(?:\.\w+\([^)]*\))*\.forEach\(\s*\(?\s*(\w+)")


def field_reads(block: dict) -> tuple[dict, list[dict], list[str]]:
    """返回 (变量绑定表, 读取点列表, fetch 到的 url 列表)。
    绑定表值为 ('root'|'obj'|'elem', path)。"""
    binds: dict[str, tuple[str, list[str]]] = {}
    reads: list[dict] = []
    urls: list[str] = []
    for off, line in enumerate(block["lines"]):
        for rx in (FETCH_RE, API_CALL_RE, API_PREFIX_RE):
            m = rx.search(line)
            if m:
                urls.append(m.group(1))
                break
        m = JSON_VAR_RE.search(line)
        if m:
            binds[m.group(1)] = ("root", [])
    if not urls:
        return binds, reads, urls
    # 迭代 / 派生变量绑定（多趟：派生变量可再派生）
    for _ in range(3):
        for line in block["lines"]:
            for m in ELEM_RE.finditer(line):
                parent, field, var = m.groups()
                if parent in binds and var not in binds:
                    binds[var] = ("elem", binds[parent][1] + [field])
            for m in OBJ_BIND_RE.finditer(line):
                var, parent, field = m.groups()
                if parent in binds and var not in binds and var != parent:
                    binds[var] = ("obj", binds[parent][1] + [field])
    # 字段读取点
    for off, line in enumerate(block["lines"]):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for var, (kind, path) in binds.items():
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
                })
    kept = [r for r in reads if r["field"] not in ERROR_BRANCH_FIELDS]
    return binds, kept, urls


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

    client = TestClient(load_app())
    text = open(FRONTEND_JS, encoding="utf-8").read()
    lines, base = script_region(text, FRONTEND_JS)
    blocks = split_blocks(lines, base)
    src_name = os.path.basename(FRONTEND_JS)
    print(f"前端载体：{src_name}（{os.path.getsize(FRONTEND_JS)}B）")
    if not blocks:
        print(f"probe_contract FAIL-ENV: 在 {src_name} 里切不出任何含 fetch 的 "
              f"handler 块。可能是代码风格变了（如改用箭头函数顶层缩进），"
              f"probe 的块切分需同步更新——静默报 0 是假通过。")
        return 2

    # ── 写端点污染基线（L-22）──────────────────────────────
    # ⚠ 从这里开始到 finally 之间的一切都必须在 try 内：本 probe 开发期实测
    # 踩过——中途异常退出（contentless fts5 的 DELETE 报错）让 4 条占位行留在
    # 了 knowledge.db 里。清理只写在成功路径上，等于没有清理。
    hist_baseline = history_db.count()
    kb_path = os.path.join(ROOT, "data", "index", "knowledge.db")
    created_derived: list[int] = []
    fav_id = None
    # 让 /api/history 与 /api/user/prefs.favorites 非空，元素字段才可判定
    seed_bazi = client.post("/api/bazi", json=FIXTURES["/api/bazi"]["json"])
    assert seed_bazi.status_code == 200, seed_bazi.text[:200]
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
        if fx is None:
            cache[url] = ("nofixture", None)
            return cache[url]
        if fx["method"] == "PATH":
            # 路径参数端点：先取一个真实存在的 id，再打具体 URL。
            # 取不到 id 就诚实报 SKIP，不编一个假 id 去打 404（那会把
            # "端点契约"测成"404 错误体契约"，是另一回事）。
            if fx["resolve"] == "thread_id":
                lst = client.get("/api/threads").json().get("threads") or []
                rid = (lst[0].get("id") if lst else None)
            else:
                recs = client.get("/api/history").json().get("records") or []
                rid = (recs[0].get("id") if recs else None)
            if rid is None:
                cache[url] = ("http", (0, f"{url} 无可用 id（列表为空），"
                                          f"无法构造路径参数请求"))
                return cache[url]
            r = client.get(f"{url.rstrip('/')}/{rid}")
            cache[url] = (("ok", r.json()) if r.status_code == 200
                          else ("http", (r.status_code, r.text[:160])))
            return cache[url]
        if fx["method"] == "GET":
            r = client.get(url, params=fx.get("params"))
        else:
            r = client.post(url, json=fx.get("json"))
        if r.status_code != 200:
            cache[url] = ("http", (r.status_code, r.text[:160]))
            return cache[url]
        body = r.json()
        if fx.get("cleanup") == "derived" and isinstance(body, dict):
            did = body.get("derived_id")
            if did:
                created_derived.append(int(did))
        cache[url] = ("ok", body)
        return cache[url]

    hard: list[dict] = []
    type_bad: list[dict] = []
    soft: list[dict] = []
    skipped: list[dict] = []
    checked = 0
    seen_reads: set[tuple] = set()

    try:
        checked = scan(blocks, fetch, hard, type_bad, soft, skipped, seen_reads)
    finally:
        cleaned, hist_after = cleanup(history_db, kb_mod, kb_path,
                                     hist_baseline, created_derived, fav_id)
        print(f"清理: {', '.join(cleaned) or '无'}；"
              f"history 行数 {hist_baseline} -> {hist_after}")

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


def cleanup(history_db, kb_mod, kb_path, hist_baseline, created_derived, fav_id):
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
            kb.db.commit()
    except Exception as exc:                      # noqa: BLE001
        cleaned.append(f"⚠ 清理未完成：{type(exc).__name__}: {exc}")
    return cleaned, history_db.count()


def scan(blocks, fetch, hard, type_bad, soft, skipped, seen_reads) -> int:
    checked = 0
    for b in blocks:
        binds, reads, urls = field_reads(b)
        if not reads:
            continue
        url = urls[0]
        state, body = fetch(url)
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
        for rd in reads:
            # 同一行同一字段可能被同一 handler 内多个变量别名重复命中，去重后
            # 计数才等于"真实读取点数"（数字必须可复验，宪法第一条）
            key = (rd["line_no"], tuple(rd["path"]), rd["soft"], rd["esc_whole"])
            if key in seen_reads:
                continue
            seen_reads.add(key)
            checked += 1
            status, value = resolve(body, rd["kind"], rd["path"])
            rd["url"] = url
            if status == "missing":
                if rd["field"] in CONDITIONAL_FIELDS.get(url, set()):
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
