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
    # R228z续：C0 控制字符剥掉——\x00 会让 FTS5 报 "unterminated string"
    # （内部按 C 串截断），别的控制符也不构成任何检索意义。
    seg = "".join(ch for ch in seg if ord(ch) >= 0x20)
    return f'"{seg}"'


def render_citation(*, work_id: str, title: str | None = None,
                    attribution: str | None = None, edition: str | None = None,
                    page_anchor: str | None = None, file: str = "",
                    scheme: str | None = None, addr_name: str | None = None,
                    gua: int | None = None, yao: str | None = None,
                    skipped_chars: int = 0, suspect: str | None = None) -> str:
    """出处渲染的**唯一实现**（`Hit.citation()` 与 bazi_lookup 共用）。

    为什么抽成模块级函数（R179b，D-231b）：`/api/bazi` 的 evidence 走
    `bazi_lookup.retrieve_fast()`，它返回裸 dict 而非 `Hit`，于是响应里
    根本没有 `citation` 键，前端 `esc(ev.citation||'')` 把出处静默渲染成
    空串——原文有了、出处没了（审查轨 R118a-03 实测）。

    修法上**绝不能在 bazi_lookup 里再拼一遍同样的格式**：同一条渲染规则
    存在两份拷贝、对同样的字节给出不同结论，正是 LESSONS.md L-01 记录的
    真实事故（变体折叠表两份拷贝给出相反结论）。故把格式收成本函数，
    两个调用点都指向它。

    每个组成部分都能在源文件里核验，不做任何推断。披露标记（! 表示引文
    非连续、? 表示地址被质量闸门标记）是出处的一部分，不是可选附加——
    隐藏自己省略了什么的出处，是本项目视为最严重的失败模式。
    """
    who = f"{title or work_id}"
    if attribution:
        who += f"（{attribution}）"
    addr = ""
    if gua is not None or addr_name:
        if scheme == "zhouyi":
            nm = f"（{addr_name}）" if addr_name else ""
            addr = f" 卦{gua}{nm}"
            if yao:
                addr += f"·{yao}"
        else:
            # Generic rendering for any other scheme, e.g. "Genesis 1:1".
            parts = [p for p in (addr_name, str(gua) if gua else None) if p]
            addr = " " + " ".join(parts) + (f":{yao}" if yao else "")
    ed = f" [{edition}]" if edition else ""
    marks = ("!" if skipped_chars else "") + ("?" if suspect else "")
    tail = f" {marks}" if marks else ""
    return f"{who}{ed}{addr} @{page_anchor or '?'} ({file}){tail}"


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
        return render_citation(
            work_id=self.work_id, title=self.title, attribution=self.attribution,
            edition=self.edition, page_anchor=self.page_anchor, file=self.file,
            scheme=self.scheme, addr_name=self.addr_name, gua=self.gua,
            yao=self.yao, skipped_chars=self.skipped_chars, suspect=self.suspect)


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
        This is the operation that page anchors cannot do (D-005).

        Restricted to scheme='zhouyi': this method answers 「what does each
        witness read at 卦N·爻」, and 卦 addressing IS the zhouyi scheme. Without
        the filter, a Bible chapter number could collide with a 卦 number
        (Psalms 99 == 卦99), which would make the impossible-address gate
        (eval_g7 卦99) return Psalms text instead of refusing. The collision is
        real, not hypothetical: measured after Douay was ingested with
        scheme='bcv', addr1=chapter.
        """
        sql = _SELECT + " WHERE u.addr1 = ? AND u.scheme = 'zhouyi'"
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

    def at_scheme(self, scheme: str, addr_name: str | None = None,
                  addr1: int | None = None, addr2: str | None = None,
                  layer: str | None = None, limit: int = 50) -> list[Hit]:
        """Generic address lookup for ANY scheme — 卦/爻 for zhouyi, 卷:章 for bcv,
        幕:場 for play, BOOK:proposition for euclid, etc. `at_address` stays the
        zhouyi-only convenience (D-005: Psalms 99 == 卦99 collision); this is the
        scheme-scoped form used by the web addr view, where the caller declares the
        scheme explicitly so no cross-scheme collision can occur.
        """
        sql = _SELECT + " WHERE u.scheme = ?"
        args: list = [scheme]
        for col, val in (("u.addr_name", addr_name), ("u.addr1", addr1),
                         ("u.addr2", addr2), ("u.layer", layer)):
            if val is not None:
                sql += f" AND {col} = ?"
                args.append(val)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def units_by_id(self, unit_ids: list[int], limit: int = 50) -> list[Hit]:
        """Fetch units by primary key. The link table speaks unit ids (G4), and this is
        the read-back for a hop: `link.dst_unit` -> the unit it points at."""
        if not unit_ids:
            return []
        ids = [int(i) for i in unit_ids[:limit]]
        ph = ",".join("?" * len(ids))
        sql = _SELECT + f" WHERE u.id IN ({ph}) ORDER BY u.work_id, u.raw_start"
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, ids)]

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
