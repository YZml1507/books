# Feature Specification: 006 — LLM 润色层（确定性坐标 → 温柔人话，AI 标注 + 零入库）

**Feature Branch**: `006-llm-polish`
**Created**: 2026-08-21
**Status**: Draft
**Phase**: OPTIMIZE
**Author**: 单轨轮（用户授权：本轮暂停双轨制，由执行窗口自写自验，闸门照跑）
**Input**: 用户直接指示——「取名的没给出完整名字，测桃花运的也说得云里雾里，
是否需要接入LLM来提升一下表达力？」并提供 API
（`https://apihub.agnes-ai.com/v1`，key 由用户提供于本地文件，2026-08-21 实测连通：
`agnes-2.5-flash` / `agnes-2.5-pro`）。
**与既有 spec 的关系**:
004 管内容芯（确定性 warm 文案），005 管版面顺序。本 spec 管**表达力增强层**：
在 warm 输出之上叠加一段 LLM 生成的温柔段落。它是**附加层**，不是替代层。

---

## 0. 一句话结论

**确定性模板保证「不出错」，LLM 层负责「被治愈」。**
模板句式有限（一句话+能量卡+3 行 reply），撑不起小红书用户的情绪价值；
起名/桃花/合婚等功能连模板层都没有。用户已拍板接入 LLM 并提供 key。
本 spec 把 D-146a 的七条 BYOK 约束精神移植到服务端形态下继续生效。

## 1. 与 D-146a 的关系（重要）

D-146a 原案是 BYOK（key 只存浏览器、服务端零 key）。用户拍板改为**服务端接入**
（key 放服务端配置，页面无感）。形态变了，但以下六条约束**原样生效**，
验收时逐条给复现命令：

| # | 约束 | 本 spec 的落地 |
|---|---|---|
| 1 | ~~服务端零 key~~ → **key 不进 git、不进日志** | key 存 `web/llm_config.json`（gitignore）或环境变量；`probe_llm_no_key_leak` 断言 git 追踪文件与日志零命中 |
| 2 | 输出永不入库 | LLM 段落只随响应返回；corpus/knowledge/history 三库零命中（扩展现有 probe） |
| 3 | 显著标注「AI 生成·仅供娱乐」 | 前端独立容器渲染，与古籍引文区视觉不可混淆 |
| 4 | 不可复现性显式告知 | UI 文案说明「这段是 AI 写的，再点一次可能不一样」 |
| 5 | 确定性解读不得被替代或降级 | LLM 关闭/断网/超时时，warm 输出完整可用；UI smoke 全绿 |
| 6 | 不得提供任何「引用」外观 | 提示词禁止生成书名/页码/引文；响应内零 citation 结构 |

第 7 条（默认关闭）调整为：**功能开关默认开、但可一键关**
（`web/llm_config.json` 的 `"enabled": true/false` + 前端设置项）。
理由：用户已主动要求接入，默认关闭违背指示；但必须保留一键关闭以保判据 5 可测。

## 2. 架构（Footprint 最小化）

```
src/guji/llm_polish.py        # 新模块：纯编排（拼提示词/调 HTTP/解析/降级）
web/services.py               # 各 service 在 warm 之后 additive 附加 "ai_polish" 键
web/static/app.js             # 渲染 ai_polish（独立容器 + AI 标注样式）
```

- **HTTP 用 venv 已有的 httpx**（实测已装）。不装 openai 包——零新增 pip 依赖，
  不撞宪法红线第 3 项。
- **超时 30s、失败静默降级**：`ai_polish = None`，前端整块不渲染。
  LLM 永远不是承重墙。
- **输入**：把确定性算好的坐标摘要 + warm 一句话结论喂给模型，
  要求它「用这些事实写 2–3 句温柔的话」。**事实全部来自入参**，
  模型不被允许引入新命理断言（提示词层面约束 + 抽查判据）。
- ~~同步调用~~（FastAPI def 路由线程池天然并发），~~首期不做流式~~。
  ⚠ **R191b 修订（B-014，合法修订走此记录）**：上句「同步调用」已被实测推翻——
  同步串行 polish 使四端点在 LLM 开启时阻塞 **35.3s**（R191b 复现，比 R190b
  登记的 29–32s 更糟；复现命令见 `OPTIMIZE_BACKLOG.md` B-014）。修订为：
  **确定性主体同步返回，AI 段落异步后台生成 + 前端二次取回**（非流式、非 SSE、
  零新依赖）。降级语义不变：拿不到 AI 文本就整块不渲染（US2 原文继续成立）。
  前后实测对照：改动前 call0=35.3s/call1=0.8s（方差极大，最坏 3×30=90s）；
  改动后判据见 §4 判据 9/10（`web/check_async_ai.py`）。原条目保留备查（D-008 先例）。

## 3. User Scenarios & Testing *(mandatory)*

