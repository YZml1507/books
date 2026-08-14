"""Find the right Gutenberg id for Legge's 易經 translation.

The earlier title regex matched nothing, so inspect what the catalogue actually
returns instead of guessing again.
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


for q in ("yi king", "i ching", "changes", "legge", "confucianism"):
    try:
        d = j(f"https://gutendex.com/books?search={urllib.parse.quote(q)}")
    except Exception as e:
        print(f"q={q!r} FAILED {type(e).__name__}: {e}")
        continue
    print(f"\n=== q={q!r} count={d.get('count')} ===")
    for b in d.get("results", [])[:8]:
        au = "; ".join(a["name"] for a in b.get("authors", []))
        print(f"  #{b['id']:>6}  {b['title'][:64]}")
        print(f"          {au[:64]}  langs={b.get('languages')}")

print("\n=== direct probe of likely ids ===")
for bid in (16019, 16020, 15250, 25501):
    try:
        b = j(f"https://gutendex.com/books/{bid}")
        au = "; ".join(a["name"] for a in b.get("authors", []))
        fmts = sorted(k for k in b["formats"] if "image" not in k)
        print(f"  #{bid}: {b['title'][:60]}")
        print(f"        {au[:60]}")
        print(f"        formats: {fmts[:5]}")
    except Exception as e:
        print(f"  #{bid}: {type(e).__name__} {e}")
