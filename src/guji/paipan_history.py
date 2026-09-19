# -*- coding: utf-8 -*-
"""guji/paipan_history.py — 排盘历史台账（2026-08-28 新增，独立轻量库）。

背景：R219b 曾整体删除「我的解读」历史（用户裁决：不记录、费内存）。
本次按当前用户需求以**独立新库**重建排盘台账，与旧 history.db（遗留存档，
已停用）物理隔离，命名全部带 paipan_ 前缀，互不影响。

设计约束（.cluster/plan.md C1）：
  * 写入绝不影响 /api/bazi 主响应：后台线程 + 静默失败（log 即可）；
  * BOOKS_PAIPAN_HISTORY_DISABLE=1 时整体关闭（不写不查）；
  * 每操作短连接（sqlite3 默认线程隔离，免锁烦恼）；
  * 算法层零依赖：本模块只认识 dict / json 字符串。
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
from datetime import datetime

# PyInstaller frozen 兼容：data/ 在 exe 同目录（与 web/deps.py 口径一致）
if getattr(__import__("sys"), "frozen", False):
    _ROOT = os.path.dirname(__import__("sys").executable)
else:
    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_ROOT, "data", "paipan_history.db")

_log_lock = threading.Lock()


def _log(msg: str) -> None:
    """轻量日志（复用 logs/ 目录，失败静默）。"""
    try:
        with _log_lock:
            log_path = os.path.join(_ROOT, "logs", "paipan_history.log")
            # R228j：原 makedirs 建的是 data/ 而 open 的是 logs/——fresh clone
            # 无 logs/ 时 open 抛错被吞，日志从未落盘（打包启动路径的
            # web_launcher.py 恰好先建了 logs/ 才掩盖此 bug）。
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def disabled() -> bool:
    return os.getenv("BOOKS_PAIPAN_HISTORY_DISABLE", "") in ("1", "on", "true", "yes")


_ddl_done = False
_ddl_lock = threading.Lock()
_write_lock = threading.Lock()   # R228b：串行化写入，削并发写锁竞争
KEEP_MAX = 500                   # R228j：排盘历史滚动上限


def _conn() -> sqlite3.Connection:
    global _ddl_done
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")   # R228b：写锁等待而非秒抛
    # R228b：DDL 每次连接都跑是无谓开销——模块级 once 即可（IF NOT EXISTS
    # 本身幂等，并发下用锁保证只执行一次）。
    if not _ddl_done:
        with _ddl_lock:
            if not _ddl_done:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS records(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        name TEXT,
                        question TEXT,
                        req_json TEXT NOT NULL,
                        result_json TEXT NOT NULL)""")
                _ddl_done = True
    return conn


def _name_summary(req: dict) -> str:
    """人话摘要：「1990-05-15 午时 女」；农历输入标注「农历」。

    前端契约：hour 缺失/非法时显示「时辰未知」；农历带 (农历) 后缀，
    闰月再补「闰X月」。
    """
    try:
        hour = int(req.get("hour"))
        hour = hour if 0 <= hour <= 23 else None
    except (TypeError, ValueError):
        hour = None
    _SC = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")
    shichen = f"{_SC[(hour + 1) // 2 % 12]}时" if hour is not None else "时辰未知"
    cal = f"（农历{'闰' if req.get('lunar_leap') else ''}）" \
        if req.get("calendar_type") == "lunar" else ""
    gender = "男" if req.get("gender") == "男" else "女"
    return f"{req.get('year')}-{req.get('month'):02d}-{req.get('day'):02d} {shichen} {gender}{cal}"


