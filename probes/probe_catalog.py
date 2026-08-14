"""Discover 術數/占卜 works available for ingest.

Tries several catalog endpoints through the local proxy and reports which ones
actually work, so book selection is based on what is reachable, not on guesses.
"""
import json
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


def get(url, timeout=30):
    """-> (status, text, headers). status None means transport failure."""
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, f"HTTPError: {e.reason}", dict(e.headers or {})
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", {}


print("=== 1. GitHub API rate limit (free call) ===")
st, body, _ = get("https://api.github.com/rate_limit")
if st == 200:
    d = json.loads(body)
    core = d["resources"]["core"]
    search = d["resources"]["search"]
    print(f"  core   {core['remaining']}/{core['limit']}")
    print(f"  search {search['remaining']}/{search['limit']}")
else:
    print(f"  status={st} {body[:200]}")

print("\n=== 2. kanripo org repo listing: naming + total size ===")
st, body, hdrs = get("https://api.github.com/orgs/kanripo/repos?per_page=100&page=1")
if st == 200:
    repos = json.loads(body)
    print(f"  got {len(repos)} repos on page 1")
    print(f"  Link: {hdrs.get('Link', '(none)')[:160]}")
    for r in repos[:6]:
        print(f"    {r['name']:16} desc={(r.get('description') or '')[:44]}")
else:
    print(f"  status={st} {body[:200]}")

print("\n=== 3. search API: 術數類 prefix KR3j ===")
st, body, _ = get("https://api.github.com/search/repositories?q=org%3Akanripo+KR3j+in%3Aname&per_page=20")
if st == 200:
    d = json.loads(body)
    print(f"  total_count={d.get('total_count')}")
    for r in d.get("items", [])[:20]:
        print(f"    {r['name']:16} {(r.get('description') or '')[:48]}")
else:
    print(f"  status={st} {body[:200]}")

print("\n=== 4. kanripo.org website catalog ===")
for url in (
    "https://www.kanripo.org/catalog/KR3j",
    "https://www.kanripo.org/catalog/",
):
    st, body, _ = get(url)
    print(f"  {url} -> status={st} len={len(body)}")
    if st == 200:
        print(f"    snippet: {body[:200].replace(chr(10), ' ')}")

print("\n=== 5. raw.githubusercontent via proxy (was blocked before) ===")
st, body, _ = get("https://raw.githubusercontent.com/kanripo/KR1a0001/master/KR1a0001_001.txt")
print(f"  status={st} len={len(body)}")
if st == 200:
    print(f"    snippet: {body[:120].replace(chr(10), ' ')}")

print("\n=== 6. archive.org search for 術數/占卜 texts ===")
q = "https://archive.org/advancedsearch.php?q=subject%3A%28%E8%A1%93%E6%95%B0+OR+%E5%8D%A0%E5%8D%9C%29&fl%5B%5D=identifier&fl%5B%5D=title&rows=8&output=json"
st, body, _ = get(q)
print(f"  status={st} len={len(body)}")
if st == 200:
    try:
        docs = json.loads(body)["response"]["docs"]
        print(f"  numFound docs returned: {len(docs)}")
        for d in docs:
            print(f"    {d.get('identifier','?'):34} {str(d.get('title',''))[:40]}")
    except Exception as e:
        print(f"  parse failed: {e} :: {body[:200]}")

print("\n=== 7. ctext catalog API (open per earlier probe) ===")
st, body, _ = get("https://api.ctext.org/gettexttitles")
print(f"  status={st} len={len(body)}")
if st == 200:
    print(f"    snippet: {body[:200]}")
