#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R6（周期二·首页 IA 重构）服务器原位补丁。

改什么（D-906，依据 docs/CYCLE2_PLAN.md 调研结论）：
  1. index.html：撤销新人条 welcome-bar（NN/g：能通过使用学会的界面
     不该有教学引导；场景条+功能卡已自解释，新人条退化为重复元素）。
     probe_ui_smoke 同名用例翻转成反向钉扎（不得回潮）。
  2. index.html：撤销 head 内联 welcomed 预绘脚本（唯一职责就是新人条
     消 CLS；app.js 侧老用户补写逻辑原样保留，互不依赖）。
  3. index.html：日卡动作组 .daily-ghost-grid（分享图/文案/护身符/
     壁纸/头像/日历 6 钮）从 daily-top（判词之前）整体平移到
     daily-meta 之后、dailyMore 之前——「先通读，再带走」，
     把视觉重心还给今日运势本身（选择悖论/渐进披露：不为当前任务
     准备的元素即噪音）。功能零删除，纯 DOM 序调整。
  4. styles.css：.daily-ghost-grid  margin-top:2px → margin:14px 0 2px
     （脱离 daily-top 后的块间距；卡本身 32px 横向内距不变）。
  5. web/selftest.py：home.ia 增补 R6 两针（新人条不得回潮 +
     动作组必须排在内容之后）——只增不减。
  6. probes/probe_ui_smoke.py：ui:welcome_bar 用例翻转（存在→不存在），
     用例不删、名字不变，改断言方向。

