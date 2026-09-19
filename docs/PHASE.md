# PHASE

    CURRENT_PHASE: OPTIMIZE

唯一有效的阶段标记就是上面那一行。任何窗口读它决定自己该做什么。

---

## 谁能改这个文件

**只有审查轨（验收窗口）能改 `CURRENT_PHASE`。**
优化轨（修复窗口）对本文件只读——修复方不得自己宣布完工（宪法第一条
NON-NEGOTIABLE：本项目历史上多次口头结论被后来实测推翻）。

## 阶段定义

### REPAIR（已完成，2026-08-20 由 R120a 翻出）
目标：让它能用。修复轨清偿 `AUDIT_FINDINGS.md` 里 OPEN 的 BLOCKER/MAJOR，
并完成 web 层分层重构与 LLM 移除。

此阶段**禁止**：美化、动效、配色调整、功能扩展。先能用，再好看。

> **R190b 订正**：本行原写「REPAIR（当前）」，与本文件第 3 行
> `CURRENT_PHASE: OPTIMIZE` 直接矛盾（该行自 R120a 起就是 OPTIMIZE）。
> 此前结论已被推翻：阶段早在 2026-08-20 翻过，本行是漏改。
> 保留错误记录而非悄悄改掉（宪法第一条 + DECISIONS D-008 先例）。

### OPTIMIZE（当前）
目标：性能 + 年轻化视觉 + 功能扩展。
审查轨写 `specs/003-youth-ui-revamp/spec.md`（只 WHAT/WHY），
优化轨写同目录 `plan.md` / `tasks.md` 并实现（宪法第六条）。

## REPAIR → OPTIMIZE 的四条闸门

四条必须**同时**成立，且每条在下方登记时附一条可复现命令（宪法第一条：
任何状态断言必须附能复现它的命令，跑不出来就当它是错的）。

| # | 闸门 | 复验命令 |
|---|---|---|
| 1 | `AUDIT_FINDINGS.md` 中状态 OPEN 且级别 BLOCKER/MAJOR 的条目为 **0** | `<py> scripts\count_open_findings.py`（退出码 0） |
| 2 | web 层自测全绿 | `<py> web\selftest.py`（退出码 0） |
| 3 | UI 冒烟全绿（每个按钮点后有内容且 console 无 error） | `<py> probes\probe_ui_smoke.py`（退出码 0） |
| 4 | 宪法第四条 13 道闸门全绿 | 见 `.specify/memory/constitution.md` §IV 命令清单 |

`<py>` = `C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`
（`.venv` 被 gitignore，不在本 worktree 内，两轨共用主 worktree 的解释器）。

**R118a 对本表的两处订正（宪法第一条：闸门必须是可复现命令）**：

1. 闸门 1 原写「人工点数 + probe 引用」。人工点数不是命令，且实测会数错——
   裸 `Select-String '^- 状态：OPEN'` 得 10，真实条目是 9（多命中的是本文件
   「条目格式」示范块）。已落成 `scripts/count_open_findings.py`，退出码即判据。
2. 闸门 2 原写 `web\selftest.py`——**该文件不存在**（实测
   `Get-ChildItem web -Filter *.py` 只有 `app.py`）。web 层自测的真实入口是
   `web\app.py --selftest`。若优化轨完成 web 分层重构、真的拆出
   `web/selftest.py`，届时由审查轨改回并附实测输出。

   > **R190b 订正（上一段的条件已经发生，闸门 2 的命令表已改回）**：
   > R178b 完成了 web 分层重构，`web/selftest.py` **已存在**，而
   > `web/app.py` 缩到 90 行且 `sys.argv` 出现 0 次——照原命令跑
   > `web\app.py --selftest` 会**起一个 8123 端口的服务**并挂住，不是自测。
   > 实测复现：`grep -c sys.argv web/app.py` → `0`；
   > `<py> web\selftest.py` → 退出码 0、`web self-test PASS (149 checks)`。
   > 此前结论（「该文件不存在」）已被推翻，保留原文备查。

**闸门必须有非零退出码**（宪法第四条 U-08 教训：`probe_bcv.py` 曾永远返回 0）。
本轮新建的三个脚本均已确认：`count_open_findings.py` 实测返回 1、
`probe_ui_smoke.py` 实测返回 1、`probe_contract.py` 实测返回 1。
「永远返回 0 的闸门等于没有闸门」。

## 附加闸门（R118a / R119a 新建，非翻阶段必需但建议纳入）

