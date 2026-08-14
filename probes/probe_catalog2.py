"""Locate the Kanripo class prefix for 術數類 and build a divination candidate list.

Core API is rate-limited to 0, but the search API works and raw.githubusercontent
now succeeds through the proxy. Results are cached to data/catalog/ so this need
not be re-run.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [
    ("User-Agent", "book-research-probe/0.1"),
    ("Accept", "application/vnd.github+json"),
]
OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "catalog"
)
os.makedirs(OUT, exist_ok=True)

# 四庫 子部 subdivisions we care about, plus 經部易類
PREFIXES = ["KR1a", "KR3f", "KR3g", "KR3h"]

DIVINATION = "占卜筮卦命相宅墓葬星曆讖緯易林靈神術數風水堪輿子平三命紫微遁甲六壬太乙演禽龜兆陰陽五行"


def get(url, timeout=30):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, f"HTTPError: {e.reason}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def search_prefix(prefix, max_pages=4):
    cache = os.path.join(OUT, f"kanripo_{prefix}.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    out, total = [], None
    for page in range(1, max_pages + 1):
        url = (
            "https://api.github.com/search/repositories?"
            f"q=org%3Akanripo+{prefix}+in%3Aname&per_page=100&page={page}"
        )
        st, body = get(url)
        if st != 200:
            print(f"    {prefix} page{page}: status={st} {body[:110]}")
            break
        d = json.loads(body)
        total = d.get("total_count", 0)
        items = [
            {"name": r["name"], "title": (r.get("description") or "").strip()}
            for r in d.get("items", [])
            if re.fullmatch(rf"{prefix}\d+", r["name"])
        ]
        out.extend(items)
        if len(d.get("items", [])) < 100:
            break
        time.sleep(7)  # search API: 10 req/min
    print(f"    {prefix}: fetched {len(out)} (reported total_count={total})")
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


print("=== identifying class prefixes by sampling titles ===")
catalog = {}
for p in PREFIXES:
    catalog[p] = search_prefix(p)
    sample = "、".join(x["title"] for x in catalog[p][:8])
    print(f"  {p}  n={len(catalog[p]):4}  sample: {sample[:96]}")
    time.sleep(7)

print("\n=== divination-relevant candidates ===")
for p, items in catalog.items():
    hits = [x for x in items if any(c in x["title"] for c in DIVINATION)]
    print(f"\n--- {p}: {len(hits)}/{len(items)} titles look divination-related ---")
    for x in sorted(hits, key=lambda y: y["name"])[:70]:
        print(f"  {x['name']:12} {x['title']}")

allitems = [x for v in catalog.values() for x in v]
with open(os.path.join(OUT, "kanripo_merged.json"), "w", encoding="utf-8") as f:
    json.dump(allitems, f, ensure_ascii=False, indent=1)
print(f"\ncached {len(allitems)} entries -> data/catalog/")
