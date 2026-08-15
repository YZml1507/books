"""Acceptance tests for the index. Each one corresponds to a bug that actually happened.

Every test asserts on RETURNED TEXT, not on hit counts. A count-only test passes under
FTS5's implicit-AND semantics even when the phrase is not present, which is exactly how
the phrase-matching defect would have slipped through.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus, fold  # noqa: E402

c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))
print("stats:", c.stats())
fails = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print("\n=== coverage per work ===")
print(f"{'id':10} {'title':16} {'genre':6} {'units':>7} {'卦':>7} {'爻':>7} {'anchor':>7}")
print("-" * 70)
for r in c.coverage():
    print(f"{r['id']:10} {(r['title'] or '')[:16]:16} {(r['genre'] or '')[:6]:6} "
          f"{r['units']:7} {r['addressed'] or 0:7} {r['yao_addressed'] or 0:7} "
          f"{r['anchored'] or 0:7}")

print("\n=== T1: 2-char CJK query (plain FTS5 returns nothing without segmentation) ===")
hits = c.search("君子", limit=5)
check("君子 returns hits", len(hits) > 0, f"{len(hits)} hits")
check("every hit actually contains 君子",
      all("君子" in h.text for h in hits),
      f"{sum('君子' in h.text for h in hits)}/{len(hits)}")

print("\n=== T2: phrase adjacency, not implicit AND ===")
hits = c.search("見群龍无首", limit=8)
bad = [h for h in hits if "見群龍无首" not in fold(h.text)]
check("all hits contain the phrase contiguously", not bad,
      f"{len(hits)} hits, {len(bad)} violate adjacency")
if bad:
    print(f"      offender: {bad[0].text[:60]}")

print("\n=== T3: variant folding is symmetric (傳 must find 𫝊) ===")
hits = c.search("傳", limit=40, work_id="KR1a0007")
only_variant = [h for h in hits if "𫝊" in h.text and "傳" not in h.text]
check("傳 also matches 𫝊-only units", len(only_variant) > 0,
      f"{len(only_variant)} of {len(hits)} contain only 𫝊")

print("\n=== T4: cross-source inversion 無/无 both reachable ===")
a = c.search("見群龍无首", limit=20)
b = c.search("見群龍無首", limit=20)
check("無 and 无 spellings return the same count", len(a) == len(b) and len(a) > 0,
      f"无→{len(a)}, 無→{len(b)}")

print("\n=== T5: canonical address lookup — the headline capability ===")
groups = c.compare(1, "九三")
check("乾九三 found in >=3 works", len(groups) >= 3, f"{len(groups)} works")
for wid, hs in sorted(groups.items()):
    h = hs[0]
    print(f"  {h.citation()}")
    print(f"      {h.text[:72]}")

print("\n=== T6: 術數 works are searchable though they have no 卦 address ===")
for q, g in (("六壬", None), ("八字", None), ("葬", "堪輿")):
    hits = c.search(q, limit=3, genre=g)
    ok = all(fold(q) in fold(h.text) for h in hits) if hits else False
    check(f"{q!r} genre={g}", ok and len(hits) > 0,
          f"{len(hits)} hits" + (f", e.g. {hits[0].work_id}" if hits else ""))

print("\n=== T7: every citation is traceable to a file + anchor ===")
# The premise here used to be implicit and it was WRONG as a system invariant: 「every unit has
# a page anchor」 is a property of the Kanripo corpus, not of this system. Herodotus carries
# ZERO <pb:> markers, so indexing it would make a whole legitimate work fail this test — the
# same shape as the schema that encoded 卦/爻 as column names (D-015) and only broke when a
# second corpus arrived (L-21).
#
# So the assertion is now CONDITIONAL rather than relaxed (relaxing it would be GOAL §1's
# second red line): a file is always required, and a work must be EITHER fully anchored OR
# declared to have no pagination system. Partial anchoring stays a defect, because that means
# the extractor lost anchors it should have found.
NO_PAGINATION: set[str] = {
    "herodotus",        # Gutenberg txt: 0 <pb:> markers, 0 id=PageN — no pagination system
    "plato-republic",   # Jowett txt: 0 <pb:> markers, 0 Stephanus — BOOK I-X only
    "shakespeare",      # Gutenberg txt: 0 <pb:> markers — play/act/scene structure only
    "homer-iliad-but",  # Butler prose txt: 0 <pb:> markers, 0 line numbers — BOOK I-XXIV only
    "homer-iliad-pope", # Pope verse txt: 0 <pb:> markers, 10 sparse right-margin numbers — BOOK I-XXIV only
    "bible-douay",      # Gutenberg txt: 0 <pb:> markers — book/chapter/verse (bcv) addressing only
    "euclid-elements",  # Gutenberg html: 0 <pb:> markers — book/proposition addressing only
    # 7 部命理书（P2 语料扩充候选）：txt 单文件，按【书名·篇名】分篇，无 <pb:> 页锚点
    # 落盘于 data/raw/{slug}/{slug}_001.txt，ingest.py 按 raw 文件扫描入索引
    # 已过三道判定第一步（文献 vs 生成物：均为古籍原文），完整接入 bazi_lookup 见 P2
    "lantai-miaoxuan",
    "mingli-tanyuan",
    "mingli-yueyan",
    "sanming-tonghui",
    "wuxing-dayi",
    "wuxing-jingji",
    "ziping-zhenquan",
    "ditiansui",        # P2 缺口1：滴天髓（任铁樵阐微），【滴天髓·篇名】分段，无 <pb:>
    "qiongtongbaojian", # P2 缺口1：穷通宝鉴，【穷通宝鉴·篇名】分段，无 <pb:>
}

r = c.db.execute("SELECT count(*) n FROM unit WHERE file IS NULL OR file = ''").fetchone()
check("every unit names a source file", r["n"] == 0, f"{r['n']} without a file")

per = c.db.execute("""
    SELECT work_id, count(*) n, sum(page_anchor IS NULL) no_anchor
    FROM unit GROUP BY work_id""").fetchall()
partial = [(x["work_id"], x["no_anchor"], x["n"]) for x in per
           if x["no_anchor"] and x["no_anchor"] != x["n"]
           and x["work_id"] not in NO_PAGINATION]
unanchored = [x["work_id"] for x in per if x["no_anchor"] == x["n"]]
undeclared = [w for w in unanchored if w not in NO_PAGINATION]
check("no work is PARTIALLY anchored (that would mean anchors were lost)",
      not partial, f"{partial[:4]}")
check("every unanchored work is declared as having no pagination",
      not undeclared,
      f"undeclared unanchored works: {undeclared}" if undeclared
      else f"{len(unanchored)} fully-unanchored works, all declared")

print("\n=== T8: layer filter separates 經 from 注 ===")
jing = c.search("君子終日乾乾", limit=10, layer="經")
zhu = c.search("君子終日乾乾", limit=10, layer="注")
check("both layers return results", len(jing) > 0 and len(zhu) > 0,
      f"經={len(jing)}, 注={len(zhu)}")
check("layer labels are correct",
      all(h.layer == "經" for h in jing) and all(h.layer == "注" for h in zhu))

print("\n=== T9: citation disclosure — skipped_chars must match actual non-contiguity ===")
# The column is worthless if it disagrees with the text. Verified against the raw body, not
# against itself: a unit claiming skipped_chars=0 must be a contiguous substring of its own
# range, and one claiming >0 must not be. Sampled at 600 for runtime; the exhaustive version
# is probes/probe_disclosure.py.
import random as _rnd  # noqa: E402

from guji.evalset import in_space, raw_body  # noqa: E402

RAWDIR = os.path.join(ROOT, "data", "raw")
rows = c.db.execute("SELECT work_id, raw_start, raw_end, text, skipped_chars "
                    "FROM unit").fetchall()
_rnd.seed(13)
sample = _rnd.sample(list(rows), min(600, len(rows)))
_bodies: dict[str, str] = {}
wrong_zero = wrong_pos = 0
for r in sample:
    w = r["work_id"]
    if w not in _bodies:
        _bodies[w] = raw_body(RAWDIR, w)
    win = in_space(_bodies[w][r["raw_start"]:r["raw_end"]], "folded_notes")
    t = in_space(r["text"], "folded_notes")
    is_contig = t in win
    if r["skipped_chars"] == 0 and not is_contig:
        wrong_zero += 1
    if r["skipped_chars"] > 0 and is_contig:
        wrong_pos += 1
check("skipped_chars=0 really is contiguous", wrong_zero == 0,
      f"{wrong_zero} of {len(sample)} claim contiguous but are not")
check("skipped_chars>0 really is non-contiguous", wrong_pos == 0,
      f"{wrong_pos} of {len(sample)} claim skipped but are contiguous")
n_skip = c.db.execute("SELECT count(*) n FROM unit WHERE skipped_chars > 0").fetchone()["n"]
tot = c.db.execute("SELECT count(*) n FROM unit").fetchone()["n"]
check("the column carries information (not ~0% or ~100%)",
      0.05 < n_skip / tot < 0.95, f"{n_skip:,}/{tot:,} = {n_skip / tot:.1%} non-contiguous")

print("\n=== T10: suspect flags come from the quality gate and reach the citation ===")
n_susp = c.db.execute("SELECT count(*) n FROM unit WHERE suspect IS NOT NULL").fetchone()["n"]
check("known-damaged addresses are flagged", n_susp > 0, f"{n_susp} units flagged")
dmg = c.db.execute("SELECT work_id, addr1, addr2, suspect FROM unit "
                   "WHERE work_id='KR1a0006' AND addr1=61 AND addr2='上九'").fetchall()
check("CONTROL KR1a0006 卦61 上九 is flagged text-damage",
      bool(dmg) and all(d["suspect"] == "text-damage" for d in dmg),
      f"{[d['suspect'] for d in dmg]}")
h = c.at_address(61, "上九", limit=10)
flagged = [x for x in h if x.work_id == "KR1a0006"]
check("the flag is visible in the rendered citation",
      bool(flagged) and "?" in flagged[0].citation()
      and "质量闸门" in flagged[0].disclosure(),
      flagged[0].citation() if flagged else "no hit")
if flagged:
    print(f"      {flagged[0].disclosure()}")
meta = dict(c.db.execute("SELECT key, value FROM build_meta").fetchall())
check("suspect provenance recorded in build_meta",
      "suspect_source" in meta and meta["suspect_source"] != "MISSING — no flags applied",
      f"{meta.get('suspect_source')} @ {meta.get('suspect_mtime')} "
      f"({meta.get('suspect_addresses')} addresses)")

print("\n=== T11: the quality gate's calibration is asserted HERE (P-03) ===")
# guji.quality's docstring has always said "both functions below are calibrated against the
# 卦61 case and the calibration is asserted in scripts/verify_index.py". It was not — there was
# no such assertion in this file. A documented guarantee that nothing checks is worse than an
# undocumented one, because it gets cited as evidence. Asserting it for real now.
from guji.quality import cross_edition_coverage  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

_bodies = {w: work_body(RAWDIR, w) for w in ("KR1a0001", "KR1a0006", "KR1a0007")}
_pol = derive_polarity(_bodies)
_diffs = cross_edition_coverage(_bodies["KR1a0006"], _bodies["KR1a0007"], _pol)
_ctl = [d for d in _diffs if d.gua == 61 and d.yao == "上九"]
check("卦61 上九 is still detected as text-damage",
      bool(_ctl) and _ctl[0].verdict == "text-damage",
      f"{[(d.gua, d.yao, d.verdict, round(d.coverage, 3)) for d in _ctl]}")
_covs = sorted(d.coverage for d in _diffs)
_med = _covs[len(_covs) // 2] if _covs else 0.0
check("the 06/07 pair still embeds near-verbatim (median coverage >= 0.95)",
      _med >= 0.95, f"median {_med:.3f} over {len(_diffs)} shared addresses")
check("enough addresses are actually compared, not filtered away",
      len(_diffs) >= 358, f"{len(_diffs)} compared")

print("\n" + "=" * 70)
print(f"{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
c.close()
sys.exit(1 if fails else 0)
