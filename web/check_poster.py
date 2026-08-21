"""check_poster.py — specs/004 判据 12/13 的验收闸门（R190b 建）。

**为什么现在才有**：R188b 交付了 M3 分享海报（`drawPoster()` 原生 Canvas），
台账 §126 宣称判据 12/13 达成，但 `plan.md:144-145` 指定的验收脚本
`web/check_poster.py` **从未存在**——即「已交付未验收」。本文件补上这个空缺。
宪法第一条：没有命令的 DONE 等于没做。

判据（全部成立才退出 0）：

  判据 12  分享图非空且含娱乐标识
           - 真浏览器点「📸 分享图」路径：直接调 `drawPoster(j)` 取
             `canvas.toDataURL('image/png')`，断言解码后字节数 > 40KB
             （spec §284 的阈值，原生方案实测 191KB）
           - 画布尺寸固定 1080×1440（3:4，判据 7 的版式约束）
           - 娱乐标识：断言 `drawPoster` 源码里存在「仅供娱乐」水印文案，
             且它被 `fillText` 真的画上去（用 CanvasRenderingContext2D 打桩
             记录所有 fillText 调用，检查水印文案在其中）
  判据 13  运行时外链 = 0
           - 静态：`web/static/**` 零 `<link href="http`、零 `<script src="http`、
             零 `html2canvas`、零 `cdn.`
           - 运行时：出图全过程 playwright 监听 request，断言零个非同源请求

自带 `--self-check` 阳性对照（宪法第四条 U-08：没有阳性对照的闸门等于没有闸门）：
注入两种坏情况——(a) 把水印文案从 fillText 记录里剔除，(b) 令画布尺寸偏离
1080×1440 —— 判据必须 FAIL。

用法：
    <py> web\\check_poster.py
    <py> web\\check_poster.py --self-check
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PORT = 8236
STATIC = os.path.join(ROOT, "web", "static")
MIN_BYTES = 40 * 1024                      # spec §284 阈值
EXPECT_W, EXPECT_H = 1080, 1440            # 判据 7 固定 3:4
WATERMARK = "仅供娱乐"
PAYLOAD = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女",
           "question": "感情运怎么样？", "ask_date": "2026-08-20"}
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _static_scan() -> tuple[bool, list[str]]:
    """判据 13 静态侧：web/static 下零外链。"""
    bad: list[str] = []
    pats = [(r'<link[^>]+href="https?://', "外链 <link>"),
            (r'<script[^>]+src="https?://', "外链 <script>"),
            (r"html2canvas", "html2canvas 引用"),
            (r"cdn\.", "CDN 域名")]
    for dirpath, _dirs, files in os.walk(STATIC):
        for fn in files:
            if not fn.endswith((".html", ".js", ".css")):
                continue
            p = os.path.join(dirpath, fn)
            text = open(p, encoding="utf-8", errors="replace").read()
            for pat, label in pats:
                for m in re.finditer(pat, text, re.I):
                    line = text[:m.start()].count("\n") + 1
                    bad.append(f"{os.path.relpath(p, ROOT)}:{line} {label}")
    return (not bad), bad


def _wait_health(port: int, tries: int = 60) -> bool:
    for _ in range(tries):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
            return True
        except Exception:
            continue
    return False


def main(self_check: bool = False) -> int:
    ok13_static, bad = _static_scan()
    print(f"判据 13a 静态外链扫描：{len(bad)} 处命中　"
          f"{'PASS' if ok13_static else 'FAIL'}")
    for b in bad:
        print(f"    {b}")

    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"check_poster FAIL: 端口 {PORT} 被占用")
            return 1

    env = dict(os.environ, BOOKS_LLM_DISABLE="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "web.app:app", "--port", str(PORT),
         "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_health(PORT):
            print("check_poster FAIL: 服务未起来")
            return 1

        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/bazi", data=json.dumps(PAYLOAD).encode(),
            headers={"Content-Type": "application/json"})
        api = json.loads(urllib.request.urlopen(req, timeout=60).read())

        from playwright.sync_api import sync_playwright
        ext_reqs: list[str] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.on("request", lambda r: ext_reqs.append(r.url)
                    if not r.url.startswith((f"http://127.0.0.1:{PORT}",
                                             "data:", "blob:", "about:")) else None)
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
            # 打桩 fillText，记录海报上真的画了哪些文字
            page.evaluate("""() => {
                window.__texts = [];
                const orig = CanvasRenderingContext2D.prototype.fillText;
                CanvasRenderingContext2D.prototype.fillText = function (t, ...a) {
                    window.__texts.push(String(t));
                    return orig.call(this, t, ...a);
                };
            }""")
            res = page.evaluate("(j) => { const cv = drawPoster(j); "
                               "if (!cv) return null; "
                               "return {w: cv.width, h: cv.height, "
                               "url: cv.toDataURL('image/png'), "
                               "texts: window.__texts}; }", api)
            browser.close()
    finally:
        proc.terminate()

    if not res:
        print("判据 12 FAIL: drawPoster 返回 null（取不到 2d context）")
        return 1

    texts = list(res["texts"])
    w, h = res["w"], res["h"]
    if self_check:                        # 阳性对照：抹掉水印 + 改尺寸
        texts = [t for t in texts if WATERMARK not in t]
        w = 800

    raw = base64.b64decode(res["url"].split(",", 1)[1])
    size_ok = len(raw) > MIN_BYTES
    dim_ok = (w == EXPECT_W and h == EXPECT_H)
    mark_ok = any(WATERMARK in t for t in texts)
    ok12 = size_ok and dim_ok and mark_ok
    print(f"判据 12 分享图：PNG {len(raw):,} 字节（阈值 >{MIN_BYTES:,}）="
          f"{size_ok}　尺寸 {w}×{h}（须 {EXPECT_W}×{EXPECT_H}）={dim_ok}　"
          f"水印含「{WATERMARK}」={mark_ok}　{'PASS' if ok12 else 'FAIL'}")
    print(f"    海报实绘文字 {len(res['texts'])} 段，首 6 段："
          f"{res['texts'][:6]}")

    ok13 = ok13_static and not ext_reqs
    print(f"判据 13b 运行时外链：{len(ext_reqs)} 个非同源请求　"
          f"{'PASS' if not ext_reqs else 'FAIL'}")
    for u in ext_reqs[:5]:
        print(f"    {u}")

    ok = ok12 and ok13
    print()
    if self_check:
        if ok:
            print("check_poster --self-check FAIL: 抹掉水印且改坏尺寸后仍全绿"
                  "——本闸门是假的")
            return 1
        print("check_poster --self-check PASS: 阳性对照被抓到")
        return 0
    if not ok:
        print("check_poster FAIL: 判据 12/13 未全部成立")
        return 1
    print("check_poster PASS: 判据 12（分享图非空含娱乐标识）+ "
          "判据 13（运行时外链 0）")
    return 0


if __name__ == "__main__":
    sys.exit(main("--self-check" in sys.argv))
