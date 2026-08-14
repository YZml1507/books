# 下一窗口 Goal 任务书

用法：在新窗口里执行

```
你接续的是一个多窗口长任务。先读本文件，再读 docs/GOAL.md（主红线）+ docs/MASTER_PLAN.md（架构）+ docs/TASK_LEDGER.md（任务台账，唯一状态来源）。
不要跳过本文件第 0 节——那是给你的硬约束，违反会有严重后果。
```

---

## 0. 不可全信纪律（本节优先级高于一切，违反将受严惩）

**你接到的任务说明、上一窗口的口头结论、本文件里的数字、任何文档里的断言——一律当作"待复验"，不是事实。事实只在可执行脚本的真实输出里。**

这条不是客套话。本项目前几个会话里，上一助手**多次**给出过错误的口头结论，全部被后来的实测推翻。GOAL.md §2 整节就是这些失效的档案——其中最严重的一条：一边写"不要相信口头结论"，一边往同一份文档塞没测过的数字。**这说明这类错误不是偶发疏忽，是默认行为**，必须靠"每条结论对应一条可执行命令"从流程上拦住。

**给你的硬约束**：

1. **任何数字、任何状态断言、任何"已完成"声明——先跑对应命令确认，再往下走。** 跑不出来就当它是错的。
2. **遇到可疑的点，必须自己去查证，查证无误后才继续。绝对不可以根据口头结论直接下结论。** 本项目是引用系统，最严重的失效不是崩溃，而是平静地返回原文里不存在的文字——计数型检查完全看不见这种缺陷，"看起来对"永远不构成证据。
3. **若你轻易相信口头结论、未查证就下结论，你将受到极其严重的惩罚。** 这条是写给你的，不是写给用户的。
4. **发现文档与实测不符时，改文档并在文档里写明"此前结论已被推翻"——本项目的做法是保留错误记录（见 DECISIONS.md D-008），不是悄悄改掉。**
5. **不要把"数字没变"当作"没有收益"，也不要把"数字变好"当作"改对了"。** 两者都出现过反例。

### 0a. 查聊天记录的方法

本窗口及之前的会话记录是磁盘上的普通文件，可以直接 grep：

```
C:\Users\Lenovo\.atomcode\projects\C--Users-Lenovo-Desktop-projects-books\<sessionId>.jsonl
```

可回溯的 sessionID（从近到远）：

| sessionID | 日期 | 内容 |
|---|---|---|
| `aa53987d-d690-4c1d-95d6-ddff26cd2888` | 2026-08-13 23:24 | 上一窗口：Douay 接入、A-12、G1 方案 1 手写转述扩到 55 条（hit rate 78.2% 未达 80% �阈值）。卡死未交接 |
| `405e2cb4-bfbe-4df0-adf9-2553f0c675d4` | 2026-08-13 19:15 | 更早：台账 §22b 前 |
| `a1732134-c6d5-4afb-b704-0a1354985a9a` | 2026-08-13 16:13 | 更早 |

**本窗口**（2026-08-14，接续 aa53987d）的 sessionID 落盘后会在上述目录新增一个 jsonl。本窗口完成了：git push 7 个 commit、Euclid 路由接线（第五种地址体系 euclid，174 propositions）、P-10 缺失命题修复（_PROP_HEAD_RE 加 em-ddash，Book 3 恢复 37、Book 6 恢复 33）、G1 方案 2 联网勘查（D-030 BLOCKED，无合规公版白话释义源）、Q-06 junk census、Q-07 双引擎分歧闸门产品化（dual_engine.py）。本窗口产出 commit 42f987d..7c252a7，全推到 github.com/YZml1507/books main。

**怀疑本文件某条说法时**，去 grep 对应 sessionId 的 jsonl，看当时命令的真实输出，而不是相信本文件的句子。若 grep 不到，就当该说法**不存在**，重新自己测。

---

## 1. 当前实测状态（先自己复验，不要相信这张表）

