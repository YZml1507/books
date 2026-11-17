import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """      function _saveCreds(n, p) {
        try {
          localStorage.setItem(_KEY, JSON.stringify({ n: n, p: p }));
        } catch (e) {}
      }"""
NEW = """      function _saveCreds(n, p) {
        try {
          localStorage.setItem(_KEY, JSON.stringify({ n: n, p: p }));
        } catch (e) {}
        /* R21（用户直报）：登录闸挂在唯一的凭据写入口上——注册/登录/退出
         * 三条路全都经 _saveCreds，在这里过闸不会漏（实测 __acctCredsChanged
         * 只被跨 tab 的 storage 事件触发，同 tab 注册根本不走它）。 */
        if (typeof _authGate === 'function') _authGate();
      }"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: anchor count=%d" % a.count(OLD))
if "登录闸挂在唯一的凭据写入口" in a:
    sys.exit("FAIL: 已打过")
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: _saveCreds 过闸")
