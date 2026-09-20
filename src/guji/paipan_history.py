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
import glob
import json
import os
import sqlite3
import threading
from datetime import datetime

# PyInstaller frozen 兼容：与 web/deps.py 同口径——先查 exe 父目录有无
# data/index（data/ 在项目根的标准摆放），找不到才退 exe 同目录。
# R230n（R26-P3）：此前本模块只认 exe 同目录，和 deps 的父目录探测
# 分叉——同一 exe 会出现两套 data 根。
if getattr(__import__("sys"), "frozen", False):
    _exe_dir = os.path.dirname(__import__("sys").executable)
    _parent = os.path.dirname(_exe_dir)
    _ROOT = (_parent if os.path.isdir(os.path.join(_parent, "data", "index"))
             else _exe_dir)
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
            # R229n（R6-#10）：追加写无轮转会长成无底洞——超 256KB 只留
            # 尾部 64KB（低频写路径，简单截断即可，不引 RotatingFileHandler）。
            try:
                if (os.path.exists(log_path)
                        and os.path.getsize(log_path) > 256 * 1024):
                    with open(log_path, "rb") as fr:
                        fr.seek(-64 * 1024, os.SEEK_END)
                        tail = fr.read()
                    with open(log_path, "wb") as fw:
                        fw.write(tail)
            except OSError:
                pass
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def disabled() -> bool:
    return os.getenv("BOOKS_PAIPAN_HISTORY_DISABLE", "") in ("1", "on", "true", "yes")


_ddl_lock = threading.Lock()
_write_lock = threading.Lock()   # R228b：串行化写入，削并发写锁竞争
KEEP_MAX = 500                   # R228j：排盘历史滚动上限


_DDL = """CREATE TABLE IF NOT EXISTS records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    name TEXT,
    question TEXT,
    req_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'bazi')"""


def _quarantine() -> None:
    """R228l：db 损坏自恢复——把坏文件挪到 .corrupt-<ts> 留档，
    下次连接开新库。功能降级为空历史，而不是永久 500。

    R230i（R21-P2-2）：时间戳带毫秒防同秒两次事件互相覆盖；留档
    只留最新 5 份，不无限攒。"""
    if not os.path.exists(DB_PATH):
        return
    qua = (DB_PATH + ".corrupt-" +
           datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:21])
    # R230t（R31-P2-8）：exists 之后 replace 之前文件被别处挪走是真实
    # 竞态——FileNotFoundError 不该冒成 500，直接让第二轮开新库。
    try:
        os.replace(DB_PATH, qua)
    except FileNotFoundError:
        return
    _log("WARN paipan_history db 损坏，已挪至 %s" % qua)
    try:
        olds = sorted(glob.glob(DB_PATH + ".corrupt-*"))
        for f in olds[:-5]:
            os.remove(f)
    except Exception:
        pass


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    for attempt in range(2):
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("PRAGMA busy_timeout=5000")  # R228b：写锁等待而非秒抛
            # R230t（R31-P2-7）：WAL——排盘页与历史页并发读写不再互斥；
            # 与 knowledge.db 同纪律。只读文件上写 PRAGMA 会抛——降级继续。
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            # 轻量完整性探针：connect 成功不代表页可解析，真读一行才暴露损坏
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
            # R230i（R21-P1-5）：运行中被换成「合法但无 records 的库」
            # 时 _ddl_done .once 缓存让全端点永久 503——每次连接验表存在，
            # 缺表当场补建；也顺带吞掉「老库缺列」漂移（ensure 补列）。
            has = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='records'").fetchone()
            if not has:
                with _ddl_lock:
                    conn.execute(_DDL)
                    conn.commit()
            _ensure_columns(conn)
            return conn
        except sqlite3.OperationalError:
            # R230i（R21-P0-3）：「database is locked」/只读是
            # OperationalError 不是损坏——此前被 DatabaseError 粗粒度
            # 当成坏库把 917KB 真库挪成 .corrupt-*。锁冒成 503 就好，
            # 不许搬库。
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            raise
        except sqlite3.DatabaseError:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            if attempt == 0:
                _quarantine()   # 损坏文件挪走，第二轮开新库
            else:
                raise
    raise AssertionError("unreachable")


