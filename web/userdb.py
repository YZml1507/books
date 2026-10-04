"""web/userdb.py — 小满轻账号存储层（昵称+口令码，不含邮箱/手机）。

存储后端两级：
  - BOOKS_USERDB_URL=libsql://<db>.turso.io + BOOKS_USERDB_TOKEN
    → Turso 云库（Render 免费档每 15 分钟清盘，服务端本地文件存
      不住账号，必须外置）。走 /v2/pipeline HTTP 协议，urllib 直连
      不引新依赖。
  - 未配 URL → 本地 data/users.db（开发/本机自跑兜底）。

隐私口径：口令只存 sha256(salt+passcode) 散列，备份负载整体
不透明存放（服务端不解析用户数据内容）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import urllib.request
from datetime import datetime, timezone

from . import deps

_LOCAL = threading.local()

# R3362（R3360 审-P2）：此前自拼 __file__ 相对路径——PyInstaller
# frozen 下 __file__ 指进 _MEIPASS 临时解压目录，users.db 每次启动
# 随解压重建丢失；与 deps.ROOT 口径统一。
_DB_PATH = os.path.join(deps.ROOT, "data", "users.db")

_URL = os.getenv("BOOKS_USERDB_URL", "").strip()
_TOKEN = os.getenv("BOOKS_USERDB_TOKEN", "").strip()
_INITED = False
_INIT_LOCK = threading.Lock()


class UserDBError(Exception):
    """libsql/本地库的语义级故障（pipeline 报错、响应对不上形）。
    errors.py 注册成 503——此前 RuntimeError 穿透成英文裸 500。"""


def config_issue() -> str:
    """半配状态检测：只配 URL 不配 token → 全请求 401；URL 不是
    libsql:// 前缀 → 静默回落 local（部署者以为云端已接）。"""
    if _URL and not _URL.startswith("libsql://"):
        return "BOOKS_USERDB_URL 不是 libsql:// 开头——已回落本机库"
    if _URL and not _TOKEN:
        return "只配了 URL 没配 BOOKS_USERDB_TOKEN——云端请求会 401"
    return ""

_DDL = [
    "CREATE TABLE IF NOT EXISTS accounts ("
    "nickname TEXT PRIMARY KEY, pass_hash TEXT NOT NULL,"
    "salt TEXT NOT NULL, created_at TEXT NOT NULL,"
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS backups ("
    "nickname TEXT PRIMARY KEY, payload TEXT NOT NULL,"
    "updated_at TEXT NOT NULL)",
]


def backend() -> str:
    return "libsql" if _URL.startswith("libsql://") else "local"


# ---------- libsql (Turso) HTTP 客户端 ----------

def _http_host() -> str:
    return "https://" + _URL[len("libsql://"):]


def _arg(v) -> dict:
    if v is None:
        return {"type": "null"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _ls_exec(sql: str, args: list) -> list[dict]:
    """返回结果行列表（每行 dict: col->python 值）。"""
    body = json.dumps({
        "requests": [
            {"type": "execute",
             "stmt": {"sql": sql, "args": [_arg(a) for a in args]}},
            {"type": "close"}]}).encode()
    req = urllib.request.Request(
        _http_host() + "/v2/pipeline", data=body,
        headers={"Authorization": "Bearer " + _TOKEN,
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read().decode())
    except (json.JSONDecodeError, ValueError) as e:
        raise UserDBError(str(e)) from e
    res = out.get("results", [])
    if not res or res[0].get("type") != "ok":
        err = (res[0].get("error", {}) if res else {}).get("message",
                                                          "libsql error")
        # R3362（R3360 审-P1）：RuntimeError 穿透成英文裸 500——
        # pipeline 语义错（SQL 错/命名空间错）归一到 UserDBError。
        raise UserDBError(err)
    try:
        result = res[0]["response"]["result"]
        cols = [c.get("name") for c in result.get("cols", [])]
        rows = []
        for row in result.get("rows", []):
            d = {}
            for c, cell in zip(cols, row):
                v = cell.get("value")
                if cell.get("type") == "integer":
                    v = int(v)
                d[c] = v
            rows.append(d)
        return rows
    except (KeyError, TypeError, ValueError) as e:
        raise UserDBError(str(e)) from e


# ---------- 本地 sqlite ----------

def _local_conn() -> sqlite3.Connection:
    c = getattr(_LOCAL, "userdb", None)
    if c is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        # R3362（R3360 审-P2）：busy_timeout——双设备同时 push
        # 两个线程并发写即 SQLITE_BUSY→503，10s 等待把短锁变排队。
        c = sqlite3.connect(_DB_PATH, timeout=10)
        c.row_factory = sqlite3.Row
        _LOCAL.userdb = c
    return c


def _exec(sql: str, args: tuple = ()) -> list[dict]:
    if backend() == "libsql":
        return _ls_exec(sql, list(args))
    conn = _local_conn()
    cur = conn.execute(sql, args)
    conn.commit()
    return [dict(r) for r in cur.fetchall()]


def init() -> None:
    """建表幂等且每进程只跑一次——此前每个账号端点调用都
    重新跑 2 条 DDL，libsql 后端下每条都是一次 HTTP 往返。"""
    global _INITED
    if _INITED:
        return
    with _INIT_LOCK:
        if _INITED:
            return
        for ddl in _DDL:
            _exec(ddl)
        _INITED = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(passcode: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + passcode).encode()).hexdigest()


# ---------- 账号操作 ----------

def register(nickname: str, passcode: str) -> tuple[bool, str]:
    """注册。返回 (ok, msg)。昵称即主键，重名拒收。"""
    init()
    if _exec("SELECT 1 FROM accounts WHERE nickname=?",
             (nickname,)):
        return False, "这个名字已经有人用了，换一个试试"
    salt = base64.b64encode(secrets.token_bytes(9)).decode()
    try:
        _exec(
            "INSERT INTO accounts (nickname, pass_hash, salt,"
            " created_at, updated_at) VALUES (?,?,?,?,?)",
            (nickname, _hash(passcode, salt), salt, _now(), _now()))
    except Exception:
        # 并发重名抢注：SELECT 后 INSERT 前另一请求先建了同昵称——
        # sqlite IntegrityError / libsql 约束报错统一归并为重名拒。
        return False, "这个名字已经有人用了，换一个试试"
    return True, "ok"


def verify(nickname: str, passcode: str) -> bool:
    init()
    rows = _exec(
        "SELECT pass_hash, salt FROM accounts WHERE nickname=?",
        (nickname,))
    if not rows:
        return False
    return secrets.compare_digest(
        _hash(passcode, rows[0]["salt"]), rows[0]["pass_hash"])


def put_backup(nickname: str, payload: str) -> None:
    init()
    _exec(
        "INSERT INTO backups (nickname, payload, updated_at)"
        " VALUES (?,?,?) ON CONFLICT(nickname) DO UPDATE SET"
        " payload=excluded.payload, updated_at=excluded.updated_at",
        (nickname, payload, _now()))


def get_backup(nickname: str) -> str | None:
    init()
    rows = _exec("SELECT payload FROM backups WHERE nickname=?",
                 (nickname,))
    return rows[0]["payload"] if rows else None
