"""web/routers/account.py — 小满轻账号 HTTP 绑定（R3358）。

昵称+口令码的极简账号：注册/登录/备份推送/备份拉取。
目的只有一个——换设备/无痕模式后能把「我的数据」拉回来；
不做找回（轻账号没有联系渠道，忘了就是没了，前端文案明说）。

口令在每个请求里直传（HTTPS），服务端只比对散列、不签发
token——账号本身无状态，没有会话可劫持。登录/拉取对
(IP+nickname) 限速，挡 6 位口令的爆破面。
"""
from __future__ import annotations

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
    xff = (req.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[-1].strip()
    return req.client.host if req.client else "?"


@router.get("/api/account/status")
def account_status() -> dict:
    """后端形态探测——前端据此决定要不要显示「同步不可用」。
    libsql=云库已配（生产该有的样子）；local=本地文件兜底。"""
    return {"backend": userdb.backend()}


@router.post("/api/account/register")
def account_register(req: AccountAuthRequest, request: Request) -> dict:
    ip = _client_ip(request)
    if not _rate_ok("reg:" + ip, 10):
        return {"ok": False, "msg": "手太快了，歇口气再来"}
    ok, msg = userdb.register(req.nickname, req.passcode)
    return {"ok": ok, "msg": msg}


@router.post("/api/account/login")
def account_login(req: AccountAuthRequest, request: Request) -> dict:
    ip = _client_ip(request)
    if not _rate_ok("login:" + ip + ":" + req.nickname, 20):
        return {"ok": False, "msg": "试太多次了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    return {"ok": True, "msg": "ok"}


@router.post("/api/account/backup/push")
def account_backup_push(req: AccountBackupPushRequest,
                        request: Request) -> dict:
    ip = _client_ip(request)
    if not _rate_ok("push:" + ip, 30):
        return {"ok": False, "msg": "同步太频繁了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    userdb.put_backup(req.nickname, req.payload)
    return {"ok": True, "msg": "ok"}


@router.post("/api/account/backup/pull")
def account_backup_pull(req: AccountAuthRequest,
                        request: Request) -> dict:
    """POST 而非 GET——口令在 body 里不进 URL/日志。"""
    ip = _client_ip(request)
    if not _rate_ok("pull:" + ip + ":" + req.nickname, 20):
        return {"ok": False, "msg": "试太多次了，歇口气再来"}
    if not userdb.verify(req.nickname, req.passcode):
        return {"ok": False, "msg": "名字或口令码不对"}
    payload = userdb.get_backup(req.nickname)
    if payload is None:
        return {"ok": False, "msg": "云端还没有备份，先在原设备同步一次"}
    return {"ok": True, "msg": "ok", "payload": payload}
