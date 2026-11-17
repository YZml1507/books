#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_slices.py — R12：把 50 个 lxgw 分片合并成一个完整 TTF。

要点：
- 新 glyph 一律**追加**到 glyphOrder 末尾 → 已有 glyph ID 不变，
  GSUB/GPOS/GDEF/morx 等按 ID 索引的表继续有效。
- 复合字形递归带上其组件。
- 输出 merged.ttf（TTF，再由 fonttools subset 出最终 woff2）。
"""
import glob
import os
import sys

from fontTools.ttLib import TTFont

SL = "/workspace/downloads/r12-font/slices"
OUT = "/workspace/downloads/r12-font/merged.ttf"


def main():
    files = sorted(glob.glob(os.path.join(SL, "*.woff2")))
    base = TTFont(files[0])
    glyf = base["glyf"]
    hmtx = base["hmtx"]
    cmap = dict(base.getBestCmap())
    order = list(base.getGlyphOrder())
    seen = set(order)
    ncopy = 0

    def copy_glyph(src, gname):
        nonlocal ncopy
        if gname in seen:
            return
        g = src["glyf"][gname]
        if getattr(g, "isComposite", lambda: False)():
            for comp in g.components:
                copy_glyph(src, comp.glyphName)
        glyf.glyphs[gname] = g
        hmtx.metrics[gname] = src["hmtx"].metrics[gname]
        if "vmtx" in src and "vmtx" in base:
            base["vmtx"].metrics[gname] = src["vmtx"].metrics[gname]
        seen.add(gname)
        order.append(gname)
        ncopy += 1

    for f in files[1:]:
        ft = TTFont(f)
        for cp, gname in sorted(ft.getBestCmap().items()):
            if cp in cmap:
                continue
            copy_glyph(ft, gname)
            cmap[cp] = gname
        ft.close()

    base.glyphOrder = order
    glyf.glyphOrder = order
    base["maxp"].numGlyphs = len(order)
    if hasattr(base["maxp"], "recalc"):
        try:
            base["maxp"].recalc(base)
        except Exception:
            pass
    base["hhea"].numberOfHMetrics = len(order)
    if "vhea" in base:
        base["vhea"].numberOfVMetrics = len(order)
    bmp = {cp: g for cp, g in cmap.items() if cp <= 0xFFFF}
    sup = {cp: g for cp, g in cmap.items() if cp > 0xFFFF}
    for st in base["cmap"].tables:
        st.cmap = dict(bmp)
    if sup:
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
        st12 = CmapSubtable.newSubtable(12)
        st12.platformID, st12.platEncID = 3, 10
        st12.language, st12.cmap = 0, dict(cmap)  # 全量：Chrome 优先选 (3,10)
        base["cmap"].tables.append(st12)
        print("  增补平面 %d 码点 → 新建 (3,10) format 12 子表" % len(sup))
    base.save(OUT)
    print("合并 %d 片 → %s" % (len(files), OUT))
    print("  glyph %d → %d（复制 %d）" % (
        len(seen) - ncopy, len(order), ncopy))
    print("  cmap %d 码点" % len(cmap))
    chk = TTFont(OUT)
    print("  复核 cmap %d，numGlyphs %d" % (
        len(chk.getBestCmap()), chk["maxp"].numGlyphs))


main()
