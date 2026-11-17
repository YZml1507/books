# -*- coding: utf-8 -*-
import io, sys
P = "/opt/books/app/src/guji/paipan_history.py"
with io.open(P, "r", encoding="utf-8") as f:
    s = f.read()


def rep(tag, old, new, n=1):
    global s
    if s.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, s.count(old)))
    if new and new in s:
        sys.exit("FAIL[%s] 已打过" % tag)
    s = s.replace(old, new, n)


Q = '"'


def q(t):
    return Q + t + Q


# 1) DDL 加 owner
rep("ddl",
    "    type TEXT NOT NULL DEFAULT 'bazi')" + Q * 3,
    "    type TEXT NOT NULL DEFAULT 'bazi',\n"
    "    /* R26（用户裁决「登录哪个账户就应该显示哪个账户里面的排盘历史」）：\n"
    "       台账此前无账号维度——所有登录用户看到同一份。加 owner 列，\n"
    "       空串=账号体系上线前的存量行，不归属任何账户，按归属过滤后自然\n"
    "       不可见（不删数据，只是不再冒名显示给别人）。 */\n"
    "    owner TEXT NOT NULL DEFAULT '')" + Q * 3)

# 2) 上下文变量
rep("ctxvar",
    "def _conn() -> sqlite3.Connection:",
    "_OWNER = contextvars.ContextVar(\"books_paipan_owner\", default=\"\")\n"
    "\n"
    "\n"
    "def _norm_owner(nick) -> str:\n"
    "    " + Q + "R26：归属标识归一——大小写不敏感、去空白、限长，防注入/脏值。" + Q + "\n"
    "    return re.sub(r\"[^0-9A-Za-z\\u4e00-\\u9fa5_-]\", \"\",\n"
    "                  str(nick or \"\"))[:40].strip().lower()\n"
    "\n"
    "\n"
    "def set_owner(nick) -> None:\n"
    "    " + Q + "R26：请求级归属——由 web/app.py 的中间件在每请求入口设入。" + Q + "\n"
    "    _OWNER.set(_norm_owner(nick))\n"
    "\n"
    "\n"
    "def current_owner() -> str:\n"
    "    return _OWNER.get()\n"
    "\n"
    "\n"
    "def _conn() -> sqlite3.Connection:")

# 3) save_async 签名 + 入口捕获 + INSERT
rep("save-sig",
    "def save_async(req_dict: dict, result_dict: dict, rtype: str = \"bazi\",",
    "def save_async(req_dict: dict, result_dict: dict, rtype: str = \"bazi\",\n"
    "               owner: str | None = None,")
rep("save-cap",
    "    # 仍在排队——wipe 的 DELETE 先落地、在途 INSERT 后落地 → 清空后",
    "    # R26：归属在入队时捕获——后台写线程不在请求上下文里，晚取会拿到\n"
    "    # 空串把这条记录写成无主行。显式 owner 优先，否则取请求级。\n"
    "    _own = _norm_owner(owner) if owner is not None else current_owner()\n"
    "    # 仍在排队——wipe 的 DELETE 先落地、在途 INSERT 后落地 → 清空后")
rep("save-ins",
    "                    " + q("INSERT INTO records(ts,name,question,req_json,result_json,") + "\n"
    "                    " + q("type) VALUES(?,?,?,?,?,?)") + ",\n"
    "                    (ts, row_name, question, row_req, row_res, rtype))",
    "                    " + q("INSERT INTO records(ts,name,question,req_json,result_json,") + "\n"
    "                    " + q("type,owner) VALUES(?,?,?,?,?,?,?)") + ",\n"
    "                    (ts, row_name, question, row_req, row_res, rtype, _own))")

# 3b) 存量表补列
rep("mig",
    '    "result_json": "TEXT NOT NULL DEFAULT \'{}\'",',
    '    "result_json": "TEXT NOT NULL DEFAULT \'{}\'",\n'
    '    # R26：归属列——CREATE TABLE IF NOT EXISTS 不给存量表补列，\n'
    '    # 走 _RECORDS_COLS 让 _ensure_columns 下次连接时 ALTER 上。\n'
    '    "owner": "TEXT NOT NULL DEFAULT \'\'",')

