# Implementation Plan: books-audit → main 融合

**Branch**: `audit/R18 → main` | **Date**: 2026-08-19 | **Spec**: `specs/001-books-audit-merge/spec.md`

**Input**: Feature specification from `specs/001-books-audit-merge/spec.md`

**Note**: 本 plan 是融合完成后的 retrospective 文档，记录实际执行的技术方案与决策。

## Summary

将审查轨（`audit/R18` 分支，42 commits）的安全审查成果合并到主仓（`main` 分支，53 commits），
采用 rebase + fast-forward merge 策略，确保 13 道闸门零回退。

## Technical Context

**Language/Version**: Python 3.14.7 (Windows venv, 工具在 `Scripts/` 非 `bin/`)
**Primary Dependencies**: FastAPI, SQLite FTS5, PyMuPDF, markitdown, bge-small-zh-v1.5
**Storage**: SQLite (data/index/corpus.db 55.7MB, knowledge.db), data/history.db
**Testing**: 13 道闸门 + web --selftest (125 checks)
**Target Platform**: Windows 桌面应用（PyInstaller 单文件 exe 218MB）
**Project Type**: 桌面应用（FastAPI web server + Python 后端 + 静态前端）
**Constraints**: 离线可用（语料本地索引），无 CUDA（CPU embedding），代理端口 7897

## Constitution Check

*GATE: 本节逐条评估宪法原则 I–VI*

### I. Fact-First Discipline ✅
- 所有数字均通过实际运行 13 道闸门验证，非口头结论
- 宪法中引用的 GOAL.md §0a/§2、DECISIONS.md D-001/D-003/D-005/D-008/D-012、LESSONS.md L-01 均已逐条核实存在
- Rebase 冲突解决、merge 结果、闸门输出均为实际命令输出

### II. Red-Line Governance ✅
- 未删除任何 data/raw/ 或 data/external/ 下的原始语料
- 未放宽任何验收闸门
- 未引入新的外部依赖
- push 到 origin/main 已按 GOAL.md 授权执行

### III. Architecture Integrity ✅
- 融合未修改分层架构
- 审查轨的代码裁剪（animotion CSS 删除、dayun_relation 删除、mcp_server 简化）是 deliberate 的设计选择，非意外破坏
- 四处偏离（双引擎/归一化/双地址/独立见证）在融合后仍完整保留

### IV. Gate-Driven Verification ✅
- Rebase 后跑 13 道闸门：全部 PASS
- Merge 后跑 13 道闸门：全部 PASS（零回退）
- web --selftest: 125 checks PASS

### V. Dual-Track Isolation ✅
- 审查轨（books-audit worktree）与优化轨（books main）严格隔离
- 审查轨只修改了 docs/（TASK_LEDGER.md, DECISIONS.md）和 scripts/assess_goals.py
- 未越界修改 src/guji/** 或 web/**（优化轨领土）
- 融合后 worktree 和分支已清理，项目回到单一工作区

### VI. Specification-First Workflow ✅
- spec.md 先于 plan.md 先于代码执行
- 本 plan.md 记录了实际执行的技术方案

## Project Structure

### 本次融合涉及的文件

| 文件 | 变更 | 来源 |
|---|---|---|
| `docs/DECISIONS.md` | 5140 行变更 | 审查轨决策记录（D-064a 起） |
| `docs/TASK_LEDGER.md` | 8083 行变更 | 审查轨任务台账（§44[审查轨] 起） |
| `scripts/assess_goals.py` | 18 行变更 | 审查轨修复（R21a） |
| `data/index/corpus.db` | 重建 | build_index.py 产物 |
| `data/history.db` | 更新 | 运行时产物 |
| `.specify/` | 新建 | spec-kit SDD 框架 |
| `specs/` | 新建 | 功能 spec 目录 |

### 融合后项目结构

```
books/                           ← 唯一工作区
├── .specify/                    ← SDD 框架（新增）
│   ├── memory/constitution.md
│   ├── templates/
│   ├── scripts/
│   └── init-options.json
├── specs/                       ← 功能 spec（新增）
│   └── 001-books-audit-merge/
│       ├── spec.md
│       └── plan.md
├── docs/                        ← 完整记录（审查轨 + 优化轨）
├── src/guji/                    ← 核心代码（未变）
├── web/                         ← 前端（已简化，无 animotion）
├── scripts/ probes/             ← 13 道闸门脚本
└── data/                        ← 语料库
```

## Research

### Rebase 策略选择

**选 rebase 而非直接 merge 的理由：**
- 审查轨（audit/R18）的 42 个 commit 需要线性地叠在优化轨（main）的 53 个 commit 之上
- Rebase 后 fast-forward merge，历史干净、可追溯
- Rebase 过程中逐行解决了 docs/ 冲突（取 --theirs），确认无代码冲突

### 冲突解决规则

| 冲突类型 | 规则 |
|---|---|
| `docs/DECISIONS.md` | 取 --theirs（审查轨版本），保留完整决策记录 |
| `docs/TASK_LEDGER.md` | 取 --theirs（审查轨版本），保留完整台账 |
| 代码文件 | 无冲突（审查轨的代码变更是删除操作，rebase 时自动应用） |
| 二进制产物 | merge 后重建（build_index），不手工挑 blob |

### 功能裁剪决策

审查轨在融合前做了三处 deliberate 的功能裁剪：

| 裁剪项 | 决策 | 理由 |
|---|---|---|
| animotion CSS (4 文件, 12,438 行) | 接受删除 | 审查轨简化方向，消除 StaticFiles 攻击面，离线更可靠 |
| hehun.dayun_relation (32 行) | 接受删除 | 功能裁剪，如需可重新 spec 添加 |
| mcp_server 自测块 (61 行) | 接受删除 | 简化方向，可通过 `python -m guji.mcp_server --selftest` 替代 |

## Quickstart

### 验证融合结果

```powershell
cd C:\Users\Lenovo\Desktop\projects\books

# 1. 确认 git 状态干净
git status --short
# 期望：无输出（或仅有 data/ 下的运行时产物）

# 2. 确认 main 包含审查轨提交
git log --oneline | Select-Object -First 5
# 期望：顶部为 5864ff7 (R117a) 及其前序审查轨提交

# 3. 跑 13 道闸门
.\.venv\Scripts\python.exe scripts/check_quality.py
.\.venv\Scripts\python.exe scripts/build_index.py
.\.venv\Scripts\python.exe scripts/verify_index.py
.\.venv\Scripts\python.exe scripts/validate_alignment.py
.\.venv\Scripts\python.exe probes/probe_conservation.py
.\.venv\Scripts\python.exe scripts/assess_goals.py
.\.venv\Scripts\python.exe scripts/check_provenance.py
.\.venv\Scripts\python.exe probes/probe_bcv.py
.\.venv\Scripts\python.exe scripts/eval_g1.py
.\.venv\Scripts\python.exe scripts/eval_g4.py
.\.venv\Scripts\python.exe scripts/eval_g7.py
.\.venv\Scripts\python.exe probes/probe_g8_isolation.py
.\.venv\Scripts\python.exe probes/probe_booksec.py
# 期望：全部 PASS

# 4. Web 自测
.\.venv\Scripts\python.exe web/app.py --selftest
# 期望：PASS (125 checks)
```

### 预期结果

```
git status --short              → 无输出
git log --oneline -3            → 5864ff7 (R117a), 97c8631 (R116a), 7a709c9 (R115a)
13 gates                        → ALL PASS
web --selftest                  → PASS (125 checks)
```