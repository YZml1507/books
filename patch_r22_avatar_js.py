# -*- coding: utf-8 -*-
import io, sys
JS = "/opt/books/app/web/static/app.js"
with io.open(JS, "r", encoding="utf-8") as f: a = f.read()
def rep(tag, old, new, n=1):
    global a
    c = a.count(old)
    if c != n: sys.exit("FAIL[%s]: anchor count=%d (预期 %d)" % (tag, c, n))
    if new in a: sys.exit("FAIL[%s]: 已打过" % tag)
    a = a.replace(old, new, n)

# A. 头像池 + 性别助手
A_OLD = """      function _readFields() {"""
A_NEW = """      /* R22（用户要「男生头像/女生头像，女生多一点，随机分一张」）：
       * 注册时按性别从池里随机取一张存进 me.av——me$ 在 _DATA_RE 备份
       * 白名单里，换设备登录原样带回，不用用户选。 */
      var _AVATAR_POOL = {
        f: ['avatar-f1.jpg', 'avatar-f2.jpg', 'avatar-f3.jpg',
            'avatar-f4.jpg', 'avatar-f5.jpg', 'avatar-f6.jpg'],
        m: ['avatar-m1.jpg', 'avatar-m2.jpg', 'avatar-m3.jpg']
      };
      function _pickAvatar(g) {
        var _p = _AVATAR_POOL[g] || _AVATAR_POOL.f;
        return _p[Math.floor(Math.random() * _p.length)];
      }
      function _acctGender() {
        var _on = document.querySelector('.acct-gender-btn.is-on');
        return (_on && _on.getAttribute('data-g')) || 'f';
      }
      /* R22：性别软分段钮（幂等） */
      function _bindGender() {
        var _btns = document.querySelectorAll('.acct-gender-btn');
        for (var i = 0; i < _btns.length; i++) {
          if (_btns[i].dataset.gbound) continue;
          _btns[i].dataset.gbound = '1';
          _btns[i].addEventListener('click', function () {
            var _all = document.querySelectorAll('.acct-gender-btn');
            for (var j = 0; j < _all.length; j++) {
              _all[j].classList.remove('is-on');
              _all[j].setAttribute('aria-pressed', 'false');
            }
            this.classList.add('is-on');
            this.setAttribute('aria-pressed', 'true');
          });
        }
      }
      /* R22：账号头像行——me.av 有就显示，随备份走 */
      function _acctFace() {
        var _who = document.getElementById('acctWho');
        if (!_who) return;
        var _row = document.getElementById('acctWhoRow');
        if (!_row) {
          _row = document.createElement('div');
          _row.id = 'acctWhoRow'; _row.className = 'acct-who-row';
          var _im = document.createElement('img');
          _im.id = 'acctFace'; _im.className = 'acct-face';
          _im.alt = ''; _im.hidden = true;
          _row.appendChild(_im);
          if (!_who.parentNode) return;
          _who.parentNode.insertBefore(_row, _who);
          _row.appendChild(_who);
        }
        var _im = document.getElementById('acctFace');
        var _av = null;
        try {
          var _m = JSON.parse(localStorage.getItem('me') || 'null');
          _av = _m && _m.av;
        } catch (eAv) {}
        if (!_im) return;
        if (_av) { _im.src = '/static/avatars/' + _av; _im.hidden = false; }
        else { _im.hidden = true; }
      }
      function _readFields() {"""
rep("A-pool", A_OLD, A_NEW)

# B. _readFields 带性别
rep("B-gender", "        return { n: n, p: p, b: _b };",
             "        return { n: n, p: p, b: _b, g: _acctGender() };")

# C. 没填生辰也分头像
C_OLD = """        if (f.b.y == null) { showToast(okMsg, 'info'); return true; }"""
C_NEW = """        if (f.b.y == null) {
          /* R22：没填生辰也要分头像——头像跟性别走，不跟生辰走 */
          try { _meSave('me', { av: _pickAvatar(f.g), g: f.g || 'f' }); }
          catch (eA0) {}
          showToast(okMsg, 'info'); return true;
        }"""
rep("C-nobirth", C_OLD, C_NEW)

# D/E. 注册链 + 登录回填链带性别与头像
D_OLD = """          await _meSaveFromBirth('me', {
            y: +f.b.y, m: +f.b.m, d: +f.b.d,
            h: f.b.h == null ? null : +f.b.h, n: f.n });"""
D_NEW = """          await _meSaveFromBirth('me', {
            y: +f.b.y, m: +f.b.m, d: +f.b.d,
            h: f.b.h == null ? null : +f.b.h, n: f.n,
            g: f.g || 'f', av: _pickAvatar(f.g) });"""
rep("D-reg", D_OLD, D_NEW)
E_OLD = """                    await _meSaveFromBirth('me', {
                      y: +f.b.y, m: +f.b.m, d: +f.b.d,
                      h: f.b.h == null ? null : +f.b.h, n: f.n });"""
E_NEW = """                    await _meSaveFromBirth('me', {
                      y: +f.b.y, m: +f.b.m, d: +f.b.d,
                      h: f.b.h == null ? null : +f.b.h, n: f.n,
                      g: f.g || 'f', av: _pickAvatar(f.g) });"""
rep("E-login", E_OLD, E_NEW)

# F. 已登录面板显示头像 + 绑性别钮
F_OLD = """          _who.textContent = c.n;"""
F_NEW = """          _who.textContent = c.n;
          _bindGender();
          _acctFace();"""
rep("F-who", F_OLD, F_NEW)

# G/H. 「已做完」自解释
rep("G-label", "        _dr.textContent = _rdone ? '✅ 已做完' : '✅ 做完了';",
               "        _dr.textContent = _rdone ? '✅ 今日宜 · 已打卡' : '✅ 做完了';")
rep("H-label", "      _dr2.textContent = '✅ 已做完'; _dr2.disabled = true;",
               "      _dr2.textContent = '✅ 今日宜 · 已打卡'; _dr2.disabled = true;")

# I. 登录成功 → 生辰齐了自动拆封面
I_OLD = """            } else {
              showToast((r && r.msg) || '名字或口令码不对', 'warn');
            }"""
I_NEW = """            } else {
              showToast((r && r.msg) || '名字或口令码不对', 'warn');
            }
            /* R22（用户直报「登录进去礼物没有自动打开，还要我点」）：
             * 生辰拉齐了就把封套拆掉——此前只有点封面才走 _tryReveal，
             * 登录后档案虽已就位，封面仍盖着。 */
            try {
              var _meG0 = _meGet('me');
              if (_meG0 && _meG0.y && _meG0.m && _meG0.d) {
                var _cov0 = document.getElementById('dailyCover');
                if (_cov0 && !_cov0.classList.contains('open')) _cov0.click();
              }
            } catch (eRv0) {}"""
rep("I-reveal", I_OLD, I_NEW)

with io.open(JS, "w", encoding="utf-8") as f: f.write(a)
print("app.js OK")
