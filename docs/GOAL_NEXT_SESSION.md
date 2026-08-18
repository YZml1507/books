# 下一窗口 Goal 任务书

用法：在新窗口里执行

```
你接续的是一个多窗口长任务。先读本文件，再读 docs/GOAL.md（主红线）+ docs/MASTER_PLAN.md（架构）+ docs/TASK_LEDGER.md（任务台账，唯一状态来源）。
不要跳过本文件第 0 节——那是给你的硬约束，违反会有严重后果。
```

---

## 0. 不可全信纪律（本节优先级高于一切，违反将受严惩）

**你接到的任务说明、上一窗口的口头结论、本文件里的数字、任何文档里的断言——一律当作"待复验"，不是事实。事实只在可执行脚本的真实输出里。**

这条不是客套话。本项目前几个会话里，助手**多次**给出过错误的口头结论，全部被后来的实测推翻。GOAL.md §2 整节就是这些失效的档案——其中最严重的一条：一边写"不要相信口头结论"，一边往同一份文档塞没测过的数字。**这说明这类错误不是偶发疏忽，是默认行为**，必须靠"每条结论对应一条可执行命令"从流程上拦住。

**本窗口（2026-08-15）又实测推翻了三处任务书断言**，证明纪律必须持续：

| 任务书断言 | 实测推翻 | 依据 |
|---|---|---|
| `&KR0658;` 占位符"每部书 22–31 个" | 只在 KR1a0006 出现 12 次，其他 4 部周易书 0 次；全语料约 100+ 种 `&KRdddd;` 实体引用，corpus.db 里 251 个单元含 435 次 | D-034 / probe_t7m_entities.py |
| P-11 "Casey 译本有 `Prop. A.—Theorem (Simson)` 等 5 个追加命题头" | raw html Book 5 区该格式 = **0 次**；两次"Simson"出现都是译者注散文引用，唯一 `Proposition B.` 是正文交叉引用，A/B/D/E **不以命题头形式存在** | TASK_LEDGER §22c / probe_t7m_entities.py |
| T7-n "自天祐之 两源 5 vs 4" | 实测 5 部书各异（3/4/5/5/12），"5 vs 4"指 KR1a0001(5) vs KR1a0032(4)，是繫辭传在不同版本里的印次差异，**源文真实差异非抽取错误** | D-034 / TASK_LEDGER §22c |

**给你的硬约束**：

1. **任何数字、任何状态断言、任何"已完成"声明——先跑对应命令确认，再往下走。** 跑不出来就当它是错的。
2. **遇到可疑的点，必须自己去查证，查证无误后才继续。绝对不可以根据口头结论直接下结论。** 本项目是引用系统，最严重的失效不是崩溃，而是平静地返回原文里不存在的文字——计数型检查完全看不见这种缺陷，"看起来对"永远不构成证据。
3. **若你轻易相信口头结论、未查证就下结论，你将受到极其严重的惩罚。** 这条是写给你的，不是写给用户的。
4. **发现文档与实测不符时，改文档并在文档里写明"此前结论已被推翻"——本项目的做法是保留错误记录（见 DECISIONS.md D-008），不是悄悄改掉。**
5. **不要把"数字没变"当作"没有收益"，也不要把"数字变好"当作"改对了"。** 两者都出现过反例（本窗口 D-031 方案 C hit rate 67.3% 比基线 78.2% 还差，"数字变好"的反例）。

### 0a. 查聊天记录的方法

本窗口及之前的会话记录是磁盘上的普通文件，可以直接 grep：

```
C:\Users\Lenovo\.atomcode\sessions\1ae2121e85ce8e84\<sessionId>.jsonl   # 本窗口（2026-08-17，含 ab629b12…jsonl；R96b 补注）
C:\Users\Lenovo\.atomcode\sessions\025973b91a55cfb5\<sessionId>.jsonl   # 旧窗口回溯目录（保留）
```

