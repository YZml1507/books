"""Fetch five external 周易/占卜 repos to use as INDEPENDENT WITNESSES, not as code.

Our 64-hexagram mappings (symbol -> number, trigram pair -> line polarity, 卦 name, 爻位
labels) are all DERIVED from the corpus rather than typed in. That is good, but it means a
single systematic error in derivation would be invisible — every downstream check would
inherit it. An external, independently-produced 卦 table is the cheapest possible witness.

Same discipline as scripts/check_quality.py (LESSONS L-03): a witness that agrees tells us
little; a witness that DISAGREES localises a defect in one of the two. Neither side is
assumed correct in advance.

Explicitly recorded per repo: licence file present or not. Our corpus manifest does this
per work already, and 25 Kanripo repos had none — do not assume permissive.
"""
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
opener.addheaders = [("User-Agent", "book-research-fetch/0.3")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "external")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(DEST, exist_ok=True)

REPOS = [
    ("lyyxqg-lyy", "suanle-me"),
    ("starloom", "starloom"),
    ("dreamhunter2333", "chatgpt-tarot-divination"),
    ("sunls2", "zhouyi"),
    ("Ovilia", "biangua"),
]
LICENCE_NAMES = ("LICENSE", "LICENCE", "LICENSE.md", "LICENSE.txt", "COPYING",
                 "LICENSE-MIT", "LICENSE.MIT")


def get(url, timeout=180):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        print(f"    transport: {type(e).__name__}: {e}")
        return None, b""


records = []
for owner, repo in REPOS:
    print(f"\n=== {owner}/{repo} ===")
    blob = None
    used = None
    for branch in ("main", "master"):
        st, body = get(f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}")
        print(f"  branch {branch}: status={st} bytes={len(body):,}")
        if st == 200 and body:
            blob, used = body, branch
            break
    if not blob:
        records.append({"repo": f"{owner}/{repo}", "fetched": False})
        continue

    d = os.path.join(DEST, repo)
    os.makedirs(d, exist_ok=True)
    zpath = os.path.join(d, f"{repo}.zip")
    with open(zpath, "wb") as f:
        f.write(blob)
    sha = hashlib.sha256(blob).hexdigest()

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        z.extractall(d)
    # strip the single top-level dir GitHub adds
    top = names[0].split("/")[0] if names else ""
    rel = [n[len(top) + 1:] for n in names if len(n) > len(top) + 1]
    licence = [n for n in rel if os.path.basename(n).upper() in
               {x.upper() for x in LICENCE_NAMES}]
    # Which files could plausibly carry a 卦 table?
    interesting = [n for n in rel if not n.endswith("/") and any(
        k in n.lower() for k in ("gua", "卦", "hexagram", "yijing", "iching", "zhouyi",
                                 "divination", "data", "json", "yml", "yaml", "csv"))]
    print(f"  extracted {len(rel)} entries, branch={used}, sha256={sha[:12]}…")
    print(f"  LICENCE file: {licence or 'NONE'}")
    print(f"  candidate data files ({len(interesting)}):")
    for n in sorted(interesting, key=lambda x: -os.path.getsize(os.path.join(d, top, x))
                    if os.path.exists(os.path.join(d, top, x)) else 0)[:14]:
        p = os.path.join(d, top, n)
        sz = os.path.getsize(p) if os.path.exists(p) else 0
        print(f"    {sz:>9,}  {n}")

    records.append({
        "repo": f"{owner}/{repo}", "fetched": True, "branch": used,
        "zip_sha256": sha, "zip_bytes": len(blob), "top_dir": top,
        "n_entries": len(rel), "licence_files": licence,
        "licence_status": "present" if licence else "none-stated",
        "candidate_data_files": interesting[:60],
        "source_url": f"https://github.com/{owner}/{repo}",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    time.sleep(0.4)

with open(os.path.join(CAT, "external_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=1)
ok = [r for r in records if r.get("fetched")]
print(f"\n{len(ok)}/{len(REPOS)} fetched -> data/catalog/external_manifest.json")
print(f"licence present: {sum(1 for r in ok if r['licence_files'])}/{len(ok)}")
