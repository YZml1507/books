# -*- coding: utf-8 -*-
"""R32：账号卡从六个按钮砍成两个——退出登录 / 注销账户。
用户原话：「六个按钮完全可以改成…一个叫退出登录一个叫注销账户，明白吗，
那个导入导出完全不需要…用户直接进入网站然后登录他的用户名，那么他的数据
就自然而然的自己就回来了，这就是我要设计的一个登录注册系统」。

砍掉的四个（立刻同步/从云端拉回/导出数据/导入备份）都是自动通路的重复面：
登录即 _pull()（R29 已修）、离页即 _push()。保留它们只会让人以为
「数据不会自己回来，得我手动搬」——正好是用户指出的设计错觉。"""
import io, sys

# ---------------- index.html ----------------
H = "/opt/books/app/web/static/index.html"
h = io.open(H, encoding="utf-8").read()


def hrep(tag, old, new):
    global h
    if h.count(old) != 1:
        sys.exit("FAIL[%s] %d" % (tag, h.count(old)))
    if new and new in h:
        sys.exit("FAIL[%s] dup" % tag)
    h = h.replace(old, new, 1)


hrep("logged",
     '        <div class="acct-logged" id="acctLogged" hidden>\n'
     '          <div class="acct-line">已登 <b id="acctWho"></b> · <span id="acctLastSync">还没同步过</span></div>\n'
     '          <div class="btn-group">\n'
     '            <div class="btn-group-lab">☁️ 和云端互传<span>存在服务器上 · 换设备能找回</span></div>\n'
     '            <div class="acct-btns">\n'
     '              <button id="acctSyncNow" type="button" class="ghost">立刻同步<small>本机 → 云端</small></button>\n'
     '              <button id="acctPull" type="button" class="ghost">从云端拉回<small>云端 → 本机</small></button>\n'
     '            </div>\n'
     '          </div>\n'
     '          <div class="btn-group">\n'
     '            <div class="btn-group-lab">⚙️ 登录状态</div>\n'
     '            <div class="acct-btns">\n'
     '              <button id="acctLogout" type="button" class="ghost">退出<small>只登出，不动任何数据</small></button>\n'
     '            </div>\n'
     '          </div>\n'
     '          <div class="acct-tip">备份会在这台设备退出页面时自动同步；换新设备登录同名账号点「从云端拉回」。</div>\n'
     '        </div>\n',
     '        <!-- R32：登录后只剩两个动作——退出 / 注销。数据通路全自动：\n'
     '             登录即 _pull()（R29），离页即 _push()。原先的「立刻同步」\n'
     '             「从云端拉回」「导出数据」「导入备份」是自动通路的手动重复面，\n'
     '             留着会让人以为数据不会自己回来、得手动搬——已全部撤掉。 -->\n'
     '        <div class="acct-logged" id="acctLogged" hidden>\n'
     '          <div class="acct-line">已登 <b id="acctWho"></b> · <span id="acctLastSync">还没同步过</span></div>\n'
     '          <div class="acct-tip">数据跟着账号走：换设备登录同名账号，档案和记录自己就回来了；离开页面时自动存上云端。不用手动导入导出。</div>\n'
     '          <div class="btn-group">\n'
     '            <div class="btn-group-lab">⚙️ 账号</div>\n'
     '            <div class="acct-btns">\n'
     '              <button id="acctLogout" type="button" class="ghost">退出登录<small>只登出，数据不动</small></button>\n'
     '              <button id="historyWipe" type="button" class="ghost">注销账户<small>档案/记录/云端一起删，救不回</small></button>\n'
     '            </div>\n'
     '          </div>\n'
     '        </div>\n')

# 整个 #myTools 撤掉（备份/导入/忘掉 三个按钮 + 说明）
_i0 = h.find('      <!-- R28：备份/清理是全量数据工具')
if _i0 < 0:
    sys.exit("FAIL[myTools-head]")
_i1 = h.find('      <div class="mem-card" id="memoryCard">', _i0)
if _i1 < 0:
    sys.exit("FAIL[myTools-tail]")
h = (h[:_i0] +
     '      <!-- R32：#myTools（备份我的数据/导入备份/忘掉我的数据）整块撤掉——\n'
     '           导出导入是账号通路的重复面；「忘掉」已并入账号卡的「注销账户」\n'
     '           （连账号带云端备份一起删，见 R31-A）。 -->\n' +
     h[_i1:])

io.open(H, "w", encoding="utf-8").write(h)
print("html OK")

# ---------------- app.js：补空值保护 ----------------
J = "/opt/books/app/web/static/app.js"
j = io.open(J, encoding="utf-8").read()


def jrep(tag, old, new):
    global j
    if j.count(old) != 1:
        sys.exit("FAIL[%s] %d" % (tag, j.count(old)))
    if new in j:
        sys.exit("FAIL[%s] dup" % tag)
    j = j.replace(old, new, 1)


# 按钮已从 DOM 撤掉（R32），这两个绑定原先没有空值保护，会直接抛错
jrep("sync",
     "      document.getElementById('acctSyncNow')\n"
     "        .addEventListener('click', function () { _push(true); });\n",
     "      /* R32：按钮已撤，补空值保护——不然这里直接抛错，\n"
     "         把后面 acctPull/acctLogout 的绑定一起带走。 */\n"
     "      var _sn = document.getElementById('acctSyncNow');\n"
     "      if (_sn) _sn.addEventListener('click', function () { _push(true); });\n")
jrep("pull",
     "      document.getElementById('acctPull')\n"
     "        .addEventListener('click', function () { _pull(); });\n",
     "      var _pl = document.getElementById('acctPull');\n"
     "      if (_pl) _pl.addEventListener('click', function () { _pull(); });\n")

io.open(J, "w", encoding="utf-8").write(j)
print("js OK")
