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


def add_local_work(wid: str, genre: str, rationale: str, txt_dir: str,
                   manifest_path: str = MANIFEST, raw_dir: str = RAW) -> dict:
    """Import a LOCAL directory of utf-8 txt files as a new work (R31b, 愿景 §10/§18).

    The local-file counterpart of add_work: zero network, zero new dependency —
    the user's own public-domain txt corpus can enter the system without waiting
    for a Kanripo repo. Same additive manifest semantics (other works kept).

    Rules:
      * only `{wid}(_\\w+)?\\.txt` files are imported (same name filter as the
        zip extractor — no stray files reach data/raw);
      * utf-8 with 'replace' — never a hard decode failure on one bad file;
      * title/edition read from `#+TITLE:` / `#+PROPERTY: BASEEDITION` headers
        when present (same convention as Kanripo files), else left blank;
      * files are COPIED (source directory untouched).
    """
    src = os.path.abspath(txt_dir)
    if not os.path.isdir(src):
        raise RuntimeError(f"{wid}: txt_dir not found: {txt_dir}")
    names = sorted(n for n in os.listdir(src)
                   if re.fullmatch(rf"{wid}(_\w+)?\.txt", n))
    if not names:
        raise RuntimeError(f"{wid}: no {wid}*.txt files in {txt_dir}")
    dest = os.path.join(raw_dir, wid)
    os.makedirs(dest, exist_ok=True)
    n_files = n_chars = 0
    title = edition = ""
    for n in names:
        with open(os.path.join(src, n), encoding="utf-8", errors="replace") as f:
            text = f.read()
        with open(os.path.join(dest, n), "w", encoding="utf-8",
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
    entry = {
        "id": wid, "title": title, "genre": genre, "rationale": rationale,
        "edition": edition, "n_files": n_files, "n_chars": n_chars,
        "source": "local", "source_dir": src,
        "licence_file_in_repo": False,
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    data = {"works": [], "errors": []}
    if os.path.exists(manifest_path):
        data = json.load(open(manifest_path, encoding="utf-8"))
    works = [w for w in data.get("works", []) if w.get("id") != wid]
    works.append(entry)
    works.sort(key=lambda w: (w.get("genre", ""), w.get("id", "")))
    data["works"] = works
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return entry


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        # R31b self-test: import a temp local txt dir into a temp raw+manifest,
        # assert additive semantics (pre-existing work kept) + name filter.
        import tempfile
        import shutil

        tmp = tempfile.mkdtemp(prefix="guji_sources_")
        try:
            src = os.path.join(tmp, "src")
            raw = os.path.join(tmp, "raw")
            man = os.path.join(tmp, "corpus_manifest.json")
            os.makedirs(src)
            with open(os.path.join(src, "T1a0001_001.txt"), "w",
                      encoding="utf-8") as f:
                f.write("#+TITLE: 测试书\n#+PROPERTY: BASEEDITION T1\n正文第一段。\n")
            with open(os.path.join(src, "T1a0001_002.txt"), "w",
                      encoding="utf-8") as f:
                f.write("正文第二段。\n")
            with open(os.path.join(src, "notes.md"), "w", encoding="utf-8") as f:
                f.write("不应被导入的非 txt 文件\n")
            # pre-existing manifest with an unrelated work — must survive
            with open(man, "w", encoding="utf-8") as f:
                json.dump({"works": [{"id": "KEEPME", "genre": "存"}],
                           "errors": []}, f, ensure_ascii=False)
            e = add_local_work("T1a0001", "测试", "本地自测", src,
                               manifest_path=man, raw_dir=raw)
            assert e["n_files"] == 2 and e["title"] == "测试书" \
                and e["edition"] == "T1", e
            assert os.path.exists(os.path.join(raw, "T1a0001", "T1a0001_001.txt"))
            assert not os.path.exists(os.path.join(raw, "T1a0001", "notes.md")), \
                "non-txt file must not be imported"
            data = json.load(open(man, encoding="utf-8"))
            ids = [w["id"] for w in data["works"]]
            assert "KEEPME" in ids and "T1a0001" in ids, \
                "additive upsert must keep the pre-existing work"
            # re-importing the same id must REPLACE, not duplicate
            e2 = add_local_work("T1a0001", "测试", "重新导入", src,
                                manifest_path=man, raw_dir=raw)
            assert e2["id"] == "T1a0001"
            ids2 = [w["id"] for w in
                    json.load(open(man, encoding="utf-8"))["works"]]
            assert ids2.count("T1a0001") == 1, \
                "re-import must replace the entry, not duplicate it"
            try:
                add_local_work("NOPE", "测试", "x", src,
                               manifest_path=man, raw_dir=raw)
                raise AssertionError("missing files must raise")
            except RuntimeError:
                pass
            print(f"[selftest] add_local_work OK: {e['n_files']} files, "
                  f"manifest ids={ids}")
            print("sources self-test PASS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        raise SystemExit(0)
    if len(sys.argv) < 5 or sys.argv[1] != "add_local":
        print("usage: python -m guji.sources add_local KRx1234 道家 理由 D:\\path\\to\\txt")
        sys.exit(2)
    e = add_local_work(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    print(f"added {e['id']} 《{e['title']}》 genre={e['genre']} "
          f"{e['n_files']} files {e['n_chars']:,} chars (local, then run build_index)")
