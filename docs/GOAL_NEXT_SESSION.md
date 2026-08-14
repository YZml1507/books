# 下一窗口 Goal 任务书

用法：在新窗口里执行

```
/goal C:\Users\Lenovo\Desktop\projects\books <下面整段话>
```

或：把下面整段话原样复制粘贴给新窗口（等价于 /goal 加载本文）。

---

## 转发给新窗口的话（用户复制下面这段即可）

你是接手"books 引用系统"项目的自主执行 agent。本任务书一次性给你，之后连续执行不中断，遇决策自主选最优方案直接执行，撞红线跳过并记录，绝不停下来询问用户。

═══ 任务 ═══

先完整读 `docs/GOAL.md` 和 `docs/TASK_LEDGER.md`，自己判断哪些任务未完成、按优先级连续执行。所有决策自主做，任务结束后一次性汇报。每完成一小项立刻在 `docs/TASK_LEDGER.md` 加一行（状态/复验命令/产物），这是跨上下文压缩、跨会话的唯一状态载体——写在对话里的结论会丢。

═══ 当前 sessionID（查聊天记录细节用） ═══

本任务由上一个会话产出，sessionID = aa53987d-d690-4c1d-95d6-ddff26cd2888。
再往前：405e2cb4-bfbe-4df0-adf9-2553f0c675d4、a1732134-c6d5-4afb-b704-0a1354985a9a。
记录是磁盘普通文件，可直接 grep：
`C:\Users\Lenovo\.claude\projects\C--Users-Lenovo-Desktop-projects-books\<sessionId>.jsonl`
怀疑任何一条结论时，去 grep 那个 `.jsonl`，看当时命令的真实输出，而不是相信口头转述。grep 不到就当该说法不存在，重新自己测。

═══ 上一轮做了什么（commit ec3a9a6） ═══

1. **P-05 DONE**：跑 `scripts/derive_eval_yilin.py` 把 yilin 32 题注入 G1 题库，`scripts/eval_g1.py` 225/225 PASS。复验：`./.venv/Scripts/python.exe scripts/eval_g1.py` → G1 = PASS 225/225。
2. **P-06 DONE（复勘）**：实测 tier 2/3 五书已全部入索引（37 部 15,213 单元），scheme 分布 None 3457 / booksec 819 / play 817 / yilin 5032 / zhouyi 5088。复验：`sqlite3 data/index/corpus.db "SELECT scheme, count(*) FROM unit GROUP BY scheme"`。
3. **T7-r DONE**：`probes/probe_t7r_concept.py` 实测 char-bigram TF-IDF + cosine 在 10 条手写转述上 hit rate (correct addr in top-10) = 8/10 = 80.0%，exact-rank-1 rate = 8/10 = 80.0%，EXIT=0。结论：CPU embedding 可行。
4. **U-06 DONE**（本窗口接手并完成）：Douay-Rheims 接入索引 35,787 单元 scheme='bcv'，13 道闸门零回退。**此前结论"75 个不同书名"已被实测推翻**（实测 73 个）；**此前结论"bcv.VERSE_RE 应能匹配 Douay"已被实测推翻**（VERSE_RE 在 group2 后要求 `\s+`，Douay 是 `1:1.` 点紧跟非空白，`VERSE_RE.match('1:1. In the beginning')` 返回 None，`bcv.parse_verses` 对 Douay 返回 0 节——接入必须给 Douay 单独解析路径 `src/guji/douay.py`）。**接入过程发现真实缺陷（已修复）**：`search.at_address` 未过滤 scheme，Douay bcv addr1=chapter 与 卦号冲突，`at_address(99)` 误把 Psalms 99 当"卦99"返回 5 段经文，eval_g7 impossible 4/4→3/4；修复加 `AND u.scheme='zhouyi'`，eval_g7 恢复 4/4=100%，G7=PASS。**Vulgate 编号特性已显式记录**：Psalms 113 合并 Protestant 诗篇 114+115（章内经文号 1-8 重置，8 个同-(C:V) 重复）；Proverbs 12:12 同节号印两次文本不同（1 个同-(C:V) 重复）；合计 9 个，`probe_bcv.py` 标为 `DOUAY_EXPECTED_CONFLICTS`，任何新增冲突变 FAIL。

