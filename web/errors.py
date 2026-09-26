"""web/errors.py — 业务异常 → HTTP 状态码的统一映射。

重构前每个端点各自 `raise HTTPException(400, ...)`，同一条校验在 bazi /
taohua / hehun 里被复制三遍，措辞漂移就是 R000a-04 那类契约漂移的来源。
现在校验只在 `schemas.py` 抛业务异常，映射只在这里做一次：

    ValidationError  -> 400   值域/参数非法（原契约：中文 detail）
    ComputeError     -> 422   合法参数但计算失败（如 1990-02-30 排盘）
    NotFoundError    -> 404   资源不存在（历史记录 / 研究线程）

此外 install() 还挂了五个基建映射（R2349s/R85-P2-5 补登记）：
    sqlite3.DatabaseError / OSError -> 503   存储层故障（可恢复口径）
    StarletteHTTPException -> 404 中文 detail / RequestValidationError -> 422 中文化
    OverflowError -> 400   int64 溢出护栏

响应体形状与重构前逐字一致：`{"detail": "<中文报错>"}`——web selftest 的
err.* 断言逐条依赖这些状态码与消息，改形状即改契约。
"""
from __future__ import annotations

import sqlite3

import re
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
    # R230c（R17-P2-3）：Corpus 缺索引现在抛 FileNotFoundError（人话）——
    # 映射 503 与「存储暂时不可用」同档（此前是 OperationalError→503）。
    (FileNotFoundError, 503),
)


def install(app: FastAPI) -> None:
    """给应用装上三个异常处理器（应用工厂调用一次）。"""

    def _make(status: int):
        async def _handler(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(exc)})
        return _handler

    for exc_type, status in STATUS_MAP:
        app.add_exception_handler(exc_type, _make(status))

    # R2349w（R93-P2-13）：FileNotFoundError 的 str(exc) 会带绝对路径
    #（开发期泄仓库路径、exe 期泄 _MEIPASS 临时目录）——剥成「文件名
    # 缺失」口径；模块自己 raise 的中文消息（如「古籍索引还没装好」）
    # 不含路径，原样放行。
    async def _fnf_handler(_request: Request,
                           exc: Exception) -> JSONResponse:
        msg = str(exc)
        if "[Errno" in msg or "/" in msg or "\\" in msg:
            # R2508（审-P2）：脱敏正则此前连「（先跑 scripts/build_index.py）」
            # 里的修复提示一起吃掉——分号内提示段不遮路径。
            _head, _sep, _tail = msg.partition("（")
            _head = re.sub(r"[\w.\-]+(?:/[\w.\-]+)+", "…", _head)
            msg = _head + (_sep + _tail if _sep else "")
            if "[Errno" in msg:
                msg = "资源文件没装进来——请确认部署包完整"
        return JSONResponse(status_code=503, content={"detail": msg})
    app.add_exception_handler(FileNotFoundError, _fnf_handler)

    # R229n（R6-#6）：sqlite 原文（"database is locked" 等）是英文实现
    # 细节，不能上屏——固定中文，原文只在服务端可见处才有价值。
    async def _sqlite_handler(_request: Request,
                              exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503,
                            content={"detail": "存储暂时不可用，请稍后再试"})
    app.add_exception_handler(sqlite3.DatabaseError, _sqlite_handler)

    # R230i（R21-P1-8）：OS 级存储失败（data/ 被普通文件占位的
    # FileExistsError、ENOSPC、EACCES）此前穿透成裸 500 英文上屏——
    # 固定中文，不让 str(exc) 的英文 errno 漏出。FileNotFoundError 是
    # OSError 子类但更具体的处理器先命中，「索引缺失…」人话不受影响。
    async def _os_handler(_request: Request,
                          exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503,
                            content={"detail": "存储暂时不可用，请稍后再试"})
    app.add_exception_handler(OSError, _os_handler)

    # R230i（R21-P3）：未知路由/静态文件的 404 是 FastAPI 默认英文
    # {"detail":"Not Found"}——翻中文；业务端点自己抛的 HTTPException
    # 已带中文 detail，原样放行不覆盖。
    async def _http_handler(_request: Request,
                            exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if exc.status_code == 404 and detail == "Not Found":
            detail = "要找的内容不在了"
        # R2508（审-P2）：框架直出英文 detail 的另两条漏口——
        # FastAPI 路由层「解析 body 失败」400 与 405 方法不允许。
        elif detail == "There was an error parsing the body":
            detail = "请求体解析不了，检查一下格式再发"
        elif exc.status_code == 405 and detail == "Method Not Allowed":
            detail = "这个接口不支持该请求方法"
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": detail},
                            headers=getattr(exc, "headers", None))
    app.add_exception_handler(StarletteHTTPException, _http_handler)

    # R230a-38（R15-P1-2）：int64 溢出（thread_id=1e20 等）在 sqlite 绑定时
    # 抛 OverflowError——非 DatabaseError 子类，此前穿透成 500（≥9 端点）。
    # 不用 STATUS_MAP：str(exc) 是英文实现细节，会漏上屏。
    async def _overflow_handler(_request: Request,
                                exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400,
                            content={"detail": "参数超出可接受范围"})
    app.add_exception_handler(OverflowError, _overflow_handler)

    # R2506（审-F4）：递归 JSON body（~950 层嵌套）在 json.loads 的递归
    # 解析里抛 RecursionError——非 JSONDecodeError 子类，
    # RequestValidationError 处理器接不住，此前穿透成英文 500。
    # 与 shape 错同档 422。
    async def _recursion_handler(_request: Request,
                                 exc: Exception) -> JSONResponse:
        # R2508：GET 上的存储 JSON 递归同走此映射——不说「请求体」。
        return JSONResponse(status_code=422,
                            content={"detail": "数据嵌套太深，处理不了"})
    app.add_exception_handler(RecursionError, _recursion_handler)

    # R2508（审-P0）：孤代理 \ud800-\udfff 走 dict/Any 备份值绕过
    # pydantic str 校验 → sqlite 绑定 / JSONResponse 序列化双双
    # 炸 UnicodeEncodeError（UnicodeError 子类、非 DatabaseError）——
    # 此前穿透成英文裸 500。写面已逐点剥除，本映射是漏面兜底 422。
    async def _unicode_handler(_request: Request,
                               exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content={"detail": "有特殊字符处理不了，换个写法再试"})
    app.add_exception_handler(UnicodeError, _unicode_handler)

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
            # ctx 里可能塞着嵌套异常对象（value_error 的 ctx.error 是
            # ValidationError 实例）——JSONResponse 序列化会炸成 500。
            if "ctx" in e:
                e["ctx"] = {k: str(v) for k, v in
                            dict(e["ctx"]).items()}
            # R230g（R19-P3-3）：body 不是合法 JSON 时 Starlette 给英文
            # msg（"JSON decode error"）——与全站中文 detail 口径统一。
            if e.get("type") == "json_invalid":
                e["msg"] = "请求体不是合法的 JSON"
            errs.append(e)
        return JSONResponse(status_code=422, content={"detail": errs})
    app.add_exception_handler(RequestValidationError, _validation_handler)
