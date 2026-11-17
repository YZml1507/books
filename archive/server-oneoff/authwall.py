import io, sys
IDX = "/opt/books/app/web/static/index.html"
CSS = "/opt/books/app/web/static/styles.css"
APP = "/opt/books/app/web/static/app.js"

# ---------- 1) index.html：把 #accountCard 从排盘历史搬进 #authWall ----------
with io.open(IDX, "r", encoding="utf-8") as f:
    h = f.read()
START = '<div class="acct-card" id="accountCard">'
if h.count(START) != 1:
    sys.exit("FAIL: accountCard start count=%d" % h.count(START))
i = h.index(START)
# 括号配平找块尾
d = 0
j = i
while True:
    d += h.count("<div", j, j + 4)
    d -= h.count("</div>", j, j + 6)
    if d == 0:
        j = h.index(">", j) + 1
        break
    j = h.index(">", j) + 1
BLOCK = h[i:j]
h = h[:i] + '<div id="acctSlot"></div>' + h[j:]
WALL = ('<!-- R21（用户直报）：全站登录墙——「必须要登录才可以进入到网站里面，\n'
        '     然后才有他的个人信息」。默认可见，只有 JS 确认已登录才隐藏\n'
        '     （fail-closed：脚本挂了用户看到的也是登录面板，不是裸站）。\n'
        '     登录成功后 #accountCard 归位回排盘历史的 #acctSlot。 -->\n'
        '<div class="auth-wall" id="authWall">\n' + BLOCK + '\n</div>\n\n')
if "<body>" not in h:
    sys.exit("FAIL: no <body>")
h = h.replace("<body>", "<body>\n" + WALL, 1)
with io.open(IDX, "w", encoding="utf-8") as f:
    f.write(h)
print("index.html: accountCard -> #authWall，原位留 #acctSlot")

# ---------- 2) styles.css ----------
with io.open(CSS, "r", encoding="utf-8") as f:
    c = f.read()
if ".auth-wall{" in c:
    sys.exit("FAIL: css 已打过")
CSS_OLD = "/* R20（用户直报）：日卡顶行账号钮"
if c.count(CSS_OLD) != 1:
    sys.exit("FAIL: css anchor count=%d" % c.count(CSS_OLD))
CSS_NEW = """/* R21（用户直报）：全站登录墙——未登录时 #accountCard 提到这里当全屏
 * 登录面板，主区被 JS inert + body 锁滚。登录成功即隐藏并归位。 */
.auth-wall{position:fixed; inset:0; z-index:99999; display:flex;
  align-items:center; justify-content:center; padding:20px 16px;
  background:var(--bg); overflow-y:auto; -webkit-overflow-scrolling:touch;}
.auth-wall[hidden]{display:none;}
.auth-wall #accountCard{width:100%; max-width:430px; margin:0 auto;
  box-shadow:0 12px 40px rgba(0,0,0,.10);}
body.auth-locked{overflow:hidden;}
""" + CSS_OLD
c = c.replace(CSS_OLD, CSS_NEW, 1)
with io.open(CSS, "w", encoding="utf-8") as f:
    f.write(c)
print("styles.css: .auth-wall")

# ---------- 3) app.js ----------
with io.open(APP, "r", encoding="utf-8") as f:
    a = f.read()
if "_authGate" in a:
    sys.exit("FAIL: app.js 已打过")
ANCH = "/* R20（用户直报）：账号钮文案"
if a.count(ANCH) != 1:
    sys.exit("FAIL: app.js anchor count=%d" % a.count(ANCH))
GATE = """/* R21（用户直报）：全站登录墙——不登录看不到任何内容。
 * 做法是把 #accountCard 这个既有节点提到 #authWall 里当全屏登录面板，
 * 而不是复制一份表单：卡内注册/登录/同步/拉回/退出全部 getElementById
 * 绑定，复制必撞 ID。登录成功后归位回 #acctSlot（排盘历史视图内）。
 * 主区 inert 用 body 逐子节点打标，比 inertTree 更硬——连侧栏/模态/
 * FAB 一起锁，不留 Tab 穿透。 */
function _authGate() {
  var wall = el('authWall'), card = el('accountCard'), slot = el('acctSlot');
  if (!wall || !card) return;
  var c = null;
  try { c = _creds(); } catch (eC) {}
  var on = !!c;
  if (on) {
    if (slot && card.parentNode !== slot) slot.appendChild(card);
    wall.hidden = true;
    document.body.classList.remove('auth-locked');
  } else {
    if (card.parentNode !== wall) wall.appendChild(card);
    wall.hidden = false;
    document.body.classList.add('auth-locked');
  }
  Array.prototype.forEach.call(document.body.children, function (n) {
    if (n === wall) return;
    try { n.inert = !on; } catch (eI) {}
  });
  if (typeof _dailyAcctText === 'function') _dailyAcctText();
}

"""
a = a.replace(ANCH, GATE + ANCH, 1)
# _acctRender 收尾：登录态每次变化都过闸（注册/登录/退出/跨 tab 换号全覆盖）
REND = "        if (typeof _dailyAcctText === 'function') _dailyAcctText();\n      }\n      window.__acctRender = _acctRender;"
if a.count(REND) != 1:
    sys.exit("FAIL: _acctRender tail count=%d" % a.count(REND))
a = a.replace(REND, "        if (typeof _dailyAcctText === 'function') _dailyAcctText();\n"
                    "        if (typeof _authGate === 'function') _authGate();\n"
                    "      }\n      window.__acctRender = _acctRender;", 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js: _authGate + _acctRender 收尾过闸")
