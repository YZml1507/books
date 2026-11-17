# -*- coding: utf-8 -*-
"""R31：忘掉我的数据 必须连云端备份一起删；回灌循环不得逐条弹 toast。
B 段改用行号替换（整串比对被某处空白卡住）。"""
import io, sys
J = "/opt/books/app/web/static/app.js"
L = io.open(J, encoding="utf-8").read().split("\n")


def rep(tag, old, new):
    s = "\n".join(L)
    if s.count(old) != 1:
        sys.exit("FAIL[%s] %d" % (tag, s.count(old)))
    if new in s:
        sys.exit("FAIL[%s] dup" % tag)
    L[:] = s.replace(old, new, 1).split("\n")


rep("A1",
    "      _hw.dataset.inflight = '1';\n"
    "      var _done = function (serverOk) {",
    "      _hw.dataset.inflight = '1';\n"
    "      /* R31-A：抓凭据——下面本地清扫会连 xmaccount 一并删，而云端\n"
    "         备份也必须删：不清它，重新登录时 _pull() 会把整份 139KB\n"
    "         原样拖回来，档案/心事/打卡全部复活，「忘掉我的数据」成了\n"
    "         假承诺（用户实测复现：wipe 后重登，me 键复活）。 */\n"
    "      var _cW = null;\n"
    "      try { _cW = _creds(); } catch (eCW) {}\n"
    "      var _done = function (serverOk) {")

rep("A2",
    "        _hw.textContent = '再点一次：生辰/昵称/记录全清';",
    "        _hw.textContent = '再点一次：档案/记录/云端备份和账号全删';")

rep("A3",
    "        _threadsDel,\n"
    "        _prefsDel\n"
    "      ]).then(function () { _phMirrorClear();",
    "        _threadsDel,\n"
    "        _prefsDel,\n"
    "        /* R31-A：账号注销（连云端备份）放最后——四表清完再销，\n"
    "           中途失败也至少本机和服务端台账已经干净了。 */\n"
    "        (_cW ? postJSON('/api/account/delete', {\n"
    "          nickname: _cW.n, passcode: _cW.p }, { silent: true })\n"
    "         : Promise.resolve(null))\n"
    "      ]).then(function () { _phMirrorClear();")

# ---- B：行号替换（31423..31443，1-based）----
_i0 = None
for _i, _ln in enumerate(L):
    if _ln == "          var _nOrph = 0, _orphBad = 0;":
        if L[_i + 20] == "          }" and "orphBad++" in L[_i + 18]:
            _i0 = _i
            break
if _i0 is None:
    sys.exit("FAIL[B] anchor")
_i1 = _i0 + 20          # 收尾那个 }
assert L[_i1] == "          }", L[_i1][:40]
NEW = """          /* R3369（审-P1-3）：孤儿手记回灌——逐条 POST orphan:true，
           * 服务端按 claim+method 幂等去重，重灌不翻倍。
           * R31-B：全部静默 + 撞写入闸即停 + 失败聚合成一句。
           * 演示站写入关闭时逐条重试，会把同一句「只能看不能改」
           * 弹成 172 个 toast（用户实测）。 */
          var _nOrph = 0, _orphBad = 0, _orphGate = false;
          if (Array.isArray(bundle.orphan_claims) &&
              bundle.orphan_claims.length) {
            for (var _oi = 0;
                 _oi < bundle.orphan_claims.length && _oi < 200; _oi++) {
              var _oc = bundle.orphan_claims[_oi];
              if (!_oc || typeof _oc !== 'object' || !_oc.claim) {
                _orphBad++; continue;
              }
              try {
                await postJSON('/api/threads', {
                  kind: String(_oc.kind || 'note').slice(0, 32),
                  claim: String(_oc.claim || '').slice(0, 2000),
                  method: String(_oc.method || 'backup-import')
                    .slice(0, 200),
                  confidence: _oc.confidence || null,
                  orphan: true }, { silent: true });
                _nOrph++;
              } catch (eOC) {
                _orphBad++;
                var _em = String((eOC && eOC.message) || eOC || '');
                if (_em.indexOf('只能看') >= 0 ||
                    _em.indexOf('演示') >= 0) { _orphGate = true; break; }
              }
            }
          }
          if (_orphGate) {
            showToast('这是公开演示站，手记回灌被关掉了——' +
              '换到能写入的环境再拉一次', 'warn');
          } else if (_orphBad > 0) {
            showToast('有 ' + _orphBad + ' 条手记没回灌上，' +
              '联网后再拉一次', 'warn');
          }""".split("\n")
L[_i0:_i1 + 1] = NEW
io.open(J, "w", encoding="utf-8").write("\n".join(L))
print("OK lines=%d..%d" % (_i0 + 1, _i1 + 1))
