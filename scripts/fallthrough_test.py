#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fallthrough_test.py — R12 前置验证：同 font-family 下，
靠前的 @font-face 声明了宽 unicode-range 但缺某字字形时，
浏览器会不会继续用靠后的 @font-face 渲染该字。

构建两个测试字：fontA 只有 'A'（加宽 3 倍字宽），fontB 有 'A'（正常）
和 'B'（加宽 3 倍）。CSS 里 A 在前、宽 range；B 在后、精确 range。
量 'A' 与 'B' 的渲染宽度 → 判定回退行为。
"""
import os
import subprocess

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

D = "/workspace/downloads/r12-font/ft"
os.makedirs(D, exist_ok=True)
SRC = "/workspace/downloads/r12-font/slices/lxgwwenkai-regular-subset-100.woff2"


def build(keep, widen, out):
    ft = TTFont(SRC)
    subprocess.run(["fonttools", "subset", SRC, "--unicodes=" + keep,
                    "--flavor=woff2", "--output-file=" + out],
                   check=True, capture_output=True)
    ft = TTFont(out)
    cm = ft.getBestCmap()
    for cp, gname in cm.items():
        if chr(cp) in widen:
            lsb, adv = ft["hmtx"].metrics[gname]
            ft["hmtx"].metrics[gname] = (lsb, adv * 3)
    ft.save(out)


# 'A' 用 U+4E00（必在切片4？未必）——改用确定存在的字：
# 先看切片4 的 cmap 前几字
ft0 = TTFont(SRC)
cps = sorted(ft0.getBestCmap().keys())
a_cp = cps[0]
b_cp = cps[1]
print("测试字: A=U+%04X B=U+%04X" % (a_cp, b_cp))
build("%X" % a_cp, chr(a_cp), D + "/A.woff2")           # 只有 A，加宽
build("%X,%X" % (a_cp, b_cp), chr(b_cp), D + "/B.woff2")  # A 正常 + B 加宽

html = """<!doctype html><meta charset="utf-8">
<style>
@font-face{font-family:T;src:url(A.woff2);unicode-range:U+0000-FFFF}
@font-face{font-family:T;src:url(B.woff2);unicode-range:U+0000-FFFF}
span{font-family:T;font-size:100px;display:inline-block}
</style>
<span id=sa>&#%d;</span><span id=sb>&#%d;</span>
""" % (a_cp, b_cp)
open(D + "/t.html", "w").write(html)

import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page()
        await pg.goto("http://127.0.0.1:8899/t.html")
        await pg.wait_for_timeout(1200)
        w = await pg.evaluate("""() => ({
            a: document.getElementById('sa').getBoundingClientRect().width,
            b: document.getElementById('sb').getBoundingClientRect().width,
        })""")
        # 参考宽度：A 在 A.woff2 加宽 3x；B 在 B.woff2 加宽 3x
        print("渲染宽度: A=%.1f B=%.1f" % (w["a"], w["b"]))
        print("判定: A 宽 → 靠前 face 命中（预期）")
        print("      B 宽 → 缺字回退成立（方案可行）")
        print("      B≈0/系统宽 → 回退不成立（方案不可行）")
        await b.close()


asyncio.run(main())
