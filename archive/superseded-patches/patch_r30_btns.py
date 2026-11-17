# -*- coding: utf-8 -*-
"""R30-c：把六个按钮按「数据去哪」分组，每颗带去向副标。
用户原话：「我一直不知道截屏那几个按钮代表的是什么什么意思」。
根因：两组按钮去向完全不同（一组走服务器、一组走本地文件），
但命名风格一致，用户无法从名字推断数据流。"""
import io, sys
H = "/opt/books/app/web/static/index.html"
h = io.open(H, encoding="utf-8").read()


def rep(tag, old, new):
    global h
    if h.count(old) != 1:
        sys.exit("FAIL[%s] %d" % (tag, h.count(old)))
    if new in h:
        sys.exit("FAIL[%s] dup" % tag)
    h = h.replace(old, new, 1)


# ---- 云端组（#acctLogged 内） ----
rep("cloud",
    '          <div class="acct-btns">\n'
    '            <button id="acctSyncNow" type="button" class="ghost">立刻同步</button>\n'
    '            <button id="acctPull" type="button" class="ghost">从云端拉回</button>\n'
    '            <button id="acctLogout" type="button" class="ghost">退出</button>\n'
    '          </div>\n',
    '          <div class="btn-group">\n'
    '            <div class="btn-group-lab">☁️ 和云端互传'
    '<span>存在服务器上 · 换设备能找回</span></div>\n'
    '            <div class="acct-btns">\n'
    '              <button id="acctSyncNow" type="button" class="ghost">'
    '立刻同步<small>本机 → 云端</small></button>\n'
    '              <button id="acctPull" type="button" class="ghost">'
    '从云端拉回<small>云端 → 本机</small></button>\n'
    '            </div>\n'
    '          </div>\n'
    '          <div class="btn-group">\n'
    '            <div class="btn-group-lab">⚙️ 登录状态</div>\n'
    '            <div class="acct-btns">\n'
    '              <button id="acctLogout" type="button" class="ghost">'
    '退出<small>只登出，不动任何数据</small></button>\n'
    '            </div>\n'
    '          </div>\n')

# ---- 本地文件组 + 清理组（#myTools 拆分） ----
rep("localfile",
    '      <div class="ph-toolbar" id="myTools">\n'
    '        <!-- R231a（R36-P3-3）：换设备备份——台账全量+浏览器侧偏好打包下载 -->\n'
    '        <button id="historyExportJson" type="button" class="ghost">备份我的数据</button>\n'
    '        <button id="historyImportBtn" type="button" class="ghost">导入备份</button>\n'
    '        <input id="historyImportFile" type="file" accept=".json,application/json" hidden>\n'
    '        <!-- R2345（R63-P1-3）：隐私卫生——生辰/昵称/提问此前只进不出。\n'
    '             两段式确认后清本机键+服务端台账。 -->\n'
    '        <button id="historyWipe" type="button" class="ghost">忘掉我的数据</button>\n'
    '        <div class="ph-hint" style="font-size:12px;color:var(--secondary);margin-top:6px;">\n'
    '          备份/清空覆盖排盘台账、研究笔记与本机偏好，本机留档（只存在这台设备上的备份）也会一起清。\n'
    '        </div>\n'
    '      </div>\n',
    '      <div class="ph-toolbar" id="myTools">\n'
    '        <div class="btn-group">\n'
    '          <div class="btn-group-lab">📄 和本地文件互传'
    '<span>下载成 .json · 不经过服务器</span></div>\n'
    '          <div class="acct-btns">\n'
    '            <button id="historyExportJson" type="button" class="ghost">'
    '备份我的数据<small>导出文件</small></button>\n'
    '            <button id="historyImportBtn" type="button" class="ghost">'
    '导入备份<small>选文件导入</small></button>\n'
    '            <input id="historyImportFile" type="file" accept=".json,application/json" hidden>\n'
    '          </div>\n'
    '        </div>\n'
    '        <div class="btn-group">\n'
    '          <div class="btn-group-lab">🗑 清理'
    '<span>本机和云端一起清 · 不可恢复</span></div>\n'
    '          <div class="acct-btns">\n'
    '            <button id="historyWipe" type="button" class="ghost">'
    '忘掉我的数据<small>全清，救不回来</small></button>\n'
    '          </div>\n'
    '        </div>\n'
    '        <div class="ph-hint" style="font-size:12px;color:var(--secondary);margin-top:6px;">\n'
    '          备份/清空覆盖排盘台账、研究笔记与本机偏好，本机留档（只存在这台设备上的备份）也会一起清。\n'
    '        </div>\n'
    '      </div>\n')

io.open(H, "w", encoding="utf-8").write(h)
print("html OK")
