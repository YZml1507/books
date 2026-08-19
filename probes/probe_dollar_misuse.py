"""probe_dollar_misuse.py — `$()` 当对象用的静态闸门（审查轨 R119a，D-134a）。

**为什么单独立一个 probe**：`index.html:842` 定义的是**函数** `function $(id)`，
但代码里有大量 `$.rq.value` 写法——把函数当对象访问属性，得到 `undefined`，
随即 `undefined.value` 抛 `TypeError`。这是 R000a-01 的机制。

`probe_ui_smoke.py` 已经能在浏览器里抓到它的运行时后果，但那需要起服务 +
起浏览器（约 3 分钟）。本 probe 是**纯静态、零依赖、秒级**的同族闸门：
修复轨改完可以先跑它快速自查，再跑完整冒烟。两者不重复——
冒烟证明"点了有反应"，本 probe 证明"这个写法一个都不剩"。

它还产出一份 **按钮 → 受影响处数** 的映射，这是修复清单本身。

复现命令：
    C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe probes\\probe_dollar_misuse.py
退出码：0 = 零命中（闸门通过）；1 = 仍有 `$.xxx` 写法。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, "web", "static", "index.html")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# `$.` 紧跟标识符 = 把 $ 当对象用。合法写法只有 $('#id') / $(sel)。
MISUSE_RE = re.compile(r"\$\.[A-Za-z_]\w*")
# handler 归属：$('#btnId').addEventListener(...) 或 $('#form').addEventListener
HANDLER_RE = re.compile(r"\$\(\s*['\"]#(\w+)['\"]\s*\)\s*\.addEventListener")
# 函数定义归属（loadDaily / searchByWork 之类的裸函数）
FUNC_RE = re.compile(r"^\s*(?:async\s+)?function\s+(\w+)\s*\(")


def main() -> int:
    lines = open(INDEX_HTML, encoding="utf-8").read().split("\n")

    # 确认前提：$ 确实是函数而非对象（若哪天改成对象，本 probe 就该退休）
    dollar_def = [(i, l.strip()) for i, l in enumerate(lines, 1)
                  if re.match(r"\s*function \$\(", l)]
    print(f"$ 的定义：{dollar_def or '未找到'}")

    owner, rows = None, []
    for i, line in enumerate(lines, 1):
        m = HANDLER_RE.search(line)
        if m:
            owner = f"#{m.group(1)} handler"
        else:
            m = FUNC_RE.match(line)
            if m:
                owner = f"{m.group(1)}()"
        found = MISUSE_RE.findall(line)
        if found:
            rows.append({"line": i, "owner": owner or "(顶层)",
                         "hits": found, "src": line.strip()})

    n_lines = len(rows)
    n_hits = sum(len(r["hits"]) for r in rows)
    by_owner: dict[str, int] = {}
    for r in rows:
        by_owner[r["owner"]] = by_owner.get(r["owner"], 0) + len(r["hits"])

    print(f"\n`$.xxx` 误用：{n_lines} 行 / {n_hits} 处")
    if by_owner:
        print("\n按归属（= 修复清单）：")
        for owner, n in sorted(by_owner.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>3} 处  {owner}")
    if rows:
        print("\n逐行：")
        for r in rows:
            print(f"  index.html:{r['line']:<5} {r['owner']:<22} "
                  f"{','.join(r['hits'])}")
            print(f"      {r['src'][:100]}")

    # 反向确认：哪些 handler 完全干净（对修复很有用——证明逻辑本身没问题）
    all_handlers = [f"#{m.group(1)} handler" for line in lines
                    for m in [HANDLER_RE.search(line)] if m]
    clean = [h for h in all_handlers if h not in by_owner]
    print(f"\n完全不含 `$.` 的 handler（{len(clean)}/{len(all_handlers)}）："
          f"{', '.join(clean) or '无'}")

    if rows:
        print(f"\nprobe_dollar_misuse FAIL: {n_lines} 行 / {n_hits} 处仍把 "
              f"$() 函数当对象用，运行时必抛 TypeError")
        return 1
    print("\nprobe_dollar_misuse PASS: 零命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
