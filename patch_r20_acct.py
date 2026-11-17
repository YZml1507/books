#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-4：注册即收生辰（CYCLE5_PLAN 任务一 §1.2-A）

用户原话：「把首页那个填年月日的彻底不要，改为在登录和注册的时候就
填好年月日还有时间等等，然后这样只要用户登录就可以直接打开那个礼物」。
链路调研结论（CYCLE5_PLAN §1.1）——三处现成机制决定了只需补注册表单：
  · app.js:17831 _tryReveal：`_meGet('me')` 有完整 y/m/d → 直接 _reveal()
    （门槛早已支持「有档案即直拆」，不必改礼物逻辑）
  · app.js:29281 _DATA_RE 含 `me$`/`me:partner$` → 云端备份本就带生日，
    换设备登录拉回即还原档案 → 登录侧零改动
  · app.js:24905 _meSaveFromBirth：农历换算/未来年拒收/时辰 0–23 归一/
    昵称清洗/换人清旧名全在里面 → 复用，不新写任何校验

本补丁：
  index.html  #acctForm 增「生辰」四字段（年/月/日必填，时辰选填）
  styles.css  .acct-birth 行样式（复用 --tap 触控下限）
  app.js      _readFields 读生辰并校验；注册成功分支在 _push 之前
              await _meSaveFromBirth('me',{y,m,d,h,n}) —— 必须在首推前
              落档，否则第一份云备份不带生日，换设备登录仍要重填。
              登录分支：拉回后若云端无 me 而用户填了生辰，按填的补档
              （照顾这个功能上线前注册的老账号）。
失败不阻塞注册：_meSaveFromBirth 内部 try/catch + 换算失败即不落档。
"""
import io, sys

IDX = "/opt/books/app/web/static/index.html"
CSS = "/opt/books/app/web/static/styles.css"
APP = "/opt/books/app/web/static/app.js"

IDX_OLD = """          <input id="acctPass" type="password" maxlength="64" autocomplete="off"
                 placeholder="口令码（至少 6 位）">
          <div class="acct-btns">"""

IDX_NEW = """          <input id="acctPass" type="password" maxlength="64" autocomplete="off"
                 placeholder="口令码（至少 6 位）">
          <!-- R20（用户直报）：生辰上移到注册时收——首页那张填年月日的
               大表单退场，这里成为唯一收生辰的地方。礼物门槛 _tryReveal
               读的是同一份 me 档案，填完即「照你的盘包好」，登录后直接拆。
               登录则从云端备份带回（_DATA_RE 含 me$），老账号云端没档时
               按这里填的补。想改随时能改：日卡「你的小档案 · 改」。 -->
          <div class="acct-birth">
            <span class="acct-birth-lab">生辰（礼物照这个包，随时能改）</span>
            <div class="acct-birth-row">
              <input id="acctY" type="number" inputmode="numeric" min="1900"
                     max="2100" autocomplete="bday-year" placeholder="年">
              <input id="acctM" type="number" inputmode="numeric" min="1"
                     max="12" autocomplete="bday-month" placeholder="月">
              <input id="acctD" type="number" inputmode="numeric" min="1"
                     max="31" autocomplete="bday-day" placeholder="日">
              <input id="acctH" type="number" inputmode="numeric" min="0"
                     max="23" placeholder="时辰·选填">
            </div>
          </div>
          <div class="acct-btns">"""

CSS_OLD = """.acct-btns { display: flex; gap: 8px; flex-wrap: wrap; }"""

CSS_NEW = """/* R20（用户直报）：注册即收生辰——四字段一行，时辰选填。
 * 16px 字号与全局输入口径一致（iOS 聚焦不整页缩放，同 fl-modal textarea）。 */
.acct-birth { display: flex; flex-direction: column; gap: 4px; }
.acct-birth-lab { font-size: 12px; color: var(--secondary); }
.acct-birth-row { display: flex; gap: 6px; flex-wrap: wrap; }
.acct-birth-row input { flex: 1 1 60px; min-width: 56px; font-size: 16px;
  min-height: var(--tap); }
