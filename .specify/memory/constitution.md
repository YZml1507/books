<!--
SYNC IMPACT REPORT
==================
Version change: (template/unratified) → 1.0.0
Bump rationale: Initial ratification of a concrete constitution for the 古籍智慧助手
(books) project, derived from the project's existing governance documents
(GOAL.md, MASTER_PLAN.md, DECISIONS.md, TASK_LEDGER.md, HANDOVER_*.md) and
the spec-kit SDD framework. MAJOR baseline because it establishes binding
governance where none previously existed at the spec-kit level.

Principles defined:
  I.   Fact-First Discipline (NON-NEGOTIABLE)
  II.  Red-Line Governance
  III. Architecture Integrity
  IV.  Gate-Driven Verification
  V.   Dual-Track Isolation
  VI.  Specification-First Workflow

Added sections:
  - Fact-First Discipline
  - Red-Line Governance
  - Architecture Integrity
  - Gate-Driven Verification
  - Dual-Track Isolation
  - Specification-First Workflow
  - Governance

Templates reviewed for alignment:
  ✅ spec-template.md — generic structure; no constitution-specific tokens; user stories,
     requirements, success criteria, assumptions sections all valid for books project.
  ✅ plan-template.md — Constitution Check gate (line 39) remains valid; gates now
     concretely populated by Principles I–VI at plan time.
  ✅ tasks-template.md — task categories (setup/foundational/story/polish) already
     accommodate fact-verification, gate-running, and dual-track tasks.
  ✅ constitution-template.md — replaced with books-specific constitution.

Follow-up TODOs: none. RATIFICATION_DATE set to first adoption date below.
-->

# 古籍智慧助手 (books) Constitution

**古籍智慧助手**（`books` 项目）是一个桌面应用：既能**读书**（检索/比对/注家/研究线程），
也能**算命/算八字**（排盘/运算/古籍依据/大白话解读），未来扩展占卜/择日/起名/外部资讯。

本宪法是项目所有开发活动的最高法则。任何 spec、plan、task、代码、文档均不得违反本宪法。
违反时，处置方式是 **改 spec/plan/tasks**，而不是稀释或 reinterpret 宪法原则。

---

## Core Principles

### I. Fact-First Discipline (NON-NEGOTIABLE)

**所有数字、状态断言、"已完成"声明——必须可复验，否则视为不存在。**

- **任何数字、任何状态断言、任何"已完成"声明——先跑对应命令确认，再往下走。**
  跑不出来就当它是错的。这是 GOAL.md §0a 的最高纪律，不是客套话。
- **遇到可疑或矛盾的地方，必须亲自去查看源码/数据/聊天记录查证，查证无误后才继续。**
  绝对不可以根据口头结论直接下结论。
- **发现文档与实测不符时，改文档并在文档里写明"此前结论已被推翻"。**
  保留错误记录（DECISIONS.md D-008 先例），不是悄悄改掉。
- **不要把"数字没变"当作"没有收益"，也不要把"数字变好"当作"改对了"。**
  两者都出现过反例。
- **不许偷懒走捷径**：跳过复验、凭印象写结论、把"看起来对"当证据、
  为了省事不动手查证——任何形式的走捷径视为严重违规。
- **唯一可信的状态来源是可执行脚本**，不是文档里的句子。
  任何状态断言必须附一条能复现它的命令。

**Rationale:** 本项目历史会话多次给出过错误的口头结论，全部被后来的实测推翻。
GOAL.md §2 列了 9 条先例。这不是信任问题，是系统性风险——
没有这条原则，项目会在错误结论上越走越远。

### II. Red-Line Governance

**三类操作绝对不可自主执行。但处置方式是「跳过并记录」，不是「停下等人」：**

1. **破坏性且不可逆的操作** —— 删除 `data/raw/` 或 `data/external/` 下的原始语料、
   `git push`（到 main 的 push 已授权，见下）、重写历史。
   - 重建 `data/index/corpus.db` **不属于**此类，它 5 秒可重建，随便重建。
   - `git push` 到 `github.com/YZml1507/books` main 已授权——历次窗口记录用户授权。
   - 重写历史仍红线。
2. **为了让数字变好而放宽任何验收闸门** —— 如果某个任务看起来**只能**靠放宽闸门
   才能完成，那么正确结论是 **这个任务的当前方案错了**。照 R-02 先例把它记为
   `REJECTED` 并附数据，换任务。不要问用户是否可以放宽。答案是不可以。
