"""Source adapters (founding brief §10): fetch a work into data/raw, legally and additively.

The first adapter is Kanripo (the corpus's main source): GitHub zips of per-work
repos, plain `KR*_*.txt` files with #+TITLE / #+PROPERTY headers. The historical
fetcher (probes/fetch_kanripo_corpus.py) REWRITES corpus_manifest.json from a
hardcoded list — fine for the original bulk fetch, wrong for adding one book
later (it would drop everything else). This module is additive: read manifest,
upsert the work, keep the rest.

Rules inherited from the corpus discipline:
  * zip-slip guard: only files matching `{kid}(_\\w+)?\\.txt` are extracted,
    and licence files are detected but nothing else touches disk.
  * Kanripo repos carry no licence file in general (recorded per work, D-055
    lineage): `licence_file_in_repo` is recorded, licence assumed public-domain
    editions — provenance (url + sha256 + fetched_at) is always kept.
  * proxy: default http://127.0.0.1:7897 (site rule mode), override with
    GUJI_PROXY (or empty string for direct).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

DEFAULT_PROXY = "http://127.0.0.1:7897"
MANIFEST = os.path.join("data", "catalog", "corpus_manifest.json")
RAW = os.path.join("data", "raw")


def _opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("GUJI_PROXY", DEFAULT_PROXY)
    handlers = ([urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy})] if proxy
        else [urllib.request.ProxyHandler({})])
    op = urllib.request.build_opener(*handlers)
    op.addheaders = [("User-Agent", "book-research-fetch/0.2")]
    return op


def fetch_zip(kid: str, opener: urllib.request.OpenerDirector | None = None) -> tuple[str, bytes]:
    """Download the Kanripo work zip; returns (url, blob)."""
    opener = opener or _opener()
    last = ""
    for branch in ("master", "main"):
        url = f"https://codeload.github.com/kanripo/{kid}/zip/refs/heads/{branch}"
        for attempt in range(3):
            try:
                with opener.open(url, timeout=90) as r:
                    return url, r.read()
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                break
            except Exception as e:  # noqa: BLE001 — network noise of all kinds
                last = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{kid}: {last}")


def extract(kid: str, blob: bytes, dest_dir: str = RAW) -> dict:
    """Extract the work's txt files into dest_dir/kid and read its metadata.

    Zip-slip proof by construction: the name filter admits only `{kid}(_\\w+)?\\.txt`,
    so no path component from the archive is ever used.
    """
    dest = os.path.join(dest_dir, kid)
    os.makedirs(dest, exist_ok=True)
    n_files = n_chars = 0
    title = edition = ""
    juan: list[str] = []
    has_licence = False
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename)
            if re.fullmatch(r"(LICEN[CS]E|COPYING)(\.\w+)?", base, re.I):
                has_licence = True
            if not re.fullmatch(rf"{kid}(_\w+)?\.txt", base):
                continue
            text = z.read(info).decode("utf-8", "replace")
            with open(os.path.join(dest, base), "w", encoding="utf-8",
                      newline="\n") as f:
                f.write(text)
            n_files += 1
            n_chars += len(text)
            if not title:
                m = re.search(r"^#\+TITLE: (.+)$", text, re.M)
                title = m.group(1).strip() if m else ""
            if not edition:
                m = re.search(r"^#\+PROPERTY: BASEEDITION (\S+)", text, re.M)
                edition = m.group(1).strip() if m else ""
            m = re.search(r"^#\+PROPERTY: JUAN (.+)$", text, re.M)
            if m:
                juan.append(m.group(1).strip())
    if not n_files:
        raise RuntimeError(f"{kid}: zip contained no {kid}*.txt")
    return {"n_files": n_files, "n_chars": n_chars, "title": title,
            "edition": edition, "juan_sample": juan[:3],
            "licence_file_in_repo": has_licence}


def add_work(kid: str, genre: str, rationale: str,
             manifest_path: str = MANIFEST, raw_dir: str = RAW) -> dict:
    """Fetch + extract + upsert into the manifest (additive; other works kept)."""
    url, blob = fetch_zip(kid)
    meta = extract(kid, blob, raw_dir)
    entry = {
        "id": kid, "title": meta["title"], "genre": genre, "rationale": rationale,
        "edition": meta["edition"], "n_files": meta["n_files"],
        "n_chars": meta["n_chars"], "juan_sample": meta["juan_sample"],
        "source_url": url, "zip_sha256": hashlib.sha256(blob).hexdigest(),
        "licence_file_in_repo": meta["licence_file_in_repo"],
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    data = {"works": [], "errors": []}
    if os.path.exists(manifest_path):
        data = json.load(open(manifest_path, encoding="utf-8"))
    works = [w for w in data.get("works", []) if w.get("id") != kid]
    works.append(entry)
    works.sort(key=lambda w: (w.get("genre", ""), w.get("id", "")))
    data["works"] = works
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return entry


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 4 or sys.argv[1] != "add":
        print("usage: python -m guji.sources add KR5c0057 道家 老子——跨书思想比較語料（願景§17.3）")
        sys.exit(2)
    e = add_work(sys.argv[2], sys.argv[3], sys.argv[4])
    print(f"added {e['id']} 《{e['title']}》 genre={e['genre']} "
          f"{e['n_files']} files {e['n_chars']:,} chars "
          f"lic={'Y' if e['licence_file_in_repo'] else 'n'}")
