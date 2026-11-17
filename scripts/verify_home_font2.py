#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_home_font2.py — R12 验证 v2：把 curated @font-face 追加进
styles.css 的响应体（从解析时就位），整页重载后测量：
1) 字体资源数量与字节（应 1 个 curated + zcool + smiley）
2) 全页截图与基线逐像素对比（沙箱无 CJK 回退字体 → 未覆盖字=tofu）
3) 逐字符字形可用性（直接查 FontFace 的 cmap，不用 check()）
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


async def run(pg, inject):
    if inject:
        body = io.open(FONT, "rb").read()

        css = await pg.request.get(URL.split("?")[0] + "static/styles.css")

        async def css_route(route):
            t = (await css.text()) + "\n" + FACE
            await route.fulfill(status=200,
                                content_type="text/css", body=t)

        async def font_route(route):
            await route.fulfill(status=200,
                                content_type="font/woff2", body=body)

        await pg.route("**/static/styles.css*", css_route)
        await pg.route("**/lxgwwenkai-home.woff2", font_route)
    await pg.goto(URL, wait_until="load")
    await pg.wait_for_timeout(7000)
    fonts = await font_list(pg)
    await pg.screenshot(path=OUT + "/v2_%s.png" % ("new" if inject else "base"),
                        full_page=True)
    if inject:
        await pg.unroute("**/static/styles.css*")
        await pg.unroute("**/lxgwwenkai-home.woff2")
    return fonts


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        base = await run(pg, False)
        print("基线：%d 个字体，%.1fKB"
              % (len(base), sum(f["b"] for f in base) / 1024))
        new = await run(pg, True)
        print("注入：%d 个字体，%.1fKB"
              % (len(new), sum(f["b"] for f in new) / 1024))
        for f in sorted(new, key=lambda x: -x["b"])[:6]:
            print("   %-42s %6.1fKB" % (f["n"], f["b"] / 1024))

        # 逐字符：用 FontFace API 直接问 curated 文件的 cmap
        import base64
        b64 = base64.b64encode(io.open(FONT, "rb").read()).decode()
        cov = await pg.evaluate("""async (b64) => {
            const ff = new FontFace('probe',
                'url(data:font/woff2;base64,' + b64 + ')');
            await ff.load();
            document.fonts.add(ff);
            const w = document.createTreeWalker(document.body,
                NodeFilter.SHOW_TEXT);
            const miss = [];
            let n;
            while ((n = w.nextNode())) {
                for (const ch of n.textContent) {
                    const c = ch.codePointAt(0);
                    if (c < 0x2000) continue;
                    if (!document.fonts.check('16px probe', ch)) miss.push(ch);
                }
            }
            return [...new Set(miss)];
        }""", b64)
        print("curated 文件未覆盖的已渲染字:", "".join(cov) or "（无）")
        await b.close()


asyncio.run(main())