**注意路径变了**：jsonl 落盘在 `sessions/1ae2121e85ce8e84/`（本窗口）与
`sessions/025973b91a55cfb5/`（旧窗口，可回溯；`ls .atomcode/sessions/`
实测两目录都存在），而非更早的 `projects/C--Users-Lenovo-Desktop-projects-books/`。
若新路径下找不到，去旧路径也查一遍。

可回溯的 sessionID（从近到远）：

| sessionID | 日期 | 内容 |
|---|---|---|
| `ab629b12-3cf7-4d09-bedf-3892431f8e60` | 2026-08-17 | **本窗口**：R75b 起优化循环（R70b-R110b docs-only、R111b 起恢复功能轮——桃花运/塔罗/大运应期/牌阵/ask 模型标注/hehun 合婚/合婚大运应期，R116b/R122b 标注；R118b/R119b/R124b/R126b/R128b/R130b/R132b/R134b/R137b/R138b/R139b 补 standing 断言），轮数以 `git log 2946a8a..HEAD \| wc -l` 实测为准（R97b 补行、R100b/R104b 去钉死），基线全绿（47 部 62,109 单元、G1–G9 PASS 9、web 106 checks），最新 commit 见台账文末 |
| `3d8bab44-30fc-4a4d-9584-7372f78e8f2b` | 2026-08-15 | **上一窗口（本文件更新者）**：T7-r 方案 C 否决（hit 67.3%）、方案 A/B BLOCKED、T5 A-12 候选 N1 否决回退、T7-q/T7-m/T7-n/T7-o/T7-p/P-11 全完成。13 道闸门全过，commit a05a9cf 已 push |
| `aa53987d-d690-4c1d-95d6-ddff26cd2888` | 2026-08-13 23:24 | 更早：Douay 接入、A-12、G1 方案 1 手写转述扩到 55 条（hit 78.2% 未达 80% 阈值） |
| `405e2cb4-bfbe-4df0-adf9-2553f0c675d4` | 2026-08-13 19:15 | 更早：台账 §22b 前 |
| `a1732134-c6d5-4afb-b704-0a1354985a9a` | 2026-08-13 16:13 | 更早 |

**怀疑本文件某条说法时**，去 grep 对应 sessionId 的 jsonl，看当时命令的真实输出，而不是相信本文件的句子。若 grep 不到，就当该说法**不存在**，重新自己测。

### 0b. 自主决策，不要停下来问（本窗口强化）

**遇到任何决策，不要停下来问用户。** 自己列 2–3 个方案，用本仓库的实测数据比较，选最优的直接执行，把比较过程写进 DECISIONS.md。

这条是本窗口被用户明确强化的：上一窗口（2026-08-15）已在 T5 A-12 上示范了"列 N1/N2/N3 三候选→实测比对→选最优→直接执行→失败就按先例否决回退"的完整闭环（D-033），**不停下来问**。本窗口剩余任务都是同一类型——查证型、方案比对型、自主执行型。停下来问用户反而是错的。

例外只在红线三类（见 §4）：那不是"停下来问"，是"跳过并记录，直接开始下一个任务"。

---

## 1. 当前实测状态（先自己复验，不要相信这张表）

