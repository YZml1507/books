"""Book Study (founding brief §7): the structured map of a whole work.

The research modes built so far answer "find me this" (search/addr), "compare
witnesses here" (compare), "follow this concept" (concept), and "run the loop"
(research). What was missing is the READING mode: 「系统性学习整本书」 — before
asking anything, a reader needs the work's skeleton: its sections in order, how
much text each carries, which layers (經/注/疏) are present, and a first-line
sample to recognise the territory.

`structure()` groups a work's units by their address key in a scheme-aware way:

  zhouyi  -> one row per 卦 (name from addr_name, 爻 count, 經/注 sizes)
  bcv     -> one row per 卷 (addr_name)
  yilin   -> one row per 本卦 (addr1)
  booksec / play / euclid -> one row per top level (addr_name or addr1)
  NULL    -> one row per FILE (卷 = file), the only structure such works have

Rows carry real citations for their samples — the map is itself evidence, not a
generated summary; every number is a COUNT over the index, recomputed on call.
"""
from __future__ import annotations

from .search import Corpus


def _row_key(r) -> tuple:
    """Group key for one unit row, by the row's OWN scheme — a work may carry a
    few unaddressed units (序/appendix) next to its addressed body, and those
    must not produce a bogus 「卦None」 section."""
    if not r["scheme"]:
        return ("file", r["file"])
    if r["scheme"] == "zhouyi":
        return ("zhouyi", r["addr1"])
    return (r["scheme"], r["addr_name"], r["addr1"])


def structure(corpus: Corpus, work_id: str, sample_chars: int = 60) -> dict:
    """The reading map of one work: sections in source order, sizes, layers, samples."""
    w = corpus.db.execute(
        "SELECT id, title, attribution, edition, genre FROM work WHERE id = ?",
        (work_id,)).fetchone()
    if w is None:
        return {"error": f"work {work_id} not found"}
    rows = corpus.db.execute(
        "SELECT scheme, addr_name, addr1, addr2, layer, text, file, page_anchor, "
        "suspect, skipped_chars FROM unit WHERE work_id = ? ORDER BY raw_start",
        (work_id,)).fetchall()
    if not rows:
        return {"error": f"work {work_id} has no units"}

    # work's main scheme = mode of non-NULL row schemes (first row may be a
    # NULL-scheme heading/appendix, e.g. KR1a0001 "** 《乾第一》")
    from collections import Counter
    _counts = Counter(r["scheme"] for r in rows if r["scheme"])
    scheme = _counts.most_common(1)[0][0] if _counts else rows[0]["scheme"]
    names = {r["addr1"]: r["addr_name"] for r in rows
             if r["scheme"] == "zhouyi" and r["addr_name"]}
    sections: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        k = _row_key(r)
        if k not in sections:
            if not r["scheme"]:
                label = r["file"]
            elif r["scheme"] == "zhouyi":
                gua = r["addr1"]
                label = f"卦{gua}" + (f"（{names.get(gua, '')}）"
                                      if names.get(gua) else "")
            else:
                label = str(r["addr_name"] or r["addr1"])
            sections[k] = {"label": label, "scheme": r["scheme"],
                           "n_units": 0, "chars": 0, "layers": {},
                           "addr2": 0, "suspect": 0,
                           "sample": None, "sample_cite": None}
            order.append(k)
        s = sections[k]
        s["n_units"] += 1
        s["chars"] += len(r["text"])
        s["layers"][r["layer"]] = s["layers"].get(r["layer"], 0) + 1
        if r["addr2"]:
            s["addr2"] += 1
        if r["suspect"]:
            s["suspect"] += 1
        if s["sample"] is None and r["text"].strip():
            s["sample"] = r["text"].strip()[:sample_chars]
            s["sample_cite"] = (f"@{r['page_anchor'] or '?'} ({r['file']})")

    out_rows = []
    for k in order:
        s = sections[k]
        out_rows.append({
            "label": s["label"], "key": list(k), "scheme": s["scheme"],
            "n_units": s["n_units"], "chars": s["chars"],
            "layers": s["layers"], "with_addr2": s["addr2"],
            "suspect_units": s["suspect"],
            "sample": s["sample"], "sample_citation": s["sample_cite"],
        })
    return {
        "work_id": work_id, "title": w["title"], "attribution": w["attribution"],
        "edition": w["edition"], "genre": w["genre"], "scheme": scheme,
        "n_units": len(rows), "n_sections": len(out_rows),
        "sections": out_rows,
    }