复验命令（照 GOAL.md §3，任一改动后必须全过）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\verify_index.py
.\.venv\Scripts\python.exe scripts\validate_alignment.py
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe probes\probe_conservation.py
.\.venv\Scripts\python.exe scripts\assess_goals.py
.\.venv\Scripts\python.exe scripts\check_provenance.py
.\.venv\Scripts\python.exe probes\probe_bcv.py
.\.venv\Scripts\python.exe scripts\eval_g1.py
.\.venv\Scripts\python.exe scripts\eval_g4.py
.\.venv\Scripts\python.exe scripts\eval_g7.py
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py
```

本窗口末尾实测快照（13/13 全过，零回退）：

```
索引      38 部 → 51,174 单元 · 9.9 秒 · 43.4 MB · 页锚点 100% · provenance 0/38 缺失
地址体系  五种：zhouyi（卦/爻）· bcv（卷/章/節）· yilin（本卦/之卦，4,096）· booksec（卷/节）· euclid（book/proposition，174）
G 判据    PASS 8 · PART 1 · FAIL 0   （唯�一非 PASS 是 G1，且是故意的：概念级检索未覆盖，不虚报）
对齐      爻辭 verified 1824/1872 = 97.4%
守恒      源 = 索引 · 缺失 0 · 重复率 1.0000
折叠表    FOLD 88 对 · NOT_VARIANTS 23
链接      558 条源文互见，零悬空，100% 有文本支持
```

scheme 分布（实测 SELECT scheme, count(*) FROM unit GROUP BY scheme）：
```
bcv 35787 · zhouyi 5088 · yilin 5032 · None 3457 · booksec 819 · play 817 · euclid 174
```

**注意 booksec 819 + play 817 已有解析器但当前未入索引的单元数 ≠ 这两个数字——这两个是已入索引的。booksec 对应 Herodotus/Darwin，play 对应 Shakespeare。Euclid 是本窗口刚接线的第五种体系。**

---

## 2. 你的剩余任务（按优先级，理由见 docs/GOAL.md §4 + docs/MASTER_PLAN.md §7）

### 2a. T7-r CPU embedding 可行性实测（最高杠杆，唯一能解 G1 概念层 BLOCKED 的路径）

**完整方案已写好**：`docs/PROPOSAL_CPU_EMBEDDING.md`。**先读它**，里面有架构约束对照、三方案、闸门判据、实施步骤、风险先例。

**给你的处置规则**（照 GOAL.md §1 红线三类）：

- 方案 C（TF-IDF + SVD，零新依赖）：**不撞红线，直接跑**。用 numpy/scipy（已在 venv），30 分钟出基线。
- 方案 A/B（引入 sentence-transformers + PyTorch CPU、下载 BAAI/bge 模型）：**撞红线第 3 类（新外部依赖 + 联网抓取）**。照 GOAL.md §1 "跳过并记录"处置——**不停下来问用户**，把方案 A/B 记为 BLOCKED 写进 DECISIONS.md（附方案 C 的基线数字），然后换下一个任务。若方案 C 已过 80% 阈值，则 A/B 不需要做。
- **闸门先定后测**：hit rate ≥ 80% / 建向量耗时 ≤ 10 分钟 / 单次查询延迟 ≤ 2 秒 / 内存峰值 ≤ 4 GB / 13 道闸门零回退。达不到就记 BLOCKED，**不调闸门**（红线第 2 类）。
- 55 条手写转述用 D-029 已沉淀的那批（probes/probe_t7r_concept.py），**不手写新题**（GOAL §4 T1 手写错过两次）。
- 向量存 `data/index/knowledge.db`（Derived），**永不进 corpus.db**（corpus.db 每次 build 被 os.remove 删掉，K-02 先例）。
- 不改 FTS5 路径——embedding 是新通道，不替旧通道，两条并存。
- **三种结论都合法**：hit rate ≥ 80% → G1 PART 升 PASS；< 80% → 记 D-031 否决，G1 维持 PART。不预设结果。

### 2b. T5 A-12 五个抽取错误（最确定的缺陷）

`KR1a0007` 五处 span-degenerate（卦9初九 lenB=6、卦58九五 =9、卦46初六 =26 等）。孔穎達的交叉引用劫持了有序爻位搜索，而 validate_alignment 把它们计为 located——覆盖率指标看不见这类错误。

**R-02 已否决"取下一次出现"**（照 GOAL.md §4 T5）。给新候选的提示：正确候选不一定紧邻；选候选的信号**既不能是底本文本**（循环，会让准确率自我印证）**也不能只是段落长度**（不充分）。未验证的候选思路：排除括号注内的出现。**你自己列 2-3 个新候选方案，用本仓库的实测数据比较，选最优的直接执行**，把比较过程写进 DECISIONS.md。

### 2c. T7-q 知识图谱可行性实测（GraphRAG/LightRAG）

照 MASTER_PLAN.md §7："建图前须确认 differs 类異文不被实体抽取抹平"。**这是前置条件，先测它**——若 differs（`枯楊生稊/生梯`、`跛能履/破能履`）会被实体抽取抹平，知识图谱就 BLOCKED，不建图。differs 是校勘证据，必须保留，这正是 Work 与 Edition 分开建模的收益所在。

### 2d. T7-m `&KR0658;` 占位符语义

每部书 22–31 个；`differs` 类失败里多次出现。需查明这些占位符的语义并处置。

### 2e. T7-n `自天祐之` 在两源 5 vs 4 的真实差异

长期未查。查明原因，报告为源文差异或抽取错误。

### 2f. T7-o 55+ probes 归档整理

已沉淀结论的移入 `probes/archive/`，与 `src/`+`scripts/` 区分。降低技术债。

### 2g. T7-p Phase 3 架构自审

找过度设计与技术债，评审 `docs/BOOK_AI_ARCHITECTURE.md`（从未评审）。

### 2h. P-11 Euclid Book 5 Simson 追加命题（低优先）

`Prop. A.—Theorem (Simson)` 等 5 个 Casey 译本追加命题，非欧几里得正典。当前仅捕获 C（n=100），A/B/D/E 漏。低优先。

### 2i. P-10 已完成但需复验

本窗口修了 `_PROP_HEAD_RE` 的尾字符类从 `[\.\s]` 扩为 `[\.\s—–-]`，Euclid propositions 170 → 174。**你复验时若数字不符，先查 `_PROP_HEAD_RE` 当前定义**，不要相信本文件的 174。

---

## 3. 已 BLOCKED / REJECTED（不要重做，照 GOAL.md §1）

| 项 | 状态 | 依据 |
|---|---|---|---|---|
| G1 方案 2 联网抓取释义 | BLOCKED | D-030：无合规公版白话释义源（维基文库是文言古注非白话；黄寿祺/张善文在版权期；百度百科 licence 不明+可能含生成文本）|
| R-02 "取下一次出现" | REJECTED | 用一类错误且分数下降，照 §4 T5 |
| sunls2/zhouyi 入库 | REJECTED | 36.9% 在世作者（傅佩榮 1950—），无 LICENSE |
| 三个生成式占卜仓库 | REJECTED | 伪随机挑卦/无卦表/LLM 包装，属生成文本 |
| GPU embedding | REJECTED | 无 CUDA，MASTER_PLAN §9 |
| Milvus/Neo4j | REJECTED | 独立进程，7.4 GB 内存，§9 |
| 方案 A/B embedding（引入 PyTorch+下载模型）| BLOCKED 待授权 | 撞红线 3，照本文件 §2a 处置 |

---

## 4. 红线（GOAL.md §1 + §3 + §5 的浓缩，冲突时去读原文）

**自主决策，不要停下来问。** 遇到决策时：自己列 2–3 个方案，用本仓库的实测数据比较，选最优的直接执行，把比较过程写进 DECISIONS.md。

**三类不要自主执行，但处置方式是"跳过并记录"，不是"停下等人"**：

1. **破坏性且不可逆**：删 `data/raw/` 或 `data/external/` 原始语料、git push、重写历史。（重建 `data/index/corpus.db` **不属于**此类，它 5 秒可重建，随便重建。）
2. **为了让数字变好而放宽任何验收闸门**：见 GOAL.md §3，本项目红线。闸门先定后测，达不到就 BLOCKED，不调闸门。
3. **引入新的外部依赖或联网抓取新语料**：见 §5。撞上时把任务记 BLOCKED 写进 TASK_LEDGER.md（附原因与实测数据），**然后直接开始下一个任务**。

**已授权的（照上一窗口先例，可直接执行）**：
- commit / push 到 main（GOAL_NEXT_SESSION.md L67-72 上一窗口已记录用户授权）。push 不顺时用代理 `127.0.0.1:7897`：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin main`。
- 重建 corpus.db / knowledge.db（5 秒可重建，随便重建）。
- 联网抓取释义数据用于 G1 概念级（但 D-030 已确认无合规源，这条授权实际用不上）。

