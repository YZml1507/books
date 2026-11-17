# -*- coding: utf-8 -*-
import io, sys
P = "/opt/books/app/src/guji/paipan_history.py"
with io.open(P, "r", encoding="utf-8") as f:
    s = f.read()
OLD = ('            "SELECT id,ts,name,question,type,result_json FROM records"\n'
       '            " WHERE owner=?"\n'
       '            " ORDER BY id DESC").fetchall()')
NEW = ('            "SELECT id,ts,name,question,type,result_json FROM records"\n'
       '            " WHERE owner=? ORDER BY id DESC",\n'
       '            (current_owner(),)).fetchall()')
if s.count(OLD) != 1:
    sys.exit("FAIL count=%d" % s.count(OLD))
if NEW in s:
    sys.exit("FAIL 已打过")
s = s.replace(OLD, NEW, 1)
with io.open(P, "w", encoding="utf-8") as f:
    f.write(s)
print("bind OK")