.acct-birth-row input::placeholder { color: var(--muted); }
.acct-btns { display: flex; gap: 8px; flex-wrap: wrap; }"""

JS_OLD = """      function _readFields() {
        var n = (_nick.value || '').trim();
        var p = (_pass.value || '').trim();
        if (!n) { showToast('先给自己起个名', 'warn'); return null; }
        if (p.length < 6) {
          showToast('口令码至少 6 位', 'warn');
          return null;
        }
        return { n: n, p: p };
      }"""

JS_NEW = """      /* R20（用户直报）：生辰一并读走——注册要，登录也读（老账号云端
       * 没档时按填的补）。校验只做「注册必须填全」：年月日为数字且在
       * 合法区间；时辰选填但填了就得是 0–23。更硬的边界（未来年、农历
       * 换算失败、时辰归一）全部交给 _meSaveFromBirth/_meSave，不重复造。 */
      function _readFields() {
        var n = (_nick.value || '').trim();
        var p = (_pass.value || '').trim();
        if (!n) { showToast('先给自己起个名', 'warn'); return null; }
        if (p.length < 6) {
          showToast('口令码至少 6 位', 'warn');
          return null;
        }
        var _b = {};
        [['y', 'acctY'], ['m', 'acctM'], ['d', 'acctD'], ['h', 'acctH']]
          .forEach(function (pair) {
            var elx = document.getElementById(pair[1]);
            var v = elx ? String(elx.value || '').trim() : '';
            _b[pair[0]] = v === '' ? null : v;
          });
        return { n: n, p: p, b: _b };
      }
      /* 返回 null 表示放行（登录态下生辰可空）；否则返回提示语。 */
      function _birthErr(b) {
        if (!b) return null;
        var _y = +b.y, _m = +b.m, _d = +b.d;
        if (b.y == null || b.m == null || b.d == null) {
          return '生辰填上年月日——礼物照着这个包，填错也能改';
        }
        if (!(+b.y >= 1900 && +b.y <= 2100)) return '年份看着不太对哦';
        if (!(_m >= 1 && _m <= 12)) return '月份得在 1 到 12 之间';
        if (!(_d >= 1 && _d <= 31)) return '日子得在 1 到 31 之间';
        if (b.h != null && !(+b.h >= 0 && +b.h <= 23)) {
          return '时辰填 0 到 23 之间的数（不知道就留空）';
        }
        return null;
      }
      /* 落档并刷新日卡——await 后再 _push，首份云备份才带得上生日。 */
      async function _saveBirthThen(okMsg) {
        var f = _readFields();
        if (!f) return false;
        var _err = _birthErr(f.b);
        if (_err) { showToast(_err, 'warn'); return false; }
        if (f.b.y == null) { showToast(okMsg, 'info'); return true; }
        try {
          await _meSaveFromBirth('me', {
            y: +f.b.y, m: +f.b.m, d: +f.b.d,
            h: f.b.h == null ? null : +f.b.h, n: f.n });
        } catch (eB) {
          showToast('生辰没存上，礼物先按通版开', 'warn');
        }
        showToast(okMsg, 'info');
        return true;
      }"""


def main():
    for path, old, new, tag in ((IDX, IDX_OLD, IDX_NEW, "index.html"),
                                (CSS, CSS_OLD, CSS_NEW, "styles.css"),
                                (APP, JS_OLD, JS_NEW, "app.js")):
        with io.open(path, "r", encoding="utf-8") as f:
            s = f.read()
        n = s.count(old)
        if n != 1:
            sys.exit("FAIL: %s anchor count=%d（预期 1）" % (tag, n))
        if "R20（用户直报）：生辰一并读走" in s and tag == "app.js":
            sys.exit("FAIL: app.js 已打过 R20-4")
        s = s.replace(old, new, 1)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(s)
        print("%s PATCHED (R20-4)" % tag)


if __name__ == "__main__":
    main()
