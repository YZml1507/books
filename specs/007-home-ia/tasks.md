# Tasks: 007 — 首页信息架构

**Format**: `- [ ] [TaskID] [P?] [Story?] Description with file path`
**依赖**: T1 → T2 → T3 →（T4 ∥ T5）→ T6

- [x] [T1] [P] [US-] web/static/index.html：funcGrid 拆三段 ia-group（测一测 7 卡按 bazi→qiming→hehun→taohua→tarot→liuyao→huangli、读书 read 单卡），卡元素原样搬入零改写，data-view 与事件语义不变
  实测：`grep -o 'data-view="[a-z]*"' web/static/index.html` → 8 卡序正确；initViews 的 querySelectorAll('.func-card') 不依赖容器结构，事件绑定零改动。
- [x] [T2] [P] [US-] web/static/styles.css：追加 .ia-group/.ia-label 规则（不改既有规则）；实测标签对比度 ≥AA
  实测：Playwright getComputedStyle + WCAG 公式 = 5.38:1（≥4.5 AA，--secondary #815934 对 --bg）。
- [x] [T3] [P] [US-] web/selftest.py：新增 home.ia 断言组——入口总数=8、簇标签存在、测一测簇内 data-view 序=spec §2 表、桃花合婚相邻；只增不减
  实测：`BOOKS_LLM_DISABLE=1 <py> web/selftest.py` → PASS 157 checks（156→157，home.ia 新增自动入 regress 基线）。
- [x] [T4] [S] [US-] 复跑 probes/probe_ui_smoke.py 全 PASS + probes/probe_first_screen.py 不回退（环境判据照 B-018 口径）
  实测：probe_ui_smoke PASS（history 235→235 零残留）；probe_first_screen PASS（首屏大白话/古籍占比判据全过）。
- [x] [T5] [S] [US-] 375px 手测截图：分组渲染正常、无横向溢出（logs/ 留档）
  实测：logs/ia_007_mobile_375.png；双标签可见=True、横向溢出 0px、总卡数 8。
- [x] [T6] [S] [US-] 收尾链：BOOKS_LLM_DISABLE=1 全量电池复跑全 0 → 台账 §133 append → DECISIONS.md D-254b 记分组方案取舍 → commit+push main
  实测：34 条电池全 EXIT=0（gates_r194b）；台账 §133；D-254b。

## 完成定义

spec.md §3 判据 1–9 全部成立且各附实测输出。
