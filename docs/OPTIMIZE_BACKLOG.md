# OPTIMIZE BACKLOG — 优化待办池

**所有权（宪法第五条）**：审查轨独占写。优化轨只读。

**本文件的存在理由**：给 MINOR / NIT 一个不阻塞阶段推进的去处。
若允许体验瑕疵和纯偏好进 `AUDIT_FINDINGS.md` 的 OPEN 清单，
`REPAIR → OPTIMIZE` 闸门将永远打不开——审查轨只要还在跑，
总能找出下一个「这里可以更好」。这是本协作模型唯一会死锁的地方。

REPAIR 阶段只**收集**不实施。翻到 OPTIMIZE 后，本池条目由审查轨
汇编进 `specs/003-youth-ui-revamp/spec.md`。

---

## 条目格式

```markdown
### B-<seq> 一句话标题
- 类型：性能 | 视觉 | 交互 | 无障碍 | 功能扩展
- 现状：<实测事实，附命令>
- 设想：<想达到什么，不写怎么实现>
- 可测量性：<如何客观验证；无法测量则写「需回滚保障」>
- 来源：R<n>a 轮次 / MINOR 降级 / 主动勘查
```

## spec 准入门槛（宪法第六条 + 全自动纪律）

写进 `spec.md` 的每条要求必须满足其一，否则不许写：

**(a) 可自动测量。** 首屏渲染时间、API p95 延迟、静态资源体积、
375px 视口无横向滚动、点击目标 ≥44px、对比度符合 WCAG AA、
尊重 `prefers-reduced-motion`、动画期间无 >50ms 长任务。

注意后几条看似「体验」实为**精致感的客观代理指标**：
廉价感往往就来自对比度不足、点击区过小、动画掉帧。

**(b) 可回滚。** 视觉方案必须能一键切回旧样式（如 CSS 变量主题切换）。
这样审查轨自主选定的审美方向即使用户事后不认可，也不构成损失——
这是「全自动决策」得以成立的前提。

审美类决策由审查轨自主拍板，但必须在 `docs/DECISIONS.md` 用 `D-<n>a`
记录至少两个候选与否决理由。不记录就等于剥夺了用户的事后否决权。

---

## 现成素材（交接窗口实测，可直接用）

- **`web/static/animotion/` 有 287KB 动画 CSS 完全没接线。**
  `animotion.css` 84KB、`keyframes.css` 115KB、`keyframes-part2.css` 84KB、
  `utilities.css` 5.8KB。实测 `index.html` **零个外部资源引用**
  （`grep '<link\|<script src' web/static/index.html` 无命中）。
  已在仓库内，用它**不算引入新外部依赖**（不撞宪法第二条红线第 3 项）。
- **`vendor/ui-ux-pro-max/`** 是一整套 UI/UX 设计 skill 集合（含
  banner-design 等子 skill 与中英文 README），可作设计参考。
- `specs/` 现有 `001-books-audit-merge`、`002-product-rebrand`，下一编号 `003`。

## 已知可优化项（交接窗口勘查，未验证优先级）

### B-001 web/app.py 单文件 2108 行，其中 912 行是塞在 __main__ 的自测
- 类型：性能（可维护性）
- 现状：`(Get-Content web/app.py | Measure-Object -Line).Lines` = 2108；
  `__main__` 块从 1365 行到 2277 行
- 设想：已在 REPAIR 阶段作为重构任务派给优化轨，非本池条目，此处仅登记
- 可测量性：单文件行数 < 300；`web/selftest.py` 独立可跑
- 来源：主动勘查

### B-002 index.html 单文件 1485 行（CSS 396 行 + JS 643 行内联）
- 类型：性能
- 现状：`web/static/index.html` 74KB 单文件，无缓存分离
- 设想：拆 `app.js` + `styles.css`，浏览器可独立缓存
- 可测量性：首屏 HTML 体积下降；重复访问命中缓存
- 来源：主动勘查（REPAIR 阶段已派给优化轨）

### B-003 每日运势 noble 字段用出生年生肖，语义可疑
- 类型：功能扩展
- 现状：`web/app.py` `api_daily` 调 `_chinese_zodiac(d.year)`，
  `d` 是**当天日期**而非用户生日——「贵人属相」取的是今年的生肖
- 设想：明确「贵人属相」的定义并与算法对齐，或改名为准确的措辞
- 可测量性：需先定义正确语义，属需求澄清而非纯审美
- 来源：主动勘查
