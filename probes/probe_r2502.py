"""probes/probe_r2502.py — R2502 批次硬修复回归闸。

钉扎本轮每个后端/边界修复，全部 TestClient 直测（离线，不打 LLM）：

 1. ask_date / client_date / range 起止的 ISO 变体（20260101、2026-W01-1）
    Py3.11+ 下能过旧校验但在 bazi_calc 的 split('-') 里炸 500 → 现 400。
 2. /api/threads?limit：0/负/超 500 → 400（与 search/addr 同口径）；
    limit>50 真正下推 SQL（此前 resume() 硬编 50，truncated 谎报）。
 3. /api/search?genre 拼错类别 → 400（与 work/layer 存在性校验同口径）。
 4. /api/daily?date= 变体 → R2502 曾归一化放行；R2506（审-F3）改为
    与 POST _iso_canonical 同口径 400——不落脏缓存键的不变式更严守；
    ?bday=garbage → 400（不再静默吞）。
 5. /api/huangli?affair 超长 → 422（max_length=32）。
 6. 备份回灌：evidence/confidence 塞非标量类型 → 不再 InterfaceError/
    OverflowError 逃逸成 5xx，坏记录跳过、好记录照常落。
 7. BOOKS_WRITE_DISABLE=1 下 GET /api/daily 照算照回但不写
    daily_cache——公开演示态共享库写面全拒。
 8. _gc_threads 排序 coalesce(updated_at, opened_at)：新建线程
    updated_at=NULL 不再被 DESC 排到最旧当场误删（实例级缩帽验证）。
 9. _access_gate 的 XFF：默认不信（轮换 XFF 不换桶 → 429 仍命中），
    BOOKS_TRUST_XFF=1 才取链尾。

退出码：0 全绿；1 有 FAIL；2 probe 自身出错。
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  {detail}" if detail else ""))


def main() -> int:
    from fastapi.testclient import TestClient
    from web.app import create_app

    app = create_app()
    c = TestClient(app)

    # ── 1. ISO 变体即拒（不再 500）────────────────────────────
    _base = {"year": 1990, "month": 5, "day": 6, "hour": 12,
             "gender": "男", "scope": "day"}
    for field, val in (("ask_date", "20260101"), ("ask_date", "2026-W01-1")):
        r = c.post("/api/bazi", json={**_base, field: val})
        check(f"bazi {field}={val} → 4xx 非 500",
              r.status_code == 400, f"status={r.status_code}")
    # client_date 长在 Liuyao/Chat/Tarot 请求体上（BaziRequest 无此字段，
    # 发过去是 pydantic 忽略的 extra → 200 属正确行为）。
    for val in ("20260101", "2026-13-40"):
        r = c.post("/api/liuyao", json={
            "method": "coins", "question": "探针", "client_date": val})
        check(f"liuyao client_date={val} → 400",
              r.status_code == 400, f"status={r.status_code}")
    r = c.post("/api/bazi", json={**_base, "scope": "range",
                                  "range_start": "20260101",
                                  "range_end": "2026-01-10"})
    check("bazi range ISO 变体 → 400", r.status_code == 400,
          f"status={r.status_code}")
    r = c.post("/api/bazi", json={**_base, "scope": "range",
                                  "range_start": "2026-01-01",
                                  "range_end": "2026-01-10"})
    check("bazi range 规范形仍可用", r.status_code == 200,
          f"status={r.status_code}")

    # ── 2. threads limit 口径 ─────────────────────────────────
    for bad in ("0", "-1", "501"):
        r = c.get(f"/api/threads?limit={bad}")
        check(f"threads limit={bad} → 400", r.status_code == 400,
              f"status={r.status_code}")
    r = c.get("/api/threads?limit=5&status=all")
    check("threads limit=5 → 200", r.status_code == 200,
          f"status={r.status_code}")

    # limit>50 真下推：临时建 55 条线程，拉 200 应全回，最后清场。
    _created = []
    try:
        for i in range(55):
            rr = c.post("/api/threads", json={
                "kind": "refusal", "claim": f"r2502-probe-{i}",
                "method": "probe-r2502", "topic": f"r2502-probe-{i}"})
            if rr.status_code == 200:
                _created.append(rr.json().get("thread_id"))
        check("建 55 条线程全部成功", len(_created) == 55,
              f"created={len(_created)}")
        r = c.get("/api/threads?status=all&limit=200")
        _rows = (r.json().get("threads") or []) if r.status_code == 200 else []
        _mine = [t for t in _rows
                 if str(t.get("topic", "")).startswith("r2502-probe-")]
        check("threads limit=200 真返回 >50 行（resume 下推）",
              r.status_code == 200 and len(_mine) >= 55,
              f"status={r.status_code} mine={len(_mine)}")
    finally:
        for _tid in _created:
            c.delete(f"/api/threads/{_tid}")

    # ── 3. search genre 存在性校验 ────────────────────────────
    r = c.get("/api/search", params={"q": "无为", "genre": "不存在的类别"})
    check("search genre=不存在的类别 → 400", r.status_code == 400,
          f"status={r.status_code}")
    # 拿一个真实 genre 验证正例仍 200
    r2 = c.get("/api/stats")
    _genres = []
    if r2.status_code == 200:
        _j = r2.json()
        _genres = ([g["genre"] for g in _j.get("genres", []) if g.get("genre")]
                   or [])
    if _genres:
        r = c.get("/api/search", params={"q": "无为", "genre": _genres[0]})
        check(f"search genre={_genres[0]}（真实类别）→ 200",
              r.status_code == 200, f"status={r.status_code}")
    else:
        check("search genre 正例", True, "stats 无 genre 列表，跳过正例")

    # ── 4. daily 日期规范形 + bday 拒垃圾 ────────────────────
    # R2506（审-F3，取代 R2502「归一化放行」口径）：GET 与 POST 的
    # _iso_canonical 同口径——非规范形（20260101/2026-W01-1）直接 400，
    # 变体根本到不了缓存层，原「不落脏缓存键」不变式以更严方式守住。
    r = c.get("/api/daily?date=20260101")
    check("daily ?date=20260101 → 400（非规范形拒）",
          r.status_code == 400, f"status={r.status_code}")
    r = c.get("/api/daily?date=2026-W01-1")
    check("daily ?date=2026-W01-1 → 400（周历形拒）",
          r.status_code == 400, f"status={r.status_code}")
    r = c.get("/api/daily?bday=garbage")
    check("daily ?bday=garbage → 400", r.status_code == 400,
          f"status={r.status_code}")
    r = c.get("/api/daily?bday=1990-05-06")
    check("daily ?bday 合法 → 200", r.status_code == 200,
          f"status={r.status_code}")

    # ── 5. huangli affair 上限 ────────────────────────────────
    r = c.get("/api/huangli", params={"affair": "搬" * 33})
    check("huangli affair 33 字 → 422", r.status_code == 422,
          f"status={r.status_code}")
    r = c.get("/api/huangli", params={"affair": "搬家", "days": 5})
    check("huangli affair=搬家 → 200", r.status_code == 200,
          f"status={r.status_code}")

    # ── 6. 备份回灌非标量字段不再 5xx ─────────────────────────
    _before = c.get("/api/threads?status=all&limit=500").json()
    _before_n = len(_before.get("threads") or [])
    r = c.post("/api/paipan/history/import", json={
        "records": [],
        "threads": [
            {"topic": "r2502-bad-ev", "opened_at": "x",
             "claims": [{"kind": "note", "claim": "坏证据行",
                         "confidence": {"a": 1},
                         "evidence": [{"work_id": ["x"],
                                       "quote": "q",
                                       "page_anchor": {"p": 1},
                                       "raw_start": 2 ** 70}]}]},
            {"topic": "r2502-good", "opened_at": "x",
             "claims": [{"kind": "note", "claim": "正常行"}]},
        ]})
    check("import 非标量字段 → 非 5xx", r.status_code < 500,
          f"status={r.status_code} body={r.text[:120]}")
    _after = c.get("/api/threads?status=all&limit=500").json()
    _after_rows = {t.get("topic"): t.get("id")
                   for t in (_after.get("threads") or [])}
    check("import 后好线程照常落库",
          "r2502-good" in _after_rows,
          f"topics={[t for t in _after_rows if 'r2502' in str(t)]}")
    # 清场：删掉本次导入写入的线程
    for _tp in ("r2502-bad-ev", "r2502-good"):
        if _tp in _after_rows:
            c.delete(f"/api/threads/{_after_rows[_tp]}")

    # ── 7. BOOKS_WRITE_DISABLE 下 daily 不写缓存 ─────────────
    import sqlite3 as _sq
    _kdb = os.path.join(ROOT, "data", "index", "knowledge.db")
    _probe_date = "2027-06-15"   # 窗内且几乎不可能已有缓存
    with _sq.connect(_kdb) as _db:
        _db.execute("DELETE FROM daily_cache WHERE date=?", (_probe_date,))
        _db.commit()
    os.environ["BOOKS_WRITE_DISABLE"] = "1"
    try:
        r = c.get(f"/api/daily?date={_probe_date}")
        check("write-disable 下 daily 仍 200 照算",
              r.status_code == 200, f"status={r.status_code}")
        with _sq.connect(_kdb) as _db:
            _n = _db.execute(
                "SELECT count(*) FROM daily_cache WHERE date=?",
                (_probe_date,)).fetchone()[0]
        check("write-disable 下 daily 不落 daily_cache", _n == 0,
              f"rows={_n}")
    finally:
        os.environ.pop("BOOKS_WRITE_DISABLE", None)
        with _sq.connect(_kdb) as _db:
            _db.execute("DELETE FROM daily_cache WHERE date=?",
                        (_probe_date,))
            _db.commit()

    # ── 8. _gc_threads coalesce 排序（实例级缩帽）─────────────
    from guji.knowledge import KnowledgeBase
    with tempfile.TemporaryDirectory() as _td:
        _kb = KnowledgeBase(os.path.join(_td, "k.db"))
        try:
            _kb._CAP_THREAD = 3
            _ids = [_kb.open_thread(f"t{i}") for i in range(4)]
            _alive = {r["id"] for r in
                      _kb.db.execute("SELECT id FROM thread").fetchall()}
            check("GC 缩帽后新线程存活、最旧被裁",
                  _ids[-1] in _alive and len(_alive) == 3
                  and _ids[0] not in _alive,
                  f"alive={sorted(_alive)} newest={_ids[-1]}")
            # 旧 bug 的后续症状：新线程被删后 add_turn 撞 FK
            _kb.add_turn(_ids[-1], "user", "hi")
            check("幸存线程 add_turn 不撞 FK", True)
        except Exception as _e:
            check("GC 缩帽验证", False, f"exc={_e!r}")
        finally:
            _kb.close()

    # ── 9. XFF 信任开关 ───────────────────────────────────────
    os.environ["BOOKS_ACCESS_TOKEN"] = "r2502-probe-token"
    try:
        _gapp = create_app()
        _gc = TestClient(_gapp)
        # 默认（无 TRUST_XFF）：轮换 XFF 不换桶——同 client.host 第 11 次 429
        _codes = []
        for i in range(12):
            _codes.append(_gc.post(
                "/_gate", content="key=wrong",
                headers={"x-forwarded-for": f"10.0.0.{i}"}).status_code)
        check("默认不信 XFF——轮换 IP 第 11 次起 429",
              _codes[:10] == [403] * 10 and 429 in _codes[10:],
          f"codes={_codes}")
        # 开 TRUST_XFF：链尾进桶——轮换 XFF 各自新桶永不 429
        os.environ["BOOKS_TRUST_XFF"] = "1"
        _gapp2 = create_app()
        _gc2 = TestClient(_gapp2)
        _codes2 = [_gc2.post(
            "/_gate", content="key=wrong",
            headers={"x-forwarded-for": f"10.1.0.{i}"}).status_code
            for i in range(12)]
        check("TRUST_XFF=1 时链尾进桶（各自新桶不 429）",
              _codes2 == [403] * 12, f"codes={_codes2}")
    finally:
        os.environ.pop("BOOKS_ACCESS_TOKEN", None)
        os.environ.pop("BOOKS_TRUST_XFF", None)

    # ── 汇总 ──────────────────────────────────────────────────
    _fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 50}\n{len(RESULTS)} checks, "
          f"{len(_fails)} failed")
    return 1 if _fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"probe 自身出错：{e!r}")
        sys.exit(2)
