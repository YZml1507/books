# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag,old,new,n=1):
    global a
    if a.count(old)!=n: sys.exit("FAIL[%s] count=%d"%(tag,a.count(old)))
    if new in a: sys.exit("FAIL[%s] 已打过"%tag)
    a=a.replace(old,new,n)

# --- 1) 全局头像兜底（唯一定义，三处共用） ---
O1 = """function _dailyAcctText() {"""
N1 = """/* R26（用户直报「右上角用户名旁边加个锁而不是加个头像」）：🔓 那个
 * 开锁表情就是用户说的「锁」。头像兜底收成**全局唯一一份**——原先
 * 档案行内联一份、账号 IIFE 里一份，算法漂移就会两张脸。 */
window.__avatarPick = function (n, g) {
  var _POOL = {
    f: ['avatar-f1.jpg', 'avatar-f2.jpg', 'avatar-f3.jpg',
        'avatar-f4.jpg', 'avatar-f5.jpg', 'avatar-f6.jpg'],
    m: ['avatar-m1.jpg', 'avatar-m2.jpg', 'avatar-m3.jpg']
  };
  var _pl = _POOL[(g === 'm') ? 'm' : 'f'], _h = 0, _s = String(n || '');
  for (var i = 0; i < _s.length; i++) {
    _h = (_h * 31 + _s.charCodeAt(i)) & 0x7fffffff;
  }
  return _pl[_h % _pl.length];
};
window.__avatarOf = function () {
  var _av = '', _n = '', _g = 'f';
  try {
    var _m = JSON.parse(localStorage.getItem('me') || 'null');
    if (_m) {
      _av = _m.av ? String(_m.av).replace(/[^a-z0-9.\\-_]/gi, '') : '';
      _n = _m.n ? String(_m.n) : '';
      if (_m.g === 'm' || _m.g === 'f') _g = _m.g;
    }
  } catch (e) {}
  return _av || window.__avatarPick(_n, _g);
};
function _dailyAcctText() {"""
rep("1-global", O1, N1)

# --- 2) 右上角账号钮：🔓 → 头像 + 用户名 ---
O2 = """  var n = (c && c.n) ? String(c.n) : '';
  b.textContent = n ? '🔓 ' + n : '🔐 账号';
  b.classList.toggle('is-on', !!n);
  b.title = n ? ('已登 ' + n + ' · 点我管账号/同步') :
    '登录 / 注册——填好生辰，礼物直接拆';"""
N2 = """  var n = (c && c.n) ? String(c.n) : '';
  /* R26：把开锁表情换成真头像——用户名旁边该是一张脸，不是一把锁 */
  var _av = '';
  try { _av = window.__avatarOf ? window.__avatarOf() : ''; } catch (eAv) {}
  if (!_av && n) _av = window.__avatarPick(n, 'f');
  _av = String(_av).replace(/[^a-z0-9.\\-_]/gi, '');
  if (n) {
    b.innerHTML = '<img class="daily-acct-face" src="/static/avatars/' + _av +
      '" alt="" onerror="this.style.display=\\'none\\'">' +
      '<span class="daily-acct-name">' + esc(n) + '</span>';
  } else {
    b.textContent = '🔐 账号';
  }
  b.classList.toggle('is-on', !!n);
  b.title = n ? ('已登 ' + n + ' · 点我管账号/同步') :
    '登录 / 注册——填好生辰，礼物直接拆';"""
rep("2-btn", O2, N2)

# --- 3) 点击目标：history → account（用户个人信息） ---
O3 = """      if (typeof showView === 'function') showView('history');
      var _c = el('accountCard');"""
N3 = """      /* R26（用户原话「点右上角用户名进的是排盘历史，但不对，
       * 应该进用户的个人信息」）：目标改到 #view-account。 */
      if (typeof showView === 'function') showView('account');
      var _c = el('accountCard');"""
rep("3-target", O3, N3)

# --- 4) 账号 IIFE 的 _avatarOf 改为委托全局（消除重复实现） ---
O4 = """      function _avatarOf() {
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
      }"""
N4 = """      /* R26：兜底收成全局唯一一份（window.__avatarOf），这里只委托，
       * 不再维护第二套算法——两套漂移就会档案行和账号卡两张脸。 */
      function _avatarOf() {
        try { if (window.__avatarOf) return window.__avatarOf(); } catch (eD) {}
        var _p = _AVATAR_POOL.f;
        return _p[0];
      }"""
rep("4-delegate", O4, N4)

# --- 5) 档案行内联兜底也改为委托全局 ---
O5 = """  /* R25：老账号/缺 me.av 也按昵称确定性兜底一张，头像位不空着。
   * 注意不能只依赖 window.__avatarOf——档案行的渲染早于账号 IIFE 执行
   * （实测：首屏调用时全局还没挂上，兜底静默失效）。这里自带一份同算法
   * 的性别池兜底，保证任何时候调用都有一张脸；算法与 _avatarOf() 一致
   * （性别池 + 昵称哈希），所以档案行和账号卡永远选到同一张。 */
  var _av = '';
  try { _av = window.__avatarOf ? window.__avatarOf() : ''; } catch (eA) {}
  if (!_av) {
    var _POOL = {
      f: ['avatar-f1.jpg', 'avatar-f2.jpg', 'avatar-f3.jpg',
          'avatar-f4.jpg', 'avatar-f5.jpg', 'avatar-f6.jpg'],
      m: ['avatar-m1.jpg', 'avatar-m2.jpg', 'avatar-m3.jpg']
    };
    var _g = (me.g === 'm') ? 'm' : 'f';
    var _pl = _POOL[_g], _h = 0, _s = String(me.n || '');
    for (var _i = 0; _i < _s.length; _i++) {
      _h = (_h * 31 + _s.charCodeAt(_i)) & 0x7fffffff;
    }
    _av = _pl[_h % _pl.length];
  }
  _av = String(_av).replace(/[^a-z0-9.\\-_]/gi, '');"""
N5 = """  /* R26：兜底走全局唯一一份（window.__avatarOf 定义在 _dailyAcctText
   * 之前，早于本渲染函数执行，不存在 R25 那个「全局还没挂上」的时序坑）。 */
  var _av = '';
  try { _av = window.__avatarOf ? window.__avatarOf() : ''; } catch (eA) {}
  if (!_av && me.n) {
    try { _av = window.__avatarPick(me.n, me.g === 'm' ? 'm' : 'f'); } catch (eP) {}
  }
  _av = String(_av).replace(/[^a-z0-9.\\-_]/gi, '');"""
rep("5-meline", O5, N5)
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("app.js OK")
