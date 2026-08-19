# Implementation Plan: 知命 — 产品重新品牌化

**Branch**: `002-product-rebrand` | **Date**: 2026-08-19 | **Spec**: `specs/002-product-rebrand/spec.md`

**Input**: Feature specification from `specs/002-product-rebrand/spec.md`

---

## Summary

将「古籍智慧助手」重新品牌化为「知命」——一个有名字、有态度、有审美的年轻化产品。改造覆盖前端（品牌命名 + 视觉设计 + 交互）、后端（LLM 风格 + 新 API 端点 + 外部资讯包装）、数据库（扩展 user_prefs/daily_cache/favorites 表）。

## Technical Context

**Language/Version**: Python 3.14.7, HTML/CSS/JS (vanilla, no build step)
**Primary Dependencies**: FastAPI, SQLite, httpx (LLM), tsparticles CDN, tailwind CDN
**Storage**: corpus.db (55.7MB, 不动), knowledge.db (扩展 3 张新表)
**Testing**: 13 道闸门 + web --selftest (125 checks)
**Target Platform**: Windows 桌面应用（PyInstaller 单文件 exe）
**Constraints**: 离线可用（语料本地索引），不引入 npm/构建工具，LLM 调用需要 API key

---

## Constitution Check

*GATE: 本节逐条评估宪法原则 I–VI*

### I. Fact-First Discipline ✅
- 所有设计决策基于小红书塔罗/八字博主风格的实际观察，不是凭空想象
- LLM 风格改造后通过实际 API 调用验证，不是口头描述
- 13 道闸门仍然全绿通过实际命令验证

### II. Red-Line Governance ✅
- 不删除 data/raw/ 或 data/external/ 下的原始语料
- 不放宽任何验收闸门
- 不引入新的 npm/前端构建工具（只用 CDN + 纯 HTML/CSS/JS）
- LLM 调用已按 GOAL.md §5 豁免

### III. Architecture Integrity ✅
- corpus.db 不动（学术检索索引保持不变）
- knowledge.db 只追加新表，不修改现有表
- 分层架构不变：Source → Parse → Normalize → Structure → Quality Gate → Index → Agent → Output
- LLM 解读层改造不改变引用与生成的分离原则（G7 纪律不变）

### IV. Gate-Driven Verification ✅
- 改造后 13 道闸门 + web --selftest 全绿
- 新增 API 端点有 selftest 覆盖

### V. Dual-Track Isolation ✅
- 本次改造在 main 分支（优化轨）直接执行
- 不涉及审查轨领土（scripts/, probes/）

### VI. Specification-First Workflow ✅
- spec.md 先于 plan.md 先于代码

---

## Project Structure

### 前端改造 (web/static/index.html)

#### 设计令牌

```css
:root{
  /* 奶油金箔风 */
  --bg:        #F5EFE6;       /* 暖奶油底 */
  --card:      #FFFFFF;       /* 纯白卡片 */
  --text:      #2A2420;       /* 深棕文字 */
  --primary:   #B8860B;       /* 金箔金 */
  --secondary: #9C6B3F;       /* 暖棕 */
  --accent:    #C43E3E;       /* 干玫瑰红（运势凶时） */
  --good:      #5B8C5A;       /* 墨绿（好运） */
  --border:    #E8DCC8;       /* 暖金细线 */
  --shadow:    0 8px 32px rgba(184,134,11,.15);

  --font-serif:  "Noto Serif TC","Songti SC","SimSun",serif;
  --font-sans:   "PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif;
  --font-mono:   "Georgia",serif;  /* 排盘数字用 */

  --radius: 16px;
}
```

#### 布局结构

