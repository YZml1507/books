# -*- coding: utf-8 -*-
"""R28-d：记忆卡挪到「我的」后，渲染触发器要跟着走。"""
import io, sys
J = "/opt/books/app/web/static/app.js"
with io.open(J, "r", encoding="utf-8") as f:
    j = f.read()
OLD = ("  Object.keys(RESULT_GEN).forEach(function (k) { RESULT_GEN[k]++; });\n"
       "  var _sy = window.scrollY;\n"
       "  var isHome = (viewId === 'home');\n")
NEW = ("  Object.keys(RESULT_GEN).forEach(function (k) { RESULT_GEN[k]++; });\n"
       "  /* R28-d：记忆卡从「排盘历史」挪进了「我的」——它的渲染原先只在\n"
       "     历史视图加载时触发（_loadPaipanHistoryInner 里），挪窝后就\n"
       "     再也不刷新，卡片永远是空的。切到账号视图时补一次。 */\n"
       "  if (viewId === 'account') {\n"
       "    try { if (typeof _xmMemRender === 'function') _xmMemRender(); } catch (eMM) {}\n"
       "  }\n"
       "  var _sy = window.scrollY;\n"
       "  var isHome = (viewId === 'home');\n")
if j.count(OLD) != 1:
    sys.exit("FAIL[showView] count=%d" % j.count(OLD))
if "R28-d" in j:
    sys.exit("FAIL[dup]")
j = j.replace(OLD, NEW, 1)
with io.open(J, "w", encoding="utf-8") as f:
    f.write(j)
print("OK")
