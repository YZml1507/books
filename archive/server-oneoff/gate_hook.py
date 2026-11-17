import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """      window.__acctCredsChanged = function (oldRaw) {
        try {"""
NEW = """      window.__acctCredsChanged = function (oldRaw) {
        /* R21（用户直报）：凭据一有变动就过登录闸——注册成功/登录成功/
         * 退出登录/跨 tab 换主，四条路全经这里，比在各 handler 里补调用
         * 更不容易漏（实测注册成功后 _acctRender 不走，闸就不收）。 */
        if (typeof _authGate === 'function') _authGate();
        try {"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: anchor count=%d" % a.count(OLD))
if "凭据一有变动就过登录闸" in a:
    sys.exit("FAIL: 已打过")
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: __acctCredsChanged 过闸")
