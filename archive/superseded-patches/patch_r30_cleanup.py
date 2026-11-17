# -*- coding: utf-8 -*-
"""R30：账号注销端点 + 自测扫尾。"""
import io, sys

# ---- 1) 路由 ----
J = "/opt/books/app/web/routers/account.py"
s = io.open(J, encoding="utf-8").read()
A = '@router.post("/api/account/backup/pull")'
N = ('@router.post("/api/account/delete")\n'
     'def account_delete(req: AccountAuthRequest, request: Request) -> dict:\n'
     '    """R30：注销账号——口令在 body 里不进 URL/日志（同 pull 口径）。\n'
     '    校验通过后连云端备份一起删，不留孤儿行。"""\n'
     '    ip = _client_ip(request)\n'
     '    if not _nick_ratelimit(ip, "delete", req.nickname, 10, 5):\n'
     '        return {"ok": False, "msg": "试太多次了，歇口气再来"}\n'
     '    ok, msg = userdb.delete_account(req.nickname, req.passcode)\n'
     '    return {"ok": ok, "msg": msg}\n'
     '\n'
     '\n' + A)
if s.count(A) != 1:
    sys.exit("FAIL[router-a] %d" % s.count(A))
if "account/delete" in s:
    sys.exit("FAIL[router-dup]")
io.open(J, "w", encoding="utf-8").write(s.replace(A, N, 1))
print("router OK")

# ---- 2) 自测：注册完扫尾删掉 ----
T = "/opt/books/app/web/selftest.py"
t = io.open(T, encoding="utf-8").read()
B = ('    check("account.pull", client.post("/api/account/backup/pull",\n'
     '          json={"nickname": _an, "passcode": "246810"}),\n'
     '          lambda j: j.get("ok") is True and\n'
     '                    \'"kind":"backup"\' in (j.get("payload") or ""))\n')
NB = B + (
    '    # R30：自测注册的账号历来不删——data/users.db 堆到 85 个，其中 83 个\n'
    '    # 是测试残留（用户直报「怎么 81 个账号？怎么这么多」）。跑完即销。\n'
    '    check("account.delete", client.post("/api/account/delete",\n'
    '          json={"nickname": _an, "passcode": "246810"}),\n'
    '          lambda j: j.get("ok") is True)\n'
    '    check("account.delete_bad", client.post("/api/account/delete",\n'
    '          json={"nickname": _an + "不存在", "passcode": "246810"}),\n'
    '          lambda j: j.get("ok") is False)\n')
if t.count(B) != 1:
    sys.exit("FAIL[st-a] %d" % t.count(B))
if "account.delete" in t:
    sys.exit("FAIL[st-dup]")
io.open(T, "w", encoding="utf-8").write(t.replace(B, NB, 1))
print("selftest OK")
