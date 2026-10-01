# R20 排雷轮审计（2026-10-01）

> 本轮不新增产品面，只做 R16–R19 收尾后的全站同款扫描。

## 1. 动态 handler 覆盖

- 扫描范围：`web/static/app.js` 中所有 `on('id', …)` 注册、
  `var x = el('id')` 后 `x.addEventListener('click', …)` 的裸绑定，
  以及 `el('id').addEventListener('click', …)` 直链式绑定。
- 工具：`probes/probe_ui_smoke.py` `gate:on_coverage`。
- 结果：**PASS**。R19 新增 `rgXhs` 按钮已补入 `NO_CASE` 豁免表。
- 结论：当前 28 个 `on()` 注册与新增裸绑定均已在 `BUTTON_CASES`
  或 `NO_CASE` 中有登记。

## 2. esc / innerHTML 审计

- 扫描范围：单 `;` 结束的 `innerHTML` 赋值由 `innerHTML_esc` 闸覆盖。
- 额外抽查：R17 `mood-jar-fold`、R18 `chat-empty-moodjar`、
  R19 `renge-actions` 三处多行 HTML builder，动态文本均过 `esc()`。
- 结果：`probe_ui_smoke` `gate:innerHTML_esc` **PASS**；抽查无新增裸字段注入。
- 结论：多行 builder 仍维持 `esc()` 纪律，未发现未转义的用户/后端文本。

## 3. sessionStorage / localStorage 边界复扫

- 新增键：`moodjar:total`、`moodjar:unlocked`（R17）。
- 处理：
  - `localStorage` 备份白名单 `_PREF` 已加 `moodjar:` 前缀；
  - `historyWipe` `localStorage` 清除正则已加 `k.indexOf('moodjar:') === 0`；
  - `sessionStorage` 清除列表仍覆盖 `ly:lastq`/`ly:lastcast`/`shareBy:*`/
    `lastResult:*` 等，无新增 session 前缀。
- 结果：`probe_ui_smoke` 隐私清理用例 **PASS**；`selftest` 375 checks **PASS**。

## 4. 待入下轮决策

- `web/services.py` 5082 行单文件仍是架构债（本轮未拆，属产品功能轮之外）。
  下轮调研后决定是否作为 R21 或 R22 重构主轴。
