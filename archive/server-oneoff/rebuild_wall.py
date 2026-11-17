import io, sys, re
IDX = "/opt/books/app/web/static/index.html"
BAK = "/tmp/index.bak-r21"
with io.open(BAK, "r", encoding="utf-8") as f:
    lines = f.readlines()
print("已恢复备份，%d 行" % len(lines))

si = None
for k, ln in enumerate(lines):
    if 'id="accountCard"' in ln and 'acct-card' in ln:
        si = k; break
if si is None:
    sys.exit("FAIL: 备份里找不到 accountCard")
depth = 0; ei = None
for k in range(si, len(lines)):
    ln = re.sub(r"<!--.*?-->", "", lines[k], flags=re.S)
    depth += len(re.findall(r"<div\b", ln)); depth -= ln.count("</div>")
    if depth == 0 and k > si:
        ei = k; break
if ei is None:
    sys.exit("FAIL: 配平失败")
BLOCK = "".join(lines[si:ei + 1])
print("accountCard 块：第 %d–%d 行（%d 行）" % (si + 1, ei + 1, ei - si + 1))
for bad in ("skip-link", "returnBanner", "homeMain", "dailyCard", "bottom-nav",
            "fab", "mem-card", "view-history", "ph-toolbar", "brand"):
    if bad in BLOCK:
        sys.exit("FAIL: 块内混入 %s" % bad)
ids = re.findall(r'id="([^"]+)"', BLOCK)
print("块内 id：%s" % ", ".join(ids))
if len(ids) != 17:
    sys.exit("FAIL: id 数 %d ≠ 17" % len(ids))
# 原位留 slot
newlines = lines[:si] + ['      <div id="acctSlot"></div>\n'] + lines[ei + 1:]
WALL = ('<!-- R21（用户直报）：全站登录墙——「必须要登录才可以进入到网站里面，\n'
        '     然后才有他的个人信息」。默认可见，只有 JS 确认已登录才隐藏\n'
        '     （fail-closed：脚本挂了用户看到的也是登录面板，不是裸站）。\n'
        '     登录成功后 #accountCard 归位回排盘历史的 #acctSlot。 -->\n'
        '<div class="auth-wall" id="authWall">\n' + BLOCK.rstrip("\n") + '\n</div>\n\n')
bi = None
for k, ln in enumerate(newlines):
    if ln.strip() == "<body>":
        bi = k; break
if bi is None:
    sys.exit("FAIL: 找不到 <body>")
newlines = newlines[:bi + 1] + [WALL] + newlines[bi + 1:]
out = "".join(newlines)
for key, want in (('id="authWall"', 1), ('id="accountCard"', 1), ('id="acctSlot"', 1),
                  ('class="skip-link"', 1), ('id="returnBanner"', 1),
                  ('id="memoryCard"', 1), ('id="dailyCard"', 1)):
    if out.count(key) != want:
        sys.exit("FAIL: %s count=%d（预期 %d）" % (key, out.count(key), want))
if out.index('id="authWall"') > out.index('id="dailyCard"'):
    sys.exit("FAIL: 墙在 dailyCard 之后")
with io.open(IDX, "w", encoding="utf-8") as f:
    f.write(out)
print("OK：authWall=1 accountCard=1 acctSlot=1，skip-link/returnBanner/memoryCard/dailyCard 全在位")
