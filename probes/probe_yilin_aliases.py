"""Which 卦名 spellings does 焦氏易林 use that the 底本-derived name table lacks?

probe_verify_recon.py reproduced 5 of 7 recon claims but not these two:
    C1  本卦 name matches its King Wen number:  60/64, the agent reported 64/64
    C2  entries:                             3,925, the agent reported exactly 4,096

Both shortfalls plausibly have ONE cause: this edition spelling some hexagram names
differently from KR1a0001, exactly as it writes 坎 for 習坎. A name my alias table lacks
fails twice over — once in its own section heading, and once for every entry line that
names it, which is ~64 entries per missing name. 171 missing entries / 64 ≈ 2.7, and 4
headings mismatch, so the arithmetic is at least consistent with that explanation.

This probe does not assume it. It prints the 4 mismatching headings and every unmatched
line-head token, so the actual spellings are visible.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.ingest import _cn_number, derive_gua_names  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
raw = work_body(RAW, "KR3g0029")
names = derive_gua_names(work_body(RAW, "KR1a0001"))
alias = {v: k for k, v in names.items()}
alias["坎"] = 29
alias["㤗"] = 11

HEAD = re.compile(r"[　]{2}([一-鿿㐀-䶿]{1,4})之第([一二三四五六七八九十]{1,4})")
heads = [(m.start(), m.group(1), _cn_number(m.group(2))) for m in HEAD.finditer(raw)]

print("=== headings whose name does not map to their own 第N ===")
bad = [(p, nm, n) for p, nm, n in heads if alias.get(nm) != n]
for p, nm, n in bad:
    print(f"  @{p:>7} 「{nm}之第{n}」   底本 name for 卦{n} = {names.get(n)!r}"
          f"   我的表里 {nm!r} -> {alias.get(nm)}")
    print(f"           codepoints: {[hex(ord(ch)) for ch in nm]}")
print(f"  total mismatching: {len(bad)}/{len(heads)}")

print("\n=== every line-head token that looks like an entry but is not in the table ===")
pieces = raw.split("¶")
unmatched = Counter()
examples: dict[str, str] = {}
for p in pieces:
    s = re.sub(r"<pb:[^>]*>", "", p.lstrip("\n"))
    if not s.strip() or s.startswith("　"):
        continue
    m = re.match(r"([一-鿿㐀-䶿]{1,4})　", s)
    if not m:
        continue
    tok = m.group(1)
    if tok not in alias:
        unmatched[tok] += 1
        examples.setdefault(tok, s[:46])
for tok, n in unmatched.most_common(20):
    print(f"  {tok!r} x{n:<4} {[hex(ord(c)) for c in tok]}   e.g. {examples[tok]}")
print(f"  distinct unmatched line-head tokens: {len(unmatched)}   "
      f"total lines: {sum(unmatched.values())}")

print("\n=== per-section entry counts with the CURRENT table (to see where they go missing) ===")
sections: list[tuple[str, int, list[str]]] = []
cur = None
for p in pieces:
    s = re.sub(r"<pb:[^>]*>", "", p.lstrip("\n"))
    hm = HEAD.match(s.lstrip())
    if hm:
        cur = (hm.group(1), _cn_number(hm.group(2)), [])
        sections.append(cur)
        continue
    if cur is None or not s.strip() or s.startswith("　"):
        continue
    m = re.match(r"([一-鿿㐀-䶿]{1,4})　", s)
    if m and m.group(1) in alias:
        cur[2].append(m.group(1))
short = [(nm, n, len(e)) for nm, n, e in sections if len(e) != 64]
print(f"  sections not at exactly 64 entries: {len(short)}/{len(sections)}")
for nm, n, k in short[:12]:
    print(f"    {nm}之第{n}: {k} entries  (short by {64 - k})")

print("\n=== which canonical names never appear as an entry head anywhere? ===")
seen = {tok for _, _, e in sections for tok in e}
missing = [(k, v) for k, v in sorted(names.items()) if v not in seen]
print(f"  canonical names never used as an entry head: {len(missing)}")
for num, nm in missing:
    alt = [t for t in unmatched if t and t[0] == nm[0]]
    print(f"    卦{num} {nm!r}   similar unmatched tokens: {alt[:4]}")
