"""Fetch a public-domain ENGLISH translation of 周易 from Project Gutenberg.

Architectural purpose, not decoration: this is the SAME work as KR1a0001 in a
different language by a named translator (Legge, 1882). It is the only material
that lets us test cross-lingual alignment and translator attribution, and it
gives markitdown a real EPUB/HTML to parse.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "raw_ext", "gutenberg")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(DEST, exist_ok=True)
os.makedirs(CAT, exist_ok=True)

WANT = re.compile(r"yi king|y[iî] king|book of changes|i ching", re.I)


def get(url, timeout=60):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        print(f"    transport: {type(e).__name__}: {e}")
        return None, b""


print("=== searching gutendex ===")
found = {}
for q in ("yi king", "book of changes", "sacred books of china"):
    st, body = get(f"https://gutendex.com/books?search={urllib.parse.quote(q)}")
    print(f"  q={q!r} status={st}")
    if st != 200:
        continue
    for b in json.loads(body.decode("utf-8")).get("results", []):
        if WANT.search(b.get("title", "")):
            found[b["id"]] = b
    time.sleep(1)

if not found:
    raise SystemExit("no candidates found; gutendex may be unreachable")

print(f"\n=== {len(found)} candidate(s) ===")
for b in found.values():
    authors = ", ".join(a["name"] for a in b.get("authors", []))
    print(f"  #{b['id']:6} {b['title'][:60]}")
    print(f"          authors: {authors[:70]}")
    print(f"          formats: {sorted(k for k in b['formats'] if 'image' not in k)[:6]}")

records = []
for b in found.values():
    d = os.path.join(DEST, str(b["id"]))
    os.makedirs(d, exist_ok=True)
    saved = {}
    for mime, url in b["formats"].items():
        if "epub" in mime:
            ext = "epub"
        elif mime.startswith("text/html"):
            ext = "html"
        elif mime.startswith("text/plain"):
            ext = "txt"
        else:
            continue
        if ext in saved or url.endswith(".zip"):
            continue
        st, blob = get(url)
        if st != 200 or not blob:
            print(f"  skip {ext} for #{b['id']} (status={st})")
            continue
        path = os.path.join(d, f"pg{b['id']}.{ext}")
        with open(path, "wb") as f:
            f.write(blob)
        saved[ext] = {
            "path": os.path.relpath(path, ROOT),
            "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "url": url,
        }
        print(f"  saved #{b['id']} {ext:4} {len(blob):>9,} bytes")
    records.append({
        "gutenberg_id": b["id"],
        "title": b.get("title", ""),
        "authors": [a["name"] for a in b.get("authors", [])],
        "translators": [a["name"] for a in b.get("translators", [])],
        "languages": b.get("languages", []),
        "rights": b.get("copyright"),
        "files": saved,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })

with open(os.path.join(CAT, "gutenberg_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
print(f"\nmanifest -> data/catalog/gutenberg_manifest.json ({len(records)} works)")
