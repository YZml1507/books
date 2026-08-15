"""history — 查询历史记录库（用户问了什么 + 项目回复了什么）。

用户需求（2026-08-15）：记录每次排盘查询的完整往返——输入参数、排盘、
运算事实、古籍引文、LLM 大白话解读（含模型），前端可回看历史。

红线变更（用户显式授权，见 docs/DECISIONS.md D-039）：
  * 原红线"LLM 解读不落库"针对 corpus.db/knowledge.db 的语料/知识库——
    生成文本不进语料库、不污染检索。本次授权把每次查询的完整往返
    （含 LLM 输出）写入**独立的历史库 data/history.db**，与语料/知识库
    物理隔离，不参与检索，13 道闸门不受影响。
  * 存储即用户要求的产品功能（历史记录），非缓存；LLM 输出仍标注生成来源。

表结构（bazi_history）：
  id           自增主键
  created_at   查询时间 ISO8601
  input_json   请求参数（year/month/day/hour/gender/question/ask_date/
               ask_hour/location）
  paipan_json  排盘（render/nayin/warn）
  calc_json    运算事实（ten_gods/five_elements/relations/day_luck/summary）
  evidence_json 古籍引文列表（带出处）
  llm_json     {"ok":bool,"text":str,"model":str}
  question     摘要列（便于列表展示，冗余自 input_json）

纯标准库 sqlite3，零新依赖。只读/写独立 db，与语料索引隔离。
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "history.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bazi_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    question       TEXT DEFAULT '',
    input_json     TEXT NOT NULL,
    paipan_json    TEXT NOT NULL,
    calc_json      TEXT NOT NULL,
    evidence_json  TEXT NOT NULL,
    llm_json       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created ON bazi_history(created_at DESC);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)   # executescript 支持多条语句
    return conn


def save_record(input_: dict, paipan: dict, calc: dict,
                evidence: list, llm: dict) -> int:
    """写入一条完整查询记录，返回新 id。

    input_: 请求参数 dict；paipan/calc/evidence/llm 与 /api/bazi 响应字段一致。
    """
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    q = (input_.get("question") or "").strip()
    with closing(_conn()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO bazi_history (created_at, question, input_json, "
            "paipan_json, calc_json, evidence_json, llm_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (now, q,
             json.dumps(input_, ensure_ascii=False),
             json.dumps(paipan, ensure_ascii=False),
             json.dumps(calc, ensure_ascii=False),
             json.dumps(evidence, ensure_ascii=False),
             json.dumps(llm, ensure_ascii=False)),
        )
        return int(cur.lastrowid)


def list_records(limit: int = 50) -> list[dict]:
    """历史列表（轻量：不带 evidence/llm 全文，便于前端列表展示）。"""
    with closing(_conn()) as conn:
        rows = conn.execute(
            "SELECT id, created_at, question, paipan_json, llm_json "
            "FROM bazi_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        try:
            paipan = json.loads(r["paipan_json"])
            llm = json.loads(r["llm_json"])
        except (json.JSONDecodeError, TypeError):
            paipan, llm = {}, {}
        out.append({
            "id": r["id"],
            "created_at": r["created_at"],
            "question": r["question"],
            "paipan_render": paipan.get("render", ""),
            "llm_ok": bool(llm.get("ok")),
            "llm_model": llm.get("model") if llm.get("ok") else None,
        })
    return out


def get_record(rid: int) -> dict | None:
    """单条完整记录（含 calc/evidence/llm 全文），不存在返回 None。"""
    with closing(_conn()) as conn:
        r = conn.execute(
            "SELECT * FROM bazi_history WHERE id=?", (rid,)).fetchone()
    if r is None:
        return None

    def _j(s: str):
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return {}

    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "question": r["question"],
        "input": _j(r["input_json"]),
        "paipan": _j(r["paipan_json"]),
        "calc": _j(r["calc_json"]),
        "evidence": _j(r["evidence_json"]),
        "llm": _j(r["llm_json"]),
    }


def delete_record(rid: int) -> bool:
    """删除一条记录，返回是否真的删掉。"""
    with closing(_conn()) as conn, conn:
        cur = conn.execute("DELETE FROM bazi_history WHERE id=?", (rid,))
        return cur.rowcount > 0


def count() -> int:
    with closing(_conn()) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM bazi_history").fetchone()["n"]


if __name__ == "__main__":
    # 自检：写入 -> 列表 -> 详情 -> 删除 -> 计数
    rid = save_record(
        {"year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
         "question": "测试", "ask_date": "2026-08-15", "ask_hour": 14},
        {"render": "庚午年 丁亥月 庚辰日 辛巳时　日主：庚　大运：顺",
         "nayin": ["路旁土"], "warn": []},
        {"summary": "test-summary", "ten_gods": []},
        [{"work_id": "KR3g0048", "text": "…"}],
        {"ok": True, "text": "## 结论\n测试", "model": "test-model"},
    )
    assert rid > 0
    lst = list_records()
    assert lst and lst[0]["id"] == rid and lst[0]["question"] == "测试"
    rec = get_record(rid)
    assert rec and rec["llm"]["ok"] and rec["calc"]["summary"] == "test-summary"
    assert rec["paipan"]["render"].startswith("庚午年")
    assert delete_record(rid) is True
    assert count() == 0
    print("history.py 自检 OK")
