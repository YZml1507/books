# -*- coding: utf-8 -*-
import io, sys
JS = "/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
def rep(tag, old, new, n=1):
    global a
    c=a.count(old)
    if c!=n: sys.exit("FAIL[%s]: count=%d (预期 %d)"%(tag,c,n))
    if new in a: sys.exit("FAIL[%s]: 已打过"%tag)
    a=a.replace(old,new,n)

# 1. _revealIfReady 助手（挂在 _acctFace 后面）
R_OLD = """      function _readFields() {"""
R_NEW = """      /* R22b：档案齐了就拆封面——注册/登录/刷新都经 _acctRender，
       * 但封面 click 由日卡 IIFE 绑，_init 时可能还没绑上，故延迟一拍。 */
      function _revealIfReady() {
        try {
          var _m = _meGet('me');
          if (!(_m && _m.y && _m.m && _m.d)) return;
          var _c = document.getElementById('dailyCover');
          if (_c && !_c.classList.contains('open')) _c.click();
        } catch (eRr) {}
      }
      function _readFields() {"""
rep("R-helper", R_OLD, R_NEW)

# 2. 注册链：头像单独合并写补上（_meSaveFromBirth 会丢 av）
G_OLD = """              await _saveBirthThen('注册好啦，正在给你同步第一份备份');
              /* R3363-P1-4：注册首推用 keepalive——注册即关页时
               * 普通 fetch 会被掐，首份备份静默丢（此时包小，不
               * 会撞 64KiB 上限）。 */
              _push(false, true);"""
G_NEW = """              await _saveBirthThen('注册好啦，正在给你同步第一份备份');
              /* R22b：头像必须单独合并写补一笔——_meSaveFromBirth 的 rec
               * 只挑 h/g/lunar/n/y/m/d，av 会被它整丢掉；这里补上，
               * 首份云备份才带得了头像。 */
              try {
                _meSave('me', { av: _pickAvatar(_acctGender()),
                                g: _acctGender() });
              } catch (eAvR) {}
              /* R3363-P1-4：注册首推用 keepalive——注册即关页时
               * 普通 fetch 会被掐，首份备份静默丢（此时包小，不
               * 会撞 64KiB 上限）。 */
              _push(false, true);"""
rep("G-reg-av", G_OLD, G_NEW)

# 3. _acctRender 尾部补延迟拆封 + 头像刷新
F_OLD = """          _bindGender();
          _acctFace();"""
F_NEW = """          _bindGender();
          _acctFace();
          setTimeout(_revealIfReady, 400);"""
rep("F-reveal", F_OLD, F_NEW)

# 4. 登录钩子改调助手（保留原处逻辑一致性）
I_OLD = """            try {
              var _meG0 = _meGet('me');
              if (_meG0 && _meG0.y && _meG0.m && _meG0.d) {
                var _cov0 = document.getElementById('dailyCover');
                if (_cov0 && !_cov0.classList.contains('open')) _cov0.click();
              }
            } catch (eRv0) {}"""
I_NEW = """            _revealIfReady();"""
rep("I-reveal", I_OLD, I_NEW)

with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("R22b OK")
