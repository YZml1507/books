### R218a-巡5 修复记录（2026-08-26 晚，优化轨，回应审查轨 R218a-巡5 交单）

审查轨 commit：无（审查轨只动 docs/UX_REVIEW_QUEUE.md）
优化轨 commit：50ad845

#### F-005 桃花应期年龄错位

**根因**：`warm_taohua` 用固定 `_user_birth_year_approx = _now.year - 22` 估算用户年龄。对 1990 年生用户，2003 年（13 岁）被误判为"±5 岁近"，导致童年应期上屏。

**修法**（2 处）：
1. `web/services.py`：`taohua()` 返回 dict 加 `"birth_year": by`（additive，零行为风险）
2. `src/guji/voice.py` `warm_taohua()`：
   - 改用 `t.get("birth_year")` 获取真实出生年份
   - `_near` 过滤从 `abs(year_start - birth_year_approx) <= 5` 改为 `abs(start_age - _user_age) <= 5`（直接用 dayun 自带的 start_age 字段）
   - 同年计算用户年龄 `_user_age = _now.year - _user_birth_year`

**实测**（`.venv/Scripts/python` 端到端跑 1990-05-15 女盘）：
- dayun_hits: `[{'pillar': '己卯', 'start_age': 13.1, 'year_start': 2003}]`
- 旧逻辑输出：`2003年前后走己卯运...`（年龄错位）
- 新逻辑输出：`未来某段时间你的社交运势会有变化——节奏上的参考，不是日程表。`（PASS）
- 成年用例（2013 年，age 33）：正常显示 `2013年前后走庚辰（龙·东南）运...`（PASS）

#### F-008 one_liner 术语残留

**根因**：`one_liner()` 和 `_reply_no_question()` 直接用五行英文名（`strong[0]` = "金"）拼标题，未走 `ELEMENT_WARM` 白话映射。

**修法**（3 处，同一文件）：
1. `one_liner()` 无提问分支：加 `_strong_label` / `_missing_label`，从 `ELEMENT_WARM` 取白话标签
2. `one_liner()` 有提问分支：`_strong_labels` 列表推导映射
3. `_reply_no_question()`：`missing` 列表推导 `_missing_labels` 映射

**实测**：
- 旧：`决断底子，金偏多`（"金"裸抛）
- 新：`决断底子，决断偏多`（PASS）
- 多元素全覆盖：木→生长、火→热度、土→厚稳、金→决断、水→柔软

#### 基线更新

`web/baselines/plain_first_fixture.json` case c8_love `one_liner`：
- 旧：`决断底子，金偏多`
- 新：`决断底子，决断偏多`

#### 闸门（.venv/Scripts/python）

| 闸门 | 结果 |
|------|------|
| check_plain_first | PASS 5用例 × 8判据 |
| check_warm_voice | PASS 10用例 × 8判据 |
| check_poster | PASS 判据12/13/14 |
| selftest163 | 失败（LLM 加载 transformers，非本次改动，R217b 引入的 ai_polish 依赖） |

#### 确定性验证

- `warm_bazi` 同输入两次输出一致 ✅
- `warm_taohua` 同输入两次输出一致 ✅
- `one_liner` 长度 ≤20 字 ✅

#### REG-001 selftest 基线未同步（R218a-巡5 复审回归）

**根因**：`taohua()` 在 `/api/taohua` 响应中新增 `birth_year` 字段（F-005 修复），但 `web/selftest.py` 的 `_expect_keys["/api/taohua"]` 未同步追加该键 → selftest shape 断言失败（实际 15 键 vs 期望 14 键）。

**修法**：`_expect_keys["/api/taohua"]` 集合中追加 `"birth_year"`。

**实测**：
- selftest.py: 163 checks PASS EXIT=0 ✅
- baseline_voice.py: PASS sha256 一致 ✅
- check_warm_voice.py: PASS 判据 1-8 ✅
- check_plain_first.py: PASS 5用例 × 8判据 ✅
- check_poster.py: PASS 判据 12/13/14 ✅

**API 端到端**（:8183 常驻服务 PID 10416 启动于 10:50，晚于代码修改）：
- `/api/taohua` 1990-05-15 女：`birth_year=1990`、warm 中无 "2003" ✅
- `/api/bazi` 1990-05-15 男：`one_liner="决断底子，决断偏多"`、无 "金偏多" ✅

**闸门**：selftest163 / baseline_voice / check_warm_voice / check_plain_first / check_poster 全 EXIT=0。

commit: 待提交
