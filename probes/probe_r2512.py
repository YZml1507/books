#!/usr/bin/env python3
"""R2512 回归钉扎——app.js 口吻切换重画路径四修。

钉扎项：
  1. voice.rebind_stored    —— rememberVoice 收 rebindFn 并存进 entry.rebind
  2. voice.rebind_replay    —— rerenderVoice 画完重放 entry.rebind（try 保护）
  3. voice.bazi_rebind      —— bazi 直绑收进 _rbBazi 并登记
  4. voice.qiming_rebind    —— qiming 三直绑收进 _rbQm
  5. voice.hehun_rebind     —— hehun 三直绑收进 _rbHh
  6. voice.taohua_rebind    —— taohua 直绑收进 _rbTh
  7. voice.liuyao_rebind    —— liuyao 直绑收进 _rbLy
  8. voice.tarot_rebind     —— tarot 直绑收进 _rbTr
  9. voice.liuyao_btn_inbuild —— shareLiuyao 在 buildLiuyaoResult 内联
 10. voice.tarot_btn_inbuild  —— shareTarot 在 buildTarotResult 内联
 11. voice.no_create_btn    —— 不再有 post-paint createElement 挂分享按钮
 12. nr.unhide_on_write     —— pollNameReview 写入前 out.hidden = false
 13. ai.daily_rearm         —— 回家时 AI_PENDING.dailyDetail 重武装
 14. stale.preserve         —— rerenderVoice 快照并复原 .is-stale
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

passed = failed = 0


def check(name, cond, note=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name} {note}")
    else:
        failed += 1
        print(f"FAIL {name} {note}")


with open(os.path.join(ROOT, "web/static/app.js"),
          encoding="utf-8") as _f:
    JS = _f.read()


def _fn_body(name):
    m = re.search(r"function " + name + r"\([^)]*\) \{(.*?)\n\}", JS, re.DOTALL)
    return m.group(1) if m else ""


# --- 1-2. rebind 存取 -----------------------------------------------------------
_rv = _fn_body("rerenderVoice")
check("voice.rebind_stored",
      "rebindFn" in _fn_body("rememberVoice") and
      "rebind: rebindFn || null" in _fn_body("rememberVoice"),
      "entry.rebind 持久化")
check("voice.rebind_replay",
      "entry.rebind" in _rv and re.search(r"try \{[^}]*rebind\(\)", _rv, re.DOTALL),
      "画完重放 rebind")

# --- 3-8. 六容器 rebind 登记 -----------------------------------------------------
_BUILDERS = {"result": "buildBaziResult", "qmResult": "buildQimingResult",
             "hhResult": "buildHehunResult", "thResult": "buildTaohuaResult",
             "lyResult": "buildLiuyaoResult",
             "trResult": "buildTarotResult"}
for cid, var in [("result", "_rbBazi"), ("qmResult", "_rbQm"),
                 ("hhResult", "_rbHh"), ("thResult", "_rbTh"),
                 ("lyResult", "_rbLy"), ("trResult", "_rbTr")]:
    want = (f"rememberVoice('{cid}', j, {_BUILDERS[cid]}, {var})" in JS
            and f"{var}()" in JS)
    check(f"voice.{cid} rebind", want, f"{var} 登记+首绑")

# --- 9-10. 分享按钮进 build ------------------------------------------------------
_li = re.search(r"function buildLiuyaoResult\(.*?\n\}", JS, re.DOTALL)
_tr = re.search(r"function buildTarotResult\(.*?\n\}", JS, re.DOTALL)
check("voice.liuyao_btn_inbuild",
      _li and 'id="shareLiuyao"' in _li.group(0), "build 内联")
check("voice.tarot_btn_inbuild",
      _tr and 'id="shareTarot"' in _tr.group(0), "build 内联")

# --- 11. 手工挂钮代码清除 --------------------------------------------------------
check("voice.no_create_btn",
      "createElement('button')" not in JS.split("id=\"shareLiuyao\"")[0][-3000:]
      or "shareLiuyao" not in JS.split("id=\"shareLiuyao\"")[0][-3000:],
      "无 post-paint createElement 分享钮")

# --- 12. nameReviewOut 写入前翻开 --------------------------------------------------
_nr = _fn_body("pollNameReview")
check("nr.unhide_on_write",
      "out.hidden = false" in _nr and
      _nr.index("out.hidden = false") < _nr.index("st.status === 'done'"),
      "写入前显式 unhide")

# --- 13. dailyDetail 回家重武装 ----------------------------------------------------
check("ai.daily_rearm",
      re.search(r"if \(isHome && AI_PENDING\.dailyDetail\).*?"
                r"pollAiPolish\('dailyDetail'", JS, re.DOTALL),
      "isHome 分支重武装")

# --- 14. is-stale 保留 --------------------------------------------------------------
check("stale.preserve",
      "_wasStale" in _rv and
      re.search(r"contains\('is-stale'\).*?classList\.add\('is-stale'\)",
                _rv, re.DOTALL),
      "快照+复原过期标")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
