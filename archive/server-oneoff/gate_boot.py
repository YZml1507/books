import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """function init() {
  applyTheme(uiTheme());       // 003 判据 12：加载时应用已保存的主题"""
NEW = """function init() {
  applyTheme(uiTheme());       // 003 判据 12：加载时应用已保存的主题
  /* R21（用户直报）：全站登录闸放在 init 第一件事——已登录则收起登录墙、
   * 账号卡归位；未登录则墙一直在（HTML 里默认可见，fail-closed）。
   * 必须早于任何视图渲染，否则会闪一下裸站。 */
  if (typeof _authGate === 'function') _authGate();"""
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if a.count(OLD) != 1:
    sys.exit("FAIL: init anchor count=%d" % a.count(OLD))
a = a.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: init() 首行过闸")
