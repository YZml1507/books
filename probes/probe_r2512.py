#!/usr/bin/env python3
"""R2512 回归钉扎——app.js 口吻切换重画路径四修。

钉扎项：
  1. voice.rebind_stored    —— 结果按钮重绑闭包存在（S2 勘：原 rememberVoice
                               收 rebindFn 存 entry.rebind 的架构已退役，
                               见下方 S2 勘说明，钉等价新机制）
  2. voice.rebind_replay    —— 复看/脏广播后按钮不死（_PH_BUILDERS 分发）
  3. voice.bazi_rebind      —— bazi 结果路径收进 _rbBazi 并首绑
  4. voice.qiming_rebind    —— qiming 结果路径收进 _rbQm
  5. voice.hehun_rebind     —— hehun 结果路径收进 _rbHh
  6. voice.taohua_rebind    —— taohua 结果路径收进 _rbTh
  7. voice.liuyao_rebind    —— liuyao 结果路径收进 _rbLy
  8. voice.tarot_rebind     —— tarot 结果路径收进 _rbTr
  9. voice.liuyao_btn_inbuild —— shareLiuyao 在 buildLiuyaoResult 内联
 10. voice.tarot_btn_inbuild  —— shareTarot 在 buildTarotResult 内联
 11. voice.no_create_btn    —— 不再有 post-paint createElement 挂分享按钮
 12. nr.unhide_on_write     —— pollNameReview 写入前 out.hidden = false
 13. ai.daily_rearm         —— 回家时 AI_PENDING.dailyDetail 重武装
 14. stale.preserve         —— rerenderVoice 快照并复原 .is-stale

S2 勘（studio）：本探针 R2512 成文时钉的 rememberVoice(cid, j, builder,
rebindFn) + entry.rebind + rerenderVoice 重放架构，已被后续轮次退役——
R3242e 把脏广播收口进 rememberResult 按 _PH_BUILDERS 品类统一发，rebindFn
参数从 remember* 签名中移除，六品类改为各自结果路径内的局部 _rbXxx 闭包
首绑 + _PH_BUILDERS 注册表复看分发 + 复看卡 #phShareBtn 显式监听（R231d）。
「出结果后按钮绑齐、复看不死钮」的不变量未变且覆盖面更宽（原 6 品类 →
_PH_BUILDERS 7 品类含 dream），故按现行机制重钉 1-8 项，不是放水。
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


# --- 1-2. 结果按钮重绑（S2 勘：rememberVoice/rebindFn 架构已退役，
    #    等价不变量改钉 _PH_BUILDERS 注册表 + 各品类 _rbXxx 首绑）----------
_PH = re.search(r"var _PH_BUILDERS = \{(.*?)\n\};", JS, re.S)
_KINDS = ["bazi", "taohua", "hehun", "tarot", "liuyao", "qiming", "dream"]
check("voice.rebind_stored",
      _PH is not None and all(
          f"{k}: function (j)" in _PH.group(1) for k in _KINDS),
      "七品类渲染器注册（复看分发表）")
check("voice.rebind_replay",
      "_builder = _PH_BUILDERS[rec.type || 'bazi']" in JS
      and "id=\"phShareBtn\"" in JS,
      "复看按品类分发+分享钮显式监听（R231d）")

# --- 3-8. 六品类结果路径的 _rbXxx 首绑 -----------------------------------------
# S2 勘：原 rememberVoice('result', j, buildBaziResult, _rbBazi) 登记式已退役；
# 现行等价 = 各结果路径内 var _rbXxx = function(){...on(...)} 定义 + 渲染后
# _rbXxx() 首绑调用。钉「定义在、首绑在」两个事实。
for cid, var in [("result", "_rbBazi"), ("qmResult", "_rbQm"),
                 ("hhResult", "_rbHh"), ("thResult", "_rbTh"),
                 ("lyResult", "_rbLy"), ("trResult", "_rbTr")]:
    check(f"voice.{cid} rebind",
          f"var {var} = function ()" in JS and f"{var}()" in JS,
          f"{var} 定义+首绑")

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
# S2 勘（studio）：R3244 起点评 AI 段写进 #nrAiOut，unhide 目标从 out 改为
# 空值保护的 _outP（el('nameReviewOut')），「写入前显式翻开」的不变量不变。
_nr = _fn_body("pollNameReview")
check("nr.unhide_on_write",
      "_outP.hidden = false" in _nr and
      _nr.index("_outP.hidden = false") < _nr.index("st.status === 'done'"),
      "写入前显式 unhide（R3244 形态）")

# --- 13. dailyDetail 回家重武装 ----------------------------------------------------
check("ai.daily_rearm",
      re.search(r"if \(isHome && AI_PENDING\.dailyDetail\).*?"
                r"pollAiPolish\('dailyDetail'", JS, re.DOTALL),
      "isHome 分支重武装")

# --- 14. is-stale 过期标保活（S2 勘：rerenderVoice 快照/复原 _wasStale 的
    #     路径随 rerenderVoice 退役；R2350e 起改为 paint() 落地摘标 +
    #     _STALE_MAP 改参标脏两段式，不变量「新结果摘标、改参标脏」不变）-----
check("stale.preserve",
      "node.classList.remove('is-stale')" in JS and
      "var _STALE_MAP = [" in JS and
      "classList.add('is-stale')" in JS,
      "paint 摘标+_STALE_MAP 标脏（R2350e）")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
