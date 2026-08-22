# 006-llm-polish 任务清单

**Written**: 2026-08-21 由 R190b 补建
**对应**: `specs/006-llm-polish/spec.md`（WHAT/WHY）+ `plan.md`（HOW）

状态列：`TODO` / `DOING` / `DONE(命令)` / `BLOCKED(原因)`。
每任务完成即改状态并附实测命令输出摘要；宪法第一条：**没有命令的 DONE 等于没做**。

> **本文件为什么迟到**：宪法第六条要求「spec.md → plan.md → tasks.md → 代码」
> 四个产物缺一不可。R187b 落了 spec 与 plan 就直接写代码，`tasks.md` 从未创建，
> 而 `src/guji/llm_polish.py` 已上线并接了四个端点。R190b 补建本文件，并按
> **本轮实测**（不采信 R187b 台账报告）逐条填状态列。
>
> `<py>` = `C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`
> 闸门环境统一 `BOOKS_LLM_DISABLE=1`（D-245a）；`--online` 用例例外。

## M1 服务端接线

- [x] T1.1 `src/guji/llm_polish.py` 模块 + 离线自测全过
  状态：DONE(R190b 实测 `PYTHONPATH=src <py> -m guji.llm_polish` 退出码 0；
  文件 14,620 字节，含 `load_config/polish/_sanitize/facts_*` 四组)
- [x] T1.2 `web/llm_config.json`（gitignored）写入真实 key；`.gitignore` 加该路径
  状态：DONE(R190b 实测 `git check-ignore -v web/llm_config.json` →
  `.gitignore:48` 命中；`git ls-files web/llm_config.json` 空 = 未被跟踪；
  40 个提交采样 `sk-[A-Za-z0-9]{20,}` 零命中)
- [x] T1.3 `web/services.py`：四端点 additive 附加 `ai_polish`，不动现有键，
  LLM 调用 try/except 全兜底
  状态：DONE(R190b 实测 `grep -c ai_polish web/services.py` → 16；
  四端点响应含 `ai_polish` 键；`BOOKS_LLM_DISABLE=1` 时四端点
  `ai_polish is None` 且确定性主体两次调用逐字节相等——见
  `<py> probes\probe_llm_polish.py` 判据 2b)
- [x] T1.4 `probes/probe_llm_polish.py`：offline 用例 + `--online` 开关 + 三库零命中
  状态：DONE(**本文件由 R190b 补建**——spec §4 判据 1/2 的唯一验收命令此前
  不存在，LLM 层上线后一直无人把关。实测：
  `<py> probes\probe_llm_polish.py` 退出码 0（判据 2/2b/3/6/7/8 全 PASS）；
  `--self-check` 退出码 0，注入「超时也返回文本」+「净化失效」后
  判据 2 四条与判据 7 一条被抓到；
  `--online` 判据 1 四端点 ai_polish 全非空)
- [x] T1.5 `web/selftest.py` 增补 ai_polish 层断言（只增不减）
  状态：DONE(R132a 审查轨实测：新增 ai_polish.key_present / disabled_none /
  additive 三条断言，149→152 checks 全绿退出码 0；baseline 150→153 同步，
  probe_selftest_regress PASS。复现：`BOOKS_LLM_DISABLE=1 <py> web\selftest.py`)
  `grep -c ai_polish web/selftest.py` → 0。
  待补断言建议：`ai_polish.key_present`（四端点键存在）、
  `ai_polish.disabled_none`（DISABLE=1 时为 None）、
  `ai_polish.additive`（其余键与关闭时逐字节相同）。
  注意 `probes/probe_selftest_regress.py` 要求断言只增不减，加断言需同步
  `probes/selftest_baseline.json`)

## M2 前端渲染

- [x] T2.1 `app.js`：四处渲染点在 `j.ai_polish` 非空时追加「✨ AI 解读」容器 + 常显标注
  状态：DONE(R190b 实测 `grep -n renderAiPolish web/static/app.js` →
  定义 `:444`，调用 `:621/:1564/:1633/:1761` 共四处；标注文案
  「AI 生成 · 仅供娱乐 · 再点一次可能不一样」在源码中存在；
  `ai_polish` 为 null 时整块不渲染)
- [x] T2.2 `styles.css`：`.ai-polish` 与古籍引文区视觉不可混淆
  状态：DONE(R190b 实测 `grep -c ai-polish web/static/styles.css` → 4；
  `probe_llm_polish` 判据 6 断言：独立 `.ai-polish` 容器、不复用
  `cite-body`/`ev-item` 类名、标注文案存在——全 PASS)
