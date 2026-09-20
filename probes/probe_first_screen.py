"""probe_first_screen.py — 首屏抵达成本闸门（审查轨 R128a，D-153a）。

**为什么存在**：`probe_ui_smoke` 有 37 个用例全绿，`specs/004` 判据 1/2/3 也全部
通过，但用户的真实体验是「全文只有引经据典，看不懂也不想看」。

原因是那些判据都测在**响应对象**上（`warm.one_liner` 长度、`warm` 里的术语数），
没有测**屏幕**。实测：一句话结论确实只有 11 字、首屏区块术语确实只有 2 个——
但它们渲染在第 **115 屏**（y=92,794px）。判据说合格，用户永远看不到。

    这是 D-149a 同族教训的第二次发作：
    判据必须测「用户真实感受到的东西」，不是测「数据结构里有没有」。

**本 probe 测什么**（全部契约驱动，不写死对方的类名——D-145a 教训）：

  1. **抵达成本**：先用 HTTP 拿 `warm.one_liner` 的真实文本，再在 DOM 里定位
     它的 y 坐标 → 「用户要滚多少像素/多少屏才看到人话」。
  2. **版面占比**：古籍原文块占结果区字数与高度的比例。
  3. **文本墙**：默认可见的单个文本块字数上限（当前实测最长 7,993 字）。
  4. **可核验性不丢**：折叠/截断后，展开的原文必须与 API 返回**逐字节一致**——
     宪法第三条要求引文可追溯，折叠 ≠ 删除。

**判据只在 warm（温柔）模式生效**。专业模式按 `specs/004` 判据 9 必须逐字节
不变，在那里报缺陷会逼出错误的修复（同 D-149a 的作用域纪律）。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_first_screen.py
退出码：0 = 全部达标；1 = 有未达标项；2 = 环境不可用/无法判定。
"""
from __future__ import annotations

import http.client
import json
import os
import socket
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

PORT_CANDIDATES = list(range(8340, 8360))
VIEWPORT = {"width": 375, "height": 812}     # 移动端基准视口（specs/003 基线）

# ── 判据阈值（写死在这里，spec 引用本文件）──────────────────
MAX_ONELINER_Y = 812          # 一句话结论必须在第 1 屏内
MAX_RESULT_SCREENS = 4        # warm 模式结果区总高 ≤ 4 屏
MAX_VISIBLE_BLOCK_CHARS = 400  # 默认可见的单块文字上限（防 7,993 字文本墙）
MAX_GUJI_SHARE_PCT = 40       # 古籍原文占结果区字数比例上限（当前 93%）

CASE = {"year": 1998, "month": 7, "day": 20, "hour": 14, "gender": "女",
        "question": "感情运怎么样？"}


def free_port(p: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) != 0


