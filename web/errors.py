"""web/errors.py — 业务异常 → HTTP 状态码的统一映射。

重构前每个端点各自 `raise HTTPException(400, ...)`，同一条校验在 bazi /
taohua / hehun 里被复制三遍，措辞漂移就是 R000a-04 那类契约漂移的来源。
现在校验只在 `schemas.py` 抛业务异常，映射只在这里做一次：

    ValidationError  -> 400   值域/参数非法（原契约：中文 detail）
    ComputeError     -> 422   合法参数但计算失败（如 1990-02-30 排盘）
    NotFoundError    -> 404   资源不存在（历史记录 / 研究线程）

响应体形状与重构前逐字一致：`{"detail": "<中文报错>"}`——web selftest 的
err.* 断言逐条依赖这些状态码与消息，改形状即改契约。
"""
from __future__ import annotations

import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .schemas import ComputeError, NotFoundError, ValidationError

# 业务异常 → 状态码。顺序无关（按类型精确匹配注册）。
STATUS_MAP: tuple[tuple[type[Exception], int], ...] = (
    (ValidationError, 400),
    (ComputeError, 422),
    (NotFoundError, 404),
    # R228j：sqlite 锁/磁盘错此前裸穿 ServerErrorMiddleware → 500 无文案。
    # busy_timeout 已把短锁变等待，真撞上（坏库/长锁）给 503 + 人话。
    (sqlite3.OperationalError, 503),
)


def install(app: FastAPI) -> None:
    """给应用装上三个异常处理器（应用工厂调用一次）。"""

    def _make(status: int):
        async def _handler(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        return _handler

    for exc_type, status in STATUS_MAP:
        app.add_exception_handler(exc_type, _make(status))

    # R229n（R6-#6）：sqlite 原文（"database is locked" 等）是英文实现
    # 细节，不能上屏——固定中文，原文只在服务端可见处才有价值。
    async def _sqlite_handler(_request: Request,
                              exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503,
                            content={"detail": "存储暂时不可用，请稍后再试"})
    app.add_exception_handler(sqlite3.OperationalError, _sqlite_handler)
