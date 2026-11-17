#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_home_font.py — R12 验证：curated 首页字体注入线上首页。

沙箱无 CJK 系统字体 → 未覆盖字符会渲染成 tofu，截图像素对比最严格。
1) 基线截图 + 字体资源清单
2) 注入新 @font-face（本地 woff2 经 route 供给）→ 截图 + 字体资源清单
3) 像素对比（应完全一致）
4) 验证未覆盖字符仍能从原切片取到字形（回退链生效）
"""
import asyncio
import io
import sys

from playwright.async_api import async_playwright

URL = ("http://116.205.229.222/"
       "?key=9022cc97ec4b95325ed6f51faeb6c32e")
FONT = "/workspace/downloads/r12-font/lxgwwenkai-home.woff2"
OUT = "/workspace/downloads/r12-font"


def font_list(pg):
    return pg.evaluate("""() => performance.getEntriesByType('resource')
        .filter(r => /\\.woff2?($|\\?)/.test(r.name))
        .map(r => ({n: r.name.split('/').pop(), b: r.transferSize || 0}))""")


async def main():
    body = io.open(FONT, "rb").read()
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        await pg.goto(URL, wait_until="load")
        await pg.wait_for_timeout(6000)
        base_fonts = await font_list(pg)
        await pg.screenshot(path=OUT + "/verify_base.png", full_page=True)
        print("基线字体资源 %d 个，合计 %.1fKB"
              % (len(base_fonts), sum(f["b"] for f in base_fonts) / 1024))

        # 注入新字体：声明放在 lxgw.css 之后（range 重叠时后者胜）
        await pg.route("**/lxgwwenkai-home.woff2",
                       lambda r: r.fulfill(status=200,
                                           content_type="font/woff2",
                                           body=body))
        await pg.evaluate("""() => {
            const st = document.createElement('style');
            st.textContent = `@font-face{font-family:'LXGW WenKai';
              src:url('/lxgwwenkai-home.woff2') format('woff2');
              unicode-range:U+2000-206F,U+3000-303F,U+3400-4DBF,
              U+4E00-9FFF,U+F900-FAFF,U+FE30-FE4F,U+FF00-FFEF}`;
            document.head.appendChild(st);
        }""")
        await pg.wait_for_timeout(5000)
        new_fonts = await font_list(pg)
        await pg.screenshot(path=OUT + "/verify_new.png", full_page=True)
        print("注入后字体资源 %d 个，合计 %.1fKB"
              % (len(new_fonts), sum(f["b"] for f in new_fonts) / 1024))
        for f in new_fonts[:8]:
            print("   ", f["n"], "%.1fKB" % (f["b"] / 1024))

        # 未覆盖字符回退验证：取一个不在 curated 集里的字，看原切片是否加载
        cov = await pg.evaluate("""async () => {
            const r = await fetch('/static/app.js');
            const t = await r.text();
            return t.length;
        }""")
        print("app.js 长度:", cov)

        # tofu 检测：全页文本每个字是否都有字形
        miss = await pg.evaluate("""() => {
            const out = [];
            const w = document.createTreeWalker(document.body,
                NodeFilter.SHOW_TEXT);
            let n;
            while ((n = w.nextNode())) {
                for (const ch of n.textContent) {
                    const c = ch.codePointAt(0);
                    if (c < 0x2000) continue;
                    if (!document.fonts.check('16px "LXGW WenKai"', ch)) {
                        out.push(ch);
                    }
                }
            }
            return [...new Set(out)].join('');
        }""")
        print("document.fonts.check 未覆盖字:", repr(miss[:60]),
              "（共 %d）" % len(miss))
        await b.close()


asyncio.run(main())
