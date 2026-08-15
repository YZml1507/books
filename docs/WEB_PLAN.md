# 网页端搭建方案（WEB_PLAN）

> 状态：方案（2026-08-15）。目标：把已实测可用的「生辰八字 → 排盘 → 命理书引用检索 → LLM 解读」能力开放为网页应用。

## 0. 现状（已实测，非口头结论）

| 能力 | 模块 | 接口 |
|---|---|---|
| 排盘（公历→四柱/日主/纳音/大运） | `src/guji/bazi.py` | `compute(y, m, d, h, gender) -> Bazi`（含 `render()`/`nayin`/`warn`） |
| 命理书 FTS 检索（9 部） | `src/guji/bazi_lookup.py` | `retrieve_fast(Bazi) -> [{work_id,title,layer,page_anchor,file,text,score}]` |
| bge 语义检索（向量缓存） | 同上 | `retrieve_semantic(Bazi) -> 同上` |
| LLM 白话解读（用户已授权） | `src/guji/llm_reader.py` | `available()` / `interpret(render_line, evidence, question)`，配置读 `llm_config.json`（已 gitignore） |
| 语料 | corpus.db 51,131 单元 · 9 部命理书 · 带文件+页锚点 | 只读 |

venv 现状：已有 `httpx`、`Jinja2`；**无** FastAPI/Flask/uvicorn/streamlit（网页端需新增依赖，属用户显式授权的项目方向）。

## 1. 架构（复用优先，新增最薄）

```
浏览器 (单页 HTML/JS)
   │  fetch POST /api/bazi
   ▼
web/app.py  (选型见 §2：FastAPI 或 Flask)
   ├─ 输入校验（年/月/日/时/性别；LLM 开关）
   ├─ bazi.compute ──────────────► 排盘坐标
   ├─ bazi_lookup.retrieve_fast ──► 引用证据（FTS）
   ├─ bazi_lookup.retrieve_semantic ─► 引用证据（bge，可选）
   └─ llm_reader.interpret ──────► LLM 解读（可选；KEY 只在服务端）
   ▼
JSON 响应 { paipan, evidence[], llm? }
```

设计原则：
- **后端无状态**：每个请求独立走「排盘→检索→(可选)解读」，不写库、不缓存解读。
- **复用现有模块**：web 层只是编排，不复制业务逻辑。
- **服务端渲染 JSON + 前端 fetch**：不引入前端框架/node 构建链，保持零构建。

## 2. 技术栈选项（需用户拍板，§任务 2）

| 方案 | 依赖 | 优点 | 缺点 |
|---|---|---|---|
| **A. FastAPI + uvicorn + 原生 HTML/JS**（推荐） | fastapi, uvicorn（2 个） | 类型化、自动 OpenAPI 文档、async 天然、社区标准 | 需装 2 个包 |
| B. Flask + 原生 HTML/JS | flask（1 个） | 最老牌、极简 | 无自动文档，手动路由 |
| C. Streamlit 快速原型 | streamlit（重，~几十包） | 最快出可点界面 | 交互受限、非标准"网页端"、依赖重 |

> 三者都需新增依赖（红线第 3 类的新增依赖在此被用户"搭建网页端"的需求显式授权）。推荐 A：与现有 Python 3.14 + 类型标注风格一致，OpenAPI 让 API 契约可自动校验。

**部署形态**（同一次决策）：本地开发（uvicorn 单进程，`127.0.0.1:8000`）起步；如需对外，加反向代理（nginx）或打包成单个可执行（PyInstaller，后议）。

## 3. API 契约（先定，照 GOAL §3 先定后测）

### `GET /` → 页面（单页 HTML/JS）

### `POST /api/bazi`
请求：
```json
{
  "year": 1990, "month": 5, "day": 15, "hour": 10,
  "gender": "男",
  "use_llm": true,
  "question": "事业运如何？"        // 可选
}
```
校验：year 1900–2100、month 1–12、day 1–31、hour 0–23、gender ∈ {男,女}；非法 → 400 + 中文错误。

响应：
```json
{
  "paipan": {
    "render": "庚午年 丁亥月 庚辰日 辛巳时　日主：庚　大运：顺",
    "nayin": ["路旁土", "屋上土", "白蜡金", "白蜡金"],
    "warn": []
  },
  "evidence": [
    {"work_id": "KR3g0042", "title": "三命通會", "layer": "正文",
     "page_anchor": "KR3g0042_WYG_008-1a", "file": "KR3g0042_008.txt",
     "text": "…", "why": "日柱"}
  ],
  "llm": { "ok": true, "text": "…", "model": "claude-opus-5" }   // use_llm=false 或未配置 → ok:false + 提示
}
```
错误响应：`{"error": "…"}` + 4xx/5xx。

## 4. 页面设计（单页，无构建）

- **输入区**：年/月/日/时（下拉或数字）、性别（男/女）、勾选「LLM 解读」+ 可选问题框、「排盘」按钮。
- **结果区（分三段，红线要求分离）**：
  1. 排盘卡片：四柱 + 纳音 + 大运 + warn（邻近节气提示）。
  2. 「古籍原文证据」列表：每条 书名/层/页锚点/文件 + 前 ~100 字，可展开看全文；无命中显示"证据不足（G7）"。
  3. 「LLM 解读（生成文本，非古籍原文）」：标注模型名；未配置 KEY 时提示去填 `llm_config.json`。
- 风格：极简（无 CDN 依赖，内联 CSS/JS），中文界面。

## 5. 红线遵守（与 CLI 完全一致）

1. **KEY 只留服务端**：`llm_config.json` 仅服务端读取（已 gitignore）；API 响应绝不回传 key；前端拿不到。
2. **生成文本不落库**：LLM 解读仅进程内返回，不写 corpus.db/knowledge.db、不缓存磁盘；每次请求即时调用。
3. **引用与生成分离**：UI 三段式 + 文案标注「非系统生成的解读」；解读须基于引文（llm_reader SYSTEM_PROMPT 已约束）。
4. **13 道闸门零回退**：web/ 为新增目录，不触碰 build/verify/eval 链；新增依赖不影响现有 venv 使用；验收时全量复验。
5. 输入校验在系统边界（API 层），不引入不必要的防御。

## 6. 实施步骤（照 §任务 3–5）

1. 新增依赖：`pip install fastapi uvicorn`（或选定栈）。
2. `web/app.py`：FastAPI 应用，路由 + 校验 + 编排（复用 bazi/bazi_lookup/llm_reader）。
3. `web/static/index.html`（含内联 CSS/JS）：表单 + 三段式结果渲染。
4. 实测：`uvicorn web.app:app` 启动；curl 测 GET / 与 POST /api/bazi（含/不含 --llm、非法输入 400）；浏览器打开 `http://127.0.0.1:8000` 走一遍真实表单。
5. 复验 13 道闸门全过；TASK_LEDGER/DECISIONS 记录；commit/push。

## 7. 验收（先定后测）

- GET / 返回可交互页面（浏览器实测）。
- POST /api/bazi 合法输入 → 排盘+证据+（可选）LLM 三字段齐全，引用带出处。
- 非法输入 → 400 中文错误，不崩。
- use_llm=true 且已配置 → LLM 解读返回并标注模型；未配置 → ok:false 提示，引用仍完整。
- 13 道闸门零回退；`.gitignore` 含 llm_config.json（已确认）；响应无 key 泄漏。
