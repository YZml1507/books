"""R14-L1/L2 补丁：桌面网格列数 landscape→宽度断点 + 心情行桌面排布。
精确字符串替换：断言原块唯一存在，失败即停不写文件。"""
import io
import sys

P = "web/static/styles.css"
css = io.open(P, encoding="utf-8").read()

ANCHOR = "@media (orientation: landscape) and (min-width: 700px){"
n = css.count(ANCHOR)
if n != 1:
    sys.exit("FAIL: anchor count = %d（期望 1），不写文件" % n)

i = css.index(ANCHOR)
j = css.index("{", i)
depth, k = 0, j
while k < len(css):
    if css[k] == "{":
        depth += 1
    elif css[k] == "}":
        depth -= 1
        if depth == 0:
            break
    k += 1
if depth != 0:
    sys.exit("FAIL: 括号不配平，不写文件")
OLD = css[i:k + 1]

NEW = """/* R14-L1（审-布局，D-912）：原 orientation:landscape 查询为横屏手机/平板
   书写，却命中全部桌面宽度——17 张功能卡恒 2 列排 9 行，1440 宽 docH
   2058px、1920 宽两侧各空 410px（实测）。改为宽度断点：横屏平板密度不
   低于原两栏，桌面宽屏按栏数吃掉留白。≤560 两栏由既有规则负责。 */
@media (min-width: 561px) and (max-width: 899px){
  .func-grid{ grid-template-columns:repeat(3,1fr); }
  .result .card{ max-width:none; }
}
@media (min-width: 900px) and (max-width: 1279px){
  .func-grid{ grid-template-columns:repeat(4,1fr); }
  .result .card{ max-width:none; }
}
@media (min-width: 1280px){
  .func-grid{ grid-template-columns:repeat(5,1fr); }
  .result .card{ max-width:none; }
}
/* R14-L2：心情行两颗入口按钮原 flex-basis:100% 独占一行右对齐，与左侧
   问题+表情按钮之间中段空心（用户截图实况）。≥900px 改同行右置。 */
@media (min-width: 900px){
  .mood-week-link-wrap{ flex-basis:auto; margin-top:0; margin-left:auto; }
}"""

out = css[:i] + NEW + css[k + 1:]
io.open(P, "w", encoding="utf-8").write(out)
print("PATCHED: 原块 %dB → 新块 %dB（净 +%dB）" % (len(OLD), len(NEW), len(NEW) - len(OLD)))
print("文件: %dB → %dB" % (len(css), len(out)))
