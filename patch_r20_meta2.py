#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20-3：让「+N 条/收起」钮恒定紧贴药丸流（CYCLE5_PLAN 任务三补刀）

R20-2 把 #dailyMetaMore 移出 .daily-meta 并插到 metaRow.nextSibling，
但实测 390 档发现：dailyTomorrow / dailyTomorrowShare 也在
`metaRow.nextSibling` 插入（app.js:7298），且晚于 MORE 创建 → 把收纳钮
挤到「明天」块之后，与它管的那排药丸隔了 112px（仍是「乱」）。

本补丁在 dailyTomorrowShare 收尾后补一次 _dailyMetaCap()——
该函数 else 分支（R20-2 加的）会把 MORE 重排回 metaRow 正后方。
后续 dailyPersonal/dailyQianWin 走 _dailyMetaItem，其末尾本就调
_dailyMetaCap()，同样会把 MORE 拉回紧贴药丸流的位置。

幂等性：_dailyMetaCap 每次现查节点、重打 capped 标、只增改 MORE，
重复调用无副作用（本就是每个 _dailyMetaItem 的收尾动作）。
≤5 粒时它早退（隐藏 MORE），不重排——不可见即无需归位。
"""
import io, sys

APP = "/opt/books/app/web/static/app.js"

OLD = """    if (_tmsEl) {
      var _tmOk = !!(tm && tm.outfit && tm.outfit.tiers &&
                     tm.outfit.tiers.length);
      _tmsEl.hidden = !_tmOk;
      _tmsEl._tm = _tmOk ? tm : null;
    }"""

NEW = """    if (_tmsEl) {
      var _tmOk = !!(tm && tm.outfit && tm.outfit.tiers &&
                     tm.outfit.tiers.length);
      _tmsEl.hidden = !_tmOk;
      _tmsEl._tm = _tmOk ? tm : null;
    }
    /* R20（用户直报）：dailyTomorrow/dailyTomorrowShare 也在
     * metaRow.nextSibling 落座且晚于收纳钮创建——实测 390 档把
     * 「+N 条」挤到「明天」块之后，跟它管的那排药丸隔了 112px。
     * 补一次收口：_dailyMetaCap 的 else 分支会把钮重排回药丸流
     * 正后方，控制钮与受控粒恒相邻。 */
    if (typeof _dailyMetaCap === 'function') _dailyMetaCap();"""


def main():
    with io.open(APP, "r", encoding="utf-8") as f:
        a = f.read()
    n = a.count(OLD)
    if n != 1:
        sys.exit("FAIL: anchor count=%d（预期 1）" % n)
    if "把钮重排回药丸流" in a:
        sys.exit("FAIL: 已打过 R20-3")
    a = a.replace(OLD, NEW, 1)
    with io.open(APP, "w", encoding="utf-8") as f:
        f.write(a)
    if a.count("if (typeof _dailyMetaCap === 'function') _dailyMetaCap();") != 1:
        sys.exit("FAIL: 打后自检未命中新增调用")
    print("app.js PATCHED (R20-3 收纳钮恒定紧贴药丸流)")


if __name__ == "__main__":
    main()
