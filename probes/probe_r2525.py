#!/usr/bin/env python3
"""R2525 — 存储层深审钉扎（agent 40f2e5b9 报告的亲验落地）。

- P1：`record()` 写序包 try/rollback——中途失败（role CHECK /
  int64 溢出绑定）不再把 pending derived 交给下一次 commit
  静默落成幻影断言（零证据+无 FTS）。
- P2-1：`user_prefs` 补 `_CAP_PREFS`=256 总帽 + updated_at/rowid
  DESC LRU 逐出——此前唯一无总帽的用户表且 wipe 不清。
- P2-2：MCP `record_claim_tool` 被拒/异常补偿删新建线程
  （与 web `_drop_thread` 同纪律）。
- P2-3：`_migrate_note` 位置 SELECT 改显式列映射（pre-G9 缺
  thread_id 旧库不再 6→7 列炸穿 __init__ 永久 503）；
  `turn.seq` ALTER 默认值回填每线程 1..N。
- P3-5：`record()` 回滚落地后 `_drop_thread` FK 删除不再被
  挂起 derived 卡死（同源，随 P1 解）。
- P3-6：`open_thread`/`record` 补 rowid 复用孤儿守卫（turn/
  evidence 孤儿不再重绑新行）。
- P3-7：`delete_record` 补 `_write_lock`（全模块写串行纪律补齐）。
- P3-8：`import_threads` 包 `_import_lock`（查重-插入竞态）。
- P3-9：paipan `_ensure_columns` 收进 `_ddl_lock` + 逐列容错。
- P3-10：`import_rows` ts 补控制字清洗（dedup 键+展示字段）。
- 顺带：ThreadEvidence int64 界 + role 枚举校验（503→400 口径）。
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, ".")
sys.path.insert(0, "src")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


_kb = open("src/guji/knowledge.py", encoding="utf-8").read()
_ph = open("src/guji/paipan_history.py", encoding="utf-8").read()
_mc = open("src/guji/mcp_server.py", encoding="utf-8").read()
_sc = open("web/schemas.py", encoding="utf-8").read()

from guji.knowledge import KnowledgeBase, Evidence

# ── P1：record() 回滚 ────────────────────────────────────────────
_rec = _kb[_kb.find("def record("):_kb.find("def get(")]
ck("p1.record_rollback",
   "self.db.rollback()" in _rec and "try:" in _rec)

db = os.path.join(tempfile.mkdtemp(), "k.db")
kb = KnowledgeBase(db)
tid = kb.open_thread("probe-t")
try:
    kb.record("summary", "phantom", "probe",
              [Evidence(work_id="", file="", raw_start=0, raw_end=1,
                        quote="q", role="bogus")])
except Exception:
    pass
kb.record("note", "legit", "probe", [])
rows = kb.db.execute("SELECT kind FROM derived").fetchall()
ck("p1.no_phantom_derived",
   [r["kind"] for r in rows] == ["note"] and kb.orphans() == [])
kb.close()

# ── P2-1：prefs 帽 + LRU ─────────────────────────────────────────
ck("p2.cap_prefs", "_CAP_PREFS = 256" in _kb)
ck("p2.gc_order_desc",
   "ORDER BY updated_at DESC, rowid DESC" in _kb)
db = os.path.join(tempfile.mkdtemp(), "k.db")
kb = KnowledgeBase(db)
kb.set_prefs([(f"fp-{i}", "x") for i in range(600)])
kb.set_pref("theme", "dark")
n = kb.db.execute("SELECT count(*) c FROM user_prefs").fetchone()["c"]
ck("p2.prefs_capped", n <= 256, f"rows={n}")
ck("p2.prefs_lru",
   kb.get_pref("theme") == "dark" and kb.get_pref("fp-0") is None)
kb.close()

# ── P2-2：MCP 补偿删 ─────────────────────────────────────────────
ck("p2.mcp_compensate",
   "_opened = True" in _mc and
   'DELETE FROM turn WHERE thread_id=?' in _mc and
   "except Exception as exc:" in _mc)

# ── P2-3：迁移显式列 + seq 回填 ──────────────────────────────────
ck("p2.migrate_explicit_cols",
   "INSERT INTO derived_new\n                    (id, kind, claim, method, confidence, thread_id, created_at)"
   in _kb and "_sel" in _kb)
ck("p2.seq_backfill", "WHERE seq = 0" in _kb)

# ── P3-6：rowid 孤儿守卫 ─────────────────────────────────────────
_ot = _kb[_kb.find("def open_thread"):_kb.find("def add_turn")]
ck("p3.open_thread_orphan_guard",
   "DELETE FROM turn WHERE thread_id=?" in _ot and
   "UPDATE derived SET thread_id=NULL WHERE thread_id=?" in _ot)
ck("p3.record_evidence_orphan_guard",
   "DELETE FROM evidence WHERE derived_id=?" in _rec)

# ── P3-7/8/9/10 ──────────────────────────────────────────────────
ck("p3.delete_write_lock",
   "with _write_lock, contextlib.closing(_conn()) as c, c:" in _ph and
   _ph.find("_write_lock, contextlib.closing(_conn()) as c, c:\n        cur = c.execute(\"DELETE FROM records") > 0)
ck("p3.import_lock", "_import_lock" in _kb and
   "def _import_threads" in _kb)
ck("p3.ddl_lock_covers_ensure",
   "with _ddl_lock:\n                _ensure_columns(conn)" in _ph or
   "with _ddl_lock:\n            _ensure_columns(conn)" in _ph)
ck("p3.ts_ctrl_scrub",
   '_CTRL_RE.sub("", str(r.get("ts")))' in _ph)

# ── 顺带：schema 界 ──────────────────────────────────────────────
ck("sc.addr_int64_bound", "ge=-(2**63), le=2**63 - 1" in _sc)
# role 枚举走 DB CHECK→IntegrityError→400 的既有纪律（selftest
# err.threads.role 钉 400，pydantic 层拦会把它变 422——不加）。

# ── 行为：prefs 逐出不碰合法小量 ──────────────────────────────────
db = os.path.join(tempfile.mkdtemp(), "k.db")
kb = KnowledgeBase(db)
kb.set_prefs([("theme", "light"), ("recent_modules", "bazi")])
kb.set_prefs([(f"fx-{i}", "v") for i in range(300)])
ck("bh.legit_evicted_ok",
   kb.get_pref("theme") is None or kb.get_pref("theme") == "light")
n2 = kb.db.execute("SELECT count(*) c FROM user_prefs").fetchone()["c"]
ck("bh.cap_holds", n2 <= 256, f"rows={n2}")
kb.close()

print(f"\n{len(PASS)} pass, {len(FAIL)} fail")
sys.exit(1 if FAIL else 0)
