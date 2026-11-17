# -*- coding: utf-8 -*-
import io, sys
JS = "/opt/books/app/web/static/app.js"
with io.open(JS, "r", encoding="utf-8") as f:
    a = f.read()


def rep(tag, old, new, n=1):
    global a
    if a.count(old) != n:
        sys.exit("FAIL[%s] count=%d" % (tag, a.count(old)))
    if new and new in a:
        sys.exit("FAIL[%s] 已打过" % tag)
    a = a.replace(old, new, n)


# 1) 两个常量 → 按账户取键的函数 + 一次性迁移
rep("keys",
    "var _PH_MIRROR_KEY = 'paipan_mirror_v1';",
    "/* R26（用户裁决「登录哪个账户就应该显示哪个账户里面的排盘历史」）：\n"
    " * 镜像此前是全局键 paipan_mirror_v1——同一台浏览器换账户登录，\n"
    " * 排盘历史里躺的还是上一个人排的盘。改成按账户分键。 */\n"
    "function _phOwnerTag() {\n"
    "  try {\n"
    "    var c = JSON.parse(localStorage.getItem('xmaccount') || 'null');\n"
    "    return (c && c.n) ? String(c.n).trim().toLowerCase() : '_guest';\n"
    "  } catch (e) { return '_guest'; }\n"
    "}\n"
    "function _phMirrorKey() { return 'paipan_mirror_v1:' + _phOwnerTag(); }\n"
    "function _phMirrorDelKey() { return 'paipan_mirror_del_v1:' + _phOwnerTag(); }\n"
    "var _PH_MIGRATED = false;\n"
    "/* 一次性迁移：老全局键里的留档归到当前登录账户名下，然后撤掉全局键——\n"
    " * 否则下一个账户会继承上一个人留下的记录。未登录不迁（避免把\n"
    " * 别人的留档记到 _guest 头上）。 */\n"
    "function _phMirrorMigrate() {\n"
    "  if (_PH_MIGRATED || _phOwnerTag() === '_guest') return;\n"
    "  _PH_MIGRATED = true;\n"
    "  try {\n"
    "    var _k = _phMirrorKey(), _kd = _phMirrorDelKey();\n"
    "    var _g = 'paipan_mirror_v1', _gd = 'paipan_mirror_del_v1';\n"
    "    if (localStorage.getItem(_k) === null &&\n"
    "        localStorage.getItem(_g) !== null) {\n"
    "      localStorage.setItem(_k, localStorage.getItem(_g));\n"
    "      localStorage.removeItem(_g);\n"
    "    }\n"
    "    if (localStorage.getItem(_kd) === null &&\n"
    "        localStorage.getItem(_gd) !== null) {\n"
    "      localStorage.setItem(_kd, localStorage.getItem(_gd));\n"
    "      localStorage.removeItem(_gd);\n"
    "    }\n"
    "  } catch (e) {}\n"
    "}")

rep("delkey",
    "var _PH_MIRROR_DEL_KEY = 'paipan_mirror_del_v1';",
    "/* R26：见 _phMirrorDelKey()——按账户分键。 */")

# 2) 全部引用换成函数调用
for old, new in (
        ("localStorage.getItem(_PH_MIRROR_DEL_KEY)", "localStorage.getItem(_phMirrorDelKey())"),
        ("localStorage.setItem(_PH_MIRROR_DEL_KEY", "localStorage.setItem(_phMirrorDelKey()"),
        ("localStorage.getItem(_PH_MIRROR_KEY)", "localStorage.getItem(_phMirrorKey())"),
        ("localStorage.setItem(_PH_MIRROR_KEY", "localStorage.setItem(_phMirrorKey()"),
        ("localStorage.removeItem(_PH_MIRROR_KEY)", "localStorage.removeItem(_phMirrorKey())"),
        ("localStorage.removeItem(_PH_MIRROR_DEL_KEY)", "localStorage.removeItem(_phMirrorDelKey())"),
        ("e.key === _PH_MIRROR_KEY || e.key === _PH_MIRROR_DEL_KEY",
         "e.key === _phMirrorKey() || e.key === _phMirrorDelKey()"),
        ("JSON.stringify(_dd)", "JSON.stringify(_dd)")):
    a = a.replace(old, new)

if "_PH_MIRROR_KEY" in a or "_PH_MIRROR_DEL_KEY" in a:
    sys.exit("FAIL 残留旧引用: %s" %
             [x for x in a.split("\n") if "_PH_MIRROR_KEY" in x or "_PH_MIRROR_DEL_KEY" in x][:3])

# 3) 读镜像前先迁移
rep("mig-hook",
    "function _phMirrorLoad() {\n  try {\n"
    "    var _m = JSON.parse(localStorage.getItem(_phMirrorKey()) || 'null');",
    "function _phMirrorLoad() {\n"
    "  _phMirrorMigrate();\n"
    "  try {\n"
    "    var _m = JSON.parse(localStorage.getItem(_phMirrorKey()) || 'null');")

with io.open(JS, "w", encoding="utf-8") as f:
    f.write(a)
print("app.js OK")
