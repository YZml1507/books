#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-2：daily-meta 展开/收起钮移出药丸流（CYCLE5_PLAN 任务三 §3.2-A）

现役锚点：
  app.js:22596-22606（_dailyMetaCap 内 _more 创建块）
    if (!_more) {
      _more = document.createElement('button');
      _more.id = 'dailyMetaMore'; _more.type = 'button';
      _more.className = 'daily-meta-item daily-meta-more';
      _metaRow.appendChild(_more);
      _more.addEventListener('click', function () {...});
    }
  styles.css:707  .daily-meta-more{cursor:pointer; font:inherit; color:var(--accent-ink);}

病灶（CYCLE5_PLAN §3.1，1440×900 实测）：
  · 钮与内容粒共用 class daily-meta-item → 长得跟「开运色」一样是颗药丸，
    用户认不出它是控件；
  · appendChild 进 flex 流末尾 → 展开态下被埋到长长一串参差药丸的尽头
    （截图里夹在「财神方位」与「下周早知道」中间），位置随 wrap 浮动；
  · 实测 h=58 且 y=80，同行内容粒 h=78/y=60 → 与同行不对齐；
  · 390px 横滚态下它在横滚区第 7 颗，要滑到底才看得见。
处方：自立成安静文本行，恒定跟在药丸流正下方；老会话就地迁移不重建。
零逻辑改动：data-capped / dataset.expanded / '+N 条' 计数 / pin 机制全不碰。
"""
import io, sys

APP = "/opt/books/app/web/static/app.js"
CSS = "/opt/books/app/web/static/styles.css"

JS_OLD = """  if (!_more) {
    _more = document.createElement('button');
    _more.id = 'dailyMetaMore'; _more.type = 'button';
    _more.className = 'daily-meta-item daily-meta-more';
    _metaRow.appendChild(_more);
    _more.addEventListener('click', function () {
      _metaRow.dataset.expanded =
        _metaRow.dataset.expanded === '1' ? '' : '1';
      _dailyMetaCap();
    });
  }"""

JS_NEW = """  if (!_more) {
    _more = document.createElement('button');
    _more.id = 'dailyMetaMore'; _more.type = 'button';
    /* R20（用户直报）：移出药丸流——自立安静文本行，不再跟内容粒
     * 共用 daily-meta-item class（否则长得像「开运色」一样是颗药丸，
     * 展开态又被 appendChild 埋到参差药丸尽头，位置随 wrap 浮动）。 */
    _more.className = 'daily-meta-more';
    _metaRow.parentNode.insertBefore(_more, _metaRow.nextSibling);
    _more.addEventListener('click', function () {
      _metaRow.dataset.expanded =
        _metaRow.dataset.expanded === '1' ? '' : '1';
      _dailyMetaCap();
    });
  } else {
    /* R20（用户直报）：旧版钮 appendChild 在 .daily-meta 里、还带
     * daily-meta-item class——就地迁出自立行并去掉药丸 class，
     * 老会话不必等节点重建（id 不变，事件监听留着）。 */
    _more.className = 'daily-meta-more';
    if (_more.parentNode !== _metaRow.parentNode ||
        _more.previousElementSibling !== _metaRow) {
      _metaRow.parentNode.insertBefore(_more, _metaRow.nextSibling);
    }
  }"""

CSS_OLD = """.daily-meta-more{cursor:pointer; font:inherit; color:var(--accent-ink);}   /* R2514：装饰色2.12:1→文字色4.87:1 */"""

CSS_NEW = """/* R20（用户直报）：展开/收起钮自立成行——不再塞进 .daily-meta 药丸流，
 * 也不再用 daily-meta-item 药丸样式（实测旧态 h=58/y=80，与同行 78px
 * 粒不对齐，且展开后被埋到参差药丸尽头）。安静文本钮，恒定跟在药丸流
 * 正下方；窄屏横滚态下它在横滚区外面，不用滑到底。 */
.daily-meta-more{display:block; width:100%; box-sizing:border-box;
  margin-top:6px; padding:5px 4px; text-align:left;
  background:none; border:0; border-radius:8px;
  font:inherit; font-size:12px; color:var(--accent-ink); cursor:pointer;
  transition:background .15s;}
.daily-meta-more:hover{background:var(--accent-soft);}"""


def main():
    with io.open(APP, "r", encoding="utf-8") as f:
        a = f.read()
    n = a.count(JS_OLD)
    if n != 1:
        sys.exit("FAIL: app.js anchor count=%d（预期 1）" % n)
    if "R20（用户直报）：移出药丸流" not in a:
        a = a.replace(JS_OLD, JS_NEW, 1)
    else:
        sys.exit("FAIL: app.js 已打过 R20-2")
    with io.open(APP, "w", encoding="utf-8") as f:
        f.write(a)

    with io.open(CSS, "r", encoding="utf-8") as f:
        c = f.read()
    m = c.count(CSS_OLD)
    if m != 1:
        sys.exit("FAIL: styles.css anchor count=%d（预期 1）" % m)
    if "R20（用户直报）：展开/收起钮自立成行" in c:
        sys.exit("FAIL: styles.css 已打过 R20-2")
    c = c.replace(CSS_OLD, CSS_NEW, 1)
    with io.open(CSS, "w", encoding="utf-8") as f:
        f.write(c)
    print("app.js + styles.css PATCHED (R20-2 meta 收起钮移出药丸流)")


if __name__ == "__main__":
    main()
