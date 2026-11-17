# -*- coding: utf-8 -*-
import io, sys
JS = "/opt/books/app/web/static/app.js"
PY = "/opt/books/app/web/app.py"

with io.open(JS, "r", encoding="utf-8") as f:
    a = f.read()


def rep(tag, old, new, n=1):
    global a
    if a.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, a.count(old)))
    if new and new in a:
        sys.exit("FAIL[%s] 已打过" % tag)
    a = a.replace(old, new, n)


# 1) 公共注入器（放在 api() 之前，两个 fetch 出口共用）
rep("hdr",
    "async function api(path, options) {\n  options = options || {};",
    "/* R26：排盘历史按登录账户归属——后端按 X-Books-Owner 过滤台账。\n"
    " * 账号体系无状态（每次请求重新验昵称+口令），没有会话可依托，\n"
    " * 归属只能由前端带上昵称。未登录时不带头，后端按空归属查。 */\n"
    "function _ownerHdr(h) {\n"
    "  h = h || {};\n"
    "  try {\n"
    "    var c = JSON.parse(localStorage.getItem('xmaccount') || 'null');\n"
    "    if (c && c.n) h['X-Books-Owner'] = String(c.n);\n"
    "  } catch (e) {}\n"
    "  return h;\n"
    "}\n"
    "async function api(path, options) {\n"
    "  options = options || {};\n"
    "  options.headers = _ownerHdr(options.headers);")

# 2) phFetch 同一处理
rep("phfetch",
    "  async function phFetch(url, opts) {",
    "  async function phFetch(url, opts) {\n"
    "    opts = opts || {};\n"
    "    opts.headers = _ownerHdr(opts.headers);")

with io.open(JS, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js OK")

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
