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

import glob
import os
import sqlite3
import time
from datetime import datetime
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
        # R230i（R21-P1-8）：data/ 是普通文件等 OS 级失败时，
        # makedirs 抛 FileExistsError——让它落到 errors.py 的 OSError→503
        # 而不是裸 500。
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        # R230i（R21-P1-1）：库损坏此前全端点永久 503（文案还暗示暂时性）。
        # 与 paipan_history 同档自愈：探测 sqlite_master 失败→坏文件挪到
        # .corrupt-<ts> 留档，开新空库——读路径降级为空数据而不是死。
        # busy_timeout 必须在探针/quick_check 之前——否则并发写期的短锁
        # 会以 OperationalError 炸在探针里（R21 P0-3 同款坑：锁≠坏）。
        self.db.execute("PRAGMA busy_timeout=8000")
        try:
            self.db.execute(
                "SELECT name FROM sqlite_master LIMIT 1").fetchall()
            # R230l（R24-P3-9）：sqlite_master 探针只验「文件头可解析」——
            # 断电写坏中层页时 sqlite_master 完好、首个查询才炸。
            # knowledge.db 体积小，quick_check 全表扫一遍代价可忽略；
            # 非 ok 走同一条隔离自愈路径。
            _qc = self.db.execute("PRAGMA quick_check(1)").fetchone()
            if not _qc or _qc[0] != "ok":
                raise sqlite3.DatabaseError("quick_check 未通过")
        except sqlite3.OperationalError:
            raise   # OperationalError（锁/忙）不是损坏——透传不隔离
        except sqlite3.DatabaseError:
            self.db.close()
            # R230t（R31-P3-16）：与 paipan_history._quarantine 对齐——
            # 毫秒戳防同秒覆盖；留档只留最新 5 份。
            qua = (path + ".corrupt-" +
                   datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:21])
            try:
                os.replace(path, qua)
            except FileNotFoundError:
                pass   # 竞态：文件已被别处挪走——直接开新库
            except OSError:
                raise   # 挪不走就维持报错，别强装自愈
            else:
                try:
                    for _f in sorted(glob.glob(path + ".corrupt-*"))[:-5]:
                        os.remove(_f)
                except OSError:
                    pass
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA busy_timeout=8000")
        self.db.execute("PRAGMA foreign_keys = ON")
        # R228b：并发写撞锁实测 5s 后抛 database is locked → 裸 500。
        # WAL 让读写不互斥；busy_timeout 把短锁等待转化为等待而非秒抛。
        # R230i（R21-P1-2）：只读文件上 journal_mode=WAL 是写操作会
        # 整库打不开——降级继续（rollback 模式照样能读，写端点自会 503）。
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            schema = open(os.path.join(here, "knowledge_schema.sql"),
                          encoding="utf-8").read()
        except FileNotFoundError as exc:
            # R2349w（R93-P0-2）：exe 打包漏带 schema 时裸
            # FileNotFoundError 穿透成 503+绝对路径。给可定位的人话。
            raise FileNotFoundError(
                "知识库的建表脚本没打进包里（knowledge_schema.sql）"
            ) from exc
        try:
            self.db.executescript(schema)
        except sqlite3.Error:
            # R230i（R21-P1-3，R230t 订正注释）：executescript 会先隐式
            # COMMIT 再逐条执行——整体并非事务性原子，中途失败时前面语句
            # 已落库。老库上 schema 漂移（如索引撞缺列）一处失败仍会让
            # 全端点 503，所以降级逐条执行，单条失败不连坐（注释行剥掉
            # 再分号切）。
            for stmt in schema.split(";"):
                stmt = "\n".join(l for l in stmt.splitlines()
                                 if not l.strip().startswith("--")).strip()
                if not stmt:
                    continue
                try:
                    self.db.execute(stmt)
                except sqlite3.Error:
                    pass
        self._ensure_columns()
        self._migrate_note()
        if first:
            self.db.execute("INSERT OR REPLACE INTO kb_meta VALUES ('created_at', ?)",
                            (time.strftime("%Y-%m-%dT%H:%M:%S"),))
        self.db.commit()

    # R230i（R21-P0-1/P0-2）：老库缺列自愈——`SELECT *`+Row 按名取列
    # 撞旧表缺列直接 IndexError→500。建库后按现行 schema 补缺失列
    # （ALTER TABLE ADD COLUMN，幂等）。
    _ENSURE_COLS = {
        "derived":    {"confidence": "TEXT"},
        "thread":     {"updated_at": "TEXT"},
        "turn":       {"seq": "INTEGER NOT NULL DEFAULT 0",
                       "text": "TEXT NOT NULL DEFAULT ''"},
        "daily_cache": {"tarot_result": "TEXT"},
        "favorites":  {"title": "TEXT NOT NULL DEFAULT ''"},
        "user_prefs": {"updated_at": "TEXT NOT NULL DEFAULT ''"},
    }

    # R2349z（R96-P0-1）：derived.kind 的 CHECK 枚举补 'note'——用户
    # 「记一条」走非断言通道。CHECK 不可 ALTER，老库整表重建
    # （行数有 _CAP_DERIVED 帽，重建代价恒定小；id 保留 → evidence/
    # derived_fts 的外键与 rowid 关系不破）。
    def _migrate_note(self) -> None:
        row = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE name='derived'").fetchone()
        if not row or "'note'" in (row[0] or ""):
            return
        try:
            self.db.execute("PRAGMA foreign_keys=OFF")
            self.db.executescript('''
                BEGIN;
                CREATE TABLE derived_new (
                    id          INTEGER PRIMARY KEY,
                    kind        TEXT NOT NULL,
                    claim       TEXT NOT NULL,
                    method      TEXT NOT NULL,
                    confidence  TEXT,
                    thread_id   INTEGER REFERENCES thread(id),
                    created_at  TEXT NOT NULL,
                    CHECK (kind IN ('summary', 'diff', 'link', 'answer',
                                   'refusal', 'note'))
                );
                INSERT INTO derived_new SELECT * FROM derived;
                DROP TABLE derived;
                ALTER TABLE derived_new RENAME TO derived;
                COMMIT;
            ''')
        finally:
            self.db.execute("PRAGMA foreign_keys=ON")

    def _ensure_columns(self) -> None:
        for table, cols in self._ENSURE_COLS.items():
            try:
                have = {r[1] for r in
                        self.db.execute(f"PRAGMA table_info({table})")}
            except sqlite3.DatabaseError:
                continue
            for col, ddl in cols.items():
                if col not in have:
                    try:
                        self.db.execute(
                            f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                    except sqlite3.DatabaseError:
                        pass
        self.db.commit()

    def close(self):
        # R230t（R31-P2-3）：WAL 侧车文件（-wal）里的已提交页在 close 前
        # 先 checkpoint 回主库——否则进程中断/冷拷贝目录时，单拿 .db 不含
        # wal 内容会丢最近的写入。
        try:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass
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
        self._gc_derived()
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
            if not r["work_id"]:
                continue    # 纯文字 claim：无出处可核验，不算 stale 也不算 ok
            if not (r["quote"] or "").strip():
                # R230a-32（R14-P2-4）：有出处无引文——声称可核验实则恒真，
                # 按 stale 计（不可核验 ≠ 已核验）。
                stale.append({"evidence_id": r["id"], "derived_id": r["derived_id"],
                              "work": r["work_id"], "quote": ""})
                continue
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
    # R233x（R56-P1）：五张用户表此前无行数帽——threads 端点实测
    # ~130KB/请求可无限写。封顶值按「单机自用十年也用不满」给。
    _CAP_THREAD = 200
    _CAP_TURN_PER_THREAD = 500
    _CAP_DERIVED = 2000
    _CAP_FAVORITES = 500

    def _gc_threads(self) -> None:
        """线程超帽：删最旧的（closed 优先，再按 updated_at），
        级联清 turn/derived/evidence/derived_fts 孤儿行。"""
        over = self.db.execute(
            "SELECT id FROM thread ORDER BY "
            "(status='open') DESC, updated_at DESC "
            "LIMIT -1 OFFSET ?", (self._CAP_THREAD,)).fetchall()
        for r in over:
            tid = r["id"]
            self.db.execute("DELETE FROM turn WHERE thread_id=?", (tid,))
            self.db.execute(
                "DELETE FROM evidence WHERE derived_id IN "
                "(SELECT id FROM derived WHERE thread_id=?)", (tid,))
            self.db.execute(
                "DELETE FROM derived_fts WHERE rowid IN "
                "(SELECT id FROM derived WHERE thread_id=?)", (tid,))
            self.db.execute("DELETE FROM derived WHERE thread_id=?", (tid,))
            self.db.execute("DELETE FROM thread WHERE id=?", (tid,))

    def _gc_derived(self) -> None:
        over = self.db.execute(
            "SELECT id FROM derived ORDER BY id DESC LIMIT -1 OFFSET ?",
            (self._CAP_DERIVED,)).fetchall()
        for r in over:
            self.db.execute("DELETE FROM evidence WHERE derived_id=?",
                            (r["id"],))
            self.db.execute("DELETE FROM derived_fts WHERE rowid=?",
                            (r["id"],))
            self.db.execute("DELETE FROM derived WHERE id=?", (r["id"],))

    def open_thread(self, topic: str) -> int:
        cur = self.db.execute(
            "INSERT INTO thread (topic, opened_at) VALUES (?,?)",
            (topic, time.strftime("%Y-%m-%dT%H:%M:%S")))
        # R233x：插后裁——先 GC 再插会恒超帽一行。
        self._gc_threads()
        self.db.commit()
        return cur.lastrowid

    def add_turn(self, thread_id: int, role: str, text: str) -> int:
        # R233x（R56-P2）：SELECT+INSERT 两段式 seq 有竞态（并发同 seq
        # 重复）——INSERT..SELECT 单语句原子化，并让单线程轮数有帽。
        cur = self.db.execute(
            "INSERT INTO turn (thread_id, seq, role, text, created_at) "
            "SELECT ?, coalesce(max(seq), 0) + 1, ?, ?, ? FROM turn "
            "WHERE thread_id=?",
            (thread_id, role, text, time.strftime("%Y-%m-%dT%H:%M:%S"),
             thread_id))
        self.db.execute(
            "DELETE FROM turn WHERE thread_id=? AND id NOT IN "
            "(SELECT id FROM turn WHERE thread_id=? ORDER BY seq DESC "
            "LIMIT ?)", (thread_id, thread_id, self._CAP_TURN_PER_THREAD))
        self.db.execute("UPDATE thread SET updated_at=? WHERE id=?",
                        (time.strftime("%Y-%m-%dT%H:%M:%S"), thread_id))
        self.db.commit()
        return cur.lastrowid

    def thread_transcript(self, thread_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM turn WHERE thread_id=? ORDER BY seq",
                               (thread_id,)).fetchall()

    def resume(self, status: str = "open") -> list[sqlite3.Row]:
        """Threads with derived-claim counts: what G9 needs to pick work back up.

        R2349z（R96-P1-1）：status 过滤——'open' 默认不变，'parked'/
        'closed' 列收起与聊完的（此前收起的线程从列表永久消失），
        'all' 全量。"""
        where = "" if status == "all" else "WHERE t.status = ?"
        args = () if status == "all" else (status,)
        return self.db.execute(f"""
            SELECT t.id, t.topic, t.status, t.opened_at, t.updated_at,
                   (SELECT count(*) FROM turn WHERE thread_id = t.id) turns,
                   (SELECT count(*) FROM derived WHERE thread_id = t.id) claims
            FROM thread t {where}
            ORDER BY coalesce(t.updated_at, t.opened_at) DESC
            LIMIT 50""", args).fetchall()
        # R230j（R22-P2-2）：无 LIMIT 时前端全量渲染——对齐
        # /api/paipan/history?limit=50 的既有口径。

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
        try:
            return {"date": r["date"],
                    "bazi": json.loads(r["bazi_result"]) if r["bazi_result"] else None,
                    "tarot": json.loads(r["tarot_result"]) if r["tarot_result"] else None}
        except ValueError:
            # R233x（R56-P0）：坏行让该日期永久 500——删掉让它走重算路径。
            self.db.execute("DELETE FROM daily_cache WHERE date=?", (date,))
            self.db.commit()
            return None

    def set_daily_cache(self, date: str, bazi: dict | None = None,
                        tarot: dict | None = None) -> None:
        import json
        from datetime import date as _d, timedelta as _td
        # R229z续24（R9-P2-5）：daily_cache 原本无 DELETE 路径——每个被查过
        # 的日期永久滞留一行。date 主键是 ISO 串，字典序=时间序，90 天前直删。
        # R230a-43 续：清在写入之前——写被拒（窗外/坏日期）时清理仍要发生，
        # 否则攻击者灌进表里的 2099-12-31 行永远没人扫。
        _cutoff = (_d.today() - _td(days=90)).strftime("%Y-%m-%d")
        _future = (_d.today() + _td(days=31)).strftime("%Y-%m-%d")
        self.db.execute(
            "DELETE FROM daily_cache WHERE date < ? OR date > ?",
            (_cutoff, _future))
        # R230a-43（R15-P2-3）：GET /api/daily 有写副作用且 purge 只删
        # 90 天前——脚本扫 1900-2100 全日期可灌 ~7.3 万行且未来行
        # 永不清理。缓存写入限窗口：过去 400 天 ~ 未来 31 天。
        try:
            _d0 = _d.fromisoformat(date)
        except ValueError:
            self.db.commit()
            return
        if not (_d.today() - _td(days=400) <= _d0 <= _d.today() + _td(days=31)):
            self.db.commit()
            return
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
        # R230i（R21-P2-1）：SELECT-then-INSERT 非原子——跨实例并发同
        # (type,ref_id) 实测落重复行。加 UNIQUE 索引后 INSERT OR IGNORE
        # 兜底；老库有重复行导致索引建不成时退回检查路径（仍能去重
        # 绝大多数场景）。
        cur = self.db.execute(
            "INSERT OR IGNORE INTO favorites (type, ref_id, title, created_at) "
            "VALUES (?,?,?,?)",
            (ftype, ref_id, title, time.strftime("%Y-%m-%dT%H:%M:%S")))
        # R233x：插后裁——先裁再插恒超帽一行。
        self.db.execute(
            "DELETE FROM favorites WHERE id NOT IN "
            "(SELECT id FROM favorites ORDER BY created_at DESC LIMIT ?)",
            (self._CAP_FAVORITES,))
        self.db.commit()
        if cur.lastrowid:
            return cur.lastrowid
        r = self.db.execute(
            "SELECT id FROM favorites WHERE type=? AND ref_id=?",
            (ftype, ref_id)).fetchone()
        return r["id"] if r else cur.lastrowid

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

    def clear_favorites(self) -> None:
        # R2349（R65-P1-2）：「忘掉我的数据」须覆盖收藏——CP/心水名单
        # 的 ref_id 编码生辰+昵称，漏清=隐私承诺破洞。
        self.db.execute("DELETE FROM favorites")
        self.db.commit()
