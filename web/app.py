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

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

    # 静态资源：/static 指向 index.html 所在目录（开发期 ROOT/web/static，
    # frozen 期 _MEIPASS/web/static，与 INDEX 同源）。
    if os.path.isdir(deps.STATIC_DIR):
        application.mount("/static",
                          StaticFiles(directory=deps.STATIC_DIR),
                          name="static")

    errors.install(application)

    for router in ROUTERS:
        application.include_router(router)

    @application.get("/", include_in_schema=False)
    def index():
        """单页前端入口。"""
        if not os.path.exists(deps.INDEX):
            raise HTTPException(500, "前端文件缺失：web/static/index.html")
        return FileResponse(deps.INDEX)

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

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8123)