| # | 闸门 | 复验命令 |
|---|---|---|
| 5 | 前后端字段名契约无漂移 | `<py> probes\probe_contract.py`（退出码 0） |
| 6 | 零 `$.xxx` 误用（`$()` 是函数不是对象） | `<py> probes\probe_dollar_misuse.py`（退出码 0） |
| 7 | selftest 断言只增不减（钉基线防放水） | `<py> probes\probe_selftest_regress.py`（退出码 0） |
| 8 | 生成叙述文本不入语料库 | `<py> probes\probe_no_generated_in_corpus.py`（退出码 0） |
| 9 | 全部脚本可 import（防改名断裂） | `<py> probes\probe_scripts_importable.py`（退出码 0） |

后续新建检查脚本不再逐行登记本表——**附加闸门以台账最近一轮判据行为准**
（现另有 `probes\probe_first_screen.py`、`web\baseline_voice.py`、
`web\check_poster.py`、`web\check_async_ai.py`、`web\check_warm_voice.py`、
`web\check_xingzuo.py`、`web\check_plain_first.py`）。

三个闸门判据互不重叠，一个闸门一个判据：

- **闸门 3**（真浏览器）抓「点了没反应」——运行时行为。
- **闸门 5**（字段契约）抓「点了有反应但读错字段」。R000a-04 三处漂移属此类：
  不抛异常、console 干净、结果区只是永远空白，只有闸门 5 能永久防再犯。
- **闸门 6**（静态 `$.`）秒级、零依赖，供修复轨改完先自查再跑 3 分钟的闸门 3；
  并覆盖闸门 3 的一处天然盲区——`searchByWork()`（书目卡片点击跳检索）里的
  那 1 处误用不在任何按钮 handler 内，逐个点按钮永远覆盖不到。

闸门 3 与闸门 6 构成**独立见证**（宪法第三条偏离 4）：R119a 实测两侧交叉吻合
——静态说只有 3 个 handler 干净（#form / #worksBtn / #newsRefresh），
真浏览器恰好也只有这 3 个通过。

MINOR / NIT **不构成**闸门条件。它们进 `OPTIMIZE_BACKLOG.md`，
不得用来阻塞阶段推进——这是本协作模型唯一会死锁的地方。

## 翻阶段登记（append-only）

翻阶段时在此追加一条，附四条闸门各自的实测输出摘要。

<!-- 例：
### 2026-08-2x REPAIR → OPTIMIZE  by 审查轨 R2xa
1. OPEN BLOCKER/MAJOR = 0（AUDIT_FINDINGS.md 计数 0，全部 VERIFIED）
2. web selftest: PASS (N checks)
3. probe_ui_smoke: PASS (M buttons, 0 console errors)
4. 13 gates: ALL PASS（逐条输出见 logs/gates_2026xxxx.txt）
-->

### 2026-08-19 阶段**不翻**（保持 REPAIR）by 审查轨 R118a

首轮建立前端闸门。四条逐条实测，**第 1、3 条不成立**，故 `CURRENT_PHASE`
保持 `REPAIR`。这条登记的意义是把"为什么还不能翻"变成可复验记录。

1. **闸门 1 = FAIL**。`<py> scripts\count_open_findings.py` → 退出码 1，
   末行 `OPEN BLOCKER 4 / OPEN MAJOR 5 / 合计 9`。
   9 条 = R000a-01/02/03/04/05（移交条目，本轮已逐条自行复现确认成立）
   + R118a-01/02/03/04（本轮新发现）。
2. **闸门 2 = PASS**。`<py> web\app.py --selftest` → 退出码 0，
   `web self-test PASS (130 checks)`。
3. **闸门 3 = FAIL**。`<py> probes\probe_ui_smoke.py` → 退出码 1，
   `32 个用例，PASS 4 / FAIL 28`。真浏览器实测原文：7 个按钮抛
   `pageerror: Cannot read properties of undefined (reading 'value')`，
   8 个 `.rsec` 面板点标签后仍不可见，`#dailyMore` 点击后 DOM 零变化，
   排盘结果区渲染出 `[object Object]` 且 `<strong>` 嵌套深度 3 / 注释节点 32。
   完整输出：`logs/probe_ui_smoke_r118a.txt`，失败截图 `logs/ui_smoke/FAIL_*.png`。
