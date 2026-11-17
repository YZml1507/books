# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag,old,new,n=1):
    global a
    if a.count(old)!=n: sys.exit("FAIL[%s] count=%d"%(tag,a.count(old)))
    if new in a: sys.exit("FAIL[%s] 已打过"%tag)
    a=a.replace(old,new,n)

# --- A) 账号 IIFE 内加 _avatarOf() 兜底 + 暴露全局 ---
O_A = """      function _pickAvatar(g) {
        var _p = _AVATAR_POOL[g] || _AVATAR_POOL.f;
        return _p[Math.floor(Math.random() * _p.length)];
      }"""
N_A = """      function _pickAvatar(g) {
        var _p = _AVATAR_POOL[g] || _AVATAR_POOL.f;
        return _p[Math.floor(Math.random() * _p.length)];
      }
      /* R25（用户直报「首页用户名旁边没有头像」）：me.av 会缺——老账号
       * 注册时还没有这功能、云端拉回缺字段、或用户手清过。缺了就按
       * 「昵称+性别」确定性兜底一张：同一个人永远同一张，不会每次刷新
       * 换脸；也别让头像位空着假装有头像。 */
      function _avatarOf() {
        var _av = '', _n = '', _g = 'f';
        try {
          var _m = JSON.parse(localStorage.getItem('me') || 'null');
          if (_m) {
            _av = _m.av ? String(_m.av).replace(/[^a-z0-9.\\-_]/gi, '') : '';
            _n = _m.n ? String(_m.n) : '';
            if (_m.g === 'm' || _m.g === 'f') _g = _m.g;
          }
        } catch (e) {}
        if (_av) return _av;
        var _pool = _AVATAR_POOL[_g] || _AVATAR_POOL.f;
        var _h = 0;
        for (var i = 0; i < _n.length; i++) _h = (_h * 31 + _n.charCodeAt(i)) & 0x7fffffff;
        return _pool[_h % _pool.length];
      }
      /* 档案行（另一作用域）也要用同一把兜底，挂全局 */
      try { window.__avatarOf = _avatarOf; } catch (eW) {}"""
rep("A", O_A, N_A)

# --- B) _acctFace 用兜底（老账号也显示） ---
O_B = """        var _im = document.getElementById('acctFace');
        var _av = null;
        try {
          var _m = JSON.parse(localStorage.getItem('me') || 'null');
          _av = _m && _m.av;
        } catch (eAv) {}
        if (!_im) return;"""
N_B = """        var _im = document.getElementById('acctFace');
        /* R25：老账号没有 me.av 也要有脸——走 _avatarOf() 确定性兜底 */
        var _av = _avatarOf();
        if (!_im) return;"""
rep("B", O_B, N_B)

# --- C) 档案行：头像 26px→40px、去掉多余 🧸、走兜底 ---
O_C = """  var txt = '🧸 ' + (me.n ? me.n + ' 的小档案' : '你的小档案') +"""
N_C = """  /* R25（用户直报）：头像才是身份标识，🧸 emoji 是重复装饰——去掉，
   * 头像同时放大到 40px（原来 26px 在近千像素宽的档案行里等于没有）。 */
  var txt = (me.n ? me.n + ' 的小档案' : '你的小档案') +"""
rep("C", O_C, N_C)

O_D = """  var _av = me.av ? String(me.av).replace(/[^a-z0-9.\\-_]/gi, '') : '';
  box.innerHTML = (_av ? '<img class="daily-me-face" src="/static/avatars/' +
      _av + '" alt="">' : '') +"""
N_D = """  /* R25：老账号/缺 me.av 也按昵称确定性兜底一张，头像位不空着 */
  var _av = (window.__avatarOf ? window.__avatarOf() : (me.av || ''));
  _av = String(_av).replace(/[^a-z0-9.\\-_]/gi, '');
  box.innerHTML = (_av ? '<img class="daily-me-face" src="/static/avatars/' +
      _av + '" alt="" onerror="this.style.display=\\'none\\'">' : '') +"""
rep("D", O_D, N_D)
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("app.js OK")

CSS="/opt/books/app/web/static/styles.css"
with io.open(CSS,"r",encoding="utf-8") as f: c=f.read()
O_E = """.daily-me-face{width:26px; height:26px; border-radius:50%; object-fit:cover;
  flex:0 0 auto; vertical-align:middle; margin-right:2px;
  background:var(--accent-soft); border:1px solid var(--border);}"""
N_E = """/* R25（用户直报「用户名旁边没有头像」）：26px 在近千像素宽的档案行里
   等于没有——放大到 40px 才配叫头像；加一圈暖描边让它从底色里浮出来。 */
.daily-me-face{width:40px; height:40px; border-radius:50%; object-fit:cover;
  flex:0 0 auto; vertical-align:middle; margin-right:10px;
  background:var(--accent-soft); border:1.5px solid var(--border);
  box-shadow:0 2px 8px rgba(184,134,11,.18);}"""
if c.count(O_E)!=1: sys.exit("FAIL E count=%d"%c.count(O_E))
if "26px 在近千像素宽的档案行里" in c: sys.exit("FAIL E 已打过")
c=c.replace(O_E,N_E,1)
O_F = """.acct-face{width:44px; height:44px; border-radius:50%; object-fit:cover;"""
N_F = """.acct-face{width:52px; height:52px; border-radius:50%; object-fit:cover;"""
if c.count(O_F)!=1: sys.exit("FAIL F count=%d"%c.count(O_F))
c=c.replace(O_F,N_F,1)
with io.open(CSS,"w",encoding="utf-8") as f: f.write(c)
print("css OK")
