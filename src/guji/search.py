"""Retrieval over the 古籍 index, addressable by 卦/爻 and filterable by layer.

The reason this is not a thin wrapper over FTS5: char-segmenting a CJK query turns it
into multiple tokens, and bare multi-token FTS5 MATCH is an implicit AND anywhere in the
document. Searching 見群龍无首 would then match any unit containing those five characters
in any order or position. Quoting the segmented string forces a phrase match, which is
what a 古籍 lookup means. A hit-count test cannot catch this — it must be checked against
the returned text.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .variants import fold, segment_cjk


def fts_phrase(q: str) -> str:
    """Segmented, folded, and quoted so FTS5 treats it as an adjacent phrase."""
    seg = segment_cjk(fold(q)).replace('"', '')
    return f'"{seg}"'


@dataclass
class Hit:
    work_id: str
    title: str | None
    attribution: str | None
    edition: str | None
    page_anchor: str | None
    gua: int | None            # = addr1
    yao: str | None            # = addr2
    layer: str
    text: str
    file: str
    score: float
    scheme: str | None = None
    addr_name: str | None = None
    skipped_chars: int = 0
    suspect: str | None = None

    @property
    def contiguous(self) -> bool:
        """Is `text` a contiguous run of the source, or an envelope with material removed?"""
        return self.skipped_chars == 0

    def disclosure(self) -> str:
        """What the citation does not otherwise say. Empty when there is nothing to disclose.

        Two things a reader cannot see from the text alone, and both were measured rather
        than assumed (probes/probe_disclosure.py, data/catalog/quality_report.json):

          * 54.1% of units skip material inside their own cited range (median 62 chars,
            max 7,388) because same-address runs were merged across an interleaved layer.
            Quoting 經 while silently dropping the 注 between its halves is conventional
            practice, but leaving it undisclosed is not honest citation.
          * 20 units sit at an address the quality gate flagged as damaged. Returning
            KR1a0006 卦61 上九翰青登于天 with no warning presents OCR corruption as text.
        """
        bits = []
        if self.skipped_chars:
            bits.append(f"⚠ 非连续引文：区间内另有 {self.skipped_chars:,} 字未包含"
                        f"（{self.layer}层过滤）")
        if self.suspect:
            bits.append(f"⚠ 该地址已被质量闸门标记：{self.suspect}")
        return "  ".join(bits)

    def citation(self) -> str:
        """Every component is verifiable in the source file; nothing is inferred."""
        who = f"{self.title or self.work_id}"
        if self.attribution:
            who += f"（{self.attribution}）"
        addr = ""
        if self.gua is not None or self.addr_name:
            if self.scheme == "zhouyi":
                nm = f"（{self.addr_name}）" if self.addr_name else ""
                addr = f" 卦{self.gua}{nm}"
                if self.yao:
                    addr += f"·{self.yao}"
            else:
                # Generic rendering for any other scheme, e.g. "Genesis 1:1".
                parts = [p for p in (self.addr_name, str(self.gua) if self.gua else None)
                         if p]
                addr = " " + " ".join(parts) + (f":{self.yao}" if self.yao else "")
        ed = f" [{self.edition}]" if self.edition else ""
        # Disclosure markers are part of the citation, not an optional extra: a citation
        # that hides what it omitted is the failure mode this project treats as most severe.
        marks = ("!" if self.skipped_chars else "") + ("?" if self.suspect else "")
        tail = f" {marks}" if marks else ""
        return f"{who}{ed}{addr} @{self.page_anchor or '?'} ({self.file}){tail}"


_SELECT = """
SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
       u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
       u.layer, u.text, u.file, u.skipped_chars, u.suspect
