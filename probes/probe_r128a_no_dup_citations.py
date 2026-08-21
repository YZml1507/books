"""probe_r128a_no_dup_citations.py — R128a-01 的可复验闸门（R190b 建）。

R128a-01：同一批古籍原文被渲染两次（`.ev-item` 24 个而 API 只返回 12 段）。
audit 侧 R131a 已签 VERIFIED，但它签的是 `2cbb1f8` 时的代码——之后 main 又
落了 R187b/R188b/R189b 三轮（含 app.js +222 行）。签字对象已变，故本轮
重新钉一个常驻闸门，而不是沿用旧结论。

判据（全部成立才退出 0）：
  A 古籍渲染元素总数 == API 段数（不重复）。统计所有承载引文正文的容器：
    `.ev-text`（旧全文渲染点）+ `.cite-body`（三级折叠树正文点）。
  B 折叠 ≠ 删除：页面 textContent 里仍能取到抽查段落的原文与出处
    （宪法第三条，与 specs/005 判据 6/7/8 同源，此处做独立第二见证）。

自带 --self-check：注入一次重复渲染（把 cite-body 内容克隆一份追加进 DOM），
判据 A 必须 FAIL，否则本闸门是假的（U-08 教训）。

用法：
    <py> probes\\probe_r128a_no_dup_citations.py
    <py> probes\\probe_r128a_no_dup_citations.py --self-check
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PORT = 8232
PAYLOAD = {"year": 1998, "month": 7, "day": 20, "hour": 14,
           "gender": "女", "question": "感情运怎么样？", "ask_date": "2026-08-20"}
# R190b 踩坑记录（写在代码里防再犯）：提问框 id 是 `question` 不是 `q`，
# 性别是 <select id="gender"> 默认「男」。填错会让浏览器那次请求与本脚本的
# API 调用参数不同，evidence 集合随之不同，判据 B 报假 FAIL（2 段"缺失"）。
# 判据 B 的正确做法：不拿自己另发的 API 响应去比，而是**拦截浏览器实际发出的
# 请求体**、用同一份参数重放取 evidence，再与页面文本比对。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


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
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"probe_r128a FAIL: 端口 {PORT} 已被占用，无法起干净实例")
            return 1

    env = dict(os.environ, BOOKS_LLM_DISABLE="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "web.app:app", "--port", str(PORT),
         "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_health(PORT):
            print("probe_r128a FAIL: 服务未起来")
            return 1

        from playwright.sync_api import sync_playwright
        sent: list[str] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.on("request", lambda r: sent.append(r.post_data or "")
                    if r.url.endswith("/api/bazi") else None)
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
            page.click('.func-card[data-view="bazi"]')
            page.fill("#year", "1998")
            page.fill("#month", "7")
            page.fill("#day", "20")
            page.fill("#hour", "14")
            page.select_option("#gender", PAYLOAD["gender"])
            page.fill("#question", PAYLOAD["question"])
            page.click("#submit")
            page.wait_for_timeout(6000)

            if self_check:                      # 阳性对照：人为制造重复渲染
                page.evaluate("""() => {
                    document.querySelectorAll('.cite-body').forEach(n => {
                        n.parentNode.appendChild(n.cloneNode(true));
                    });
                }""")

            got = page.evaluate("""() => ({
                ev_text: document.querySelectorAll('.ev-text').length,
                cite_body: document.querySelectorAll('.cite-body').length,
                text: document.body.textContent || '',
            })""")
            browser.close()

        # 用浏览器**实际发出的**请求体重放，保证比对对象与页面同源
        if not sent:
            print("probe_r128a FAIL: 未捕获到浏览器的 /api/bazi 请求")
            return 1
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/bazi", data=sent[-1].encode(),
            headers={"Content-Type": "application/json"})
        api = json.loads(urllib.request.urlopen(req, timeout=60).read())
        n_api = len(api["evidence"])
        print(f"浏览器实际请求体：{sent[-1]}")
    finally:
        proc.terminate()

    n_dom = got["ev_text"] + got["cite_body"]
    a_ok = n_dom == n_api
    print(f"判据 A 不重复渲染：DOM 引文容器 {n_dom} 个"
          f"（.ev-text {got['ev_text']} + .cite-body {got['cite_body']}）"
          f" vs API {n_api} 段　{'PASS' if a_ok else 'FAIL'}")

    body = re.sub(r"\s+", "", got["text"])
    probe_texts = [re.sub(r"\s+", "", e["text"])[:24] for e in api["evidence"][:6]]
    probe_titles = [e["title"] for e in api["evidence"][:6]]
    miss_t = [t for t in probe_texts if t not in body]
    miss_s = [t for t in probe_titles if re.sub(r"\s+", "", t) not in body]
    b_ok = not miss_t and not miss_s
    print(f"判据 B 折叠≠删除：抽查 {len(probe_texts)} 段原文缺 {len(miss_t)}、"
          f"出处缺 {len(miss_s)}　{'PASS' if b_ok else 'FAIL'}")
    for t in miss_t:
        print(f"    缺失原文片段：{t!r}")

    ok = a_ok and b_ok
    print()
    if self_check:
        if ok:
            print("probe_r128a --self-check FAIL: 注入重复渲染后仍全绿——假闸门")
            return 1
        print("probe_r128a --self-check PASS: 阳性对照被抓到")
        return 0
    if not ok:
        print("probe_r128a FAIL: 古籍原文重复渲染或折叠变成了删除")
        return 1
    print("probe_r128a PASS: 古籍原文一段一次、折叠不删除")
    return 0


if __name__ == "__main__":
    sys.exit(main("--self-check" in sys.argv))
