# 新窗口任务书 HANDOVER_20260816_R18_AUDIT — 审查轨（双窗口并行·第一轨）

> **本任务书的所有结论均不可轻信。** 你必须对每一项亲自核实代码与闸门，
> 发现台账/本文件/其他窗口任何口头结论与代码矛盾时，**以代码为准**并纠正台账。
> 历史已多次证明：正则工具结论会误判（knowledge SQL 注入正则误判 4 处实际全参数化）、
> 子 agent 声称的 P0 假阳性率约 70%、docstring 会与代码矛盾（douay"续行累加"实为丢弃、
> renderMD 声称 esc() 实为未调）、台账曾引用根本不存在的 DECISIONS 条目（D-050..D-062
> 上窗口漏写，R17 才补记）。**只看代码推断不算核实，边界输入必须亲自实跑复现。**

---

## 0. 双窗口并行协议（违反=互相踩踏，最高优先级纪律）

本窗口是**审查轨**；另一窗口（主仓）是**优化轨**（差距分析→优化文档→实施优化）。
两轨并行只在你严格遵守以下隔离时成立：

1. **你的工作区**：`C:/Users/Lenovo/Desktop/projects/books-audit`
   ——这是主仓的 git worktree，分支 `audit/R18`。
   **绝对禁止**在 `C:/Users/Lenovo/Desktop/projects/books`（主仓/优化轨）里
   跑任何命令、改任何文件。反向同样：优化轨不进你的目录。
2. **Python**：worktree 里没有 `.venv`（.gitignore 排除）。所有闸门命令用主仓绝对路径：
   ```
   C:/Users/Lenovo/Desktop/projects/books/.venv/Scripts/python.exe
   ```
   例如：`cd /c/Users/Lenovo/Desktop/projects/books-audit && C:/Users/Lenovo/Desktop/projects/books/.venv/Scripts/python.exe scripts/verify_index.py`
3. **文件所有权（硬边界）**：
   - 你独占：`scripts/`、`probes/`、`web_launcher.py`、`start_web.bat`、
     `books_app.spec`、`build/`、`dist/`、根目录 `temp_*.py`、散落 `*.zip`、
     `logs/`、`web_server*.log` 的**审查与修复**。
   - 禁改：`src/guji/**`、`web/**`（优化轨所有）；发现这些里面的问题
     **不要动手修**，记入你的台账条目标注"移交优化轨"，继续审你的范围。
   - `llm_config.json` 不在你的 worktree（.gitignore），审查轨不需要它。
4. **台账分区**：`docs/TASK_LEDGER.md` 你从 **§44[审查轨]** 起续编，轮次号
   `R18a、R19a…`；优化轨用 `§44[优化轨]/R18b…`。两轨各自 append-only，
   **绝不改写对方条目**。合并时文件尾冲突的解决规则：两段都保留，按轮次号排序。
   `docs/DECISIONS.md` 同理：你的决策从 **D-064a** 起编号，优化轨从 D-064b 起。
5. **commit/push/merge 协议**：
   - 每轮修复在 `audit/R18` 分支 commit（格式与 trailer 见 §4），`git push -u origin audit/R18`。
   - 13 闸门全绿后才允许 merge 回 main：
     ```
     git fetch origin && git rebase origin/main   # main 被优化轨推进过就先 rebase
     # 重跑 13 闸门确认 rebase 后仍全绿
     git checkout main && git merge audit/R18 && git push origin main
     ```
   - `data/index/corpus.db` 等闸门产物二进制冲突时：merge 后**重建**
     （build_index）再跑闸门，以重建产物为准提交，不手工挑 blob。
   - 主仓 remote 已无明文 PAT（R17 移除，credential manager 持有凭据），
     你的 worktree 共享同一凭据，push 直接可用。

---

## 1. 项目环境（上一窗口核实过，你仍须亲自验证）