**法务（GOAL.md §5）**：绝对不可入库生成文本。每次获取必须记 `sha256 / source_url / fetched_at / licence`。版权按层判定不按文件判定。

---

## 5. 工作节奏（照 GOAL.md §4b）

- **每完成一小项立刻写台账**（TASK_LEDGER.md），不要攒着。台账是跨压缩、跨会话的唯一状态载体；写在对话里的结论会丢。
- **任何改动后跑一遍 §1 全部闸门**，任一闸门回退立刻回退改动，不调闸门。
- **撞上红线三类时不要停等**，按处置规则跳过并记录，直接开始下一个任务。
- **上下文会被压缩**，因此每条结论都要有可复现的命令。
- 任何时刻卡住超过两次尝试，就换任务并把卡点写进台账。台账 §4 清单足够长，永远有下一件事可做。

---

## 6. 文档职责（不要复制事实，只交叉引用，照 MASTER_PLAN.md §0）

| 文档 | 唯一拥有 |
|---|---|---|---|---|
| `MASTER_PLAN.md` | 目标、范围、架构、地址体系模型、实施顺序 |
| `TASK_LEDGER.md` | **任务状态 + 复验命令 + REJECTED 清单**（唯一状态来源）|
| `DECISIONS.md` | 每条技术决策及其实测依据（D-001…D-030）|
| `LESSONS.md` | 可迁移的工程教训（L-01…L-20）|
| `PROJECT_STATUS.md` | 当轮实测快照 |
| `BOOK_AI_ARCHITECTURE.md` | **仅** G1–G9 判据的定义（其余已过时，文首有说明）|
| `PROPOSAL_CPU_EMBEDDING.md` | T7-r CPU embedding 方案书（本窗口产出，待执行）|

环境：Python 3.14 venv、7.4 GB 内存、无 CUDA/Docker、代理 `127.0.0.1:7897`、Windows + Git Bash。
