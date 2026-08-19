"""history — 查询历史记录库（用户问了什么 + 项目回复了什么）。

用户需求（2026-08-15）：记录每次排盘查询的完整往返——输入参数、排盘、
运算事实、古籍引文、LLM 大白话解读（含模型），前端可回看历史。

红线变更（用户显式授权，见 docs/DECISIONS.md D-039）：
  * 原红线"LLM 解读不落库"针对 corpus.db/knowledge.db 的语料/知识库——
    生成文本不进语料库、不污染检索。本次授权把每次查询的完整往返
    写入**独立的历史库 data/history.db**，与语料/知识库物理隔离，
    不参与检索，13 道闸门不受影响。
  * 存储即用户要求的产品功能（历史记录），非缓存。
  * R178b（D-226b）：LLM 层已整体移除，落库内容改为 `guji.interpreter` 的
    确定性输出（规则转述，非生成文本）。列名不变，见下方表结构注释。

表结构（bazi_history）：
  id           自增主键
  created_at   查询时间 ISO8601
  input_json   请求参数（year/month/day/hour/gender/question/ask_date/
               ask_hour/location）
  paipan_json  排盘（render/nayin/warn）
  calc_json    运算事实（ten_gods/five_elements/relations/day_luck/summary）
  evidence_json 古籍引文列表（带出处）
  llm_json     解读输出。**列名保留做向后兼容**（R178b，D-226b）：LLM 生成式
               解读层已移除，本列现在写 `guji.interpreter` 的确定性输出
               {"ok":bool,"kind":"rule-based","engine":str,"sections":[...],
                "citations":[...],"text":str,"basis":[...],"disclaimer":str}。
               旧记录仍是 {"ok","text","model"} 形状，读取端两种都要能处理
               ——不改列名是为了不动已有历史记录（实测 51 行，max id 826）。
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
            # 列名与键名保留做向后兼容（R178b/D-226b：写入内容已从 LLM 生成
            # 文本换成 guji.interpreter 确定性输出，`model` 键换成 `engine`）。
            # 旧记录读 model，新记录读 engine——同一列两种历史内容都能展示。
            "llm_ok": bool(llm.get("ok")),
            "llm_model": (llm.get("model") or llm.get("engine")
                          if llm.get("ok") else None),
            "engine": llm.get("engine"),
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
    #
    # R178b 修正（宪法第一条：跑不出来就当它是错的）：原自检最后一行是
    # `assert count() == 0`，那假设**真实历史库是空的**——库里现有 51 条
    # 用户记录，这条断言从写下起就必然失败，等于这个自检从来没被跑过。
    # 改为断言「写入前后计数守恒」：写 N 条、删 N 条，count 回到基线。
    base_count = count()
    rid = save_record(
        {"year": 1990, "month": 5, "day": 15, "hour": 10, "gender": "男",
         "question": "测试", "ask_date": "2026-08-15", "ask_hour": 14},
        {"render": "庚午年 丁亥月 庚辰日 辛巳时　日主：庚　大运：顺",
         "nayin": ["路旁土"], "warn": []},
        {"summary": "test-summary", "ten_gods": []},
        [{"work_id": "KR3g0048", "text": "…"}],
        {"ok": True, "kind": "rule-based", "text": "## 排盘坐标\n- 测试",
         "engine": "guji.interpreter/1.0（确定性规则，无 LLM）"},
    )
    assert rid > 0
    lst = list_records()
    assert lst and lst[0]["id"] == rid and lst[0]["question"] == "测试"
    # 新形状（engine 键）经 list_records 后落在向后兼容的 llm_model 字段上
    assert lst[0]["llm_model"] == "guji.interpreter/1.0（确定性规则，无 LLM）"
    rec = get_record(rid)
    assert rec and rec["llm"]["ok"] and rec["calc"]["summary"] == "test-summary"
    assert rec["paipan"]["render"].startswith("庚午年")
    assert delete_record(rid) is True
    # 旧形状（model 键）仍须可读——库里既有历史记录是这个形状（R178b）
    rid2 = save_record({"question": "旧形状"}, {"render": "x"}, {}, [],
                       {"ok": True, "text": "t", "model": "legacy-model"})
    old = [r for r in list_records() if r["id"] == rid2]
    assert old and old[0]["llm_model"] == "legacy-model", old
    assert delete_record(rid2) is True
    # 计数守恒：本次写 2 条、删 2 条，回到基线（不假设库为空）
    assert count() == base_count, (count(), base_count)
    print(f"history.py 自检 OK（新 engine 形状 + 旧 model 形状均可读；"
          f"计数守恒 {base_count}）")