def http_json(port: int, method: str, path: str, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
    conn.request(method, path,
                 body=json.dumps(body) if body else None,
                 headers={"Content-Type": "application/json"} if body else {})
    return json.loads(conn.getresponse().read())


# 在 DOM 里按「真实文本」定位块，并统计版面构成。
# 传入 needle（warm.one_liner 的真实值）与 guji_heads（引文正文的开头片段），
# 全部来自 API 响应——不依赖任何 class 名。
LOCATE = r"""
([needle, gujiHeads, vh]) => {
  const r = document.getElementById('result');
  if (!r) return { error: 'no #result' };
  const norm = (s) => (s || '').replace(/\s+/g, '');

  // 「默认不可见」的判定。
  // ⚠ 不能只看 offsetParent===null || height===0——实测（R129a 亲验）
  // `<details>` 关闭态下子元素**仍有完整布局盒**：height=300px、
  // offsetParent 非 null、display=block（浏览器只是不绘制它）。
  // 若只用那个判据，任何用 <details> 做折叠的实现都会被判成"没折叠"，
  // 等于 probe 在强迫对方改用 hidden——**闸门不该规定实现方式**（D-145a）。
  // 故补上「祖先链上有关闭的 <details>」这一支，让 details / hidden /
  // display:none / 折叠面板等各种实现都能被正确识别。
  const isHidden = (el, box) => {
    if (el.offsetParent === null) return true;
    if (box && box.height === 0) return true;
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      if (p.tagName === 'DETAILS' && !p.open) return true;
      if (p.hasAttribute && p.hasAttribute('hidden')) {
        if (getComputedStyle(p).display === 'none') return true;
      }
      const st = getComputedStyle(p);
      if (st.display === 'none' || st.visibility === 'hidden') return true;
      if (st.contentVisibility === 'hidden') return true;
    }
    return false;
  };

  // 1. 一句话结论的位置：找**最深**的那个含 needle 的元素（避免命中整个卡片）
  let onel = null;
  const n = norm(needle);
  if (n) {
    let best = null;
    r.querySelectorAll('*').forEach(e => {
      if (e.children.length === 0 && norm(e.innerText).includes(n)) {
        const b = e.getBoundingClientRect();
        const y = Math.round(b.top + window.scrollY);
        if (best === null || y < best.y) {
          best = { y, y_viewport: Math.round(b.top),
                   text: e.innerText.trim() };
        }
      }
    });
    if (!best) {
      r.querySelectorAll('*').forEach(e => {
        if (norm(e.innerText).includes(n) && e.children.length <= 3) {
          const b = e.getBoundingClientRect();
          const y = Math.round(b.top + window.scrollY);
          if (best === null || y < best.y) {
            best = { y, y_viewport: Math.round(b.top),
                     text: e.innerText.trim() };
          }
        }
      });
    }
    onel = best;
  }

  // 2. 古籍原文块：按引文开头片段定位，统计默认可见的字数与高度。
  // ⚠ 每段引文**只取最深的那一个**命中元素。否则父容器与子元素会各计一次
  //   （实测曾报「48 段、占比 188%」——12 段引文 × 嵌套层级，占比超 100%
  //   本身就说明重复计数）。R129a 修正。
  let gujiChars = 0, gujiH = 0, gujiN = 0, gujiHidden = 0;
  const counted = new Set();
  gujiHeads.forEach(head => {
    const h = norm(head).slice(0, 22);
    if (!h) return;
    // 取所有「自身含该片段、但没有后代也含它」的元素 = 每次渲染的最内层节点。
    // 这样既不把父容器重复计一次，也**不会漏掉同一段被渲染多次**的情形
    // （R128a-01：j.evidence 全文版与 warm.citations 截断版同时上屏）。
    //
    // ⚠ 用 textContent 而非 innerText 定位（R130a 修正，优化轨 D-240b 报出）。
    //   实测：关闭态 <details> 内元素 innerText 长度 = **0**、textContent = 32。
    //   若用 innerText，`<details>` 折叠会定位到 **0 段**，判据 4 报「0%」——
    //   而「真把原文删掉」也是 0 段。两者在探针眼里完全一样，
    //   **等于无法区分折叠与删除，而那正是宪法第三条要守的唯一一件事。**
    //   textContent 不受 display/details 影响，两种机制都能定位到，
    //   再由 isHidden() 判断它是否默认可见 → 得到「定位 12 段 / 折叠 12 段」
    //   这样的阳性证据。
    const hits = [];
    r.querySelectorAll('*').forEach(e => {
      if (!norm(e.textContent).includes(h)) return;
      let childHas = false;
      for (const c of e.querySelectorAll('*')) {
        if (norm(c.textContent).includes(h)) { childHas = true; break; }
      }
      if (!childHas) hits.push(e);
    });
    hits.forEach(e => {
      if (counted.has(e)) return;
      counted.add(e);
      gujiN += 1;
      const b = e.getBoundingClientRect();
      if (isHidden(e, b)) { gujiHidden += 1; }
      // 可见块的字数用 textContent（与定位一致）；隐藏块不计入可见占比
      else { gujiChars += (e.textContent || '').length; gujiH += b.height; }
    });
  });

  // 3. 默认可见的最长文本块
  let worst = { chars: 0, head: '', y: 0 };
  r.querySelectorAll('*').forEach(e => {
    if (e.children.length > 0) return;
    const b = e.getBoundingClientRect();
    if (isHidden(e, b)) return;          // 同上：details 关闭态也算隐藏
    const t = (e.innerText || '').trim();
    if (t.length > worst.chars) {
      worst = { chars: t.length, head: t.slice(0, 50).replace(/\n/g, ' '),
                y: Math.round(b.top + window.scrollY) };
    }
  });

  const rb = r.getBoundingClientRect();
  return {
    result_top: Math.round(rb.top + window.scrollY),
    result_h: Math.round(rb.height),
    result_chars: (r.innerText || '').trim().length,
    result_screens: Math.ceil(rb.height / vh),
    doc_h: document.documentElement.scrollHeight,
    oneliner: onel,
    guji: { visible_chars: gujiChars, visible_h: Math.round(gujiH),
            n_found: gujiN, n_hidden: gujiHidden },
    worst_block: worst
  };
}
"""


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("probe_first_screen SKIP-ENV: playwright 未安装")
        return 2
    port = next((p for p in PORT_CANDIDATES if free_port(p)), None)
    if port is None:
        print("probe_first_screen SKIP-ENV: 无空闲端口（不抢占他人端口）")
        return 2

    from guji import history as history_db
    hist_baseline = history_db.count()

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

    failures: list[str] = []
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                c.request("GET", "/api/health")
                if c.getresponse().status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print("probe_first_screen SKIP-ENV: 服务未就绪")
            return 2

        # 契约侧：先拿真实响应，作为 DOM 定位的 needle 与可核验性基线
        api = http_json(port, "POST", "/api/bazi", CASE)
        warm = api.get("warm") or {}
        needle = warm.get("one_liner") or ""
        evidence = api.get("evidence") or []
        guji_heads = [(e.get("text") or "")[:40] for e in evidence if e.get("text")]
        if not needle:
            print("probe_first_screen SKIP-ENV: 响应无 warm.one_liner，"
                  "无法定位大白话（契约变了？）")
            return 2
        print(f"契约侧：warm.one_liner = {needle!r}")
        print(f"　　　　evidence {len(evidence)} 段，"
              f"合计 {sum(len(e.get('text') or '') for e in evidence):,} 字")

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport=VIEWPORT)
            page = ctx.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            page.wait_for_timeout(1500)
            mode = page.evaluate(
                "() => { try { return localStorage.getItem('voiceMode')"
                " || 'warm'; } catch (e) { return 'warm'; } }")
            print(f"　　　　当前口吻模式 = {mode}")
            if mode != "warm":
                print("probe_first_screen SKIP: 非 warm 模式，本闸门不判定"
                      "（专业模式按 specs/004 判据 9 逐字节不变）")
                return 0
            page.click(".func-card[data-view='bazi']")
            page.wait_for_selector("#view-bazi.active", timeout=5000)
            # ⚠ 必须把 CASE 的每个字段都填进表单。
            # 本 probe 第一版只填了 #question，其余走 HTML 默认值
            # （1990-05-15 男），于是**契约侧与浏览器侧跑的是两个不同的人**——
            # 契约侧拿 1998-07-20 女的引文去 1990-05-15 男的页面里找，
            # 两案引文交集只有 3/12，probe 于是报出 4 段"原文缺失"的**假阳性**。
            # 这个 bug 没被 needle 暴露，是因为两案的一句话结论恰好同为
            # 「感情这块，盘里有着落点」（由提问主题决定，与生日无关）。
            # 由优化轨 R184b 在模拟目标形态时发现并移交（D-154a）。
            page.fill("#year", str(CASE["year"]))
            page.fill("#month", str(CASE["month"]))
            page.fill("#day", str(CASE["day"]))
            page.fill("#hour", str(CASE["hour"]))
            page.select_option("#gender", CASE["gender"])
            page.fill("#question", CASE["question"])
            page.click("#submit")
            # 等结果区出现真实内容
            for _ in range(60):
                page.wait_for_timeout(400)
                if len((page.inner_text("#result") or "").strip()) > 80:
                    break
            page.wait_for_timeout(800)

            m = page.evaluate(LOCATE, [needle, guji_heads, VIEWPORT["height"]])
            if m.get("error"):
                print(f"probe_first_screen SKIP-ENV: {m['error']}")
                return 2

            vh = VIEWPORT["height"]
            print(f"\n=== 版面实测（{VIEWPORT['width']}×{vh}）===")
            print(f"  整页 {m['doc_h']:,}px　结果区 {m['result_h']:,}px "
                  f"= {m['result_screens']} 屏　共 {m['result_chars']:,} 字")

            # 判据 1：提交后无需滚动即可看到一句话结论。
            # ⚠ 口径订正（R129a）：原先量的是**文档绝对 y**，实测不可达——
            # `#result` 自身绝对 y 就是 3,005px（品牌 55 + 今日卡 577 +
            # 功能卡 618 + 最近/收藏 600 + 表单 888），即使结果区第一个像素就是
            # 那句话也是阈值的 3.7 倍。把绝对 y 当判据等于隐含要求前端删掉首页
            # 各块——那是 probe 在规定实现方式（D-145a 同族错误）。
            # 现改为量**相对当前视口顶部**的偏移：用户提交后不滚动能否看到。
            onel = m.get("oneliner")
            if not onel:
                failures.append("DOM 里找不到 warm.one_liner 的文本"
                                "（渲染分支没输出它？）")
                print("  ❌ 一句话结论：DOM 中未找到")
            else:
                y_doc = onel["y"]
                y_vp = onel.get("y_viewport", y_doc)
                ok = 0 <= y_vp <= MAX_ONELINER_Y
                print(f"  {'✅' if ok else '❌'} 一句话结论 "
                      f"相对视口 {y_vp:,}px（文档绝对 y={y_doc:,}px）"
                      f"　阈值 0–{MAX_ONELINER_Y}px（提交后无需滚动即可见）")
                print(f"      文本：{onel['text'][:60]!r}")
                if not ok:
                    failures.append(
                        f"提交后一句话结论在视口外（相对视口 {y_vp:,}px，"
                        f"文档绝对 {y_doc:,}px）——用户仍需滚动才看到人话。"
                        f"实现方式由优化轨定（上浮/滚动定位/独立视图皆可），"
                        f"但不得把「今日入口」永久藏死")

            # 判据 2：结果区总屏数
            ok = m["result_screens"] <= MAX_RESULT_SCREENS
            print(f"  {'✅' if ok else '❌'} 结果区 {m['result_screens']} 屏"
                  f"　阈值 ≤{MAX_RESULT_SCREENS} 屏")
            if not ok:
                failures.append(f"warm 模式结果区 {m['result_screens']} 屏，"
                                f"要求 ≤{MAX_RESULT_SCREENS} 屏")

            # 判据 3：默认可见的单块文字上限（防文本墙）
            w = m["worst_block"]
            ok = w["chars"] <= MAX_VISIBLE_BLOCK_CHARS
            print(f"  {'✅' if ok else '❌'} 默认可见最长文本块 {w['chars']:,} 字"
                  f"（y={w['y']:,}）　阈值 ≤{MAX_VISIBLE_BLOCK_CHARS} 字")
            if w["chars"]:
                print(f"      开头：{w['head']!r}")
            if not ok:
                failures.append(f"默认可见存在 {w['chars']:,} 字的文本墙，"
                                f"要求单块 ≤{MAX_VISIBLE_BLOCK_CHARS} 字"
                                f"（超出部分应折叠，不是删除）")

            # 判据 4：古籍占版面比例
            g = m["guji"]
            share = (g["visible_chars"] * 100 //
                     max(1, m["result_chars"]))
            ok = share <= MAX_GUJI_SHARE_PCT
            print(f"  {'✅' if ok else '❌'} 古籍原文默认可见 "
                  f"{g['visible_chars']:,} 字 = 结果区 {share}%"
                  f"　阈值 ≤{MAX_GUJI_SHARE_PCT}%")
            print(f"      定位到 {g['n_found']} 段，其中默认已折叠 "
                  f"{g['n_hidden']} 段")
            if not ok:
                failures.append(f"古籍原文占结果区 {share}% 字数，"
                                f"要求 ≤{MAX_GUJI_SHARE_PCT}%")

            # 判据 4b：「0% 可见」必须是**折叠**造成的，不能是**删除**造成的。
            # 这条是宪法第三条的守门人（优化轨 D-240b 指出旧版无法区分二者）。
            # 判据 4 只看「可见占比低」，低到 0 也算过——但若原文根本不在 DOM 里，
            # 占比同样是 0。故必须独立断言：定位到的段数 == API 返回的段数。
            n_api = len(evidence)
            if g["n_found"] < n_api:
                failures.append(
                    f"只在 DOM 中定位到 {g['n_found']} 段引文，"
                    f"而 API 返回 {n_api} 段——缺失的 {n_api - g['n_found']} 段"
                    f"是**被删除**而非被折叠。宪法第三条要求引文可追溯，"
                    f"折叠可以，删除不行。")
                print(f"  ❌ 折叠 vs 删除：定位 {g['n_found']} / API {n_api} 段"
                      f"——有段落不在 DOM 里")
            else:
                print(f"  ✅ 折叠 vs 删除：定位 {g['n_found']} 段 ≥ API {n_api} 段"
                      f"（{g['n_hidden']} 段默认折叠，"
                      f"{g['n_found'] - g['n_hidden']} 段默认可见）"
                      f"——原文都在 DOM 里，是折叠不是删除")

            # 判据 5：可核验性不丢——引文文本必须仍能在页面上取到（展开后逐字一致）
            print("\n=== 可核验性（宪法第三条：折叠 ≠ 删除）===")
            full = page.evaluate(
                """() => { const r = document.getElementById('result');
                     if (!r) return '';
                     // 包含被折叠内容的全文（textContent 不受 display 影响）
                     return (r.textContent || '').replace(/\\s+/g, ''); }""")
            missing = []
            for e in evidence[:6]:
                t = (e.get("text") or "").replace(" ", "").replace("\n", "")[:40]
                if t and t.replace("\u3000", "") not in full.replace("\u3000", ""):
                    missing.append(t[:24])
            cite_missing = []
            for e in evidence[:6]:
                cit = (e.get("citation") or "").replace(" ", "")
                if cit and cit not in full:
                    cite_missing.append(cit[:30])
            if missing:
                failures.append(f"{len(missing)} 段引文原文在页面上完全取不到"
                                f"（折叠可以，删除不行）：{missing}")
                print(f"  ❌ {len(missing)} 段原文缺失：{missing}")
            else:
                print("  ✅ 抽查 6 段引文原文均可在页面取到（含折叠内容）")
            if cite_missing:
                failures.append(f"{len(cite_missing)} 段引文的出处缺失："
                                f"{cite_missing}")
                print(f"  ❌ 出处缺失：{cite_missing}")
            else:
                print("  ✅ 抽查 6 段引文出处均在页面上")

            page.screenshot(
                path=os.path.join(ROOT, "logs", "first_screen_375.png"),
                full_page=False)
            ctx.close()
            browser.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        cleaned = []
        try:
            extra = history_db.count() - hist_baseline
            for rec in history_db.list_records(200)[:max(0, extra)]:
                if history_db.delete_record(rec["id"]):
                    cleaned.append(rec["id"])
        except Exception as exc:                      # noqa: BLE001
            print(f"⚠ 清理未完成：{type(exc).__name__}: {exc}")
        print(f"\n清理 history {len(cleaned)} 条；"
              f"行数 {hist_baseline} -> {history_db.count()}")

    if failures:
        print(f"\nprobe_first_screen FAIL: {len(failures)} 项未达标")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nprobe_first_screen PASS: 大白话在第 1 屏、无文本墙、"
          "古籍占比达标、引文可核验性完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