FROM unit u JOIN work w ON w.id = u.work_id
"""


class Corpus:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    def stats(self) -> dict:
        q = ("SELECT (SELECT count(*) FROM work) w, (SELECT count(*) FROM unit) u, "
             "(SELECT count(*) FROM unit WHERE addr1 IS NOT NULL) g, "
             "(SELECT count(*) FROM unit WHERE addr2 IS NOT NULL) y")
        r = self.db.execute(q).fetchone()
        return {"works": r["w"], "units": r["u"], "with_gua": r["g"], "with_yao": r["y"]}

    def coverage(self) -> list[sqlite3.Row]:
        return self.db.execute("""
            SELECT w.id, w.title, w.genre, count(u.id) units,
                   sum(u.addr1 IS NOT NULL) addressed,
                   sum(u.addr2 IS NOT NULL) yao_addressed,
                   sum(u.page_anchor IS NOT NULL) anchored
            FROM work w LEFT JOIN unit u ON u.work_id = w.id
            GROUP BY w.id ORDER BY w.genre, w.id""").fetchall()

    def search(self, query: str, limit: int = 10, gua: int | None = None,
               yao: str | None = None, layer: str | None = None,
               work_id: str | None = None, genre: str | None = None,
               scheme: str | None = None, addr_name: str | None = None,
               addr1: int | None = None, addr2: str | None = None) -> list[Hit]:
        """`gua`/`yao` are convenience aliases for `addr1`/`addr2` (D-016). They are kept
        because 卦/爻 is what a 周易 caller means, but they carry no special status in
        storage — a Bible caller passes addr_name/addr1/addr2 through the same path."""
        sql = """
            SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
                   u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
                   u.layer, u.text, u.file, u.skipped_chars, u.suspect,
                   bm25(unit_fts) AS score
            FROM unit_fts
            JOIN unit u ON u.id = unit_fts.rowid
            JOIN work w ON w.id = u.work_id
            WHERE unit_fts MATCH ?"""
        args: list = [fts_phrase(query)]
        for col, val in (("u.addr1", gua if gua is not None else addr1),
                         ("u.addr2", yao if yao is not None else addr2),
                         ("u.scheme", scheme), ("u.addr_name", addr_name),
                         ("u.layer", layer),
                         ("u.work_id", work_id), ("w.genre", genre)):
            if val is not None:
                sql += f" AND {col} = ?"
                args.append(val)
        sql += " ORDER BY score LIMIT ?"
        args.append(limit)
        return [self._hit(r) for r in self.db.execute(sql, args)]

    def at_address(self, gua: int, yao: str | None = None,
                   layer: str | None = None, limit: int = 50) -> list[Hit]:
        """Every edition's text at one canonical address — no query string involved.
        This is the operation that page anchors cannot do (D-005)."""
        sql = _SELECT + " WHERE u.addr1 = ?"
        args: list = [gua]
        if yao:
            sql += " AND u.addr2 = ?"
            args.append(yao)
        if layer:
            sql += " AND u.layer = ?"
            args.append(layer)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def compare(self, gua: int, yao: str, per_work: int = 2) -> dict[str, list[Hit]]:
        """Group one address's text by work: the shape 'compare the commentators' needs."""
        out: dict[str, list[Hit]] = {}
        for h in self.at_address(gua, yao, limit=400):
            out.setdefault(h.work_id, [])
            if len(out[h.work_id]) < per_work:
                out[h.work_id].append(h)
        return out

    @staticmethod
    def _hit(r: sqlite3.Row, score: float | None = None) -> Hit:
        # Explicit field names: positional construction silently misassigns if the
        # SELECT column order is ever edited.
        return Hit(
            work_id=r["work_id"], title=r["title"], attribution=r["attribution"],
            edition=r["edition"], page_anchor=r["page_anchor"], gua=r["gua"],
            yao=r["yao"], layer=r["layer"], text=r["text"], file=r["file"],
            score=score if score is not None else r["score"],
            scheme=r["scheme"], addr_name=r["addr_name"],
            skipped_chars=r["skipped_chars"] or 0, suspect=r["suspect"],
        )