3. **引入新的外部依赖或联网抓取新语料** —— 见 MASTER_PLAN.md §2。

**处置规则（这条关系到能否长时间连续工作）：** 撞上以上任一类时，
**不要停下来询问**。把当前任务标记为 `BLOCKED` 或 `REJECTED` 写进
`docs/TASK_LEDGER.md`（附原因与实测数据），**然后直接开始下一个任务**。

**Rationale:** "停下来问"会打断长时间连续工作流。"跳过并记录"保证了
项目永远有下一件事可做，同时保留了完整的决策痕迹。

### III. Architecture Integrity

**分层架构不可越界。任何改动必须在正确的层：**

```
Source Adapter   Kanripo · Gutenberg · Local        + provenance(sha256/url/time/licence)
       ↓
Parse Layer      双引擎并行 → 分歧即质量闸门          ★偏离1
       ↓
Normalise        異體字折叠 · 占位符 · 逐字切分        ★偏离2
       ↓
Structure        单元切分 + 双地址 + 层(layer)        ★偏离3
       ↓
Quality Gate     独立见证交叉校验 → 损坏/缺陷分类      ★偏离4
       ↓
Index            SQLite FTS5（逐字切分）+ 元数据
       ↓
Agent            检索即推理：判型→选书→读→扩展→验证
       ↓
Output           答案 + 引用 + 证据充分性判定
```

- **偏离 1 — 解析层双引擎**（D-001）：两个引擎失败方式相反：PyMuPDF 静默产出
  看似合理的错字，markitdown 显式输出 `(cid:N)`。分歧处即不可信字符。
- **偏离 2 — 归一化是独立可测层**（D-003）：異體字折叠必须在索引与查询**两端**施加。
- **偏离 3 — 每个单元两个地址**（D-005）：页锚点是版本局部的，能引用不能对齐；
  正典地址能对齐不能指向印本位置。对不上就是 `unknown`，不猜。
- **偏离 4 — 质量闸门用独立见证，不用表面统计**（D-012）：**没有已知阳性对照的
  质量闸门等于没有闸门。**
- **绝对不可入库的一类内容：生成文本。** 这条是硬约束,不是偏好。
  外部数据入库前必须判定它是**文献**还是**生成物**，判据是「能否追溯到印本/底本」。

**Rationale:** 四处偏离都是由实测强制的，不是审美偏好。越界修改架构
会导致不可预测的连锁反应。

### IV. Gate-Driven Verification

**13 道闸门是 merge 的硬前提。任何改动后必须全绿。**

