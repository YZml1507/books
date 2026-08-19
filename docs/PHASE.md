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
| 1 | `AUDIT_FINDINGS.md` 中状态 OPEN 且级别 BLOCKER/MAJOR 的条目为 **0** | 人工点数 + probe 引用 |
| 2 | web 层自测全绿 | `.\.venv\Scripts\python.exe web\selftest.py` |
| 3 | UI 冒烟全绿（每个按钮点后有内容且 console 无 error） | `.\.venv\Scripts\python.exe probes\probe_ui_smoke.py` |
| 4 | 宪法第四条 13 道闸门全绿 | 见 `constitution.md` §IV 命令清单 |

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
