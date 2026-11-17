#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_home_font3.py — R12 验证 v3：curated @font-face 追加到
lxgw.css 响应末尾（该文件由 JS 动态加载，必晚于 styles.css，
而 range 重叠时靠后的 face 胜——实验室已验证）。

测量：字体资源数与字节、全页截图与基线像素对比。
沙箱无 CJK 回退字体 → 未覆盖字=tofu，像素对比即覆盖性验证。
"""
import asyncio
import io

from playwright.async_api import async_playwright

URL = ("http://116.205.229.222/"
       "?key=9022cc97ec4b95325ed6f51faeb6c32e")
FONT = "/workspace/downloads/r12-font/lxgwwenkai-home.woff2"
OUT = "/workspace/downloads/r12-font"
FACE = ("@font-face{font-family:'LXGW WenKai';"
        "src:url('/lxgwwenkai-home.woff2') format('woff2');"
        "unicode-range:U+2000-206F,U+3000-303F,U+3400-4DBF,U+4E00-9FFF,"
        "U+F900-FAFF,U+FE30-FE4F,U+FF00-FFEF;font-display:swap}")


def font_list(pg):
    return pg.evaluate("""() => performance.getEntriesByType('resource')
        .filter(r => /\\.woff2?($|\\?)/.test(r.name))
        .map(r => ({n: r.name.split('/').pop(), b: r.transferSize || 0}))""")


async def run(pg, inject, tag):
    if inject:
        body = io.open(FONT, "rb").read()
        css = await pg.request.get(
            URL.split("?")[0] + "static/fonts/lxgw.css")

        async def css_route(route):
            t = (await css.text()) + "\n/* R12 curated home face */\n" + FACE
            await route.fulfill(status=200, content_type="text/css",
                                body=t)

        async def font_route(route):
            await route.fulfill(status=200, content_type="font/woff2",
                                body=body)

        await pg.route("**/static/fonts/lxgw.css*", css_route)
        await pg.route("**/lxgwwenkai-home.woff2", font_route)
    await pg.goto(URL, wait_until="load")
    await pg.wait_for_timeout(8000)
    fonts = await font_list(pg)
    await pg.screenshot(path="%s/v3_%s.png" % (OUT, tag), full_page=True)
    if inject:
        await pg.unroute("**/static/fonts/lxgw.css*")
        await pg.unroute("**/lxgwwenkai-home.woff2")
    return fonts


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        base = await run(pg, False, "base")
        print("基线：%d 个字体，%.1fKB"
              % (len(base), sum(f["b"] for f in base) / 1024))
        new = await run(pg, True, "new")
        print("注入：%d 个字体，%.1fKB"
              % (len(new), sum(f["b"] for f in new) / 1024))
        for f in sorted(new, key=lambda x: -x["b"])[:6]:
            print("   %-44s %6.1fKB" % (f["n"], f["b"] / 1024))
        await b.close()


asyncio.run(main())
