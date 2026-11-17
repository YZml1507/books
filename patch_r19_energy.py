#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R19 首页日卡审计：同卡两个「今日能量」——标签消歧。

结论文据（服务端实测 + 代码追溯）：
  · 首屏 daily-main 的「今日能量 75」= 日辰级次哈希：
      app.js:6093  var _energy = _lvR[0] + _sdH % (_lvR[1]-_lvR[0]+1)
      _lvR 由当日级次定档（吉 [82,95] / 小吉 [68,81] / 凶 [30,50] / 平 [55,72]），
      _sdH = hash(日期|生日)。确定性、不落缓存不落库（注释原话）。
  · 卡尾 daily-mine-block 的「今日能量 67 分」= 你的盘对今日干支：
      services.py:15595  _personal["energy"] = {score: _energy_for(今日干支, 日主, 日支, 月支)}
      42–96 钳位。这是 R3621 刻意置顶的个人分。
  → 两套算法共用一个标签，用户读成「同一个东西两个数」，是 bug 观感。

产品自身早已有「通版 / 对你」两套口径：
  R3245 注释「通判 level 是大家同款，『对你』这层才是你的盘与今天的对位」；
  开运色也标注「（今日通版）」。唯独能量漏了这层区分。
本补丁把卡尾那个补上「对你·」前缀：首屏那个留作「今日能量」头条读数，
深的那个明示是「你的盘」视角。不删任何功能、不改任何算式。
"""
import sys, io

PATH = "/opt/books/app/web/static/app.js"

OLD = """      var _en = j.personal.energy;
      if (_en && _en.score) {
        _pc2.push('<span class="daily-energy">' +
          '⚡ 今日能量 ' + esc(_en.score) + ' 分</span> ' +
          esc(_en.line || ''));
      }
"""

NEW = """      var _en = j.personal.energy;
      if (_en && _en.score) {
        /* R19（首页日卡审计）：同卡曾并存两个「今日能量」——首屏那个是
         * 日辰级次哈希（通版档位内按 日期|生日 取数，app.js:6093），
         * 这个是日主对今日干支的冲合会局（services.py:15595，42–96）。
         * 同标签不同算法，用户读成 bug。产品既有「通版/对你」口径
         * （R3245、开运色「今日通版」），这里补「对你·」前缀，
         * 两数各归其位；算法一律不动。 */
        _pc2.push('<span class="daily-energy">' +
          '⚡ 对你·今日能量 ' + esc(_en.score) + ' 分</span> ' +
          esc(_en.line || ''));
      }
"""

def main():
    with io.open(PATH, encoding="utf-8") as f:
        src = f.read()
    n = src.count(OLD)
    if n != 1:
        sys.stderr.write("FAIL: anchor count=%d (expect 1)\n" % n)
        return 2
    if "对你·今日能量" in src:
        sys.stderr.write("FAIL: already patched\n")
        return 3
    with io.open(PATH, "w", encoding="utf-8") as f:
        f.write(src.replace(OLD, NEW, 1))
    print("app.js PATCHED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