复验命令（照 GOAL.md §3，任一改动后必须全过；顺序重要：check_quality 在 build_index 前）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\verify_index.py
.\.venv\Scripts\python.exe scripts\validate_alignment.py
.\.venv\Scripts\python.exe probes\probe_conservation.py
.\.venv\Scripts\python.exe scripts\check_provenance.py
.\.venv\Scripts\python.exe probes\probe_bcv.py
.\.venv\Scripts\python.exe scripts\eval_g1.py
.\.venv\Scripts\python.exe scripts\summarise_diff.py
.\.venv\Scripts\python.exe scripts\eval_g7.py
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py
.\.venv\Scripts\python.exe scripts\eval_g4.py
.\.venv\Scripts\python.exe probes\probe_booksec.py
.\.venv\Scripts\python.exe scripts\assess_goals.py
# 各层 standing 自测（R49b 起全齐；web 106 checks 为 R53b/R54b/R61b/R69b 扩展后 + R110b-R115b 功能轮 +11 + R118b/R119b 各 +2（liuyao.time/huangli.affair/bazi.lunar/bazi.lunar_leap）+ R121b +1（hehun）+ R124b +5（错误路径断言 err.*）+ R126b +2（bazi.range/bazi.life）+ R128b +2（search.layer/search.work）+ R130b +2（compare_works.refuse/bookstudy.chapter.nullscheme）+ R132b +1（research.allow_damaged）+ R134b +1（bookstudy.summary.missing）+ R136b +1（history.detail.missing，R137b 误删 R138b 恢复）+ R137b +1（addr.zhouyi.yao）+ R138b +1（hehun.dayun）+ R139b +3（err.bazi.calendar/scope/gender）+ R140b +2（err.qiming.gender/year）+ R141b +3（err.liuyao.time.year/month/missing）+ R142b +3（err.huangli.date/year/illegal）+ R143b +3（err.taohua.year/gender/calendar）+ R144b +3（err.compare_works.missing/err.concept.empty/err.research.max_addresses）+ R145b +1（err.search.empty）+ R146b +2（err.concept.too_long/err.research.too_long）+ R147b +1（err.compare.gua_range）+ R148b +3（err.addr.zhouyi.no_gua/err.bookstudy.structure.empty/err.bookstudy.chapter.empty）+ R149b +5（err.liuyao.time.day/hour/err.qiming.month/day/hour）+ R150b +6（err.bazi.lunar_missing/month/day/err.hehun.b_year/b_month/b_day）+ R151b +4（err.bazi.ask_hour/ask_date/range_missing/range_format）+ R152b +4（err.bazi.range_order/range_span/err.bookstudy.chapter.scheme/err.qiming.calc_fail）+ R153b +2（err.research.empty/err.compare_works.q_empty）+ R154b +4（err.hehun.a_month/a_day/a_hour/b_hour）+ R156b +1（err.bazi.lunar_year）实测数，R139b-R156b 同步）：
PYTHONPATH=src .\.venv\Scripts\python.exe -m guji.sources --selftest
PYTHONPATH=src .\.venv\Scripts\python.exe -m guji.bookstudy
PYTHONPATH=src .\.venv\Scripts\python.exe -m guji.research
PYTHONPATH=src .\.venv\Scripts\python.exe -m guji.mcp_server --selftest
cd web; PYTHONPATH=src:. ..\.venv\Scripts\python.exe -m app --selftest
```

**当前（R69b 功能终态，13/13 全过 + 五层自测全齐；web 自测 106 checks，R53b/R54b/R61b/R69b 补端点 + R110b-R115b 功能轮 +11 + R118b/R119b 各 +2 + R121b +1 + R124b +5 + R126b +2 + R128b +2 + R130b +2 + R132b +1 + R134b +1 + R136b +1 + R137b +1 + R138b +1 + R139b +3 + R140b +2 + R141b +3 + R142b +3 + R143b +3 + R144b +3 + R145b +1 + R146b +2 + R147b +1 + R148b +3 + R149b +5 + R150b +6 + R151b +4 + R152b +4 + R153b +2 + R154b +4 + R156b +1，R139b-R156b 同步）**（R85b 补注、R92b 去范围钉死、R116b 修正：R70b-R110b 为 docs-only 对齐轮、功能终态维持 R69b；**R111b 起恢复功能轮**——桃花运/塔罗/大运应期/牌阵/ask 模型标注/hehun 合婚/合婚大运应期，web 24→35→39→40→45→47→49→51→52→53→55→56→59→61→64→67→70→73→74→76→77→80→85→91→95→99→101→105→106 checks；PROJECT_STATUS 头部 R78b 指快照块内容轮次，见 D-119b/D-130b）：

```
索引      47 部 → 62,109 单元 · 55.7 MB · 页锚点 13,954 · 有地址 57,315（92.3%）
G 判据    PASS 9 · PART 0 · FAIL 0（含 G4 多跳/G8 三类知识隔离/G9 跨会话）
地址体系  六类：zhouyi · bcv · yilin · booksec · play（幕/场）· euclid（卷/命题）
研究模式  八模式全落地（R18b-R27b）：Quick/Deep/Book Study/Chapter/Comparative/
          Cross-book/Book Summary/Concept；web 9 tab + MCP 12 工具同源
