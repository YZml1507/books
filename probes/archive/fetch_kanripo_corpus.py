"""Fetch a divination-focused Kanripo corpus via codeload, with provenance.

Selection is deliberate, not convenient: it spans the distinct 術數 sub-genres
(卜筮 / 三式 / 命理 / 相術 / 堪輿 / 占候 / 擬易) plus the 易類 works needed to test
multi-commentator and multi-EDITION handling on one base text.

Records sha256, source URL, fetch time and licence-file presence per work so the
ingest layer never has to guess where a text came from.
"""
import concurrent.futures as cf
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(RAW, exist_ok=True)
os.makedirs(CAT, exist_ok=True)

# (KR id, genre tag, why this one)
WORKS = [
    # --- 卜筮: casting-based divination ---
    ("KR3g0029", "卜筮", "焦氏易林 漢 — 4096 林辭, structurally unlike any commentary"),
    ("KR3g0030", "卜筮", "京氏易傳 漢 — 納甲 system, basis of later 卦氣 divination"),
    ("KR3g0028", "卜筮", "靈棋經 漢 — lot-casting manual"),
    ("KR3g0032", "卜筮", "卜法詳考 清 — survey of divination procedures"),
    # --- 三式: the three canonical mantic systems ---
    ("KR3g0031", "三式", "六壬大全 清 — 六壬"),
    ("KR3g0047", "三式", "太乙金鏡式經 唐 — 太乙"),
    ("KR3g0048", "三式", "遁甲演義 明 — 奇門遁甲"),
    # --- 命理: fate calculation (算命) ---
    ("KR3g0042", "命理", "三命通會 明 — the major 八字 compendium"),
    ("KR3g0033", "命理", "李虛中命書 — early 命理, short"),
    ("KR3g0041", "命理", "星學大成 明 — 星命 compendium"),
    ("KR3g0035", "命理", "星命溯源"),
    # --- 相術: physiognomy ---
    ("KR3g0045", "相術", "太清神鑑 後周 — 相法"),
    ("KR3g0044", "相術", "玉管照神局 南唐"),
    # --- 堪輿: siting of dwellings and graves ---
    ("KR3g0020", "堪輿", "葬書 晉 郭璞 — root text of 風水"),
    ("KR3g0019", "堪輿", "宅經 — 陽宅"),
    ("KR3g0025", "堪輿", "靈城精義 南唐"),
    # --- 占候: astral / omen reading ---
    ("KR3g0018", "占候", "唐開元占經 唐 — large astral omen classic"),
    ("KR3g0050", "占候", "御定星歷考原 清"),
    # --- 擬易: alternative systems modelled on 易 ---
    ("KR3g0001", "擬易", "太玄經 漢 揚雄 — 81 首 instead of 64 卦"),
    ("KR3g0015", "擬易", "易象圖說 元"),
    # --- 易類: needed for multi-commentator and multi-edition tests ---
    ("KR1a0031", "易類", "原本周易本義 朱熹 — closes the 王弼-vs-朱熹 comparison gap"),
    ("KR1a0032", "易類", "別本周易本義 朱熹 — SAME work, different edition"),
    ("KR1a0016", "易類", "伊川易傳 程頤 — third commentator on the same base text"),
    ("KR1a0030", "易類", "周易古占法 宋 程迥 — 占法 applied to 周易"),
    ("KR1a0003", "易類", "周易鄭康成註 漢 鄭玄 — earliest layer"),
]


def fetch_zip(kid):
    last = None
    for branch in ("master", "main"):
        url = f"https://codeload.github.com/kanripo/{kid}/zip/refs/heads/{branch}"
        for attempt in range(3):
            try:
                with opener.open(url, timeout=90) as r:
                    return url, r.read()
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{kid}: {last}")


def ingest(kid, genre, why):
    url, blob = fetch_zip(kid)
    sha = hashlib.sha256(blob).hexdigest()
    dest = os.path.join(RAW, kid)
    os.makedirs(dest, exist_ok=True)

    n_files = n_chars = 0
    title = edition = ""
    juan = []
    has_licence = False
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            base = os.path.basename(info.filename)
            if re.fullmatch(r"(LICEN[CS]E|COPYING)(\.\w+)?", base, re.I):
                has_licence = True
            if not re.fullmatch(rf"{kid}(_\w+)?\.txt", base):
                continue
            text = z.read(info).decode("utf-8", "replace")
            with open(os.path.join(dest, base), "w", encoding="utf-8", newline="\n") as f:
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
    return {
        "id": kid, "title": title, "genre": genre, "rationale": why,
        "edition": edition, "n_files": n_files, "n_chars": n_chars,
        "juan_sample": juan[:3], "source_url": url, "zip_sha256": sha,
        "licence_file_in_repo": has_licence,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


results, errors = [], []
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    futs = {ex.submit(ingest, k, g, w): k for k, g, w in WORKS}
    for fu in cf.as_completed(futs):
        kid = futs[fu]
        try:
            results.append(fu.result())
            print(f"  ok   {kid}")
        except Exception as e:
            errors.append((kid, str(e)))
            print(f"  FAIL {kid}: {e}")

results.sort(key=lambda r: (r["genre"], r["id"]))
print(f"\n{'id':10} {'genre':6} {'title':26} {'ed':7} {'files':>5} {'chars':>8} lic")
print("-" * 78)
for r in results:
    print(f"{r['id']:10} {r['genre']:6} {r['title'][:26]:26} {r['edition'][:7]:7} "
          f"{r['n_files']:5} {r['n_chars']:8} {'Y' if r['licence_file_in_repo'] else 'n'}")
print("-" * 78)
print(f"{len(results)} works, {sum(r['n_chars'] for r in results):,} chars, {len(errors)} failures")

with open(os.path.join(CAT, "corpus_manifest.json"), "w", encoding="utf-8") as f:
    json.dump({"works": results, "errors": errors}, f, ensure_ascii=False, indent=1)
print("manifest -> data/catalog/corpus_manifest.json")
