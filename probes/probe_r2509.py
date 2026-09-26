"""probe_r2509 — R2509 钉扎。

覆盖：
1. CSP 安全头在 HTML/API/413 三通道都存在且含关键指令
2. probe_contract 的 /api/threads 列表 fixture 自愈（先建线程再 GET）
3. CSP 不破真实页面（inline script/onerror/style= 仍放行——
   真浏览器验证在 ui_smoke，此处只钉服务端契约）
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("BOOKS_LLM_DISABLE", "1")

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


# ── 1. CSP 头契约 ────────────────────────────────────────────
from fastapi.testclient import TestClient
from web.app import create_app

client = TestClient(create_app())

r = client.get("/")
csp = r.headers.get("content-security-policy", "")
ok("csp.首页存在", "default-src 'self'" in csp, csp[:80])
ok("csp.connect封闭", "connect-src 'self'" in csp)
ok("csp.object禁", "object-src 'none'" in csp)
ok("csp.base_uri", "base-uri 'self'" in csp)
ok("csp.frame_ancestors", "frame-ancestors 'none'" in csp)
ok("csp.img_data", "data:" in csp and "img-src" in csp)

r = client.get("/api/daily")
ok("csp.api响应", "default-src 'self'" in
   r.headers.get("content-security-policy", ""))

r = client.get("/static/app.js")
ok("csp.静态响应", "default-src 'self'" in
   r.headers.get("content-security-policy", ""))

# 413 通道（本中间件在 _security_headers 外侧，需就地补齐——R2508 先例）
r = client.post("/api/bazi", content=b"x" * (513 * 1024),
                headers={"Content-Type": "application/json"})
ok("csp.413补齐", "default-src 'self'" in
   r.headers.get("content-security-policy", "")
   and r.status_code == 413, str(r.status_code))

# ── 2. 太阳星座边界（自测发现：11/22 应为天蝎非射手）────────
sys.path.insert(0, os.path.join(ROOT, "src"))
from guji.xingzuo import sun_sign
_BOUNDARY = {(11, 21): "天蝎", (11, 22): "天蝎", (11, 23): "射手",
             (10, 23): "天秤", (10, 24): "天蝎", (12, 21): "射手",
             (12, 22): "摩羯"}
for (m, d), want in _BOUNDARY.items():
    got = sun_sign(m, d)
    ok(f"sun_sign.{m}/{d}", got == want, f"{got} != {want}")

# ── 3. calc_range 闭区间上限（审-P3：31 天差曾吐 32 条）───────
from guji.bazi import compute as _bz_compute
from guji.bazi_calc import calc_range as _cr
_b = _bz_compute(1990, 5, 15, 10, "男")
ok("range.30天差→31条", len(_cr(_b, "2026-01-01", "2026-01-31")["days"]) == 31)
try:
    _cr(_b, "2026-01-01", "2026-02-01")
    ok("range.31天差拒", False)
except ValueError:
    ok("range.31天差拒", True)

# ── 4. contract fixture 自愈钉扎（源码级）────────────────────
src = open(os.path.join(ROOT, "probes", "probe_contract.py"),
           encoding="utf-8").read()
m = re.search(r'url_real == "/api/threads".{0,200}fetch\("POST /api/threads"\)',
              src, re.S)
ok("contract.threads自愈", m is not None)

# 直验证 GET /api/threads 在空库也能通过 fixture 造出非空列表：
# 直接用 TestClient 复现探针的两步——POST 建线程 → GET 列表非空
r = client.post("/api/threads", json={
    "kind": "refusal", "claim": "r2509 钉扎", "method": "probe_r2509",
    "topic": "r2509 钉扎线程",
    "evidence": [{"work_id": "KR1a0001", "file": "KR1a0001_001.txt",
                  "quote": "潛龍勿用", "scheme": "zhouyi",
                  "addr1": 1, "addr2": "初九", "role": "supports"}]})
_j = r.json() if r.status_code == 200 else {}
tid, did = _j.get("thread_id"), _j.get("derived_id")
ok("threads.建钉扎线程", tid is not None, f"{r.status_code}")
r = client.get("/api/threads")
lst = (r.json() or {}).get("threads") or []
ok("threads.列表非空", any(t.get("id") == tid for t in lst),
   f"n={len(lst)}")
# 清理：按回包 id 精删本行（不按 thread_id 横扫——rowid 复用会误伤
# 旧线程名下的残留 derived，R2508 孤儿问题的镜像）。全链同
# probe_contract：evidence→derived→turn→thread。
if tid is not None:
    import sqlite3
    kb = os.path.join(ROOT, "data", "index", "knowledge.db")
    con = sqlite3.connect(kb)
    if did is not None:
        con.execute("DELETE FROM evidence WHERE derived_id=?", (did,))
        con.execute("DELETE FROM derived WHERE id=?", (did,))
    con.execute("DELETE FROM turn WHERE thread_id=?", (tid,))
    con.execute("DELETE FROM thread WHERE id=?", (tid,))
    con.commit()
    con.close()

print("=" * 50)
print(f"{len(PASS) + len(FAIL)} checks, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
