"""Probe what 周易 source text is actually obtainable, and in what quality."""
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "book-probe/0.1", "Accept": "application/vnd.github+json"}


def gh(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


print("=== 1. daizhigev20: locate 易经 files ===")
try:
    tree = gh("https://api.github.com/repos/garychowcmu/daizhigev20/git/trees/master")
    for t in tree.get("tree", []):
        print(f"   {t['type']:4} {t['path']}")
except Exception as e:
    print("   FAIL", type(e).__name__, str(e)[:100])

print("\n=== 2. search GitHub for dedicated 周易/易经 text repos ===")
for q in ["周易 易经 古籍", "kanripo", "chinese classics text corpus", "ctext 古籍 json"]:
    try:
        u = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q) + "&sort=stars&per_page=5"
        d = gh(u)
        print(f"  -- {q!r} (total {d['total_count']})")
        for it in d["items"]:
            print(f"     {it['full_name']:44} ★{it['stargazers_count']:<6} pushed={it['pushed_at'][:10]} lic={(it.get('license') or {}).get('spdx_id')}")
    except Exception as e:
        print(f"  -- {q!r} FAIL {type(e).__name__} {str(e)[:70]}")

print("\n=== 3. Kanripo: does the 周易 repo (KR1a0001) have real text? ===")
try:
    d = gh("https://api.github.com/repos/kanripo/KR1a0001/git/trees/master?recursive=1")
    for t in d.get("tree", [])[:25]:
        print(f"   {t['type']:4} {t.get('size','-'):>8} {t['path']}")
except Exception as e:
    print("   FAIL", type(e).__name__, str(e)[:100])