4. **闸门 4 = PASS**。13 道闸门逐条实测退出码全 0：
   check_quality PASS（works with any junk: 30）/ build_index 47 works
   62,109 units 14.5s / verify_index ALL PASS（T11 median 0.991、362 compared）
   / validate_alignment（→ alignment_score.json）/ probe_conservation PASS
   （missing 0.0000% invented 0.0000% ratio 1.0000）/ assess_goals G1–G9 全 PASS
   / check_provenance 0/47 missing / probe_bcv PASS（kjv 66/66、web 66/66）
   / eval_g1 PASS（8 项全 PASS）/ eval_g4 PASS（yilin outgoing 520 targeted 490）
   / eval_g7 PASS（30/30、25/25、4/4、FABRICATIONS 0）/ probe_g8_isolation PASS
   / probe_booksec PASS（Darwin 14 distinct chapters）。

**附加闸门 5（本轮新建）= FAIL**。`<py> probes\probe_contract.py` → 退出码 1，
`118 个字段读取点，HARD=10 TYPE=1 SOFT=15 SKIP=0`。
完整输出：`logs/probe_contract_r118a.txt`。

### 2026-08-19 阶段**不翻**（保持 REPAIR）by 审查轨 R119a

`git merge main` → `Already up to date.`，修复轨本轮无新提交，
`AUDIT_FINDINGS.md` 无 `FIXED-R<n>b` 可复验。本轮把缺陷清单补完整。

1. **闸门 1 = FAIL**。`<py> scripts\count_open_findings.py` → 退出码 1，
   `OPEN BLOCKER 4 / OPEN MAJOR 5 / 合计 9`（与 R118a 一致，无条目被修复）。
2. **闸门 2 = PASS**。R118a 已实测 `web self-test PASS (130 checks)` 退出码 0；
   本轮 `git diff -- src web` 为空（被测代码零改动），结论仍有效。
3. **闸门 3 = FAIL**。`<py> probes\probe_ui_smoke.py` → 退出码 1，
   `32 个用例，PASS 5 / FAIL 27`。相比 R118a 的 PASS 4：`btn:works` 由 FAIL
   转 PASS——它此前是被 R000a-03 遮挡**点不到**，不是真坏。这条修正很重要：
   避免修复轨去"修"一个没坏的按钮。
4. **闸门 4 = PASS**。R118a 已逐条实测 13 道闸门退出码全 0；本轮
   `git diff -- src web` 为空，未重跑（无被测代码改动即无回归面）。

附加闸门：**5 = FAIL**（`probe_contract` 退出码 1，
`HARD=10 TYPE=1 SOFT=15 SKIP=0`）；**6 = FAIL**（本轮新建
`probe_dollar_misuse` 退出码 1，`49 行 / 61 处`）。

→ 闸门 1、3 不成立，`CURRENT_PHASE` 保持 `REPAIR`。

### 2026-08-20 REPAIR → **OPTIMIZE** by 审查轨 R120a

`git merge main` 纳入优化轨 95ce343（R178b 分层重构 + 移除 LLM + 前端拆分）。
三个 append-only 文档冲突，按宪法第五条**两段都保留**解决（审查轨实测证据 +
优化轨状态标记），未丢任何一侧、未改写对方条目。

四条闸门**同时成立**，每条附实测命令与输出：

**闸门 1 = PASS**　`<py> scripts\count_open_findings.py` → 退出码 **0**
`OPEN BLOCKER 0 / OPEN MAJOR 0 / 合计 0`。9 条全部 `VERIFIED-R120a`——
**每条都是审查轨自己重跑复现命令确认的**，不凭优化轨报告签字
（宪法第一条 NON-NEGOTIABLE）。

**闸门 2 = PASS**　`<py> web\selftest.py` → 退出码 **0**
`web self-test PASS (138 checks)`。断言数 130 → 138。
**已验证不是靠放宽换来的**（宪法第二条红线第 2 项）：新建
`<py> probes\probe_selftest_regress.py` 逐名比对，实测
`130 - 1 + 9 = 138`，唯一消失的 `ask.llm.shape` 由 `ask.interpretation.shape`
接管，且**新断言更强**（`web/selftest.py:671-677` 断言 interpretation 是
dict、ok is True、engine 含「无 LLM」、sections 与 citations 非空、
两次同输入 text 完全相等）。改名已登记进 `probes/selftest_baseline.json`。

