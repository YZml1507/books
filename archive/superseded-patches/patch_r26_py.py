# -*- coding: utf-8 -*-
import io, sys
PY = "/opt/books/app/web/app.py"
with io.open(PY, "r", encoding="utf-8") as f:
    p = f.read()
OLD = """    application.add_middleware(GZipMiddleware, minimum_size=1000)"""
NEW = """    application.add_middleware(GZipMiddleware, minimum_size=1000)
    # R26（用户裁决「登录哪个账户就应该显示哪个账户里面的排盘历史」）：
    # 台账此前无账号维度——所有登录用户看到同一份。账号体系无状态、
    # 没有会话可依托，归属由前端用 X-Books-Owner 头带上，这里设进
    # 请求级上下文变量，paipan_history 的读写全按它切。
    @application.middleware("http")
    async def _paipan_owner(request, call_next):
        from guji import paipan_history as _ph
        _ph.set_owner(request.headers.get("x-books-owner", ""))
        return await call_next(request)"""
if p.count(OLD) != 1:
    sys.exit("FAIL py count=%d" % p.count(OLD))
if "_paipan_owner" in p:
    sys.exit("FAIL py 已打过")
p = p.replace(OLD, NEW, 1)
with io.open(PY, "w", encoding="utf-8") as f:
    f.write(p)
print("app.py OK")
