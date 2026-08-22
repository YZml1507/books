# Implementation Plan: 007 — 首页信息架构

**Branch**: `007-home-ia`（单 commit 直接落 main，R193b 先例）
**Created**: 2026-08-22
**Spec**: [spec.md](spec.md)
**Constitution Check**: 
- 第五条领土：只动 `web/static/**`（优化轨独占）+ `web/selftest.py`（优化轨）。
  probes/、specs/*/spec.md 既有文件零触碰；本 spec 目录为本轮新建
  （specs/006 先例：402e586 由优化轨自建）。
- 第六条 SDD：spec → plan → tasks → 代码，四件套本轮一次补齐（单轨授权轮惯例，
  同 006）。
- 第三条红线：无内容生成、无引用改动——纯 DOM 结构调整。
- 闸门：收尾照 R133a/R193b 电池口径全量复跑。

## 技术上下文

现状（实测）：
- `web/static/index.html:60-89`：`.func-grid#funcGrid` 平铺 8 张
  `.func-card[data-view]`，顺序 bazi→read→tarot→huangli→qiming→taohua→liuyao→hehun。
- `app.js initViews()`（2100 行附近）：`querySelectorAll('.func-card')`
  绑定 click/keydown → `showView(dataset.view)`。**不依赖 #funcGrid 容器、
  不依赖卡片父级结构**——分组后事件绑定天然继续生效。
- 探针依赖盘点：
  - probe_ui_smoke：经 `.func-card[data-view='X']` 点击导航，与容器无关；
  - probe_ui_baseline / probe_first_screen：量首页性能/首屏文案，与卡片顺序无关；
  - pro_render_baseline.json：钉三个结果视图，不钉首页结构；
  - web/selftest.py `home` 断言仅查 HTML 状态码与 content-type。
  - **结论：零冻结基线钉 funcGrid 内部结构，无需重冻任何基线。**
- CSS：styles.css `.func-grid` grid 布局 + 每卡 `--card-accent` 主题色
  （223-230 行按 data-view 定制，与位置无关，重排不影响配色）。

## 方案（对应 spec §2）

index.html 把单个 funcGrid 改为三段：

```
<div class="ia-group" data-group="ask">      <!-- 测一测 -->
  <div class="ia-label">🔮 测一测</div>
  <div class="func-grid">
    bazi · qiming · hehun · taohua · tarot · liuyao · huangli（卡元素原样搬入）
  </div>
</div>
<div class="ia-group" data-group="read">     <!-- 读书 -->
  <div class="ia-label">📜 读书</div>
  <div class="func-grid"><div class="func-card" data-view="read">…</div></div>
</div>
```

「今日」簇 = 现有每日运势卡本身，不加壳不加标签（spec §2 表第一行），
功能组从它下方开始。

CSS 增量（styles.css 追加，不改既有规则）：
```css
.ia-group{margin-top:28px;}
.ia-label{font-size:15px;font-weight:600;color:var(--secondary);
  margin:0 0 12px 2px;letter-spacing:.5px;}
```
对比度：--secondary 现值需 ≥AA（4.5:1）——实现时用 getComputedStyle 实测，
不足则该标签用 --text 色并记 D 决策。

## 数据模型 / 接口契约

无。纯前端静态结构调整。

## Quick Start 验证

```
BOOKS_LLM_DISABLE=1 <py> web/selftest.py          # 含新增 ia.* 断言全绿
BOOKS_LLM_DISABLE=1 <py> probes/probe_ui_smoke.py # 经卡片导航全 PASS
<py> probes/probe_first_screen.py                 # 首屏判据不回退
```

## 回滚

单 commit `git revert` 即回到 R193b 视觉与结构（spec §4）。
