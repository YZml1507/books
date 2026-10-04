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

def _canon(nickname: str) -> str:
    """R3372-低-2：昵称大小写归一——'Abc' 与 'abc' 是同一个账号
    （NFKC 已在 schema 层做过）。新注册的账号行存归一形；
    老库里大小写账号靠 lower() 兜底仍能登。"""
    return nickname.casefold()


def register(nickname: str, passcode: str) -> tuple[bool, str]:
    """注册。返回 (ok, msg)。昵称即主键，重名拒收。"""
    init()
    # R3372-低-2：大小写不敏感查重——'Abc' 存在时 'ABC' 也拒。
    if _exec("SELECT 1 FROM accounts WHERE lower(nickname)=lower(?)",
             (nickname,)):
        # R3372-P2-3：文案不再点明「已有人用」——注册面不再泄露
        # 账号存在性（与登录侧「名字或口令码不对」同口径）。
        return False, "这个名字不能用，换一个试试"
    salt = base64.b64encode(secrets.token_bytes(9)).decode()
    try:
        _exec(
            "INSERT INTO accounts (nickname, pass_hash, salt,"
            " created_at, updated_at) VALUES (?,?,?,?,?)",
            (_canon(nickname),
             _hash(passcode, salt), salt, _now(), _now()))
    except Exception:
        # 并发重名抢注：SELECT 后 INSERT 前另一请求先建了同昵称——
        # sqlite IntegrityError / libsql 约束报错统一归并为重名拒。
        return False, "这个名字不能用，换一个试试"
    return True, "ok"


def verify(nickname: str, passcode: str) -> bool:
    init()
    rows = _exec(
        "SELECT pass_hash, salt FROM accounts WHERE nickname=?",
        (_canon(nickname),))
    if not rows and _canon(nickname) != nickname:
        # 老库里大小写账号——casefold 前注册的 'Abc' 仍按 lower() 兜住。
        rows = _exec(
            "SELECT pass_hash, salt FROM accounts"
            " WHERE lower(nickname)=lower(?)", (nickname,))
    if not rows:
        return False
    return secrets.compare_digest(
        _hash(passcode, rows[0]["salt"]), rows[0]["pass_hash"])


def _backup_nick(nickname: str) -> str:
    """backups 表规范昵称：已有行（含老大小写行）按原 case 命中，
    新行存归一形——避免 'Abc'/'abc' 裂成两条备份。"""
    rows = _exec("SELECT nickname FROM backups"
                 " WHERE lower(nickname)=lower(?)", (nickname,))
    return rows[0]["nickname"] if rows else _canon(nickname)


def put_backup(nickname: str, payload: str,
               base_updated_at: str | None = None) -> str | None:
    """写入备份。返回 None=成功；返回 str=冲突时云端当前 updated_at。
    R3372-P2-1：base_updated_at 非 None 且与云端不一致→拒写回当前
    云端戳（乐观并发：另一台设备先推过，客户端先拉回再推）。
    SELECT→写之间仍有微竞态——轻账号按建议性并发控制处理，不做
    分布式锁。"""
    init()
    nick = _backup_nick(nickname)
    if base_updated_at is not None:
        rows = _exec("SELECT updated_at FROM backups WHERE nickname=?",
                     (nick,))
        if rows and rows[0]["updated_at"] != base_updated_at:
            return rows[0]["updated_at"]
    _exec(
        "INSERT INTO backups (nickname, payload, updated_at)"
        " VALUES (?,?,?) ON CONFLICT(nickname) DO UPDATE SET"
        " payload=excluded.payload, updated_at=excluded.updated_at",
        (nick, payload, _now()))
    return None


def get_backup(nickname: str) -> dict | None:
    init()
    rows = _exec("SELECT payload, updated_at FROM backups WHERE nickname=?",
                 (_canon(nickname),))
    if not rows and _canon(nickname) != nickname:
        rows = _exec(
            "SELECT payload, updated_at FROM backups"
            " WHERE lower(nickname)=lower(?)", (nickname,))
    return dict(rows[0]) if rows else None
