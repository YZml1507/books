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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .schemas import ComputeError, NotFoundError, ValidationError

# 业务异常 → 状态码。顺序无关（按类型精确匹配注册）。
STATUS_MAP: tuple[tuple[type[Exception], int], ...] = (
    (ValidationError, 400),
    (ComputeError, 422),
    (NotFoundError, 404),
    # R228j：sqlite 锁/磁盘错此前裸穿 ServerErrorMiddleware → 500 无文案。
    # busy_timeout 已把短锁变等待，真撞上（坏库/长锁）给 503 + 人话。
    # R229z续18：放宽到 DatabaseError 父类——IntegrityError/坏库读错
    # （非 OperationalError 子类）此前仍会 500 无文案。
    (sqlite3.DatabaseError, 503),
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
    app.add_exception_handler(sqlite3.DatabaseError, _sqlite_handler)

    # R230a-38（R15-P1-2）：int64 溢出（thread_id=1e20 等）在 sqlite 绑定时
    # 抛 OverflowError——非 DatabaseError 子类，此前穿透成 500（≥9 端点）。
    # 不用 STATUS_MAP：str(exc) 是英文实现细节，会漏上屏。
    async def _overflow_handler(_request: Request,
                                exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400,
                            content={"detail": "参数超出可接受范围"})
    app.add_exception_handler(OverflowError, _overflow_handler)

    # R230a-39（R15-P2-1+P3 回显放大）：422 错误体里的 `input` 原样回显
    # 原始输入——孤立代理项（\ud800）让默认序列化炸成 500，超长 input
    # 又造成 ~2x 响应放大。改成 repr 转义 + 200 字截断。
    async def _validation_handler(_request: Request,
                                  exc: RequestValidationError
                                  ) -> JSONResponse:
        errs = []
        for e in exc.errors():
            e = dict(e)
            if "input" in e:
                s = repr(e["input"])
                e["input"] = s[:200] + ("…" if len(s) > 200 else "")
            errs.append(e)
        return JSONResponse(status_code=422, content={"detail": errs})
    app.add_exception_handler(RequestValidationError, _validation_handler)
