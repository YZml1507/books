# -*- coding: utf-8 -*-
import io, sys
JS = "/opt/books/app/web/static/app.js"
with io.open(JS, "r", encoding="utf-8") as f:
    a = f.read()


def rep(tag, old, new, n=1):
    global a
    if a.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, a.count(old)))
    if new and new in a:
        sys.exit("FAIL[%s] 已打过" % tag)
    a = a.replace(old, new, n)


# 1) 赋值式改函数声明式（函数声明会被提升，任意调用点都够得着）
rep("pick-decl",
    "window.__avatarPick = function (n, g) {",
    "function __avatarPick(n, g) {")
rep("of-decl",
    "window.__avatarOf = function () {",
    "function __avatarOf() {")

# 2) 两处收尾：把 window 挂载补在函数体之后
rep("pick-tail",
    "  return _pl[_h % _pl.length];\n"
    "};\n"
    "function __avatarOf() {",
    "  return _pl[_h % _pl.length];\n"
    "}\n"
    "window.__avatarPick = __avatarPick;\n"
    "function __avatarOf() {")
rep("of-tail",
    "  return _av || window.__avatarPick(_n, _g);\n"
    "};\n"
    "function _dailyAcctText() {",
    "  return _av || __avatarPick(_n, _g);\n"
    "}\n"
    "window.__avatarOf = __avatarOf;\n"
    "function _dailyAcctText() {")

# 3) 内部调用点全部改用提升后的裸名（不再依赖 window 挂载时机）
rep("call-btn1",
    "  try { _av = window.__avatarOf ? window.__avatarOf() : ''; } catch (eAv) {}\n"
    "  if (!_av && n) _av = window.__avatarPick(n, 'f');",
    "  try { _av = __avatarOf(); } catch (eAv) {}\n"
    "  if (!_av && n) _av = __avatarPick(n, 'f');")
rep("call-line1",
    "  try { _av = window.__avatarOf ? window.__avatarOf() : ''; } catch (eA) {}\n"
    "  if (!_av && me.n) {\n"
    "    try { _av = window.__avatarPick(me.n, me.g === 'm' ? 'm' : 'f'); } catch (eP) {}\n"
    "  }",
    "  try { _av = __avatarOf(); } catch (eA) {}\n"
    "  if (!_av && me.n) {\n"
    "    try { _av = __avatarPick(me.n, me.g === 'm' ? 'm' : 'f'); } catch (eP) {}\n"
    "  }")
rep("call-acct",
    "      function _avatarOf() {\n"
    "        try { if (window.__avatarOf) return window.__avatarOf(); } catch (eD) {}\n"
    "        var _p = _AVATAR_POOL.f;\n"
    "        return _p[0];\n"
    "      }",
    "      function _avatarOf() {\n"
    "        try { return __avatarOf(); } catch (eD) {}\n"
    "        var _p = _AVATAR_POOL.f;\n"
    "        return _p[0];\n"
    "      }")

with io.open(JS, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js OK")