# R230i（R21-P0-1 同款）：老库缺列自愈——pre-git 版本的 records 可能
# 缺后加的列；PRAGMA table_info 查缺失、ALTER TABLE ADD COLUMN 补上。
_RECORDS_COLS = {
    "ts": "TEXT NOT NULL DEFAULT ''",
    "name": "TEXT",
    "question": "TEXT",
    "req_json": "TEXT NOT NULL DEFAULT '{}'",
    "result_json": "TEXT NOT NULL DEFAULT '{}'",
    # R230z（R36-P1-1）：品类列——历史台账不再只收八字。桃花/合婚/塔罗/
    # 六爻/起名同写一张表，老库经 _ensure_columns 补列（默认 'bazi'，存量
    # 行语义正确，无需回填）。
    "type": "TEXT NOT NULL DEFAULT 'bazi'",
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    have = {r[1] for r in conn.execute("PRAGMA table_info(records)")}
    for col, ddl in _RECORDS_COLS.items():
        if col not in have:
            conn.execute(
                f"ALTER TABLE records ADD COLUMN {col} {ddl}")
    conn.commit()


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


def save_async(req_dict: dict, result_dict: dict, rtype: str = "bazi",
               name: str | None = None) -> None:
    """排盘成功后异步落一条记录。永不抛错、永不阻塞调用方。

    R230z（R36-P1-1）：rtype 标记品类（bazi/taohua/hehun/tarot/liuyao/
    qiming），name 允许调用方覆盖摘要（合婚双人/塔罗张数等非生辰形）。"""
    if disabled():
        return

    def _work():
        try:
            row_req = json.dumps(req_dict, ensure_ascii=False)
            row_res = json.dumps(result_dict, ensure_ascii=False)
            row_name = name if name else _name_summary(req_dict)
            question = (req_dict.get("question") or None)
            ts = datetime.now().isoformat(timespec="seconds")
            # closing() 只负责关连接，无隐式 commit——写路径用 `with c:`
            # 保住原 `with _conn()` 的提交语义（R228b 重构注意点）。
            with _write_lock, contextlib.closing(_conn()) as c, c:
                c.execute(
                    "INSERT INTO records(ts,name,question,req_json,result_json,"
                    "type) VALUES(?,?,?,?,?,?)",
                    (ts, row_name, question, row_req, row_res, rtype))
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
        # R229z续10（R8 P2-5）：原实现为渲染摘要把整行 req_json+result_json
        # （~50KB/行）搬进 Python 再 json.loads——改 json_extract 在 SQLite
        # 内直取两个摘要字段；req 全字段前端列表零引用（复看走详情接口），
        # 不再回吐。
        # R230z：多类型共存后 result_summary 只对 bazi 有意义——非八字
        # 行 render 落空字符串，前端按 type 渲染徽标，摘要区展示 name。
        rows = c.execute(
            # R233x（R56-P0）：坏 result_json 行让 json_extract 抛
            # malformed JSON → 整列 503，且列表恰是找坏行的唯一入口。
            "SELECT id,ts,name,question,type,"
            " CASE WHEN json_valid(result_json) THEN"
            "   json_extract(result_json,'$.paipan.render') END,"
            " CASE WHEN json_valid(result_json) THEN"
            "   json_extract(result_json,'$.calc.five_elements.counts') END,"
            " CASE WHEN json_valid(result_json) THEN"
            "   json_extract(result_json,'$.render') END"
            " FROM records ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
    items = []
    for rid, ts, name, question, rtype, render, counts, flat_render in rows:
        try:
            counts = json.loads(counts) if counts else None
        except ValueError:
            counts = None
        items.append({
            "id": rid, "ts": ts, "name": name,
            "question": question,
            "type": rtype or "bazi",
            "result_summary": {
                "paipan_render": render or flat_render,
                "five_elements": counts,
            },
        })
    return {"total": total, "items": items}


def get_record(rid: int) -> dict | None:
    """单条完整记录；不存在返回 None（路由层转 404）。"""
    with contextlib.closing(_conn()) as c:
        row = c.execute(
            "SELECT id,ts,name,question,req_json,result_json,type"
            " FROM records WHERE id=?", (int(rid),)).fetchone()
    if row is None:
        return None
    rid, ts, name, question, req_json, res_json, rtype = row
    try:
        req_obj = json.loads(req_json) if req_json else {}
    except ValueError:
        req_obj = {}                    # R228j：同 list_records 的护栏
    try:
        res_obj = json.loads(res_json) if res_json else {}
    except ValueError:
        res_obj = {}
    return {"id": rid, "ts": ts, "name": name, "question": question,
            "type": rtype or "bazi", "req": req_obj, "result": res_obj}


def delete_record(rid: int) -> bool:
    """删除单条；返回是否存在。"""
    with contextlib.closing(_conn()) as c, c:
        cur = c.execute("DELETE FROM records WHERE id=?", (int(rid),))
        return cur.rowcount > 0


def export_rows() -> list[tuple]:
    """CSV 导出数据行：(id, ts, name, question, type, paipan_render)。"""
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT id,ts,name,question,type,result_json FROM records"
            " ORDER BY id DESC").fetchall()
    out = []
    for rid, ts, name, question, rtype, res_json in rows:
        try:
            _robj = json.loads(res_json) or {}
            render = (_robj.get("paipan") or {}).get("render") or \
                _robj.get("render") or ""
        except ValueError:
            render = ""
        out.append((rid, ts, _csv_safe(name or ""),
                    _csv_safe(question or ""), _csv_safe(rtype or "bazi"),
                    _csv_safe(render)))
    return out


# R231a（R36-P3-3）：换设备数据迁移——导出全量行（含 req/result 供
# 复看回放）+ 导入落库。导入走独立函数而非 save_async：批量、同步返回
# 计数、跳过禁用闸（用户显式恢复动作——与 export 在禁用下仍可读的
# 既有口径一致）。
_VALID_TYPES = {"bazi", "taohua", "hehun", "tarot", "liuyao", "qiming"}


def export_all() -> list[dict]:
    """全量导出：每行含 req/result dict，前端打包成备份 JSON。"""
    with contextlib.closing(_conn()) as c:
        rows = c.execute(
            "SELECT ts,name,question,type,req_json,result_json FROM records"
            " ORDER BY id").fetchall()
    out = []
    for ts, name, question, rtype, req_json, res_json in rows:
        try:
            req_obj = json.loads(req_json) if req_json else {}
        except ValueError:
            req_obj = {}
        try:
            res_obj = json.loads(res_json) if res_json else {}
        except ValueError:
            res_obj = {}
        out.append({"ts": ts, "name": name or "", "question": question or "",
                    "type": rtype or "bazi",
                    "req": req_obj, "result": res_obj})
    return out


def import_rows(rows: list[dict]) -> int:
    """批量落库（追加式，去重靠 ts+name+type 三元组）；返回写入条数。

    防线：条数 ≤ KEEP_MAX、单行序列化 ≤256KB、字段截断到列上限、
    type 白名单——备份文件是用户可控输入，按不可信数据验。"""
    if not isinstance(rows, list) or not rows:
        return 0
    with _write_lock, contextlib.closing(_conn()) as c, c:
        written = 0
        for r in rows[:KEEP_MAX]:
            if not isinstance(r, dict):
                continue
            rtype = r.get("type") if r.get("type") in _VALID_TYPES else "bazi"
            try:
                req_s = json.dumps(r.get("req") or {}, ensure_ascii=False)
                res_s = json.dumps(r.get("result") or {}, ensure_ascii=False)
            except (TypeError, ValueError):
                continue
            if len(req_s) > 262144 or len(res_s) > 262144:
                continue
            ts = str(r.get("ts") or "")[:32] or \
                datetime.now().isoformat(timespec="seconds")
            name = str(r.get("name") or "")[:200]
            question = str(r.get("question") or "")[:200] or None
            # 同 (ts,name,type) 视为同一记录——重复导入不产生重复行
            dup = c.execute(
                "SELECT 1 FROM records WHERE ts=? AND name=? AND type=?",
                (ts, name, rtype)).fetchone()
            if dup:
                continue
            c.execute(
                "INSERT INTO records(ts,name,question,req_json,result_json,"
                "type) VALUES(?,?,?,?,?,?)",
                (ts, name, question, req_s, res_s, rtype))
            written += 1
        c.execute(
            "DELETE FROM records WHERE id NOT IN "
            "(SELECT id FROM records ORDER BY id DESC LIMIT ?)",
            (KEEP_MAX,))
    return written


def _csv_safe(v: str) -> str:
    """R229n（R6-#9）：CSV 单元格以 =+-@ / 制表符开头时 Excel/WPS 会按
    公式执行（question 是用户自由文本）——前置 ' 转义。"""
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
