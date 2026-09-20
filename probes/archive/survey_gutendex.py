"""Survey gutendex for structurally-diverse non-CJK candidates.

We do NOT pick books by reputation. Each candidate is fetched as plain text and
probed for the STRUCTURAL feature we actually want to test (canonical reference
numbers, footnote markers, tables, equations). A book that lacks the feature in
its digitisation is useless to us however famous it is.
"""
import json
import urllib.parse
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

QUERIES = [
    "Republic Plato",
    "Nicomachean Ethics Aristotle",
    "Ethics Spinoza",
    "Summa Theologica",
    "Iliad Homer",
    "Odyssey Homer",
    "Moby Dick Melville",
    "Decline and Fall Roman Empire Gibbon",
    "History Herodotus",
    "Elements Euclid",
    "Relativity Einstein",
    "Origin of Species Darwin",
]


def get(url):
    with opener.open(url, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


for q in QUERIES:
    url = "https://gutendex.com/books?search=" + urllib.parse.quote(q)
    try:
        data = get(url)
    except Exception as e:
        print(f"!! {q}: {type(e).__name__}: {e}")
        continue
    print(f"\n=== {q}  ({data['count']} hits) ===")
    for b in data["results"][:8]:
        fmts = sorted(
            {
                ("epub" if "epub" in m else "html" if m.startswith("text/html")
                 else "txt" if m.startswith("text/plain") else "")
                for m in b["formats"]
            }
            - {""}
        )
        auth = "; ".join(a["name"] for a in b["authors"])[:44]
        trs = "; ".join(
            a["name"] for a in b.get("translators", [])
        )[:34]
        print(f"  {b['id']:>6} {b['title'][:52]:52} | {auth:44} | tr={trs:34} "
              f"| {b.get('languages')} {','.join(fmts)} dl={b.get('download_count')}")