记忆闭环  研究→记录→跨会话恢复：web POST /api/threads + 三 tab 记入 + 列表自动
          刷新 + 长期研究续接（R34b-R46b）；MCP record_claim_tool + threads 读回
术数功能  八字排盘 · 六爻 · 黄历 · 起名 · 桃花运（R111b）· 塔罗占卜（R112b）
          · 大运桃花应期（R113b）· 塔罗牌阵位置（R114b）· 八字合婚（R121b，
          R123b 补）；web 术数 tab 8 个，
          MCP 12 工具（术数不在 MCP，同源承诺不含术数）
前端      R155b 重构：布局/风格/动画叠加层（tailwind Play CDN 禁用
          preflight + tsparticles 粒子背景 CDN + 本地 animotion
          动画 CSS 745 类离线可用；id/handler/API 零改动，见 D-201b）
```

> 本文件 §2 旧任务清单（T7-r/T5 A-12/T7-m 等）已被 R18b–R50b 优化循环取代——
> 见 §2 顶部指引。REJECTED/BLOCKED 防重做清单在 §3 保留。

---

## 2. 你的剩余任务（按优先级，理由见 docs/GOAL.md §4 + docs/MASTER_PLAN.md §7）

> **⚠ 重要更新（R51b）**：本节原任务清单（T7-r embedding 方案 A/B、T5 A-12
> 吸裸注剥离、T7-m &KR0658; 实体映射等）**全部已被 R18b–R50b 优化循环取代**：
> - T7-r 方案 A/B：G1 概念级检索已在 R18b 前经 bge（用户授权）落地为 PASS，
>   方案 C 仍 REJECTED（D-031）；本条不再开放。
> - T5 A-12：KR1a0007 吸裸注问题早已在质量归责链（quality.py）处置，N1/N2/N3
>   仍 REJECTED（D-033），不重做。
> - T7-m：&KR0658; 等实体引用已在后续 ingest 轮次处理；本条不再开放。
> **当前本轨的活状态是"优化循环"**：每轮 fetch → 摸底 → 列 2-3 方案写
> DECISIONS → 选最优实施 → 自测+13 闸门 → 台账 § + DECISIONS → commit+push，
> 直到用户叫停。接续轮次从 `docs/TASK_LEDGER.md` 末条编号 +1 开始，
> DECISIONS 从末条 D- 编号 +1 开始。

### 2a. 当前移交项（开放，非本轨领土）

- **R21a 委托合入 main**：`scripts/assess_goals.py` 的 raw_body 委托已在审查轨
  实施（`337aadc`"delegate G6 body to evalset.raw_body — R21a 审查轨"；原引用
  `23d0f94` 在审查轨历轮 rebase 后被重写失效，`git merge-base --is-ancestor
  23d0f94 origin/audit/R18` 失败，见 DECISIONS.md:2987；R98b 补注）仍在审查轨
  分支，main 侧保持内联——待审查轨合入（scripts/ 属审查轨领土，优化轨不做）。
- **愿景 §15 评估缺口**（跨书/版本意识/研究深度正式 eval）：scripts/ 属审查
  轨领土（O8 移交）；本轨已用各层 standing 自测（sources/bookstudy/research/
  mcp/web）覆盖能力级回归。
- **G9 SCOPE 声明过时**（R64b 发现，待审查轨修正措辞）：`scripts/
  assess_goals.py` line 372-374 写"no component writes to this store
  during ordinary operation yet — research_thread.py is the only writer"，
  与事实不符——web POST /api/threads（R34b，web/app.py:655）与 MCP
  record_claim_tool（R36b，mcp_server.py:233）均写 knowledge.db（实测
  derived=2, evidence=6）。真实意图是"无**自动**捕获"，措辞应改为
  "无自动捕获，写入口均需用户主动选择记录"。scripts/ 属审查轨领土，
  优化轨只记录不移交实施。

### 2b. 其他低优先（若优化循环外还有余力）

- ~~**BOOK_AI_ARCHITECTURE.md §5 "自天祐之 5 vs 4 原因待查"补注**~~ **已完成**
  （2026-08-15 已补注，见 `BOOK_AI_ARCHITECTURE.md` §5 行内补注：原因查清，
  繫辞传印次差异，D-034/T7-n；R57b 核实后本条关闭，新会话勿再做）。

---

## 3. 已 BLOCKED / REJECTED（不要重做，照 GOAL.md §1）

| 项 | 状态 | 依据 |
|---|---|---|
| G1 方案 2 联网抓取释义 | BLOCKED | D-030：无合规公版白话释义源（维基文库是文言古注非白话；黄寿祺/张善文在版权期；百度百科 licence 不明+可能含生成文本）|
| R-02 "取下一次出现" | REJECTED | 用一类错误且分数下降，照 §4 T5 |
| sunls2/zhouyi 入库 | REJECTED | 36.9% 在世作者（傅佩榭 1950—），无 LICENSE |
| 三个生成式占卜仓库 | REJECTED | 伪随机挑卦/无卦表/LLM 包装，属生成文本 |
| GPU embedding | REJECTED | 无 CUDA，MASTER_PLAN §9 |
| Milvus/Neo4j | REJECTED | 独立进程，7.4 GB 内存，§9 |
| 方案 A/B embedding（引入 PyTorch+下载模型）| BLOCKED 待授权 | D-032：撞红线 3 |
| 方案 C（TF-IDF+SVD）| REJECTED | D-031：hit rate 67.3% < 80%，比基线还差 |
| T5 A-12 候选 N1（改 clean 全局剥离裸注）| REJECTED | D-033：T11 362→293 compared，回退 |
| T5 A-12 候选 N2（span end 用"注"字）| REJECTED | D-033：误切彖曰/象曰 |
| T5 A-12 候选 N3（裸注边界枚举）| REJECTED | D-033：误切裸注中段"故曰" |
| P-11 Simson 命题 A/B/D/E | REJECTED | TASK_LEDGER §22c：raw html 0 次该格式，不以命题头存在 |

---

## 4. 红线（GOAL.md §1 + §3 + §5 的浓缩，冲突时去读原文）

**自主决策，不要停下来问。** 遇到决策时：自己列 2–3 个方案，用本仓库的实测数据比较，选最优的直接执行，把比较过程写进 DECISIONS.md。

**三类不要自主执行，但处置方式是"跳过并记录"，不是"停下等人"**：

1. **破坏性且不可逆**：删 `data/raw/` 或 `data/external/` 原始语料、git push、重写历史。（重建 `data/index/corpus.db` **不属于**此类，它 5 秒可重建，随便重建。）
2. **为了让数字变好而放宽任何验收闸门**：见 GOAL.md §3，本项目红线。闸门先定后测，达不到就 BLOCKED，不调闸门。
3. **引入新的外部依赖或联网抓取新语料**：见 §5。撞上时把任务记 BLOCKED 写进 TASK_LEDGER.md（附原因与实测数据），**然后直接开始下一个任务**。

**已授权的（照上一窗口先例，可直接执行）**：
- commit / push 到 main（历次窗口已记录用户授权）。push 不顺时用代理 `127.0.0.1:7897`：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main`。
- 重建 corpus.db / knowledge.db（5 秒可重建，随便重建）。
- 联网抓取释义数据用于 G1 概念级（但 D-030 已确认无合规源，这条授权实际用不上）。

