"""R15-L1：心情行桌面工具栏化（治「两颗链被撑到行两端、中段空一大片」）。
app.js：两颗链串出心情历，插到回执 span 之前（桌面与问题/表情钮同行，
右侧成组）；styles.css：原 R14-L2 双 auto 边距方案替换为首链推右 +
问题行内化，手机端 order:1 保持原阅读顺序。全部锚点唯一断言。"""
import io
import sys

ok = True

# ---------- app.js ----------
P = "web/static/app.js"
src = io.open(P, encoding="utf-8").read()
A1_OLD = """    /* 心情周记入口——打卡区小链，点进出「这周的你」周记卡视图。
     * 独占一行右对齐——塞在心情历行尾会被挤成竖条还戳出卡缘。 */
    _calHtml += '<span class="mood-week-link-wrap">' +
      '<button type="button" class="mood-week-link">' +
      '📒 看看这周的你 →</button></span>';"""
A1_NEW = """    /* 心情周记入口——R15-L1（用户实测「这一块很影响用户体验」）：
     * 两颗链串出心情历，桌面端与问题/表情钮收成一条工具栏（右侧成组，
     * 不再被两个 auto 边距撑到整行两端）；手机端 order:1 归位，仍排
     * 心情历之后，阅读顺序不变。首链挂 mood-links-lead 供 CSS 推右。 */
    var _linkHtml = '<span class="mood-week-link-wrap mood-links-lead">' +
      '<button type="button" class="mood-week-link">' +
      '📒 看看这周的你 →</button></span>';"""
A2_OLD = """        _calHtml += '<span class="mood-week-link-wrap">' +
          '<button type="button" class="mood-backfill" data-d="' +"""
A2_NEW = """        _linkHtml += '<span class="mood-week-link-wrap">' +
          '<button type="button" class="mood-backfill" data-d="' +"""
A3_OLD = """    mc.innerHTML = _calHtml;
  }"""
A3_NEW = """    mc.innerHTML = _calHtml;
    if (_linkHtml) (el('moodAns') || mc).insertAdjacentHTML('beforebegin', _linkHtml);
  }"""
for old, new, tag in [(A1_OLD, A1_NEW, "A1"), (A2_OLD, A2_NEW, "A2"), (A3_OLD, A3_NEW, "A3")]:
    n = src.count(old)
    if n != 1:
        sys.exit("FAIL app.js %s 锚点 %d 处（应 1），不写文件" % (tag, n))
    src = src.replace(old, new, 1)
io.open(P, "w", encoding="utf-8").write(src)
print("app.js PATCHED (%dB)" % len(src))

# ---------- styles.css ----------
P = "web/static/styles.css"
css = io.open(P, encoding="utf-8").read()
C_OLD = """/* R14-L2：心情行两颗入口按钮原 flex-basis:100% 独占一行右对齐，与左侧
   问题+表情按钮之间中段空心（用户截图实况）。≥900px 改同行右置。 */
@media (min-width: 900px){
  .mood-week-link-wrap{ flex-basis:auto; margin-top:0; margin-left:auto; }
}"""
C_NEW = """/* R15-L1（用户实测「这一块很影响用户体验」）：R14-L2 用两个 auto 边距
   把两颗链撑到整行两端、中段空一大片——不协调的根因。改为桌面工具栏：
   问题与表情钮同行（flex-basis:auto），两颗链在右侧成组（首链
   mood-links-lead 推右、次链紧跟 6px 间距），视线一条线走完。
   手机端 order:1 归位——仍排心情历之后，原阅读顺序零变化。 */
@media (min-width: 900px){
  .mood-q{ flex-basis:auto; }
  .mood-week-link-wrap{ flex-basis:auto; margin-top:0; }
  .mood-links-lead{ margin-left:auto; }
}
@media (max-width: 899px){
  .mood-week-link-wrap{ order:1; }
}"""
n = css.count(C_OLD)
if n != 1:
    sys.exit("FAIL styles.css 锚点 %d 处（应 1），不写文件" % n)
css = css.replace(C_OLD, C_NEW, 1)
io.open(P, "w", encoding="utf-8").write(css)
print("styles.css PATCHED (%dB)" % len(css))
