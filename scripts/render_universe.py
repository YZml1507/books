#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_universe.py — R12：全站「可渲染字符宇宙」。

纳入：static/{index.html,*.js,*.css,manifest.json,tarot/*.json}
      web/*.py、src/**/*.{py,json}、data/**（语料可被检索/阅读视图渲染）
排除：docs/specs/probes/scripts/.specify/.agents/licenses/requirements
      .git/node_modules/__pycache__/.md 文档/.txt 许可证与依赖清单
输出：/tmp/r12_universe.txt（fonttools --unicodes-file 用的十六进制码点）
       + 分扩展名统计 + 每片切片的保留字数估算。
"""
import io
import os
import re
import sys
import glob

ROOT = "/opt/books/app"
OUT = "/tmp/r12_universe.txt"
CJK = re.compile(
    r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\ufe30-\ufe4f\uff00-\uffef\u2000-\u206f]")
INC_DIRS = ("web", "src", "data")
SKIP_DIRS = ("__pycache__", "node_modules", "licenses", "raw_ext_meta")
INC_EXT = (".py", ".js", ".html", ".css", ".json", ".txt", ".svg", ".yml")
# data/ 下只算会被服务端读取的语料（raw/external/index/catalog）
SKIP_PATH = ("licenses", "requirements", "specs", "probes", "scripts",
             ".specify", ".agents", ".hermes", "docs", ".git")


def want(p):
    r = os.path.relpath(p, ROOT)
    top = r.split(os.sep)[0]
    if top not in INC_DIRS and top != "scripts":
        return False
    for s in SKIP_PATH:
        if ("/" + s + "/") in ("/" + r) or r.startswith(s + "/"):
            return False
    return os.path.splitext(p)[1].lower() in INC_EXT


per_ext = {}
allc = set()
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in (".git", "node_modules",
                                          "__pycache__", ".venv", "venv")]
    for n in fns:
        p = os.path.join(dp, n)
        if not want(p):
            continue
        try:
            t = io.open(p, encoding="utf-8").read()
        except Exception:
            continue
        c = set(CJK.findall(t))
        if not c:
            continue
        per_ext.setdefault(os.path.splitext(n)[1], set()).update(c)
        allc |= c

print("### R12 可渲染字符宇宙（纳入 data 语料）")
for e in sorted(per_ext):
    print("  %-6s %5d 字" % (e, len(per_ext[e])))
print("  合计唯一 %d 字" % len(allc))

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(",".join("%X" % ord(c) for c in sorted(allc)))
print("  已写 %s（%d 码点）" % (OUT, len(allc)))

# 每片保留多少
try:
    from fontTools.ttLib import TTFont
except Exception:
    print("  （无 fontTools，跳过切片估算）")
    sys.exit(0)
tot_keep = 0
rows = []
for f in sorted(glob.glob(os.path.join(
        ROOT, "web/static/fonts/lxgw/*.woff2"))):
    try:
        ft = TTFont(f)
        cm = set(ft.getBestCmap().keys())
    except Exception:
        continue
    keep = len(cm & allc)
    tot_keep += keep
    rows.append((os.path.basename(f), len(cm), keep))
print("\n-- 切片保留估算（保留/原有）--")
for name, orig, keep in rows[:6]:
    print("  %-44s %4d → %4d" % (name, orig, keep))
print("  …共 %d 片， glyph 总数 %d → %d（%.0f%%）"
      % (len(rows), sum(r[1] for r in rows), tot_keep,
         tot_keep / max(1, sum(r[1] for r in rows)) * 100))
# 粗估瘦身后体积：全量 2.6MB / 全 glyph 数 × 保留 glyph 数
tot_orig = sum(r[1] for r in rows)
est = 2607836 * tot_keep / max(1, tot_orig)
print("  估算瘦身后总体积 ≈ %.0fKB（原 2548KB）" % (est / 1024))