def chapter(corpus: Corpus, work_id: str, scheme: str,
            addr_name: str | None = None, addr1: int | None = None,
            file: str | None = None, limit: int = 60) -> dict:
    """One section's reading view: every unit in source order with citations —
    經/注 interleaved as printed, damaged units disclosed, not silently dropped."""
    # The section filter must live in SQL, BEFORE the LIMIT: raw_start order is
    # work-global, so the first `limit` rows of a big work (bible-douay 35,787
    # verses, zhouyi 527 units) are all the EARLIEST section — filtering after
    # the LIMIT would report every later section (卦40, Exodus) as "not found".
    if scheme == "file":
        # NULL-scheme works (老子/莊子注…) group by FILE in structure() and
        # their units carry scheme=NULL — the section filter must be u.file.
        if file is None:
            return {"error": f"section needs file for {work_id}"}
        where = "u.work_id = ? AND u.file = ?"
        params: list = [work_id, file]
    else:
        where = "u.work_id = ? AND u.scheme = ?"
        params = [work_id, scheme]
        if scheme == "zhouyi":
            if addr1 is None:
                return {"error": f"section needs addr1 (卦號) for {work_id}"}
            where += " AND u.addr1 = ?"
            params.append(addr1)
        else:
            if addr_name is not None:
                where += " AND u.addr_name = ?"
                params.append(addr_name)
            if addr1 is not None:
                where += " AND u.addr1 = ?"
                params.append(addr1)
    rows = corpus.db.execute(
        "SELECT u.scheme, u.addr_name, u.addr1, u.addr2, u.layer, u.text, "
        "u.file, u.page_anchor, u.suspect, u.skipped_chars FROM unit u "
        f"WHERE {where} ORDER BY u.raw_start LIMIT ?",
        params + [limit]).fetchall()
    if not rows:
        # R230a-35（R14-P3-11）：三者皆空时返回文本不再出现字面 "None"。
        sec = file or addr_name or addr1
        return {"error": f"section {sec if sec is not None else '(未指名)'} "
                         f"not found in {work_id}"}
    units = [{
        "addr2": r["addr2"], "layer": r["layer"], "text": r["text"],
        "citation": (f"@{r['page_anchor'] or '?'} ({r['file']})"
                     + (" ?" if r["suspect"] else "")
                     + (" !" if r["skipped_chars"] else "")),
        "suspect": r["suspect"],
    } for r in rows]
    return {"work_id": work_id, "scheme": scheme,
            "section": file or addr_name or addr1, "n_units": len(units), "units": units}


def book_summary(corpus: Corpus, work_id: str) -> dict:
    """One work's structured knowledge card (愿景 §7 Book Summary): aggregated
    counts and layer distribution over the WHOLE book, plus the reading
    attention points (largest/smallest sections, damaged units disclosed).

    Pure read-only aggregation over the index — every number is a COUNT
    recomputed on call, exactly like structure().
    """
    w = corpus.db.execute(
        "SELECT id, title, attribution, edition, genre FROM work WHERE id = ?",
        (work_id,)).fetchone()
    if w is None:
        return {"error": f"work {work_id} not found"}
    rows = corpus.db.execute(
        "SELECT scheme, layer, text, suspect, skipped_chars FROM unit "
        "WHERE work_id = ?", (work_id,)).fetchall()
    if not rows:
        return {"error": f"work {work_id} has no units"}
    n_units = len(rows)
    total_chars = sum(len(r["text"]) for r in rows)
    layers: dict[str, dict] = {}
    suspect = skipped = unaddressed = 0
    for r in rows:
        if r["scheme"]:
            lv = layers.setdefault(r["layer"], {"units": 0, "chars": 0})
            lv["units"] += 1
            lv["chars"] += len(r["text"])
        else:
            unaddressed += 1
        if r["suspect"]:
            suspect += 1
        if r["skipped_chars"]:
            skipped += 1
    st = structure(corpus, work_id, sample_chars=60)
    sections = st.get("sections", [])
    if sections:
        largest = max(sections, key=lambda s: s["chars"])
        smallest = min(sections, key=lambda s: s["chars"])
        largest = {"label": largest["label"], "chars": largest["chars"]}
        smallest = {"label": smallest["label"], "chars": smallest["chars"]}
    else:
        largest = smallest = None
    return {
        "work_id": work_id, "title": w["title"], "attribution": w["attribution"],
        "edition": w["edition"], "genre": w["genre"], "scheme": st.get("scheme"),
        "n_sections": len(sections), "n_units": n_units, "total_chars": total_chars,
        "layers": layers, "unaddressed_units": unaddressed,
        "suspect_units": suspect, "skipped_chars_units": skipped,
        "largest_section": largest, "smallest_section": smallest,
    }


