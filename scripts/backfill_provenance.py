"""Backfill provenance for the three works ingested before the manifest pipeline existed.

They are not incidental: KR1a0001 is the BASE TEXT from which every gold 爻辭 is derived, and
KR1a0006/KR1a0007 are the edition pair the quality gate diffs. So the foundation of every
alignment number in this project had no recorded sha256, source URL, or fetch time, and could
not be re-fetched or licence-audited from the record.

This does more than fill fields: it re-fetches upstream and compares the on-disk text against
it. If they differ, the gold set was derived from something other than what the source now
holds, and every downstream number needs re-examination. That check is the real point.
"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
opener.addheaders = [("User-Agent", "book-research-fetch/0.4")]

TARGETS = {
    "KR1a0001": ("周易正文", "易類", "周易(正文) — 底本，gold set 来源"),
    "KR1a0006": ("周易註", "易類", "王弼註"),
    "KR1a0007": ("周易註疏", "易類", "王弼註 + 孔穎達疏"),
}
LICENCE_NAMES = {"LICENSE", "LICENCE", "LICENSE.MD", "LICENSE.TXT", "COPYING"}


def get(url, timeout=180):
    try:
        with opener.open(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        print(f"    transport: {type(e).__name__}: {e}")
        return None, b""


def digest_dir(d):
    """sha256 over the work's .txt files, content only, order-stable."""
    h = hashlib.sha256()
    for f in sorted(os.listdir(d)):
        if f.endswith(".txt"):
            h.update(open(os.path.join(d, f), "rb").read())
    return h.hexdigest()


man_path = os.path.join(CAT, "corpus_manifest.json")
man = json.load(open(man_path, encoding="utf-8"))
have = {w["id"] for w in man["works"]}
added = []

for wid, (title, genre, note) in TARGETS.items():
    print(f"\n=== {wid} {title} ===")
    local_dir = os.path.join(RAW, wid)
    if not os.path.isdir(local_dir):
        print("  no local dir — skipping")
        continue
    local_files = sorted(f for f in os.listdir(local_dir) if f.endswith(".txt"))
    local_sha = digest_dir(local_dir)
    print(f"  on disk: {len(local_files)} txt files, content sha256={local_sha[:16]}…")

    blob, branch = None, None
    for b in ("master", "main"):
        st, body = get(f"https://codeload.github.com/kanripo/{wid}/zip/refs/heads/{b}")
        print(f"  upstream branch {b}: status={st} bytes={len(body):,}")
        if st == 200 and body:
            blob, branch = body, b
            break
    if not blob:
        print("  UPSTREAM UNREACHABLE — recording local digest only, marked unverified")
        added.append({
            "id": wid, "title": title, "genre": genre, "rationale": note,
            "n_files": len(local_files), "local_content_sha256": local_sha,
            "source_url": f"https://github.com/kanripo/{wid}",
            "zip_sha256": None, "licence_file_in_repo": None,
            "upstream_verified": False,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "provenance_note": "backfilled; upstream unreachable at backfill time",
        })
        continue

    zip_sha = hashlib.sha256(blob).hexdigest()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        top = names[0].split("/")[0]
        up_txt = {}
        for n in names:
            if n.endswith(".txt"):
                up_txt[os.path.basename(n)] = z.read(n)
        lic = [n for n in names
               if os.path.basename(n).upper() in LICENCE_NAMES]
    h = hashlib.sha256()
    for f in sorted(up_txt):
        h.update(up_txt[f])
    up_sha = h.hexdigest()

    same_names = set(up_txt) == set(local_files)
    same_bytes = up_sha == local_sha
    print(f"  upstream: {len(up_txt)} txt files, content sha256={up_sha[:16]}…")
    print(f"  filenames match: {same_names}    CONTENT MATCH: {same_bytes}")
    print(f"  LICENCE in repo: {lic or 'NONE'}")
    if not same_bytes:
        diff = [f for f in sorted(set(up_txt) | set(local_files))
                if up_txt.get(f) != (open(os.path.join(local_dir, f), "rb").read()
                                     if f in local_files else None)]
        print(f"  !! DIFFERING FILES ({len(diff)}): {diff[:8]}")
        print("  !! the gold set was derived from text that differs from upstream —")
        print("  !! every alignment number needs re-examination")

    added.append({
        "id": wid, "title": title, "genre": genre, "rationale": note,
        "edition": None, "n_files": len(local_files),
        "n_chars": sum(len(open(os.path.join(local_dir, f), encoding="utf-8").read())
                       for f in local_files),
        "source_url": f"https://codeload.github.com/kanripo/{wid}/zip/refs/heads/{branch}",
        "zip_sha256": zip_sha,
        "local_content_sha256": local_sha,
        "upstream_content_sha256": up_sha,
        "upstream_verified": same_bytes,
        "licence_file_in_repo": bool(lic),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provenance_note": "backfilled: ingested before the manifest pipeline existed",
    })

new = [a for a in added if a["id"] not in have]
man["works"].extend(new)
man["works"].sort(key=lambda w: w["id"])
json.dump(man, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\nmanifest: {len(have)} -> {len(man['works'])} works")
print(f"backfilled: {[a['id'] for a in new]}")
print(f"upstream-verified: {[a['id'] for a in added if a.get('upstream_verified')]}")
print("\nRebuild the index so `work` rows pick up the new provenance:")
print("  .\\.venv\\Scripts\\python.exe scripts\\build_index.py")
