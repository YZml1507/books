"""Fetch actual 周易 text from Kanripo + daizhige and inspect real structure/quality."""
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "book-probe/0.1"}


def raw(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def gh(url):
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


print("=== Kanripo KR1a0001 (周易 with 注疏?) — first file verbatim ===")
try:
    t = raw("https://raw.githubusercontent.com/kanripo/KR1a0001/master/KR1a0001_001.txt")
    print(t[:1800])
    print(f"\n   [total {len(t)} chars]")
except Exception as e:
    print("FAIL", type(e).__name__, str(e)[:120])

print("\n\n=== what is KR1a0001? check the repo description / metadata ===")
try:
    d = gh("https://api.github.com/repos/kanripo/KR1a0001")
    print("   name:", d.get("name"), "| desc:", d.get("description"))
except Exception as e:
    print("   FAIL", str(e)[:100])

print("\n=== daizhige 易藏 listing ===")
try:
    d = gh("https://api.github.com/repos/garychowcmu/daizhigev20/contents/%E6%98%93%E8%97%8F")
    for it in d[:30]:
        print(f"   {it['type']:4} {it['name']}")
except Exception as e:
    print("   FAIL", type(e).__name__, str(e)[:120])