```
┌──────────────────────────────────────────────┐
│  🔮 知命              知书·知命·知天机       │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │  🌟 今日运势                              │ │
│  │  ★★★★☆  平    贵人：鼠  宜：合作 忌：争执 │ │
│  │  今天适合做决定，...                        │ │
│  │                            [查看完整解读]   │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  [排盘]  [读书]  [塔罗]  [黄历]               │
│  [起名]  [择日]  [桃花]  [消息]               │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │  📜 最近的解读                            │ │
│  │  · 08-19  八字排盘    庚午年 丁亥月 ...    │ │
│  │  · 08-18  塔罗占卜    正位·命运之轮       │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

#### 关键 CSS 组件

| 组件 | 选择器 | 特征 |
|---|---|---|
| 品牌标题 | `.brand-title` | 衬线大字 + 金箔渐变文字 + 小号 tagline |
| 每日运势卡 | `.daily-card` | 白卡 + 金边 + 光晕 hover + 星级评分 |
| 功能卡片 | `.func-card` | 白卡 + 圆角 + 图标 + 标题 + 描述 + hover 上浮 |
| 排盘结果卡 | `.result-card` | 金边 + 衬线排版 + 等宽数字 |
| 塔罗牌卡 | `.tarot-card` | 翻牌动画 + 背面金箔纹理 |

#### 塔罗翻牌动画

```css
@keyframes flip-card {
  0%   { transform: rotateY(0deg); }
  50%  { transform: rotateY(90deg); }
  100% { transform: rotateY(360deg); }
}
```

### 后端改造 (web/app.py + src/guji/llm_reader.py)

#### 新增 API 端点

```python
# 每日运势
@app.get("/api/daily")
async def api_daily():
    # 返回今日运势等级、一句话、贵人、宜忌
    # 命中 daily_cache 表，不重复调用 LLM

# 功能卡片数据
@app.get("/api/widget")
async def api_widget():
    # 返回各功能模块的卡片数据（图标、标题、描述、最近使用）

# 塔罗抽牌
@app.post("/api/tarot/draw")
async def api_tarot_draw(req: TarotDrawRequest):
    # 调用 tarot.py 抽牌 + LLM 解读

# 分享卡片
@app.get("/api/share/{share_type}/{share_id}")
async def api_share(share_type: str, share_id: str):
    # 返回可分享的结果摘要

# 用户偏好
@app.get("/api/user/prefs")
async def api_user_prefs():
    # 返回用户主题偏好、收藏、最近使用
```

#### LLM 解读风格改造

**当前 system prompt**（学术腔）：
```
"你是古籍命理资料的研究助理……"
```

**改造后 system prompt**（博主腔）：
```
你是一个温暖、有同理心的命理博主，像在小红书上发笔记一样跟用户说话。

风格要求：
1. 结论先行：第一句就给出明确运势判断（如"今天整体平顺，适合做决定"），不以"所依据的原文引文"开头
2. 生活化比喻：把命理术语翻译成"人话"（如"感情宫位逢冲，不用刻意追，缘分自然来"）
3. 适度 emoji：🔮✨🌟🍀🌙，不超过 5 个
4. 口语化：用"你"不用"您"，用"挺"不用"甚"，像朋友聊天
5. 引用只写书名：如《三命通會》，不展示内部编号
6. 结尾可以有一句"温暖的话"——不是命理结论，是给用户的鼓励
```

### 数据库改造 (knowledge.db)

```sql
-- 用户偏好（主题、收藏、最近使用）
CREATE TABLE IF NOT EXISTS user_prefs (
    key   TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);

-- 每日运势缓存（避免重复调用 LLM）
CREATE TABLE IF NOT EXISTS daily_cache (
    date        TEXT PRIMARY KEY,    -- 'YYYY-MM-DD'
    bazi_result TEXT,                -- JSON
    tarot_result TEXT,               -- JSON
    created_at  TEXT NOT NULL
);

-- 收藏
CREATE TABLE IF NOT EXISTS favorites (
    id         INTEGER PRIMARY KEY,
    type       TEXT NOT NULL,        -- bazi | tarot | book | thread
    ref_id     TEXT NOT NULL,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### 外部资讯改造 (src/guji/external.py)

当前：返回原始 news feed
改造：包装为运势风格内容，按日期返回"今天需要注意什么"

---

## Quickstart

### 验证步骤

```powershell
cd C:\Users\Lenovo\Desktop\projects\books

# 1. 启动服务
python web_launcher.py

# 2. 浏览器访问
http://localhost:8123/

# 3. 验证品牌
# 标题应显示「知命」而非「八字命理检索」

# 4. 验证每日运势
# 首页应有每日运势大卡片

# 5. 验证 API
curl http://localhost:8123/api/daily
curl http://localhost:8123/api/widget

# 6. 跑闸门
.\.venv\Scripts\python.exe scripts/check_quality.py
.\.venv\Scripts\python.exe scripts/build_index.py
.\.venv\Scripts\python.exe scripts/verify_index.py
# ... 全部 13 道
```

### 预期结果

```
首页标题          → 「知命」
每日运势卡片      → 可见
功能卡片平铺      → 可见
13 道闸门         → ALL PASS
web --selftest    → PASS
```