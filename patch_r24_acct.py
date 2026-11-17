# -*- coding: utf-8 -*-
import io, sys
HTML="/opt/books/app/web/static/index.html"
JS="/opt/books/app/web/static/app.js"
def rd(p):
    with io.open(p,"r",encoding="utf-8") as f: return f.read()
def wr(p,s):
    with io.open(p,"w",encoding="utf-8") as f: f.write(s)
h=rd(HTML)

# --- 1) #acctSlot 从排盘历史里挪走 ---
O1 = """      <!-- R3358：轻账号（昵称+口令码，不要邮箱/手机）——注册/登录后
           备份自动同步到云端，换设备/无痕模式登录同名账号即可拉回。
           口令码没有找回渠道，忘了就是没了（前端明说）。 -->
      <div id="acctSlot"></div>
"""
N1 = """      <!-- R24（用户原话「不把整个历史删除」+ 账号信息要独立）：
           #acctSlot 已挪去 #view-account——账号/生辰/头像不再寄生在
           排盘历史里，历史只留历史自己的东西。 -->
"""
if h.count(O1)!=1: sys.exit("FAIL O1 count=%d"%h.count(O1))
h=h.replace(O1,N1,1)

# --- 2) 新增 #view-account 视图（含 acctSlot + 空态提示） ---
O2 = '  <div class="view" id="view-history">'
N2 = """  <!-- R24（用户要求）：账号/个人信息从排盘历史里独立成视图——
       历史整块保留（用户明确说不删），只把账号面提出来。 -->
  <div class="view" id="view-account">
    <div class="card">
      <h2><span aria-hidden="true">🧸</span> 我的账号 <span class="card-sub">生辰 · 头像 · 云端备份</span></h2>
      <div id="acctSlot"></div>
      <p class="acct-empty" id="acctEmpty">还没登录——回首页登录后，你的生辰、头像和云端备份就摆在这儿。</p>
    </div>
  </div>
""" + O2
if h.count(O2)!=1: sys.exit("FAIL O2 count=%d"%h.count(O2))
h=h.replace(O2,N2,1)

# --- 3) 首页加「我的账号」入口（排在排盘历史旁边） ---
O3 = """      <img class="func-icon-img" loading="lazy" decoding="async" data-view="history" src="/static/cream/cream-icon-history.jpg" alt="" width="56" height="56" onerror="this.classList.add('is-missing')"><div class="func-name">排盘历史</div><div class="func-desc">翻翻看过的盘 · 可导出</div>
    </div>
"""
N3 = O3 + """    <!-- R24（用户要求）：账号/个人信息独立入口——不再埋在排盘历史里 -->
    <div class="func-card func-entry" data-view="account" role="button" tabindex="0" aria-label="我的账号">
      <img class="func-icon-img" loading="lazy" decoding="async" data-view="account" src="/static/avatars/avatar-f3.jpg" alt="" width="56" height="56" onerror="this.classList.add('is-missing')"><div class="func-name">我的账号</div><div class="func-desc">生辰 · 头像 · 云端备份</div>
    </div>
"""
if h.count(O3)!=1: sys.exit("FAIL O3 count=%d"%h.count(O3))
h=h.replace(O3,N3,1)
wr(HTML,h); print("index.html OK")

# --- 4) app.js：账号卡归位/离开时切空态提示 ---
a=rd(JS)
O4 = """  if (on) {
    if (slot && card.parentNode !== slot) slot.appendChild(card);
    wall.hidden = true;
    document.body.classList.remove('auth-locked');
  } else {
    if (card.parentNode !== wall) wall.appendChild(card);"""
N4 = """  var _ae = el('acctEmpty');
  if (on) {
    if (slot && card.parentNode !== slot) slot.appendChild(card);
    wall.hidden = true;
    document.body.classList.remove('auth-locked');
    /* R24：账号卡归位到 #view-account 的 #acctSlot，空态提示同步收起来 */
    if (_ae) _ae.hidden = true;
  } else {
    if (card.parentNode !== wall) wall.appendChild(card);
    if (_ae) _ae.hidden = false;"""
if a.count(O4)!=1: sys.exit("FAIL O4 count=%d"%a.count(O4))
a=a.replace(O4,N4,1)
wr(JS,a); print("app.js OK")
