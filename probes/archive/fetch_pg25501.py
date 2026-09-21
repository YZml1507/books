"""Fetch Gutenberg #25501 易經 — an INDEPENDENT digitisation of the text we already
hold as Kanripo KR1a0001.

Purpose: cross-source validation. If two unrelated digitisations of "the same"
work disagree, the system must be able to say so rather than silently pick one.
Also exercises markitdown's EPUB converter on real CJK content.
"""
import hashlib
import json
import os
import time
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "raw_ext", "gutenberg", "25501")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(DEST, exist_ok=True)
os.makedirs(CAT, exist_ok=True)

with opener.open("https://gutendex.com/books/25501", timeout=60) as r:
    meta = json.loads(r.read().decode("utf-8"))

print(f"title   : {meta['title']}")
print(f"langs   : {meta.get('languages')}")
print(f"rights  : {meta.get('copyright')}")

saved = {}
for mime, url in meta["formats"].items():
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
    with opener.open(url, timeout=120) as r:
        blob = r.read()
    path = os.path.join(DEST, f"pg25501.{ext}")
    with open(path, "wb") as f:
        f.write(blob)
    saved[ext] = {
        "path": os.path.relpath(path, ROOT),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": url,
    }
    print(f"saved {ext:4} {len(blob):>9,} bytes")

rec = {
    "gutenberg_id": 25501,
    "title": meta["title"],
    "languages": meta.get("languages"),
    "rights": meta.get("copyright"),
    "role": "independent digitisation of the same work as KR1a0001",
    "files": saved,
    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
with open(os.path.join(CAT, "gutenberg_manifest.json"), "w", encoding="utf-8") as f:
    json.dump([rec], f, ensure_ascii=False, indent=1)
print("manifest -> data/catalog/gutenberg_manifest.json")
