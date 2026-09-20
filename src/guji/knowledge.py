"""G8: the Derived and Conversation stores, kept physically apart from Source.

Source knowledge lives in corpus.db and is regenerated from data/raw/ by a build. Derived
knowledge (anything a machine concluded) and Conversation memory live in knowledge.db and
cannot be regenerated at all. See knowledge_schema.sql for why that forces two files.

The API is deliberately narrow, and each restriction is the enforcement of a rule that would
otherwise depend on a caller remembering it:

  * `record` will not store an asserting claim with no evidence. Refusals are the sole
    exception, because 「证据不足」 is itself a valid derived output (G7).
  * evidence is captured from a search Hit, so it carries the same file + anchor + address a
    citation carries. There is no way to attach evidence that is not a real passage.
  * `verify` re-reads data/raw/ and re-checks every stored quote. A derived claim whose
    evidence no longer matches the corpus is reported STALE rather than served — the same
    discipline eval_g1.py applies to its gold set, and for the same reason: the store must
    not become an authority on the text.
"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field

from .evalset import body_in, in_space
from .variants import fold, segment_cjk

ASSERTING = ("summary", "diff", "link", "answer")


@dataclass
class Evidence:
    work_id: str
    file: str
    raw_start: int
    raw_end: int
    quote: str
    page_anchor: str | None = None
    scheme: str | None = None
    addr1: int | None = None
    addr2: str | None = None
    role: str = "supports"

    @classmethod
    def from_hit(cls, hit, role: str = "supports") -> "Evidence":
        """Build evidence from a retrieval Hit, so provenance comes along automatically."""
        rs = getattr(hit, "raw_start", None)
        re_ = getattr(hit, "raw_end", None)
        return cls(work_id=hit.work_id, file=hit.file,
                   raw_start=rs if rs is not None else -1,
                   raw_end=re_ if re_ is not None else -1,
                   quote=hit.text, page_anchor=hit.page_anchor, scheme=hit.scheme,
                   addr1=hit.gua, addr2=hit.yao, role=role)

    def citation(self) -> str:
        addr = ""
        if self.scheme == "zhouyi" and self.addr1:
            addr = f" 卦{self.addr1}" + (f"·{self.addr2}" if self.addr2 else "")
        elif self.addr1:
            addr = f" {self.addr1}" + (f":{self.addr2}" if self.addr2 else "")
        return f"{self.work_id}{addr} @{self.page_anchor or '?'} ({self.file})"


@dataclass
class Derived:
    id: int
    kind: str
    claim: str
    method: str
    confidence: str | None
    created_at: str
    evidence: list[Evidence] = field(default_factory=list)


class KnowledgeBase:
    """Derived + Conversation. Opening it never touches corpus.db."""

    def __init__(self, path: str):
        first = not os.path.exists(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        # R228b：并发写撞锁实测 5s 后抛 database is locked → 裸 500。
        # WAL 让读写不互斥；busy_timeout 把短锁等待转化为等待而非秒抛。
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=8000")
        here = os.path.dirname(os.path.abspath(__file__))
        self.db.executescript(
            open(os.path.join(here, "knowledge_schema.sql"), encoding="utf-8").read())
        if first:
            self.db.execute("INSERT OR REPLACE INTO kb_meta VALUES ('created_at', ?)",
                            (time.strftime("%Y-%m-%dT%H:%M:%S"),))
        self.db.commit()

    def close(self):
        self.db.close()

    # -- Derived ---------------------------------------------------------------------
    def record(self, kind: str, claim: str, method: str,
               evidence: list[Evidence] | None = None,
               confidence: str | None = None, thread_id: int | None = None) -> int:
        """Store a derived claim. Refuses an asserting claim with no evidence.

        The refusal is raised rather than logged: a claim without provenance is precisely the
        thing this store exists to make impossible, so allowing it "just this once" would
        defeat the table. G7 refusals pass because kind='refusal' asserts nothing about the
        text — it reports the absence of support, which is a finding in its own right.
        """
        evidence = evidence or []
        if kind in ASSERTING and not evidence:
            raise ValueError(
                f"kind={kind!r} asserts a claim, so it needs at least one Evidence. "
                f"If the point IS that support is missing, record it as kind='refusal'.")
        if kind == "refusal" and evidence:
            # Allowed, and worth keeping: a refusal may cite what it DID look at.
            pass
        cur = self.db.execute(
            "INSERT INTO derived (kind, claim, method, confidence, thread_id, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (kind, claim, method, confidence, thread_id,
             time.strftime("%Y-%m-%dT%H:%M:%S")))
        did = cur.lastrowid
        for e in evidence:
            self.db.execute(
                "INSERT INTO evidence (derived_id, role, work_id, file, raw_start, raw_end,"
                " page_anchor, scheme, addr1, addr2, quote) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (did, e.role, e.work_id, e.file, e.raw_start, e.raw_end, e.page_anchor,
                 e.scheme, e.addr1, e.addr2, e.quote))
        self.db.execute("INSERT INTO derived_fts(rowid, seg) VALUES (?,?)",
                        (did, segment_cjk(fold(claim))))
        self.db.commit()
        return did

    def get(self, derived_id: int) -> Derived | None:
        r = self.db.execute("SELECT * FROM derived WHERE id=?", (derived_id,)).fetchone()
        if not r:
            return None
        ev = [Evidence(work_id=x["work_id"], file=x["file"], raw_start=x["raw_start"],
                       raw_end=x["raw_end"], quote=x["quote"],
                       page_anchor=x["page_anchor"], scheme=x["scheme"],
                       addr1=x["addr1"], addr2=x["addr2"], role=x["role"])
              for x in self.db.execute(
                  "SELECT * FROM evidence WHERE derived_id=? ORDER BY id", (derived_id,))]
        return Derived(r["id"], r["kind"], r["claim"], r["method"], r["confidence"],
                       r["created_at"], ev)

    # R229n（R6-#7）：search_derived 删除——全仓零调用方，且对 C0/NUL
    # 查询仍抛 OperationalError（search.fts_phrase 修过它没修）；留着
    # 是给将来接线埋雷。
    def orphans(self) -> list[int]:
        """Asserting claims with no evidence. Must always be empty (assert in the gate)."""
        return [r["id"] for r in self.db.execute(
            "SELECT d.id FROM derived d LEFT JOIN evidence e ON e.derived_id = d.id "
            "WHERE d.kind != 'refusal' AND e.id IS NULL")]

    def verify(self, raw_dir: str, derived_ids=None) -> dict:
        """Re-check every stored quote against data/raw/. -> {ok, stale, details}.

        Checked in the `folded_notes` space, the same space eval_g1.py verifies its gold in,
        because a quote lifted from a unit has already lost punctuation and had 異體字 folded
        (guji.evalset). Comparing raw bytes here would report every quote as stale.
        derived_ids 给定时只验这些 derived 名下的 evidence（thread_detail
        读路径用——全表重扫挂进 GET 是 R8 P2-4 抓出的 N×全书 放大）。
        """
        ok = 0
        stale = []
        bodies = {}   # R228f：per-work memo——原实现每条 evidence 都重读整本
        if derived_ids is None:
            rows = self.db.execute("SELECT * FROM evidence ORDER BY id")
        elif not derived_ids:
            return {"ok": 0, "stale": 0, "details": []}
        else:
            _ph = ",".join("?" * len(derived_ids))
            rows = self.db.execute(
                f"SELECT * FROM evidence WHERE derived_id IN ({_ph}) ORDER BY id",
                tuple(derived_ids))
        for r in rows:
            if r["work_id"] not in bodies:
                bodies[r["work_id"]] = body_in(raw_dir, r["work_id"],
                                               "folded_notes")
            body = bodies[r["work_id"]]
            # BOTH sides through the same normaliser. An earlier version folded the quote and
            # stripped whitespace by hand, which left punctuation in place: KR1a0001's
            # 「初九、潛龍勿用。」 was reported stale while KR1a0006's unpunctuated 「初九濳龍勿用」
            # verified — the identical signature to the citation 0/30 artefact (L-18), caught
            # here by probe_g8_isolation rather than shipped.
            q = in_space(r["quote"], "folded_notes")
            # Subsequence, not substring: a layer-filtered quote legitimately skips an
            # interleaved 注 (X-10 / G6).
            i = 0
            for ch in body:
                if i < len(q) and ch == q[i]:
                    i += 1
                if i == len(q):   # R8 P2-4：命中即停——原实现恒扫完整本书体
                    break
            if i == len(q):
                ok += 1
            else:
                stale.append({"evidence_id": r["id"], "derived_id": r["derived_id"],
                              "work": r["work_id"], "quote": r["quote"][:40]})
        return {"ok": ok, "stale": len(stale), "details": stale}

    # -- Conversation ----------------------------------------------------------------
    def open_thread(self, topic: str) -> int:
        cur = self.db.execute(
            "INSERT INTO thread (topic, opened_at) VALUES (?,?)",
            (topic, time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.commit()
        return cur.lastrowid

    def add_turn(self, thread_id: int, role: str, text: str) -> int:
        seq = self.db.execute("SELECT coalesce(max(seq), 0) + 1 n FROM turn "
                              "WHERE thread_id=?", (thread_id,)).fetchone()["n"]
        cur = self.db.execute(
            "INSERT INTO turn (thread_id, seq, role, text, created_at) VALUES (?,?,?,?,?)",
            (thread_id, seq, role, text, time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.execute("UPDATE thread SET updated_at=? WHERE id=?",
                        (time.strftime("%Y-%m-%dT%H:%M:%S"), thread_id))
        self.db.commit()
        return cur.lastrowid

    def thread_transcript(self, thread_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM turn WHERE thread_id=? ORDER BY seq",
                               (thread_id,)).fetchall()

    def resume(self) -> list[sqlite3.Row]:
        """Open threads with their derived-claim counts: what G9 needs to pick work back up."""
        return self.db.execute("""
            SELECT t.id, t.topic, t.status, t.opened_at, t.updated_at,
                   (SELECT count(*) FROM turn WHERE thread_id = t.id) turns,
                   (SELECT count(*) FROM derived WHERE thread_id = t.id) claims
            FROM thread t WHERE t.status = 'open'
            ORDER BY coalesce(t.updated_at, t.opened_at) DESC""").fetchall()

    def stats(self) -> dict:
        q = ("SELECT (SELECT count(*) FROM derived) d, (SELECT count(*) FROM evidence) e, "
             "(SELECT count(*) FROM thread) t, (SELECT count(*) FROM turn) u, "
             "(SELECT count(*) FROM derived WHERE kind='refusal') r")
        r = self.db.execute(q).fetchone()
        return {"derived": r["d"], "evidence": r["e"], "threads": r["t"],
                "turns": r["u"], "refusals": r["r"]}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # -- 知命产品化：user_prefs / daily_cache / favorites (R002) ----------------------

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        r = self.db.execute("SELECT value FROM user_prefs WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_pref(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO user_prefs (key, value, updated_at) VALUES (?,?,?)",
            (key, value, time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.commit()

    def set_prefs(self, items: list[tuple[str, str]]) -> None:
        """R228l：批量写偏好——一个事务一次 commit，不再逐键 commit
        （原来 N 键部分成功会留下半截偏好状态）。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.db.executemany(
            "INSERT OR REPLACE INTO user_prefs (key, value, updated_at) VALUES (?,?,?)",
            [(k, v, now) for k, v in items])
        self.db.commit()

    def get_daily_cache(self, date: str) -> dict | None:
        r = self.db.execute("SELECT * FROM daily_cache WHERE date=?", (date,)).fetchone()
        if not r:
            return None
        import json
        return {"date": r["date"],
                "bazi": json.loads(r["bazi_result"]) if r["bazi_result"] else None,
                "tarot": json.loads(r["tarot_result"]) if r["tarot_result"] else None}

    def set_daily_cache(self, date: str, bazi: dict | None = None,
                        tarot: dict | None = None) -> None:
        import json
        # R228j：INSERT OR REPLACE 是整行覆盖——只传 bazi 会把已缓存的
        # tarot_result 抹成 NULL（反之亦然）。UPSERT + COALESCE 只写传入列。
        self.db.execute(
            "INSERT INTO daily_cache (date, bazi_result, tarot_result, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET "
            "bazi_result=COALESCE(excluded.bazi_result, daily_cache.bazi_result), "
            "tarot_result=COALESCE(excluded.tarot_result, daily_cache.tarot_result), "
            "created_at=excluded.created_at",
            (date,
             json.dumps(bazi, ensure_ascii=False) if bazi else None,
             json.dumps(tarot, ensure_ascii=False) if tarot else None,
             time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.commit()

    def add_favorite(self, ftype: str, ref_id: str, title: str) -> int:
        # R228l：同 (type, ref_id) 去重——重复收藏返回已有 id，
        # 幂等比连点出 N 条重复行更贴用户预期。
        r = self.db.execute(
            "SELECT id FROM favorites WHERE type=? AND ref_id=?",
            (ftype, ref_id)).fetchone()
        if r:
            return r["id"]
        cur = self.db.execute(
            "INSERT INTO favorites (type, ref_id, title, created_at) VALUES (?,?,?,?)",
            (ftype, ref_id, title, time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.db.commit()
        return cur.lastrowid

    def list_favorites(self, ftype: str | None = None) -> list[sqlite3.Row]:
        if ftype:
            return self.db.execute(
                "SELECT * FROM favorites WHERE type=? ORDER BY created_at DESC",
                (ftype,)).fetchall()
        return self.db.execute(
            "SELECT * FROM favorites ORDER BY created_at DESC").fetchall()

    def remove_favorite(self, fid: int) -> None:
        self.db.execute("DELETE FROM favorites WHERE id=?", (fid,))
        self.db.commit()
