import io, sys, re
IDX = "/opt/books/app/web/static/index.html"
with io.open(IDX, "r", encoding="utf-8") as f:
    lines = f.readlines()
# 1) 找到 accountCard 起始行
si = None
for k, ln in enumerate(lines):
    if 'id="accountCard"' in ln and 'acct-card' in ln:
        si = k; break
if si is None:
    sys.exit("FAIL: 找不到 accountCard 起始行")
# 2) 逐行括号配平（按行内 <div / </div> 计数，注释行先剥掉）
depth = 0
ei = None
for k in range(si, len(lines)):
    ln = re.sub(r"<!--.*?-->", "", lines[k], flags=re.S)
    depth += len(re.findall(r"<div\b", ln))
    depth -= ln.count("</div>")
    if depth == 0 and k > si:
        ei = k; break
if ei is None:
    sys.exit("FAIL: 配平失败 depth=%d" % depth)
BLOCK = "".join(lines[si:ei + 1])
print("accountCard 块：第 %d–%d 行，共 %d 行" % (si + 1, ei + 1, ei - si + 1))
# 3) 校验块内没有外来节点
for bad in ("skip-link", "returnBanner", "homeMain", "dailyCard", "bottom-nav", "fab"):
    if bad in BLOCK:
        sys.exit("FAIL: 块内混入 %s——提取仍越界" % bad)
if BLOCK.count('id="') > 14:
    sys.exit("FAIL: 块内 id 数 %d 异常" % BLOCK.count('id="'))
# 4) 从墙里摘掉整个错块，恢复 view-history 原位
#    当前墙是：<div class="auth-wall" id="authWall">\n <错块> \n</div>\n\n
wstart = None
for k, ln in enumerate(lines):
    if 'id="authWall"' in ln:
        wstart = k; break
if wstart is None:
    sys.exit("FAIL: 找不到 authWall")
# 墙的结束：从 wstart 起找 depth 归零
depth = 0
wend = None
for k in range(wstart, len(lines)):
    ln = re.sub(r"<!--.*?-->", "", lines[k], flags=re.S)
    depth += len(re.findall(r"<div\b", ln))
    depth -= ln.count("</div>")
    if depth == 0:
        wend = k; break
if wend is None:
    sys.exit("FAIL: 墙配平失败")
print("authWall：第 %d–%d 行" % (wstart + 1, wend + 1))
newlines = lines[:wstart] + lines[wend + 1:]
# 5) 找 acctSlot，把正确块放回墙
sidx = None
for k, ln in enumerate(newlines):
    if 'id="acctSlot"' in ln:
        sidx = k; break
if sidx is None:
    sys.exit("FAIL: 找不到 acctSlot")
WALL = ('<!-- R21（用户直报）：全站登录墙——「必须要登录才可以进入到网站里面，\n'
        '     然后才有他的个人信息」。默认可见，只有 JS 确认已登录才隐藏\n'
        '     （fail-closed：脚本挂了用户看到的也是登录面板，不是裸站）。\n'
        '     登录成功后 #accountCard 归位回排盘历史的 #acctSlot。 -->\n'
        '<div class="auth-wall" id="authWall">\n' + BLOCK.rstrip("\n") + '\n</div>\n\n')
newlines = newlines[:sidx] + [WALL] + newlines[sidx:]
out = "".join(newlines)
# 6) 总校验
if out.count('id="authWall"') != 1 or out.count('id="accountCard"') != 1 \
   or out.count('id="acctSlot"') != 1:
    sys.exit("FAIL: 结构计数异常")
if 'id="skip-link"' not in out or 'id="returnBanner"' not in out:
    sys.exit("FAIL: 兄弟节点丢了")
# 墙必须紧跟在 <body> 之后、且在 dailyCard 之前
if out.index('id="authWall"') > out.index('id="dailyCard"'):
    sys.exit("FAIL: 墙位置在 dailyCard 之后")
with io.open(IDX, "w", encoding="utf-8") as f:
    f.write(out)
print("index.html 重建完成：墙=%d 卡=%d slot=%d，兄弟节点完好" %
      (out.count('id="authWall"'), out.count('id="accountCard"'), out.count('id="acctSlot"')))
