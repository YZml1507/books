"""probe_dollar_misuse.py — 「函数当对象用」的静态闸门（审查轨 R119a→R120a）。

**原始机制（R000a-01）**：`index.html:842` 定义的是**函数** `function $(id)`，
但代码里有 61 处 `$.rq.value` 写法——把函数当对象访问属性，得到 `undefined`，
随即 `undefined.value` 抛 `TypeError`。

**R120a 泛化（D-138a）**：R178b 重构删掉了 `$`，改用 `el()` / `val()` / `num()`
三个取值函数，于是"只查 `$.`"的判据前提消失——probe 一度报「0 命中」，
那是**假通过**（宪法第四条 U-08：永远返回 0 的闸门等于没有闸门）。
本 probe 因此改为查**这一类错误**而非那一个符号：

  自动扫出文件里所有顶层 `function name(...)` 定义，然后检查是否有任何一处
  把这些名字当对象访问属性（`name.foo`）。判据随代码自动更新——
  以后再改一次辅助函数命名，闸门依然有效，不需要人记得来改 probe。

`probe_ui_smoke.py` 能在浏览器里抓到运行时后果，但要起服务 + 起浏览器
（约 3 分钟）。本 probe 纯静态、零依赖、秒级：修复轨改完可先跑它自查。
两者不重复——冒烟证明"点了有反应"，本 probe 证明"这个写法一个都不剩"，
且覆盖冒烟的天然盲区（不在任何按钮 handler 里的代码路径）。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_dollar_misuse.py
退出码：0 = 零命中（闸门通过）；1 = 存在「函数当对象」写法；
        2 = probe 无法判定（前端载体找不到 / 扫不到任何函数定义）。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "web", "static")
# R120a：R178b 把内联 JS 拆到 app.js，前端 JS 不再只在 index.html 里。
# 扫描**所有**前端 JS 载体，否则 probe 会因为"找不到代码"而报 0 命中——
# 那是假通过，正是宪法第四条 U-08 要杜绝的（「永远返回 0 的闸门等于没有闸门」）。
SCAN_FILES = ["index.html", "app.js"]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# `$.` 紧跟标识符 = 把 $ 当对象用（R178b 前的原始形态，保留以防回退）。
DOLLAR_RE = re.compile(r"\$\.[A-Za-z_]\w*")
# handler 归属：$('#btnId').addEventListener(...) / on('btnId', fn)（R178b 起）
HANDLER_RE = re.compile(
    r"\$\(\s*['\"]#(\w+)['\"]\s*\)\s*\.addEventListener"
    r"|(?:^|\W)on\(\s*['\"](\w+)['\"]\s*,")
# 函数定义归属（loadDaily / doSearch 之类的裸函数）
FUNC_RE = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(")
# 取值/工具函数：这些是**被当成对象误用**的高危对象。自动从代码里扫出来，
# 不写死名字——写死会在下一次改名时静默失效。
DEF_RE = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(")
# JS 内建/宿主对象上的合法属性访问，不能算误用
BUILTIN_SAFE = {"document", "window", "console", "JSON", "Math", "Object",
                "Array", "String", "Number", "Date", "Promise", "location",
                "navigator", "history", "localStorage", "sessionStorage"}


def main() -> int:
    targets = [(f, os.path.join(STATIC, f)) for f in SCAN_FILES
               if os.path.exists(os.path.join(STATIC, f))]
    if not targets:
        print(f"probe_dollar_misuse FAIL-ENV: {SCAN_FILES} 在 {STATIC} 全部不存在"
              f"——前端载体改名了？probe 必须先能找到代码才能判定"
              f"（零命中 ≠ 通过，见宪法第四条 U-08）")
        return 2

    print(f"扫描载体：{', '.join(f'{f}（{os.path.getsize(p)}B）' for f, p in targets)}")

    # 第一趟：扫出所有函数名（含 $ 若仍存在），它们是"可能被当对象误用"的对象
    sources = {}
    func_names: set[str] = set()
    has_dollar = False
    for fname, path in targets:
        text = open(path, encoding="utf-8").read()
        sources[fname] = text.split("\n")
        for line in sources[fname]:
            m = DEF_RE.match(line)
            if m:
                func_names.add(m.group(1))
            if re.search(r"function \$\(|const \$\s*=|let \$\s*=", line):
                has_dollar = True
                func_names.add("$")
    print(f"扫到函数定义 {len(func_names)} 个"
          f"（`$` {'仍存在' if has_dollar else '已不存在'}）")
    if not func_names:
        print("probe_dollar_misuse FAIL-ENV: 扫不到任何 function 定义。"
              "前端可能改成了别的组织方式（class / 模块 / 打包产物），"
              "本 probe 的判据前提不成立——报 0 命中会是假通过。")
        return 2

    # 第二趟：找「函数名.属性」这种把函数当对象用的写法
    misuse_re = re.compile(
        r"(?<![\w.$])(" + "|".join(re.escape(n) for n in sorted(func_names, key=len, reverse=True))
        + r")\.([A-Za-z_]\w*)")
    rows, all_handlers = [], []
    for fname, lines in sources.items():
        owner = None
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            m = HANDLER_RE.search(line)
            if m:
                btn = m.group(1) or m.group(2)
                owner = f"#{btn} handler"
                all_handlers.append(owner)
            else:
                m2 = FUNC_RE.match(line)
                if m2:
                    owner = f"{m2.group(1)}()"
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            hits = []
            for mm in misuse_re.finditer(line):
                obj, prop = mm.group(1), mm.group(2)
                if obj in BUILTIN_SAFE:
                    continue
                # 函数对象上的合法属性（call/apply/bind/name/length）不算误用
                if prop in ("call", "apply", "bind", "name", "length",
                            "prototype", "toString"):
                    continue
                hits.append(f"{obj}.{prop}")
            if hits:
                rows.append({"file": fname, "line": i, "owner": owner or "(顶层)",
                             "hits": hits, "src": stripped})

    n_lines = len(rows)
    n_hits = sum(len(r["hits"]) for r in rows)
    by_owner: dict[str, int] = {}
    for r in rows:
        by_owner[r["owner"]] = by_owner.get(r["owner"], 0) + len(r["hits"])

    print(f"\n「函数当对象用」（`函数名.属性`）：{n_lines} 行 / {n_hits} 处")
    if by_owner:
        print("\n按归属（= 修复清单）：")
        for owner, n in sorted(by_owner.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3} 处  {owner}")
    if rows:
        print("\n逐行：")
        for r in rows:
            print(f"  {r['file']}:{r['line']:<5} {r['owner']:<22} "
                  f"{','.join(r['hits'])}")
            print(f"      {r['src'][:100]}")

    # 反向确认：哪些 handler 完全干净（对修复很有用——证明逻辑本身没问题）
    clean = [h for h in dict.fromkeys(all_handlers) if h not in by_owner]
    uniq_handlers = list(dict.fromkeys(all_handlers))
    print(f"\n完全不含 `$.` 的 handler（{len(clean)}/{len(uniq_handlers)}）："
          f"{', '.join(clean) or '无'}")

    if rows:
        print(f"\nprobe_dollar_misuse FAIL: {n_lines} 行 / {n_hits} 处把函数"
              f"当对象访问属性，运行时得 undefined，再取值即抛 TypeError")
        return 1
    print(f"\nprobe_dollar_misuse PASS: 零命中"
          f"（检查了 {len(func_names)} 个函数名的属性访问）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
