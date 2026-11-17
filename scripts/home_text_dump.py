#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""home_text_dump.py — R12：浏览器实测首页可见文本。

抓：首页 innerText、抽屉全文、填生日表单后的日卡（personal 行）、
以及首页所有 DOM 文本节点（含隐藏 overlay 的，一次性全收）。
输出 /workspace/downloads/r12-font/home_text.txt。
"""
import asyncio
import io
import re
import sys

from playwright.async_api import async_playwright

URL = ("http://116.205.229.222/"
       "?key=9022cc97ec4b95325ed6f51faeb6c32e")
OUT = "/workspace/downloads/r12-font/home_text.txt"
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")


async def main():
    texts = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 375, "height": 812})
        await pg.goto(URL, wait_until="domcontentloaded")
        await pg.wait_for_timeout(2500)

        async def dump(tag):
            t = await pg.evaluate(
                "() => document.body.innerText")
            texts.append("### " + tag + "\n" + t)

        await dump("home-visible")
        # 全量 DOM 文本（含隐藏 overlay/drawer）
        t = await pg.evaluate(
            "() => { const w = document.createTreeWalker("
            "document.body, NodeFilter.SHOW_TEXT); const o = [];"
            "let n; while ((n = w.nextNode())) { const s = n.textContent"
            ".trim(); if (s) o.push(s); } return o.join('\\n'); }")
        texts.append("### all-text-nodes\n" + t)
        # 抽屉展开
        for sel in ["#drawerBtn", ".drawer-open", "[data-drawer]",
                    "#menuBtn", ".icon-menu"]:
            try:
                el = await pg.query_selector(sel)
                if el:
                    await el.click()
                    await pg.wait_for_timeout(600)
                    break
            except Exception:
                pass
        await dump("after-drawer")
        # 填生日表单触发 personal 行
        try:
            await pg.evaluate("""() => {
                const y = document.querySelector('[data-k=y]');
                const m = document.querySelector('[data-k=m]');
                const d = document.querySelector('[data-k=d]');
                if (!y || !m || !d) return;
                for (const [sel, v] of [[y, '1995'], [m, '8'], [d, '20']]) {
                    sel.value = v;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""")
            await pg.wait_for_timeout(2500)
            await dump("after-bday-form")
        except Exception as e:
            texts.append("### bday-form ERR %s" % e)
        await b.close()

    all_text = "\n".join(texts)
    io.open(OUT, "w", encoding="utf-8").write(all_text)
    chars = set(CJK.findall(all_text))
    print("首页实测文本 %d 字符，唯一 CJK %d 字"
          % (len(all_text), len(chars)))
    print("已写 %s" % OUT)


asyncio.run(main())
