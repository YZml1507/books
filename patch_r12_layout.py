#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R12：打卡区/今日牌排版修正（用户报四障，全部先实测后开刀）。

实测病灶（scripts/audit.py + 375×812 实拍）：
  1. 今日牌缩略钮：padding+负 margin 在 Chromium flex+gap 下不抵消，
     钮壳 44px vs 图 32px → 图右 12px 死区（用户报「有空隙」）。
  2. 「抽三张」被挤出第二行右侧成孤儿钮（strip 135px）。
  3. 心情钮第 4 枚掉行（.mood-row 269px 装不下 label+4×44px）。
  4. 心情历月点阵 30 枚横溢 46px 出卡（moodCal 315 > 栏 269）。
  5. 未来信入口是打卡区唯一裸文本行，上邻周信卡下接任务卡全是卡面。
  6. 打卡小钮 inline-block 空白符 → 130+127px 两枚在 241px 栏逐枚
     换行，右侧拉三条空带。

修法（零功能删除、零行为变更，仅布局）：
  - 缩略钮命中区改绝对定位 ::after 外扩，布局盒=图尺寸。
  - 「牌意」「抽三张」包 .dc-acts 动作组，整组换行不产孤儿。
  - .mood-q 独占一行 → 4 钮一行；.mood-cal 允许换行+min-width:0。
  - .fl-entry 补 ck-quest 同族软卡底。
  - 打卡小钮包 .ck-share-row 2 列网格。
"""
import io
import sys

CSS = 'web/static/styles.css'
JS = 'web/static/app.js'


def read(p):
    with io.open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(s)


def patch(path, old, new, cnt=1):
    s = read(path)
    n = s.count(old)
    if n != cnt:
        print('FATAL %s: anchor count=%d (expect %d)\n---anchor---\n%s' % (path, n, cnt, old[:200]))
        sys.exit(1)
    write(path, s.replace(old, new, cnt))
    print('OK %s <- %s...' % (path, old.strip().splitlines()[0][:60]))


def main():
    # ── CSS 1：缩略钮命中区（::after 外扩，布局盒=图） ──────────────
    patch(CSS,
          """.daily-card-line .dc-thumb-btn{/* R3432-P2-8（审）：32×52 触摸目标
   * 不足 44px——透明 padding+负 margin 扩命中，视觉分毫不动。 */
  padding:0 12px 0 0; margin:0 -12px 0 0; border:0; background:none;
  cursor:pointer; flex:none; line-height:0; border-radius:4px;
  min-width:44px; min-height:52px;}""",
          """/* R12：透明 padding+负 margin 在 Chromium flex+gap 下不抵消——
 * 实测钮壳 44px vs 图 32px，图右 12px 死区（用户报「有空隙」）。
 * 改绝对定位 ::after 外扩命中区：布局盒严格等于图，视觉分毫不动，
 * 触摸目标仍 ≥44px（右 12 + 上下各 6 外扩）。 */
.daily-card-line .dc-thumb-btn{position:relative; padding:0; margin:0;
  border:0; background:none; cursor:pointer; flex:none; line-height:0;
  border-radius:4px;}
.daily-card-line .dc-thumb-btn::after{content:""; position:absolute;
  top:-6px; bottom:-6px; left:-6px; right:-12px;}""")

    # ── CSS 2：动作组（牌意+抽三张 整组换行，消孤儿） ──────────────
    patch(CSS,
          """.daily-card-line .dc-thumb-btn:focus-visible{
  outline:2px solid var(--primary); outline-offset:1px;}""",
          """.daily-card-line .dc-thumb-btn:focus-visible{
  outline:2px solid var(--primary); outline-offset:1px;}
/* R12：「牌意」「抽三张」包成动作组——窄屏整组换行到第二行
 * 右侧，不再剩一枚孤儿钮独占一行（strip 135px→约 100px）。 */
.daily-card-line .dc-acts{margin-left:auto; display:flex;
  align-items:center; gap:7px; flex:none;}
.daily-card-line .dc-acts .dc-more{margin-left:0;}""")

    # ── CSS 3：心情问句独占一行 → 4 钮一行 ────────────────────────
    patch(CSS,
          '.mood-q{font-size:12px; color:var(--secondary); margin-right:2px;}',
          """/* R12：label+4×44px = 320px > 269px 栏——第 4 枚心情钮掉行
 * 成孤儿。问句独占一行（与 mood-cal/mood-week 同 flex-basis:100%
 * 模式），4 钮 194px 稳居一行。 */
