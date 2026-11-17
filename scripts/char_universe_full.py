#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""char_universe_full.py — R12 全仓字符宇宙（含语料/数据文件）。

比 char_universe.py 更狠：扫整个 repo（排除 .git/node_modules），
按扩展名分桶统计唯一 CJK 字符。用于「切片瘦身」的保留集：
任何可能被渲染的字符都必须留在某个切片里，否则退化系统字体。
"""
import io
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/opt/books/app"
SKIP = (".git", "node_modules", "__pycache__", ".venv", "venv")
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")
EXT = (".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".yml",
       ".yaml", ".svg")


def scan():
    per_ext = {}
    allc = set()
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP]
        for n in fns:
            e = os.path.splitext(n)[1].lower()
            if e not in EXT:
                continue
            p = os.path.join(dp, n)
            try:
                t = io.open(p, encoding="utf-8").read()
            except Exception:
                continue
            c = set(CJK.findall(t))
            per_ext.setdefault(e, set()).update(c)
            allc |= c
    return per_ext, allc


per, allc = scan()
print("### R12 全仓字符宇宙")
for e in sorted(per):
    print("  %-6s %5d 字" % (e, len(per[e])))
print("  合计唯一 %d 字" % len(allc))
# 与 50 切片可覆盖字符求交（能交付的才算数）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
cov = set()
import glob
try:
    from fontTools.ttLib import TTFont
except Exception:
    TTFont = None
if TTFont:
    for f in glob.glob(os.path.join(
            ROOT, "web", "static", "fonts", "lxgw", "*.woff2")):
        try:
            ft = TTFont(f)
            cov |= set(ft.getBestCmap().keys())
        except Exception:
            pass
    inter = allc & cov
    print("  50 切片可覆盖 %d 字；全仓字符中可被切片渲染 %d 字"
          % (len(cov), len(inter)))
    miss = allc - cov
    if miss:
        print("  不在切片覆盖内的 %d 字（今天就走系统字体，不影响瘦身）: %s"
              % (len(miss), "".join(sorted(miss))[:80]))
else:
    print("  （沙箱无 fontTools，跳过覆盖计算）")
