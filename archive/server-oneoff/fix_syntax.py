import io, sys
APP = "/opt/books/app/web/static/app.js"
BAD = "/* R231g（R39-P2-3）：聊天空态个性化——存过档案的用户，chips 换成  (function () {"
GOOD = "(function () {"
with io.open(APP, "r", encoding="utf-8") as f:
    s = f.read()
n = s.count(BAD)
if n != 1:
    sys.exit("FAIL: 破损行 count=%d" % n)
s = s.replace(BAD, GOOD, 1)
with io.open(APP, "w", encoding="utf-8") as f:
    f.write(s)
print("FIXED: 注释吞代码已修复")
