"""web/app.py — 应用工厂（古籍智慧助手：读书 + 数术）。

本文件在 R178b 之前是 2277 行的单文件后端，其中 912 行是塞在 `__main__`
里的自测。重构后它只做四件事：建 FastAPI 实例、挂静态资源、装异常处理器、
装四个域路由。业务在 `services.py`，校验在 `schemas.py`，HTTP 绑定在
`routers/`，自测搬到独立的 `selftest.py`。

分层（宪法 III「分层架构不可越界」在 web 层的落地）：
    deps.py       路径解析（含 PyInstaller frozen 分支）+ 资源句柄
    schemas.py    输入形状与值域校验 → 抛业务异常
    services.py   编排 src/guji，返回纯 dict，不认识 HTTP
    errors.py     业务异常 + 基建异常 → 400/422/404/503 的统一映射点
    routers/*.py  HTTP 绑定，按域拆分
    selftest.py   standing 自测（原 __main__ 那 912 行，断言逐条保留）

解读层（R178b，D-226b）：解读走 `guji.interpreter` 确定性规则引擎——零
网络、零成本、同输入必同输出。原 LLM 生成式解读（`llm_reader`）已删除，
`use_llm` 开关不再存在，响应字段统一为 `interpretation`。

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe web\\selftest.py
    .\\.venv\\Scripts\\python.exe -m uvicorn web.app:app --port 8123
"""
from __future__ import annotations

import html as _html
import os
import re
import time
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

# 双导入形态支持（R179b，D-233b）：本模块必须在两种导入方式下都能工作。
#   * `web.app:app`   —— 包导入（web/selftest.py、web_launcher.py 用）
#   * `app:app`       —— 顶层模块导入，cwd=web/（审查轨 probes/ 用：
#                        probe_ui_smoke.py:158 与 probe_contract.py:224）
# 后者下 `__package__` 为空，相对导入 `from . import deps` 会抛
# ImportError: attempted relative import with no known parent package。
# probes/ 是审查轨领土（宪法第五条），不能改它来适配我这侧的重构——
# 兼容责任在 web/ 这边。
if __package__:
    from . import deps, errors
    from .routers import ROUTERS
else:                                    # pragma: no cover - 顶层导入分支
    import os as _os
    import sys as _sys

    _here = _os.path.dirname(_os.path.abspath(__file__))
    _root = _os.path.dirname(_here)
    for _p in (_root, _os.path.join(_root, "src")):
        if _p not in _sys.path:
            _sys.path.insert(0, _p)
    from web import deps, errors
    from web.routers import ROUTERS

VERSION = "0.6.0"

# R2509（审-P2-7）：_index_response 原每请求同步 open() 50KB——
# async _spa_fallback 里它直接跑在事件循环上。按 mtime 缓存原文，
# 改文件自动失效（dev 友好），og/base 注入仍是每请求的事。
# R2522（审-P3-1）：键加 st_size——cp -p/tar -p 保 mtime 的部署曾会
# 永久发旧壳；stat→read 间隙的半写文件也可能顶着新 mtime 被缓存。
_INDEX_CACHE: dict[str, tuple[tuple[int, int], str]] = {}


def _read_index_text(path: str) -> str:
    st = os.stat(path)
    sig = (st.st_mtime_ns, st.st_size)
    ent = _INDEX_CACHE.get(path)
    if ent is not None and ent[0] == sig:
        return ent[1]
    txt = open(path, encoding="utf-8").read()
    _INDEX_CACHE[path] = (sig, txt)
    return txt


