# Feature Specification: 知命 — 产品重新品牌化

**Feature Branch**: `002-product-rebrand`
**Created**: 2026-08-19
**Status**: Draft
**Input**: User description: "项目不够吸引人，不论从项目本身还是前端设计都不够吸引人，吸引不了年轻人。需要重新思考命名、定位、前端设计、后端 API、数据库，整体提升产品吸引力。"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 品牌重塑：从"古籍智慧助手"到"知命" (Priority: P1)

**作为**年轻用户，**我想要**一个有名字、有态度、有审美的产品，**以便**觉得这是一个"懂我的"工具，而不是一个政府文化项目。

**Why this priority**: 项目当前名称"古籍智慧助手"和前端标题"八字命理检索"都缺乏吸引力。小红书上的塔罗/八字博主都有鲜明的个人品牌，用户信任的是"博主"而不是"工具"。产品需要人格化。

**Independent Test**: 打开浏览器访问 `http://localhost:8123/`，看到的是「知命」品牌首页，而非"八字命理检索"。

**Acceptance Scenarios**:

1. **Given** 服务已启动，**When** 打开首页，**Then** 看到「知命」标题 + tagline「知书 · 知命 · 知天机」
2. **Given** 首页已加载，**Then** 顶部有一个"每日运势"大卡片，显示运势等级、一句话解读、贵人属相、宜忌
3. **Given** 首页已加载，**Then** 下方是功能卡片平铺（排盘/读书/塔罗/黄历/起名/择日/历史/消息），不是表单填写
4. **Given** 点击任意功能卡片，**Then** 进入对应功能，有明确的视觉反馈

### User Story 2 - LLM 解读风格改造：从学术腔到博主腔 (Priority: P1)

**作为**年轻用户，**我想要**命理解读像小红书博主发的笔记一样自然、温暖、有同理心，**以便**觉得这个工具"懂我"而不是"在交作业"。

**Why this priority**: 当前 LLM system prompt 是"古籍命理资料的研究助理"，输出风格偏学术。小红书博主风格是"朋友聊天 + 生活化比喻 + emoji 点缀 + 结论先行"。这是产品人格化的核心。

**Independent Test**: 调用 `/api/bazi` 并传入测试数据，检查返回的 `llm_out.text` 是否符合博主风格。

**Acceptance Scenarios**:

1. **Given** 调用 `/api/bazi`，**Then** 解读以明确的运势判断开头（如"今天整体平顺，适合做决定"），不是以"所依据的原文引文"开头
2. **Given** 解读文本，**Then** 使用生活化比喻（如"感情像春天的风，不用刻意追"），不是术语堆砌
3. **Given** 解读文本，**Then** 适度使用 emoji（🔮✨🌟），不滥用
4. **Given** 解读文本，**Then** 引用来源只写书名（如《三命通會》），不展示内部检索编号

### User Story 3 - 新增产品化 API 端点 (Priority: P2)

**作为**前端开发者，**我想要**以下产品化 API 端点，**以便**实现每日运势卡片、功能卡片网格、分享卡片等产品功能。

**Why this priority**: 当前 API 全是原始数据端点（/api/bazi, /api/search 等），缺少产品化的"每日运势""功能入口""分享"等接口。前端无法直接消费。

**Independent Test**: 调用每个新端点，验证返回数据结构正确。

**Acceptance Scenarios**:

1. **Given** `GET /api/daily`，**Then** 返回 `{level: "平", summary: "...", noble: "鼠", do: "...", dont: "...", date: "2026-08-19"}`
2. **Given** `GET /api/widget`，**Then** 返回各功能模块列表 `[{id, icon, title, desc, recent: [...]}]`
3. **Given** `POST /api/tarot/draw`，**Then** 返回抽牌结果 `{card, orientation, meaning, interpretation}`
4. **Given** `GET /api/share/{type}/{id}`，**Then** 返回可分享的结果摘要 `{title, subtitle, content, image_color}`
5. **Given** `GET /api/user/prefs`，**Then** 返回用户偏好 `{theme: "cream", favorites: [...], recent: [...]}`

### User Story 4 - 数据库扩展 (Priority: P2)

**作为**后端开发者，**我想要**在 knowledge.db 中新增用户偏好、每日缓存、收藏三个表，**以便**支撑产品化功能的数据持久化。

**Why this priority**: 当前 knowledge.db 只有 derived/evidence/thread 三个表，都是为学术研究设计的。产品化需要用户偏好存储、每日运势缓存（避免重复计算）、收藏功能。

**Independent Test**: 查询新表，验证数据可以读写。

**Acceptance Scenarios**:

1. **Given** `user_prefs` 表，**Then** 可以存储和读取用户的主题偏好、最近使用的功能
2. **Given** `daily_cache` 表，**Then** 同一天的运势请求可以命中缓存，不重复调用 LLM
3. **Given** `favorites` 表，**Then** 用户可以收藏算命结果、读书笔记、塔罗牌阵

### Edge Cases

- **LLM 调用失败**：解读降级为只展示原文引文，不编造（G7 纪律不变）
- **每日缓存命中**：缓存只存当天，第二天自动失效
- **用户偏好不存在**：返回默认值（theme: "cream"）
- **分享链接过期**：分享数据存 7 天，过期返回 404
- **数据库迁移**：新表追加到 knowledge.db，不破坏现有表

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 品牌名称改为「知命」，tagline 为「知书 · 知命 · 知天机」
- **FR-002**: 前端首页改为"每日运势卡片 + 功能卡片平铺"布局
- **FR-003**: LLM 解读风格从学术腔改为博主腔（结论先行、生活化比喻、适度 emoji）
- **FR-004**: 新增 5 个产品化 API 端点（/api/daily, /api/widget, /api/tarot/draw, /api/share, /api/user/prefs）
- **FR-005**: knowledge.db 新增 user_prefs / daily_cache / favorites 三个表
- **FR-006**: 外部资讯包装为"每日运势"风格内容
- **FR-007**: 13 道闸门仍然全绿（改动不破坏学术检索能力）
- **FR-008**: 打包后单文件 exe 仍然可用（PyInstaller 不受影响）

### Key Entities

- **品牌**：名称「知命」、tagline、视觉令牌（底色/强调色/字体）
- **每日运势**：level（吉/平/凶）、summary、noble（贵人属相）、do/dont（宜忌）
- **功能卡片**：id、icon、title、desc、recent（最近使用）
- **用户偏好**：theme、favorites[]、recent[]
- **分享**：type、ref_id、title、subtitle、content、image_color、expires_at

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 首页加载后 3 秒内看到完整的「知命」品牌首页（含每日运势卡片）
- **SC-002**: LLM 解读风格改造后，解读文本以明确运势判断开头的比例 ≥ 90%
- **SC-003**: 5 个新 API 端点全部可用，返回数据结构正确
- **SC-004**: 新表读写正常，不影响现有 knowledge.db 功能
- **SC-005**: 13 道闸门 + web --selftest 仍然全绿
- **SC-006**: PyInstaller 打包后 exe 仍然可用

## Assumptions

- **A-001**: LLM API key 已配置（llm_config.json 或环境变量）
- **A-002**: tsparticles CDN 可用（粒子背景需要），加载失败时有降级方案
- **A-003**: 不引入新的 npm/前端构建工具，只用纯 HTML/CSS/JS + CDN
- **A-004**: knowledge.db 的现有表结构不动，只追加新表
- **A-005**: corpus.db 不动（学术检索索引保持不变）
- **A-006**: 用户已授权 LLM 调用（GOAL.md §5 红线已豁免）