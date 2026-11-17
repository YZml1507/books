#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""appjs_pools.py — R12：程序化提取 app.js 中日卡/首页渲染路径的
池变量字符串字面量，输出十六进制码点。

定位策略：`var _NAME = [ ... ];` 块 + 指定内联 _dayPick([...]) 数组。
"""
import io
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "app.js"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/r12_appjs_pools.txt"
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")

t = io.open(SRC, encoding="utf-8").read()
chars = set()
got = []

POOL_VARS = ["_DAY_QUOTES", "_MANTRA_POOL", "_MANTRA_FAV_TOAST",
             "_WL_C", "_WL_I", "_WL_F", "_MS", "WARM_EMPATHY"]
for name in POOL_VARS:
    m = re.search(r"var %s\s*=\s*\[" % re.escape(name), t)
    if not m:
        print("  !! 未找到 %s" % name)
        continue
    i = m.end() - 1
    depth = 0
    for j in range(i, len(t)):
        if t[j] == "[":
            depth += 1
        elif t[j] == "]":
            depth -= 1
            if depth == 0:
                break
    block = t[i:j + 1]
    c = set(CJK.findall(block))
    chars |= c
    got.append("%s:%d字" % (name, len(c)))

# 内联 _dayPick([...], 'salt') 数组（首页文案）
INLINE_ANCHORS = ["「缓」不是坏日子", "点我看明天", "小满第 ",
                  "🎀 ", "新的一天到啦", "新的一周，日子翻开"]
for a in INLINE_ANCHORS:
    k = t.find(a)
    if k < 0:
        print("  !! 未找到内联锚点 %r" % a)
        continue
    s = t.rfind("[", 0, k)
    if s < 0:
        continue
    depth = 0
    for j in range(s, len(t)):
        if t[j] == "[":
            depth += 1
        elif t[j] == "]":
            depth -= 1
            if depth == 0:
                break
    chars |= set(CJK.findall(t[s:j + 1]))

print("### app.js 首页池提取")
print("  " + "  ".join(got))
print("  合计唯一 CJK %d 字" % len(chars))
io.open(OUT, "w", encoding="utf-8").write(
    ",".join("%X" % ord(c) for c in sorted(chars)))
print("  已写 %s" % OUT)
