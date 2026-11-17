#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cycle3_audit.py — 周期三深度审计（R11 数据采集，无浏览器环境）。

量什么（全部静态可复现）：
  1. head 资源链：渲染阻塞面（link/script 数量与字节）。
  2. 字体：子集文件字节 + font-display 策略。
  3. 首屏关键图：hero/og-card/gift 字节。
  4. CSS 死代码率：styles.css 里定义的类选择器，有多少在
     index.html + app.js + app_*.js 里零引用（近似，动态模板已扫）。
  5. SW 更新 UX：sw.js/app.js 里有无 updatefound→提示用户的链路。
  6. a11y 基线：skip-link/prefers-reduced-motion/focus-visible/
     aria-live/lang。
  7. 入口可发现性：更多玩法抽屉的 12 卡标签可读性（文案列名）。
  8. 页面元数据：viewport/theme-color/manifest/og 四件套。
"""
import io
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
ST = os.path.join(ROOT, "web", "static")


def rd(p):
    return io.open(p, encoding="utf-8").read()


def sec(t):
    print("\n" + "=" * 12 + " " + t + " " + "=" * 12)


html = rd(os.path.join(ST, "index.html"))
appjs = rd(os.path.join(ST, "app.js"))
css = rd(os.path.join(ST, "styles.css"))
swjs = rd(os.path.join(ST, "sw.js"))

sec("1. head 资源链（渲染阻塞面）")
head = html[html.index("<head>"):html.index("</head>")]
res = re.findall(r'<(link|script)\b[^>]*>', head)
tot = 0
for m in re.finditer(r'<(link|script)\b([^>]*)>', head):
    tag, attrs = m.group(1), m.group(2)
    src = re.search(r'(?:href|src)="([^"]+)"', attrs)
    rel = re.search(r'rel="([^"]+)"', attrs)
    if not src:
        continue
    p = src.group(1)
    local = p.split("?")[0]
    fp = os.path.join(ST, local.replace("/static/", "")) \
        if local.startswith("/static/") else None
    size = os.path.getsize(fp) if fp and os.path.exists(fp) else -1
    if size > 0:
        tot += size
    kind = "script" if tag == "script" else (rel.group(1) if rel else "?")
    defer = " defer" if "defer" in attrs else ""
    print("  %-22s %-18s %8dB%s" % (kind, os.path.basename(local), size,
                                    defer))
print("  head 本地资源合计: %dB" % tot)

sec("2. 字体")
for f in sorted(os.listdir(os.path.join(ST, "fonts"))):
    d = os.path.join(ST, "fonts", f)
    if os.path.isdir(d):
        for g in sorted(os.listdir(d)):
            print("  fonts/%s/%s %dB" % (f, g, os.path.getsize(
                os.path.join(d, g))))
    else:
        print("  fonts/%s %dB" % (f, os.path.getsize(d)))
fd = re.findall(r"font-display\s*:\s*(\w+)", css)
print("  font-display 声明: %s" % (set(fd) or "无（默认 auto=阻塞）"))

sec("3. 首屏关键图")
for p in ("cream/cream-hero-v2.jpg", "shared/og-card.jpg",
          "cream/gift-box.png", "cream/icon-192.png"):
    fp = os.path.join(ST, p)
    if os.path.exists(fp):
        print("  %-28s %dB" % (p, os.path.getsize(fp)))

sec("4. CSS 死代码率")
classes = set(re.findall(r"\.([a-zA-Z_][\w-]*)", css))
blob = html + appjs + swjs
for extra in ("app_poster.js", "app_research.js", "app_wallpaper.js"):
    fp = os.path.join(ST, extra)
    if os.path.exists(fp):
        blob += rd(fp)
used = {c for c in classes if re.search(
    r"[\"'`\s({,;=]%s[\"'`\s)},;:=.]" % re.escape(c), blob)}
dead = sorted(classes - used)
print("  定义类 %d / 引用类 %d / 零引用 %d (%.0f%%)"
      % (len(classes), len(used), len(dead), len(dead) / len(classes) * 100))
print("  零引用样例: %s" % ", ".join(dead[:18]))
css_dead_bytes = sum(len(c) + 2 for c in dead)

sec("5. SW 更新 UX")
print("  updatefound in sw.js:", "updatefound" in swjs)
print("  controllerchange in sw.js:", "controllerchange" in swjs)
print("  app.js 更新提示链路:",
      bool(re.search(r"更新|刷新|新版本", appjs[:200000])) and
      ("controllerchange" in appjs or "updatefound" in appjs))
m = re.search(r"(controllerchange|updatefound)[\s\S]{0,400}", appjs)
if m:
    print("  app.js 片段: %s" % m.group(0)[:200].replace("\n", " "))

sec("6. a11y 基线")
for k, pat in (("skip-link", 'class="skip-link"'),
               ("lang", '<html lang='),
               ("reduced-motion", "prefers-reduced-motion"),
               ("focus-visible", "focus-visible"),
               ("aria-live", "aria-live"),
               ("theme-color", 'name="theme-color"')):
    where = []
    if re.search(pat, html):
        where.append("html")
    if re.search(pat, css):
        where.append("css")
    if re.search(pat, appjs):
        where.append("app.js")
    print("  %-16s %s" % (k, ",".join(where) or "缺失"))

sec("7. 更多玩法抽屉 12 卡标签")
more = html[html.index('id="funcMoreGrid"'):] if 'id="funcMoreGrid"' in html \
    else html[html.index("func-more"):]
labels = re.findall(r'class="fc-name"[^>]*>([^<]+)<', more)
print("  收纳卡: %s" % " / ".join(labels[:14]))
print("  抽屉开关文案:",
      re.findall(r'id="funcMoreBtn"[^>]*>([^<]+)<', html) or "未找到")

sec("8. 元数据四件套")
for k, pat in (("viewport", 'name="viewport"'),
               ("manifest", 'rel="manifest"'),
               ("og:title", 'property="og:title"'),
               ("og:image", 'property="og:image"'),
               ("twitter:card", 'name="twitter:card"')):
    print("  %-14s %s" % (k, "有" if re.search(pat, html) else "缺"))
mf = os.path.join(ST, "manifest.json")
if os.path.exists(mf):
    mj = rd(mf)
    print("  manifest: %dB, icons=%d, display=%s" % (
        len(mj.encode()), mj.count('"src"'),
        re.search(r'"display"\s*:\s*"([^"]+)"', mj).group(1)
        if re.search(r'"display"\s*:\s*"([^"]+)"', mj) else "?"))