**法务（GOAL.md §5）**：绝对不可入库生成文本。每次获取必须记 `sha256 / source_url / fetched_at / licence`。版权按层判定不按文件判定。

---

## 5. 工作节奏（照 GOAL.md §4b）

- **每完成一小项立刻写台账**（TASK_LEDGER.md），不要攒着。台账是跨压缩、跨会话的唯一状态载体；写在对话里的结论会丢。
- **任何改动后跑一遍 §1 全部闸门**，任一闸门回退立刻回退改动，不调闸门。
- **撞上红线三类时不要停等**，按处置规则跳过并记录，直接开始下一个任务。
- **上下文会被压缩**，因此每条结论都要有可复现的命令。
- **写 DECISIONS.md 时照 D-033 先例**：候选方案、实测数据、反例、决策理由、否决回退都要留——这是下一窗口的回溯依据。

---

## 6. 本窗口（2026-08-15，sessionID `3d8bab44-30fc-4a4d-9584-7372f78e8f2b`）交接摘要

上一窗口完成了 11 项任务，commit a05a9cf 已 push 到 github.com/YZml1507/books main。

**核心产出**：
- `probes/probe_embed_tfidf.py` + `probes/embed_c_report.json`：方案 C 实测否决（hit 67.3%）
- `probes/probe_t7q_kg_precondition.py`：T7-q KG 前置条件满足
- `probes/probe_t7m_entities.py`：&KR0658; = 虩 查清
- `probes/archive/`：45 个已沉淀探针归档
- `docs/DECISIONS.md` 增 D-031~D-034（方案 C 否决、方案 A/B BLOCKED、A-12 N1 否决、T7-p 架自审通过）
- `docs/TASK_LEDGER.md` 增 §22c + P-11 复验否决

