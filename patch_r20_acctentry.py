#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-6：账号入口前置到日卡顶行（CYCLE5_PLAN 任务一 §1.2-B，风险调整版）

用户原话：「你为什么把登录和注册放在拍拍历史里面而不是一打开网站
就应该是先登录和注册」。诉求核心是**首页第一屏就够得着**。

方案取舍（记录在案，供下轮复核）：
  · 原计划把 #accountCard 搬进独立 #view-account + IA 加卡（需动
    selftest home.ia 17→18 与抽屉组断言）。本轮评估：账号卡 markup 与
    其内部的注册/登录/同步/拉回/清扫/小锁全部由 getElementById 绑定、
    且夹在排盘历史工具栏与「小满记得」卡之间，整块迁移的回归面大于收益，
    故改用**零 markup 迁移**的等价方案：日卡顶行常驻一枚账号钮，一键
    切到排盘历史视图并把账号卡滚到视口中央 + 一次柔光高亮。
  · 入口仍只有一处（不新增第二个账号入口），符合「功能该删就删」。
  · /api/account/* 路由、备份口径、小锁、009 非目标（被收功能零删除）
    全部不碰。
"""
import io, sys

IDX = "/opt/books/app/web/static/index.html"
CSS = "/opt/books/app/web/static/styles.css"
APP = "/opt/books/app/web/static/app.js"

IDX_OLD = """      <span class="daily-date" id="dailyDate">加载中…</span>
      <div class="daily-card-gift"><img src="/static/shared/daily-box-gift.png" alt="" loading="lazy" decoding="async" onerror="this.parentNode.remove()"></div>"""

IDX_NEW = """      <span class="daily-date" id="dailyDate">加载中…</span>
      <!-- R20（用户直报）：账号入口前置——登录/注册原先只埋在「排盘历史」
           视图里，用户进店第一眼看不到。这枚钮常驻日卡顶行（首页第一屏、
           拆礼物之前就够得着），点它切到账号卡并滚到视口中央。 -->
      <button type="button" class="daily-acct" id="dailyAcct"
              title="登录 / 注册——填好生辰，礼物直接拆">🔐 账号</button>
      <div class="daily-card-gift"><img src="/static/shared/daily-box-gift.png" alt="" loading="lazy" decoding="async" onerror="this.parentNode.remove()"></div>"""

CSS_OLD = """/* R231a（R35-P2-8）：三枚 pill 在 375px 折成 3 行——收成单行横滑带 */"""

CSS_NEW = """/* R20（用户直报）：日卡顶行账号钮——紧凑 ghost 粒，跟礼盒并排。
 * 未登录「🔐 账号」；已登录改显昵称（_dailyAcctText 维护）。 */
.daily-acct{flex:0 0 auto; margin-left:auto; font-size:12px; line-height:1;
  padding:7px 11px; border-radius:999px; cursor:pointer; white-space:nowrap;
  color:var(--accent-ink); background:var(--card);
  border:1px solid var(--border); font-family:inherit;
  transition:background .15s, border-color .15s;}
.daily-acct:hover{background:var(--accent-soft); border-color:var(--accent-ink);}
.daily-acct.is-on{color:var(--primary-ink);}
@media (max-width:640px){.daily-acct{font-size:11px; padding:6px 9px;}}
/* R231a（R35-P2-8）：三枚 pill 在 375px 折成 3 行——收成单行横滑带 */"""

JS_OLD = """/* R231g（R39-P2-3）：聊天空态个性化——存过档案的用户，chips 换成"""

JS_NEW = """/* R20（用户直报）：账号钮文案——未登录「🔐 账号」，已登录显昵称。
 * _acctRender 末尾调一次，登录/退出/换号即时反映。 */