.mood-q{font-size:12px; color:var(--secondary); margin-right:2px;
  flex-basis:100%;}""")

    # ── CSS 4：心情历月点阵收进卡内 ───────────────────────────────
    patch(CSS,
          """.mood-cal{flex-basis:100%; display:flex; align-items:center; gap:4px;
  margin-top:6px;}""",
          """/* R12：月点阵 30 枚 446px 在 269px 栏里横溢 46px 出卡
 * （实测 moodCal 315 > 容器 269，scrollWidth 同步外溢）。
 * flex-wrap + min-width:0 解 flex 项最小内容宽钳制，点阵换行收栏。 */
.mood-cal{flex-basis:100%; min-width:0; display:flex; flex-wrap:wrap;
  align-items:center; gap:4px; margin-top:6px;}""")

    # ── CSS 5：未来信入口补卡面节奏 ───────────────────────────────
    patch(CSS,
          """.fl-entry{display:flex; align-items:baseline; gap:10px;
  margin:4px 0 2px; flex-wrap:wrap;}""",
          """/* R12：打卡区唯一裸文本行——上邻周信卡、下接小功课/旺运/
 * 要紧日子全是卡面，独它一缕带下划线纯文本（用户报「整体格式
 * 有点问题」）。补 ck-quest 同族软卡底归队；下划线/文案不动。 */
.fl-entry{display:flex; align-items:center; gap:10px;
  margin:8px 0 2px; padding:8px 12px; flex-wrap:wrap;
  background:var(--accent-soft); border:1px dashed var(--border);
  border-radius:10px;}""")

    # ── CSS 6：打卡小钮 2 列网格 ─────────────────────────────────
    patch(CSS,
          '.checkin-share:disabled:hover{background:#FFF2EA; transform:none;}',
          """.checkin-share:disabled:hover{background:#FFF2EA; transform:none;}
/* R12：5+ 枚打卡小钮 inline-block + 节点空白符——130+127px 两枚
 * 在 241px 栏里逐枚换行，右侧拉三条空带（实测 5 钮占 5 行）。
 * 包 .ck-share-row 改 2 列等宽网格，纹样归整；按钮 id/行为不动。 */
.ck-share-row{display:grid; grid-template-columns:1fr 1fr; gap:8px;
  margin-top:8px;}
.ck-share-row .checkin-share{margin-top:0; width:100%;
  text-align:center; box-sizing:border-box;}""")

    # ── JS 1：今日牌动作组包裹 ───────────────────────────────────
    patch(JS,
          """          (_dc.meaning
            ? '<button type="button" class="sign-peek" id="tarotPeekBtn"' +
              ' aria-expanded="false" aria-controls="tarotCard">牌意</button>'
            : '') +
          '<button type="button" class="dc-more" id="dailyCardDraw" ' +
          'title="抽一组今天的三张牌">抽三张</button>';""",
          """          /* R12：两枚动作钮包 .dc-acts——窄屏整组换行，不再剩
           * 一枚孤儿钮独占第二行右侧（详见 styles.css 注释）。 */
          '<span class="dc-acts">' +
          (_dc.meaning
            ? '<button type="button" class="sign-peek" id="tarotPeekBtn"' +
              ' aria-expanded="false" aria-controls="tarotCard">牌意</button>'
            : '') +
          '<button type="button" class="dc-more" id="dailyCardDraw" ' +
          'title="抽一组今天的三张牌">抽三张</button></span>';""")

    # ── JS 2：打卡小钮网格容器（开） ─────────────────────────────
    patch(JS,
          """    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>' +
    /* R231d（R37-F15）：连签 ≥3 天给「晒连签」出口——里程碑文案不外溢""",
          """    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>' +
    /* R12：打卡小钮 2 列网格容器——inline-block 空白符致逐枚换行，
     * 右侧拉三条空带（详见 styles.css .ck-share-row 注释）。 */
    '<div class="ck-share-row">' +
    /* R231d（R37-F15）：连签 ≥3 天给「晒连签」出口——里程碑文案不外溢""")

    # ── JS 3：打卡小钮网格容器（闭） ─────────────────────────────
    patch(JS,
          """    '<button type="button" class="checkin-share" id="shopShare" ' +
      'title="把这铺子发给闺蜜">📮 安利铺子</button>' +""",
          """    '<button type="button" class="checkin-share" id="shopShare" ' +
      'title="把这铺子发给闺蜜">📮 安利铺子</button></div>' +""")

    print('R12 patch applied: 8 edits')


if __name__ == '__main__':
    main()