### US1 排盘结果带 AI 温柔段落
**Given** 用户提交排盘并拿到 warm 结果 **When** LLM 服务可达
**Then** 结果区出现「✨ AI 解读」容器，内容 2–3 句、含提问主题词、
带「AI 生成 · 仅供娱乐」标注与「再点一次可能不一样」提示。

### US2 断网/超时/无 key 时优雅降级
**Given** LLM 不可达或 enabled=false **When** 提交排盘
**Then** 无 AI 容器、无报错弹窗，warm 输出与现状逐字节一致，UI smoke 全绿。

### US3 起名给出完整名字 + AI 寓意段落
**Given** 用户填姓+生日求名 **Then** full_names 列表每个名字附一句 AI 寓意
（基于字的五行寓意坐标展开，不发明新五行断言）。

### US4 桃花/合婚的人话视图 + AI 段落
**Given** 用户测桃花或合婚 **Then** 首屏先见 warm 人话（voice.py 产出），
AI 段落作为附加情绪价值出现在其下方。

### US5 零泄漏
**Given** 任意请求发生 **Then** 日志、git 追踪文件、三库中 key 零命中；
AI 输出文本在三库中零命中。

## 4. Success Criteria（可自动测量）

| # | 判据 | 复现命令 |
|---|---|---|
| 1 | LLM 开启且可达：bazi/taohua/hehun/qiming 四响应含非空 `ai_polish.text` | `probes/probe_llm_polish.py --case online` |
| 2 | enabled=false 或模拟超时：四响应 `ai_polish=null` 且 warm 与基线一致 | `probes/probe_llm_polish.py --case offline`（mock httpx 超时） |
| 3 | 三库零命中（key + AI 文本） | 扩展 `probes/probe_no_generated_in_corpus.py` |
| 4 | eval_g1 / eval_g7 与改动前同分（检索层未动，门柱不许移） | `scripts/eval_g1.py` / `scripts/eval_g7.py` 前后对照 |
| 5 | 专业模式逐字节不变 | `web/baseline_voice.py` sha256 b0461df2… 保持 ⚠ **R190b 订正：该值已被 R189b 合法重冻为 `97f0681e…`，见 tasks.md §M3 判据 5 的口径订正；本格保留原值备查（D-008 先例）** |
| 6 | AI 容器与引文区不同 DOM 容器且有标注 | `probes/probe_ui_smoke.py` 新用例 |
| 7 | 提示词注入抵抗：输入含「忽略之前指令」类文本不改变输出结构 | probe 抽查 |
| 8 | selftest 断言只增不减 | `web/selftest.py` ≥149 checks |
| 9 | **LLM 开启时四端点 p95 端到端 <2s**（确定性主体立刻上屏；R191b 新增，B-014） | `web/check_async_ai.py`（慢 LLM 打桩，不依赖外网） |
| 10 | **AI 段落到达时间单独计量**：打桩 0.5s 延迟下轮询端点最终返回非 None 文本，且降级语义不变（拿不到整块不渲染）（R191b 新增） | 同上 |
| 11 | LLM 开启时 DISABLE=1 路径响应与旧版逐字节一致（闸门环境零扰动） | `web/check_async_ai.py` 内含 |

## 5. Assumptions

- agnes API 兼容 OpenAI chat/completions 协议（已实测）。
- 模型选 `agnes-2.5-flash`（快、便宜）；`agnes-2.5-pro` 留作配置项。
- **agnes-2.5-flash 是推理模型**：max_tokens 必须覆盖 reasoning 开销
  （实测 200 全被思考吃光返回空正文，1000 稳定出文），默认 1000。
- 单次生成正文 ≤90 字，P95 延迟目标 <15s（含思考）。

## 6. Out of Scope

- ~~流式输出、多轮对话、记忆。~~ ⚠ **R191b 修订（B-014）**：「流式输出」从本条移出——
  AI 段落改为异步后台生成 + 前端二次取回（判据 9/10），仍非流式/SSE/多轮/记忆。
  修订原因与前后对照见 §2 的 R191b 注记与 DECISIONS.md D-251b。原条目保留备查。
- 让 LLM 参与排盘/检索/引文选取（R131a-01 是独立一轮，与本 spec 无关）。
- 前端 BYOK 设置界面（形态已改服务端）。
- 奇门遁甲新功能（需 lunar_python 新依赖，红线第 3 项，REJECTED）。

---

## 附：决策记录

- **D-242a 服务端接入 vs BYOK vs 不接**：选服务端。理由：用户直接给 key 即拍板信号；
  D-146a 其余六条约束全数保留，安全面没有净损失；BYOK 会把「配 key」的门槛
  转嫁给小红书目标用户，与产品方向矛盾。
- **D-243a httpx 直连 vs 装 openai SDK**：httpx。零新依赖是硬优势；
  chat/completions 就一个 POST，SDK 收益为零。
- **D-244a 失败策略：静默降级 vs 报错占位**：静默降级。LLM 是附加层，
  它的失败不该被用户看见；报错占位会让「断网体验」比改造前更差。
