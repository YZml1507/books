"""Fetch 周易 text via GitHub Contents API (base64) instead of raw.githubusercontent, which is blocked."""
import base64
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "book-probe/0.1", "Accept": "application/vnd.github+json"}
PROXY = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})
)


def gh(url, use_proxy=False):
    req = urllib.request.Request(url, headers=UA)
    opener = PROXY.open if use_proxy else urllib.request.urlopen
    with opener(req, timeout=45) as r:
        return json.load(r)


def content(repo, path, use_proxy=False):
    u = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(path)}"
    d = gh(u, use_proxy)
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


print("=== A. Kanripo KR1a0001_001.txt via Contents API (direct) ===")
try:
    t = content("kanripo/KR1a0001", "KR1a0001_001.txt")
    print(t[:1500])
    print(f"\n   [total {len(t)} chars]")
except Exception as e:
    print("   direct FAIL:", type(e).__name__, str(e)[:90])
    try:
        t = content("kanripo/KR1a0001", "KR1a0001_001.txt", use_proxy=True)
        print("   (via proxy)")
        print(t[:1500])
    except Exception as e2:
        print("   proxy FAIL too:", type(e2).__name__, str(e2)[:90])

print("\n\n=== B. Kanripo: is there a 注疏 (commentary) edition of 周易? ===")
for repo in ["kanripo/KR1a0002", "kanripo/KR1a0003", "kanripo/KR1a0004"]:
    try:
        d = gh(f"https://api.github.com/repos/{repo}")
        print(f"   {repo}: {d.get('description')}")
    except Exception as e:
        print(f"   {repo}: FAIL {str(e)[:60]}")

print("\n=== C. daizhige 易藏/易经 listing ===")
try:
    d = gh("https://api.github.com/repos/garychowcmu/daizhigev20/contents/" + urllib.parse.quote("易藏/易经"))
    print(f"   {len(d)} entries; first 25:")
    for it in d[:25]:
        print(f"   {it['type']:4} {it.get('size','-'):>9} {it['name']}")
except Exception as e:
    print("   FAIL", type(e).__name__, str(e)[:110])
