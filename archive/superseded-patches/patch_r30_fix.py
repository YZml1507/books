# -*- coding: utf-8 -*-
"""R30-b：把删销检查挪到账号测试块末尾——前面若干检查（casefold 去重、
push 冲突、push_updated_at）都依赖该账号还在，插在中间会把它们全废掉。"""
import io, sys
T = "/opt/books/app/web/selftest.py"
t = io.open(T, encoding="utf-8").read()

# 撤掉插在中间的那段
BAD = ('    # R30：自测注册的账号历来不删——data/users.db 堆到 85 个，其中 83 个\n'
       '    # 是测试残留（用户直报「怎么 81 个账号？怎么这么多」）。跑完即销。\n'
       '    check("account.delete", client.post("/api/account/delete",\n'
       '          json={"nickname": _an, "passcode": "246810"}),\n'
       '          lambda j: j.get("ok") is True)\n'
       '    check("account.delete_bad", client.post("/api/account/delete",\n'
       '          json={"nickname": _an + "不存在", "passcode": "246810"}),\n'
       '          lambda j: j.get("ok") is False)\n')
if t.count(BAD) != 1:
    sys.exit("FAIL[rm] %d" % t.count(BAD))
t = t.replace(BAD, "", 1)

# 重新插到 push_updated_at 之后（账号测试块的收尾）
A = ('    assert (_r.status_code == 200 and _r.json().get("ok") is True\n'
     '            and _r.json().get("updated_at")), \\\n'
     '        ("account.push_updated_at", _r.status_code, _r.text[:200])\n'
     '    ok.append("account.push_updated_at")\n')
N = A + (
    '\n'
    '    # R30：账号测试块收尾——自测注册的账号历来不删，data/users.db 堆到\n'
    '    # 85 个、其中 83 个是测试残留（用户直报「怎么 81 个账号？怎么这么多」）。\n'
    '    # 必须放在本块最后：上面 casefold 去重 / push 冲突 / push_updated_at\n'
    '    # 都还要用这个账号，中途删会把它们全废掉。\n'
    '    check("account.delete", client.post("/api/account/delete",\n'
    '          json={"nickname": _an, "passcode": "246810"}),\n'
    '          lambda j: j.get("ok") is True)\n'
    '    check("account.delete_bad", client.post("/api/account/delete",\n'
    '          json={"nickname": _an + "不存在", "passcode": "246810"}),\n'
    '          lambda j: j.get("ok") is False)\n'
    '    # 删过再登——应拒，证明真删掉了而不是软标记。\n'
    '    _r = client.post("/api/account/login",\n'
    '                     json={"nickname": _an, "passcode": "246810"})\n'
    '    assert _r.status_code == 200 and not _r.json().get("ok"), \\\n'
    '        ("account.deleted_gone", _r.status_code, _r.text[:200])\n'
    '    ok.append("account.deleted_gone")\n')
if t.count(A) != 1:
    sys.exit("FAIL[anchor] %d" % t.count(A))
t = t.replace(A, N, 1)
io.open(T, "w", encoding="utf-8").write(t)
print("OK")
