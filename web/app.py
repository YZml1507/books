"""web/app.py — 应用工厂（古籍智慧助手：读书 + 数术）。

本文件在 R178b 之前是 2277 行的单文件后端，其中 912 行是塞在 `__main__`
里的自测。重构后它只做四件事：建 FastAPI 实例、挂静态资源、装异常处理器、
装四个域路由。业务在 `services.py`，校验在 `schemas.py`，HTTP 绑定在
`routers/`，自测搬到独立的 `selftest.py`。

分层（宪法 III「分层架构不可越界」在 web 层的落地）：
    deps.py       路径解析（含 PyInstaller frozen 分支）+ 资源句柄
    schemas.py    输入形状与值域校验 → 抛业务异常
    services.py   编排 src/guji，返回纯 dict，不认识 HTTP
    errors.py     业务异常 → 400/422/404 的唯一映射点
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

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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


def create_app() -> FastAPI:
    """构建应用。可被自测、uvicorn、PyInstaller 入口各自调用。"""
    application = FastAPI(title="古籍智慧助手（读书 + 数术）", version=VERSION)

    # R229z续8（R8 P1-2）：HTTP 压缩——starlette 自带零新依赖。实测
    # app.js 269KB→97KB、/api/bazi 46KB 约压 80%，/api/research 349KB
    # 收益更大。1KB 以下的响应不值得压（gzip 有固定头）。
    application.add_middleware(GZipMiddleware, minimum_size=1000)

    # 静态资源：/static 指向 index.html 所在目录（开发期 ROOT/web/static，
    # frozen 期 _MEIPASS/web/static，与 INDEX 同源）。
    if os.path.isdir(deps.STATIC_DIR):
        application.mount("/static",
                          StaticFiles(directory=deps.STATIC_DIR),
                          name="static")

    errors.install(application)

    # R228t：安全响应头——本地单用户应用也经浏览器渲染，nosniff 防 MIME
    # 嗅探把上传/拼接内容当可执行，DENY 防被 iframe 套壳钓鱼，
    # no-referrer 防查询串外泄。CSP 不配：index.html 有内联 <script>/
    # style=，要配只能 unsafe-inline，形同虚设。
    @application.middleware("http")
    async def _security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    # R229r：请求体大小护栏——FastAPI 默认无上限，超大 POST 在 pydantic
    # 校验前就全量读进内存（写放大之外的另一颗雷）。已知最长字段是
    # threads.claim 2000 字 + evidence ≤64×~2400 字 ≈ 160KB，放宽到 512KB。
    @application.middleware("http")
    async def _body_size_guard(request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None and cl.isdigit() and int(cl) > 512 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体太大了，精简一下再发"})
        # R230a-40（R15-P1-1）：chunked 传输天然无 Content-Length，此前整体
        # 绕过护栏（2MB body 实测走到校验层）。浏览器永远不会发 chunked
        # 请求体——见到 transfer-encoding 且无长度声明就拒。
        if cl is None and request.headers.get("transfer-encoding"):
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体太大了，精简一下再发"})
        return await call_next(request)

    # R229z续8 续（R8 P1-2 附）：字体/出图资产低变动——一天 Cache-Control，
    # 非 SW 会话不必每次逐个 304 回源。
    @application.middleware("http")
    async def _static_cache(request, call_next):
        resp = await call_next(request)
        p = request.url.path
        if p.startswith(("/static/fonts/", "/static/cream/",
                         "/static/tarot/", "/static/animotion/",
                         "/static/_candidates/")):
            resp.headers.setdefault("Cache-Control",
                                    "public, max-age=86400")
        elif p.startswith(("/static/",)) and p.endswith((".js", ".css")):
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

    def _index_response(request: Request):
        """单页前端入口响应。R230n（R25-3.1）：og:image 是相对路径时主流
        卡片爬虫不解析——按 request.base_url 注入绝对 URL（不依赖固定域名）。"""
        if not os.path.exists(deps.INDEX):
            raise HTTPException(500, "前端文件缺失：web/static/index.html")
        try:
            html = open(deps.INDEX, encoding="utf-8").read()
            base = str(request.base_url).rstrip("/")
            html = html.replace('content="/static/', f'content="{base}/static/')
            return HTMLResponse(html)
        except OSError:
            return FileResponse(deps.INDEX)

    @application.get("/", include_in_schema=False)
    def index(request: Request):
        return _index_response(request)

    # R228k：SW 根作用域——/static/sw.js 默认只管 /static/ 下的请求，
    # '/' 的导航永远进不了 fetch 分支，「断网不白屏」此前完全不生效。
    # 改从根路径下发同一文件并显式放行 scope。
    @application.get("/sw.js", include_in_schema=False)
    def service_worker():
        sw_path = os.path.join(deps.STATIC_DIR, "sw.js")
        if not os.path.exists(sw_path):
            raise HTTPException(404, "sw.js 缺失")
        return FileResponse(sw_path, media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/"})

    # R230n（R25-3.3）：SPA 兜底——乱路径此前 404 JSON（无 SW 时）与
    # SW 接管渲染首页（有 SW 时）口径分裂。统一：非 /api//static 的 GET
    # 且下游已返 404 时回 index.html（?view= 深链随之可用）。
    # 注意必须做成中间件而非 `/{path:path}` 路由——catch-all 路由对
    # DELETE 等非 GET 方法是部分匹配，会把未知路径的 404 抬成 405。
    @application.middleware("http")
    async def _spa_fallback(request, call_next):
        resp = await call_next(request)
        if (request.method == "GET" and resp.status_code == 404
                and not request.url.path.startswith(("/api/", "/static/"))
                and os.path.exists(deps.INDEX)):
            return _index_response(request)
        return resp

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8123)