**最终闸门快照（13/13 通过）**：check_quality PASS · build_index 8.5s 37 部 15,213 单元 32.5 MB · verify_index ALL PASS（T1–T11）· validate_alignment 爻辭 verified 1824/1872 = 97.4% · probe_conservation TOTAL 2653857 = 2653857 missing 0.0000% invented 0.0000% ratio 1.0000 · assess_goals PASS 8 · PART 1 · FAIL 0 · NOT-MEASURABLE 0 of 9 · check_provenance 0/37 missing · probe_bcv control cases PASS EXIT=0 · eval_g1 G1 = PASS 225/225 EXIT=0 · summarise_diff EXIT=0 · eval_g7 FABRICATIONS 0 G7 = PASS EXIT=0 · probe_g8_isolation PASS EXIT=0 · eval_g4 yilin cells 4096 G4 = PASS EXIT=0。

**本窗口（U-06 Douay 接入）后实测快照（13/13 通过）**：build_index 9.6s 37 部 **51,000 单元** 42.1 MB（Douay +35,787 bcv 单元，scheme 分布 zhouyi 5088 / yilin 5032 / bcv 35787 / None 3457 / booksec 819 / play 817）· verify_index ALL PASS · validate_alignment 爻辭 verified 1824/1872 = 97.4% 零回退 · probe_conservation ratio 1.0000 · assess_goals PASS 8 · PART 1 · FAIL 0 · eval_g1 G1 = PASS 225/225 · eval_g7 G7 = PASS（修复 at_address scheme 过滤后 impossible 4/4=100%）· probe_bcv control cases PASS（Douay 35,787 verses，9 个已知 Vulgate 冲突显式记录）· eval_g4 G4 = PASS · probe_g8_isolation PASS · check_provenance 0/37 missing。

G 判据明细：**G1 PART**（逐字层全覆盖，概念层未覆盖，FTS5 做不到）· G2-G9 全 PASS。**G1 是唯一非 PASS 项。**

═══ 绝对纪律：不可全信任务书与既有文档 ═══

上一个会话多次给出过错误的口头结论，全部被实测推翻（GOAL.md §2 列了 9 条先例，包括撰写警告文档的同时往里塞没测过的数字——一边写"不要相信口头结论"一边往同一份文档里塞没测过的数字，说明这类错误不是偶发疏忽而是默认行为）。因此：

1. 文档里的数字一律当"待复验"，不是事实。事实只在脚本输出里。
2. 任何一条结论，先跑对应命令确认再往下走。跑不出来就当它是错的。
3. 发现文档与实测不符时，改文档并写明"此前结论已被推翻"——本项目保留错误记录（见 DECISIONS.md D-008 那段被划掉的结论），不是悄悄改掉。
4. 如果你轻信口头结论直接下结论导致错误，将受到极其严重的惩罚。任何可疑点必须自己查证，确认正确后才可继续，绝对不可凭口头结论直接下结论——否则极大概率得出错误结论。
5. 不要把"数字没变"当作"没有收益"，也不要把"数字变好"当作"改对了"。两者都出现过反例。
6. 这条纪律同样适用于本任务书本身：本任务书里若有任何数字、状态声明、结论与仓库实测不符，以仓库实测为准，并反过来修正本任务书。本任务书不是权威，脚本输出才是。
7. 默认怀疑级别设为最高：任何一句话——无论来自上一个会话、来自本文、来自 docs/ 下任何文档、来自台账——在没有对应可执行命令复验通过之前，一律视为"未经证实"，不得据此推进。宁可重测一遍已对的事，不可放过一次可能错的事。
8. 连"看起来显然对"的结论也要测。本项目最严重的失效是平静地返回一段原文里不存在的文字（GOAL.md §2 末段），而这类缺陷在所有计数型检查下都通过——"看起来对"永远不构成证据。只有可执行命令的真实输出构成证据。

═══ 三条红线（撞上跳过+记 BLOCKED/REJECTED，不停下问） ═══

1. **破坏性且不可逆的操作** —— 删除 `data/raw/` 或 `data/external/` 下的原始语料、重写历史。（`git push` **不属于**此类，见下方 git 授权。重建 `data/index/corpus.db` 也不属此类，5 秒可重建，随便重建。）
2. **为了让数字变好而放宽任何验收闸门** —— 见 GOAL.md §3，本项目红线。
3. **不引入新外部依赖或联网抓取新语料** —— 见 §5。**例外（用户已明确授权）**：用户已授权"联网抓取释义数据"用于 G1 概念级题库。这是 G1 概念级方案 2，**允许执行**。抓取的释义数据必须记 `sha256 / source_url / fetched_at / licence`（照 W-06 先例）。若抓取的释义数据无明确 licence 或属生成文本（GOAL §5：五个外部"周易"项目三个是生成的），**不得入库**，记 BLOCKED。

