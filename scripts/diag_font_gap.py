#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_font_gap.py — R12 诊断：注入 curated 字体后，
逐个已渲染字符检测是否由 curated 文件提供字形；
并报告触发原切片加载的字符及其宿主元素。
"""
import asyncio
import base64
import io

from playwright.async_api import async_playwright

URL = ("http://116.205.229.222/"
       "?key=9022cc97ec4b95325ed6f51faeb6c32e")
FONT = "/workspace/downloads/r12-font/lxgwwenkai-home.woff2"
FACE = ("@font-face{font-family:'LXGW WenKai';"
        "src:url('/lxgwwenkai-home.woff2') format('woff2');"
        "unicode-range:U+2000-206F,U+3000-303F,U+3400-4DBF,U+4E00-9FFF,"
        "U+F900-FAFF,U+FE30-FE4F,U+FF00-FFEF;font-display:swap}")


async def main():
    body = io.open(FONT, "rb").read()
    b64 = base64.b64encode(body).decode()
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        css = await pg.request.get(
            URL.split("?")[0] + "static/fonts/lxgw.css")

        async def css_route(route):
            t = (await css.text()) + "\n/* R12 */\n" + FACE
            await route.fulfill(status=200, content_type="text/css",
                                body=t)

        async def font_route(route):
            await route.fulfill(status=200, content_type="font/woff2",
                                body=body)

        await pg.route("**/static/fonts/lxgw.css*", css_route)
        await pg.route("**/lxgwwenkai-home.woff2", font_route)
        await pg.goto(URL, wait_until="load")
        await pg.wait_for_timeout(8000)

        r = await pg.evaluate("""async (b64) => {
            const ff = new FontFace('probe',
                'url(data:font/woff2;base64,' + b64 + ')');
            try { await ff.load(); } catch (e) { return {err: '' + e}; }
            document.fonts.add(ff);
            const w = document.createTreeWalker(document.body,
                NodeFilter.SHOW_TEXT);
            const miss = {};
            let n;
            while ((n = w.nextNode())) {
                const el = n.parentElement;
                const cls = el ? (el.className || el.tagName) : '?';
                for (const ch of n.textContent) {
                    const c = ch.codePointAt(0);
                    if (c < 0x2000) continue;
                    if (!document.fonts.check('16px probe', ch)) {
                        const k = ch;
                        miss[k] = miss[k] || {n: 0, cls: []};
                        miss[k].n++;
                        if (miss[k].cls.length < 2 && cls)
                            miss[k].cls.push(String(cls).slice(0, 40));
                    }
                }
            }
            return {miss: miss};
        }""", b64)
        if "err" in r:
            print("probe 加载失败:", r["err"])
            await b.close()
            return
        miss = r["miss"]
        print("curated 未覆盖的已渲染字 %d 个:" % len(miss))
        for ch, v in sorted(miss.items()):
            print("   %s ×%d  in %s" % (ch, v["n"], v["cls"]))
        fonts = await pg.evaluate("""() => performance
            .getEntriesByType('resource')
            .filter(r => /\\.woff2?($|\\?)/.test(r.name))
            .map(r => r.name.split('/').pop())""")
        print("加载的字体:", fonts)
        await b.close()


asyncio.run(main())
