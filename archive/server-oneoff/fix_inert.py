import io, sys
APP = "/opt/books/app/web/static/app.js"
OLD = """      Array.prototype.forEach.call(_card0.children, function (c) {
        if (c !== _cov && !c.hasAttribute('inert')) c.setAttribute('inert', '');
      });"""
NEW = """      Array.prototype.forEach.call(_card0.children, function (c) {
        /* R20（用户直报）：顶行豁免 inert——账号钮必须在封面没拆时就点
         * 得到，否则最需要注册的新用户反而被挡住（实测 click 直接报
         * "element is inert"，账号入口形同虚设）。顶行里只有账号钮是
         * 可交互的（问候/日期/礼盒图都不是控件），整行豁免无副作用；
         * 封面点击门槛 _tryReveal 一行未动。 */
        if (c !== _cov && !c.hasAttribute('inert') &&
            !(c.classList && c.classList.contains('daily-top')))
          c.setAttribute('inert', '');
      });"""
with io.open(APP, "r", encoding="utf-8") as f:
    s = f.read()
n = s.count(OLD)
if n != 1:
    sys.exit("FAIL: anchor count=%d" % n)
if "顶行豁免 inert" in s:
    sys.exit("FAIL: 已打过")
s = s.replace(OLD, NEW, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(s)
print("app.js PATCHED (R20-7 顶行豁免 inert)")