- 主仓：`C:/Users/Lenovo/Desktop/projects/books`；你的 worktree：
  `C:/Users/Lenovo/Desktop/projects/books-audit`（分支 `audit/R18`，创建自
  main@0c5dff6 之后）。bash 工具走 Git Bash，用 `/` 路径。
- Python 3.14.7（Windows venv，工具在 `Scripts/`）。注意你的 worktree 无 venv，见 §0.2。
- 梯子：规则模式端口 `7897`，查询外网直接经此端口拉取。
- **13 闸门命令**（在你的 worktree 目录下执行；eval_g1 偶发 60s 超时需 timeout 180s）：
  ```
  PY=C:/Users/Lenovo/Desktop/projects/books/.venv/Scripts/python.exe
  $PY scripts/build_index.py        # 重建 corpus.db（merge 后产物冲突时用）
  $PY scripts/verify_index.py       # T1-T13 闸门
  $PY scripts/check_quality.py      # quality_report.json
  $PY scripts/assess_goals.py       # G1-G9 目标评估
  $PY probes/probe_conservation.py  # 越界检测
  $PY probes/probe_bcv.py           # 圣经 66 书控制
  $PY probes/probe_huangli_shensha.py
  $PY probes/probe_liuyao_najia.py
  $PY scripts/eval_g1.py            # 偶发超时
  $PY scripts/eval_g4.py
  $PY scripts/eval_g7.py
  ```
- **闭环标准**：verify_index ALL PASS + check_quality PASS + assess_goals G1-G9 PASS
  + 4 probe 全 PASS + eval_g1/g4/g7 PASS。

## 2. 基线状态（R17 收尾时核实，你必须亲自重跑核对）

- 13 闸门全绿。`works=44 units=61,732 db=55.2MB`。
- **`suspect=10 units / 5 地址`**（R17 修复后：20→10。旧文档写 20 属修复前状态，
  不要误报回退；T10 断言的是 >0 与 卦61上九 控制项，非硬编码 20）。
- R17 修复（commit 9e50cc1）：load_suspect 按 verdict 后缀归责（-B→B 作品），
  (EXPECTED) 非缺陷不入 suspect。若你重跑后 suspect≠10 units，先查是不是
  quality_report.json 变了，再怀疑代码。
- 决策链现状：TASK_LEDGER §43 / DECISIONS D-063（R17），D-050..D-062 为补记。

## 3. 你的审查范围（阶段B；已审模块勿重复，见 §5 名单）

1. **`scripts/` 全部脚本逐行深查**（此前仅抽样核实无 SQL 注入/subprocess/eval）：
   ask.py ask_bazi.py assess_coverage.py assess_goals.py backfill_*.py
   build_index.py check_*.py derive_*.py diagnose_yao.py dump_candidates.py
   eval_*.py merge_manifests.py probe_herodotus.py research_thread.py
   summarise_diff.py validate_alignment.py verify_index.py。
   重点：路径拼接/编码/异常冒泡/subprocess 与 shell 注入/临时文件/网络调用
   （research_thread.py probe_herodotus.py 可能走外网——经端口 7897 核实其行为）、
   对 corpus.db/knowledge.db 的写路径、退出码语义（闸门脚本误吞失败=闸门失效红线）。
2. **`probes/` 全部 probe 脚本**：断言是否真的在断言（probe 只 print 不断言=假闸门）。
3. **打包链**：`books_app.spec`、`web_launcher.py`、`start_web.bat`、`build/`、`dist/`：
   spec 是否打包了不该带的文件（llm_config.json/API key/日志）、启动脚本的路径假设、
   dist 产物是否陈旧到误导。
4. **根目录杂项盘点**：8 个 `temp_*.py`（逐个核实无人引用后处置：归档进
   `docs/archive/` 或删除，删除前 grep 全仓引用+你自己判断，保守优先归档）；
   4 个散落 zip（Agent-Reach/browser-use/markitdown/ui-ux-pro-max-skill）——
   逐个打开盘点内容、判断是否被项目引用（vendor/ 是否已含同样内容），
   处置进台账；`logs/`、`web_server*.log`（日志是否含敏感信息、是否该进 .gitignore）。