- [x] T2.3 UI smoke 新用例行为描述登记台账，移交审查轨扩展
  状态：DONE(R132a 审查轨补两条 AI 区块行为用例（D-145a 只断行为）：
  `ai.block.renders_with_ai`——LLM 可用时结果区出现 .ai-polish 区块且标注
  「AI 生成」「仅供娱乐」常显；`ai.block.separate_from_citations`——AI 容器
  与 .cite-body 互不嵌套、类名零复用。离线可复现：probe 内置 stdlib mock
  OpenAI 兼容端点经 BOOKS_LLM_BASE_URL 注入被测子进程。R132a 实测
  probe_ui_smoke 40 用例全 PASS 退出码 0。注：R190b 建议的「LLM 关闭时不出现」
  由既有判据覆盖——BOOKS_LLM_DISABLE=1 下 ai_polish=None 时 renderAiPolish
  返回空串整块不渲染，probe 的其余 38 个用例全程在该模式下跑，零 .ai-polish
  出现即此语义的行为见证)
- [x] T2.3a（R132a 追加）B-018 news.refresh 两层拆分 + B-013 长任务判据
  状态：DONE(见 docs/OPTIMIZE_BACKLOG.md B-018/B-013 处置记录与
  docs/AUDIT_FINDINGS.md R132a-04)

## M3 判据验收（spec §4 表逐条，R190b 实测）

| # | 判据 | 验收命令 | R190b 实测 |
|---|---|---|---|
| 1 | 四响应含非空 `ai_polish` | `probes\probe_llm_polish.py --online` | **PASS**（四端点全非空；不进闸门清单——依赖外网） |
| 2 | 关闭/超时 → `ai_polish=null` 且 warm 不变 | `probes\probe_llm_polish.py` | **PASS**（四种坏响应 + 总开关；四端点确定性主体逐字节相等） |
| 3 | 三库零命中（key + AI 文本） | 同上（内含扫描） | **PASS**（corpus/knowledge/history 三库对注入标记与 api_key 零命中） |
| 4 | eval_g1 / eval_g7 同分 | `scripts\eval_g1.py` / `eval_g7.py` | **PASS**（246/248；30/30·25/25·4/4·FAB 0） |
| 5 | 专业模式逐字节不变 | `web\baseline_voice.py` | **PASS**，但**基线值已变更**：spec 写 `b0461df2…`，实际为 `97f0681e…`（R189b 合法重冻，见下方订正） |
| 6 | AI 容器与引文区不同 DOM 且有标注 | `probes\probe_llm_polish.py` 判据 6 | **PASS** |
| 7 | 提示词注入抵抗 | 同上 判据 7 | **PASS**（注入文本只作事实拼接；`_sanitize` 剥书名号/页码） |
| 8 | selftest 断言只增不减 | `web\selftest.py` | **PASS**（149 checks ≥ 149），但 T1.5 的 ai_polish 专项断言仍缺 |

**判据 5 的口径订正（宪法第一条：文档与实测不符时改文档并写明推翻）**：
`spec.md:92` 与 `specs/005` 多处把 pro 基线钉为 sha256 `b0461df2…`。该值已被
R189b **合法重冻**为 `97f0681e…`（原因：R131a-01 修复后 3 个带提问用例的证据集
合法变化，interpreter 的 citations 随输入联动）。R190b 实测
`web/baselines/voice_baseline.json` 内 `sha256` 字段 = `97f0681e674e…`，
`<py> web\baseline_voice.py` 退出码 0、`14 用例逐字节一致`。
**此前钉死的 `b0461df2…` 已被推翻**，但保留在原文档中备查（D-008 先例）。

## 明确不做（承 plan §明确不做）

- 不让 LLM 参与排盘/检索/引文选取
- 不做流式/多轮/记忆 —— **注**：R190b 实测发现同步阻塞 29–32 秒
  （`OPTIMIZE_BACKLOG.md` B-014），修法很可能**必须**引入二次请求或流式。
  届时属于对本条的合法修订，需走 spec 修订 + DECISIONS 记录，不得默默开工。
- 不装 openai SDK（httpx 直连）
- 奇门遁甲（lunar_python 新依赖，红线第 3 项 REJECTED）

## 移交清单（给审查轨）

1. T1.5 selftest 的 ai_polish 三条断言（需同步 `probes/selftest_baseline.json`）
2. T2.3 `probe_ui_smoke` 的两条 AI 区块行为用例
3. B-014（LLM 30 秒阻塞）/ B-016（`facts_qiming` 缺性别导致 AI 称「林先生」）
   的复验判据，见 `docs/OPTIMIZE_BACKLOG.md`
4. `probes/probe_llm_polish.py` 本身的独立性审计——它由 R190b（修复方）所建，
   审查轨应亲自跑 `--self-check` 确认它不是假闸门，而非采信本表