def save_async(req_dict: dict, result_dict: dict) -> None:
    """排盘成功后异步落一条记录。永不抛错、永不阻塞调用方。"""
    if disabled():
        return

    def _work():
        try:
            row_req = json.dumps(req_dict, ensure_ascii=False)
            row_res = json.dumps(result_dict, ensure_ascii=False)
            name = _name_summary(req_dict)
            question = (req_dict.get("question") or None)
            ts = datetime.now().isoformat(timespec="seconds")
            # closing() 只负责关连接，无隐式 commit——写路径用 `with c:`
            # 保住原 `with _conn()` 的提交语义（R228b 重构注意点）。
            with _write_lock, contextlib.closing(_conn()) as c, c:
                c.execute(
                    "INSERT INTO records(ts,name,question,req_json,result_json)"
                    " VALUES(?,?,?,?,?)",
                    (ts, name, question, row_req, row_res))
                # R228j：滚动裁剪——单行 ~50KB，不裁剪用户每排一次盘就永久
                # +1 行（实测 31 次→3.7MB），列表/导出全量 fetchall 越滚越慢。
                c.execute(
                    "DELETE FROM records WHERE id NOT IN "
                    "(SELECT id FROM records ORDER BY id DESC LIMIT ?)",
                    (KEEP_MAX,))
        except Exception as exc:  # noqa: BLE001 — 台账绝不拖垮排盘
            _log(f"save failed: {type(exc).__name__}: {exc}")

    threading.Thread(target=_work, daemon=True,
                     name="paipan-history-save").start()


def list_records(limit: int = 20, offset: int = 0) -> dict:
    """分页列表（id 倒序=最新在前）。返回前端契约结构。"""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    with contextlib.closing(_conn()) as c:
        total = c.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        rows = c.execute(
            "SELECT id,ts,name,question,req_json,result_json FROM records"
            " ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    items = []
    for rid, ts, name, question, req_json, res_json in rows:
        try:
            result = json.loads(res_json)
        except ValueError:
            result = {}
        # R228j：req_json 护栏——原实现只包 res_json，一行坏 req_json
        # 就让整页 500 且没有删除该行的前端路径（删行要先列出）。
        try:
            req_obj = json.loads(req_json) if req_json else {}
        except ValueError:
            req_obj = {}
        paipan = result.get("paipan") or {}
        calc = result.get("calc") or {}
        items.append({
            "id": rid, "ts": ts, "name": name,
            "question": question,
            "req": req_obj,
            "result_summary": {
                "paipan_render": paipan.get("render"),
                "five_elements": (calc.get("five_elements") or {}).get("counts"),
            },
        })
    return {"total": total, "items": items}


def get_record(rid: int) -> dict | None:
    """单条完整记录；不存在返回 None（路由层转 404）。"""
    with contextlib.closing(_conn()) as c:
        row = c.execute(
            "SELECT id,ts,name,question,req_json,result_json FROM records"
            " WHERE id=?", (int(rid),)).fetchone()
    if row is None:
        return None
    rid, ts, name, question, req_json, res_json = row
    try:
        req_obj = json.loads(req_json) if req_json else {}
    except ValueError:
        req_obj = {}                    # R228j：同 list_records 的护栏
    try:
        res_obj = json.loads(res_json) if res_json else {}
    except ValueError:
        res_obj = {}
    return {"id": rid, "ts": ts, "name": name, "question": question,
            "req": req_obj, "result": res_obj}


def delete_record(rid: int) -> bool:
    """删除单条；返回是否存在。"""
    with contextlib.closing(_conn()) as c, c:
        cur = c.execute("DELETE FROM records WHERE id=?", (int(rid),))
        return cur.rowcount > 0


def export_rows() -> list[tuple]:
    """CSV 导出数据行：(id, ts, name, question, paipan_render)。"""
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT id,ts,name,question,result_json FROM records"
            " ORDER BY id DESC").fetchall()
    out = []
    for rid, ts, name, question, res_json in rows:
        try:
            render = ((json.loads(res_json) or {}).get("paipan") or {}).get("render") or ""
        except ValueError:
            render = ""
        out.append((rid, ts, name or "", question or "", render))
    return out
