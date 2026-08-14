"""Locate Legge's Yî King on Gutenberg. Earlier regex missed it: the title uses
'Yî' (î = U+00EE), and gutendex search does not fold diacritics.

Strategy: enumerate every work by 'Legge, James' via the author filter rather
than guessing title spellings.
"""
import json
import urllib.parse
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-probe/0.1")]


def j(url):
    with opener.open(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


seen = {}
url = "https://gutendex.com/books?search=" + urllib.parse.quote("legge")
page = 1
while url and page <= 3:
    d = j(url)
    for b in d.get("results", []):
        if any("Legge, James" in a["name"] for a in b.get("authors", [])):
            seen[b["id"]] = b
    url = d.get("next")
    page += 1

print(f"=== works credited to Legge, James: {len(seen)} ===")
for b in sorted(seen.values(), key=lambda x: x["id"]):
    fmts = [k.split("/")[-1][:18] for k in b["formats"] if "image" not in k]
    print(f"  #{b['id']:>6}  {b['title'][:66]}")
    print(f"          langs={b.get('languages')}  fmts={len(fmts)}")
