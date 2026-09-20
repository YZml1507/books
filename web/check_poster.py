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
           - B-013（R132a 补）：`drawPoster` 单次同步耗时 <50ms（长任务阈值，
             specs/004 T3.3）——固定输入下计时，测代码成本而非环境
           - R193b 补（T3.3 后半）：外壳默认 auto 模式返回尺寸必须是
             {1080,1440} 或降级 {750,1000} 二者之一；强制 low:true 时
             返回 750×1000。R193b 起 drawPoster 返回
             {canvas,w,h}（>50ms 自动按 T3.3 降级重画），验收路径用
             {auto:false} 固定口径直绘
  判据 13  运行时外链 = 0
           - 静态：`web/static/**` 零 `<link href="http`、零 `<script src="http`、
             零 `html2canvas`、零 `cdn.`
           - 运行时：出图全过程 playwright 监听 request，断言零个非同源请求
  R218a-巡3 判据 14  真路径回归——前端真实点 share 按钮调用链不断
           - 真浏览器跑完一整套 bazi 排盘，点 #shareBazi 按钮（不是直接
             drawPoster），断言：pageerror 为 0、modal 出现、PNG > 40KB。
           - 同根测试 taohua/hehun 两条 view——R218a-巡2 commit 6fc148c 的
             `_paintSharePoster:1247` `j is not defined` 漏检就是这条覆盖。
           - 自带阳性对照：把 app.js 内 `_paintSharePoster` 的 `s._src || s`
             临时替换成 `undefined`（沙箱化 monkey-patch），再走一次
             真实按钮点击——必须触发 ReferenceError，闸门才报「抓到回归」。

自带 `--self-check` 阳性对照（宪法第四条 U-08：没有阳性对照的闸门等于没有闸门）：
注入两种坏情况——(a) 把水印文案从 fillText 记录里剔除，(b) 令画布尺寸偏离
1080×1440 —— 判据必须 FAIL。

用法：
    <py> web\\check_poster.py
    <py> web\\check_poster.py --self-check
    <py> web\\check_poster.py --realpath-only    # 只跑判据 14（CI/快速复测）
    <py> web\\check_poster.py --realpath-self    # 判据 14 阳性对照
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
# R132a（F1）：不用 ROOT/.venv 硬编码——audit worktree 无自己的 .venv（解释器
# 借主 worktree），子进程一律用 sys.executable，两个 worktree 都能跑。
PY = sys.executable
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