def create_app() -> FastAPI:
    """构建应用。可被自测、uvicorn、PyInstaller 入口各自调用。"""
    application = FastAPI(title="古籍智慧助手（读书 + 数术）", version=VERSION)

    # R229z续8（R8 P1-2）：HTTP 压缩——starlette 自带零新依赖。实测
    # app.js 269KB→97KB、/api/bazi 46KB 约压 80%，/api/research 349KB
    # 收益更大。1KB 以下的响应不值得压（gzip 有固定头）。
    application.add_middleware(GZipMiddleware, minimum_size=1000)

    # R2357（R113-P2-15/P3-21）：公网部署两个可选闸——
    #  BOOKS_ALLOWED_HOSTS：逗号分隔 Host 白名单（TrustedHost），防伪造
    #    Host 让 og:url/og:image 缓存投毒；不设 = 现状放行（本地单用户）。
    #  BOOKS_CORS_ORIGINS：逗号分隔 Origin 白名单（分体部署用，如
    #    github.io 落地页 + Railway API）；不设 = 不加 CORS 头（同源形态）。
    _hosts = [h.strip() for h in
              os.getenv("BOOKS_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if _hosts:
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        application.add_middleware(TrustedHostMiddleware,
                                   allowed_hosts=_hosts)
    _origins = [o.strip() for o in
                os.getenv("BOOKS_CORS_ORIGINS", "").split(",") if o.strip()]
    if _origins:
        from starlette.middleware.cors import CORSMiddleware
        application.add_middleware(CORSMiddleware,
                                 allow_origins=_origins,
                                 # R2522（审-P3-4）：分体部署 + 访问口令
                                 # 此前结构性不通——缺 credentials 浏览器
                                 # 不送 books_key cookie，跨源恒 401。
                                 # origins 已是显式白名单（非 *），开
                                 # credentials 安全；同源形态不受影响。
                                 allow_credentials=True,
                                 allow_methods=["GET", "POST", "DELETE",
                                                "PATCH"],
                                 allow_headers=["Content-Type"])

    # 静态资源：/static 指向 index.html 所在目录（开发期 ROOT/web/static，
    # frozen 期 _MEIPASS/web/static，与 INDEX 同源）。
    if os.path.isdir(deps.STATIC_DIR):
        application.mount("/static",
                          StaticFiles(directory=deps.STATIC_DIR),
                          name="static")

    errors.install(application)

    # R2361（部署）：BOOKS_ACCESS_TOKEN 访问令闸——设了它整站带钥匙才
    # 进（含页面/静态/全部 API），没钥匙只见到一把「输口令」的门；
    # /api/health 豁免（托管平台健康探测要用）。不设 = 现状全开
    # （本地单用户），自用公网实例强烈建议设。
    _GATE_PAGE = (
        "<!doctype html><meta charset=utf-8><meta name=viewport "
        "content='width=device-width,initial-scale=1'>"
        "<title>小满的门</title><body style='margin:0;min-height:100vh;"
        "display:flex;align-items:center;justify-content:center;"
        "background:#f7efe6;font-family:ui-rounded,PingFang SC,"
        "Microsoft YaHei,sans-serif'>"
        "<form method=post action='/_gate' style='background:#fff;"
        "padding:32px 28px;border-radius:18px;box-shadow:0 8px 30px "
        "rgba(120,80,40,.12);text-align:center;max-width:320px'>"
        "<div style='font-size:34px'>🌾</div>"
        "<p style='color:#7a6650;margin:10px 0 16px'>这里是小满的解忧铺，"
        "带钥匙的朋友请进～</p>"
        "<input name=key type=password placeholder='口令' autofocus "
        "style='width:100%;box-sizing:border-box;padding:10px 12px;"
        "border:1.5px solid #e5d5c0;border-radius:12px;font-size:15px'>"
        # R2400（R129-P2-9）：门页按钮收编品牌玫瑰渐变（原 #c96f4a
        # 陶土色与 app 内玫瑰不同族），圆角随全站 12px 档。
        "<button style='margin-top:14px;width:100%;padding:10px 0;border:0;"
        "border-radius:12px;background:linear-gradient(135deg,#B04E40,"
        "#A8435F);color:#fff;font-size:15px;cursor:pointer'>开门</button>"
        # R2364（R120-P1-1）：next 槽——门页记住你要去的深链，
        # 解锁完跳回原址（邀请链生辰参数不再被闸吃掉）。
        "<input type=hidden name=next value='{next}'>"
        "{hint}</form></body>")
    _GATE_HINT = ("<p style='color:#c0504a;font-size:13px;margin:10px 0 0'>"
                  "钥匙不对——再想想？</p>")

    @application.middleware("http")
    async def _access_gate(request, call_next):
        import hmac as _hmac
        _tok = os.getenv("BOOKS_ACCESS_TOKEN", "")
        if not _tok:
            return await call_next(request)

        def _eq(a: str, b: str) -> bool:
            # R2522（审-P1）：compare_digest(str) 双参要求 ASCII——非 ASCII
            # 口令/cookie/?key=/表单值在 ExceptionMiddleware 外侧抛
            # TypeError → 匿名可达裸 500（非 ASCII 口令更直接全站 500）。
            # 统一 bytes 比对，非 ASCII 口令也能正常工作。
            return _hmac.compare_digest(
                a.encode("utf-8", "replace"), b.encode("utf-8", "replace"))
        path = request.url.path
        # 健康探测永远放行（平台探活用，无敏感内容）。
        if path == "/api/health":
            return await call_next(request)
        # R2506（审-F5）：CORS 预检放行——本闸注册在 CORSMiddleware
        # 之后 = 位置更靠外，OPTIONS /api/* 此前直撞 401 且响应无
        # ACAO 头，BOOKS_ACCESS_TOKEN + BOOKS_CORS_ORIGINS 的分体部署
        # （github.io 落地页 + API）浏览器层全灭。预检不带凭据、不泄
        # 业务数据，放行由内层 CORS 中间件正常回答；真实请求仍被拦。
        if request.method == "OPTIONS":
            return await call_next(request)
        # R2400（R137-P2-2）：cookie 值改为口令的派生指纹而非明文——
        # 浏览器侧/日志里见到 cookie 不再等于见到钥匙本身。
        _ck = _hmac.new(_tok.encode(), b"books-gate-cookie",
                        "sha256").hexdigest()
        good = _eq(request.cookies.get("books_key", ""), _ck)
        # R2503（审-P1）：限速桶/IP 解析从 POST /_gate 块内提出来——
        # ?key= 直通此前不耗桶，302/403 oracle 下 GET 旁路把
        # 10 次/60s/IP 爆破防线整体架空。两个认证原语同桶同口径。
        def _gate_ip() -> str:
            _ip = (request.client.host if request.client else "?")
            # R2400（R137-P1-2）：XFF 首元素客户端可伪造——自填
            # X-Forwarded-For 即换桶绕过 _gate 限速。单可信代理（Render）
            # 下链尾 = 离服务端最近一跳回源的真实客户端。
            # R2502：整链无条件信任仍有洞——直连部署（无代理）时攻击者
            # 整根伪造 XFF 轮换桶位。改为显式开关：BOOKS_TRUST_XFF=1 才信。
            # R2522（审-P3-5）：Dockerfile 并不设此开关（恒代理部署靠
            # --forwarded-allow-ips '*' + 下方 __all__ 全局桶兜底）。
            _xff = request.headers.get("x-forwarded-for") or ""
            if _xff.strip() and os.getenv(
                    "BOOKS_TRUST_XFF", "").strip().lower() in (
                    "1", "on", "true", "yes"):
                _ip = _xff.split(",")[-1].strip() or _ip
                return _ip
            # R2506（审-F1）：不信 XFF 时 _ip 也不能当桶键——
            # Dockerfile 以 --forwarded-allow-ips '*' 起 uvicorn，
            # proxy-headers 早把 scope["client"] 用自填 XFF[0] 改写，
            # 客户端旋转换 IP 值即无限换桶，10/60s 限速被整体架空。
            # 默认桶退化为全局桶——单口令场景语义反而更对：验对口令
            # 与已解锁 Cookie 不耗桶，攻击者灌桶也锁不住正确解锁。
            return "__all__"

        _gate_bucket = getattr(_access_gate, "_bucket", None)
        if _gate_bucket is None:
            _gate_bucket = {}
            _access_gate._bucket = _gate_bucket

        def _gate_limited() -> bool:
            # R2363（R116-P1-2）：在线爆破面——口令闸是唯一防线，
            # 进程内 10 次/60s/IP 限速（单 worker 下够用）。
            _now = time.time()
            _hist = [t for t in _gate_bucket.get(_gate_ip(), [])
                     if _now - t < 60]
            if len(_hist) >= 10:
                return True
            _hist.append(_now)
            _gate_bucket[_gate_ip()] = _hist
            if len(_gate_bucket) > 2000:
                _gate_bucket.clear()
            return False

        # 解锁端点：表单口令 → 写 Cookie 回首页。
        # （不用 request.form()——Starlette 表单解析要 python-multipart，
        #   runtime 依赖里没有；urlencoded body 手工 parse_qs 零新依赖）
        if path == "/_gate" and request.method == "POST":
            from urllib.parse import parse_qs
            _qs = parse_qs(
                (await request.body()).decode("utf-8", "replace"))
            key = _qs.get("key", [""])[0]
            # R2364：解锁跳回深链原址；只放站内相对路径防开放跳转。
            # R2400（R130-P2-1/P2-3）：next 白名单收紧——`%5c` 解码进
            # next 被浏览器归一成 `//` 即成开放跳转；CRLF 落 Location
            # 头是未处理异常面。`/` 起、字符集内全收，越界回落 '/'。
            _nxt = _qs.get("next", [""])[0]
            if (_nxt.startswith("//") or
                    not re.fullmatch(r"/[A-Za-z0-9_/?=&%#.:\-~+]*", _nxt)):
                _nxt = "/"
            # R2506（审-F1 配套）：先验口令再扣桶——与 ?key= 直通同口径。
            # 验对不耗桶也不查桶（全局桶下攻击者灌桶锁不住主人自己解锁）；
            # 验错才计一次失败。
            if _eq(key, _tok):
                resp = PlainTextResponse("ok", status_code=302,
                                         headers={"Location": _nxt})
                resp.set_cookie("books_key", _ck, httponly=True,
                                samesite="lax",
                                secure=request.url.scheme == "https",
                                max_age=30 * 86400)
                return resp
            if _gate_limited():
                return PlainTextResponse(
                    "敲太多次门啦——歇一分钟再来",
                    status_code=429)
            # 403 而非 200：SW 的 navigate 分支只缓存 resp.ok——门页
            # 被 200 吐出去会进 '/' 壳位，cookie 过期后解锁了还见门页。
            # 浏览器照常渲染 HTML 体，用户看到同样的门。
            return PlainTextResponse(
                _GATE_PAGE.format(hint=_GATE_HINT,
                                  next=_html.escape(_nxt, quote=True)),
                media_type="text/html", status_code=403)
        if good:
            return await call_next(request)
        # ?key= 直通：给主人自己用的可分享链接——验完设 Cookie 再跳回
        # 原路径（钥匙不进历史记录）。
        # R2503（审-P1）：?key= 直通此前不耗限速桶——302/403 oracle 下
        # GET 旁路把爆破防线整体架空。补齐「验错才扣桶」：对口令不罚
        # （分享链让同 NAT 的朋友秒进不是攻击），错 key 与 POST /_gate
        # 同桶，10 次/60s 后 429。
        _key_ok = _eq(request.query_params.get("key", ""), _tok)
        if ("key" in request.query_params and not _key_ok
                and _gate_limited()):
            return PlainTextResponse(
                "敲太多次门啦——歇一分钟再来",
                status_code=429)
        if _key_ok:
            q = dict(request.query_params)
            q.pop("key", None)
            target = path + ("?" + urlencode(q, doseq=True) if q else "")
            # R2400（R130-P2-1）：?key= 跳回同样组 Location——path 里
            # 解码出的 `\`/CRLF 与 next 同洞，同白名单回落 '/'。
            if (target.startswith("//") or
                    not re.fullmatch(r"/[A-Za-z0-9_/?=&%#.:\-~+]*", target)):
                target = "/"
            resp = PlainTextResponse("ok", status_code=302,
                                     headers={"Location": target or "/"})
            resp.set_cookie("books_key", _ck, httponly=True,
                            samesite="lax",
                            secure=request.url.scheme == "https",
                            max_age=30 * 86400)
            return resp
        if path.startswith("/api"):
            return JSONResponse(status_code=401,
                                content={"detail": "需要钥匙才能进来哦"})
        # R2364：GET 深链被闸 → 门页记住原路径+查询，解锁跳回。
        _orig = request.url.path + (
            "?" + request.url.query if request.url.query else "")
        return PlainTextResponse(
            _GATE_PAGE.format(hint="", next=_html.escape(_orig, quote=True)),
            media_type="text/html", status_code=403)

    # R228t：安全响应头——本地单用户应用也经浏览器渲染，nosniff 防 MIME
    # 嗅探把上传/拼接内容当可执行，DENY 防被 iframe 套壳钓鱼，
    # no-referrer 防查询串外泄。
    # R2509：CSP 补位——早前因 index.html 有内联 <script>/style= 判定
    # 「要配只能 unsafe-inline，形同虚设」整体不配。但 CSP 的价值不
    # 止 script-src：connect-src 'self' 封死注入脚本的 fetch/beacon
    # 外联（任何 esc() 漏网 XSS 都偷不走数据），base-uri/object-src/
    # form-action 各堵一类注入面，代价为零（全站无外部资源、无
    # eval/Worker、fetch 全走同源相对路径——已逐点核实）。
    _SEC = {"X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy":
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "worker-src 'self'; "
                "manifest-src 'self'"}

    @application.middleware("http")
    async def _security_headers(request, call_next):
        resp = await call_next(request)
        for _k, _v in _SEC.items():
            resp.headers.setdefault(_k, _v)
        return resp

    # R229r：请求体大小护栏——FastAPI 默认无上限，超大 POST 在 pydantic
    # 校验前就全量读进内存（写放大之外的另一颗雷）。已知最长字段是
    # threads.claim 2000 字 + evidence ≤64×~2400 字 ≈ 160KB，放宽到 512KB。
    @application.middleware("http")
    async def _body_size_guard(request, call_next):
        cl = request.headers.get("content-length")
        # R2508（审-P1）：CL+TE 双头时 TE 按 h11 语义赢——旧顺序只看
        # cl 有没有，TE chunked 的多 MB body 照样全量进内存。TE 在场
        # 一律拒（无法预先验长），与 TE-only 同口径。
        if request.headers.get("transfer-encoding"):
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体太大了，精简一下再发"},
                # R2508（审-P2）：本中间件在 _security_headers 外侧——
                # 它的 413 拿不到安全头（也拿不到 CORS 头）。就地补齐。
                headers=_SEC)
        if cl is not None and cl.isdigit() and int(cl) > 512 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体太大了，精简一下再发"},
                headers=_SEC)
        return await call_next(request)

    # R229z续8 续（R8 P1-2 附）：字体/出图资产低变动——一天 Cache-Control，
    # 非 SW 会话不必每次逐个 304 回源。
    @application.middleware("http")
    async def _static_cache(request, call_next):
        resp = await call_next(request)
        p = request.url.path
        # R2508（审-P1）：此前不判状态码——/static/fonts/ 下未部署文件
        # 的 404 被盖 public,max-age=86400，浏览器/中间缓存钉死负缓存
        # 一天；POST 体积超限的 413 也吃到 3600。正缓存只盖 2xx。
        if resp.status_code < 300 and p.startswith(
                ("/static/fonts/", "/static/cream/",
                 "/static/tarot/", "/static/animotion/")):
            resp.headers.setdefault("Cache-Control",
                                    "public, max-age=86400")
        elif resp.status_code < 300 and p.startswith(("/static/",)) \
                and p.endswith((".js", ".css")):
            # R230n（R25-5.1）：主资源此前只有启发式缓存——SW 未装的回访
            # 用户每次全量重拉 ~400KB。1h 缓存+SW shell-hash 保证版本一致。
            resp.headers.setdefault("Cache-Control",
                                    "public, max-age=3600")
        elif p == "/":
            resp.headers.setdefault("Cache-Control", "no-cache")
        elif p.startswith("/api/"):
            # R230v（R34-#17）：API 响应钉死 no-store——SW 已不缓存，
            # 但代理/隐私扩展见到无声明的 JSON 可能启发式暂存命理数据。
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    for router in ROUTERS:
        application.include_router(router)

    # R2349u（R91-P0-2）：壳资产版本化——HTML 引用 app.js/styles.css
    # 时注入 ?v=<shell-hash>，与 sw.js 的 CACHE 名同源。旧 SW 存活期内
    # 「新 HTML + 旧 JS」混版被一次收掉：旧壳里没有 ?v=新 的请求，
    # caches.match 直接 miss → 走网拿到新字节。sw.js 用 ignoreSearch
    # 匹配，新 SW 的钉死壳件照常命中。
    _SW_HASH = {"t": 0.0, "v": ""}

    def _shell_hash() -> str:
        sw_path = os.path.join(deps.STATIC_DIR, "sw.js")
        try:
            mt = os.path.getmtime(sw_path)
            if _SW_HASH["t"] == mt and _SW_HASH["v"]:
                return _SW_HASH["v"]
            m = re.search(r"books-shell-(\w+)",
                           open(sw_path, encoding="utf-8").read())
            v = m.group(1) if m else ""
            _SW_HASH["t"], _SW_HASH["v"] = mt, v
            return v
        except OSError:
            return ""

    def _index_response(request: Request):
        """单页前端入口响应。R230n（R25-3.1）：og:image 是相对路径时主流
        卡片爬虫不解析——按 request.base_url 注入绝对 URL（不依赖固定域名）。"""
        if not os.path.exists(deps.INDEX):
            raise HTTPException(500, "前端文件缺失：web/static/index.html")
        try:
            html = _read_index_text(deps.INDEX)
            # R2508（审-P2）：base_url 取自 Host/X-Forwarded-Host
            # （--proxy-headers 下全可控）——含引号即破 og 属性注 HTML。
            # 按 URL 安全集过滤后再注入（robots/sitemap 同款）。
            base = re.sub(r"[^\w.\-~:/?#[\]@!$&'()*+,;=%]+", "",
                          str(request.base_url).rstrip("/"))
            html = html.replace('content="/static/', f'content="{base}/static/')
            # R2350b（R99-P2）：og:url/og:site_name 补缺——爬虫拿到
            # 规范地址与站名；部署在 TLS 反代后需 uvicorn
            # --proxy-headers 才能拿到对的 scheme/host（base_url
            # 落成 http://内网 时 og:image 静默抓不到）。
            html = html.replace(
                '<meta property="og:type" content="website">',
                '<meta property="og:type" content="website">\n'
                f'<meta property="og:url" content="{base}/">\n'
                '<meta property="og:site_name" content="小满的解忧铺">')
            # R2350f（R102-P2-3）：分享链按 ?view= 换 og:title/description——
            # 微信/QQ 预览此前千链一面，不含「她在测塔罗」语境。
            _OG_VIEW = {
                "tarot": ("塔罗占卜", "抽到的是哪几张？晒晒你的牌"),
                "liuyao": ("六爻摇卦", "摇出来的卦，读给你听"),
                "hehun": ("八字合婚", "和 TA 配不配 · 看缘分深浅"),
                "huangli": ("翻黄历", "今天适合做什么 · 宜忌一览"),
                "bazi": ("今日命盘", "生日一填 · 大白话解读你的盘"),
                "taohua": ("桃花运", "最近的桃花信号帮你看看"),
                "qiming": ("五行起名", "按五行补缺 · 起个好名字"),
                "daily": ("今日一签", "每天抽一签 · 攒连签好运"),
                "xingzuo": ("今日星座", "十二宫 · 今日运势播报"),
                "xzm": ("星座速配", "你们俩的星座合拍指数"),
                "history": ("排盘历史", "翻翻看过的盘 · 可导出"),
            }
            _v = (request.query_params.get("view") or "").lower()
            if not _v:
                # 路径式深链 /tarot 走 SPA fallback——路径段也当视图名。
                _seg = request.url.path.strip("/").lower()
                if _seg and "/" not in _seg:
                    _v = _seg
            if _v in _OG_VIEW:
                _t, _d = _OG_VIEW[_v]
                html = html.replace(
                    '<meta property="og:title" content="小满的解忧铺">',
                    f'<meta property="og:title" content="{_t} · 小满的解忧铺">')
                html = html.replace(
                    '<meta property="og:description" content="黄历择日 · 八字塔罗 · 每日一签——测测你今天什么签">',
                    f'<meta property="og:description" content="{_d}">')
            v = _shell_hash()
            if v:
                html = html.replace('src="/static/app.js"',
                                    f'src="/static/app.js?v={v}"')
                html = html.replace('href="/static/styles.css"',
                                    f'href="/static/styles.css?v={v}"')
            # R2349u（R91-P2-4）：SPA fallback 走这条路时绕过了内层
            # 安全头/no-cache 中间件——在出口补齐同口径。
            # R2509（审-P2-4）：上轮补 CSP 时漏了这条手工复刻路径——
            # /tarot 等深链入口响应独缺 CSP，正好是最需要 connect-src
            # 的地方。直接复用 _SEC，不再逐项手写。
            resp = HTMLResponse(html)
            resp.headers["Cache-Control"] = "no-cache"
            for _k, _v in _SEC.items():
                resp.headers[_k] = _v
            return resp
        except OSError:
            return FileResponse(deps.INDEX)

    @application.get("/", include_in_schema=False)
    def index(request: Request):
        return _index_response(request)

    # R2350g（R105-P2-3）：HEAD / ——监控/链接检查器裸 HEAD 此前 405。
    @application.head("/", include_in_schema=False)
    def index_head():
        return HTMLResponse("")

    # R228k：SW 根作用域——/static/sw.js 默认只管 /static/ 下的请求，
    # '/' 的导航永远进不了 fetch 分支，「断网不白屏」此前完全不生效。
    # 改从根路径下发同一文件并显式放行 scope。
    # R2350g（R105-P1-1）：爬虫三件套从根路径下发——/static/ 下的文件
    # 爬虫不会去翻。favicon.ico 旧式 UA 会裸请求根路径。
    @application.api_route("/robots.txt", methods=["GET", "HEAD"],
                           include_in_schema=False)
    def robots(request: Request):
        # R2357（R113-P2-11）：robots 的 Sitemap 指令同样要绝对 URL。
        p = os.path.join(deps.STATIC_DIR, "robots.txt")
        if not os.path.exists(p):
            raise HTTPException(404)
        base = re.sub(r"[^\w.\-~:/?#[\]@!$&'()*+,;=%]+", "",
                      str(request.base_url).rstrip("/"))
        body = open(p, encoding="utf-8").read().replace(
            "Sitemap: /sitemap.xml", f"Sitemap: {base}/sitemap.xml")
        return PlainTextResponse(body)

    @application.api_route("/sitemap.xml", methods=["GET", "HEAD"],
                           include_in_schema=False)
    def sitemap(request: Request):
        # R2357（R113-P2-11）：sitemap 规范要绝对 URL——全相对 <loc>
        # 会被搜索引擎整体丢弃。按请求 base_url（含 proxy-headers 还原
        # 的公网域）动态拼，部署域名写死不得。
        p = os.path.join(deps.STATIC_DIR, "sitemap.xml")
        if not os.path.exists(p):
            raise HTTPException(404)
        base = re.sub(r"[^\w.\-~:/?#[\]@!$&'()*+,;=%]+", "",
                      str(request.base_url).rstrip("/"))
        body = re.sub(r"<loc>/", "<loc>" + base + "/",
                      open(p, encoding="utf-8").read())
        return Response(body, media_type="application/xml")

    @application.api_route("/favicon.ico", methods=["GET", "HEAD"],
                           include_in_schema=False)
    def favicon():
        for name in ("icon-192.png", "icon-512.png"):
            p = os.path.join(deps.STATIC_DIR, "cream", name)
            if os.path.exists(p):
                return FileResponse(p, media_type="image/png")
        raise HTTPException(404)

    @application.get("/sw.js", include_in_schema=False)
    def service_worker():
        sw_path = os.path.join(deps.STATIC_DIR, "sw.js")
        if not os.path.exists(sw_path):
            raise HTTPException(404, "sw.js 缺失")
        # R2345（R63-P2-1）：sw.js 自身无 Cache-Control 时 Chrome 的
        # SW 更新检查在 24h 窗口内走启发式缓存——新部署最长 ~24h 才被
        # 发现。no-cache 强制每次 revalidate（有 ETag，304 仍省流）。
        return FileResponse(sw_path, media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/",
                                     "Cache-Control": "no-cache"})

    # R230n（R25-3.3）：SPA 兜底——乱路径此前 404 JSON（无 SW 时）与
    # SW 接管渲染首页（有 SW 时）口径分裂。统一：非 /api//static 的 GET
    # 且下游已返 404 时回 index.html（?view= 深链随之可用）。
    # 注意必须做成中间件而非 `/{path:path}` 路由——catch-all 路由对
    # DELETE 等非 GET 方法是部分匹配，会把未知路径的 404 抬成 405。
    @application.middleware("http")
    async def _spa_fallback(request, call_next):
        resp = await call_next(request)
        # R2350g（R105-P2-3）：HEAD 同样收——监控/链接检查器/IM 预取
        # 先发 HEAD，405 会被误判成站点挂了。Starlette 对 HEAD 自动剥体。
        if (request.method in ("GET", "HEAD") and resp.status_code == 404
                and not request.url.path.startswith(("/api/", "/static/"))
                # R2506（审-F6）：裸 /api、/static 也要守 404 JSON 契约——
                # startswith 带尾斜杠漏放裸路径，GET /api 此前收 200
                # 的 index.html（与其他 /api/* 404 契约不一致）。
                and request.url.path not in ("/api", "/static")
                # R2350g（R105-P1-1）：含扩展名的请求（robots.txt /
                # sitemap.xml / favicon.ico / 任意 .xml）不做 SPA 兜底——
                # 否则爬虫拿到 50KB HTML 壳当 robots，坏链全成 soft-404。
                and "." not in request.url.path.rsplit("/", 1)[-1]
                and os.path.exists(deps.INDEX)):
            return _index_response(request)
        return resp

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8123)