if __name__ == "__main__":
    # Self-test (R23b). Run: PYTHONPATH=src python -m guji.bookstudy
    import os
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    c = Corpus(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "index", "corpus.db"))

    s1 = structure(c, "KR1a0001")
    zy = [r for r in s1.get("sections", []) if r["scheme"] == "zhouyi"]
    assert "error" not in s1 and s1["scheme"] == "zhouyi" and len(zy) == 64, \
        (s1.get("error"), len(zy))
    q1 = next(r for r in zy if r["key"] == ["zhouyi", 1])
    assert "乾" in q1["label"] and q1["chars"] > 0 and q1["sample"]
    print(f"[1] KR1a0001 -> {len(zy)} 卦 (+{s1['n_sections'] - len(zy)} 未编址区), "
          f"卦1 {q1['label']} {q1['chars']} chars, layers={q1['layers']}")

    s2 = structure(c, "KR5c0057")   # 老子, NULL scheme -> per-file sections
    assert "error" not in s2 and s2["n_sections"] >= 70, s2.get("error")
    assert all(r["sample_citation"] for r in s2["sections"])
    print(f"[2] 老子 -> {s2['n_sections']} file-sections, "
          f"first: {s2['sections'][0]['label']} {s2['sections'][0]['chars']} chars")

    s3 = structure(c, "bible-douay")
    assert "error" not in s3 and s3["n_sections"] >= 60
    print(f"[3] douay -> {s3['n_sections']} books under {s3['scheme']}")

    ch = chapter(c, "KR1a0001", "zhouyi", addr1=1)
    assert "error" not in ch and ch["n_units"] > 0 and \
        all(u["citation"] for u in ch["units"])
    print(f"[4] chapter 卦1 -> {ch['n_units']} units in source order")
    ch404 = chapter(c, "KR1a0001", "zhouyi", addr1=99)
    assert "error" in ch404
    print("[5] chapter 卦99 -> refused:", ch404["error"])

    # later sections must survive the work-global raw_start LIMIT (regression:
    # the section filter used to run AFTER the SQL LIMIT, so any section beyond
    # the first `limit` rows — 卦40, Exodus — was misreported as not found)
    ch40 = chapter(c, "KR1a0001", "zhouyi", addr1=40)
    assert "error" not in ch40 and ch40["n_units"] > 0 and \
        all(u["citation"] for u in ch40["units"])
    print(f"[6] chapter 卦40 -> {ch40['n_units']} units (not first section, still found)")
    ch_ex = chapter(c, "bible-douay", "bcv", addr_name="Exodus")
    assert "error" not in ch_ex and ch_ex["n_units"] > 0 and \
        all(u["citation"] for u in ch_ex["units"])
    print(f"[7] chapter douay Exodus -> {ch_ex['n_units']} verses in source order")

    # NULL-scheme works (老子) group by FILE in structure(); chapter must open
    # that file section via the file param (scheme-filter alone would match 0)
    ch_file = chapter(c, "KR5c0057", "file", file="KR5c0057_001.txt")
    assert "error" not in ch_file and ch_file["n_units"] > 0 and \
        all(u["citation"] for u in ch_file["units"])
    print(f"[8] chapter 老子 file 001 -> {ch_file['n_units']} units "
          f"(NULL-scheme file section readable)")

    sm = book_summary(c, "KR1a0001")
    assert "error" not in sm and sm["n_sections"] == 65 and sm["n_units"] > 0
    assert sm["total_chars"] > 0 and sm["layers"]["經"]["units"] > 0
    assert sm["largest_section"] and sm["smallest_section"]
    assert sm["n_units"] == sum(sv["units"] for sv in sm["layers"].values()) \
        + sm["unaddressed_units"], "layer units + unaddressed must equal n_units"
    print(f"[9] book_summary KR1a0001 -> {sm['n_sections']} 节 {sm['n_units']} "
          f"单元 {sm['total_chars']} 字 layers={sorted(sm['layers'])} "
          f"largest={sm['largest_section']['label']}")
    sm2 = book_summary(c, "KR5c0057")
    assert "error" not in sm2 and sm2["n_sections"] >= 70
    print(f"[10] book_summary 老子 -> {sm2['n_sections']} 节 "
          f"{sm2['total_chars']} 字 unaddressed={sm2['unaddressed_units']}")
    sm404 = book_summary(c, "NO_SUCH_WORK")
    assert "error" in sm404
    print(f"[11] book_summary missing -> refused: {sm404['error']}")
    print("self-test PASS")
    c.close()
