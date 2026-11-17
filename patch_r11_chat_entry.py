#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R11：修「和小满聊聊」入口死键（用户直报：有时候点了打不开）。

病灶（代码实证）：
  侧栏开着时 _mainInert(true) 把 .wrap 整块 inert，落在聊天入口上的
  点击先命中 #recentBackdrop → document 捕获段（R3258）按「点外面
  收栏」收掉侧栏并记 _swallowPt → 紧随的 click 被吞（stopImmediate
  Propagation）→ 入口监听器永远收不到。R3258 的 [data-chat-entry]
  例外只贴在了侧栏内部按钮，首页三个聊天入口都没贴，且被整块
  inert 挡住够不着。侧栏已开时点入口 / 连点两下 = 死键。

修法（两边补，功能零删除）：
  ① 三个聊天入口打 data-chat-entry 标（功能卡 / 💭chip / 深拥横幅钮）；
  ② _mainInert 纯侧栏开合时主区改逐子 inert，[data-chat-entry]
     整棵豁免——入口保持可点，点击走既有委托链 chatOpen()（语义
     正是 R3258 注释写的「入口按钮交给委托链处理」）。模态开
   （except 在）仍整块 inert，不给叠层下漏点。
"""
import io, sys

PATCHES = [
    # ── index.html：三个聊天入口打标 ──────────────────────────
    ('web/static/index.html',
     '<div class="func-card func-entry func-chat" data-view="chat" role="button" tabindex="0" aria-label="和小满聊聊">',
     '<div class="func-card func-entry func-chat" data-view="chat" data-chat-entry role="button" tabindex="0" aria-label="和小满聊聊">'),
    ('web/static/index.html',
     '<button type="button" class="scene-chip" data-scene="chat">',
     '<button type="button" class="scene-chip" data-scene="chat" data-chat-entry>'),
    ('web/static/index.html',
     '<button type="button" class="ghost" id="returnChat">和小满聊聊</button>',
     '<button type="button" class="ghost" id="returnChat" data-chat-entry>和小满聊聊</button>'),
    # ── app.js：_inertTree 助手 + _mainInert 改逐子 inert ──────
    ('web/static/app.js',
     """function _mainInert(on, except) {
  var w = document.querySelector('.wrap');
  if (w) { w.inert = on; if (_NO_INERT) sbFocusable(w, !on); }""",
     """/* R11（用户直报「和小满聊聊有时候点了打不开」）：侧栏开着时主区
 * 整块 inert，落在聊天入口上的点击先命中遮罩——document 捕获段按
 * 「点外面收栏」收掉侧栏，还把紧随的 click 吞了（_swallowPt），
 * 入口监听器永远收不到：侧栏已开时点入口 / 连点两下 = 死键。
 * R3258 的 [data-chat-entry] 例外只贴在了侧栏内部按钮，首页三个
 * 聊天入口（功能卡 / 💭chip / 深拥横幅钮）没贴且被整块 inert 挡住。
 * 修法：入口打标 + 主区逐子 inert、入口整棵豁免（点击走委托链
 * chatOpen——正是 R3258 注释说的「入口按钮交给委托链处理」）。
 * 代价：侧栏开着时 Tab 能到这几个入口——可接受，它们就是制裁过
 * 的再入口（Enter 即 chatOpen）。模态开（except 在）仍整块 inert。 */
function _inertTree(root, on, skipSel) {
  if (!root) return;
  Array.prototype.forEach.call(root.children, function (c) {
    if (!c || c.nodeType !== 1) return;
    if (skipSel && c.matches && c.matches(skipSel)) return;  /* 整棵豁免 */
    c.inert = on;
    if (_NO_INERT) sbFocusable(c, !on);
    _inertTree(c, on, skipSel);
  });
}
function _mainInert(on, except) {
  var w = document.querySelector('.wrap');
  if (w) {
    if (on && !except) {
      w.inert = false;
      _inertTree(w, true, '[data-chat-entry]');
    } else {
      w.inert = on;
      if (!on) _inertTree(w, false, null);   /* 收摊：子树 inert 一并解 */
      if (_NO_INERT) sbFocusable(w, !on);
    }
  }"""),
    ('web/static/app.js',
     """    if (n.classList && n.classList.contains('page-glow')) return;
    n.inert = on;""",
     """    if (n.classList && n.classList.contains('page-glow')) return;
    /* R11：body 级聊天入口（深拥横幅）同样豁免——同 .wrap 口径 */
    if (!except && n.matches && n.matches('[data-chat-entry]')) return;
    n.inert = on;"""),
]


def main():
    files = {}
    for path, old, new in PATCHES:
        if path not in files:
            with io.open(path, encoding='utf-8') as f:
                files[path] = f.read()
        s = files[path]
        n = s.count(old)
        if n != 1:
            print('FAIL %s: anchor count=%d (need 1): %r' % (path, n, old[:70]))
            sys.exit(1)
        files[path] = s.replace(old, new)
        print('ok %s <- %r' % (path, old[:60]))
    for path, s in files.items():
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(s)
    print('R11 patch applied: %d edits' % len(PATCHES))


if __name__ == '__main__':
    main()
