#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""browser_bytes.py — R11 补充：真线字节账 + 字体使用面。

用 Resource Timing API（transferSize=真实线字节，含响应头）而不是
response.body()（可能已被解压），并回答：
  · 每类资源真实传输字节（首访）
  · 哪些元素在用 lxgw 文楷（决定字体能不能只给标题用）
  · 字体子集加载清单与触发元素抽样
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

URL = "http://116.205.229.222/?key=9022cc97ec4b95325ed6f51faeb6c32e"
OUT = "/workspace/downloads/cycle3-r11"
VIEWPORT = {"width": 375, "height": 812}


async def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "slow4g"
    slow = label != "fast"
    d = os.path.join(OUT, label)
    os.makedirs(d, exist_ok=True)
    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--disable-dev-shm-usage", "--no-sandbox"])
        ctx = await browser.new_context(viewport=VIEWPORT)
        page = await ctx.new_page()
        if slow:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": 400,
                "downloadThroughput": 50000,
                "uploadThroughput": 20000, "connectionType": "cellular4g"})
            await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        await page.goto(URL, wait_until="load", timeout=90000)
        await page.wait_for_timeout(3000)

        rt = await page.evaluate("""() => {
            const out = {agg: {}, rows: [], fonts: []};
            performance.getEntriesByType('resource').forEach(e => {
                const u = e.name; if (u.startsWith('data:')) return;
                const t = e.initiatorType || 'other';
                const g = t === 'font' ? 'font'
                        : (u.includes('.css') ? 'css'
                        : (u.includes('.js') ? 'js'
                        : (u.match(/\\.(png|jpg|jpeg|webp|svg|gif)/) ? 'img'
                        : (t === 'fetch' || t === 'xmlhttprequest' ? 'xhr' : t))));
                out.agg[g] = out.agg[g] || {n: 0, wire: 0, dec: 0};
                out.agg[g].n++;
                out.agg[g].wire += e.transferSize;
                out.agg[g].dec += e.decodedBodySize;
                out.rows.push([e.transferSize, g, decodeURIComponent(u.split('/').pop()).slice(0, 60)]);
                if (g === 'font') out.fonts.push([e.transferSize, decodeURIComponent(u.split('/').pop())]);
            });
            const n = performance.getEntriesByType('navigation')[0] || {};
            out.nav = {wire: n.transferSize, dec: n.decodedBodySize, n: 1};
            return out;
        }""")

        say("### R11-b 真实线字节（%s）" % label)
        say("%-8s %5s %12s %12s" % ("类型", "请求", "线字节", "解码"))
        tw = td = 0
        for g, v in sorted(rt["agg"].items(), key=lambda x: -x[1]["wire"]):
            say("%-8s %5d %10.1fKB %10.1fKB" % (
                g, v["n"], v["wire"] / 1024, v["dec"] / 1024))
            tw += v["wire"]
            td += v["dec"]
        say("%-8s %5d %10.1fKB %10.1fKB" % ("文档", 1,
            rt["nav"]["wire"] / 1024, rt["nav"]["dec"] / 1024))
        tw += rt["nav"]["wire"]
        say("%-8s %5s %10.1fKB" % ("合计", "", tw / 1024))
        say("\n-- top 12 线字节 --")
        for b, g, n in sorted(rt["rows"], reverse=True)[:12]:
            say("  %8.1fKB %-6s %s" % (b / 1024, g, n))
        say("\n-- 字体加载清单（%d 个）--" % len(rt["fonts"]))
        for b, n in sorted(rt["fonts"], reverse=True):
            say("  %7.1fKB %s" % (b / 1024, n))

        # 谁在用文楷
        fam = await page.evaluate("""() => {
            const sels = ['body', '.brand-title', '.brand-tagline', '.hero-line-text',
                          '.daily-main', '.daily-level', '.daily-mantra', '.fc-name',
                          '.scene-chip', '.daily-label', '.disclaimer', '.daily-meta-item',
                          '#dailyAsk .da-title', 'h1', 'h2', 'h3'];
            const out = [];
            sels.forEach(s => { const e = document.querySelector(s);
                if (e) out.push([s, getComputedStyle(e).fontFamily.slice(0, 70)]); });
            const cnt = {};
            document.querySelectorAll('*').forEach(e => {
                const f = getComputedStyle(e).fontFamily;
                cnt[f] = (cnt[f] || 0) + 1;
            });
            const top = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 6);
            return {sels: out, top};
        }""")
        say("\n-- 关键元素 font-family --")
        for s, f in fam["sels"]:
            say("  %-22s %s" % (s, f))
        say("\n-- 全页 font-family 分布 top6 --")
        for f, c in fam["top"]:
            say("  %4d 个元素  %s" % (c, f[:76]))
        await browser.close()

    with open(os.path.join(d, "bytes.txt"), "w") as f:
        f.write("\n".join(lines))


asyncio.run(main())
