"""Corpus quality gate: find damaged text and mis-extracted spans, with a control.

    python scripts/check_quality.py

Exits non-zero if the known-positive control stops being detected, so the gate cannot rot
into a no-op. Writes data/catalog/quality_report.json.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.quality import cross_edition_coverage  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")

# (A, B) where B is expected to embed A near-verbatim.
PAIRS = [("KR1a0006", "KR1a0007"), ("KR1a0031", "KR1a0032")]
bodies = {w: work_body(RAW, w)
          for w in {"KR1a0001", *[x for p in PAIRS for x in p]}}
polarity = derive_polarity(bodies)

report = {}
fails = []
for a, b in PAIRS:
    diffs = cross_edition_coverage(bodies[a], bodies[b], polarity)
    covs = sorted(d.coverage for d in diffs)
    med = covs[len(covs) // 2] if covs else 0.0
    # The final address of 卦64 absorbs whatever follows the last hexagram, and the editions
    # arrange the 十翼 differently there (31,523 vs 14,402 chars in KR1a0031/0032). That is
    # an artefact of where the span ends, not damage, so it is excluded rather than left to
    # inflate the count. Excluding it is only defensible because it is ONE known address.
    tail = [d for d in diffs if d.gua == 64 and d.coverage < 0.60]
    low = [d for d in diffs if d.coverage < 0.60 and d.gua != 64]
    print(f"\n{'='*78}\n{a} vs {b}: {len(diffs)} shared addresses, median coverage {med:.3f}")
    print(f"  below 0.60: {len(low)}")
    print(f"\n  {'cover':>6} {'contig':>7} {'卦':>4} {'爻':6} {'lenA':>6} {'lenB':>6}  verdict")
    for d in low:
        print(f"  {d.coverage:6.3f} {d.contiguity:7.3f} {d.gua:4} {d.yao:6} "
              f"{d.len_a:6} {d.len_b:6}  {d.verdict}")
    by_verdict = {}
    for d in low:
        by_verdict.setdefault(d.verdict, []).append(f"卦{d.gua}{d.yao}")
    for v, ks in sorted(by_verdict.items()):
        print(f"\n  {v}: {len(ks)}  {' '.join(ks)}")
    if tail:
        print(f"\n  excluded (卦64 tail absorbs the 十翼, arranged differently per edition): "
              f"{len(tail)}")
    report[f"{a}|{b}"] = {
        "shared": len(diffs), "median_coverage": med,
        "low": [{"gua": d.gua, "yao": d.yao, "coverage": round(d.coverage, 4),
                 "contiguity": round(d.contiguity, 4),
                 "len_a": d.len_a, "len_b": d.len_b, "verdict": d.verdict,
                 "text_a": d.text_a[:200], "text_b": d.text_b[:200]} for d in low],
    }

print(f"\n{'='*78}\n=== CONTROL: KR1a0006 卦61 中孚 must be detected as text damage ===")
ctl = report.get("KR1a0006|KR1a0007", {}).get("low", [])
hit = [x for x in ctl if x["gua"] == 61 and x["verdict"] == "text-damage"]
if hit:
    for h in hit:
        print(f"  [PASS] 卦61 {h['yao']} coverage {h['coverage']:.3f} "
              f"contiguity {h['contiguity']:.3f}  verdict {h['verdict']}")
        print(f"         damaged : {h['text_a'][:96]}")
        print(f"         witness : {h['text_b'][:96]}")
else:
    print("  [FAIL] control region no longer detected — the gate has stopped working")
    fails.append("control")

# KNOWN-NEGATIVE control, the mirror of the one above. A gate with only a positive control can
# drift into marking everything; a false 'damaged' flag makes the answering layer REFUSE sound
# text, and that is invisible unless someone reads the passage (L-20).
#
# 卦47 上六 is the case that forced this: contiguity 0.199 had it classified text-damage while
# it carries just 2 substitutions and a 92-character common run — KR1a0006's span simply runs
# on into 卦48 井. It must stay classified as a span problem, never as damage.
print(f"\n=== KNOWN-NEGATIVE CONTROL: 卦47 上六 must NOT be called text-damage ===")
neg = [x for x in ctl if x["gua"] == 47 and x["yao"] == "上六"]
if not neg:
    print("  [PASS] 卦47 上六 is not among the low-coverage outliers at all")
else:
    for n in neg:
        ok = n["verdict"] != "text-damage"
        print(f"  [{'PASS' if ok else 'FAIL'}] 卦47 上六 verdict={n['verdict']} "
              f"contiguity {n['contiguity']:.3f} (low contiguity is expected here; "
              f"the OCR signature is what must be absent)")
        if not ok:
            fails.append("known-negative 卦47")

with open(os.path.join(CAT, "quality_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print(f"\n-> data/catalog/quality_report.json")
print("PASS" if not fails else f"FAIL: {fails}")
sys.exit(1 if fails else 0)
