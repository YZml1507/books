import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """  var c = null;
  try { c = _creds(); } catch (e) {}
  var n = (c && c.n) ? String(c.n) : '';"""
NEW = """  /* 同 _authGate：_creds() 在账号 IIFE 里，模块作用域调不到，
   * try/catch 会把 ReferenceError 静默吞成「永远未登录」。直读同一把键。 */
  var c = null;
  try {
    var _cj = JSON.parse(localStorage.getItem('xmaccount') || 'null');
    c = (_cj && _cj.n && _cj.p) ? _cj : null;
  } catch (e) {}
  var n = (c && c.n) ? String(c.n) : '';"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: anchor count=%d" % a.count(OLD))
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: _dailyAcctText 改直读")
