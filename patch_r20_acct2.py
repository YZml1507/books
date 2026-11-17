#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-5：把生辰落档接进注册/登录链（CYCLE5_PLAN 任务一 §1.2-A 接线）

注册：_saveCreds 之后、_push 之前 await —— 首份云备份必须带得上生日
      （_DATA_RE 含 me$），否则换设备登录拉回的还是没有生辰的档。
登录：await _pull() 之后——云端有档则以云端为准不动；云端没档（本功能
      上线前注册的老账号）而用户填了生辰，就补一份并推回云端。
"""
import io, sys

APP = "/opt/books/app/web/static/app.js"

REG_OLD = """              _acctRender();
              showToast('注册好啦，正在给你同步第一份备份', 'info');
              /* R3363-P1-4：注册首推用 keepalive——注册即关页时"""

REG_NEW = """              _acctRender();
              /* R20（用户直报）：生辰在注册时落档——必须在首推之前，
               * 云备份才带得上生日（_DATA_RE 含 me$）；换设备登录拉回
               * 即完整档案，_tryReveal 见 me 有 y/m/d 直接拆礼物，不必
               * 再回首页填那张年月日表单。生辰填不全只提示，不阻断注册
               * 与首推（账号已建成，生日随时能从「你的小档案 · 改」补）。 */
              await _saveBirthThen('注册好啦，正在给你同步第一份备份');
              /* R3363-P1-4：注册首推用 keepalive——注册即关页时"""

LOGIN_OLD = """              /* 登录即拉回——这是换设备的主场景；云端没备份时
               * _pull 会明说「先在原设备同步一次」。 */
              await _pull();
            } else {"""

LOGIN_NEW = """              /* 登录即拉回——这是换设备的主场景；云端没备份时
               * _pull 会明说「先在原设备同步一次」。 */
              await _pull();
              /* R20（用户直报）：老账号（本功能上线前注册）云端备份里
               * 没有 me 生辰档——登录时按表单填的补一份并推回云端，
               * 下次换设备登录就是完整档案、礼物直接拆。云端已有档的
               * 不动（以云端为准，本地表单填什么都不覆盖）。 */
              var _meL = null;
              try { _meL = _meGet('me'); } catch (eML) {}
              if (!(_meL && _meL.y && _meL.m && _meL.d) && f.b && f.b.y) {
                var _errL = _birthErr(f.b);
                if (!_errL) {
                  try {
                    await _meSaveFromBirth('me', {
                      y: +f.b.y, m: +f.b.m, d: +f.b.d,
                      h: f.b.h == null ? null : +f.b.h, n: f.n });
                    _push(false, true);
                    showToast('生辰补上啦，已同步到云端', 'info');
                  } catch (eBL) {}
                }
              }
            } else {"""


def main():
    with io.open(APP, "r", encoding="utf-8") as f:
        a = f.read()
    for old, new, tag in ((REG_OLD, REG_NEW, "register"), (LOGIN_OLD, LOGIN_NEW, "login")):
        n = a.count(old)
        if n != 1:
            sys.exit("FAIL: %s anchor count=%d（预期 1）" % (tag, n))
        a = a.replace(old, new, 1)
    if "await _saveBirthThen('注册好啦" not in a:
        sys.exit("FAIL: 注册链未接上")
    if "老账号（本功能上线前注册）云端备份里" not in a:
        sys.exit("FAIL: 登录链未接上")
    with io.open(APP, "w", encoding="utf-8") as f:
        f.write(a)
    print("app.js PATCHED (R20-5 生辰落档接入注册/登录链)")


if __name__ == "__main__":
    main()
