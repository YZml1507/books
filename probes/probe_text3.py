"""Assess the two 古籍 corpora head-to-head on the things that matter for citation."""
import base64
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "book-probe/0.1", "Accept": "application/vnd.github+json"}


def gh(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def content(repo, path):
    u = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    return base64.b64decode(gh(u)["content"]).decode("utf-8", "replace")


print("=== 1. How big is the Kanripo corpus? (org repo count) ===")
try:
    d = gh("https://api.github.com/orgs/kanripo")
    print(f"   public_repos = {d.get('public_repos')}  created={d.get('created_at','')[:10]}")
    print(f"   desc: {d.get('description')}")
except Exception as e:
    print("   FAIL", str(e)[:90])

print("\n=== 2. Do the 注疏 editions carry the same page-anchor format? (王弼注/孔穎達疏) ===")
# search kanripo repos mentioning 正義 (Kong Yingda's 疏) or 注
try:
    d = gh("https://api.github.com/search/repositories?q=" + urllib.parse.quote("org:kanripo 周易") + "&per_page=20")
    print(f"   matches: {d['total_count']}")
    for it in d["items"]:
        print(f"   {it['name']:14} {it.get('description')}")
except Exception as e:
    print("   FAIL", str(e)[:90])

print("\n=== 3. daizhige text quality: 周易.txt head, and does it have ANY structure? ===")
try:
    t = content("garychowcmu/daizhigev20", "易藏/易经/周易.txt")
    print(f"   length={len(t)}")
    print("   --- first 700 chars verbatim ---")
    print(t[:700])
    trad = len(re.findall(r"[個並東說學萬與"
                          r"]", t))
    print(f"\n   traditional-char sample hits: {trad}")
    print(f"   contains page markers? {'<pb:' in t}")
    print(f"   line count: {t.count(chr(10))}")
except Exception as e:
    print("   FAIL", type(e).__name__, str(e)[:110])

print("\n=== 4. 伊川易传 (程頤) + 原本周易本义 (朱熹) exist in daizhige? head of each ===")
for name in ["易藏/易经/伊川易传.txt", "易藏/易经/原本周易本义.txt"]:
    try:
        t = content("garychowcmu/daizhigev20", name)
        print(f"\n   --- {name} ({len(t)} chars) ---")
        print("   " + t[:320].replace("\n", "\n   "))
    except Exception as e:
        print(f"   {name}: FAIL {type(e).__name__} {str(e)[:80]}")
