"""probe_ui_baseline.py — OPTIMIZE 阶段的**基线量尺**（审查轨 R121a，D-143a）。

`specs/003-youth-ui-revamp/spec.md` 的每条要求必须可自动测量。要measurable，
先得有**当前值**——否则「首屏更快」「点击区更大」都是空话，事后无法判定
是否达成，也无法判定是否退步。

本 probe 用真浏览器测出下列客观量，全部写进 `logs/ui_baseline.json`：

  * 静态资源体积（index.html / app.js / styles.css，字节）
  * 首屏渲染时间（DOMContentLoaded、load、首次内容绘制 FCP）
  * 三个主要 API 的响应延迟（连打 5 次取 p95）
  * 375px 视口下的横向溢出像素
  * **点击目标 < 44×44 的元素清单**（Apple HIG / WCAG 2.5.5 的常用阈值）
  * **对比度低于 WCAG AA（正文 4.5:1 / 大字 3:1）的元素清单**
  * `prefers-reduced-motion: reduce` 下仍在跑的动画数
  * 动画期间的长任务（>50ms）数

这些不是"体验感觉"，是**精致感的客观代理**——廉价感往往就来自对比度不足、
点击区过小、动画掉帧。spec 里每条 (a) 类要求都应引用本 probe 的某个量。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_ui_baseline.py
退出码：0 = 测量完成（**不做通过/失败判定**，它是量尺不是闸门）；
        2 = 环境不可用。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT_CANDIDATES = list(range(8220, 8240))
OUT = os.path.join(ROOT, "logs", "ui_baseline.json")
STATIC = os.path.join(ROOT, "web", "static")

# 对比度与点击区的判定脚本在浏览器里跑（拿计算样式，不靠猜）
MEASURE_JS = r"""
() => {
  // ── 相对亮度与对比度（WCAG 2.1 定义）──
  const lum = (rgb) => {
    const f = (c) => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
  };
  const parse = (s) => {
    const m = String(s).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x.trim()));
    return { rgb: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1 };
  };
  // 逐级向上找真实背景色（透明会继承父级）
  const bgOf = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
      const c = parse(getComputedStyle(node).backgroundColor);
      if (c && c.a > 0.05) return c.rgb;
      node = node.parentElement;
    }
    const b = parse(getComputedStyle(document.body).backgroundColor);
    return b ? b.rgb : [255, 255, 255];
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden'
      && st.display !== 'none' && parseFloat(st.opacity || '1') > 0.05;
  };

  // ── 点击目标尺寸（WCAG 2.5.5 / Apple HIG 44px）──
  const small = [];
  document.querySelectorAll(
    'button, a[href], input, select, textarea, [role=button], [onclick]'
  ).forEach(el => {
    if (!visible(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44) {
      small.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        cls: (el.className || '').toString().slice(0, 40) || null,
        text: (el.textContent || '').trim().slice(0, 18),
        w: Math.round(r.width * 10) / 10,
        h: Math.round(r.height * 10) / 10
      });
    }
  });

  // ── 文字对比度（正文 4.5:1，>=18.66px 或 >=24px 粗体算大字 3:1）──
  const low = [];
  document.querySelectorAll('body *').forEach(el => {
    if (!visible(el)) return;
    // 只看直接含文字的元素
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own.length) return;
    const st = getComputedStyle(el);
    const fg = parse(st.color);
    if (!fg) return;
    const size = parseFloat(st.fontSize);
    const weight = parseInt(st.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const cr = ratio(fg.rgb, bgOf(el));
    if (cr < need) {
      low.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 40) || null,
        text: own.map(n => n.textContent.trim()).join(' ').slice(0, 24),
        size: size, weight: weight,
        ratio: Math.round(cr * 100) / 100, need: need
      });
    }
  });

  // ── 动画数量 ──
  const anims = (document.getAnimations ? document.getAnimations() : []).length;

  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paints = {};
  performance.getEntriesByType('paint').forEach(p => {
    paints[p.name] = Math.round(p.startTime);
  });

  return {
    small_targets: small,
    low_contrast: low,
    animations_running: anims,
    dom_nodes: document.querySelectorAll('*').length,
    timing: {
      dom_content_loaded: Math.round(nav.domContentLoadedEventEnd || 0),
      load_event: Math.round(nav.loadEventEnd || 0),
      first_paint: paints['first-paint'] || null,
      first_contentful_paint: paints['first-contentful-paint'] || null
    }
  };
}
"""


def free_port(p: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) != 0


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probe_ui_baseline SKIP-ENV: playwright 未安装")
        return 2

    port = next((p for p in PORT_CANDIDATES if free_port(p)), None)
    if port is None:
        print("probe_ui_baseline SKIP-ENV: 无空闲端口（不抢占他人端口）")
        return 2

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([ROOT, os.path.join(ROOT, "src")])
    env["PYTHONIOENCODING"] = "utf-8"
    target = ("web.app:app"
              if os.path.exists(os.path.join(ROOT, "web", "__init__.py"))
              else "app:app")
    cwd = ROOT if target.startswith("web.") else os.path.join(ROOT, "web")
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=cwd, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT)

    data: dict = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "port": port, "target": target}
    # L-22：写端点自测不得污染真实库。本 probe 会打 5 次 /api/bazi 测延迟，
    # 每次都往 history.db 写一条。第一版漏了清理（实测 43 → 48），
    # 靠人工补删——那正是 L-22 要防的。现在记基线并在 finally 里清。
    from guji import history as history_db
    hist_baseline = history_db.count()
    try:
        deadline = time.time() + 90
        ready = False
        while time.time() < deadline:
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c.request("GET", "/api/health")
                if c.getresponse().status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)
        if not ready:
            print("probe_ui_baseline SKIP-ENV: 服务未就绪")
            return 2

        # ── 静态资源体积 ────────────────────────────────
        data["asset_bytes"] = {
            f: os.path.getsize(os.path.join(STATIC, f))
            for f in ("index.html", "app.js", "styles.css")
            if os.path.exists(os.path.join(STATIC, f))
        }
        animo = os.path.join(STATIC, "animotion")
        if os.path.isdir(animo):
            data["asset_bytes"]["animotion/(未接线)"] = sum(
                os.path.getsize(os.path.join(animo, f))
                for f in os.listdir(animo))
        data["asset_bytes_total_wired"] = sum(
            v for k, v in data["asset_bytes"].items() if "animotion" not in k)

        # ── API 延迟（连打 5 次取 p95）────────────────────
        lat: dict = {}
        cases = [("GET", "/api/health", None),
                 ("GET", "/api/works", None),
                 ("GET", "/api/search?q=%E6%BD%9B%E9%BE%8D%E5%8B%BF%E7%94%A8", None),
                 ("POST", "/api/bazi", json.dumps(
                     {"year": 1990, "month": 5, "day": 15, "hour": 10,
                      "gender": "男"}))]
        for method, path, body in cases:
            samples = []
            for _ in range(5):
                t0 = time.perf_counter()
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
                conn.request(method, path, body=body,
                             headers={"Content-Type": "application/json"}
                             if body else {})
                conn.getresponse().read()
                samples.append((time.perf_counter() - t0) * 1000)
            samples.sort()
            lat[path] = {
                "n": len(samples),
                "median_ms": round(statistics.median(samples), 1),
                "p95_ms": round(samples[int(len(samples) * 0.95) - 1], 1),
                "max_ms": round(samples[-1], 1),
            }
        data["api_latency"] = lat

        # ── 浏览器侧量测 ────────────────────────────────
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for label, vw, vh, motion in (("desktop_1280", 1280, 900, "no-preference"),
                                          ("mobile_375", 375, 812, "no-preference"),
                                          ("mobile_375_reduced_motion", 375, 812,
                                           "reduce")):
                ctx = browser.new_context(viewport={"width": vw, "height": vh},
                                          reduced_motion=motion)
                page = ctx.new_page()
                longtasks = []
                page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
                page.wait_for_timeout(1800)
                m = page.evaluate(MEASURE_JS)
                m["h_overflow_px"] = page.evaluate(
                    "() => document.documentElement.scrollWidth"
                    " - document.documentElement.clientWidth")
                # 长任务：注册观察器后触发一次真实交互再读
                page.evaluate(
                    "() => { window.__lt = []; try {"
                    " new PerformanceObserver(l => l.getEntries().forEach("
                    "e => window.__lt.push(Math.round(e.duration))))"
                    ".observe({entryTypes:['longtask']}); } catch(e) {} }")
                try:
                    page.click(".func-card[data-view='tarot']")
                    page.wait_for_timeout(400)
                    page.click("#trSubmit")
                    page.wait_for_timeout(2500)
                except Exception:
                    pass
                m["long_tasks_ms"] = page.evaluate("() => window.__lt || []")
                m["animations_after_interaction"] = page.evaluate(
                    "() => (document.getAnimations ?"
                    " document.getAnimations() : []).length")
                page.screenshot(path=os.path.join(ROOT, "logs",
                                                  f"baseline_{label}.png"),
                                full_page=True)
                data[label] = m
                ctx.close()
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        # 清理本轮 /api/bazi 写入（L-22），异常路径也要清 → 放在 finally
        cleaned = []
        try:
            extra = history_db.count() - hist_baseline
            for rec in history_db.list_records(200)[:max(0, extra)]:
                if history_db.delete_record(rec["id"]):
                    cleaned.append(rec["id"])
        except Exception as exc:                      # noqa: BLE001
            print(f"⚠ 清理未完成：{type(exc).__name__}: {exc}")
        hist_after = history_db.count()
        print(f"清理 history {len(cleaned)} 条；"
              f"行数 {hist_baseline} -> {hist_after}")
        if hist_after != hist_baseline:
            print(f"⚠ history.db 未回到基线（{hist_baseline} vs {hist_after}）")

    json.dump(data, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ── 摘要 ───────────────────────────────────────
    print("=== 静态资源（字节）===")
    for k, v in data["asset_bytes"].items():
        print(f"  {k:<24} {v:>8,}")
    print(f"  已接线合计 {data['asset_bytes_total_wired']:,}")
    print("\n=== API 延迟（5 次采样）===")
    for k, v in data["api_latency"].items():
        print(f"  {k:<52} median {v['median_ms']:>7.1f}ms  "
              f"p95 {v['p95_ms']:>7.1f}ms")
    for label in ("desktop_1280", "mobile_375", "mobile_375_reduced_motion"):
        m = data.get(label)
        if not m:
            continue
        t = m["timing"]
        print(f"\n=== {label} ===")
        print(f"  DOM 节点 {m['dom_nodes']}　横向溢出 {m['h_overflow_px']}px")
        print(f"  DOMContentLoaded {t['dom_content_loaded']}ms　"
              f"load {t['load_event']}ms　FCP {t['first_contentful_paint']}ms")
        # R125a：拆成「固定 UI」与「数据驱动」两类。数据驱动那部分（历史行
        # 按钮、外部新闻链接）随 history.db 行数与当日新闻条数变化——同一份
        # 代码今天 56 明天 72，当判据会自己漂移，那不是判据是噪声。
        # specs/003 判据 1/2 只数固定 UI（见该文件「判据 1/2 的口径订正」）。
        DATA_CLS = ("hist-view", "hist-del", "fav-del", "news-item")
        fixed = [s for s in m["small_targets"]
                 if s["tag"] != "a"
                 and not any(x in (s.get("cls") or "") for x in DATA_CLS)]
        driven = [s for s in m["small_targets"] if s not in fixed]
        m["small_fixed_ui"] = len(fixed)
        m["small_data_driven"] = len(driven)
        print(f"  点击目标 <44px：共 {len(m['small_targets'])} 个 = "
              f"固定 UI {len(fixed)}（← 判据 1/2 数这个）"
              f" + 数据驱动 {len(driven)}（随数据量变化，不作判据）")
        for s in fixed[:6]:
            print(f"     [固定] {s['tag']}#{s['id'] or '-'} {s['text']!r} "
                  f"{s['w']}×{s['h']}")
        if len(fixed) > 6:
            print(f"     …另 {len(fixed) - 6} 个固定 UI")
        print(f"  对比度低于 AA：{len(m['low_contrast'])} 个")
        for s in m["low_contrast"][:6]:
            print(f"     {s['tag']}.{s['cls'] or '-'} {s['text']!r} "
                  f"{s['ratio']}:1 < {s['need']}:1 ({s['size']}px)")
        if len(m["low_contrast"]) > 6:
            print(f"     …另 {len(m['low_contrast']) - 6} 个")
        print(f"  动画：加载后 {m['animations_running']}、"
              f"交互后 {m['animations_after_interaction']}")
        lt = m["long_tasks_ms"]
        print(f"  长任务 >50ms：{len(lt)} 个 {lt[:8]}")

    print(f"\n基线已写入 {OUT}")
    print("注：本 probe 是**量尺**不是闸门——它不做通过/失败判定，"
          "只产出 spec.md 引用的当前值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
