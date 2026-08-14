"""Diagnose: which of the 44 TOC titles are NOT found in the body?"""
import re
import sys
sys.path.insert(0, "src")
from guji.play import TOC_ENTRIES, TITLE_RE
from pathlib import Path

raw = (Path("data/raw_ext/generality") / "shakespeare" / "pg100.txt").read_text(encoding="utf-8", errors="replace")
m = re.search(r"\*\*\* START.*?\*\*\*", raw, re.S)
body = raw[m.end():]
m2 = re.search(r"\*\*\* END", body)
body = body[:m2.start()]

# All ALL-CAPS title candidates found in body
body_titles = []
for m in TITLE_RE.finditer(body):
    body_titles.append(m.group(1).strip())

# Normalise both sides: curly quotes to straight
def norm(s):
    return s.replace("’", "'").replace("‘", "'").strip()

body_norm = set(norm(t) for t in body_titles)
toc_norm_list = [norm(t) for t in TOC_ENTRIES]
toc_norm = set(toc_norm_list)

print(f"body title candidates: {len(body_titles)}")
print(f"TOC entries: {len(TOC_ENTRIES)}")
print()
print("=== TOC entries NOT found as ALL-CAPS in body ===")
for t in TOC_ENTRIES:
    n = norm(t)
    if n not in body_norm:
        print(f"  MISSING: {t!r}")
        # Try to find it case-insensitively
        case_insens = re.search(re.escape(t), body, re.I)
        if case_insens:
            ctx = body[max(0, case_insens.start()-80):case_insens.end()+80]
            print(f"    found case-insensitively at {case_insens.start()}, ctx: ...{ctx!r}...")
        else:
            # Try just the distinctive part
            words = t.split()
            if len(words) > 2:
                key = " ".join(words[:3])
                ki = re.search(re.escape(key), body, re.I)
                if ki:
                    ctx = body[max(0, ki.start()-40):ki.end()+120]
                    print(f"    partial '{key}' found, ctx: ...{ctx!r}...")

print()
print("=== body ALL-CAPS lines that are NOT in TOC (first 20) ===")
not_in = [t for t in body_titles if norm(t) not in toc_norm]
for t in not_in[:20]:
    print(f"  {t!r}")
print(f"... total {len(not_in)} not in TOC")