纪律：全部精确字符串替换，锚点计数必须为 1，缺任一锚点即整体报错退出，
不落半成品。本地与服务器两套基线分别跑（selftest 两线有 F-01 差异，
但本补丁锚点均在共同区）。
"""
import io
import sys


def _rd(p):
    return io.open(p, encoding="utf-8").read()


def _wr(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def _rep(src, old, new, what, path):
    n = src.count(old)
    assert n == 1, "%s：锚点命中 %d 次（要求 1）——%s 已漂移？未落盘" % (
        path, n, what)
    return src.replace(old, new)


def patch_index(p):
    s = _rd(p)

    # ── 1. 撤销新人条 ──────────────────────────────────────────────
    old_bar = (
        '  <div id="welcomeBar" class="welcome-bar" role="note">\n'
        '    <span class="welcome-txt">\u7b2c\u4e00\u6b21\u6765\uff1f\u70b9'
        '\u4e00\u5f20\u5361\u5c31\u80fd\u6d4b\uff0c\u5854\u7f57 \u00b7 \u6843'
        '\u82b1 \u00b7 \u5408\u5a5a \u00b7 \u9ec4\u5386\u90fd\u6709 \u2728'
        '</span>\n'
        '    <button type="button" class="welcome-close" aria-label="'
        '\u77e5\u9053\u4e86">\u00d7</button>\n'
        '  </div>\n')
    new_bar = (
        '  <!-- R6\uff08\u5468\u671f\u4e8c\u00b7\u9996\u9875 IA\uff09\uff1a'
        '\u65b0\u4eba\u6761\u64a4\u9500\u3002NN/g \u79fb\u52a8\u7aef onboarding'
        '\u7ed3\u8bba\u2014\u2014\u201c\u80fd\u901a\u8fc7\u4f7f\u7528\u5b66'
        '\u4f1a\u7684\u754c\u9762\u4e0d\u8be5\u6709\u6559\u5b66\u5f15\u5bfc'
        '\u201d\uff1b\u573a\u666f\u6761+\u529f\u80fd\u5361\u5df2\u81ea\u89e3'
        '\u91ca\uff0c\u65b0\u4eba\u6761\u4ece\u5f15\u5bfc\u9000\u5316\u4e3a'
        '\u4e0e\u573a\u666f\u6761\u91cd\u590d\u7684\u7b2c\u4e09\u5957\u5bfb'
        '\u822a\u3002\u8bba\u8bc1\u89c1 D-906\uff1bprobe_ui_smoke \u540c\u540d'
        '\u7528\u4f8b\u5df2\u7ffb\u8f6c\u4e3a\u53cd\u5411\u9489\u624e\u3002 -->\n')
    s = _rep(s, old_bar, new_bar, "welcome-bar \u5143\u7d20", p)
    # ── 1b. R2348 注释随被撤元素作废（保留史注，删失效描述）──────
    old_stale = (
        '<!-- R2348\uff08R67-P1\uff09\uff1awelcome-bar \u9759\u6001\u6e32'
        '\u67d3\u6d88 CLS\u2014\u2014bar \u5728\u9996\u5e27\u5c31\u5360\u4f4d\uff0c\n'
        '     \u8001\u7528\u6237\u7531 head \u5185\u8054\u811a\u672c\u5728\u9996'
        '\u6b21\u7ed8\u5236\u524d\u6253 welcomed \u7c7b\u85cf\u6389\uff0c'
        '\u96f6\u4f4d\u79fb\u3002 -->\n')
    new_stale = (
        '<!-- R2348\uff08R67-P1\uff09\uff1awelcome-bar \u9759\u6001\u6e32'
        '\u67d3\u6d88 CLS\u2014\u2014\u5df2\u968f R6 \u64a4\u9500\uff0c'
        '\u672c\u6ce8\u91ca\u53ea\u4f5c\u53f2\u6ce8\u3002 -->\n')
    s = _rep(s, old_stale, new_stale, "R2348 \u5931\u6548\u6ce8\u91ca", p)

    # ── 2. 撤销 head welcomed 预绘脚本（行区间+首末行断言）──────────
    lines = s.split("\n")
    i0 = next(i for i, l in enumerate(lines)
              if l.startswith("<script>try{var _w=window.localStorage"
                              ".getItem('welcomed');"))
    i1 = next(i for i, l in enumerate(lines)
              if "classList.add('welcomed')" in l and l.rstrip().endswith(
                  "</script>"))
    assert i1 > i0 >= 0, "head \u811a\u672c\u533a\u95f4\u5f02\u5e38"
    assert lines[i1 - 1].strip().endswith("}"), "head \u811a\u672c\u672b\u884c"\
        " \u5f62\u6001\u5f02\u5e38\uff1a%r" % lines[i1 - 1]
    repl = [
        '<!-- R6\uff08\u5468\u671f\u4e8c\u00b7\u9996\u9875 IA\uff09\uff1a'
        'welcomed \u9884\u7ed8\u9690\u85cf\u811a\u672c\u968f\u65b0\u4eba\u6761'
        '\u4e00\u8d77\u64a4\u9500\u2014\u2014\u5b83\u552f\u4e00\u7684\u804c'
        '\u8d23\u5c31\u662f\u7ed9\u65b0\u4eba\u6761\u6d88 CLS\u3002app.js '
        '\u5085\u5c42\u7684\u8001\u7528\u6237\u8865\u5199\uff08\u8bbf\u6b21>1'
        '/checkin:\u952e\uff09\u4e0e\u5b58\u50a8\u4e8b\u4ef6\u76d1\u542c'
        '\u539f\u6837\u4fdd\u7559\uff0c\u4e0e\u672c\u811a\u672c\u65e0\u4f9d'
        '\u8d56\u3002 -->',
    ]
    lines[i0:i1 + 1] = repl
    s = "\n".join(lines)

    # ── 3. 动作组平移到通读内容之后 ────────────────────────────────
    lines = s.split("\n")
    g0 = next(i for i, l in enumerate(lines)
              if l == '    <div class="daily-ghost-grid">')
    g1 = next(i for i, l in enumerate(lines)
              if l.startswith('    <!-- R2363\uff08R117-P0-1\uff09'))
    assert g1 > g0, "ghost-grid \u533a\u95f4\u5f02\u5e38"
    block = lines[g0:g1]
    assert block[-1].strip() == "</div>", \
        "ghost-grid \u5757\u672b\u884c\u5e94\u4e3a </div>\uff1a%r" % block[-1]
    # 删除时连带吃掉块前空行，保持版面干净
    if lines[g0 - 1].strip() == "":
        del lines[g0 - 1:g1]
        g0 -= 1
    else:
        del lines[g0:g1]
    # 插到 daily-xingzuo 之后、dailyMore 之前
    ins = next(i for i, l in enumerate(lines)
               if 'R228c' in l and 'loadDailyDetail' in l)
    lines[ins:ins] = block
    s = "\n".join(lines)

    _wr(p, s)
    print("%s: \u65b0\u4eba\u6761\u5df2\u64a9\u3001ghost \u7ec4\u5df2\u5e73"
          "\u79fb" % p)


def patch_css(p):
    s = _rd(p)
    old = (".daily-ghost-grid{display:flex; flex-wrap:wrap; gap:2px 6px; "
           "margin-top:2px;}")
    new = (".daily-ghost-grid{display:flex; flex-wrap:wrap; gap:2px 6px; "
           "margin:14px 0 2px;}")
    s = _rep(s, old, new, ".daily-ghost-grid \u89c4\u5219", p)
    _wr(p, s)
    print("%s: ghost \u7ec4\u5757\u8fb9\u8ddd\u5df2\u968f\u4f4d\u7f6e\u8c03"
          "\u6574" % p)


def patch_selftest(p):
    s = _rd(p)
    old = ('    assert "dataset.view === \'chat\'" in _appsrc_g and \\\n'
           '        "chatOpen(); return" in _appsrc_g, \\\n'
           '        ("home.ia.chat-card-wiring",)\n'
           '    ok.append("home.ia")\n')
    new = ('    assert "dataset.view === \'chat\'" in _appsrc_g and \\\n'
           '        "chatOpen(); return" in _appsrc_g, \\\n'
           '        ("home.ia.chat-card-wiring",)\n'
           '    # R6\uff08\u5468\u671f\u4e8c\u00b7\u9996\u9875 IA\uff09\uff1a'
           '\u65b0\u4eba\u6761\u64a4\u9500\u53cd\u5411\u9489\u624e\u9632'
           '\u56de\u6f6f\uff1b\u65e5\u5361\u52a8\u4f5c\u7ec4\u5fc5\u987b'
           '\u6392\u5728\u5224\u8bcd\u4e4b\u540e\uff08\u201c\u5148\u901a'
           '\u8bfb\uff0c\u518d\u5e26\u8d70\u201d\uff0cD-906\uff09\u3002\n'
           '    assert \'id="welcomeBar"\' not in home.text, \\\n'
           '        ("home.ia.no-welcome-bar",)\n'
           '    assert _home_seg.index("daily-ghost-grid") > \\\n'
           '        _home_seg.index("daily-main"), \\\n'
           '        ("home.ia.ghost-after-content",)\n'
           '    ok.append("home.ia")\n')
    s = _rep(s, old, new, "home.ia \u95ed\u5408\u5757", p)
    _wr(p, s)
    print("%s: home.ia R6 \u4e24\u9488\u5df2\u8865\uff08\u53ea\u589e\u4e0d"
          "\u51cf\uff09" % p)


def patch_probe(p):
    s = _rd(p)
    old_cmt = ("            # R231d\uff08R37-F4/F7\uff09\uff1a\u9996\u8bbf"
               "\u5e94\u6709\u65b0\u4eba\u6761\uff1b\u5173\u6389\u540e"
               "\u5237\u65b0\u4e0d\u518d\u51fa\u73b0\u3002\n")
    new_cmt = ("            # R6\uff08\u5468\u671f\u4e8c\u00b7\u9996\u9875 "
               "IA\uff09\uff1a\u65b0\u4eba\u6761\u64a4\u9500\uff08D-906"
               "\uff09\u2014\u2014\u7528\u4f8b\u4e0d\u5220\u3001\u540d\u5b57"
               "\u4e0d\u53d8\uff0c\u65ad\u8a00\u7ffb\u8f6c\u4e3a\u53cd\u5411"
               "\u9489\u624e\uff08\u4e0d\u5f97\u56de\u6f6f\uff09\u3002\n")
    s = _rep(s, old_cmt, new_cmt, "probe \u6ce8\u91ca", p)
    old_eval = ('                    " return !!(w && w.offsetParent !== '
                'null); }")')
    new_eval = '                    " return !w; }")'
    s = _rep(s, old_eval, new_eval, "probe evaluate", p)
    old_det = ('                    "detail": "\u9996\u8bbf\u65b0\u4eba'
               '\u6761\u5b58\u5728=%s" % wv})')
    new_det = ('                    "detail": "\u65b0\u4eba\u6761\u5df2'
               '\u64a4\u9500\uff08R6 \u53cd\u5411\u9489\u624e\uff09=%s" % '
               'wv})')
    s = _rep(s, old_det, new_det, "probe detail", p)
    _wr(p, s)
    print("%s: ui:welcome_bar \u7528\u4f8b\u5df2\u7ffb\u8f6c" % p)


def main():
    jobs = [
        (patch_index, "web/static/index.html"),
        (patch_css, "web/static/styles.css"),
        (patch_selftest, "web/selftest.py"),
        (patch_probe, "probes/probe_ui_smoke.py"),
    ]
    for fn, p in jobs:
        fn(p)
    print("R6 \u8865\u4e01\u5168\u90e8\u843d\u76d8")


if __name__ == "__main__":
    sys.exit(main())