**新窗口要做的第一件事**：跑 §1 全部 13 道闸门 + 五层 standing 自测复验基线，确认与 §1 快照一致（R50b 终态：47 部 62,109 单元、G1–G9 全 PASS）。若不符，先查最近 commit 是否真的 push 成功、工作树是否干净——不要相信本文件的数字（本段以下是 2026-08-15 历史窗口交接存档，数字已过时，仅作演进对照）。

---

## 7. 下一窗口（2026-08-15 接续）交接摘要

本窗口完成 4 项任务 + 低优先 3 项，commit 已 push 到 main。

**核心产出**：
- **2c &KR0658;→虩 落地**：任务书"在 clean() 里加解析"位置被实测推翻（clean() 不参与 unit.text/FTS 生成链）——改为在 ingest.py:631 FTS 喂入点 decode。13 道闸门零回退，search('虩') 命中 KR1a0006 从 0→2 条
- **2b A-12 局部剥离 P1-P5 全否决（D-035）**：结构性冲突——T11 依赖 with-notes 全文比对（A 括号注/B 裸注），剥 B 裸注 coverage 0.991→0.132 崩；对称经-only compared 362→218 破 358 阈值。quality.py 零 diff，A-12 维持 EXPECTED_DEGENERATE
- **2a 方案 A/B**：未获显式授权，维持 BLOCKED（照红线跳过并记录），G1 维持 PART
- **2d 低优先**：probes 归档 12 个（archive 57、活跃 54）、架构 §5 补注、通用性证伪探针 probe_generality_roundtrip.py（6 体系 25/25 100% round-trip 未被证伪）

**新探针**：probes/probe_a12_local.py（负结果记录，照 rarity_scores 先例）、probes/probe_generality_roundtrip.py（通用性证伪）

**13 道闸门末态**：build 51,174 单元 43.4 MB · verify_index ALL PASS（T11 362 compared）· validate_alignment 1824/1872 = 97.4% · check_quality PASS · probe_conservation ratio 1.0000 · assess_goals PASS 8 · PART 1 · FAIL 0 · check_provenance 0/38 · probe_bcv PASS · eval_g1 PASS · eval_g4 PASS · eval_g7 PASS FABRICATIONS 0 · probe_g8 PASS

**剩余任务（照 §2 优先级不变）**：2a 方案 A/B 待用户显式授权（授权条件见 §2a 六步）；2b 已闭环（P1-P5 否决，不再重做）；2d 通用性证伪已做一轮，可扩展（如跨体系交叉引用、地址别名）。
