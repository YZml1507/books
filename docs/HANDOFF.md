# 新窗口接手任务书

## 会话上下文

**前序会话ID**: `f918574d-beac-4f67-8d7f-5f2bcc555a20`  
**完整历史**: `C:\Users\Lenovo\.claude\projects\C--Users-Lenovo\f918574d-beac-4f67-8d7f-5f2bcc555a20.jsonl`

本会话已压缩多次。遇到矛盾时优先相信实测数据，用命令复验。

---

## 核心指令

0. **先读 `docs/PHASE.md` 的 `CURRENT_PHASE`**（当前 OPTIMIZE）决定自己在哪条轨：
   审查轨/优化轨双轨制，分工与闸门表见 PHASE.md；优化池见 `docs/OPTIMIZE_BACKLOG.md`，
   缺陷清单见 `docs/AUDIT_FINDINGS.md`，规范见 `specs/`。
1. **完整读** `docs/GOAL.md`，理解 §1 授权与约束、§4 任务优先级（§4 的 T1–T7
   早已全部 DONE，勿按它排队——实际优先级以台账末轮为准）
2. **完整读** `docs/TASK_LEDGER.md`，找出所有标记为 TODO/PART/未完成的任务
3. **按 §4 顺序连续执行**，不要停下来问意见
4. **每完成一小项立刻更新台账**（`TASK_LEDGER.md`）——这是跨压缩唯一状态载体

---

## 授权与红线

### ✅ 你有完全自主决策权
- 列方案 → 实测比较 → 选最优 → 直接执行
- 决策过程记入 `docs/DECISIONS.md`
- **包括 commit 和 push**——在任务结束报告中说明即可

### ⛔ 三类红线（标记 BLOCKED 写台账，然后继续下一个）
1. 破坏性不可逆操作（删源语料、rewrite history）
2. 为数字好看而放宽验收闸门
3. 引入新依赖或联网抓取新语料

### 🔒 并发约束
同一时刻只允许一个 agent 写 `src/guji/*.py`、`schema.sql`、`corpus.db`。  
子 agent 只做**只读勘查**。

---

## 关键原则

> **不要相信任何文档的结论和数字**——包括 `GOAL.md`、`TASK_LEDGER.md` 和本文档。

任何结论都先跑命令验证。`GOAL.md` §2 列了 8 条被推翻的错误结论。

---

## 已知待办（仅供参考，以你读台账后的判断为准）

前窗口提到但未验证的（R228s 复核更新）：
- ~~**P-05**: 焦氏易林 4,096 单元未纳入 G1 题库~~ **DONE**——eval_g1 已含 32 道易林题（现 248 题）
- ~~**P-06**: tier 2/3 五书解析器部分完成~~ **DONE**——五书全部入索引
- **W-04**: 京氏易傳编址标记 PART（59/62，3 处符号/内容错配）——仍属实，未清偿

**你自己判断**：
1. 这些是否真的未完成（读代码、跑命令验证）
2. 优先级是什么（按 `GOAL.md` §4）
3. 是否有新问题需要先解决

---

## 决策要求

遇到需要决策的地方：
1. **仔细思考**，列出不同方案
2. **实测比较**（不是猜测）
3. **选择最优解**（不是随便一个方向）
4. **直接执行**（不要问用户）

新发现的问题也要汇总、加入台账、解决。

可并行处理的任务派多个子 agent 并行（参考 `GOAL.md` §1b）。

---

## 任务结束报告格式

完成所有任务后，汇报：
1. 已完成哪些任务（附复验命令）
2. 自主做了哪些决策（附实测依据）
3. 新发现的问题（已加入台账）
4. Git 操作（commit/push 了什么）
5. 当前闸门状态（`scripts/assess_goals.py` 输出 + web 层闸门：`web/selftest.py`、
   `probes/probe_ui_smoke.py`、`probes/probe_contract.py`、`probes/probe_dollar_misuse.py`、
   `probes/probe_selftest_regress.py`、`probes/probe_first_screen.py`、
   `probes/probe_date_parity.py`——全集合见 TASK_LEDGER 开头闸门清单与 PHASE.md 闸门表；
   另 `probes/eval_xiaoman_llm.py` 为需真实 key 的人工复验工具，不进 CI）

---

## 立即行动

```powershell
# 0. 看当前阶段
#    type docs\PHASE.md 第三行（CURRENT_PHASE）

# 1. 看当前状态（语料侧 + web 侧）
.\.venv\Scripts\python.exe scripts\assess_goals.py
$env:BOOKS_LLM_DISABLE="1"
.\.venv\Scripts\python.exe web\selftest.py
.\.venv\Scripts\python.exe probes\probe_ui_smoke.py

# 2. 读任务书
# docs/GOAL.md（重点 §1 §4）
# docs/TASK_LEDGER.md（找 TODO/PART）

# 3. 开始执行
```

每完成一小步就更新台账，不要攒着！