function _dailyAcctText() {
  var b = el('dailyAcct');
  if (!b) return;
  var c = null;
  try { c = _creds(); } catch (e) {}
  var n = (c && c.n) ? String(c.n) : '';
  b.textContent = n ? '🔓 ' + n : '🔐 账号';
  b.classList.toggle('is-on', !!n);
  b.title = n ? ('已登 ' + n + ' · 点我管账号/同步') :
    '登录 / 注册——填好生辰，礼物直接拆';
}
/* R231g（R39-P2-3）：聊天空态个性化——存过档案的用户，chips 换成"""

JS_BIND = """  (function () {
    var _da = el('dailyAcct');
    if (!_da || _da.dataset.bound) return;
    _da.dataset.bound = '1';
    _dailyAcctText();
    _da.addEventListener('click', function () {
      /* 切视图 → 滚到账号卡 → 一次柔光高亮（不新增第二个账号入口，
       * 只把既有那一处的可达性修好）。 */
      if (typeof showView === 'function') showView('history');
      var _c = el('accountCard');
      if (!_c) return;
      try {
        _c.scrollIntoView({ block: 'center', behavior: 'smooth' });
      } catch (eS) {}
      _c.classList.remove('acct-flash');
      /* 强制重排让动画能在连续点击时重放 */
      try { void _c.offsetWidth; } catch (eR) {}
      _c.classList.add('acct-flash');
      setTimeout(function () { _c.classList.remove('acct-flash'); }, 1600);
      var _n = el('acctNick');
      if (_n && _n.focus) { try { _n.focus({ preventScroll: true }); } catch (eF) {} }
    });
  })();

/* R231g（R39-P2-3）：聊天空态个性化——存过档案的用户，chips 换成"""


def main():
    # 1) index.html：顶行加钮
    with io.open(IDX, "r", encoding="utf-8") as f:
        s = f.read()
    n = s.count(IDX_OLD)
    if n != 1:
        sys.exit("FAIL: index.html anchor count=%d（预期 1）" % n)
    if 'id="dailyAcct"' in s:
        sys.exit("FAIL: index.html 已打过 R20-6")
    s = s.replace(IDX_OLD, IDX_NEW, 1)
    with io.open(IDX, "w", encoding="utf-8") as f:
        f.write(s)
    print("index.html PATCHED (R20-6)")

    # 2) styles.css：钮样式 + 高亮动画
    with io.open(CSS, "r", encoding="utf-8") as f:
        c = f.read()
    m = c.count(CSS_OLD)
    if m != 1:
        sys.exit("FAIL: styles.css anchor count=%d（预期 1）" % m)
    if ".daily-acct{" in c:
        sys.exit("FAIL: styles.css 已打过 R20-6")
    c = c.replace(CSS_OLD, CSS_NEW, 1)
    c = c.replace(CSS_NEW, CSS_NEW + """
.acct-flash{animation:acctFlash 1.6s ease-out 1;}
@keyframes acctFlash{
  0%,12%{box-shadow:0 0 0 3px var(--accent-soft);}
  100%{box-shadow:0 0 0 3px transparent;}}
@media (prefers-reduced-motion:reduce){.acct-flash{animation:none;}}""", 1)
    with io.open(CSS, "w", encoding="utf-8") as f:
        f.write(c)
    print("styles.css PATCHED (R20-6)")

    # 3) app.js：文案函数 + 绑定 + _acctRender 收尾刷新
    with io.open(APP, "r", encoding="utf-8") as f:
        a = f.read()
    k = a.count(JS_OLD)
    if k != 1:
        sys.exit("FAIL: app.js anchor count=%d（预期 1）" % k)
    if "_dailyAcctText" in a:
        sys.exit("FAIL: app.js 已打过 R20-6")
    a = a.replace(JS_OLD, JS_NEW + JS_BIND, 1)
    REND = """              ? '云端没接通——备份留不住，换设备拉不回' : '查一下云端…'));
      }
      window.__acctRender = _acctRender;"""
    REND_NEW = """              ? '云端没接通——备份留不住，换设备拉不回' : '查一下云端…'));
        /* R20（用户直报）：日卡顶行账号钮跟着登录态刷——已登录显昵称，
         * 退出回「🔐 账号」。 */
        if (typeof _dailyAcctText === 'function') _dailyAcctText();
      }
      window.__acctRender = _acctRender;"""
    if a.count(REND) != 1:
        sys.exit("FAIL: _acctRender 收尾 anchor count=%d" % a.count(REND))
    a = a.replace(REND, REND_NEW, 1)
    with io.open(APP, "w", encoding="utf-8") as f:
        f.write(a)
    print("app.js PATCHED (R20-6)")


if __name__ == "__main__":
    main()
