"""Fetch a test set that can FALSIFY the claim "general book research infrastructure".

The corpus is 28 works, all Chinese 古籍, so nothing so far distinguishes a general system
from a 周易 system. The weakest point is not genre coverage — it is that exactly one
canonical addressing scheme (卦 + 爻位) has ever been implemented. So the set is chosen to
attack that:

  tier 1  MULTI-EDITION + canonical address   Bible book/chapter/verse across translations.
          The direct analogue of the 周易 case: same work, independent witnesses, an address
          scheme every edition shares. If the architecture is general, this needs a new
          address parser and NOTHING else.
  tier 2  DIFFERENT address shape             Plato (Stephanus), Shakespeare (act/scene),
          Euclid (book/proposition) — addresses that are not (chapter, verse) at all.
  tier 3  NO canonical address                Darwin, Gibbon — prose with only chapters,
          the case where the answer must be "page/offset anchor only", as with the 術數 works.

Fetched by explicit id (gutendex /books/{id}) rather than by search, because search burns
quota and returns unstable results.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
opener.addheaders = [("User-Agent", "book-research-fetch/0.2")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "raw_ext", "generality")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(DEST, exist_ok=True)

WANT = {
    # id: (slug, tier, expected address scheme)
    10:    ("bible-kjv",        1, "book/chapter/verse"),
    8294:  ("bible-web",        1, "book/chapter/verse"),
    1581:  ("bible-douay",      1, "book/chapter/verse"),
    1497:  ("plato-republic",   2, "stephanus/book"),
    100:   ("shakespeare",      2, "play/act/scene"),
    21076: ("euclid-elements",  2, "book/proposition"),
    2199:  ("homer-iliad-but",  1, "book/line"),
    6130:  ("homer-iliad-pope", 1, "book/line"),
    1228:  ("darwin-origin",    3, "chapter"),
    2707:  ("herodotus",        3, "book/section"),
}


def get(url, timeout=120):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        print(f"    transport: {type(e).__name__}: {e}")
        return None, b""


records = []
for gid, (slug, tier, scheme) in WANT.items():
    st, body = get(f"https://gutendex.com/books/{gid}")
    if st != 200:
        print(f"  #{gid} {slug}: metadata status={st}")
        continue
    b = json.loads(body.decode("utf-8"))
    d = os.path.join(DEST, slug)
    os.makedirs(d, exist_ok=True)
    saved = {}
    # Prefer plain text (parsers are already proven on text); keep EPUB to exercise
    # markitdown, which D-001 measured at 0 page markers.
    for mime, url in sorted(b["formats"].items()):
        if url.endswith(".zip"):
            continue
        ext = ("txt" if mime.startswith("text/plain") else
               "epub" if "epub" in mime else
               "html" if mime.startswith("text/html") else None)
        if not ext or ext in saved:
            continue
        st2, blob = get(url)
        if st2 != 200 or not blob:
            continue
        path = os.path.join(d, f"pg{gid}.{ext}")
        with open(path, "wb") as f:
            f.write(blob)
        saved[ext] = {"path": os.path.relpath(path, ROOT), "bytes": len(blob),
                      "sha256": hashlib.sha256(blob).hexdigest(), "url": url}
        print(f"  #{gid:6} {slug:18} {ext:5} {len(blob):>10,} bytes")
    records.append({
        "gutenberg_id": gid, "slug": slug, "tier": tier,
        "expected_address_scheme": scheme,
        "title": b.get("title", ""),
        "authors": [a["name"] for a in b.get("authors", [])],
        "translators": [a["name"] for a in b.get("translators", [])],
        "languages": b.get("languages", []),
        "copyright": b.get("copyright"),
        "files": saved,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    time.sleep(0.5)

with open(os.path.join(CAT, "generality_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
ok = [r for r in records if r["files"]]
print(f"\n{len(ok)}/{len(WANT)} works fetched -> data/catalog/generality_manifest.json")
for t in (1, 2, 3):
    ts = [r["slug"] for r in ok if r["tier"] == t]
    print(f"  tier {t}: {len(ts)}  {', '.join(ts)}")
