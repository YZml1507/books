# -*- coding: utf-8 -*-
"""R28：把「排盘历史」里不属于历史的东西挪进「我的」。
用户原话：「我实在是不知道排盘历史这个功能和个人账户到底有什么区别，
为什么不能合并在一起，排盘历史的档案不就是用户的个人信息吗」。
"""
import io, sys
H = "/opt/books/app/web/static/index.html"
with io.open(H, "r", encoding="utf-8") as f:
    h = f.read()


def rep(tag, old, new, n=1):
    global h
    if h.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, h.count(old)))
    if new and new in h:
        sys.exit("FAIL[%s] 已打过" % tag)
    h = h.replace(old, new, n)


# ---- 1) 取出记忆卡整块 ----
MEM_START = '      <div class="mem-card" id="memoryCard">'
MEM_END = '      <!-- R3200：类型筛选——记录多了按品类过一眼。只在有条目时出现。 -->'
i = h.index(MEM_START)
j = h.index(MEM_END)
mem = h[i:j]
h = h[:i] + h[j:]

# ---- 2) 取出备份/清理工具（全量数据工具，不属于「历史」） ----
TOOLS = ('        <!-- R231a（R36-P3-3）：换设备备份——台账全量+浏览器侧偏好打包下载 -->\n'
         '        <button id="historyExportJson" type="button" class="ghost">备份我的数据</button>\n'
         '        <button id="historyImportBtn" type="button" class="ghost">导入备份</button>\n'
         '        <input id="historyImportFile" type="file" accept=".json,application/json" hidden>\n'
         '        <!-- R2345（R63-P1-3）：隐私卫生——生辰/昵称/提问此前只进不出。\n'
         '             两段式确认后清本机键+服务端台账。 -->\n'
         '        <button id="historyWipe" type="button" class="ghost">忘掉我的数据</button>\n')
if h.count(TOOLS) != 1:
    sys.exit("FAIL[tools] count=%d" % h.count(TOOLS))
h = h.replace(TOOLS, "", 1)

HINT = ('        <div class="ph-hint" style="font-size:12px;color:var(--secondary);margin-top:6px;">\n'
        '          备份/清空覆盖排盘台账、研究笔记与本机偏好，本机留档（只存在这台设备上的备份）也会一起清。\n'
        '        </div>\n')
if h.count(HINT) != 1:
    sys.exit("FAIL[hint] count=%d" % h.count(HINT))
h = h.replace(HINT, "", 1)

# ---- 3) 「我的」视图：改名 + 收进记忆卡 + 收进备份工具 ----
rep("acct-h2",
    '      <h2><span aria-hidden="true">🧸</span> 我的账号 <span class="card-sub">生辰 · 头像 · 云端备份</span></h2>\n'
    '      <div id="acctSlot"></div>\n'
    '      <p class="acct-empty" id="acctEmpty">还没登录——回首页登录后，你的生辰、头像和云端备份就摆在这儿。</p>\n'
    '    </div>\n'
    '  </div>',
    '      <h2><span aria-hidden="true">🧸</span> 我的 <span class="card-sub">身份 · 小满记得的 · 备份</span></h2>\n'
    '      <div id="acctSlot"></div>\n'
    '      <p class="acct-empty" id="acctEmpty">还没登录——回首页登录后，你的档案、头像和云端备份就摆在这儿。</p>\n'
    '      <!-- R28：备份/清理是全量数据工具，原先寄生在「排盘历史」里——那页\n'
    '           自己的说明都写着「覆盖排盘台账、研究笔记与本机偏好」，放在一个\n'
    '           以单类数据命名的页面下名不正言不顺。挪到「我的」。 -->\n'
    '      <div class="ph-toolbar" id="myTools">\n'
    + TOOLS + HINT +
    '      </div>\n'
    + mem +
    '    </div>\n'
    '  </div>')

# ---- 4) 排盘历史 → 排盘记录（只留记录自己的东西） ----
rep("hist-h2",
    '      <h2><span aria-hidden="true">🕘</span> 排盘历史 <span class="card-sub">本机记录 · 可回查可导出</span></h2>',
    '      <h2><span aria-hidden="true">🕘</span> 排盘记录 <span class="card-sub">只放记录本身 · 档案和备份在「我的」</span></h2>')

# ---- 5) 功能卡：两个入口重新定性 ----
rep("card-hist",
    '<div class="func-card func-entry func-more" data-view="history" role="button" tabindex="0" aria-label="排盘历史">',
    '<div class="func-card func-entry func-more" data-view="history" role="button" tabindex="0" aria-label="排盘记录">')
rep("card-hist-name",
    '<div class="func-name">排盘历史</div><div class="func-desc">翻翻看过的盘 · 可导出</div>',
    '<div class="func-name">排盘记录</div><div class="func-desc">只看记录 · 档案在「我的」</div>')
rep("card-acct",
    '<div class="func-card func-entry func-more" data-view="account" role="button" tabindex="0" aria-label="我的账号">',
    '<div class="func-card func-entry func-more" data-view="account" role="button" tabindex="0" aria-label="我的">')
rep("card-acct-name",
    '<div class="func-name">我的账号</div><div class="func-desc">生辰 · 头像 · 云端备份</div>',
    '<div class="func-name">我的</div><div class="func-desc">档案 · 小满记得的 · 备份</div>')

with io.open(H, "w", encoding="utf-8") as f:
    f.write(h)
print("index.html OK")
