#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R8 spike：量 app.js 里可剥离子懒载的数据语料块占比。"""
import io
import re
import sys

s = io.open(sys.argv[1], encoding="utf-8").read()
n = len(s.encode("utf-8"))
print("app.js 总字节:", n)
blocks = []
for m in re.finditer(r"^(?:var|const|let)\s+(_?[A-Za-z_][\w]*)\s*=\s*([\[{])",
                     s, re.M):
    name, op = m.group(1), m.group(2)
    close = "]" if op == "[" else "}"
    j, depth, instr = m.end(2) - 1, 0, None
    while j < len(s):
        ch = s[j]
        if instr:
            if ch == "\\":
                j += 2
                continue
            if ch == instr:
                instr = None
        elif ch in ('"', "'", "`"):
            instr = ch
        elif ch == op:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                break
        j += 1
    if j < len(s):
        seg = s[m.start():j + 1]
        cjk = sum(1 for c in seg if "\u4e00" <= c <= "\u9fff")
        blocks.append((len(seg.encode("utf-8")), name,
                       round(cjk / max(len(seg), 1) * 100)))
blocks.sort(reverse=True)
tot = sum(b[0] for b in blocks)
print("顶层数据块合计: %dB = %.0f%%" % (tot, tot / n * 100))
for b in blocks[:12]:
    print("  %7dB %5.1f%% CJK%-3s %s" % (b[0], b[0] / n * 100, b[2], b[1]))
