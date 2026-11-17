# -*- coding: utf-8 -*-
import io, sys
JS="/opt/books/app/web/static/app.js"
with io.open(JS,"r",encoding="utf-8") as f: a=f.read()
OLD = """  /* R25：老账号/缺 me.av 也按昵称确定性兜底一张，头像位不空着 */
  var _av = (window.__avatarOf ? window.__avatarOf() : (me.av || ''));
  _av = String(_av).replace(/[^a-z0-9.\\-_]/gi, '');"""
NEW = """  /* R25：老账号/缺 me.av 也按昵称确定性兜底一张，头像位不空着。
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
if a.count(OLD)!=1: sys.exit("FAIL count=%d"%a.count(OLD))
if "不能只依赖 window.__avatarOf" in a: sys.exit("FAIL 已打过")
a=a.replace(OLD,NEW,1)
with io.open(JS,"w",encoding="utf-8") as f: f.write(a)
print("OK")
