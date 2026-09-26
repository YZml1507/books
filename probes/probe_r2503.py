"""probes/probe_r2503.py — R2503 批次修复回归闸。

钉扎本轮三条修复（TestClient 直测，离线不打 LLM）：

 1. 备份回灌容器级畸形：threads[].turns / threads[].claims 不是 list
    （塞 42 / {"a":1} / "abc"）→ 此前切片 TypeError 穿透成裸 500 且
    thread 行已插一半；现按空容器收敛，好线程照常落库。
 2. _access_gate 的 ?key= 直通与 POST /_gate 同桶限速：GET 旁路
    不再架空 10 次/60s/IP 爆破防线（302/403 oracle 有成本）；
    混合打满 10 次后第 11 次 429。
 3. （V-01 视觉回归由 probe_ui_smoke 的 ui.fab.mobile_right 钉扎——
     .recent-toggle 窄屏规则曾误置 @media print 内从未生效。）

退出码：0 全绿；1 有 FAIL；2 probe 自身出错。
"""
from __future__ import annotations

import os
import sys

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

    # ── 1. 备份回灌容器级畸形不再 500 ─────────────────────────
    app = create_app()
    c = TestClient(app)
    r = c.post("/api/paipan/history/import", json={
        "records": [],
        "threads": [
            {"topic": "r2503-turns-int", "opened_at": "x", "turns": 42},
            {"topic": "r2503-turns-dict", "opened_at": "x",
             "turns": {"a": 1}},
            {"topic": "r2503-claims-int", "opened_at": "x", "claims": 7},
            {"topic": "r2503-claims-dict", "opened_at": "x",
             "claims": {"a": 1}},
            {"topic": "r2503-good", "opened_at": "x",
             "turns": [{"role": "user", "text": "hi"}],
             "claims": [{"kind": "note", "claim": "正常行"}]},
        ]})
    check("import 容器畸形 → 非 5xx", r.status_code < 500,
          f"status={r.status_code} body={r.text[:120]}")
    _after = c.get("/api/threads?status=all&limit=500").json()
    _rows = {t.get("topic"): t.get("id")
             for t in (_after.get("threads") or [])}
    check("畸形容器线程按空收敛落库", "r2503-turns-int" in _rows,
          f"topics={[t for t in _rows if 'r2503' in str(t)]}")
    check("混批好线程照常落库", "r2503-good" in _rows)
    # 好线程的 turns 真落了一条（readback 验证非空容器正常）
    if "r2503-good" in _rows:
        r2 = c.get(f"/api/threads/{_rows['r2503-good']}")
        _turns = (r2.json().get("turns") or []) if r2.status_code == 200 else []
        check("好线程 turns readback ≥1", len(_turns) >= 1,
              f"turns={len(_turns)}")
    for _tp, _id in _rows.items():
        if _tp and str(_tp).startswith("r2503-"):
            c.delete(f"/api/threads/{_id}")

    # ── 2. ?key= 与 /_gate 同桶限速 ───────────────────────────
    os.environ["BOOKS_ACCESS_TOKEN"] = "r2503-probe-token"
    try:
        _gc = TestClient(create_app())
        # GET ?key=wrong 每 IP 10 次/60s——第 11 次起 429（此前永不 429）
        _codes = [_gc.get("/", params={"key": f"guess{i}"}).status_code
                  for i in range(12)]
        check("?key=wrong 第 11 次起 429",
              _codes[:10] == [403] * 10 and 429 in _codes[10:],
              f"codes={_codes}")
        # 混合桶：5 次 GET + 5 次 POST 打满后 GET 也 429
        _g2 = TestClient(create_app())
        for i in range(5):
            _g2.get("/", params={"key": f"g{i}"})
        for i in range(5):
            _g2.post("/_gate", content="key=wrong")
        _c11 = _g2.get("/", params={"key": "again"}).status_code
        check("GET+POST 同桶——混合 10 次后 ?key= 也 429",
              _c11 == 429, f"code={_c11}")
        # 正例：限速内 ?key= 对口令仍 302 + 写 Cookie
        _g3 = TestClient(create_app())
        _r3 = _g3.get("/", params={"key": "r2503-probe-token"},
                      follow_redirects=False)
        check("限速内 ?key= 对口令仍 302 设 Cookie",
              _r3.status_code == 302
              and "books_key" in (_r3.headers.get("set-cookie") or ""),
              f"status={_r3.status_code}")
        # 对口令首尝即 302 并落 Cookie；之后请求带有效 Cookie 走
        # good 短路（不再扣桶也不再验 key）——契约：只有未认证尝试扣桶。
        _g4 = TestClient(create_app())
        _codes4 = [_g4.get("/", params={"key": "r2503-probe-token"},
                           follow_redirects=False).status_code
                   for _i in range(3)]
        check("对口令 302 后凭 Cookie 直通行（good 短路不耗桶）",
              _codes4 == [302, 200, 200], f"codes={_codes4}")
    finally:
        os.environ.pop("BOOKS_ACCESS_TOKEN", None)

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