**闸门 3 = PASS**　`<py> probes\probe_ui_smoke.py` → 退出码 **0**
`35 个用例，PASS 35 / FAIL 0`（R118a 时是 PASS 4 / FAIL 28）。
真浏览器逐个点击实测：9 个 tab 全部「面板可见」、3 个 subtab 全部
「子标签 active」、`#dailyMore`「点击后 DOM 有变化」、16 个提交按钮全部
渲染出真实内容（排盘 31893 字符、深度研究 18735 字符、六爻 4308 字符…）、
`dom:bazi.strong-nesting` 实测 `<strong>` 嵌套层数 **0**、注释节点 **0**、
375px 视口横向溢出 **0px**、首屏零 console.error。
完整输出 `logs/probe_ui_smoke_r120a.txt`。

**闸门 4 = PASS**　13 道闸门逐条实测**退出码全 0**：
check_quality PASS / build_index 47 works 62,109 units（suspect 10）/
verify_index **ALL PASS**（T11 median 0.991、362 compared）/
validate_alignment / probe_conservation PASS（missing 0.0000%、
invented 0.0000%、ratio 1.0000）/ assess_goals **G1–G9 全 PASS** /
check_provenance 0/47 missing / probe_bcv PASS（kjv 66/66、web 66/66）/
eval_g1 PASS / eval_g4 PASS（outgoing 520、targeted 490）/
eval_g7 PASS（30/30、25/25、4/4、**FABRICATIONS 0**）/
probe_g8_isolation PASS / probe_booksec PASS。

附加闸门（R118a–R120a 新建）同样全绿：
**5** `probe_contract` 退出码 0 —— 191 个字段读取点，`HARD=0 TYPE=0 SKIP=0`
（R118a 时 HARD=10 TYPE=1）；
**6** `probe_dollar_misuse` 退出码 0 —— 58 个函数名 0 处属性误用，
**含阳性对照**（注入 `val.rq.value` → 退出码 1 抓到，还原 → 0）；
**7** `probe_selftest_regress` 退出码 0 —— 断言只增不减；
**8** `probe_no_generated_in_corpus` 退出码 0 —— 生成叙述文本在
corpus.unit / derived / evidence **零命中**，同时**阳性对照 6/6** 引文可在
语料中定位（证明搜索路径真的有效，零命中不是搜索失灵）；
**9** `probe_scripts_importable` 退出码 0 —— 88 个模块 131 处 guji 引用全部
有效，**含阳性对照**。

**本轮在审查轨自己领土发现并修掉的一处断裂**：`scripts/ask_bazi.py --llm`
因 R178b 删除 `guji.llm_reader` 而崩溃（实测退出码 1、
`ImportError: cannot import name 'llm_reader' from 'guji'`）。已改走
`guji.interpreter` 确定性引擎，`--llm` 保留为别名不破旧命令；实测退出码 0、
两次运行输出**逐字节相同**（4297 chars）。这类缺陷 13 道闸门覆盖不到
（闸门只跑其中 9 个脚本），故新建闸门 9 永久防再犯。

→ **`CURRENT_PHASE` 由 `REPAIR` 翻为 `OPTIMIZE`。**
下一步：审查轨写 `specs/003-youth-ui-revamp/spec.md`（只 WHAT/WHY），
`plan.md` / `tasks.md` 由优化轨写（宪法第六条，文件级分工避免冲突）。

### 2026-08-20 阶段保持 OPTIMIZE（复验 R179b 无回归）by 审查轨 R122a

R179b 是 REPAIR 遗留清偿 + 闸门兼容修复，不改变阶段。四条闸门复跑确认无回归：

1. **闸门 1 = PASS**　`<py> scripts\count_open_findings.py` 退出码 0，
   `OPEN BLOCKER 0 / OPEN MAJOR 0`。R118a-03 经实测确认真修好——
   `/api/bazi` evidence 全 12 条 citation 非空，且出处格式为
   `search.py:24 render_citation()` **单一实现**（未在第二处复制，避开 L-01）。
2. **闸门 2 = PASS**　`<py> web\selftest.py` 退出码 0，**140 checks**（R120a 138）。
3. **闸门 3 = PASS**　`<py> probes\probe_ui_smoke.py` 退出码 0，**36/36**。
   首跑曾 29 PASS / 6 FAIL，追查为**双轨命名协调事故而非产品缺陷**
   （详见 DECISIONS.md D-145a）：probe 把对方内部命名钉成契约，
   已改为运行时从 DOM 发现。
4. **闸门 4 = PASS**　13 道闸门退出码全 0。

附加闸门 5–9 退出码全 0。
