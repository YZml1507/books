#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""home_text_multiday.py — R12：mock 不同日期的 /api/daily 响应，
验证首页是否渲染 API 之外的客户端推算文本（农历/节气/干支/生肖）。
输出追加到 home_text.txt。
"""
import asyncio
import io
import json
import re
import sys

from playwright.async_api import async_playwright

URL = ("http://116.205.229.222/"
       "?key=9022cc97ec4b95325ed6f51faeb6c32e")
OUT = "/workspace/downloads/r12-font/home_text_multiday.txt"
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")
DATES = ["2024-02-10", "2024-03-21", "2024-05-01", "2024-06-10",
         "2024-08-08", "2024-09-17", "2024-11-07", "2024-12-22",
         "2025-01-29", "2025-04-04", "2025-07-15", "2025-10-23"]


async def main():
    texts = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        await pg.goto(URL, wait_until="domcontentloaded")
        await pg.wait_for_timeout(2000)
        for d in DATES:
            try:
                resp = await pg.evaluate("""async (d) => {
                    const r = await fetch('/api/daily?date=' + d);
                    return await r.json();
                }""", d)
            except Exception as e:
                texts.append("### %s ERR %s" % (d, e))
                continue
            await pg.route("**/api/daily*",
                           lambda route: route.fulfill(
                               status=200, content_type="application/json",
                               body=json.dumps(resp, ensure_ascii=False)))
            await pg.reload(wait_until="domcontentloaded")
            await pg.wait_for_timeout(1800)
            t = await pg.evaluate("() => document.body.innerText")
            texts.append("### %s\n%s" % (d, t))
            await pg.unroute("**/api/daily*")
        await b.close()
    all_text = "\n".join(texts)
    io.open(OUT, "w", encoding="utf-8").write(all_text)
    print("12 日期 mock 渲染文本 %d 字符，唯一 CJK %d 字"
          % (len(all_text), len(set(CJK.findall(all_text)))))


asyncio.run(main())
