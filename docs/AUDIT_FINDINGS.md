# AUDIT FINDINGS — 审查轨缺陷清单

**所有权（宪法第五条）**：本文件由**审查轨独占写**。
优化轨只能做一件事：把自己已修的条目状态改成 `FIXED-R<n>b`，
或在条目下追加 `REJECTED-R<n>b` + 被违反的宪法条款。
**不得改写标题、复现命令、实测输出、严重级。**

复验纪律（宪法第一条 NON-NEGOTIABLE）：审查轨复验必须**自己重跑命令**，
绝不能凭优化轨的报告签字。本项目历史上多次口头结论被后来实测推翻。

---

## 严重级定义

| 级别 | 含义 | 是否卡阶段闸门 |
|---|---|---|
| `BLOCKER` | 功能完全不可用（点击报错、端点 500） | **是** |
| `MAJOR` | 契约错误、数据显示错误、修复引入的回归 | **是** |
| `MINOR` | 体验瑕疵、文案、边界情况 | 否 → `OPTIMIZE_BACKLOG.md` |
| `NIT` | 纯偏好 | 否 → `OPTIMIZE_BACKLOG.md` |

**只有 BLOCKER 和 MAJOR 写进本文件。** MINOR/NIT 一律进
`OPTIMIZE_BACKLOG.md`，禁止用来阻塞阶段推进。

## 状态流转

    OPEN ──修复轨修完──> FIXED-R<n>b ──审查轨重跑复验──> VERIFIED
                                          └──复现依旧──> REOPEN

## 条目格式（固定，不得简化）

```markdown
### R<n>a-<seq> 一句话标题
- 复现：<可直接执行的命令，或 probes/probe_x.py::用例名>
- 实测：<真实输出 / 报错原文，不是描述>
- 位置：<文件:行号>
- 期望：<可验证的期望行为>
- 严重级：BLOCKER | MAJOR | MINOR | NIT
- 状态：OPEN
```

---

## 待清偿（OPEN / FIXED 待复验）

以下 5 条为交接窗口实测移交（2026-08-19，非审查轨轮次，编号用 R000a 占位）。
审查轨接手后应自己重跑复现命令确认，再照常流转状态。

### R000a-01 除八字排盘外全部按钮点击即抛 TypeError
- 复现：`grep '\$\.[a-zA-Z_]' web/static/index.html`（49 处命中）
- 实测：`index.html` 定义 `function $(id)`，但 49 处写成 `$.rq.value`、
  `$.ly_year.value`、`$.hh_a_year.value` 等——把函数当对象访问属性，
  返回 `undefined`，随即 `undefined.value` 抛
  `TypeError: Cannot read properties of undefined (reading 'value')`
- 位置：`web/static/index.html` 1000-1002, 1027-1028, 1052-1057, 1081-1082,
  1127, 1139, 1151-1157, 1182-1184, 1214-1219, 1244-1248, 1270-1272, 1308-1317
- 期望：检索/深度研究/定位/比对/书目/研究线程/六爻/黄历/起名/桃花/塔罗/合婚
  全部按钮点击后正常发请求并渲染结果。（八字排盘用的是正确的 `$('#year')`
  写法，未受影响）
- 严重级：BLOCKER
- 状态：FIXED-R178b

### R000a-02 两书对照与概念研究按钮完全没有事件处理器
- 复现：`grep -n 'cwBtn\|conceptBtn' web/static/index.html`（各仅 1 处命中）
- 实测：`#cwBtn`、`#conceptBtn` 只在 HTML 里出现一次（按钮本身），
  JS 区无任何 `addEventListener`
- 位置：`web/static/index.html:688`（cwBtn）、`:699`（conceptBtn）
- 期望：点击后分别调用 `/api/compare_works`、`/api/concept` 并渲染
  （两端点实测均返回 200）
- 严重级：BLOCKER
- 状态：FIXED-R178b

### R000a-03 读书页九个标签页与三个子标签点击无反应
- 复现：`grep -n 'rtab\|rsec2' web/static/index.html`
- 实测：`.rtab` 有 18 处（全在 HTML），`data-rsec2` 3 处，
  但 JS 区无 `.rtab` 或 `rsec2` 的事件绑定；`#dailyMore` 同样只有 1 处
  （HTML）无处理器
- 位置：`web/static/index.html:550-558`（rtab）、`:668-670`（rsec2）、
  `:428`（dailyMore）
- 期望：点击标签切换对应 `.rsec` 面板；`#dailyMore` 有明确行为
- 严重级：BLOCKER
- 状态：FIXED-R178b

### R000a-04 三处响应字段名契约漂移导致结果区永远空白
- 复现：起服务后 `curl http://127.0.0.1:8123/api/history`
  与 `grep -n 'j.items\|j.llm_out\|j.addresses' web/static/index.html` 对照
- 实测：前端读 `j.llm_out` / `j.items` / `j.addresses`，
  后端实际返回 `llm` / `records` / `evidence`
- 位置：`web/static/index.html:987`（llm_out）、`:1367` `:1392`（items）、
  `:1034`（addresses）；后端 `web/app.py:299` `:307` `:500`
- 期望：字段名以真实响应为准，或后端显式改契约并同步自测断言
- 严重级：MAJOR
- 状态：FIXED-R178b

### R000a-05 排盘结果模板 `</strong>` 拼写损坏 + 研究线程请求体不匹配必然 422
- 复现：`sed -n '963p' web/static/index.html`；
  `curl -X POST http://127.0.0.1:8123/api/threads -H "Content-Type: application/json" -d '{"topic":"x"}'`
- 实测：963 行为
  `html += \`<li><strong>${esc(ik)}：</${esc(iv)}\`;`
  （`</strong>` 写成 `</` + 变量，标签结构损坏）；
  `/api/threads` 返回 422 `Field required: kind / claim / method`
  而前端只发 `{topic}`
- 位置：`web/static/index.html:963`、`:1139`；
  后端 `web/schemas.py` `ThreadRecordRequest`
- 期望：标签正确闭合；线程创建请求体符合 `ThreadRecordRequest`
- 严重级：MAJOR
- 状态：FIXED-R178b

---

## 已确认无缺陷（不要"修"没坏的东西）

交接窗口对全部端点发过真实 HTTP 请求，**25 个端点全部返回 200**：
`/api/health` `/api/works` `/api/search` `/api/addr` `/api/compare`
`/api/research` `/api/concept` `/api/compare_works` `/api/bookstudy/*`
`/api/bazi`（day/range/life/lunar）`/api/liuyao` `/api/huangli` `/api/qiming`
`/api/taohua` `/api/hehun` `/api/tarot` `/api/tarot/draw` `/api/history`
`/api/threads` `/api/daily` `/api/widget` `/api/user/prefs` `/api/favorites`

后端**功能**没坏。它的问题是**组织**：`web/app.py` 2108 行里 912 行是塞在
`__main__` 里的自测。那属于重构任务，不是缺陷。

---

## VERIFIED 归档

<!-- 复验通过的条目移到这里，保留完整原文 + 复验命令输出摘要 -->
