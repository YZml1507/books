#!/usr/bin/env python3
"""R2514 回归钉扎——index.html/styles.css 结构面审查收口。

钉扎项：
  1. css.hidden_global_guard  —— 全局 [hidden]{display:none!important} 灭 bug 类
  2. css.accent_cta           —— daily-personal-cta 用 --accent-ink
  3. css.accent_meta_more     —— daily-meta-more 用 --accent-ink
  4. css.accent_hh_score      —— hh-score strong 用 --accent-ink
  5. css.signpeek_tap         —— sign-peek 文字色 accent-ink + --tap 下限
  6. css.pill_ji              —— hl-pill-ji 用 --rose-deep
  7. css.trback_width         —— tr-back ≥40px
  8. css.theme_toggle         —— theme-toggle 44×44
  9. css.daily_retry_tap      —— daily-retry --tap
 10. css.celeb_print          —— celeb-backdrop 进 print 隐藏表
 11. js.hl_date_validate      —— huangli 手输日期本地校验
 12. js.wish_aria             —— 许愿瓶 chips aria-pressed+role=group
 13. js.thread_dedup          —— data-thread 点击 inflight 去重
 14. html.autocomplete        —— 主表单 autocomplete 属性
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


with open(os.path.join(ROOT, "web/static/styles.css"),
          encoding="utf-8") as _f:
    CSS = _f.read()
with open(os.path.join(ROOT, "web/static/app.js"),
          encoding="utf-8") as _f:
    JS = _f.read()
with open(os.path.join(ROOT, "web/static/index.html"),
          encoding="utf-8") as _f:
    HTML = _f.read()

# --- 1. 全局 hidden 守卫 -----------------------------------------------------------
check("css.hidden_global_guard",
      "[hidden]{display:none !important;}" in CSS.replace(" ", "")
      or "[hidden]{display:none !important" in CSS,
      "灭 display 压 hidden bug 类")

# --- 2-6. 语义色交换 ------------------------------------------------------------------
for name, sel in [("css.accent_cta", ".daily-personal-cta"),
                  ("css.accent_meta_more", ".daily-meta-more"),
                  ("css.accent_hh_score", ".hh-score strong")]:
    _m = re.search(re.escape(sel) + r"\{[^}]*\}", CSS, re.DOTALL)
    check(name, _m and "var(--accent-ink)" in _m.group(0),
          "accent→accent-ink")
_sp = re.search(r"\.sign-peek\{[^}]*\}", CSS, re.DOTALL)
check("css.signpeek_tap",
      _sp and "var(--accent-ink)" in _sp.group(0)
      and "var(--tap)" in _sp.group(0),
      "文字色+触控下限")
check("css.pill_ji",
      ".hl-pill-ji{color:var(--rose-deep)" in CSS, "3.2:1→达标")

# --- 7-9. 触控下限 --------------------------------------------------------------------
check("css.trback_width", ".tr-back{width:40px" in CSS, "34→40px")
check("css.theme_toggle",
      re.search(r"\.theme-toggle\{[^}]*width:44px", CSS, re.DOTALL), "40→44")
check("css.daily_retry_tap",
      ".daily-retry{padding:4px 14px;min-height:var(--tap)" in CSS, "36→--tap")

# --- 10. 打印隐藏 -----------------------------------------------------------------------
check("css.celeb_print",
      re.search(r"@media print[^}]*\{(?:[^}]|\}[^@])*\.celeb-backdrop",
                CSS, re.DOTALL) or ".celeb-backdrop" in
      CSS[CSS.index("@media print"):CSS.index("@media print") + 1500],
      "进 print 隐藏表")

# --- 11. huangli 手输校验 ------------------------------------------------------------------
_hl = re.search(r"y = num\('hl_year'\).*?\n  \}", JS, re.DOTALL)
check("js.hl_date_validate",
      _hl and "_badRange('hl_year', 1900, 2100)" in _hl.group(0)
      and "_badYmdField('hl_year'" in _hl.group(0),
      "年界+日期有效性本地拦")

# --- 12. 许愿瓶 aria ------------------------------------------------------------------------
check("js.wish_aria",
      'role="group" aria-label="愿望分类"' in JS
      and 'aria-pressed="' in JS.split("ck-wish-cats")[1][:800]
      and "setAttribute('aria-pressed'" in JS,
      "chips 选中态进无障碍树")

# --- 13. data-thread 去重 ----------------------------------------------------------------------
check("js.thread_dedup",
      re.search(r"threadBtn\.dataset\.inflight === '1'.*?"
                r"showThread\(threadBtn\.dataset\.thread\)\.finally",
                JS, re.DOTALL),
      "连点去重+finally 复位")

# --- 14. autocomplete -----------------------------------------------------------------------------
check("html.autocomplete",
      all(x in HTML for x in ['autocomplete="bday-year"',
                              'autocomplete="bday-month"',
                              'autocomplete="bday-day"',
                              'autocomplete="family-name"']),
      "生日三元组+姓氏")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
