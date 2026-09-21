"""READ-ONLY probe: the actual textual layout of KR3g0029 焦氏易林 (WYG / Kanripo).

Measures, never assumes:
  1 file inventory + markup census (# headers, <pb:>, ¶, hexagram symbols)
  2 the surface form of the structure: is it 「本卦 heading -> 之卦 entry」, and how is
    each entry written (bare 卦名 at column 0? 「之X」? something else?)
  3 role census for every 卦名 occurrence: heading / entry head / 之X / prose
  4 hexagram symbols U+4DC0..U+4DFF present at all?
  5 verbatim excerpts with raw offsets
  6 (本卦, 之卦) pair coverage vs 64x64, and the order of 之卦 within one 本卦
  7 addressing failure modes: 卦名 that are also ordinary words

Writes nothing. Offsets are offsets into ingest.load_work(RAW, "KR3g0029")[0], i.e. the
concatenated files with Org-mode 「#」 header lines blanked — the same space the index uses.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.stdout.reconfigure(encoding="utf-8")

from guji.ingest import _cn_number, derive_gua_names, load_work   # noqa: E402
from guji.variants import fold                               # noqa: E402
from guji.zhouyi import work_body                            # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORK = "KR3g0029"
PB_RE = re.compile(r"<pb:[^>]*>")
HEX_SYM = re.compile(r"[䷀-䷿]")
HEADING_RE = re.compile(r"([^\s　¶<>]{1,3})之第([一二三四五六七八九十]+)")
IDEO = "　"
DROP_FOR_CONTENT = set(" \t\r\n" + IDEO + "¶/")


def rule(title: str) -> None:
    print("\n" + "=" * 10 + " " + title + " " + "=" * 10)


def scan(text: str, forms: set[str], maxlen: int) -> list[tuple[int, str]]:
    """Non-overlapping longest-match scan -> [(offset, surface_form)]."""
    out: list[tuple[int, str]] = []
    i, n = 0, len(text)
    while i < n:
        for L in range(min(maxlen, n - i), 0, -1):
            if text[i:i + L] in forms:
                out.append((i, text[i:i + L]))
                i += L
                break
        else:
            i += 1
    return out


# ---- 1: inventory --------------------------------------------------------------------
rule("1 FILE INVENTORY + MARKUP CENSUS")
paths = sorted(glob.glob(os.path.join(RAW, WORK, "*.txt")))
tot_file = 0
for p in paths:
    src = open(p, encoding="utf-8").read()
    hdr = len(re.findall(r"^#.*$", src, flags=re.M))
    juan = re.findall(r"^#\+PROPERTY: JUAN (.*)$", src, flags=re.M)
    print(f"{os.path.basename(p):>20}  chars={len(src):>7}  #hdr={hdr:>2}  "
          f"pb={len(PB_RE.findall(src)):>4}  pilcrow={src.count('¶'):>5}  "
          f"JUAN={[j.strip() for j in juan]}")
    tot_file += len(src)
body, bounds = load_work(RAW, WORK)
print(f"files={len(paths)}  raw_chars_on_disk={tot_file}  body_chars(after # strip)={len(body)}")
print(f"file boundaries in body offsets: {bounds}")
print(f"body: pb={len(PB_RE.findall(body))}  pilcrow={body.count('¶')}  "
      f"newline={body.count(chr(10))}  ideographic_space={body.count(IDEO)}  "
      f"paren_open={body.count('(')}  slash={body.count('/')}")

# ---- gua names, derived from KR1a0001 ------------------------------------------------
rule("0 卦名 DERIVED FROM KR1a0001 《X第N》")
names = derive_gua_names(work_body(RAW, "KR1a0001"))
print(f"derive_gua_names -> {len(names)} entries; missing numbers: "
      f"{[n for n in range(1, 65) if n not in names]}")
print("  " + " ".join(f"{n}{names[n]}" for n in sorted(names)))
canon = {names[n]: n for n in names}
assert len(canon) == len(names), "duplicate 卦名"
# alias map: any surface form whose fold() equals a canonical name's fold()
folded_canon = {fold(k): v for k, v in canon.items()}
MAXLEN = max(len(k) for k in canon)
print(f"max 卦名 length = {MAXLEN}; 2-char names = "
      f"{sorted(k for k in canon if len(k) == 2)}")
sub = [(a, b) for a in canon for b in canon if a != b and a in b]
print(f"names that are substrings of another name: {sub}")

# collect actual surface forms present in the body that fold to a canonical name
present: dict[str, int] = {}
for L in (1, 2, 3):
    for i in range(len(body) - L + 1):
        s = body[i:i + L]
        if any(c in DROP_FOR_CONTENT or c in "<>:" for c in s):
            continue
        f = fold(s)
        if f in folded_canon and s not in canon:
            present[s] = present.get(s, 0) + 1
print(f"non-canonical surface forms folding to a 卦名 (variants in this book): "
      f"{sorted(present.items(), key=lambda kv: -kv[1])[:20]}")
FORMS = dict(canon)
for s in present:
    FORMS[s] = folded_canon[fold(s)]
# drop any alias that is a substring of a LONGER alias handled by longest-match anyway
print(f"total surface forms used for matching = {len(FORMS)}")
# ---- content view (markup stripped) with an offset map back to raw ---------------------
content_chars: list[str] = []
cmap: list[int] = []
i, n = 0, len(body)
while i < n:
    if body.startswith("<pb:", i):
        j = body.find(">", i)
        i = n if j == -1 else j + 1
        continue
    if body[i] not in DROP_FOR_CONTENT:
        content_chars.append(body[i])
        cmap.append(i)
    i += 1
content = "".join(content_chars)
raw2c = {r: k for k, r in enumerate(cmap)}

# ---- 2: line-shape census -------------------------------------------------------------
rule("2 LINE-SHAPE CENSUS (what does an entry actually look like?)")
kinds: Counter = Counter()
headings: list[tuple[int, str, int]] = []       # (raw offset of 卦名, name, 第N)
entries: list[tuple[int, str]] = []             # (raw offset of 卦名, surface form)
odd: list[str] = []
sections: list[dict] = []
pos = 0
for line in body.split("\n"):
    ls = pos
    pos += len(line) + 1
    after_pb = re.match(r"^(?:<pb:[^>]*>)*", line).end()
    rest = line[after_pb:]
    bare = rest.rstrip("¶").rstrip()
    if not bare.strip(IDEO + " "):
        kinds["blank_or_pb_only"] += 1
        continue
    hm = HEADING_RE.match(bare.lstrip(IDEO + " "))
    if hm and bare.startswith(IDEO):
        kinds["heading 「X之第N」"] += 1
        headings.append((ls + line.index(hm.group(0)), hm.group(1),
                         _cn_number(hm.group(2)) or -1))
        sections.append({"ben": hm.group(1), "n": _cn_number(hm.group(2)) or -1,
                         "at": ls, "zhi": []})
        continue
    form = None
    for L in range(min(MAXLEN, len(rest)), 0, -1):
        if rest[:L] in FORMS:
            form = rest[:L]
            break
    if form and rest[len(form):len(form) + 1] == IDEO:
        kinds["entry 「卦名+U+3000+辭」"] += 1
        entries.append((ls + after_pb, form))
        if sections:
            sections[-1]["zhi"].append((ls + after_pb, form))
        continue
    if form:
        kinds[f"starts with 卦名 but NOT followed by U+3000 (next={rest[len(form)]!r})"] += 1
        odd.append(f"@{ls} {line[:60]}")
        continue
    if rest.startswith(IDEO):
        kinds["continuation (leading U+3000)"] += 1
        continue
    kinds["other (no leading U+3000, no 卦名 head)"] += 1
    odd.append(f"@{ls} {line[:60]}")
for k, v in kinds.most_common():
    print(f"{v:>6}  {k}")
print(f"\nheadings={len(headings)}  entry-lines={len(entries)}")
print("first 20 non-conforming lines:")
for s in odd[:20]:
    print("   " + s)
print(f"...total non-conforming = {len(odd)}")
# ---- 3: role census for every 卦名 occurrence ------------------------------------------
rule("3 ROLE CENSUS FOR EVERY 卦名 OCCURRENCE")
occ_body = scan(body, set(FORMS), MAXLEN)
occ_cont = scan(content, set(FORMS), MAXLEN)
print(f"卦名 occurrences, body view (markup present) = {len(occ_body)}")
print(f"卦名 occurrences, content view (markup stripped) = {len(occ_cont)}")
print(f"distinct canonical 卦名 seen (content view) = "
      f"{len({FORMS[s] for _, s in occ_cont})}")
seen = {FORMS[s] for _, s in occ_cont}
print(f"canonical 卦名 with ZERO occurrences: "
      f"{[(n, names[n]) for n in sorted(names) if n not in seen]}")

head_off = {o for o, _, _ in headings}
entry_off = {o for o, _ in entries}
roles: Counter = Counter()
zhi_pairs: list[tuple[int, str, str]] = []      # (offset, prev_name_or_'', name) for 之X
prose_ctx: dict[str, list[int]] = defaultdict(list)
for o, s in occ_body:
    c = raw2c.get(o)
    prev = content[c - 1] if c is not None and c > 0 else ""
    if o in head_off:
        roles["A heading 本卦 (X之第N)"] += 1
    elif o in entry_off:
        roles["B entry head (卦名+U+3000)"] += 1
    elif prev == "之":
        roles["C preceded by 之"] += 1
        zhi_pairs.append((o, "", s))
    else:
        roles["D other / prose"] += 1
        prose_ctx[FORMS[s]].append(o)
tot = sum(roles.values())
for k, v in sorted(roles.items()):
    print(f"{v:>6}  {v / tot:6.2%}  {k}")
print(f"{tot:>6}          TOTAL")

print("\n-- 之 + 卦名 measured directly on the content view --")
zx = [(c, s) for c, s in occ_cont if c > 0 and content[c - 1] == "之"]
print(f"occurrences of 「之」 immediately followed by a 卦名 = {len(zx)}")
print(f"total 「之」 in content view = {content.count('之')}")
print(f"distinct 卦名 appearing in 之X position = {len({FORMS[s] for _, s in zx})}")
print("top 之X forms: " + ", ".join(
    f"之{k}:{v}" for k, v in Counter(s for _, s in zx).most_common(15)))
print("sample 之X contexts (content view offsets):")
for c, s in zx[:12]:
    print(f"   c@{c} raw@{cmap[c]}  …{content[max(0, c - 12):c + len(s) + 8]}…")

# ---- 4: hexagram symbols --------------------------------------------------------------
rule("4 HEXAGRAM SYMBOLS U+4DC0..U+4DFF")
syms = HEX_SYM.findall(body)
print(f"count in {WORK} body = {len(syms)}  distinct = {len(set(syms))}")
print("corpus-wide comparison (per work, first 8 non-zero):")
nz = []
for d in sorted(os.listdir(RAW)):
    if not os.path.isdir(os.path.join(RAW, d)):
        continue
    b = work_body(RAW, d)
    k = len(HEX_SYM.findall(b))
    if k:
        nz.append((d, k))
print("   " + ", ".join(f"{d}:{k}" for d, k in nz[:8]) + f"   (works with >0 = {len(nz)})")

# ---- 6a: adjacency (the disputed 3.4% vs 96.8%) ----------------------------------------
rule("6a ADJACENCY OF 卦名 (re-measuring the disputed figure)")
for label, occ, view in (("content view (markup stripped)", occ_cont, content),
                         ("body view (markup present)", occ_body, body)):
    adj = [(occ[k], occ[k + 1]) for k in range(len(occ) - 1)
           if occ[k][0] + len(occ[k][1]) == occ[k + 1][0]]
    distinct = {(FORMS[a[1]], FORMS[b[1]]) for a, b in adj}
    print(f"{label}: occurrences={len(occ)}  adjacent pairs={len(adj)}  "
          f"distinct pairs={len(distinct)}  "
          f"rate(adj/occ)={len(adj) / max(len(occ), 1):.2%}")
print("sample adjacent pairs in content view:")
adjc = [(occ_cont[k], occ_cont[k + 1]) for k in range(len(occ_cont) - 1)
        if occ_cont[k][0] + len(occ_cont[k][1]) == occ_cont[k + 1][0]]
for a, b in adjc[:10]:
    print(f"   c@{a[0]} {a[1]}|{b[1]}   …{content[max(0, a[0] - 10):b[0] + len(b[1]) + 10]}…")
# ---- 6b: section structure, pair coverage, ordering -------------------------------------
rule("6b SECTION STRUCTURE / (本卦,之卦) PAIR COVERAGE / ORDER")
print(f"sections (headings) = {len(sections)}")
print("本卦 sequence with 第N and entry count:")
for k, s in enumerate(sections):
    if k % 4 == 0:
        print("   ", end="")
    print(f"{s['n']:>3}{s['ben']}({len(s['zhi'])})  ", end="")
    if k % 4 == 3:
        print()
print()
ben_nums = [s["n"] for s in sections]
print(f"第N values: min={min(ben_nums)} max={max(ben_nums)} "
      f"distinct={len(set(ben_nums))} strictly_increasing={ben_nums == sorted(ben_nums)}")
print(f"本卦 names distinct = {len({s['ben'] for s in sections})}; "
      f"unknown to 卦名 list = {sorted({s['ben'] for s in sections} - set(FORMS))}")
print(f"第N matches King Wen number of 本卦 for "
      f"{sum(1 for s in sections if FORMS.get(s['ben']) == s['n'])}/{len(sections)} sections")
ecount = Counter(len(s["zhi"]) for s in sections)
print(f"entries per section distribution = {sorted(ecount.items())}")
print(f"total entries = {sum(len(s['zhi']) for s in sections)}  (theoretical 64x64 = 4096)")

pairs = {(FORMS[s['ben']] if s['ben'] in FORMS else s['ben'],
          FORMS[f]) for s in sections for _, f in s["zhi"]}
print(f"distinct (本卦,之卦) pairs = {len(pairs)}  of 4096 = "
      f"{len(pairs) / 4096:.2%}   self-pairs (本==之) = "
      f"{sum(1 for a, b in pairs if a == b)}")
dupe = [(s['ben'], [f for _, f in s['zhi']]) for s in sections
        if len({f for _, f in s['zhi']}) != len(s['zhi'])]
print(f"sections containing a repeated 之卦 = {len(dupe)}")
for b, lst in dupe[:5]:
    rep = [k for k, v in Counter(lst).items() if v > 1]
    print(f"   {b}: repeated {rep}")

ordered = 0
for s in sections:
    seq = [FORMS[f] for _, f in s["zhi"]]
    if seq == list(range(1, len(seq) + 1)):
        ordered += 1
print(f"sections whose 之卦 sequence is exactly King Wen 1..N = {ordered}/{len(sections)}")
for s in sections[:3]:
    seq = [FORMS[f] for _, f in s["zhi"]]
    bad = [(k + 1, seq[k]) for k in range(len(seq)) if seq[k] != k + 1]
    print(f"   {s['ben']}之: n={len(seq)} deviations from 1..N = {bad[:8]}")
missing_all = []
for s in sections:
    got = {FORMS[f] for _, f in s["zhi"]}
    miss = [n for n in range(1, 65) if n not in got]
    if miss:
        missing_all.append((s["ben"], [names[m] for m in miss]))
print(f"sections missing at least one of the 64 之卦 = {len(missing_all)}")
for b, m in missing_all[:8]:
    print(f"   {b}之 missing {m}")

# ---- 7: ambiguity / failure modes ------------------------------------------------------
rule("7 AMBIGUITY: 卦名 THAT ARE ALSO ORDINARY WORDS")
print(f"prose (role D) occurrences total = {sum(len(v) for v in prose_ctx.values())}")
print("top 20 by prose count  (canonical / prose count / entry-head count):")
entry_count = Counter(FORMS[f] for _, f in entries)
for g, lst in sorted(prose_ctx.items(), key=lambda kv: -len(kv[1]))[:20]:
    print(f"   {names[g]:<3} prose={len(lst):>4}  entry_head={entry_count.get(g, 0):>3}  "
          f"ratio_prose={len(lst) / (len(lst) + entry_count.get(g, 0)):.1%}")
print("\nverbatim prose contexts for the named suspects:")
for nm in ("比", "需", "復", "遯", "大有", "同人", "井", "革", "困", "臨", "豐", "旅"):
    g = FORMS.get(nm)
    if g is None or not prose_ctx.get(g):
        print(f"   {nm}: prose occurrences = 0")
        continue
    lst = prose_ctx[g]
    print(f"   {nm}: prose={len(lst)}")
    for o in lst[:3]:
        c = raw2c.get(o, 0)
        print(f"      raw@{o}  …{content[max(0, c - 14):c + 14]}…")

# ---- 5: verbatim excerpts --------------------------------------------------------------
rule("5 VERBATIM EXCERPTS (raw body offsets; newlines shown as \\n)")


def excerpt(label: str, at: int, span: int = 320) -> None:
    a = max(0, at)
    print(f"\n--- {label}  raw[{a}:{a + span}] ---")
    print(body[a:a + span].replace("\n", "\\n"))


if headings:
    excerpt("start of body proper (first heading 乾之第一 minus 120)", headings[0][0] - 120)
    mid = headings[len(headings) // 2]
    excerpt(f"mid-book heading {mid[1]}之第{mid[2]}", mid[0] - 60)
    last = headings[-1]
    excerpt(f"last heading {last[1]}之第{last[2]}", last[0] - 60)
# a page break landing inside a 林辭
m = re.search(r"[^\n¶]{6}¶\n<pb:[^>]*>¶\n" + IDEO, body)
if m:
    excerpt("page break inside a 林辭 (continuation line)", m.start() - 140)
# the 提要 prose that cites 震之蹇 — 之X in running prose, not an entry
z = body.find("震之蹇")
if z != -1:
    excerpt("提要 prose citing 「震之蹇」 (a 之X that is NOT an entry head)", z - 160)

rule("SUMMARY NUMBERS")
print(f"files={len(paths)} body_chars={len(body)} pb={len(PB_RE.findall(body))} "
      f"pilcrow={body.count('¶')}")
print(f"卦名 occurrences body={len(occ_body)} content={len(occ_cont)} "
      f"distinct={len(seen)}")
print(f"headings={len(headings)} entries={len(entries)} pairs={len(pairs)} "
      f"hexagram_symbols={len(syms)}")
print("role split: " + "  ".join(f"{k.split()[0]}={v}" for k, v in sorted(roles.items())))
print(f"之+卦名 = {len(zx)}   adjacency(content) = {len(adjc)} "
      f"({len(adjc) / max(len(occ_cont), 1):.2%})")

# ======================================================================================
# PASS 2 — 坎/習坎, the parenthetical cross-references, and the real false-positive rate
# ======================================================================================
rule("8 THIS BOOK'S OWN 卦名 SPELLINGS vs KR1a0001")
FORMS2 = dict(FORMS)
FORMS2["坎"] = 29          # this book writes 坎; KR1a0001 writes 習坎. NOT in FOLD.
FORMS2["㤗"] = 11          # 坤之泰's entry head is cut 㤗, not 泰. NOT in FOLD either.
print(f"「㤗」 (variant of 泰) occurrences = {body.count('㤗')}; "
      f"in FOLD = {'㤗' in fold.__globals__['FOLD']}")
book_spell: dict[int, Counter] = defaultdict(Counter)
pos = 0
for line in body.split("\n"):
    ls = pos
    pos += len(line) + 1
    rest = line[re.match(r"^(?:<pb:[^>]*>)*", line).end():]
    for L in range(min(MAXLEN, len(rest)), 0, -1):
        if rest[:L] in FORMS2 and rest[L:L + 1] == IDEO:
            book_spell[FORMS2[rest[:L]]][rest[:L]] += 1
            break
diff = [(n, names[n], dict(book_spell[n])) for n in sorted(book_spell)
        if set(book_spell[n]) != {names[n]}]
print(f"卦名 whose ENTRY-HEAD spelling in this book differs from KR1a0001: {len(diff)}")
for n, canonical, got in diff:
    folds = [k for k in got if fold(k) == fold(canonical) and k != canonical]
    print(f"   {n:>2} KR1a0001={canonical}  KR3g0029={got}  handled_by_FOLD={folds}")
print(f"「習坎」 occurrences in this book = {body.count('習坎')}; "
      f"「坎」 = {body.count('坎')}")

rule("9 RE-RUN LINE CENSUS WITH 坎 ADDED")
kinds2: Counter = Counter()
sections2: list[dict] = []
odd2: list[str] = []
pos = 0
for line in body.split("\n"):
    ls = pos
    pos += len(line) + 1
    after_pb = re.match(r"^(?:<pb:[^>]*>)*", line).end()
    rest = line[after_pb:]
    bare = rest.rstrip("¶").rstrip()
    if not bare.strip(IDEO + " "):
        kinds2["blank_or_pb_only"] += 1
        continue
    hm = HEADING_RE.match(bare.lstrip(IDEO + " "))
    if hm and bare.startswith(IDEO):
        kinds2["heading"] += 1
        sections2.append({"ben": hm.group(1), "n": _cn_number(hm.group(2)) or -1,
                          "at": ls + line.index(hm.group(0)), "zhi": []})
        continue
    form = next((rest[:L] for L in range(min(MAXLEN, len(rest)), 0, -1)
                 if rest[:L] in FORMS2), None)
    if form and rest[len(form):len(form) + 1] == IDEO:
        kinds2["entry"] += 1
        if sections2:
            sections2[-1]["zhi"].append((ls + after_pb, form))
        continue
    if rest.startswith(IDEO):
        kinds2["continuation"] += 1
        continue
    kinds2["other"] += 1
    odd2.append(f"@{ls} {line[:56]}")
print(dict(kinds2))
print(f"entries per section = {sorted(Counter(len(s['zhi']) for s in sections2).items())}")
print(f"total entries = {sum(len(s['zhi']) for s in sections2)}   sections = {len(sections2)}")
pairs2 = {(FORMS2[s['ben']], FORMS2[f]) for s in sections2 for _, f in s['zhi']}
print(f"distinct (本卦,之卦) pairs = {len(pairs2)} / 4096 = {len(pairs2) / 4096:.2%}")
print(f"remaining 'other' lines = {len(odd2)} (all in front matter?): "
      f"{sum(1 for s in odd2 if int(s[1:s.index(' ')]) < 2097)} of {len(odd2)} "
      f"are at offset < 2097 (= file _000)")
for s in odd2:
    if int(s[1:s.index(' ')]) >= 2097:
        print("   BODY-PROPER other: " + s)
rule("10 ORDER OF 之卦 WITHIN A SECTION")
h_first = sum(1 for s in sections2 if s["zhi"] and FORMS2[s["zhi"][0][1]] == FORMS2[s["ben"]])
print(f"sections whose FIRST entry is the 本卦 itself = {h_first}/{len(sections2)}")
model_ok = 0
devs = []
for s in sections2:
    seq = [FORMS2[f] for _, f in s["zhi"]]
    b = FORMS2[s["ben"]]
    model = [b] + [n for n in range(1, 65) if n != b]      # 本卦 first, then King Wen
    if seq == model:
        model_ok += 1
    else:
        devs.append((s["ben"], [(k, seq[k], model[k]) for k in range(min(len(seq), len(model)))
                                if seq[k] != model[k]][:4], len(seq)))
print(f"sections matching 「本卦 first, then King Wen 1..64 skipping 本卦」 = "
      f"{model_ok}/{len(sections2)}")
print(f"deviating sections = {len(devs)}:")
for b, d, ln in devs:
    print(f"   {b}: n_entries={ln} first deviations (idx, got, expected) = "
          f"{[(k, names[g], names[e]) for k, g, e in d]}")

rule("11 PARENTHETICAL CROSS-REFERENCE NOTES (where 之X actually lives)")
notes = re.findall(r"\(([^()]*)\)", content)
notes_all = "".join(notes)
print(f"note groups in content view = {len(notes)}  total note chars = {len(notes_all)}")
verse = re.sub(r"\([^()]*\)", "", content)
print(f"content chars = {len(content)}  verse-only chars (notes removed) = {len(verse)}")
# classify each 之X by whether it sits inside a (...) note
in_note = [False] * len(content)
for m in re.finditer(r"\([^()]*\)", content):
    for k in range(m.start(), m.end()):
        in_note[k] = True
zx_in = sum(1 for c, _ in zx if in_note[c])
print(f"之+卦名 total = {len(zx)}; inside a (...) note = {zx_in}; outside = {len(zx) - zx_in}")
occ_note = [(c, s) for c, s in occ_cont if in_note[c]]
print(f"卦名 occurrences inside notes = {len(occ_note)}")
print("sample notes containing 之X:")
shown = 0
for m in re.finditer(r"\(([^()]*)\)", content):
    if "之" in m.group(1) and shown < 12:
        print(f"   c@{m.start()} raw@{cmap[m.start()]}  {m.group(0)}")
        shown += 1
kinds_note: Counter = Counter()
for g in notes:
    if re.fullmatch(r"[^之]*之[^之]*", g) and "一作" not in g:
        kinds_note["single 之-reference"] += 1
    elif g.count("之") > 1:
        kinds_note["multiple 之-references"] += 1
    elif "一作" in g:
        kinds_note["一作 textual variant"] += 1
    elif g in ("同", "俱同"):
        kinds_note["「同」/「俱同」 only"] += 1
    else:
        kinds_note["other"] += 1
print(f"note kinds: {dict(kinds_note)}")
print("first 25 notes verbatim: " + " | ".join(notes[:25]))
rule("12 FALSE POSITIVES: 卦名 INSIDE THE 林辭 VERSE TEXT ITSELF")
# Build each entry's verse: from just after the entry-head 卦名 to the start of the next
# entry head / heading, with <pb:> tags, ¶, spaces and (...) notes removed.
marks: list[tuple[int, str, str]] = []      # (raw offset, kind, label)
for s in sections2:
    marks.append((s["at"], "H", s["ben"]))
    for o, f in s["zhi"]:
        marks.append((o, "E", f))
marks.sort()
verses: list[tuple[str, str, str]] = []     # (本卦, 之卦, verse text)
cur_ben = None
for k, (o, kind, label) in enumerate(marks):
    if kind == "H":
        cur_ben = label
        continue
    end = marks[k + 1][0] if k + 1 < len(marks) else len(body)
    seg = body[o + len(label):end]
    seg = PB_RE.sub("", seg)
    seg = "".join(c for c in seg if c not in DROP_FOR_CONTENT)
    seg = re.sub(r"\([^()]*\)", "", seg)
    verses.append((cur_ben, label, seg))
print(f"verses reconstructed = {len(verses)}  mean length = "
      f"{sum(len(v) for _, _, v in verses) / len(verses):.1f} chars  "
      f"min={min(len(v) for _, _, v in verses)} max={max(len(v) for _, _, v in verses)}")
fp: Counter = Counter()
fp_verses = 0
fp_examples: dict[str, list[str]] = defaultdict(list)
for ben, zh, v in verses:
    hits = scan(v, set(FORMS2), MAXLEN)
    if hits:
        fp_verses += 1
    for c, s in hits:
        fp[s] += 1
        if len(fp_examples[s]) < 2:
            fp_examples[s].append(v[max(0, c - 10):c + 10])
print(f"verses containing at least one 卦名 in the VERSE BODY = {fp_verses}/{len(verses)} "
      f"= {fp_verses / len(verses):.1%}")
print(f"total false-positive 卦名 tokens in verse bodies = {sum(fp.values())}")
print("top 25 offenders (surface form / count / 2 verbatim contexts):")
for s, k in fp.most_common(25):
    print(f"   {s:<3} {k:>4}   " + " ·· ".join(fp_examples[s]))
print("\nnamed suspects, verse-body counts: " + ", ".join(
    f"{nm}={fp.get(nm, 0)}" for nm in
    ("比", "需", "復", "遯", "大有", "同人", "井", "革", "困", "臨", "豐", "旅", "師", "履", "離")))

rule("13 WHAT A NAIVE 'ADJACENT 卦名' PAIR EXTRACTOR WOULD PRODUCE")
adj_pairs = Counter()
for k in range(len(occ_cont) - 1):
    a, b = occ_cont[k], occ_cont[k + 1]
    if a[0] + len(a[1]) == b[0]:
        adj_pairs[(FORMS[a[1]], FORMS[b[1]])] += 1
真 = {(FORMS2[s['ben']], FORMS2[f]) for s in sections2 for _, f in s['zhi']}
print(f"adjacent-pair extraction yields {sum(adj_pairs.values())} tokens, "
      f"{len(adj_pairs)} distinct pairs")
print(f"  of those distinct pairs, how many are REAL (本卦,之卦) pairs? "
      f"{len(set(adj_pairs) & 真)} / {len(adj_pairs)}")
print(f"  real pairs it MISSES: {len(真 - set(adj_pairs))} of {len(真)}")
print(f"  => recall {len(set(adj_pairs) & 真) / len(真):.2%}, "
      f"precision {len(set(adj_pairs) & 真) / max(len(adj_pairs), 1):.2%}")

rule("14 VERBATIM: THE TWO ANOMALIES (坤 missing 泰, 艮 repeating 小過)")
for s in sections2:
    if s["ben"] in ("坤", "艮"):
        seq = [FORMS2[f] for _, f in s["zhi"]]
        b = FORMS2[s["ben"]]
        model = [b] + [n for n in range(1, 65) if n != b]
        print(f"\n{s['ben']}之第{s['n']}: n_entries={len(seq)} "
              f"missing={[names[n] for n in range(1, 65) if n not in seq]} "
              f"repeated={[names[n] for n, c in Counter(seq).items() if c > 1]}")
        # locate the anomaly and print raw text around it
        for k in range(min(len(seq), len(model))):
            if seq[k] != model[k]:
                at = s["zhi"][k][0]
                print(f"   first divergence at entry idx {k}: got {names[seq[k]]}, "
                      f"model expects {names[model[k]]}; raw@{at}")
                print("   " + body[max(0, at - 200):at + 120].replace("\n", "\\n"))
                break

# ======================================================================================
# PASS 3 — entities, exact totals, cross-reference parse quality
# ======================================================================================
rule("15 &KRxxxx; ENTITIES (Kanripo placeholders for non-Unicode glyphs)")
ents = re.findall(r"&KR\d+;", body)
print(f"entity occurrences = {len(ents)}  distinct = {len(set(ents))}  "
      f"top = {Counter(ents).most_common(6)}")
ent_lines = [ln for ln in body.split("\n") if "&KR" in ln]
print(f"lines containing an entity = {len(ent_lines)}")
for ln in ent_lines[:4]:
    print("   " + ln[:90])
ent_at_head = sum(1 for ln in ent_lines
                  if re.match(r"^(?:<pb:[^>]*>)*&KR", ln))
print(f"entities at an ENTRY-HEAD position (would break 卦名 detection) = {ent_at_head}")

rule("16 EXACT 卦名 OCCURRENCE TOTALS (full form set incl. 坎, 㤗)")
occ_body2 = scan(body, set(FORMS2), MAXLEN)
occ_cont2 = scan(content, set(FORMS2), MAXLEN)
print(f"body view = {len(occ_body2)}   content view = {len(occ_cont2)}")
print(f"distinct canonical = {len({FORMS2[s] for _, s in occ_cont2})}")
print(f"  (pass-1 numbers WITHOUT 坎/㤗 were body={len(occ_body)} content={len(occ_cont)} "
      f"distinct=63 — the '63 distinct / ~6985' figures)")
adj2 = [(occ_cont2[k], occ_cont2[k + 1]) for k in range(len(occ_cont2) - 1)
        if occ_cont2[k][0] + len(occ_cont2[k][1]) == occ_cont2[k + 1][0]]
print(f"adjacency with full form set: pairs={len(adj2)} "
      f"rate={len(adj2) / len(occ_cont2):.2%} distinct="
      f"{len({(FORMS2[a[1]], FORMS2[b[1]]) for a, b in adj2})}")
roles2: Counter = Counter()
h2 = {s["at"] for s in sections2}
e2 = {o for s in sections2 for o, _ in s["zhi"]}
for o, s in occ_body2:
    c = raw2c.get(o)
    prev = content[c - 1] if c is not None and c > 0 else ""
    if o in h2:
        roles2["A heading 本卦"] += 1
    elif o in e2:
        roles2["B entry head"] += 1
    elif in_note[c] if c is not None else False:
        roles2["C inside a (...) note"] += 1
    else:
        roles2["D 林辭 verse text / front matter"] += 1
t2 = sum(roles2.values())
for k, v in sorted(roles2.items()):
    print(f"{v:>6}  {v / t2:6.2%}  {k}")

rule("17 CROSS-REFERENCE NOTES: CAN THEY BE PARSED AS (A之B) PAIRS?")
# Notes are cut across woodblock lines, so one logical note can appear as two paren groups
# in the content view: 「(否之革同人之)(否)」. Measure how often.
NOTE_ZX = re.compile(r"([^之]{1,2})之([^之]{1,2})")
ok = bad = 0
bad_ex = []
for g in notes:
    if "之" not in g or "一作" in g:
        continue
    frags = NOTE_ZX.findall(g)
    good = [(a, b) for a, b in frags if a in FORMS2 and b in FORMS2]
    if len(good) == len(frags) and frags:
        ok += 1
    else:
        bad += 1
        if len(bad_ex) < 12:
            bad_ex.append((g, frags))
print(f"notes containing 之: parse cleanly as (卦名之卦名)+ = {ok}; imperfect = {bad}")
print("imperfect examples (note, extracted fragments):")
for g, f in bad_ex:
    print(f"   {g!r} -> {f}")
trunc = [g for g in notes if g.endswith("之") or g.startswith("之")]
print(f"notes ending or starting with a bare 之 (cut across a woodblock line) = {len(trunc)}: "
      f"{trunc[:10]}")

rule("18 艮 ANOMALY: IS 小過 REALLY PRINTED TWICE?")
for s in sections2:
    if s["ben"] == "艮":
        for k, (o, f) in enumerate(s["zhi"]):
            if FORMS2[f] == 62:
                print(f"   idx {k} form={f} raw@{o}: "
                      + body[o:o + 46].replace("\n", "\\n"))
print(f"   「小畜」 in the 艮 section at all? "
      f"{'小畜' in body[sections2[51]['at']:sections2[52]['at']]}")
print(f"   (section 艮 spans raw {sections2[51]['at']}..{sections2[52]['at']})")

rule("19 NOTE PARSE WITH A REAL TOKENISER (longest-match 卦名 + 之)")


def tokenise(g: str):
    """-> list of ('G', canonical) / ('Z',) / ('X', char) tokens."""
    out = []
    i = 0
    while i < len(g):
        hit = None
        for L in (2, 1):
            if g[i:i + L] in FORMS2:
                hit = (g[i:i + L], L)
                break
        if hit and not (hit[0] == "之"):
            out.append(("G", FORMS2[hit[0]]))
            i += hit[1]
            continue
        if g[i] == "之":
            out.append(("Z",))
            i += 1
            continue
        out.append(("X", g[i]))
        i += 1
    return out


shape: Counter = Counter()
clean_pairs = 0
examples: dict[str, list[str]] = defaultdict(list)
for g in notes:
    if "之" not in g:
        continue
    toks = tokenise(g)
    sig = "".join(t[0] for t in toks)
    # canonical shape for a pure cross-reference list: (GZG)+  e.g. 泰之復同人之歸妹
    if re.fullmatch(r"(GZG)+", sig):
        shape["pure (GZG)+ — cleanly parseable"] += 1
        clean_pairs += sig.count("Z")
    elif re.fullmatch(r"(GZG)+G", sig):
        shape["(GZG)+G — trailing bare 卦名 (e.g. 姤之師比)"] += 1
    elif re.fullmatch(r"(GZG)*GZ", sig):
        shape["(GZG)*GZ — note CUT mid-reference at a line break"] += 1
    elif sig.endswith("X") and re.fullmatch(r"(GZG)+X+", sig):
        shape["(GZG)+ plus trailing 同/俱同 etc."] += 1
    elif "X" in sig:
        shape["contains non-卦名 chars (一作 variants, prose)"] += 1
        if len(examples["X"]) < 10:
            examples["X"].append(f"{g} [{sig}]")
    else:
        shape[f"other: {sig[:16]}"] += 1
        if len(examples["o"]) < 10:
            examples["o"].append(f"{g} [{sig}]")
tot_z = sum(1 for g in notes if "之" in g)
for k, v in shape.most_common():
    print(f"{v:>5}  {v / tot_z:6.1%}  {k}")
print(f"{tot_z:>5}          notes containing 之")
print("examples with non-卦名 chars:")
for e in examples["X"]:
    print("   " + e)
print("other examples:")
for e in examples["o"]:
    print("   " + e)

rule("20 REJOINING NOTES CUT ACROSS A WOODBLOCK LINE")
# Raw form of a cut note: 「(節之觀/大過之)¶\n　(困中孚/之泰)」 — the 「/」 is the column break
# inside the note (ingest._runs already strips it), and the closing/opening parens are
# artefacts of the cut. Rejoin adjacent groups when the shape demands it.
joined_ok = joined_fail = 0
fails = []
k = 0
while k < len(notes):
    g = notes[k]
    sig = "".join(t[0] for t in tokenise(g))
    need = re.fullmatch(r"(GZG)*GZ", sig) or (k + 1 < len(notes)
                                              and notes[k + 1].startswith("之"))
    if need and k + 1 < len(notes):
        merged = g + notes[k + 1]
        msig = "".join(t[0] for t in tokenise(merged))
        if re.fullmatch(r"(GZG)+", msig):
            joined_ok += 1
        else:
            joined_fail += 1
            if len(fails) < 10:
                fails.append(f"{g} + {notes[k + 1]} -> {merged} [{msig}]")
        k += 2
        continue
    k += 1
print(f"cut notes that rejoin into a clean (GZG)+ = {joined_ok}; "
      f"still imperfect = {joined_fail}")
for f in fails:
    print("   " + f)
print("\nraw evidence of one cut note:")
z = body.find("(節之觀/大過之)")
print("   " + body[z - 60:z + 90].replace("\n", "\\n") if z != -1 else "   (pattern absent)")

rule("21 HOW MANY CROSS-REFERENCES, AND DO THEY POINT AT REAL PAIRS?")
xrefs = set()
xref_tok = 0
for g in notes:
    toks = tokenise(g)
    for i in range(1, len(toks) - 1):
        if toks[i][0] == "Z" and toks[i - 1][0] == "G" and toks[i + 1][0] == "G":
            xrefs.add((toks[i - 1][1], toks[i + 1][1]))
            xref_tok += 1
print(f"cross-reference tokens (A之B inside notes) = {xref_tok}  distinct = {len(xrefs)}")
real = {(FORMS2[s['ben']], FORMS2[f]) for s in sections2 for _, f in s['zhi']}
print(f"of those distinct refs, resolve to an existing (本卦,之卦) entry = "
      f"{len(xrefs & real)} / {len(xrefs)} = {len(xrefs & real) / len(xrefs):.1%}")
print(f"unresolvable refs (would be dangling links) = {len(xrefs - real)}: "
      f"{[(names[a], names[b]) for a, b in sorted(xrefs - real)][:10]}")

rule("22 ADJACENCY SENSITIVITY: WHICH VIEW/FORM-SET GIVES WHICH NUMBER?")
from guji.variants import DROP        # noqa: E402

views = {
    "A raw body (nothing stripped)": body,
    "B body, pb tags removed only": PB_RE.sub("", body),
    "C variants.DROP applied, pb tags KEPT": "".join(c for c in body if c not in DROP),
    "D variants.DROP applied, pb removed": "".join(
        c for c in PB_RE.sub("", body) if c not in DROP),
    "E content view (pb + all space/¶/ / removed)": content,
    "F content view, notes also removed": re.sub(r"\([^()]*\)", "", content),
}
sets = {
    "64 canonical only (no variants)": set(canon),
    "63 canonical + book variants (pass 1)": set(FORMS),
    "64 canonical + variants + 坎/㤗 (pass 2)": set(FORMS2),
}
print(f"{'view':<46} {'form set':<40} {'occ':>6} {'adj':>5} {'dist':>5} {'rate':>7}")
for vn, v in views.items():
    for sn, S in sets.items():
        oc = scan(v, S, 2)
        ad = [(oc[k], oc[k + 1]) for k in range(len(oc) - 1)
              if oc[k][0] + len(oc[k][1]) == oc[k + 1][0]]
        dm = FORMS2 if "坎" in S else FORMS if len(S) > 64 else canon
        ds = {(dm[a[1]], dm[b[1]]) for a, b in ad}
        print(f"{vn:<46} {sn:<40} {len(oc):>6} {len(ad):>5} {len(ds):>5} "
              f"{len(ad) / max(len(oc), 1):>6.2%}")
print("\nfolded variants: also try fold() applied to corpus AND names")
fb = fold(body)
fcanon = {fold(k) for k in canon}
for vn, v in (("G fold(body), DROP applied, pb kept",
               "".join(c for c in fb if c not in DROP)),
              ("H fold(content view)", fold(content))):
    oc = scan(v, fcanon, 2)
    ad = [(oc[k], oc[k + 1]) for k in range(len(oc) - 1)
          if oc[k][0] + len(oc[k][1]) == oc[k + 1][0]]
    print(f"{vn:<46} {'64 folded canonical':<40} {len(oc):>6} {len(ad):>5} "
          f"{len({(a[1], b[1]) for a, b in ad}):>5} {len(ad) / max(len(oc), 1):>6.2%}")

print("\ncan 237 adjacent / 219 distinct be reproduced? further variants:")
one = {k for k in FORMS2 if len(k) == 1}
for label, v, S in (("single-char 卦名 only, content view", content, one),
                    ("single-char only, DROP view pb kept",
                     "".join(c for c in body if c not in DROP), one),
                    ("content view, self-pairs excluded", content, set(FORMS2))):
    oc = scan(v, S, 2)
    ad = [(oc[k], oc[k + 1]) for k in range(len(oc) - 1)
          if oc[k][0] + len(oc[k][1]) == oc[k + 1][0]]
    if "self-pairs" in label:
        ad = [(a, b) for a, b in ad if FORMS2[a[1]] != FORMS2[b[1]]]
    ds = {(FORMS2[a[1]], FORMS2[b[1]]) for a, b in ad}
    print(f"   {label:<44} occ={len(oc):>5} adj={len(ad):>4} distinct={len(ds):>4} "
          f"rate={len(ad) / max(len(oc), 1):.2%}")