撞上时：不停下询问，把当前任务标记为 `BLOCKED` 或 `REJECTED` 写进 `TASK_LEDGER.md`（附原因与实测数据），**然后直接开始下一个任务**。§4 的清单足够长，永远有下一件事可做。

尤其是第 2 类：如果某个任务看起来**只能**靠放宽闸门才能完成，那么正确结论是**这个任务的当前方案错了**——照 R-02 的先例把它记为 `REJECTED` 并附数据，换任务。不要问用户是否可以放宽。答案是不可以。

除此之外：改代码、加模块、重建索引、写探针、改文档、否决自己的方案、派子 agent、`git commit`、`git push`，全部自主进行，不要征求意见。

═══ git 授权（用户明确授予） ═══

用户已授权：**该 commit/push 时就 commit/push，不需要询问用户意见。**

- `git commit`：每完成一个可验证的小里程碑就 commit，commit message 用 Conventional Commit 格式，结尾加 `Co-Authored-By: AtomCode (GLM-5.2) <noreply@atomgit.com>`（HEREDOC 保留空行）。
- `git push`：推到 `github.com/YZml1507/books` 私有库的 `main` 分支。**这是用户明确授权的操作**，不属于"破坏性不可逆操作"红线。push 前先 `git pull --rebase` 处理远程更新。
- **例外**：`git rebase -i`、`git commit --amend`、`git reset --hard`、`git push --force` 这些重写历史的操作**仍是红线**，除非用户明确要求。

═══ 决策方式 ═══

遇决策：自己列 2–3 个方案，用本仓库实测数据比较，选最优直接执行，把比较过程写进 `docs/DECISIONS.md`。不问用户。

═══ 可派子 agent 并行 ═══

GOAL.md §1b 列了 6 组可并行任务（A–F）。子 agent 负责只读勘查与产出方案（写自己的 `probes/probe_*.py` 和结论），对 `src/` 与索引的修改收回主线串行执行，每次改完跑一遍 §3 全部闸门。硬约束：同一时刻只允许一个 agent 写共享状态（`src/guji/*.py`、`schema.sql`、`corpus.db`），否则会重演 L-01 事故（同一张折叠表两份拷贝对同样字节给出相反结论）。子 agent 之间不要共用探针文件名。

═══ 环境 ═══

- Python 3.14 venv 在 `.\.venv\Scripts\python.exe`。
- 无 CUDA/Docker。AMD Ryzen 5 4600U 6-core 2.1GHz，7.4GB RAM。
- 代理 `127.0.0.1:7897`。
- PowerShell——内联 `python -c` 会被花括号和引号搞坏，写成脚本文件。
- git 已装 `F:\Program Files\Git\cmd\git.exe`，用前 `set PATH=%PATH%;F:\Program Files\Git\cmd;F:\Program Files\Git\mingw64\bin`。
- 仓库已推 `github.com/YZml1507/books`（私有）。

═══ 八条复验命令（任何改动后必须全过） ═══

