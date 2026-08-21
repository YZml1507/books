"""probe_r131a_relevance.py — R131a-01 的可复验闸门（R190b 建）。

R131a-01「提问对检索零影响」由 R189b 声称修复（TOPIC_QUERIES 主题词追加式）。
宪法第一条：任何状态断言必须附一条能复现它的命令。本探针就是那条命令。

三条判据（全部成立才退出 0）：

  判据 A 引文分化：N 个不同主题的提问 → 至少 N 种不同的 evidence 集合。
                   阳性对照方向：若检索无视提问，集合数恒为 1。
  判据 B 无提问不变：不传 question 时 topic_queries(None) == []，且两次调用
                   evidence 逐字节相等。这条保护「旧行为零回归」——
                   R189b 的核心承诺。
  判据 C 主题词真的生效：带提问时 evidence 的 why 字段出现「提问主题」，
                   证明主题词进了检索队列而不是只改了文案。

自带 --self-check 阳性对照：把 topic_queries 打桩成恒返回 []（模拟「检索无视
提问」的回归），三条判据必须至少一条 FAIL——否则本探针是个永远返回 0 的
假闸门（宪法第四条 U-08 教训）。

用法：
    <py> probes\\probe_r131a_relevance.py
    <py> probes\\probe_r131a_relevance.py --self-check
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")     # 闸门环境禁 LLM（D-245a）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = {"year": 1998, "month": 7, "day": 20, "hour": 14,
        "gender": "女", "ask_date": "2026-08-20"}
QUESTIONS = ["感情运怎么样？", "事业运怎么样？", "学业运怎么样？",
             "财运怎么样？", "健康要注意什么？"]


def _sig(evidence: list[dict]) -> str:
    payload = [(e.get("work_id"), e.get("title"), e.get("text", "")[:40])
               for e in evidence]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def main(self_check: bool = False) -> int:
    from fastapi.testclient import TestClient
    from web.app import app
    from guji import bazi_lookup

    if self_check:                                   # 阳性对照：注入回归
        bazi_lookup.topic_queries = lambda q: []     # type: ignore[assignment]

    client = TestClient(app)
    import web.services as _svc                      # noqa: F401  (确保已加载)

    # ---- 判据 A：引文分化 -------------------------------------------------
    sigs: dict[str, list[str]] = {}
    for q in QUESTIONS:
        ev = client.post("/api/bazi", json=dict(BASE, question=q)).json()["evidence"]
        sigs.setdefault(_sig(ev), []).append(q)
    n_sets = len(sigs)
    a_ok = n_sets >= len(QUESTIONS)
    print(f"判据 A 引文分化：{len(QUESTIONS)} 个提问 → {n_sets} 种引文集合　"
          f"阈值 = {len(QUESTIONS)}　{'PASS' if a_ok else 'FAIL'}")
    for sig, qs in sigs.items():
        print(f"    {sig[:12]}  ← {'、'.join(qs)}")

    # ---- 判据 B：无提问逐字节不变 ----------------------------------------
    tq_none = bazi_lookup.topic_queries(None)
    e1 = client.post("/api/bazi", json=dict(BASE)).json()["evidence"]
    e2 = client.post("/api/bazi", json=dict(BASE)).json()["evidence"]
    b_ok = (not tq_none) and _sig(e1) == _sig(e2)
    print(f"判据 B 无提问不变：topic_queries(None)={tq_none}　"
          f"两次调用 sha 相等={_sig(e1) == _sig(e2)}　{'PASS' if b_ok else 'FAIL'}")

    # ---- 判据 C：主题词真的进检索 ----------------------------------------
    ev = client.post("/api/bazi",
                     json=dict(BASE, question="感情运怎么样？")).json()["evidence"]
    whys = [e.get("why", "") for e in ev]
    hits = sum(1 for w in whys if "提问主题" in w)
    c_ok = hits > 0
    print(f"判据 C 主题词生效：why 含「提问主题」= {hits}/{len(ev)} 段　"
          f"why 取值域={sorted(set(whys))}　{'PASS' if c_ok else 'FAIL'}")

    ok = a_ok and b_ok and c_ok
    print()
    if self_check:
        if ok:
            print("probe_r131a_relevance --self-check FAIL: "
                  "注入「检索无视提问」的回归后三条判据仍全绿——本探针是假闸门")
            return 1
        print("probe_r131a_relevance --self-check PASS: 阳性对照被抓到")
        return 0
    if not ok:
        print("probe_r131a_relevance FAIL: R131a-01 未真正修复")
        return 1
    print("probe_r131a_relevance PASS: 引文随提问分化、无提问零回归、主题词进检索")
    return 0


if __name__ == "__main__":
    sys.exit(main("--self-check" in sys.argv))
