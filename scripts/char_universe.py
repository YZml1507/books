#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""char_universe.py — R12 数据：全站字符宇宙有多大。

扫描：index.html / app*.js / web/*.py / sw.js / manifest.json，
统计唯一 CJK 字符（含常用全角标点），分桶：
  · static  = index.html + web/*.py + sw.js（服务端模板/静态壳）
  · client  = app*.js 字符串字面量（含每日文案数据块）
  · 合并    = 全站唯一字符（自定义子集必须覆盖它，否则混排字体）
并给出「若按此字符集重建子集」的估算 Glyph 数。
"""
import io
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/opt/books/app"
ST = os.path.join(ROOT, "web", "static")

# CJK 统一表意 + 扩展A + 兼容 + 常用全角标点/符号
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")


def chars_of(text):
    return set(CJK.findall(text))


def read(p):
    try:
        return io.open(p, encoding="utf-8").read()
    except Exception:
        return ""


buckets = {"static": set(), "client": set(), "server_py": set()}
files = {"static": [], "client": [], "server_py": []}

html = read(os.path.join(ST, "index.html"))
buckets["static"] |= chars_of(html)
files["static"].append("index.html")

for f in sorted(os.listdir(ST)):
    if f.endswith(".js"):
        t = read(os.path.join(ST, f))
        buckets["client"] |= chars_of(t)
        files["client"].append(f)
mf = os.path.join(ST, "manifest.json")
if os.path.exists(mf):
    t = read(mf)
    buckets["static"] |= chars_of(t)
    files["static"].append("manifest.json")

for dirpath, _dirs, names in os.walk(os.path.join(ROOT, "web")):
    for n in names:
        if n.endswith(".py"):
            t = read(os.path.join(dirpath, n))
            buckets["server_py"] |= chars_of(t)
            files["server_py"].append(os.path.relpath(
                os.path.join(dirpath, n), ROOT))

allc = buckets["static"] | buckets["client"] | buckets["server_py"]
print("### R12 字符宇宙")
print("index.html        : %4d 字" % len(chars_of(html)))
print("app*.js (%d 个)   : %4d 字" % (len(files["client"]),
                                      len(buckets["client"])))
print("web/*.py (%d 个)  : %4d 字" % (len(files["server_py"]),
                                      len(buckets["server_py"])))
print("合并唯一字符      : %4d 字" % len(allc))
print("static∩client 重叠: %4d 字" % len(buckets["static"] &
                                         buckets["client"]))
# 常用度抽样：出现频次 top（判断骨架字）
freq = {}
for src in (html, "".join(read(os.path.join(ST, f))
                          for f in files["client"] if f.endswith(".js"))):
    for ch in CJK.findall(src):
        freq[ch] = freq.get(ch, 0) + 1
top = sorted(freq.items(), key=lambda x: -x[1])[:30]
print("\n最高频 30 字: %s" % "".join(c for c, _ in top))
once = sum(1 for c, n in freq.items() if n == 1)
print("只出现 1 次的字符: %d（长尾，子集切片元凶）" % once)
# 只出现一次且不在常用 3500 表思路：直接报告长尾占比
print("长尾占比: %.0f%%" % (once / max(1, len(freq)) * 100))
