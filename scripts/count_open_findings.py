"""count_open_findings.py — 阶段闸门第 1 条的可复验点数器（审查轨 R118a）。

`docs/PHASE.md` 闸门 1 要求「OPEN 的 BLOCKER/MAJOR 为零」，但原表格里那格
写的是「人工点数」——人工点数不是可复现命令，违反宪法第一条。本脚本把它
变成命令。

为什么不能用裸 grep：`AUDIT_FINDINGS.md` 里有「条目格式」示范块与严重级
定义表，`^- 状态：OPEN` 会多命中一次（实测 10 vs 真实 9）。本脚本只识别
`### R<n>a-<seq>` 开头的真实条目。

退出码：0 = OPEN 的 BLOCKER/MAJOR 为零（闸门 1 通过）；1 = 仍有 OPEN。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "AUDIT_FINDINGS.md")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ITEM_RE = re.compile(r"^### (R\d+a-\d+)\s+(.*?)$(.*?)(?=^### |^---\s*$)",
                     re.S | re.M)
BLOCKING = ("BLOCKER", "MAJOR")


def main() -> int:
    text = open(DOC, encoding="utf-8").read()
    rows = []
    for ident, title, body in ITEM_RE.findall(text):
        status = re.search(r"^- 状态：(\S+)", body, re.M)
        sev = re.search(r"^- 严重级：(BLOCKER|MAJOR|MINOR|NIT)", body, re.M)
        rows.append({
            "id": ident, "title": title.strip(),
            "status": status.group(1) if status else "?",
            "sev": sev.group(1) if sev else "?",
        })
    if not rows:
        print("count_open_findings FAIL: 未解析到任何条目——"
              "格式可能已变，闸门 1 不可判定")
        return 1

    open_blocking = [r for r in rows
                     if r["status"] == "OPEN" and r["sev"] in BLOCKING]
    print(f"{DOC}")
    print(f"条目总数 {len(rows)}")
    for r in rows:
        mark = "→闸门" if (r["status"] == "OPEN" and r["sev"] in BLOCKING) else ""
        print(f"  {r['id']:<12} {r['sev']:<8} {r['status']:<14} {mark} "
              f"{r['title'][:44]}")
    n_b = sum(1 for r in open_blocking if r["sev"] == "BLOCKER")
    n_m = sum(1 for r in open_blocking if r["sev"] == "MAJOR")
    print(f"\nOPEN BLOCKER {n_b} / OPEN MAJOR {n_m} / 合计 {len(open_blocking)}")
    if open_blocking:
        print("闸门 1 = FAIL（CURRENT_PHASE 必须保持 REPAIR）")
        return 1
    print("闸门 1 = PASS（OPEN 的 BLOCKER/MAJOR 为零）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
