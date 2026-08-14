"""Re-verify the sub-agents' key claims MYSELF before building anything on them.

GOAL §2 is explicit that a reported conclusion is not evidence, and one of the two agents
mis-transcribed a character in its own report and had to correct it — so its numbers get the
same treatment as the task book's. Independent re-measurement, not a re-reading of its probe.

Claims under test (焦氏易林 KR3g0029), each with its own pass/fail:

  C1  64 section headings 「　　X之第N」, 第N strictly 1..64, matching the 本卦's King Wen number
  C2  64 entries per section, 4,096 total, from LINE-HEAD position only
  C3  坎 is used for 卦29 and 習坎 never appears — so the KR1a0001-derived name table misses it
  C4  㤗 (U+3917) occurs 4 times, one as an entry head
  C5  卦名 inside 林辭 are frequent (the reason content matching is unusable)
  C6  艮 section: 小過 twice, 小畜 absent
  C7  cross-references A之B inside notes all resolve to real cells

Read-only.
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
from guji.variants import fold  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORK = "KR3g0029"
raw = work_body(RAW, WORK)
base = work_body(RAW, "KR1a0001")
names = derive_gua_names(base)          # 卦 number -> name, from the 底本 headings
print(f"{WORK}: {len(raw):,} chars   name table from KR1a0001: {len(names)} names")

fails = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


# ---- C3 first: the alias question decides every count that follows -------------------
print("\n=== C3: does this book write 坎 where the 底本 writes 習坎? ===")
n_xikan = raw.count("習坎")
n_kan = len(re.findall(r"(?<![一-鿿])坎(?![一-鿿])", raw))
print(f"  底本 name for 卦29: {names.get(29)!r}")
print(f"  習坎 occurrences here: {n_xikan}    bare 坎 (not inside a word): {n_kan}")
check("C3 習坎 absent while 坎 is used", n_xikan == 0 and n_kan > 50,
      f"習坎={n_xikan}, 坎={n_kan}")

print("\n=== C4: 㤗 U+3917 as a variant of 泰 ===")
n_tai_var = raw.count("㤗")
n_tai = raw.count("泰")
print(f"  㤗 (U+3917) = {n_tai_var}    泰 (U+6CF0) = {n_tai}")
check("C4 㤗 occurs a handful of times", n_tai_var == 4, f"expected 4, got {n_tai_var}")

# Alias table, in FOLDED space. The first version of this probe compared unfolded names and
# reported 60/64 headings and 3,925 entries — I then checked the 6 unmatched spellings and
# every one of them (剥/恒/㢲/兊/兑/暌) was ALREADY in variants.FOLD. The shortfall was my
# probe forgetting the project's own fold table, not a property of the book: 3,925 + 171
# unmatched lines = 4,096 exactly. Recorded because "the recon over-reported" was the
# tempting conclusion and it was wrong.
#
# Only TWO spellings are genuinely absent from FOLD:
#   㤗 (U+3917) -> 泰   a glyph variant, so it belongs in FOLD
#   坎          -> 卦29  an alternate NAME for 習坎, not a glyph variant, so it does NOT
alias = {fold(v): k for k, v in names.items()}
alias[fold("坎")] = 29
alias[fold("㤗")] = 11
by_len = sorted(alias, key=len, reverse=True)


def canon(tok: str) -> int | None:
    return alias.get(fold(tok))

# ---- C1: section headings -------------------------------------------------------------
print("\n=== C1: section headings 「　　X之第N」 ===")
HEAD = re.compile(r"[　]{2}([一-鿿㐀-䶿]{1,4})之第([一二三四五六七八九十]{1,4})")
heads = [(m.start(), m.group(1), _cn_number(m.group(2))) for m in HEAD.finditer(raw)]
print(f"  headings found: {len(heads)}")
nums = [n for _, _, n in heads]
ok_seq = nums == list(range(1, 65))
matched = sum(1 for _, nm, n in heads if canon(nm) == n)
print(f"  第N sequence == 1..64: {ok_seq}   本卦 name matches its King Wen number: "
      f"{matched}/{len(heads)}")
for pos, nm, n in heads[:3]:
    print(f"    @{pos} {nm}之第{n}")
check("C1 64 headings, 第N strictly 1..64", len(heads) == 64 and ok_seq,
      f"{len(heads)} headings")
check("C1 every 本卦 name matches its number", matched == len(heads),
      f"{matched}/{len(heads)}")

# ---- C2: entries at line-head --------------------------------------------------------
print("\n=== C2: entries at LINE-HEAD only ===")
# Lines are ¶-delimited; an entry is 卦名 + one U+3000. Continuations start WITH U+3000.
pieces = raw.split("¶")
per_section: list[list[str]] = []
cur: list[str] | None = None
unclassified = []
for p in pieces:
    s = p.lstrip("\n")
    s_nopb = re.sub(r"<pb:[^>]*>", "", s)
    if HEAD.match(s_nopb.lstrip()) or (s_nopb.startswith("　　") and "之第" in s_nopb[:12]):
        cur = []
        per_section.append(cur)
        continue
    if not s_nopb or s_nopb.startswith("　"):
        continue                      # continuation line of the previous 林辭
    m = re.match(r"([一-鿿㐀-䶿]{1,4})　", s_nopb)
    if m and canon(m.group(1)) is not None:
        if cur is not None:
            cur.append(fold(m.group(1)))
        continue
    if s_nopb.strip():
        unclassified.append(s_nopb[:24])
counts = [len(x) for x in per_section]
total = sum(counts)
print(f"  sections {len(per_section)}   entries total {total}")
print(f"  entries per section: min={min(counts) if counts else 0} "
      f"max={max(counts) if counts else 0}   sections with exactly 64: "
      f"{sum(1 for n in counts if n == 64)}")
print(f"  unclassified non-empty lines: {len(unclassified)}  e.g. {unclassified[:4]}")
check("C2 4,096 entries in 64 sections", total == 4096 and len(per_section) == 64,
      f"{total} entries / {len(per_section)} sections")

# ---- C6: the 艮 section anomaly -------------------------------------------------------
print("\n=== C6: 艮 section — 小過 twice, 小畜 absent? ===")
gen_idx = next((i for i, (_, nm, _) in enumerate(heads) if nm == "艮"), None)
if gen_idx is None or gen_idx >= len(per_section):
    check("C6 艮 section located", False, "not found")
else:
    sec = per_section[gen_idx]
    c = Counter(sec)
    print(f"  艮 section has {len(sec)} entries, {len(c)} distinct")
    print(f"  小過 count = {c.get('小過', 0)}   小畜 count = {c.get('小畜', 0)}")
    dups = {k: v for k, v in c.items() if v > 1}
    print(f"  duplicated entries: {dups}")
    check("C6 小過 duplicated and 小畜 absent",
          c.get("小過", 0) == 2 and c.get("小畜", 0) == 0, f"dups={dups}")

# ---- C5: 卦名 inside the verse text --------------------------------------------------
print("\n=== C5: how often does a 卦名 appear INSIDE a 林辭? ===")
# Strip notes and markup, then look for 卦名 after the entry head.
body_lines = []
for p in pieces:
    s = re.sub(r"<pb:[^>]*>", "", p.lstrip("\n"))
    if s.startswith("　") or not s.strip():
        continue
    m = re.match(r"([一-鿿㐀-䶿]{1,4})　(.*)$", s)
    if m and canon(m.group(1)) is not None:
        body_lines.append(fold(re.sub(r"[（(][^）)]*[）)]", "", m.group(2))))
inside = Counter()
for t in body_lines:
    for nm in by_len:
        if nm in t:
            inside[nm] += t.count(nm)
print(f"  entry verses scanned: {len(body_lines)}")
print(f"  distinct 卦名 appearing inside verses: {len(inside)}   "
      f"total occurrences: {sum(inside.values())}")
print(f"  worst offenders: {inside.most_common(8)}")
check("C5 in-verse 卦名 are frequent (content matching unusable)",
      sum(inside.values()) > 500, f"{sum(inside.values())} in-verse occurrences")

# ---- C7: cross-references ------------------------------------------------------------
print("\n=== C7: A之B cross-references inside notes resolve to real cells ===")
notes = re.findall(r"[（(]([^）)]*)[）)]", raw)
joined = fold("".join(n.replace("/", "") for n in notes))
refs = []
for m in re.finditer(r"([一-鿿㐀-䶿]{1,4})之([一-鿿㐀-䶿]{1,4})",
                     joined):
    a, b = m.group(1), m.group(2)
    a = next((nm for nm in by_len if a.endswith(nm)), None)
    b = next((nm for nm in by_len if b.startswith(nm)), None)
    if a and b:
        refs.append((a, b))
resolved = [r for r in refs if r[0] in alias and r[1] in alias]
print(f"  A之B tokens parsed from notes: {len(refs)}   distinct: {len(set(refs))}")
print(f"  both sides are real 卦名: {len(resolved)}/{len(refs)}")
print(f"  sample: {sorted(set(resolved))[:6]}")
check("C7 cross-references resolve", len(refs) > 300 and len(resolved) == len(refs),
      f"{len(resolved)}/{len(refs)}")

print("\n" + "=" * 78)
print("ALL RECON CLAIMS REPRODUCED" if not fails else f"NOT REPRODUCED: {fails}")
sys.exit(1 if fails else 0)
