#!/usr/bin/env python3
"""R2513 回归钉扎——app_poster/app_research 懒载 chunk 审查四修。

钉扎项：
  1. poster.inflight_flag    —— _POSTER_INFLIGHT 模块旗标存在
  2. poster.inflight_gate    —— downloadPoster 入口吞点在途
  3. poster.inflight_release —— finally 双分支复位
  4. poster.on_return        —— 六个 on('shareX') 处理器 return promise
  5. poster.chip_collect     —— _posterTextCollect 收 s.chip
  6. poster.blob_revoke_safe —— a.click() 包 try/finally
  7. thread.gen_at_entry     —— doThread 入口抬 _TR_VIEW_GEN
  8. thread.gen_paint_check  —— paint 前 _g!==_TR_VIEW_GEN 校验
  9. thread.gen_fail_check   —— catch/failWithRetry 前同款校验
 10. thread.del_inflight     —— deleteThread DELETE 在途闸+复位
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


with open(os.path.join(ROOT, "web/static/app_poster.js"),
          encoding="utf-8") as _f:
    PJ = _f.read()
with open(os.path.join(ROOT, "web/static/app_research.js"),
          encoding="utf-8") as _f:
    RJ = _f.read()
with open(os.path.join(ROOT, "web/static/app.js"),
          encoding="utf-8") as _f:
    AJ = _f.read()

# --- 1-3. inflight 旗标 ----------------------------------------------------------
_dl = re.search(r"async function downloadPoster\(j, view\).*?\n\}", PJ, re.DOTALL)
check("poster.inflight_flag", "_POSTER_INFLIGHT" in PJ,
      "模块旗标声明")
check("poster.inflight_gate",
      _dl and "if (_POSTER_INFLIGHT) return" in _dl.group(0),
      "入口吞点")
check("poster.inflight_release",
      _dl and "_POSTER_INFLIGHT = false" in _dl.group(0),
      "finally 复位")

# --- 4. on() 处理器 return --------------------------------------------------------
_missing = [v for v in ["bazi", "liuyao", "qiming", "taohua", "tarot", "hehun"]
            if f"return downloadPoster(j, '{v}')" not in AJ]
check("poster.on_return", not _missing,
      f"6/6 return（缺：{_missing}）")

# --- 5. chip 收集 ------------------------------------------------------------------
_tc = re.search(r"function _posterTextCollect.*?\n\}", PJ, re.DOTALL)
check("poster.chip_collect", _tc and "_pStr(s.chip)" in _tc.group(0),
      "s.chip 进预热集")

# --- 6. blob revoke 安全 -------------------------------------------------------------
check("poster.blob_revoke_safe",
      re.search(r"try \{ a\.click\(\); \} finally", PJ),
      "click 包 try/finally")

# --- 7-9. doThread 代际 ---------------------------------------------------------------
_dt = re.search(r"async function doThread\(\).*?\n\}", RJ, re.DOTALL)
_dt_body = _dt.group(0) if _dt else ""
check("thread.gen_at_entry",
      re.search(r"function doThread\(\) \{\s*"
                r"(?:/\*.*?\*/\s*)*var _g = \+\+_TR_VIEW_GEN",
                _dt_body, re.DOTALL),
      "入口抬号")
check("thread.gen_paint_check",
      "if (_g !== _TR_VIEW_GEN) return;\n    paint('threadResult'" in _dt_body,
      "paint 前校验")
check("thread.gen_fail_check",
      "if (_g !== _TR_VIEW_GEN) return;\n    failWithRetry" in _dt_body,
      "failWithRetry 前校验")

# --- 10. deleteThread 在途闸 ----------------------------------------------------------
_del = re.search(r"async function deleteThread.*?\n\}", RJ, re.DOTALL)
_del_body = _del.group(0) if _del else ""
check("thread.del_inflight",
      "dataset.inflight === '1'" in _del_body
      and _del_body.count("dataset.inflight = ''") >= 2,
      "在途闸+双分支复位")

print("=" * 50)
print(f"{passed + failed} checks, {failed} failed")
sys.exit(1 if failed else 0)
