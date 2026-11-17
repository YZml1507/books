#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""font_subset_map.py — R12 数据：哪个文字块触发哪个文楷子集。

对每个实际加载的 woff2 子集：
  · 统计页面可见文本里落在该 unicode-range 的字符
  · 抽样这些字符来自哪些元素（class）
输出：子集 → 字符来源归因，回答「把哪些文字换成系统字体能砍掉哪些子集」。
"""
import asyncio
import json
import os
import re
import sys

from playwright.async_api import async_playwright

URL = "http://116.205.229.222/?key=9022cc97ec4b95325ed6f51faeb6c32e"
LXGW_CSS = "/static/fonts/lxgw.css"
OUT = "/workspace/downloads/cycle3-r11/font_map.txt"


def ranges_of(css_text):
    """从 lxgw.css 解析 (subset_url, [ranges])。"""
    out = []
    for m in re.finditer(
            r"url\('\./(lxgw/lxgwwenkai-regular-subset-[\w.]+)'\)"
            r"[^}]*?unicode-range:\s*([^;]+);", css_text, re.S):
        url, rng = m.group(1), m.group(2)
        pairs = []
        for p in re.findall(r"U\+([0-9a-fA-F]+)(?:-([0-9a-fA-F]+))?", rng):
            a = int(p[0], 16)
            b = int(p[1], 16) if p[1] else a
            pairs.append((a, b))
        out.append((url, pairs))
    return out


async def main():
    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    async with async_playwright() as p:
        b = await p.chromium.launch(
            args=["--disable-dev-shm-usage", "--no-sandbox"])
        ctx = await b.new_context(viewport={"width": 375, "height": 812})
        page = await ctx.new_page()
        css_resp = {}

        async def on_resp(r):
            if "lxgw.css" in r.url:
                try:
                    css_resp["t"] = await r.text()
                except Exception:
                    pass
        page.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        await page.goto(URL, wait_until="load", timeout=90000)
        await page.wait_for_timeout(4000)

        loaded = await page.evaluate("""() => performance.getEntriesByType('resource')
            .filter(e => e.name.includes('lxgwwenkai'))
            .map(e => ({u: e.name.split('/').pop(), w: e.transferSize}))""")
        css_text = css_resp.get("t", "")
        if not css_text:
            say("!! 没抓到 lxgw.css")
            return
        subs = ranges_of(css_text)
        say("### R12 文楷子集归因（%d 个子集被加载）" % len(loaded))

        # 页面可见文本 → 字符 → 来源元素
        data = await page.evaluate("""() => {
            const out = [];
            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const seen = new Set();
            while (walk.nextNode()) {
                const t = walk.currentNode;
                const s = (t.nodeValue || '').trim();
                if (!s) continue;
                const e = t.parentElement;
                if (!e) continue;
                const cs = getComputedStyle(e);
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (!/LXGW/.test(cs.fontFamily)) continue;
                const r = e.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) continue;
                const key = e.className + '|' + e.tagName;
                if (seen.has(key + s.slice(0, 8))) continue;
                seen.add(key + s.slice(0, 8));
                out.push({cls: String(e.className).slice(0, 40), tag: e.tagName,
                          txt: s.slice(0, 60)});
            }
            return out;
        }""")

        def owner(ch):
            for d in data:
                if ch in d["txt"]:
                    return "%s.%s" % (d["tag"].lower(),
                                      d["cls"].split()[0] if d["cls"] else "")
            return "?"

        for entry in sorted(loaded, key=lambda x: -x["w"]):
            url = entry["u"]
            base = url.split("/")[-1]
            rngs = next((r for u, r in subs if u.split("/")[-1] == base),
                        None)
            if rngs is None:
                continue
            chars = set()
            for d in data:
                for ch in d["txt"]:
                    cp = ord(ch)
                    if any(a <= cp <= bb for a, bb in rngs):
                        chars.add(ch)
            if not chars:
                say("  %-42s %6.1fKB  无可见文本命中（隐藏/未渲染）"
                    % (url, entry["w"] / 1024))
                continue
            att = {}
            for ch in chars:
                o = owner(ch)
                att[o] = att.get(o, 0) + 1
            top = sorted(att.items(), key=lambda x: -x[1])[:3]
            say("  %-42s %6.1fKB  %2d字  %s" % (
                url, entry["w"] / 1024, len(chars),
                " ".join("%s×%d" % (k, v) for k, v in top)))
        await b.close()

    with open(OUT, "w") as f:
        f.write("\n".join(lines))


asyncio.run(main())
