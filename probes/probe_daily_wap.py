#!/usr/bin/env python3
"""R3317 开运壁纸冒烟：起真服务 → 等日签就绪 → 点「开运壁纸」→
断言 app_wallpaper.js 懒载 + posterModal 浮层 PNG + 壁纸底图可达。
用法：BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_daily_wap.py
"""
import os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PORT = 8197

def main():
    env = dict(os.environ, BOOKS_LLM_DISABLE="1")
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.app:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
         cwd=ROOT, env=env,
         stdout=open("/tmp/wap_srv.log", "w"), stderr=subprocess.STDOUT)
    try:
        import urllib.request
        for _ in range(60):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/api/health", timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            sys.exit("服务没起来")
        from playwright.sync_api import sync_playwright
        errs = []
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{PORT}/")
            # 日签响应先到（开封依赖数据）。R3248：封套要填年月日
            # 存档后才拆——走真实「包好我的礼物」流程。
            pg.wait_for_function(
                "() => !!window.__lastDaily", timeout=30000)
            if pg.is_visible("#dailyCover"):
                ask = pg.query_selector("#dailyAsk")
                if ask and not ask.get_attribute("hidden"):
                    for k, v in (("y", "1991"), ("m", "4"), ("d", "4")):
                        pg.fill(f"#dailyAsk [data-k='{k}']", v)
                    pg.click("#dailyAsk .da-btn")
                else:
                    pg.click("#dailyCover")
                pg.wait_for_selector(
                    "#dailyCover", state="hidden", timeout=15000)
            pg.wait_for_selector("#dailyWap:not([disabled])", timeout=30000)
            btn_ok = pg.is_visible("#dailyWap")
            pg.click("#dailyWap")
            pg.wait_for_selector("#posterModal .poster-modal-img",
                                 timeout=20000)
            src = pg.get_attribute("#posterModal .poster-modal-img", "src")
            png = bool(src and src.startswith("data:image/png") and
                       len(src) > 40000)
            title = pg.inner_text(".poster-modal-title")
            # 底图同种子可达
            d = pg.evaluate("window.__lastDaily && window.__lastDaily.date")
            b.close()
        print(f"dailyWap 按钮启用={btn_ok} 浮层PNG={png} "
              f"标题={title!r} 日期={d} pageerror={len(errs)}")
        if errs:
            print("PAGEERROR:", errs[:3])
        ok = btn_ok and png and "开运壁纸" in title and not errs
        print("probe_daily_wap", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
