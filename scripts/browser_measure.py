#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""browser_measure.py — R11：线上真页浏览器实测（沙箱 playwright）。

用法: python3 browser_measure.py [标签] [网络档]
  标签  slow4g | fast   网络档默认 slow4g（4x CPU + 慢 4G，贴近真实低端机）
  输出: /workspace/downloads/cycle3-r11/<标签>/ 下 report.txt + 截图

口径（与 specs/003 基线一致）：
  · 视口 375×812（iPhone X 类）
  · 门匙走 ?key= URL 参数（应用会自行落 cookie）
  · 每轮全新 context（无 SW 缓存）→ 量的是首访成本
  · 指标: FCP / LCP / CLS / TTFBP(导航完成) / 传输字节分类 / 首屏元素坐标
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

URL = "http://116.205.229.222/?key=9022cc97ec4b95325ed6f51faeb6c32e"
OUT = "/workspace/downloads/cycle3-r11"
VIEWPORT = {"width": 375, "height": 812}
SLOW4G = {"download": 50000, "upload": 20000, "latency": 400}  # bytes/s, ms


async def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "slow4g"
    slow = label != "fast"
    os.makedirs(os.path.join(OUT, label), exist_ok = None) if False else None
    d = os.path.join(OUT, label)
    os.makedirs(d, exist_ok=True)
    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[
            "--disable-dev-shm-usage", "--no-sandbox"])
        ctx = await browser.new_context(viewport=VIEWPORT,
                                        device_scale_factor=2)
        page = await ctx.new_page()
        if slow:
            cdp = await ctx.new_cdp_session(page)
            await cdp.send("Network.enable")
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": 400,
                "downloadThroughput": 50000,
                "uploadThroughput": 20000,
                "connectionType": "cellular4g"})
            await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        # 资源瀑布
        reqs = []
        page.on("response", lambda r: reqs.append(r))

        await page.goto(URL, wait_until="load", timeout=90000)
        await page.wait_for_timeout(2500)  # 让日卡/懒块安静下来

        perf = await page.evaluate("""() => {
            const n = performance.getEntriesByType('navigation')[0] || {};
            const p = performance.getEntriesByType('paint') || [];
            const fcp = (p.find(x => x.name === 'first-contentful-paint') || {}).startTime;
            let lcp = 0, lcpEl = '';
            try {
                const lo = performance.getEntriesByType('largest-contentful-paint');
                if (lo && lo.length) { lcp = lo[lo.length-1].startTime; lcpEl = String((lo[lo.length-1].element||{}).className || '').slice(0,60); }
            } catch (e) {}
            return {
                ttfb: n.responseStart, domContentLoaded: n.domContentLoadedEventEnd,
                loadEnd: n.loadEventEnd, fcp, lcp, lcpEl,
                transfer: n.transferSize, encoded: n.encodedBodySize,
                cls: (window.__clsTotal != null ? window.__clsTotal : null),
            };
        }""")

        # CLS：用 PerformanceObserver 重放不可行（已过窗口），改抽样 layout shift 计数
        cls = await page.evaluate("""() => new Promise(res => {
            let total = 0, n = 0;
            try {
                const po = new PerformanceObserver(l => {
                    for (const e of l.getEntries()) if (!e.hadRecentInput) { total += e.value; n++; }
                });
                po.observe({type: 'layout-shift', buffered: true});
            } catch (e) {}
            setTimeout(() => res({total, n}), 800);
        })""")

        say("### R11 浏览器实测（%s，375×812，%s）" % (
            label, "Slow4G+4xCPU" if slow else "无节流"))
        say("导航 TTFB %.0fms | DCL %.0fms | load %.0fms" % (
            perf["ttfb"], perf["domContentLoaded"], perf["loadEnd"]))
        say("FCP %.0fms | LCP %.0fms (%s)" % (perf["fcp"], perf["lcp"],
                                              perf["lcpEl"]))
        say("CLS 抽样 %.4f（%d 次 shift）" % (cls["total"], cls["n"]))
        say("导航文档传输 %dB / 解码 %dB" % (perf["transfer"], perf["encoded"]))

        # 资源瀑布（按类型汇总 + top10）
        agg = {}
        rows = []
        for r in reqs:
            try:
                u = r.url
                if u.startswith("data:"):
                    continue
                t = (r.request.resource_type or "other")
                hdr = await r.header_value("content-encoding") or ""
                body = 0
                try:
                    body = len(await r.body())
                except Exception:
                    pass
                agg[t] = agg.get(t, 0) + body
                rows.append((body, t, u.split("/")[-1][:46]))
            except Exception:
                pass
        say("\n-- 传输（解码后字节，按类型）--")
        for t, b in sorted(agg.items(), key=lambda x: -x[1]):
            say("  %-12s %8.1fKB" % (t, b / 1024))
        say("  %-12s %8.1fKB" % ("合计", sum(agg.values()) / 1024))
        say("  请求数 %d" % len(rows))
        say("\n-- top 10 资源 --")
        for b, t, n in sorted(rows, reverse=True)[:10]:
            say("  %8.1fKB %-10s %s" % (b / 1024, t, n))

        # 首屏元素坐标（回答 R7 遗留问题：入口区到底在几屏）
        geo = await page.evaluate("""() => {
            const pick = s => { const e = document.querySelector(s); if (!e) return null;
                const r = e.getBoundingClientRect(); return {top: r.top + scrollY, h: r.height, vis: r.height > 0}; };
            const out = {};
            [['.ink-hero-wrap','hero'],['.brand','brand'],['#dailyCard','dailyCard'],
             ['#dailyAsk','dailyAsk'],['[data-group="ask"]','askZone'],
             ['.scene-bar','sceneBar'],['#funcGrid','funcGrid'],['#funcMoreBtn','moreBtn'],
             ['.install-pwa-row','installRow']].forEach(([s,k]) => { const v = pick(s); if (v) out[k]=v; });
            out.docH = document.documentElement.scrollHeight;
            return out;
        }""")
        say("\n-- 首屏元素坐标（文档坐标）--")
        for k in ("hero", "brand", "dailyCard", "dailyAsk", "askZone",
                  "sceneBar", "funcGrid", "moreBtn", "installRow"):
            if k in geo:
                say("  %-11s top=%4dpx h=%3dpx %s" % (
                    k, geo[k]["top"], geo[k]["h"],
                    "" if geo[k]["vis"] else "(隐藏)"))
        say("  文档总高 %dpx = %.2f 屏" % (geo["docH"], geo["docH"] / 812))
        # 小满第一问：判词前可交互
        pre = await page.evaluate("""() => {
            const main = document.querySelector('#dailyCard .daily-main');
            if (!main) return null;
            const r = main.getBoundingClientRect();
            const inter = [...document.querySelectorAll('#dailyCard button, #dailyCard a, #dailyCard input, #dailyCard select')];
            const above = inter.filter(e => { const b = e.getBoundingClientRect(); return b.height > 0 && b.top < r.top; });
            return {total: inter.length, aboveVerdict: above.length};
        }""")
        if pre:
            say("  日卡可交互 %d，其中判词(main)之前 %d" % (
                pre["total"], pre["aboveVerdict"]))

        await page.screenshot(path=os.path.join(d, "viewport.png"),
                              full_page=False)
        await page.screenshot(path=os.path.join(d, "full.png"), full_page=True)
        await browser.close()

    with open(os.path.join(d, "report.txt"), "w") as f:
        f.write("\n".join(lines))


asyncio.run(main())