闸门命令（顺序重要：`check_quality.py` 必须在 `build_index.py` **之前**跑）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\verify_index.py
.\.venv\Scripts\python.exe scripts\validate_alignment.py
.\.venv\Scripts\python.exe probes\probe_conservation.py
.\.venv\Scripts\python.exe scripts\assess_goals.py
.\.venv\Scripts\python.exe scripts\check_provenance.py
.\.venv\Scripts\python.exe probes\probe_bcv.py
.\.venv\Scripts\python.exe scripts\eval_g1.py
.\.venv\Scripts\python.exe scripts\eval_g4.py
.\.venv\Scripts\python.exe scripts\eval_g7.py
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py
.\.venv\Scripts\python.exe probes\probe_booksec.py
```

**13 道闸门全部有非零退出码。** 上一轮的八道里 `probe_bcv.py` 其实**永远返回 0**，
包括它打印「56/66 卷」的那一次——见 U-08。**永远不接受"永远返回 0"的闸门。**

**Rationale:** 闸门是项目的生命线。没有闸门的 merge 等于没有 merge 标准。

### V. Dual-Track Isolation

**审查轨与优化轨并行，有严格的文件所有权边界：**

| 轨道 | 独占文件 | 禁改 |
|---|---|---|
| **审查轨** (`books-audit` worktree) | `scripts/`、`probes/`、`web_launcher.py`、`start_web.bat`、`books_app.spec`、`build/`、`dist/`、根目录 `temp_*.py`、散落 `*.zip`、`logs/`、`web_server*.log` | `src/guji/**`、`web/**` |
| **优化轨** (`books` main) | `src/guji/**`、`web/**` | `scripts/`、`probes/` |

- **同一时刻只允许一个 agent 写共享状态。** 共享状态指：
  `src/guji/*.py`（尤其 variants.py 的折叠表、anchors.py、ingest.py）、
  `src/guji/schema.sql`、`data/index/corpus.db`（build_index.py 会删掉重建）。
- **理由不是洁癖，是本项目的真实事故**：同一张折叠表存在两份拷贝，
  对同样的字节给出了相反结论（`LESSONS.md` L-01）。
- **推荐工作方式**：子 agent 负责**只读的勘查与产出方案**（写自己的
  `probes/probe_*.py` 和结论），把对 `src/` 与索引的修改**收回主线串行执行**。
- **台账分区**：`docs/TASK_LEDGER.md` 两轨各自 append-only，
  **绝不改写对方条目**。审查轨从 §44[审查轨] 起续编（R18a、R19a…），
  优化轨用 §44[优化轨]/R18b…。合并时文件尾冲突的解决规则：两段都保留，按轮次号排序。
- **`docs/DECISIONS.md` 同理**：审查轨从 D-064a 起编号，优化轨从 D-064b 起。

**Rationale:** 两个 agent 同时改 `variants.py` 或同时 `build_index.py`，
会重演 L-01 的事故且更难察觉。

### VI. Specification-First Workflow

**Spec-Driven Development (SDD) 是项目的默认工作流。**

- **规格是第一公民，代码是规格的生成物。** 不是"先写代码再补文档"，
  而是"先写规格，代码从规格生成"。
- **每个 feature 必须先有 spec.md，再有 plan.md，再有 tasks.md，最后才到代码。**
  四个产物缺一不可。
- **spec.md 只写 WHAT 和 WHY，不写 HOW。** 不涉及技术栈、API、代码结构。
  写给非技术干系人看，不是写给开发者看的。
- **plan.md 是 spec 到代码的桥梁。** 包含技术上下文、宪法检查、
  数据模型、接口契约、快速入门验证。
- **tasks.md 是可执行的勾选清单。** 每个 task 必须有 ID、文件路径、
  依赖关系。格式：`- [ ] [TaskID] [P?] [Story?] Description with file path`
- **analyze 是只读的。** 它不改任何文件，只产出一致性分析报告。
  宪法冲突自动标为 CRITICAL。
- **converge 是对齐工具。** 对比 spec/plan/tasks 与实际代码，填补差距。

**Rationale:** SDD 消除了"意图"与"实现"之间的鸿沟。
当规格驱动实现时，变更需求不再是障碍，而是系统性的重新生成。

---

## Fact-First Discipline (detailed)

### 可复验命令清单

每个状态断言必须附带至少一条可复现它的命令。以下是项目的标准复验命令：

```powershell
# 全量闸门（顺序重要）
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\verify_index.py
.\.venv\Scripts\python.exe scripts\validate_alignment.py
.\.venv\Scripts\python.exe probes\probe_conservation.py
.\.venv\Scripts\python.exe scripts\assess_goals.py
.\.venv\Scripts\python.exe scripts\check_provenance.py
.\.venv\Scripts\python.exe probes\probe_bcv.py
.\.venv\Scripts\python.exe scripts\eval_g1.py
.\.venv\Scripts\python.exe scripts\eval_g4.py
.\.venv\Scripts\python.exe scripts\eval_g7.py
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py
.\.venv\Scripts\python.exe probes\probe_booksec.py

# Web 自测
.\.venv\Scripts\python.exe web/app.py --selftest

# Git 状态
git log --oneline -5
git status --short
```

### 文档与代码冲突时

**以代码为准。** 发现文档与实测不符时：
1. 改文档
2. 在文档里写明"此前结论已被推翻"
3. 保留错误记录（DECISIONS.md D-008 先例），不是悄悄改掉

---

## Governance

本宪法 supersede 一切 ad-hoc convention。现有代码模式是权威参考，但不得违反本宪法。

- **Authority.** 原则 I–VI 是 binding gates。
  plan.md 的「Constitution Check」阶段必须逐条评估。
  `/speckit.analyze` 把宪法冲突自动标为 CRITICAL。
  **违反的解决方式是改 spec/plan/tasks，而不是稀释原则。**
- **Amendments.** 本宪法的变更需要 rationale + 版本 bump。
  任何 amendment 必须 propagate 到依赖的模板和命令 guidance，
  并在 Sync Impact Report 中记录。
- **Versioning policy (SemVer for governance).**
  MAJOR = backward-incompatible governance 或原则 removal/redefinition；
  MINOR = 新原则/section 或 materially expanded guidance；
  PATCH = clarifications and non-semantic refinements。
- **Compliance review.** 每个 PR 和 review 必须 verify compliance。
  Added complexity 或任何 deviation 必须在 PR 中 justified。
  Unjustified violations block merge。

**Version**: 1.0.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19