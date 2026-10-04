"""web/routers/account.py — 小满轻账号 HTTP 绑定（R3358）。

昵称+口令码的极简账号：注册/登录/备份推送/备份拉取。
目的只有一个——换设备/无痕模式后能把「我的数据」拉回来；
不做找回（轻账号没有联系渠道，忘了就是没了，前端文案明说）。

口令在每个请求里直传（HTTPS），服务端只比对散列、不签发
token——账号本身无状态，没有会话可劫持。登录/拉取对
(IP+nickname) 限速，挡 6 位口令的爆破面。
"""
from __future__ import annotations

import os
import threading
import time

from fastapi import APIRouter, Request

from .. import userdb
from ..schemas import AccountAuthRequest, AccountBackupPushRequest

router = APIRouter(tags=["account"])

_RATE: dict[str, list[float]] = {}
_RATE_LOCK = threading.Lock()
_RATE_WIN_S = 60.0


def _rate_ok(key: str, limit: int) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        kl = [t for t in _RATE.get(key, ()) if now - t < _RATE_WIN_S]
        _RATE[key] = kl
        if len(_RATE) > 4096:
            for k in list(_RATE)[2048:]:
                _RATE.pop(k, None)
        if len(kl) >= limit:
            return False
        kl.append(now)
        return True


def _client_ip(req: Request) -> str:
    # R3362（R3359/60 审-P1）：与 _gate_ip 同口径——XFF 只在
    # BOOKS_TRUST_XFF=1 时取尾段，否则无条件信会被自填值轮换桶位；
    # 不信时退化为全局桶（与闸的 __all__ 同语义）。
    xff = (req.headers.get("x-forwarded-for") or "").strip()
    if xff and os.getenv("BOOKS_TRUST_XFF", "").strip().lower() in (
            "1", "on", "true", "yes"):
        return xff.split(",")[-1].strip() or "?"
    # 不信时连 req.client 都不能用——uvicorn --forwarded-allow-ips
    # 已把 scope["client"] 用自填 XFF[0] 改写，同闸口径退全局桶。
    return "__all__"


@router.get("/api/account/status")
def account_status() -> dict:
    """后端形态探测——前端据此决定要不要显示「同步不可用」。
    libsql=云库已配（生产该有的样子）；local=本地文件兜底。
    issue=半配状态（只配了 URL 或 token 之一等），空串=正常。"""
    return {"backend": userdb.backend(), "issue": userdb.config_issue()}


def _nick_ratelimit(ip: str, bucket: str, nickname: str,
                    ip_limit: int, nick_limit: int) -> bool:
    """R3372-P1-1：无 XFF 信任时 _client_ip 恒 '__all__'——ip 桶
    退化成全站共享桶，一个人撞线全站 429。此时只按昵称分桶；
    有真 IP 时照旧双因子（ip 全局防跨昵称喷洒 + ip+昵称）。"""
    if ip == "__all__":
        return _rate_ok(bucket + ":" + nickname, nick_limit)
    return (_rate_ok(bucket + "-ip:" + ip, ip_limit)
            and _rate_ok(bucket + ":" + ip + ":" + nickname, nick_limit))


@router.post("/api/account/register")
def account_register(req: AccountAuthRequest, request: Request) -> dict:
    ip = _client_ip(request)
    if not _nick_ratelimit(ip, "reg", req.nickname, 10, 10):
        return {"ok": False, "msg": "手太快了，歇口气再来"}
    ok, msg = userdb.register(req.nickname, req.passcode)
    return {"ok": ok, "msg": msg}


@router.post("/api/account/login")
def account_login(req: AccountAuthRequest, request: Request) -> dict:
    ip = _client_ip(request)
    # R3362（R3359 审-P1）：纯按昵称分桶时同码跨昵称喷洒不耗桶——
    # 叠一层 IP 全局桶，60/分 ≈ 每秒一个，人用不了那么多。
    if not _nick_ratelimit(ip, "login", req.nickname, 60, 20):
        return {"ok": False, "msg": "试太多次了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    return {"ok": True, "msg": "ok"}


@router.post("/api/account/backup/push")
def account_backup_push(req: AccountBackupPushRequest,
                        request: Request) -> dict:
    ip = _client_ip(request)
    if not _nick_ratelimit(ip, "push", req.nickname, 30, 30):
        return {"ok": False, "msg": "同步太频繁了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    # R3372-P2-1：乐观并发——客户端带上它最近一次看到的云端
    # updated_at；不一致说明另一台设备先推过，拒写回 409 语义
    # （ok:false + conflict），让客户端先拉回再推，不再静默互踩。
    conflict_at = userdb.put_backup(
        req.nickname, req.payload, req.base_updated_at)
    if conflict_at is not None:
        return {"ok": False, "conflict": True,
                "msg": "另一台设备刚推了新备份——先点「从云端拉回」再同步",
                "updated_at": conflict_at}
    return {"ok": True, "msg": "ok",
            "updated_at": userdb.get_backup(req.nickname)["updated_at"]}


@router.post("/api/account/backup/pull")
def account_backup_pull(req: AccountAuthRequest,
                        request: Request) -> dict:
    """POST 而非 GET——口令在 body 里不进 URL/日志。"""
    ip = _client_ip(request)
    if not _nick_ratelimit(ip, "pull", req.nickname, 60, 20):
        return {"ok": False, "msg": "试太多次了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    row = userdb.get_backup(req.nickname)
    if row is None:
        return {"ok": False, "msg": "云端还没有备份，先在原设备同步一次"}
    return {"ok": True, "msg": "ok", "payload": row["payload"],
            "updated_at": row["updated_at"]}
