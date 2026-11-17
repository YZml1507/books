# -*- coding: utf-8 -*-
"""R28-b：登录/注册分模式 + 账号昵称与档案名合并。"""
import io, sys
H = "/opt/books/app/web/static/index.html"
J = "/opt/books/app/web/static/app.js"
with io.open(H, "r", encoding="utf-8") as f:
    h = f.read()
with io.open(J, "r", encoding="utf-8") as f:
    j = f.read()


def rep(tag, old, new, n=1):
    global h, j
    tgt = h if tag.startswith("H:") else j
    key = tag[2:] if tag.startswith("H:") else tag
    if tgt.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, tgt.count(old)))
    if new and new in tgt:
        sys.exit("FAIL[%s] 已打过" % tag)
    tgt = tgt.replace(old, new, n)
    if tag.startswith("H:"):
        h = tgt
    else:
        j = tgt


# ---------- HTML：表单改成分模式 ----------
OLD_FORM = (
    '        <div class="acct-form" id="acctForm">\n'
    '          <input id="acctNick" type="text" maxlength="24" autocomplete="off"\n'
    '                 placeholder="给自己起个名（昵称）">\n'
    '          <input id="acctPass" type="password" maxlength="64" autocomplete="off"\n'
    '                 placeholder="口令码（至少 6 位）">\n')
rep("H:form-top", OLD_FORM,
    '        <div class="acct-form" id="acctForm">\n'
    '          <!-- R28-b（用户直报「登录和注册应该点击不同的按钮显示要填的东西\n'
    '               应该不一样才对呀，你这个怎么一样」）：改成显式分段控件——\n'
    '               登录只要昵称+口令码，注册才收生辰和性别。原先两套字段\n'
    '               平铺在一张表上，登录的人也被告知要填生辰。 -->\n'
    '          <div class="acct-tabs" role="tablist" aria-label="登录或注册">\n'
    '            <button type="button" class="acct-tab is-on" id="acctTabLogin"\n'
    '                    role="tab" aria-selected="true">登录</button>\n'
    '            <button type="button" class="acct-tab" id="acctTabReg"\n'
    '                    role="tab" aria-selected="false">注册</button>\n'
    '          </div>\n'
    '          <input id="acctNick" type="text" maxlength="24" autocomplete="off"\n'
    '                 placeholder="你的昵称">\n'
    '          <input id="acctPass" type="password" maxlength="64" autocomplete="off"\n'
    '                 placeholder="口令码（至少 6 位）">\n')

# 生辰 / 性别整块包上 hidden 容器
rep("H:birth-wrap",
    '          <div class="acct-birth">\n'
    '            <span class="acct-birth-lab">生辰（礼物照这个包，随时能改）</span>',
    '          <div class="acct-birth" id="acctBirthBox" hidden>\n'
    '            <span class="acct-birth-lab">生辰（礼物照这个包，随时能改）</span>')

OLD_BTNS = (
    '          <div class="acct-btns">\n'
    '            <div class="acct-gender">\n'
    '              <span class="acct-birth-lab">你是</span>\n'
    '              <div class="acct-gender-row" role="group" aria-label="性别">\n'
    '                <button type="button" class="acct-gender-btn is-on" id="acctGF" data-g="f" aria-pressed="true">女生</button>\n'
    '                <button type="button" class="acct-gender-btn" id="acctGM" data-g="m" aria-pressed="false">男生</button>\n'
    '              </div>\n'
    '              <span class="acct-gender-note">小满会按这个给你分一张头像，随机不重样</span>\n'
    '            </div>\n'
    '            <button id="acctRegister" type="button" class="ghost">注册</button>\n'
    '            <button id="acctLogin" type="button" class="ghost">登录</button>\n'
    '          </div>\n'
    '          <div class="acct-tip">口令码记个牢的就好。注册即同步一份备份到云端——换设备登录同名账号，生辰和数据都给你拉回来。</div>\n')
rep("H:btns", OLD_BTNS,
    '          <div class="acct-gender" id="acctGenderBox" hidden>\n'
    '            <span class="acct-birth-lab">你是</span>\n'
    '            <div class="acct-gender-row" role="group" aria-label="性别">\n'
    '              <button type="button" class="acct-gender-btn is-on" id="acctGF" data-g="f" aria-pressed="true">女生</button>\n'
    '              <button type="button" class="acct-gender-btn" id="acctGM" data-g="m" aria-pressed="false">男生</button>\n'
    '            </div>\n'
    '            <span class="acct-gender-note">小满会按这个给你分一张头像，随机不重样</span>\n'
    '          </div>\n'
    '          <!-- 主操作唯一化：原先「注册」「登录」两颗并排，用户每次都要先\n'
    '               猜哪颗是干什么的。现在一颗，文案跟着模式走。 -->\n'
    '          <button id="acctGo" type="button" class="acct-go">登录</button>\n'
    '          <div class="acct-tip" id="acctTip">口令码记个牢的就好。同名账号换设备登录，生辰和数据都给你拉回来。</div>\n'
    '          <!-- 原两颗按钮保留在 DOM 里（隐藏）——app.js 的既有绑定不动，\n'
    '               #acctGo 只负责按当前模式去点对应那颗。 -->\n'
    '          <div id="acctLegacyBtns" hidden>\n'
    '            <button id="acctRegister" type="button" class="ghost">注册</button>\n'
    '            <button id="acctLogin" type="button" class="ghost">登录</button>\n'
    '          </div>\n')

