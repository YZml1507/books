"""Fetch Kanripo repos as tarballs via codeload (raw.githubusercontent is blocked here).

Superseded by probes/fetch_kanripo_corpus.py (which writes the canonical data/raw/ with
manifest provenance). Kept as the original one-shot fetcher; note its OUT is a SCRATCH
dir under probes/ (single dirname), deliberately NOT the repo data/raw, so a re-run
cannot clobber the canonical corpus. R18a audit note.
"""
import io
import os
import tarfile
import urllib.request

UA = {"User-Agent": "book-probe/0.1"}
# scratch dir under probes/ — NOT the repo data/raw (see docstring)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")

REPOS = {
    "KR1a0001": "周易(正文)",
    "KR1a0006": "周易註 (王弼注)",
    "KR1a0007": "周易註疏 (王弼注+孔穎達疏)",
}


def fetch(repo):
    for branch in ("master", "main"):
        url = f"https://codeload.github.com/kanripo/{repo}/tar.gz/refs/heads/{branch}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(), branch
        except Exception as e:
            last = e
    raise last


os.makedirs(OUT, exist_ok=True)
for repo, label in REPOS.items():
    try:
        blob, branch = fetch(repo)
        dest = os.path.join(OUT, repo)
        os.makedirs(dest, exist_ok=True)
        n = 0
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile() or not m.name.endswith(".txt"):
                    continue
                fname = os.path.basename(m.name)
                data = tf.extractfile(m).read()
                with open(os.path.join(dest, fname), "wb") as f:
                    f.write(data)
                n += 1
        size = sum(os.path.getsize(os.path.join(dest, f)) for f in os.listdir(dest))
        print(f"  {repo} ({label}): {n} txt files, {size/1024:.0f} KB  [branch={branch}]")
    except Exception as e:
        print(f"  {repo} ({label}): FAIL {type(e).__name__} {str(e)[:110]}")
