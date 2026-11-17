#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_home_budget.py — 首屏垂直预算与 clutter 静态测量（R7，D-907）。

**为什么不用浏览器**：服务器无 playwright/chromium（已实测），为一次
测量给生产机装 150MB 浏览器违背最小足迹；本项目自己的
probe_first_screen.py 需要浏览器环境，此处不可复现。

**方法论（诚实声明局限）**：无布局引擎，高度用「CSS 推导固定高度 +
内容行数估算」，假设全部写死在 HEIGHT_HINTS 里可复查；绝对像素是
估算，**before/after 同口径对比**才是有效信号（测量的是 R6 的 delta，
不是给设计师当施工图）。

测量口径（specs/003 基线视口 375×812）：
  A. clutter：入口区（scene-bar）之上的一切——元素总数、可交互元素
     数（button/a/[role=button]）、纯装饰元素数。用户原话「东西很乱」
     的直接代理。
  B. 垂直预算：自 body 顶到 scene-bar 的估算像素 / 屏数。
  C. 日卡内部：判词（daily-main）之前 vs 之后的可交互元素数——
     R6 的靶子（动作组抢在内容前）。
  D. 传输：页面原始字节 + gzip 后字节。
"""
import gzip
import html.parser
import io
import re
import sys

# CSS 推导的固定高度（px）。查自 styles.css 当前值；内容驱动块用
# 行数×行高估算（见 CONTENT_HINTS）。每一项都可 grep 复核。
HEIGHT_HINTS = {
    "hero": 190,          # ink-hero-wrap：min-height 查证
    "brand": 64,          # brand 图标+店名+副标题两行
    "daily_card_pad": 56,  # .daily-card padding:28px 32px（上下 56）
    "daily_top": 44,      # label+date+礼盒一行
    "daily_main": 150,    # level 盒 108px 固定 + 判词/维度/咒语行
    "daily_checkin": 64,  # 打卡条
    "daily_meta": 84,     # 贵人/宜试试/先缓缓 三粒 + ritual 钮
    "daily_xingzuo": 0,   # hidden 默认
    "daily_disclaimer": 20,
    "daily_more": 40,
    "ghost_row": 36,      # 375px 下 flex 1 1 44% → 每行 2 钮
    "daily_ask": 128,     # 生日表单（新客无档案时出现）
    "scene_bar": 52,
    "install_row": 56,
}
INTERACTIVE = re.compile(r"<(button|a)\b", re.I)


class _P(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.counts = {}
        self.inter = 0
        self.imgs = 0

    def handle_starttag(self, tag, attrs):
        self.counts[tag] = self.counts.get(tag, 0) + 1
        if tag in ("button", "a"):
            self.inter += 1
        if tag == "img":
            self.imgs += 1
        if tag not in ("img", "br", "input", "meta", "link", "hr"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i:]
                break


def measure(path):
    s = io.open(path, encoding="utf-8").read()
    p = _P()
    p.feed(s)
    total_el = sum(p.counts.values())

    # ── A. 入口区之上的 clutter（scene-bar 位置切分）────────────
    i_scene = s.index('class="scene-bar"')
    i_body = s.index("<body")
    above = s[i_body:i_scene]
    pa = _P()
    pa.feed(above)
    above_el = sum(pa.counts.values())
    above_inter = pa.inter
    above_imgs = pa.imgs

    # ── C. 日卡：判词之前/之后的可交互元素 ─────────────────────
    i_card = s.index('class="daily-card"')
    i_main = s.index('class="daily-main"')
    i_more = s.index('id="dailyMore"')
    before_main = s[i_card:i_main]
    after_main = s[i_main:i_more]
    pb, pm = _P(), _P()
    pb.feed(before_main)
    pm.feed(after_main)

    # ── B. 垂直预算（自 hero 顶到 scene-bar 底）────────────────
    has_welcome = 'id="welcomeBar"' in s
    ghost_before = s.index("daily-ghost-grid") < i_main
    ask_visible = True  # 新客无档案时 dailyAsk 出现（保守按出现计）
    h = (HEIGHT_HINTS["hero"] + HEIGHT_HINTS["brand"]
         + HEIGHT_HINTS["daily_card_pad"]
         + HEIGHT_HINTS["daily_top"]
         + (44 if has_welcome else 0)          # 新人条
         + HEIGHT_HINTS["daily_main"]
         + HEIGHT_HINTS["daily_checkin"]
         + HEIGHT_HINTS["daily_meta"]
         + HEIGHT_HINTS["daily_xingzuo"]
         + HEIGHT_HINTS["daily_disclaimer"]
         + HEIGHT_HINTS["ghost_row"] * 3       # 6 钮 @375px → 3 行
         + HEIGHT_HINTS["daily_more"]
         + (HEIGHT_HINTS["daily_ask"] if ask_visible else 0)
         + HEIGHT_HINTS["scene_bar"])
    screens = h / 812

    raw = len(s.encode("utf-8"))
    gz = len(gzip.compress(s.encode("utf-8"), 6))
    return {
        "file": path,
        "总元素": total_el,
        "入口区上方元素": above_el,
        "入口区上方可交互": above_inter,
        "入口区上方图片": above_imgs,
        "日卡判词前可交互": pb.inter,
        "日卡判词后可交互": pm.inter,
        "ghost 在判词前": ghost_before,
        "有新人条": has_welcome,
        "到入口区估算 px": h,
        "屏数": round(screens, 2),
        "原始 KB": round(raw / 1024, 1),
        "gzip KB": round(gz / 1024, 1),
    }


if __name__ == "__main__":
    rows = [measure(p) for p in sys.argv[1:]]
    keys = list(rows[0].keys())
    w = max(len(k) for k in keys)
    print(" " * w + "  " + "  ".join("%-14s" % ("R6前" if i == 0 else "R6后")
                                     for i in range(len(rows))))
    for k in keys:
        cells = []
        for r in rows:
            v = r[k]
            cells.append("%-14s" % (str(v) if not isinstance(v, bool)
                                    else ("是" if v else "否")))
        print("%-*s  %s" % (w, k, "  ".join(cells)))