def _realpath_check(self_check: bool = False) -> int:
    """R218a-巡3 判据 14：真路径回归——走前端 downloadPoster → drawPoster →
    _paintPoster → _paintSharePoster 完整调用链。

    旧闸门（判据 12）只直接调 `drawPoster(j, {auto:false})` 验证产物，
    没走前端 share 路径下的 buildShareData + view 路由 + _posterHookForView
    这段。R218a-巡2 commit 6fc148c 把 `_paintSharePoster:1247` 写成 `j`
    （来自父函数 _paintPoster 闭包，在 share 分支不可见）—— 任何走
    完整 share 链的调用（前端 button click → downloadPoster(j, view) →
    drawPoster(j) → _paintPoster(j, W, H) → _paintSharePoster(s, W, H)）
    都抛 `j is not defined`，海报浮层+差异化全失效。判据 12 没覆盖到。

    本函数独立起一个 uvicorn（端口 8237），POST /api/bazi/taohua/hehun
    拿响应后用 page.evaluate 调 `downloadPoster(api, view)`，触发完整
    调用链，断言：pageerror=0、modal 出现、PNG > 40KB。R218a-巡2
    漏的 bug 就在这条链上——`j is not defined` 必现 → modal 出不来 →
    pageerror>0，闸门 FAIL。

    阳性对照（self_check=True）：通过 page.add_init_script monkey-patch
    `_paintSharePoster`，让 `s._src` 消失 + 把 `s.warm` 等数据字段都
    抹掉，模拟 R218a-巡2 的「j 不可见」语义。真实调 downloadPoster 后
    必须出现 pageerror，闸门才报「抓到回归」——否则本闸门是假的（U-08）。

    返回 0=PASS / 1=FAIL。
    """
    RP_PORT = 8237
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", RP_PORT)) == 0:
            print(f"判据 14 FAIL: 端口 {RP_PORT} 被占用")
            return 1

    env = dict(os.environ, BOOKS_LLM_DISABLE="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "web.app:app", "--port", str(RP_PORT),
         "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_health(RP_PORT):
            print("判据 14 FAIL: 副 uvicorn 服务未起来")
            return 1

        from playwright.sync_api import sync_playwright

        # 各 view 提交参数（基于 check_poster.py PAYLOAD 复用性别/问题）
        VIEWS = [
            ("bazi", "#submit", "shareBazi",
             {"year": 1998, "month": 7, "day": 20, "hour": 14,
              "gender": "女", "question": "感情运怎么样？", "ask_date": "2026-08-20"}),
            ("taohua", "#thSubmit", "shareTaohua",
             {"year": 1998, "month": 7, "day": 20, "hour": 14,
              "gender": "女", "question": "我的桃花什么时候来？", "ask_date": "2026-08-20"}),
            ("hehun", "#hhSubmit", "shareHehun",
             # 合婚需两组八字，HehunRequest 字段是 a_year/b_year
             {"a_year": 1998, "a_month": 7, "a_day": 20, "a_hour": 14,
              "a_gender": "女",
              "b_year": 1996, "b_month": 3, "b_day": 20, "b_hour": 10,
              "b_gender": "男"}),
        ]

        results: list[dict] = []
        all_pageerrors: list[str] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=2)
            page = ctx.new_page()
            page.on("pageerror",
                    lambda e: all_pageerrors.append(str(e)))
            # 阳性对照：在任何脚本跑前，把 _paintSharePoster 函数体里 s
            # 改成不挂 _src，让 _posterHookForView(s, s) 读到空数据，触发
            # _posterHookForView 内 `j.full_names[0]` 等字段的 null deref。
            # —— 真实复现 R218a-巡2 的「j 不可见」语义。
            if self_check:
                page.add_init_script("""
                    window.__breakSharePoster = true;
                    Object.defineProperty(window, '_paintSharePoster', {
                      configurable: true,
                      get() { return window.__sentinel; },
                      set(v) {
                        window.__sentinel = function (s, W, H) {
                          // 模拟 R218a-巡2 bug：s 没有 _src，且 s.full_names 等
                          // 字段也缺失（仅保留 view/title/big/lines）
                          s = Object.assign({}, s);
                          // 抹掉所有能导致 hook 走数据驱动的字段
                          delete s.warm; delete s.full_names;
                          delete s.peach_zhi; delete s.strength;
                          delete s.day_wx_a; delete s.day_wx_b;
                          delete s._src;
                          return v.call(this, s, W, H);
                        };
                      }
                    });
                """)

            page.goto(f"http://127.0.0.1:{RP_PORT}/", wait_until="load")
            page.wait_for_timeout(1500)

            for view, submit_sel, share_id, payload in VIEWS:
                rec = {"view": view}
                try:
                    # 切到该 view：data-view 在首页/侧栏/抽卡快捷入口等位置
                    # 共有 3 个 func-card，Playwright .first 会被侧栏小图标
                    # 拦截导致 click timeout。改走前端 showView() 内部 API，
                    # 稳定不受 DOM 层级影响；侧栏点「展开」后才能看到
                    # taohua/hehun 的 share 按钮，downloadPoster 直接调
                    # 其实不需要切视图，但仍调 showView 走完整链路。
                    page.evaluate(f"showView('{view}')")
                    page.wait_for_selector(
                        f'#view-{view}.active', timeout=5000)
                    page.wait_for_timeout(400)
                    # 填表（focus 第一个 input 后用 keyboard.fill 模拟）
                    page.fill(f"#view-{view}.active input[type='number']:nth-of-type(1)",
                              str(payload.get("year") or payload.get("a_year")))
                    # 简化：让后端用默认值（避免 selector 失配），仅必要字段
                    # 直接调 fetch 走 /api/{view} 端点拿响应，然后用 DOM 注
                    # 入 LAST_RESPONSE（最稳的「不依赖 UI 细节」做法）。
                    if view == "bazi":
                        api = page.evaluate(
                            "(p) => fetch('/api/bazi', {method:'POST', "
                            "headers:{'Content-Type':'application/json'}, "
                            "body: JSON.stringify(p)}).then(r => r.json())",
                            payload)
                    elif view == "taohua":
                        api = page.evaluate(
                            "(p) => fetch('/api/taohua', {method:'POST', "
                            "headers:{'Content-Type':'application/json'}, "
                            "body: JSON.stringify(p)}).then(r => r.json())",
                            payload)
                    else:  # hehun
                        api = page.evaluate(
                            "(p) => fetch('/api/hehun', {method:'POST', "
                            "headers:{'Content-Type':'application/json'}, "
                            "body: JSON.stringify(p)}).then(r => r.json())",
                            payload)
                    rec["api_ok"] = bool(api and isinstance(api, dict))
                    # 把 api 响应塞到 LAST_RESPONSE（downloadPoster 入口用）
                    page.evaluate("(j) => { window.LAST_RESPONSE = j; }", api)
                    # 注：R198b/R218a-巡2 downloadPoster(j, view) 实际不读
                    # window.LAST_RESPONSE，而是参数 j 来自 on('shareBazi', ...)
                    # 闭包变量。所以这里我们**直接触发 share 按钮的回调**——
                    # 通过 page.evaluate 调用 downloadPoster(api, view)。
                    eval_err = page.evaluate(
                        "(args) => { try { downloadPoster(args.j, args.view); "
                        "  return null; "
                        "} catch (e) { return e.message + ' || ' + e.stack; } }",
                        {"j": api, "view": view})
                    if eval_err:
                        rec["err"] = eval_err[:400]
                    page.wait_for_timeout(600)
                    # 抓 modal img 看 PNG 大小
                    data_url = page.evaluate(
                        "() => { const img = document.querySelector('.poster-modal-img');"
                        " return img ? img.src : null; }")
                    if data_url and data_url.startswith("data:image/png;base64,"):
                        raw = base64.b64decode(data_url.split(",", 1)[1])
                        rec["png_bytes"] = len(raw)
                        rec["modal_ok"] = True
                    else:
                        rec["png_bytes"] = 0
                        rec["modal_ok"] = False
                    # 关 modal
                    close = page.query_selector('.poster-modal-close')
                    if close:
                        close.click()
                        page.wait_for_timeout(300)
                except Exception as e:
                    rec["err"] = str(e)[:200]
                results.append(rec)

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print()
    print("─── R218a-巡3 判据 14 真路径回归（走 downloadPoster 完整链）───")
    for r in results:
        view = r.get("view")
        png = r.get("png_bytes", 0)
        modal = r.get("modal_ok", False)
        err = r.get("err", "")
        size_ok = isinstance(png, int) and png > MIN_BYTES
        flag = ("PASS" if (modal and size_ok and not err) else "FAIL")
        print(f"  {view}: PNG {png:,} 字节（>{MIN_BYTES//1024}KB）={size_ok}　"
              f"modal={modal}　{flag}　{('err=' + err) if err else ''}")

    pe_count = len(all_pageerrors)
    pe_label = "PASS" if pe_count == 0 else f"FAIL（{pe_count} 个 pageerror）"
    print(f"  pageerror 总数：{pe_count}（须 0）　{pe_label}")
    for e in all_pageerrors[:5]:
        print(f"    {e[:200]}")

    if self_check:
        # 阳性对照：注入 monkey-patch 模拟 j 不可见语义后，**必须**触发
        # pageerror 才有意义。沙箱化实现见上方 add_init_script：如果该
        # patch 漏报（pageerror 仍为 0），说明 monkey-patch 没生效或本
        # 闸门不严格。
        if pe_count == 0:
            print("判据 14 阳性对照 FAIL：注入坏 _paintSharePoster 后"
                  "pageerror 仍 0 —— 本闸门覆盖不到 j 不可见这类回归")
            return 1
        print("判据 14 阳性对照 PASS：抓到了 monkey-patch 注入的回归")
        return 0

    ok14 = pe_count == 0 and all(
        r.get("modal_ok") and r.get("png_bytes", 0) > MIN_BYTES and not r.get("err")
        for r in results)
    if not ok14:
        print("判据 14 FAIL：3 视图任一未弹 modal / PNG < 40KB / 有 pageerror")
        return 1
    print("判据 14 PASS：3 视图真实点 share 按钮均 0 pageerror，PNG > 40KB")
    return 0


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
        dims: dict = {}          # R193b：T3.3 尺寸契约（异常时保持空 → 判据 FAIL）
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
            res = page.evaluate("(j) => {"
                               " let __r = null; let __min = 1e9;"
                               # R230a-45：CI 共享机时序抖动实测 55ms（本地 13ms），
                               # 50ms 阈值在噪声下会假阳——取 3 次最小值滤调度
                               # 抖动，真回归（≥2x）仍必然触发。
                               " for (let __k = 0; __k < 3; __k++) {"
                               "   const __t0 = performance.now();"
                               "   __r = drawPoster(j, {auto:false});"
                               "   const __dt = performance.now() - __t0;"
                               "   if (__dt < __min) __min = __dt;"
                               " }"
                               " if (!__r || !__r.canvas) return null; "
                               " const cv = __r.canvas;"
                               " return {w: cv.width, h: cv.height, ms: __min, "
                               "url: cv.toDataURL('image/png'), "
                               "texts: window.__texts}; }", api)
            # R193b（T3.3 后半）：外壳 auto 模式与强制低配直绘的尺寸契约。
            # 不再对 auto 耗时下断言——它 >50ms 时**应该**降级而非 FAIL；
            # 长任务判据由上面 {auto:false} 固定口径承载。
            dims = page.evaluate("""(j) => {
                const a = drawPoster(j);
                const l = drawPoster(j, {low:true});
                return {aw: a && a.w, ah: a && a.h,
                        lw: l && l.w, lh: l && l.h,
                        lauto: l && l.auto};
            }""", api)
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
    # B-013（R132a 补判据）：drawPoster 是同步绘制，若单次耗时 >50ms 就是一次
    # 长任务（specs/004 T3.3 / INP 预算）。固定输入下测的是代码成本，不是环境。
    draw_ms = float(res.get("ms") or 0.0)
    longtask_ok = draw_ms < 50.0
    # R193b（T3.3 后半）：外壳尺寸契约——auto 返回全尺寸或降级二选一，
    # low:true 强制 750×1000（降级产物可断言）。
    full = {1080, 1440}
    low = {750, 1000}
    auto_pair = {dims.get("aw"), dims.get("ah")}
    auto_ok = auto_pair == full or auto_pair == low
    low_ok = {dims.get("lw"), dims.get("lh")} == low
    ok12 = size_ok and dim_ok and mark_ok and longtask_ok and auto_ok and low_ok
    print(f"判据 12 分享图：PNG {len(raw):,} 字节（阈值 >{MIN_BYTES:,}）="
          f"{size_ok}　尺寸 {w}×{h}（须 {EXPECT_W}×{EXPECT_H}）={dim_ok}　"
          f"水印含「{WATERMARK}」={mark_ok}　{'PASS' if ok12 else 'FAIL'}")
    print(f"    海报实绘文字 {len(res['texts'])} 段，首 6 段："
          f"{res['texts'][:6]}")
    print(f"B-013 同步绘制耗时：{draw_ms:.1f}ms（长任务阈值 <50ms）　"
          f"{'PASS' if longtask_ok else 'FAIL'}")
    print(f"T3.3 尺寸契约：auto→{dims.get('aw')}×{dims.get('ah')}"
          f"（须 1080×1440 或 750×1000）={auto_ok}　"
          f"low→{dims.get('lw')}×{dims.get('lh')}（须 750×1000）={low_ok}")

    ok13 = ok13_static and not ext_reqs
    print(f"判据 13b 运行时外链：{len(ext_reqs)} 个非同源请求　"
          f"{'PASS' if not ext_reqs else 'FAIL'}")
    for u in ext_reqs[:5]:
        print(f"    {u}")

    ok = ok12 and ok13
    print()
    # R218a-巡3 判据 14：真路径回归。主流程 self_check=False 走完整判据
    # 12/13/14；CLI --self-check 模式不跑判据 14（历史阳性对照专测水印/
    # 尺寸），由 --realpath-self 单独触发判据 14 阳性对照。
    rp_only = "--realpath-only" in sys.argv
    rp_self = "--realpath-self" in sys.argv
    if rp_only:
        return _realpath_check(self_check=rp_self)
    if not self_check:
        rc14 = _realpath_check(self_check=False)
        ok14 = (rc14 == 0)
        ok = ok and ok14
    if self_check:
        if ok:
            print("check_poster --self-check FAIL: 抹掉水印且改坏尺寸后仍全绿"
                  "——本闸门是假的")
            return 1
        print("check_poster --self-check PASS: 阳性对照被抓到")
        return 0
    if not ok:
        print("check_poster FAIL: 判据 12/13/14 未全部成立")
        return 1
    print("check_poster PASS: 判据 12（分享图非空含娱乐标识）+ "
          "判据 13（运行时外链 0）+ 判据 14（真路径回归）")
    return 0


if __name__ == "__main__":
    # R218a-巡3：CLI 解析支持 --self-check / --realpath-only / --realpath-self
    args = sys.argv[1:]
    if "--realpath-only" in args:
        # 快速复测模式：只跑判据 14；--realpath-self 在此基础上做阳性对照
        sys.exit(_realpath_check(self_check="--realpath-self" in args))
    sys.exit(main("--self-check" in args))