5. **`.gitignore` 完备性**：build/dist/logs/zip 是否该忽略而未忽略。

## 4. 纪律（与原任务书同级严苛，一条都不可松）

1. **绝不轻信**：本文件、台账、DECISIONS、优化轨窗口的任何结论、子 agent 声称、
   正则/工具输出，全部当"待复验"，亲自看代码+亲自实跑。矛盾以代码为准并纠正文档。
2. **子 agent 只做初筛**：可派 explore/general 子 agent 并行读代码，但其结论
   （尤其 P0/红线）一律"待复验"，亲自复现后才入账。历史假阳性率约 70%。
3. **正则只作初筛**：SQL 注入类必须逐行看 SQL 拼接；曾正则误判 4 处"非参数化"。
4. **docstring 不可信**：以代码为准；矛盾时修代码或修 docstring 使其一致，并入账。
5. **发现问题→入台账（§44[审查轨] 起，R18a…）→修复→修复中发现的新问题也入账
   并递归处理→13 闸门全绿→commit+push**，不留未闭环状态（上窗口曾中断留下
   未 commit 的台账，教训入 §7）。
6. **commit message**：`fix(模块): 简述 — R18a 审查`，英文写技术部分，
   末尾 trailer（HEREDOC 保留空行）：
   ```
   Co-Authored-By: AtomCode (GLM-5.2) <noreply@atomgit.com>
   ```
7. **决策自主**：需决策处（修/不修/怎么修/删/归档/merge 时机）亲自给出多个方案、
   权衡后选最优直接执行，**不问用户任何问题**。修复优先级：红线 > 中 > 低 > 文档对齐。
8. **闸门后才能 merge main**：见 §0.5。rebase 后必须重跑闸门，不轻信"应该没问题"。

## 5. 已审模块名单（勿重复审查，除非发现新红线）

liuyao / huangli / qiming / bazi / bazi_calc / lunar / ingest / web / douay /
search / knowledge / quality / answer / history / external / llm_reader /
variants / zhouyi / anchors / compare / evalset / bcv / play / yilin /
booksec / bazi_lookup / dual_engine（均为 src/guji 或 web，属优化轨领土，
你发现问题只记录移交、不动手）。

## 6. 流程（循环执行，除非用户明确叫停）

- **阶段A**：读本文件 + `docs/TASK_LEDGER.md` §43 + `docs/DECISIONS.md` D-063；
  在你的 worktree 亲自跑 13 闸门核对 §2 基线；异常先报告进台账再处置。
- **阶段B**：按 §3 顺序审查（可派子 agent 初筛，结论待复验）。
- **阶段C**：问题入台账 → 修复 → 13 闸门 → commit → push 分支 →（全绿且非高峰
  merge 冲突期）merge main。
- **阶段D**：你的范围全部审完且问题清零后，写审查轨总结（覆盖清单+残留风险），
  等价于优化轨的"优化文档"角色；然后回到阶段A复查优化轨 merge 进来的新代码
  （优化轨改 src/guji/web，其新代码进入你的复审视野——这是双轨的交叉制衡）。
- **阶段E**：循环，轮次 R19a、R20a…

## 7. 历史教训（继承自 R16 任务书，全部有实例）

1. 正则工具结论会误判（knowledge SQL 注入 4 处误判）。
2. 子 agent 的 P0 多为假阳性（约 70%）。
3. 台账/文档会过时或错误（R8 三轮才修成；台账曾引用不存在的 D-050..D-062）。
4. docstring 与代码矛盾（douay 续行、renderMD esc）。
5. 边界输入必须亲自实跑复现，不可只看代码推断。
6. 每轮修复完成立即 commit+push 闭环，中断=未闭环状态留给下个窗口。
7. **双窗口新增**：任何"顺手帮对面改一下"都是越界——记台账移交，不动手。
