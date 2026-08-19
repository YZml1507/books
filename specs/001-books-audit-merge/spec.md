# Feature Specification: books-audit → main 融合

**Feature Branch**: `audit/R18 → main`
**Created**: 2026-08-19
**Status**: Draft
**Input**: User description: "融合 books-audit (audit/R18 分支) 到 books (main 分支)，确保 13 道闸门零回退"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 审查轨成果回流到主仓 (Priority: P1)

**作为**项目维护者，**我想要**把审查轨（`audit/R18` 分支）的审查成果安全地合并到主仓（`main` 分支），**以便**项目的最终代码同时包含优化轨的能力和审查轨的修复。

**Why this priority**: 这是项目当前最高优先级的事项。审查轨已经运行了多个周期，积累了大量修复和文档更新。不合并，这些成果只存在于一个 worktree 中，随时可能丢失。

**Independent Test**: 执行完整的 merge 流程后，`main` 分支包含 `audit/R18` 的所有提交，且 13 道闸门全部通过。

**Acceptance Scenarios**:

1. **Given** `audit/R18` 分支已 rebase 到 `origin/main` 上，**When** 执行 `git merge audit/R18`，**Then** `main` 分支包含 `audit/R18` 的所有提交且无冲突
2. **Given** merge 完成，**When** 重跑 13 道闸门，**Then** 全部 PASS（零回退）
3. **Given** merge 完成且闸门全绿，**When** `git push origin main`，**Then** 远端 `main` 与本地一致
4. **Given** 融合完成，**When** 删除 `audit/R18` 分支和 `books-audit` worktree，**Then** 项目回到单一工作区状态

### User Story 2 - 融合过程可复验 (Priority: P2)

**作为**项目维护者，**我想要**融合的每一个步骤都有可复验的命令和明确的检查点，**以便**下次融合时可以重放，或者出问题时可以回滚。

**Why this priority**: 项目历史上出现过多次"口头结论与实测不符"的情况。融合过程必须可复验，不能靠记忆。

**Independent Test**: 融合结束后，从 `TASK_LEDGER.md` 中读出融合步骤和对应命令，逐条重跑，全部通过。

**Acceptance Scenarios**:

1. **Given** 融合流程已执行，**When** 按 `TASK_LEDGER.md` 记录的步骤重跑，**Then** 每一步的结果与记录一致
2. **Given** 融合过程中出现冲突，**When** 按既定协议处理（docs 冲突取 `--theirs`，二进制产物重建），**Then** 冲突解决后 13 道闸门仍全绿

### Edge Cases

- **merge 冲突**：`docs/` 下的 append-only 冲突按协议取 `--theirs`；代码冲突逐行审查。
- **二进制产物冲突**：`corpus.db` / `knowledge.db` 等 merge 后**重建**（build_index），不手工挑 blob。
- **rebase 后回归**：rebase 后和 merge 后各跑一次全量闸门，确认无回归。
- **领土越界**：确认审查轨没有动 `src/guji/**` 和 `web/**`（优化轨领土）。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 融合流程必须包含 rebase、13 闸门验证、merge、push 四个阶段
- **FR-002**: 每个阶段必须有明确的进入条件和退出条件
- **FR-003**: 冲突处理必须有明确规则（docs 取 theirs，代码逐行审，二进制重建）
- **FR-004**: 融合后必须重跑 13 道闸门确认零回退
- **FR-005**: 融合过程必须记录到 `TASK_LEDGER.md`（含复验命令）
- **FR-006**: 融合完成后可选清理 `audit/R18` 分支和 `books-audit` worktree

### Key Entities

- **Git 分支**：`main`（目标）、`audit/R18`（源）、`origin/main`（远端）
- **Worktree**：`books`（主仓）、`books-audit`（审查轨）
- **闸门产物**：`data/index/corpus.db`、`data/index/knowledge.db`、`data/catalog/quality_report.json`

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `main` 分支的 commit 数量 ≥ `audit/R18` 的 commit 数量（融合不丢失提交）
- **SC-002**: 13 道闸门全部 PASS（零回退）
- **SC-003**: `web --selftest` 全 PASS
- **SC-004**: 融合过程记录到 `TASK_LEDGER.md`，每步有复验命令
- **SC-005**: 融合后 `git status --short` 无未提交的改动（除重建的二进制产物外）

## Assumptions

- **A-001**: `audit/R18` 分支当前处于可 merge 状态（13 闸门全绿，pending 清空）
- **A-002**: `origin/main` 没有未拉取的提交（已 `git fetch origin`）
- **A-003**: 用户已授权 push 到 `github.com/YZml1507/books` main
- **A-004**: Python 环境在 `books/.venv/` 中可用
- **A-005**: 梯子（代理端口 7897）可用（如需拉取外部数据）
- **A-006**: 审查轨的领土边界已确认（`src/guji/**` 和 `web/**` 未被越界修改）