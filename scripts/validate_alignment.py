"""Score 卦/爻 alignment against a gold set derived FROM the base text.

Deliberately reports accuracy separately from coverage. The first attempt at this
problem reported 84% coverage while being wrong in ways coverage cannot see, so any
number here that could be mistaken for accuracy is labelled.

Gold construction: 爻辭 are read out of KR1a0001 (the 正文) by ordered 爻位 scan, never
typed from memory — a hand-written gold set had 屯 六二 wrong and scored 0 against the
corpus, which would have invalidated every downstream measurement.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import (clean, detect_mislabelled_yao, extract_yao, gua_spans,  # noqa: E402
                  lines_from_trigrams, yao_names)
from guji.anchors import HEX_RE, gua_number  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")
TRIGRAM_RE = re.compile(r"[（(]([^（()）/]{1,3})下\s*/?\s*([^（()）/]{1,3})上[）)]")

COMMENTARIES = ["KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
NAMES = {1: "乾", 2: "坤", 3: "屯"}


def body(work):
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt")))
    )


# ---------- derive 卦 -> line polarity from the corpus, not a hardcoded table ----------
def derive_lines(bodies):
    votes = {}
    for raw in bodies.values():
        for m in HEX_RE.finditer(raw):
            g = gua_number(m.group())
            t = TRIGRAM_RE.search(raw[m.start():m.start() + 40])
            if not t:
                continue
            lines = lines_from_trigrams(t.group(1), t.group(2))
            if lines:
                votes.setdefault(g, {}).setdefault(lines, 0)
                votes[g][lines] += 1
    return {g: max(v.items(), key=lambda kv: kv[1])[0] for g, v in votes.items()}


bodies = {w: body(w) for w in ["KR1a0001"] + COMMENTARIES}
LINES = derive_lines(bodies)
print(f"=== 卦 line polarity derived from corpus trigram notes: {len(LINES)}/64 ===")
missing = [g for g in range(1, 65) if g not in LINES]
if missing:
    print(f"  no trigram note found for 卦: {missing}")
qian, kun = LINES.get(1), LINES.get(2)
print(f"  sanity: 卦1={qian} -> {yao_names(qian) if qian else '?'}")
print(f"          卦2={kun} -> {yao_names(kun) if kun else '?'}")

# ---------- gold 爻辭 from the base text ----------
print("\n=== gold 爻辭 extracted from KR1a0001 ===")
base_raw = bodies["KR1a0001"]
base_spans, base_tail = gua_spans(base_raw)
print(f"  base spans={len(base_spans)} distinct={len({s.number for s in base_spans})}"
      f" tail_symbols={len(base_tail)}")

GOLD = {}
for s in base_spans:
    if s.number not in LINES or s.number in GOLD:
        continue
    exp = yao_names(LINES[s.number])
    view = clean(base_raw[s.start:s.end], keep_notes=False)
    hits = extract_yao(base_raw[s.start:s.end], exp, jing=view)
    entry = {}
    for label in exp:
        rng = hits.get(label)
        if rng:
            txt = view.text[rng[0] + len(label):rng[1]]
            # cut at the 象曰 that follows each 爻辭 in the 正文 layout
            txt = txt.split("象曰")[0]
            if txt:
                entry[label] = txt
    if entry:
        GOLD[s.number] = entry

full = [g for g, e in GOLD.items() if len(e) == len(yao_names(LINES[g]))]
print(f"  卦 with a complete 爻辭 set: {len(full)}/64")
for g in (1, 2, 3):
    if g in GOLD:
        print(f"  卦{g} {NAMES[g]}: " + " | ".join(
            f"{k}={v[:14]}" for k, v in GOLD[g].items()))

# ---------- score each commentary ----------
print(f"\n{'='*76}")
print(f"{'work':10} {'spans':>6} {'卦':>5} {'tail':>5} {'爻 located':>11} "
      f"{'爻辭 verified':>13} {'unknown':>8}")
print("-" * 76)
summary = {}
for w in COMMENTARIES:
    raw = bodies[w]
    spans, tail = gua_spans(raw)
    seen, located, verified, unknown = set(), 0, 0, 0
    per_gua = {}
    mislabelled = []
    for s in spans:
        if s.number not in LINES or s.number in seen:
            continue
        seen.add(s.number)
        exp = yao_names(LINES[s.number])
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=False)
        hits = extract_yao(seg, exp, jing=view)
        got = [k for k, v in hits.items() if v]
        located += len(got)
        unknown += len(exp) - len(got)
        # Separate "we failed to find it" from "the edition printed the wrong 爻位".
        for want, printed in detect_mislabelled_yao(view.text, exp):
            if not hits.get(want):
                mislabelled.append((s.number, want, printed))
        vok = 0
        for label in got:
            want = GOLD.get(s.number, {}).get(label)
            if not want:
                continue
            rng = hits[label]
            actual = view.text[rng[0] + len(label):rng[1]]
            head = want[:6]
            if head and head in actual:
                vok += 1
        verified += vok
        per_gua[s.number] = {"expected": len(exp), "located": len(got),
                             "verified": vok, "anchor": s.page_anchor}
    total_exp = sum(v["expected"] for v in per_gua.values())
    print(f"{w:10} {len(spans):6} {len(seen):5} {len(tail):5} "
          f"{located:>5}/{total_exp:<5} {verified:>6}/{located:<6} {unknown:8}")
    if mislabelled:
        print(f"{'':10} └ source anomalies (edition misprints the 爻位, not a parse "
              f"failure): {len(mislabelled)}")
        for g, want, printed in mislabelled:
            print(f"{'':12} 卦{g} expected {want}, printed "
                  f"{printed or '(nothing)'}")
    summary[w] = {"spans": len(spans), "gua": len(seen), "tail": len(tail),
                  "expected": total_exp, "located": located,
                  "verified": verified, "unknown": unknown,
                  "mislabelled": [[g, a, b] for g, a, b in mislabelled],
                  "per_gua": per_gua}

print("-" * 76)
print("爻 located    = an ordered 爻位 label was found inside the 卦 span (coverage)")
print("爻辭 verified = the text after that label matches the base-text 爻辭 (accuracy)")
print("unknown      = expected 爻 not located; reported, never guessed")

# ---------- the use case that motivates all of this ----------
print(f"\n{'='*76}\n乾九三 across commentators — the headline query\n{'='*76}")
for w in COMMENTARIES:
    raw = bodies[w]
    spans, _ = gua_spans(raw)
    s = next((x for x in spans if x.number == 1), None)
    if not s:
        print(f"{w}: 卦1 span not found")
        continue
    seg = raw[s.start:s.end]
    view = clean(seg, keep_notes=True)
    jing = clean(seg, keep_notes=False)
    hits = extract_yao(seg, yao_names(LINES[1]), jing=jing)
    rng = hits.get("九三")
    if not rng:
        print(f"{w}: 九三 not located")
        continue
    key = "君子終日乾乾"
    at = view.text.find(key)
    excerpt = view.text[at:at + 150] if at >= 0 else jing.text[rng[0]:rng[1]][:150]
    print(f"\n[{w}] page anchor {s.page_anchor}")
    print(f"  {excerpt}")

with open(os.path.join(CAT, "alignment_score.json"), "w", encoding="utf-8") as f:
    json.dump({"gold": GOLD, "summary": summary}, f, ensure_ascii=False, indent=1)
print("\nscores -> data/catalog/alignment_score.json")
