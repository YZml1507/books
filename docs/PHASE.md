# PHASE

    CURRENT_PHASE: REPAIR

唯一有效的阶段标记就是上面那一行。任何窗口读它决定自己该做什么。

---

## 谁能改这个文件

**只有审查轨（验收窗口）能改 `CURRENT_PHASE`。**
优化轨（修复窗口）对本文件只读——修复方不得自己宣布完工（宪法第一条
NON-NEGOTIABLE：本项目历史上多次口头结论被后来实测推翻）。

## 阶段定义

### REPAIR（当前）
目标：让它能用。修复轨清偿 `AUDIT_FINDINGS.md` 里 OPEN 的 BLOCKER/MAJOR，
并完成 web 层分层重构与 LLM 移除。

此阶段**禁止**：美化、动效、配色调整、功能扩展。先能用，再好看。

### OPTIMIZE
目标：性能 + 年轻化视觉 + 功能扩展。
审查轨写 `specs/003-youth-ui-revamp/spec.md`（只 WHAT/WHY），
优化轨写同目录 `plan.md` / `tasks.md` 并实现（宪法第六条）。

## REPAIR → OPTIMIZE 的四条闸门

四条必须**同时**成立，且每条在下方登记时附一条可复现命令（宪法第一条：
任何状态断言必须附能复现它的命令，跑不出来就当它是错的）。

| # | 闸门 | 复验命令 |
|---|---|---|
| 1 | `AUDIT_FINDINGS.md` 中状态 OPEN 且级别 BLOCKER/MAJOR 的条目为 **0** | `<py> scripts\count_open_findings.py`（退出码 0） |
| 2 | web 层自测全绿 | `<py> web\app.py --selftest`（退出码 0） |
| 3 | UI 冒烟全绿（每个按钮点后有内容且 console 无 error） | `<py> probes\probe_ui_smoke.py`（退出码 0） |
| 4 | 宪法第四条 13 道闸门全绿 | 见 `constitution.md` §IV 命令清单 |

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

**闸门必须有非零退出码**（宪法第四条 U-08 教训：`probe_bcv.py` 曾永远返回 0）。
本轮新建的三个脚本均已确认：`count_open_findings.py` 实测返回 1、
`probe_ui_smoke.py` 实测返回 1、`probe_contract.py` 实测返回 1。
「永远返回 0 的闸门等于没有闸门」。

## 附加闸门（R118a 新建，非翻阶段必需但建议纳入）

| # | 闸门 | 复验命令 |
|---|---|---|
| 5 | 前后端字段名契约无漂移 | `<py> probes\probe_contract.py`（退出码 0） |

闸门 5 与闸门 3 分工不重叠：3 抓「点了没反应」（运行时行为），
5 抓「点了有反应但读错字段」（静态契约）。R000a-04 三处漂移属后者——
它不抛异常、console 干净、结果区只是永远空白，只有闸门 5 能永久防再犯。

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