# 4) 列表 COUNT + SELECT
rep("list-cnt",
    "        total = c.execute(" + q("SELECT COUNT(*) FROM records") + ").fetchone()[0]",
    "        total = c.execute(" + q("SELECT COUNT(*) FROM records WHERE owner=?") + ",\n"
    "                           (current_owner(),)).fetchone()[0]")
rep("list-sel",
    "            " + q(" FROM records ORDER BY id DESC LIMIT ? OFFSET ?") + ",\n"
    "            (limit, offset)).fetchall()",
    "            " + q(" FROM records WHERE owner=?") + "\n"
    "            " + q(" ORDER BY id DESC LIMIT ? OFFSET ?") + ",\n"
    "            (current_owner(), limit, offset)).fetchall()")

# 5) 详情 / 删除 / 图鉴 / 导出 / 清空
rep("get",
    "            " + q(" FROM records WHERE id=?") + ", (int(rid),)).fetchone()",
    "            " + q(" FROM records WHERE id=? AND owner=?") + ",\n"
    "            (int(rid), current_owner())).fetchone()")
rep("del",
    "        cur = c.execute(" + q("DELETE FROM records WHERE id=?") + ", (int(rid),))",
    "        cur = c.execute(" + q("DELETE FROM records WHERE id=? AND owner=?") + ",\n"
    "                        (int(rid), current_owner()))")
rep("tarot",
    "                " + q("SELECT result_json FROM records WHERE type='tarot'") + "\n"
    "                " + q(" ORDER BY id DESC LIMIT 500") + ").fetchall()",
    "                " + q("SELECT result_json FROM records WHERE type='tarot'") + "\n"
    "                " + q(" AND owner=? ORDER BY id DESC LIMIT 500") + ",\n"
    "                (current_owner(),)).fetchall()")
rep("export1",
    "            " + q("SELECT id,ts,name,question,type,result_json FROM records"),
    "            " + q("SELECT id,ts,name,question,type,result_json FROM records") + "\n"
    "            " + q(" WHERE owner=?"))
rep("export2",
    "            " + q("SELECT ts,name,question,type,req_json,result_json FROM records"),
    "            " + q("SELECT ts,name,question,type,req_json,result_json FROM records") + "\n"
    "            " + q(" WHERE owner=?"))
rep("wipe",
    "        cur = c.execute(" + q("DELETE FROM records") + ")",
    "        cur = c.execute(" + q("DELETE FROM records WHERE owner=?") + ",\n"
    "                        (current_owner(),))")

# 6) 导入
rep("imp-sig",
    "def import_rows(rows: list[dict]) -> tuple[int, int, list[dict]]:",
    "def import_rows(rows: list[dict],\n"
    "                owner: str | None = None) -> tuple[int, int, list[dict]]:")
rep("imp-own",
    "    if not isinstance(rows, list) or not rows:\n"
    "        return 0, 0, []",
    "    _own_imp = _norm_owner(owner) if owner is not None else current_owner()\n"
    "    if not isinstance(rows, list) or not rows:\n"
    "        return 0, 0, []")
rep("imp-dup",
    "                " + q("SELECT 1 FROM records WHERE ts=? AND name=? AND type=?") + ",\n"
    "                (ts, name, rtype)).fetchone()",
    "                " + q("SELECT 1 FROM records WHERE ts=? AND name=? AND type=?") + "\n"
    "                " + q(" AND owner=?") + ",\n"
    "                (ts, name, rtype, _own_imp)).fetchone()")
rep("imp-ins",
    "                " + q("INSERT INTO records(ts,name,question,req_json,result_json,") + "\n"
    "                " + q("type) VALUES(?,?,?,?,?,?)") + ",\n"
    "                (ts, name, question, req_s, res_s, rtype))",
    "                " + q("INSERT INTO records(ts,name,question,req_json,result_json,") + "\n"
    "                " + q("type,owner) VALUES(?,?,?,?,?,?,?)") + ",\n"
    "                (ts, name, question, req_s, res_s, rtype, _own_imp))")

with io.open(P, "w", encoding="utf-8") as f:
    f.write(s)
print("paipan_history.py OK")