# ---------- JS：模式切换 + 昵称同步 ----------
rep("_acctMode",
    "      document.getElementById('acctRegister')\n"
    "        .addEventListener('click', async function () {\n"
    "          var f = _readFields();",
    "      /* R28-b：登录/注册分模式。_acctMode 'login' | 'reg'。 */\n"
    "      var _acctMode = 'login';\n"
    "      function _acctSetMode(m) {\n"
    "        _acctMode = m;\n"
    "        var _L = document.getElementById('acctTabLogin');\n"
    "        var _R = document.getElementById('acctTabReg');\n"
    "        var _B = document.getElementById('acctBirthBox');\n"
    "        var _G = document.getElementById('acctGenderBox');\n"
    "        var _GO = document.getElementById('acctGo');\n"
    "        var _T = document.getElementById('acctTip');\n"
    "        if (_L) { _L.classList.toggle('is-on', m === 'login'); _L.setAttribute('aria-selected', m === 'login' ? 'true' : 'false'); }\n"
    "        if (_R) { _R.classList.toggle('is-on', m === 'reg'); _R.setAttribute('aria-selected', m === 'reg' ? 'true' : 'false'); }\n"
    "        if (_B) _B.hidden = (m !== 'reg');\n"
    "        if (_G) _G.hidden = (m !== 'reg');\n"
    "        if (_GO) _GO.textContent = (m === 'reg' ? '注册' : '登录');\n"
    "        if (_T) _T.textContent = (m === 'reg'\n"
    "          ? '口令码记个牢的就好。注册即同步一份备份到云端——换设备登录同名账号，生辰和数据都给你拉回来。'\n"
    "          : '口令码记个牢的就好。同名账号换设备登录，生辰和数据都给你拉回来。');\n"
    "        try { localStorage.setItem('xm_acct_mode', m); } catch (eM) {}\n"
    "      }\n"
    "      try {\n"
    "        var _m0 = localStorage.getItem('xm_acct_mode');\n"
    "        if (_m0 === 'reg' || _m0 === 'login') _acctSetMode(_m0);\n"
    "      } catch (eM0) {}\n"
    "      var _tL = document.getElementById('acctTabLogin');\n"
    "      var _tR = document.getElementById('acctTabReg');\n"
    "      if (_tL) _tL.addEventListener('click', function () { _acctSetMode('login'); });\n"
    "      if (_tR) _tR.addEventListener('click', function () { _acctSetMode('reg'); });\n"
    "      var _go = document.getElementById('acctGo');\n"
    "      if (_go) _go.addEventListener('click', function () {\n"
    "        var _b = document.getElementById(_acctMode === 'reg' ? 'acctRegister' : 'acctLogin');\n"
    "        if (_b) _b.click();\n"
    "      });\n"
    "      /* R28-b：账号昵称是登录身份，作为唯一真源；档案名 me.n 跟随它。\n"
    "       * 用户直报「排盘历史是小静，个人账号是小霖（我以小静身份注册登录，\n"
    "       * 但是我后面又改了名字，可能没有一起同步）」——两个名字各存一份、\n"
    "       * 谁也不通知谁，就是这个困惑的根。 */\n"
    "      function _syncMeName(nick) {\n"
    "        try {\n"
    "          var _m = _meGet('me') || {};\n"
    "          if (nick && _m.n !== nick) _meSave('me', { n: nick });\n"
    "        } catch (eSN) {}\n"
    "      }\n"
    "      window.__syncMeName = _syncMeName;\n"
    "      document.getElementById('acctRegister')\n"
    "        .addEventListener('click', async function () {\n"
    "          var f = _readFields();")

# 登录成功后同步昵称（云端拉回可能带回旧名字）
rep("sync-login",
    "              await _pull();\n",
    "              await _pull();\n"
    "              _syncMeName(f.n);\n")

with io.open(H, "w", encoding="utf-8") as f:
    f.write(h)
with io.open(J, "w", encoding="utf-8") as f:
    f.write(j)
print("OK")
