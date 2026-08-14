"""Round 2: confirm the specific reference schemes, and check the Greek Iliad.

Round 1 told us WHICH books carry a scheme. This measures whether the scheme is
dense enough to align on, and whether PG52692 really is the Greek Iliad (its
gutendex language is 'la', which would be a problem for a cross-lingual test).
"""
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw_ext", "_probe")


def out(*a):
    print(*a)
    sys.stdout.flush()


def cached(pid):
    p = os.path.join(CACHE, f"pg{pid}.txt")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read().decode("utf-8", "replace")


def fetch_txt(pid):
    t = cached(pid)
    if t:
        return t
    with opener.open(f"https://gutendex.com/books/{pid}", timeout=90) as r:
        meta = json.loads(r.read().decode("utf-8"))
    url = None
    for m, u in meta["formats"].items():
        if m.startswith("text/plain") and not u.endswith(".zip"):
            url = u
            if "utf-8" in m:
                break
    if not url:
        out(f"  pg{pid}: no text/plain; formats={sorted(meta['formats'])}")
        return None
    with opener.open(url, timeout=240) as r:
        blob = r.read()
    with open(os.path.join(CACHE, f"pg{pid}.txt"), "wb") as f:
        f.write(blob)
    return blob.decode("utf-8", "replace")


# ---- 1. Republic 55201: Stephanus density ----
t = cached(55201)
steph = re.findall(r"\*(?:Ed\. Steph\. )?(\d{3}[A-E]?)\*", t)
pages = re.findall(r"\{(\d{1,4})\}", t)
out(f"[55201 Republic/Jowett] Stephanus markers={len(steph)} "
    f"distinct={len(set(steph))} first={steph[:6]} last={steph[-4:]}")
out(f"                        printed-page markers={len(pages)} "
    f"range={pages[:3]}..{pages[-3:] if pages else '-'}")
nfoot = len(re.findall(r"\[Footnote", t))
nside = len(re.findall(r"\[Sidenote", t))
out(f"                        [Footnote blocks={nfoot} [Sidenote={nside}")
m = re.search(r"\*565A\*", t)
out(f"                        contains *565A* marker: {bool(m)}")

# ---- 2. Iliad line numbers in each translation ----
for pid, lab in [(6130, "Pope"), (2199, "Butler"), (3059, "LangLeafMyers"),
                 (22382, "Buckley")]:
    t = cached(pid)
    if not t:
        continue
    ln = re.findall(r"^.{10,}?\s{2,}(\d{1,4})\s*$", t, re.M)
    books = re.findall(r"^\s*BOOK\s+([IVXLC]+)\.?\s*$", t, re.M | re.I)
    gk = len(re.findall(r"[ἀ-῿]", t))
    out(f"[{pid} Iliad {lab:14}] trailing-linenos={len(ln)} BOOK headings={len(books)} "
        f"greek_chars={gk} sample_books={books[:4]}")

# ---- 3. PG52692 Homeri Carmina — is the Greek actually there? ----
t = fetch_txt(52692)
if t:
    gk = len(re.findall(r"[ἀ-῿Ͱ-Ͽ]", t))
    la = len(re.findall(r"\b(et|in|est|non|qui)\b", t))
    out(f"[52692 Homeri Carmina] chars={len(t):,} greek_chars={gk:,} latin_hits={la}")
    out("  --- first Greek-dense window ---")
    for mm in re.finditer(r"[ἀ-῿]{4,}", t):
        s = max(0, mm.start() - 300)
        out(t[s:mm.start() + 500].replace("\r", ""))
        break
    # Book/line structure markers
    out(f"  ILIAS/Α headings: {re.findall(r'^\s*(?:ILIA[DS]|RHAPSOD|[Α-Ω])\.?\s*$', t, re.M)[:12]}")
    for pat in (r"^\s*(\d{1,3})\.\s*$", r"^\s{0,8}(\d{1,4})\s*$", r"\b(\d{1,3})\s*$"):
        out(f"  linenum pat {pat!r}: {len(re.findall(pat, t, re.M))}")