见 GOAL.md §3。任一闸门回退→立刻回退你的改动，不要调闸门。验收判据必须在看数据之前定下。

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py      # 先跑：产出 quality_report.json
.\.venv\Scripts\python.exe scripts\build_index.py        # 重建索引（约 5 秒）
.\.venv\Scripts\python.exe scripts\verify_index.py       # 12 项验收，须 ALL PASS
.\.venv\Scripts\python.exe scripts\validate_alignment.py # 对齐，须 >= 1824/1872
.\.venv\Scripts\python.exe probes\probe_conservation.py  # 守恒，须 delta 0 / ratio 1.0000
.\.venv\Scripts\python.exe scripts\assess_goals.py        # G1–G9
.\.venv\Scripts\python.exe scripts\check_provenance.py    # provenance，须 0/37 缺失
.\.venv\Scripts\python.exe probes\probe_bcv.py            # 第二地址体系，须 control cases PASS
```

═══ 下一窗口的任务清单（按优先级） ═══

### 任务 1：U-06 Douay-Rheims 接入索引（最高优先，勘查已完成）

**现状**：Douay-Rheims 在 `data/raw_ext/generality/bible-douay/pg1581.txt`（5,880,420 字节，144,111 行），勘查完成但未接入索引。`corpus.db` 里 Douay 0 单元（work 表有 1 条记录）。`ingest.py` 完全没引用 Douay（grep No matches）。

**勘查结论（实测）**：
- 1334 个 `"X Chapter N"` 章标题（如 `Genesis Chapter 1`），**73 个**不同书名（**此前结论"75 个"已被实测推翻**——73 来自 `^(\S.+) Chapter (\d+)\s*$` 全量匹配），全部正典数对齐：Genesis 50、Isaias 66、Psalms 150、Matthew 28 等。
- 经文格式 `"1:1. In the beginning God created heaven, and earth."`——与 KJV 几乎一致（只多一个点）。
- **此前结论"bcv.py 的 VERSE_RE = ^\s{0,6}(\d{1,3}):(\d{1,3})\s+(\S.*)$ 应能匹配 Douay"已被实测推翻**：`VERSE_RE` 在 group2 后要求 `\s+`，但 Douay 是 `1:1.`（点紧跟，非空白），所以 `VERSE_RE.match('1:1. In the beginning')` 返回 None。实测：`bcv.parse_verses` 对 Douay 返回 0 节。**接入必须给 Douay 单独的解析路径**（见 `src/guji/douay.py`，已实现）。

**实施方案**：
1. 在 `ingest.py` 加 `bible-douay` 路由，走 `douay.parse_verses`（**已实现**：`src/guji/douay.py`，独立解析路径，因为 `bcv.VERSE_RE` 不能匹配 Douay 的 `C:V.` 点号格式——此前的"应能匹配"已被实测推翻）。
2. 跑 `check_provenance.py` 确认 provenance 0 缺失（Douay 已在 work 表，provenance 可能已齐）。
3. 跑全 13 道闸门确认零回退。
4. 若 13 道闸门全过，`git commit` 然后 `git push`。
5. 在 `TASK_LEDGER.md` 记一行。

**验收判据（先定后测）**：
- Douay 单元数 > 0（接入成功）。**实测：35,787 单元，scheme='bcv'**。
- 13 道闸门零回退。**实测：13/13 全过**。
- `assess_goals.py` 仍 PASS 8 · PART 1 · FAIL 0（不降级）。**实测确认**。

**接入过程实测发现的真实缺陷（已修复）**：
- `search.at_address(gua, ...)` 原先只过滤 `WHERE u.addr1 = ?`，不带 `scheme` 过滤。Douay 接入后 `bcv` 单元的 `addr1=chapter` 与 卦号冲突：`at_address(99, None)` 把 Douay Psalms 99（bcv, addr1=99）误当"卦99"返回 5 段经文，导致 `eval_g7` 的 impossible-address 测试从 4/4 退到 3/4。**修复**：`at_address` 加 `AND u.scheme = 'zhouyi'` 过滤，eval_g7 恢复 4/4=100%，G7 = PASS。

**Douay 接入实测的 Vulgate 编号特性（已显式记录于 `probes/probe_bcv.py`，不静默放宽）**：
- Psalms 113：Vulgate 把 Protestant 诗篇 114+115 合并为一章，章内经文号 1-8 重置一次（8 个同-(C:V) 重复）。
- Proverbs 12:12：同一节号 12:12 印两次，文本不同（1 个同-(C:V) 重复）。
- 合计 9 个同-(C:V) 重复，全部是源版本特性而非解析器 bug。`probe_bcv.py` 把这 9 个标为 `DOUAY_EXPECTED_CONFLICTS`，任何新增冲突都会变 FAIL。

### 任务 2：G1 概念级检索尝试（用户已授权方案 1）

**现状**：G1 是唯一 PART 项。逐字层全覆盖（225/225 PASS），但概念层（转述/语义）检索未覆盖，FTS5 做不到。T7-r 已实测 char-bigram TF-IDF + cosine 在 10 条手写转述上 80% 命中正确地址。

**用户授权（明确）**：用户已明确说"我授权联网抓取释义数据"。**方案 2（联网抓取释义数据）允许执行**。方案 1（手写转述）作为 fallback 也可执行——如果方案 2 抓取的数据无明确 licence 或属生成文本（GOAL §5），记 BLOCKED 转方案 1。

**实施方案（方案 2，用户已授权联网）**：
1. **抓取释义数据**：从公开周易释义源（如百度百科、维基文库、或公版注疏白话译本）抓取 64 卦的爻辭白话释义。抓取前先查 `data/raw/` 里是否已有白话释义（KR1a0006 王弼注、KR1a0031 朱熹本義等可能有，先 grep 实测）。**如果语料内已有白话释义，优先用语料内的，不联网**（照 GOAL §5"验证不需要新书"原则）。
2. **记录 provenance**：抓取的释义数据必须记 `sha256 / source_url / fetched_at / licence`（照 W-06 先例）。无明确 licence 或属生成文本的，**不得入库**，记 BLOCKED。
3. **构建概念级题库**：用抓取的释义作为查询（白话转述），gold 答案是语料中逐字存在的爻辭原文+地址。用 `derive_eval_g1.py` 的自动抽取+人工审核方法，不手写 gold（手写 gold 在本项目错过两次：屯六二漏 `匪寇婚媾`，爻位写错）。
4. **验证概念级检索**：在 `probes/probe_t7r_concept.py` 基础上跑扩充题库，记录 hit rate。
5. **正式纳入 eval_g1.json**：若 hit rate ≥ 80%（T7-r 基线）且释义数据 provenance 合规，把概念级题目纳入 `eval_g1.json`。
6. 跑 `eval_g1.py` 确认全过。若 G1 概念层达标，`assess_goals.py` 的 G1 可从 PART 升 PASS——**但只有当概念层题目确实覆盖且全过才可升**，不要为了让数字变好而虚升。
7. `git commit` 然后 `git push`。在 `TASK_LEDGER.md` 记一行。

**实施方案（方案 1 fallback，不联网）**：
1. 在 `probes/probe_t7r_concept.py` 基础上扩充手写转述题库（从 10 条扩到 ~30-50 条，覆盖更多卦）。
2. 跑扩充后的 probe，记录 hit rate。
3. 若 hit rate ≥ 80%，考虑把概念级题目正式纳入 `eval_g1.json`。
4. 跑 `eval_g1.py` 确认全过。
5. `git commit` 然后 `git push`。在 `TASK_LEDGER.md` 记一行。

**验收判据（先定后测）**：
- 概念级题库覆盖 ≥ 20 条转述（方案 1）或 ≥ 64 卦释义（方案 2）。
- hit rate ≥ 80%（T7-r 基线）。
- 若纳入 eval_g1.json：`eval_g1.py` 全过 EXIT=0。
- 13 道闸门零回退。

**红线提醒**：不要为了升 G1 而：
- 引入新外部依赖（方案 2 联网抓取已授权，但抓取的数据无 licence/属生成文本时不得入库）。
- 放宽 eval_g1.py 的判据（target 95%/100% 不变）。
- 手写 gold 当事实（手写 gold 在本项目错过两次：屯六二漏 `匪寇婚媾`，爻位写错）。

### 任务 3：A-12 / T5 五个抽取错误（可选，独立推进）

**现状**：`KR1a0007` 五处 `span-degenerate`（卦9初九 lenB=6、卦58九五 =9、卦46初六 =26 等），孔穎達的交叉引用劫持了有序爻位搜索，而 `validate_alignment` 把它们计为 located——覆盖率指标看不见这类错误。

**R-02 已否决"取下一次出现"**。给下一次尝试的提示：正确候选不一定紧邻；选候选的信号既不能是底本文本（循环，会让准确率自我印证）也不能只是段落长度（不充分）。未验证的候选思路：排除括号注内的出现。

**实施方案**：
1. 先读 `REJECTED` R-02 和 `anchors._repair_degenerate`（标注为负结果的代码）。
2. 实测五个错误的当前状态（跑 `validate_alignment.py` 看 span-degenerate 计数）。
3. 尝试"排除括号注内的出现"候选思路。
4. 每次改完跑全 13 道闸门，任一回退立刻回退改动（照 R-02 先例，若新方案也导致一类错误换另一类错误且分数下降，记 REJECTED）。
5. `git commit` 然后 `git push`。在 `TASK_LEDGER.md` 记一行。

═══ 节奏建议 ═══

任务 1（U-06 接入）→ 任务 2（G1 概念级）→ 任务 3（A-12，可选）。任何时刻卡住超过两次尝试就换任务，把卡点写进台账。

═══ 收尾 ═══

所有可做任务做完或撞红线被记 BLOCKED/REJECTED 后，一次性汇报：做了什么、每条决策的实测依据、哪些被否决及数据、最终闸门快照、下一步该从哪接。汇报里任何一条结论都要附对应复验命令——没有命令的结论不可信。
