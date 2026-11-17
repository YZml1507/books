import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """  var c = null;
  try { c = _creds(); } catch (eC) {}
  var on = !!c;
  if (on) {
    if (slot && card.parentNode !== slot) slot.appendChild(card);"""
NEW = """  /* 不能调 _creds()——它住在账号 IIFE 里，模块作用域看不见，调用会抛
   * ReferenceError 并被上面的 try/catch 静默吞掉，c 恒为 null，闸永远
   * 不收（本轮实测：注册成功、凭据已落盘 xmaccount，墙就是不隐藏）。
   * 这里按同一把键、同一份 {n,p} 格式直读，与 _creds 判据保持一致。 */
  var c = null;
  try {
    var _cj = JSON.parse(localStorage.getItem('xmaccount') || 'null');
    c = (_cj && _cj.n && _cj.p) ? _cj : null;
  } catch (eC) {}
  var on = !!c;
  if (on) {
    if (slot && card.parentNode !== slot) slot.appendChild(card);"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: anchor count=%d" % a.count(OLD))
if "不能调 _creds()" in a:
    sys.exit("FAIL: 已打过")
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: _authGate 改直读凭据")
