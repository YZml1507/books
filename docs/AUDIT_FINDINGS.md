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

### R118a 轮次新增（2026-08-19，审查轨首轮实测）

本轮新建两个前端闸门 probe，把移交的 5 条 R000a 全部**自己重跑复现**（宪法
第一条：不凭移交报告签字），并新发现 4 条移交清单里没有的缺陷。

两条复现命令（下方条目共用，`<py>` =
`C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books-audit
<py> probes\probe_ui_smoke.py     # 真起服务（--port 8199）+ 真点按钮，退出码 1
<py> probes\probe_contract.py     # 前端字段名 vs 真实响应，退出码 1
```

本轮实测汇总。完整输出落在 `logs/probe_ui_smoke_r118a.txt`、
`logs/probe_contract_r118a.txt`，失败截图 `logs/ui_smoke/FAIL_*.png`。
⚠ **`logs/` 被 gitignore**（`.gitignore:42`），所以修复轨 merge audit 后
**拿不到这些文件**——每条缺陷的关键实测原文已逐条抄进下方条目，
需要更多上下文时请自己重跑那两条命令（这本来也是宪法第一条的要求）。

    probe_ui_smoke: 32 个用例，PASS 4 / FAIL 28
    probe_contract: 21 个含 fetch 的 handler 块，118 个字段读取点，
                    HARD=10 TYPE=1 SOFT=15 SKIP=0

**本轮 OPEN 计数（阶段闸门第 1 条的可复验数字）**：
BLOCKER 4（R000a-01/02/03、R118a-04）+ MAJOR 5（R000a-04/05、
R118a-01/02/03）= **9 条 OPEN**，故 `CURRENT_PHASE` 保持 `REPAIR`。
点数命令（R118a 新建，`PHASE.md` 闸门 1 原写「人工点数」——人工点数不是
可复现命令，违反宪法第一条，故落成脚本）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books-audit
C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe scripts\count_open_findings.py
# 退出码 0 = 闸门 1 通过；1 = 仍有 OPEN 的 BLOCKER/MAJOR
```

本轮实测输出末行：`OPEN BLOCKER 4 / OPEN MAJOR 5 / 合计 9`，退出码 1。

（不要用裸 `Select-String '^- 状态：OPEN' | Measure-Object` —— 它会把本文件
「条目格式」示范块里的那行也数进去，实测得 10 而非 9。这类"数字差一"正是
宪法第一条要求每个数字都附可复验命令的原因。）

**对照：`web/app.py --selftest` 同时是 PASS (130 checks)、13 道闸门同时全绿。**
这正是本轮要补的覆盖缺口的实测证明——130 条后端断言对上述 28 个失败用例
零感知。

---

### R000a 移交条目（2026-08-19 交接窗口移交，R118a 已逐条自行复现）

以下 5 条为交接窗口实测移交（非审查轨轮次，编号用 R000a 占位）。
R118a 已自己重跑复现命令确认全部成立，并在每条下追加实测复现记录。

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
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke 用例 btn:search/liuyao/huangli/qiming/taohua/tarot/hehun/research/addr/compare/threads 全部 PASS，零 pageerror；probe_dollar_misuse 58 个函数名 0 处属性误用
- **R118a 自行复现（不凭移交报告签字）**：
  `<py> probes\probe_ui_smoke.py` 真浏览器点击，6 个按钮拿到**运行时原文**：

      [FAIL] btn:search:  25s 后仍停在占位文案: '检索中…'
             | pageerror: Cannot read properties of undefined (reading 'value')
      [FAIL] btn:liuyao:  25s 后仍停在占位文案: '摇卦中…'   | 同上 pageerror
      [FAIL] btn:huangli: 25s 后仍停在占位文案: '查询中…'   | 同上 pageerror
      [FAIL] btn:qiming:  25s 后仍停在占位文案: '起名中…'   | 同上 pageerror
      [FAIL] btn:taohua:  25s 后仍停在占位文案: '测算中…'   | 同上 pageerror
      [FAIL] btn:tarot:   25s 后仍停在占位文案: '抽牌中…'   | 同上 pageerror
      [FAIL] btn:hehun:   25s 后仍停在占位文案: '计算中…'   | 同上 pageerror

  **R119a 补测（解除级联遮挡后的完整清单）**：另 7 个按钮此前因 R000a-03
  标签不切换而**根本点不到**（playwright 报 not visible），其自身好坏无法测量。
  probe 增加「测试侧强制显示面板」（只操作 DOM class，**不改 web/**，标签用例
  仍照原样点击照原样判失败），实测拿到剩余按钮的真实结论：

      [FAIL] btn:research: 25s 后仍停在 '研究中…' | pageerror: …reading 'value'
      [FAIL] btn:addr:     25s 后仍停在 '定位中…' | pageerror: …reading 'value'
      [FAIL] btn:compare:  25s 后仍停在 '比对中…' | pageerror: …reading 'value'
      [FAIL] btn:threads:  .no-evidence 渲染: "创建失败：Cannot read
             properties of undefined (reading 'value')"
      [PASS] btn:works:    容器 1509 字符（书目卡片正常渲染 47 部书）

  即 `$.xxx` 误用实测影响 **11 个按钮**（search / research / addr / compare /
  threads / liuyao / huangli / qiming / taohua / tarot / hehun），
  比移交清单描述的范围更完整。
  **`#worksBtn` 是唯一不受影响的按钮**——它的 handler 不读任何输入框
  （`index.html:1100-1123` 直接 `fetch('/api/works')`），所以没有 `$.xxx`。
  这条对修复很有用：它证明缺陷成因**只是** `$.` 取值写法，handler 的
  fetch/渲染逻辑本身是好的。
  `btn:threads` 的失败文案还额外确证了 R000a-05 的后半：异常发生在
  `$.tq.value`（读输入框）阶段，**请求根本没发出**，所以那个必然 422 的
  请求体不匹配当前还被 TypeError 掩盖着——修完 `$.` 之后 422 才会露出来。
  计数与归属（R119a 新建静态闸门 `<py> probes\probe_dollar_misuse.py`，
  秒级、零依赖，修复轨改完可先跑它自查再跑完整冒烟）：

      $ 的定义：[(842, 'function $(id) {')]        ← 是函数，不是对象
      `$.xxx` 误用：49 行 / 61 处

      按归属（= 修复清单）：
         11 处  #addrBtn handler        4 处  #researchBtn handler
         10 处  #hhSubmit handler       4 处  #compareBtn handler
          7 处  #lySubmit handler       3 处  #hlSubmit handler
          6 处  #searchBtn handler      3 处  #trSubmit handler
          6 处  #qmSubmit handler       1 处  searchByWork()
          5 处  #thSubmit handler       1 处  #threadBtn handler

      完全不含 `$.` 的 handler（3/14）：
      #form handler, #worksBtn handler, #newsRefresh handler

  **两条独立证据交叉吻合**：静态扫描说只有 3 个 handler 干净，真浏览器冒烟
  也恰好只有这 3 个通过（`btn:bazi` 是 `#form`——它另有 R118a-01 的
  `[object Object]` 问题但不抛 TypeError；`btn:works`、`btn:news.refresh` 全绿）。
  静态与动态两侧独立得出同一结论，符合宪法第三条偏离 4「用独立见证，
  不用表面统计」。
  另注：`searchByWork()` 那 1 处（`:1127 $.rwork.value = workId`）是**书目卡片
  点击跳检索**的路径——它不在任何按钮的 handler 里，容易在逐个修按钮时漏掉。

### R000a-02 两书对照与概念研究按钮完全没有事件处理器
- 复现：`grep -n 'cwBtn\|conceptBtn' web/static/index.html`（各仅 1 处命中）
- 实测：`#cwBtn`、`#conceptBtn` 只在 HTML 里出现一次（按钮本身），
  JS 区无任何 `addEventListener`
- 位置：`web/static/index.html:688`（cwBtn）、`:699`（conceptBtn）
- 期望：点击后分别调用 `/api/compare_works`、`/api/concept` 并渲染
  （两端点实测均返回 200）
- 严重级：BLOCKER
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke btn:compare_works 容器 1217 字符、btn:concept 容器 1421 字符，均真发请求并渲染
- **R118a/R119a 自行复现**：解除 R000a-03 的级联遮挡后拿到运行时确证：

      [FAIL] btn:compare_works: 结果容器点击后仍为空；
             且点击后零 /api 请求（handler 在 fetch 之前就抛了）
      [FAIL] btn:concept:       结果容器点击后仍为空；
             且点击后零 /api 请求

  注意这两条与 `$.xxx` 那 11 个按钮的**失败特征不同**：它们
  **零 console 错误、零 pageerror、零 /api 请求、容器完全不变**——
  因为根本没有 handler 被调用。这正是「按钮没接线」与「按钮接线了但抛异常」
  的可区分判据，两类缺陷需要两种修法。
  静态确认：`#cwBtn` / `#conceptBtn` 各仅 1 处命中（按钮自身），
  JS 区零 `addEventListener`（`<py>` 逐行扫描确认）。

### R000a-03 读书页九个标签页与三个子标签点击无反应
- 复现：`grep -n 'rtab\|rsec2' web/static/index.html`
- 实测：`.rtab` 有 18 处（全在 HTML），`data-rsec2` 3 处，
  但 JS 区无 `.rtab` 或 `rsec2` 的事件绑定；`#dailyMore` 同样只有 1 处
  （HTML）无处理器
- 位置：`web/static/index.html:550-558`（rtab）、`:668-670`（rsec2）、
  `:428`（dailyMore）
- 期望：点击标签切换对应 `.rsec` 面板；`#dailyMore` 有明确行为
- 严重级：BLOCKER
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke 九个 tab 全部『面板可见』、三个 subtab 全部『子标签 active』、btn:dailyMore『点击后 DOM 有变化』
- **R118a 自行复现**：`probe_ui_smoke` 12 个用例实测原文：

      [FAIL] tab:rsec-research:  点击后 #rsec-research 仍不可见
      [FAIL] tab:rsec-addr:      点击后 #rsec-addr 仍不可见
      [FAIL] tab:rsec-compare:   点击后 #rsec-compare 仍不可见
      [FAIL] tab:rsec-works:     点击后 #rsec-works 仍不可见
      [FAIL] tab:rsec-threads:   点击后 #rsec-threads 仍不可见
      [FAIL] tab:rsec-cw:        点击后 #rsec-cw 仍不可见
      [FAIL] tab:rsec-concept:   点击后 #rsec-concept 仍不可见
      [FAIL] tab:rsec-bookstudy: 点击后 #rsec-bookstudy 仍不可见
      [FAIL] subtab:bs-structure/bs-chapter/bs-summary:
             TimeoutError: Page.click ... element is not visible
      [FAIL] btn:dailyMore: 点击后 DOM 无任何变化（无事件处理器）
      [PASS] tab:rsec-search: 面板可见   ← 唯一通过，因为它带死的 class="active"

  `rsec-search` 通过是**静态默认值**而非切换生效：`index.html:562` 写死
  `class="rsec active"`。这条是本缺陷影响面的确证——**九个标签里只有默认
  那个能看到内容**，另外八个面板的全部功能对用户完全不可达。
  子标签额外事实：`bs-structure` 已带 `class="rtab active"`，但三个子标签
  连同 `#bsStructure`/`#bsChapter`/`#bsSummary` 三个容器都无任何 JS 填充逻辑
  （`grep -n 'bsStructure\|bsChapter\|bsSummary' web/static/index.html`
  仅命中 HTML 定义），即读书页三个子功能整体未接线。

### R000a-04 三处响应字段名契约漂移导致结果区永远空白
- 复现：起服务后 `curl http://127.0.0.1:8123/api/history`
  与 `grep -n 'j.items\|j.llm_out\|j.addresses' web/static/index.html` 对照
- 实测：前端读 `j.llm_out` / `j.items` / `j.addresses`，
  后端实际返回 `llm` / `records` / `evidence`
- 位置：`web/static/index.html:987`（llm_out）、`:1367` `:1392`（items）、
  `:1034`（addresses）；后端 `web/app.py:299` `:307` `:500`
- 期望：字段名以真实响应为准，或后端显式改契约并同步自测断言
- 严重级：MAJOR
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_contract 191 个字段读取点 HARD=0 TYPE=0 SKIP=0；前端已改读 interpretation / records / evidence
- **R118a 自行复现**：`<py> probes\probe_contract.py` 用真实响应逐字段比对，
  三处全部确证，且**位置比移交清单更精确**：

      index.html:987   /api/bazi      读 j.llm_out   （真实响应键为 llm）
      index.html:1034  /api/research  读 j.addresses （真实响应键为 evidence）
      index.html:1035  /api/research  读 j.addresses
      index.html:1367  /api/history   读 j.items     （真实响应键为 records）
      index.html:1369  /api/history   读 j.items
      index.html:1374  /api/history   读 j.items.id
      index.html:1375  /api/history   读 j.items.id
      index.html:1392  /api/history   读 j.items
      index.html:1395  /api/history   读 j.items

  真实响应键（TestClient 实测）：
  `/api/bazi` → `['calc','evidence','llm','paipan']`；
  `/api/research` → `['comparisons','evidence','flagged','question','reason',
  'refused','steps']`；`/api/history` → `['records']`。
  影响面确证：`j.items` 缺失使**历史记录与"最近解读"两个列表永久走空分支**，
  `loadHistory()` / `loadRecent()` 首屏即调用，所以这条不需要点任何按钮就已生效。

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
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke dom:bazi.strong-nesting 实测 <strong> 嵌套层数=0、注释节点=0；btn:threads 容器 96 字符『线程已创建』
- **R118a 自行复现**：两半都确证，且拿到了移交清单没有的**浏览器实际解析后果**。
  行号修正：损坏模板在 **963 行**（移交清单写 963 正确；注意用
  `Get-Content` 读该文件会因解码错位报成别的行，以 Python/read 工具为准）。

  DOM 事实（`probe_ui_smoke` 用例 `dom:bazi.strong-nesting`）：

      [FAIL] dom:bazi.strong-nesting:
             #result 内 <strong> 最大嵌套层数=3（应 ≤1）、注释节点=32（应 =0）

  浏览器把 `</${esc(iv)}` 解析成**注释**，`<strong>` 永不闭合，逐条累积嵌套。
  实测渲染出的 HTML 原文（chromium innerHTML）：

      <li><strong>pos：<!--年干<span class="basis"--> [庚庚同为金，同阴阳]</strong></li>
      <li><strong><strong>gan：<!--庚<span class="basis"--> …</strong></strong></li>
      <li><strong><strong><strong>god：<!--比肩<span class="basis"--> …</strong>…

  后果不止是样式：`item.basis` 的真实值（年干/庚/比肩）被吞进注释**从页面上
  消失了**，而注释里吞掉的正是 `<span class="basis">` 出处标注——属数据丢失，
  不是排版瑕疵。
  线程 422 一半：`probe_contract` fixture 实测 `POST /api/threads {"topic":"x"}`
  → 422 `Field required: kind / claim / method`，与移交记录一致。

---

### R118a-01 排盘结果把 five_elements / day_luck 渲染成 `[object Object]`
- 复现：`<py> probes\probe_ui_smoke.py`（用例 `btn:bazi`）；
  或 `<py> probes\probe_contract.py`（TYPE 段）
- 实测：真浏览器点「排 盘 推 算」后 `#result` 容器文本原文：

      basis： [巳藏丙庚戊，主气丙：丙克庚（火克金），同阴阳]
      five_elements

      [object Object]

      relations
      day_luck

      [object Object]

      scope
      day

  成因（`index.html:954-975`）：`for (const [k,v] of Object.entries(j.calc))`
  只分 `Array.isArray(v)` 与 `else → esc(v)` 两支，漏了 **v 是 object** 的情形。
  `/api/bazi` 实测 `calc` 键为
  `['day_luck','five_elements','relations','scope','summary','ten_gods']`，
  其中 `five_elements` 与 `day_luck` 都是 dict。JS `String({..})` 恒等于
  `"[object Object]"`。
- 位置：`web/static/index.html:972-974`（`else { html += esc(v) }` 分支）；
  真实数据形状见 `web/app.py:240`（`bazi_calc` 返回值）
- 期望：object 值按键展开渲染（如五行分布逐项显示），页面任何位置不得出现
  `[object Object]` 字面量；`probe_ui_smoke` 的 `btn:bazi` 用例转 PASS
- 严重级：MAJOR
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke btn:bazi 容器 31893 字符，无 [object Object]；probe_contract TYPE=0
### R118a-02 黄历「彭祖百忌」渲染成 `[object Object]`
- 复现：`<py> probes\probe_contract.py`（TYPE 段单条）
- 实测：

      index.html:1195  /api/huangli  读 j.pengzu
        实测值类型=dict 渲染为 [object Object]
        {"gan": "乙", "zhi": "丑", "gan_text": "乙不栽植，千株不长",
         "zhi_text": "丑不冠带，主不还乡"}

  前端把整个 dict 塞进 `esc(j.pengzu)` 输出到 pill 里。
- 位置：`web/static/index.html:1195`；后端 `web/app.py:891`
- 期望：渲染 `gan_text` / `zhi_text` 两句忌语（这是彭祖百忌的实际内容），
  不得出现 `[object Object]`
- 严重级：MAJOR
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke btn:huangli 实测渲染『彭祖百忌 乙：乙不栽植，千株不长 / 丑：丑不冠带，主不还乡』，非 [object Object]
### R118a-03 排盘「古籍依据」出处永久为空（引用与生成分离被静默破坏）
- 复现：`<py> probes\probe_contract.py`（HARD 段第 1 条）
- 实测：

      index.html:983  /api/bazi  读 j.evidence.citation
        ⚠ 出处字段缺失（宪法第三条）：|| 兜底把出处静默渲染成空串

  `/api/bazi` 的 evidence 元素实测键为
  `['file','layer','page_anchor','query','score','text','title','why','work_id']`
  —— **没有 `citation`**。成因：该路径走 `retrieve_fast()`，不经
  `_hit_dict()`（`web/app.py:345`，只有它才调 `h.citation()`）。
  前端写 `esc(ev.citation||'')`，所以页面不报错、`<div class="ev-meta">`
  渲染成空 div，古籍原文照常显示——**原文有了，出处没了**。
- 位置：`web/static/index.html:983`；后端 `web/app.py:245`
  （`retrieve_fast` 结果直接进 `evidence` 字段）
- 期望：evidence 每条带可核验出处串（与 `_hit_dict` 的 `citation` 同源），
  页面 `.ev-meta` 非空。宪法第三条「引用与生成分离」要求原文必带出处，
  `||''` 兜底不构成合规
- 严重级：MAJOR
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_contract 出处字段 citation 不再缺失（HARD=0）；probe_no_generated_in_corpus 阳性对照 6/6 引文可在语料中定位
### R118a-04 `#dailyMore`「查看完整解读」点击后 DOM 零变化
- 复现：`<py> probes\probe_ui_smoke.py`（用例 `btn:dailyMore`）
- 实测：`[FAIL] btn:dailyMore: 点击后 DOM 无任何变化（无事件处理器）`；
  静态确认 `dailyMore` 全文件仅 1 处命中（`:428` 按钮自身），JS 区零绑定
- 位置：`web/static/index.html:428`
- 期望：点击后有明确行为（跳排盘视图或展开完整运势），DOM 可观测变化
- 严重级：BLOCKER（按本文件定义：点了完全无反应＝功能完全不可用）
- 状态：VERIFIED-R120a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：probe_ui_smoke btn:dailyMore『点击后 DOM 有变化』

---

### R128a-01 同一批古籍原文被渲染两次，21,153 字全文与 2,640 字截断版同时上屏
- 复现：`<py> probes\probe_first_screen.py`（报 `.ev-item` 24 个而 API 只返回 12 段）；
  或直接比对两个字段：

      <py> -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'src')
      from fastapi.testclient import TestClient
      from web.app import app
      j = TestClient(app).post('/api/bazi', json={'year':1998,'month':7,
          'day':20,'hour':14,'gender':'女','question':'感情运怎么样？'}).json()
      ev, ct = j['evidence'], j['warm']['citations']
      print(len(ev), len(ct))
      print(sum(len(e['text']) for e in ev), sum(len(x['text']) for x in ct))"

- 实测：

      API evidence 12 段、总 21,153 字（未截断全文）
      API warm.citations 12 段、总 2,640 字（已截断版）
      逐条比对：**12/12 条目完全相同**，citations 独有 0、evidence 独有 0
      页面 .ev-item 元素数 **24**、.ev-text **24**

  即后端**已经做对了截断**（`warm.citations` 只有 2,640 字），前端却把全文版与
  截断版**同时**渲染。同一段《穷通宝鉴·论庚金》《五行大义·论合》在页面上各出现两次。
- 位置：`web/static/app.js:610`（渲染 `j.evidence` 全文）
  与 `:302-307`（渲染 `warm.citations` 截断版），两处并存
- 期望：warm 模式下同一段古籍**只渲染一次**（`specs/005` 判据 5）。
  用截断版还是全文版由优化轨定，但不得两者都渲染。
  ⚠ 折叠/去重**不得删除内容**：页面 `textContent` 中必须仍能取到每段原文与出处
  （宪法第三条，`specs/005` 判据 6/7/8）。
- 严重级：MAJOR（数据显示错误：同一内容重复上屏，且是当前 124 屏版面的主要成因）
- 状态：VERIFIED-R131a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：
  `<py> probes\probe_first_screen.py` → **退出码 0，八条判据全绿**：
  一句话相对视口 **353px**（原 71,094px）、结果区 **4 屏**（原 102 屏）、
  最长可见块 **71 字**（原 4,123）、古籍默认可见 **0%**（原 92%）、
  **折叠 vs 删除：定位 12 段 ≥ API 12 段（12 段折叠、0 段可见）**——
  即 24 段重复渲染已消除，且原文都还在 DOM 里（是折叠不是删除）。
  可核验性 12/12 原文与出处均可取。
  专业模式未受牵连：`web\baseline_voice.py` 逐字节一致（sha256 `b0461df2…`），
  `specs/004` 判据 9 保持成立。
  （R190b 注：`b0461df2…` 是**当时**的正确值，此处不改写历史记录。该基线已在
  R189b 因 R131a-01 修复合法重冻为 `97f0681e…`；现值复验命令与理由见
  `specs/006-llm-polish/tasks.md` §M3 判据 5。）

---

### R131a-01 提问对检索零影响——问感情与问事业拿到完全相同的 12 段引文
- 复现（审查轨实测，7 个提问变体 × 同一生日）：

      <py> -c "import sys, json; sys.path.insert(0,'.'); sys.path.insert(0,'src')
      from fastapi.testclient import TestClient
      from web.app import app
      c = TestClient(app)
      B = {'year':1998,'month':7,'day':20,'hour':14,'gender':'女'}
      sigs = {}
      for q in [None,'','感情运怎么样？','事业运如何？','今年财运好不好？',
                '健康要注意什么？','适合考研还是工作？']:
          body = dict(B)
          if q is not None: body['question'] = q
          ev = c.post('/api/bazi', json=body).json()['evidence']
          sig = json.dumps([(e['work_id'], e['text'][:24], e['why']) for e in ev],
                           ensure_ascii=False)
          sigs.setdefault(sig, []).append(repr(q))
      print('不同引文集合数:', len(sigs))"
      # 记得清理 history（每次调用写一条）

- 实测：

      7 个提问变体（含「无 question 字段」与「空串」）
      → 引文集合**只有 1 种**，12 段逐字节相同
      why 字段取值域 = ['年柱', '日柱', '月柱']  ← 盘位，不是与提问的相关性
      retrieve_fast 签名 = (b, per_query=2, per_work=1, top_queries=3)
      → **根本不接受 question 参数**

  对照：`warm.one_liner` 确实随提问变化（'感情这块…' / '事业这块…' /
  '财运这块，盘里信息偏少'），但那是**文案模板在响应提问**，检索层从未看见提问。
- 位置：`web/services.py:159` 调用 `retrieve_fast(b, per_query=2, per_work=1)`
  ——只传盘，不传 `question`；`src/guji/bazi_lookup.py` 的 `retrieve_fast`
  签名无 question 参数
- 期望：用户问什么，证据应与之相关。宪法第三条架构图的 Agent 层是
  「**检索即推理**：判型→选书→读→扩展→验证」，当前退化为「按盘取书」——
  这也解释了 R128a 实测为何会带出「遁甲演義」`王璋曰乙竒臨乾驚門…`、
  「太乙金鏡式經」这类与八字提问弱关联的内容（`specs/005` US5 已预留此条）。
  ⚠ **改检索会移动 eval_g1/eval_g7 的门柱**，须单独一轮并附前后对照，
  不得为了让相关性变好而放宽那两个闸门（红线第 2 项）。
- 严重级：MAJOR（契约错误：`question` 是 API 入参且前端在收集它，
  但对证据选取无任何作用——用户合理预期它有作用）
- 状态：VERIFIED-R132a（新审查轨四条前置命令全部复现，见下方 R132a 复验记录）

**R190b 补记——修复方声明 + 第三方独立复验（此段由 R190b 追加，不改写上方原始条目）**

R189b（优化轨）声称已修：`src/guji/bazi_lookup.py` 新增写死映射 `TOPIC_QUERIES`
与 `topic_queries()` 纯函数，`retrieve_fast()` 增可选 `question` 参数，主题词
追加在坐标词队尾（`why="提问主题"`）；`web/services.py` 传入 `req.question`。

**R190b 不采信上述声明，另建独立闸门自行复验**（宪法第一条：跑不出来就当它
不存在）。新建 `probes/probe_r131a_relevance.py`，三条判据 + 阳性对照：

    <py> probes\probe_r131a_relevance.py              # 退出码 0
    判据 A 引文分化：5 个提问 → 5 种引文集合　阈值 = 5　PASS
        b4d2da221006 ← 感情运　ac3249de14e4 ← 事业运　cc5ad0da4d17 ← 学业运
        a44ddcb39299 ← 财运　  e1c2c97b48a4 ← 健康
    判据 B 无提问不变：topic_queries(None)=[]　两次调用 sha 相等=True　PASS
    判据 C 主题词生效：why 含「提问主题」= 2/12 段
                       why 取值域=['年柱','提问主题','日柱','月柱']　PASS

    <py> probes\probe_r131a_relevance.py --self-check  # 退出码 0
    把 topic_queries 打桩成恒返回 [] 后：判据 A 5→1 种集合 FAIL、判据 C 0/12
    FAIL —— 阳性对照被抓到，本探针不是「永远返回 0 的假闸门」（U-08 教训）

**门柱未移动实测**（红线第 2 项）：`<py> scripts\eval_g1.py` → 退出码 0，
`G1 = PASS 246/248 (99.2%)`，八个子项逐项 100%/96.4% 与 R189b 前记录一致；
`<py> scripts\eval_g7.py` → 退出码 0，`must_refuse 30/30`、`must_answer 25/25`、
`impossible 4/4`、`FABRICATIONS 0`。两脚本本轮零改动（`git diff` 空）。

**为什么状态是 FIXED 而不是 VERIFIED**：宪法第一条「修复方不得自己宣布完工」。
R190b 这一轮同时在改代码与文档，属修复方，无权自签 VERIFIED。转 VERIFIED 的
条件写在此：新审查轨自己重跑上面两条 probe 命令 + eval_g1/g7，四条都复现，
才可改本行为 `VERIFIED-R<n>a`；任一不复现则 REOPEN 并附反证命令。

---

**R190b 补记——R128a-01 的签字对象已变，重钉常驻闸门（不改写上方 audit 的复验记录）**

audit 侧 R131a 在 `2cbb1f8` 上签了 `VERIFIED-R131a`。但此后 main 又落了
R187b/R188b/R189b 三轮，其中 `web/static/app.js` 变动 +222 行（含 `drawPoster`、
`renderAiPolish`、三级折叠树数据源由 citations 改 evidence）。**签字对象已经不是
被签的那份代码**，故本轮不沿用旧结论，另建常驻闸门重新钉住：

    <py> probes\probe_r128a_no_dup_citations.py               # 退出码 0
    浏览器实际请求体：{...,"gender":"女",...,"question":"感情运怎么样？"}
    判据 A 不重复渲染：DOM 引文容器 12 个（.ev-text 0 + .cite-body 12）
                       vs API 12 段　PASS
    判据 B 折叠≠删除：抽查 6 段原文缺 0、出处缺 0　PASS

    <py> probes\probe_r128a_no_dup_citations.py --self-check   # 退出码 0
    克隆一份 .cite-body 注入 DOM 后：判据 A 12→24 个 FAIL —— 阳性对照被抓到

结论：R128a-01 在当前 HEAD 上仍然成立地「已修好」——`.ev-text` 归零，古籍
只经三级折叠树渲染一次，与 API 段数 1:1。旧的全文渲染点（`app.js:610` 渲染
`j.evidence`）已不存在于 warm 路径。

**本轮踩的坑（写进条目防后人再犯）**：首版探针把提问框写成 `#q`（真实 id 是
`question`）、没设 `<select id="gender">`（默认「男」），于是浏览器那次请求与
探针自己发的 API 调用参数不同，evidence 集合随之不同，判据 B 假报「2 段原文
缺失」。**险情**：这个假 FAIL 长得非常像「折叠变成了删除」（宪法第三条红线）。
正确做法已落进探针：拦截浏览器实际发出的 request body、用同一份参数重放，
再比对；文本比对前统一去空白（DOM textContent 的空白与 API 原文不同）。
教训同族于 D-145a（探针不得把内部命名钉成契约）与 L-09（测试脚本自己错了）。

---

### R124a-01 温柔模式下结果区仍原样打印内部字段名 ten_gods / five_elements / day_luck / relations
- 复现：真浏览器默认（warm）模式点「排 盘 推 算」，读 `#result` 文本；
  或 `<py> probes\probe_ui_smoke.py` 后看 `logs/probe_ui_smoke_r124a.txt`
  的 `btn:bazi` 用例（该用例仍 PASS——它不检查内部字段名，见下方「探针盲区」）
- 实测：默认模式（首次打开 `localStorage.voiceMode` 为 `null` → 走 warm 分支）
  `#result` 共 32514 字符，首 260 字即含裸键名：

      纳音：路旁土 · 白蜡金 · 白蜡金 · 白蜡金
      ten_gods
      pos：年干　gan：庚　god：比肩 [庚庚同为金，同阴阳]
      …
      five_elements
      counts：木 0.3、火 1.9、土 1.1、金 4.6、水 0.1
      missing：—　strong：金
      relations
      day_luck
      day_ganzhi：丙寅

  四个内部键名（`ten_gods` / `five_elements` / `day_luck` / `relations`）
  与多个子键（`pos`/`gan`/`god`、`counts`/`missing`/`strong`、
  `day_ganzhi`/`day_master_rel`）全部原样上屏。
- 位置：`web/static/app.js:364`（`renderCalc` 用 `esc(k)` 把 dict 键当标题）；
  调用点 `:485`（daily）、`:556`（bazi）、`:1384`（history detail）
- 成因（已定位到行，不是猜）：`renderVoice`（`:289`）本身正确，warm 分支也
  确实接线了（`:562`）；但 `:556` 的 `renderCalc(j.calc)` 在它**之前**
  无条件执行，**两种模式都会打印**。即 warm 视图做对了，
  旧的 calc 网格没跟着收进折叠层。
- 期望：`specs/003` 判据 14「结果区暴露内部字段名 → 无」。
  warm 模式下不出现任何内部键名。
  ⚠ **专业模式不要求改动**——`specs/004` 判据 9 要求它逐字节不变。
  这是两条判据的交叉点，修的时候只动 warm 分支。
- 严重级：MAJOR（数据显示错误：用户看到的是程序变量名，不是人话）
- 状态：VERIFIED-R127a
- 复验（审查轨自己重跑，非凭优化轨报告签字）：
  `probes\probe_ui_smoke.py` → **37 用例 PASS 37 / FAIL 0** 退出码 0。
  `btn:bazi` 容器实测首 260 字已无任何内部键名，改为
  `🔮 排盘结果 … 纳音：路旁土 · 白蜡金 … 📜 古籍依据 命理探原 @? …`；
  `INTERNAL_KEYS` 18 个键名（含 `ten_gods` / `five_elements` / `day_luck` /
  `relations` / `day_ganzhi` / `day_master_rel`）**零命中**。
  同时 `web\baseline_voice.py` 14 用例逐字节一致（sha256 `b0461df2…`），
  说明专业模式未被牵连改动，`specs/004` 判据 9 保持成立。

**本条暴露的探针盲区（审查轨自己的问题，已记 D-149a）**：
`probe_ui_smoke` 的 `btn:bazi` 用例只检查「容器非空 + 无 `[object Object]`
+ 无失败文案」，**不检查内部字段名**，所以 36/36 全绿却漏了这条。
下一轮把「结果区不得出现内部键名」加成 smoke 的断言。

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

**R118a 补充确认（自己重跑，不凭移交结论）**：

- `web/app.py --selftest` = **PASS (130 checks)**，退出码 0。命令：
  `cd books-audit; <py> web\app.py --selftest`
  （移交文档写"912 行自测"，本轮实测断言数为 130 条、`__main__` 块
  1365→2277 行 = 913 行。数字以本命令输出为准。）
- 宪法第四条 13 道闸门**全部 PASS**，退出码全 0。实测摘要见
  `docs/TASK_LEDGER.md` §109 R118a。
- 本轮 `probe_contract` 对 21 个 handler 块的 118 个字段读取点做了全量比对，
  除上方列出的 10 HARD + 1 TYPE 外，其余读取点在真实响应中均存在——
  即**前端契约漂移是局部的，不是系统性的**，不需要重写前端。
- 唯一"probe 自身无法判定"的情形（SKIP）本轮为 **0**：所有列表型响应都被
  fixture 喂成了非空。这条重要——SKIP 不为 0 时本 probe 会返回退出码 2 而
  不是假装通过。

---

## R132a（2026-08-22，审查轨首轮全量复验 + 四项职权清偿）

**背景**：双轨已对账同步（`git rev-list --count main..audit` / `audit..main` 均 0，
HEAD=ab9b017）。本轮 = 审 D-250b 越界 + 亲验 R190b 新建 4 闸门 + 复现 R131a-01
四条前置 + 抽查文档-实况对账 + 清偿移交清单四项。

### R132a-00 对 D-250b 越界的复核结论：约束守住，越界本身追认

逐条核实（命令可复现）：

    git show bfdc58d --stat                       # 改动范围与声明一致，无暗改
    git show bfdc58d -- docs/AUDIT_FINDINGS.md | grep "^-"
      # 删除行仅一处："- 状态：OPEN"（R118a-03 → FIXED-R189b 的合法流转）
    git diff bfdc58d^ bfdc58d -w -- specs/005-plain-first/tasks.md
      # -w 下实质改动 2 行，均为带「R190b 订正」标注的 sha256 订正注；
      # 裸 diff 的 362 行是行尾符重写噪音，非内容改写
    grep -n CURRENT_PHASE docs/PHASE.md           # 第 3 行仍 OPTIMIZE，未动

PHASE.md 的 REPAIR 矛盾订正、specs/005/006 的 sha256 订正注、AUDIT_FINDINGS 的
两段补记——全部带显式标注、保留原文备查。**追认本次越界**；但注意：这是
「审查轨无人在跑」这一条件下的例外通道，不构成惯例，下次优先等审查轨或
在台账挂起。

### R132a-01 R190b 新建 4 闸门亲验：全部为真闸门

主用例 + `--self-check` 各跑一遍（BOOKS_LLM_DISABLE=1），并读源码确认阳性对照
真实注入坏情况（U-08 防假闸门检查）：

| 探针 | 主用例 | self-check | 被抓明细 |
|---|---|---|---|
| probe_r131a_relevance | 0 | 0 | 判据 A 5→1 种集合 FAIL、判据 C 0/12 FAIL |
| probe_r128a_no_dup_citations | 0 | 0 | DOM 容器 12→24 vs API 12 FAIL |
| web/check_poster | 0 | 0 | 尺寸 1080→800、水印被抹 → 判据 12 FAIL |
| probe_llm_polish | 0 | 0 | _sanitize 失效后《穷通宝鉴》漏出被抓 |

打桩有效性核验：r131a 的 stub 打在 `guji.bazi_lookup.topic_queries` 模块属性上，
`retrieve_fast()` 内部以模块全局名调用（src/guji/bazi_lookup.py:145），stub 生效。

### R132a-02 R131a-01 转 VERIFIED（四条前置全部复现）

    <py> probes\probe_r131a_relevance.py              # 0（5 提问→5 集合、B/C PASS）
    <py> probes\probe_r131a_relevance.py --self-check # 0（阳性对照被抓）
    <py> scripts\eval_g1.py   # 0，G1 = PASS 246/248 (99.2%)——门柱未移
    <py> scripts\eval_g7.py   # 0，30/30·25/25·4/4·FABRICATIONS 0——门柱未移

另 `<py> web\baseline_voice.py` → 0（14 用例逐字节一致，sha256 97f0681e…）。
基线重冻审计（宪法第三条）：diff eefd28e^..eefd28e 基线文件，155 个叶子变更
**全部落在 3 个带提问用例**（day.q_career/day.q_love/male.day——male.day 实带
「财运怎么样？」），7 个无提问用例逐字节 SAME；14 个「有 text 无出处」节点新旧
同构（interpretation 正文串本身，非本次重冻造成）→ 出处零丢失，重冻合法。

### R132a-03 文档-实况对账抽查：R190b 五处声明全部属实

1. specs/004 tasks M2/M3：T2.1/T2.2/T3.1 重跑输出与状态列一致（xingzuo
   self-test PASS、check_xingzuo 判据 10/12 锚点达标、PNG 249,688 字节/
   1080×1440）；T3.3 仍 TODO 未虚报。
2. PHASE.md 闸门 2 命令：`grep -c sys.argv web/app.py` = 0（旧命令确实失效），
   `web/selftest.py` 退出码 0。订正属实。
3. sha256 五处订正注：见 R132a-02 重冻审计。
4. specs/006 T1.5/T2.3 如实留 TODO：`grep -c ai_polish web/selftest.py
   probes/probe_ui_smoke.py` 当时均 0。本轮已清偿（见 R132a-04）。

### R132a-04 移交清单四项清偿（审查轨职权内）

> 领土说明（宪法第五条，主动声明）：`web/selftest.py` 与 `specs/006/tasks.md`
> 严格说是优化轨文件，但开机指令第四件事 a) 把 T1.5 明确列为审查轨移交任务、
> T2.3 同单；状态列更新沿用 R190b 已被追认的惯例（完成方附命令改状态）。
> 特此声明，优化轨可复核。

a) **T1.5 selftest 补 ai_polish 三条断言**：key_present（四端点恒带键）/
   disabled_none（总开关下 polish() 返回 None 不抛）/ additive（四端点顶层键
   集合钉死 = LLM 前形状 + ai_polish 一个键，D-228b 先例）。149→152 checks 全绿；
   `probes/selftest_baseline.json` 同步 150→153；probe_selftest_regress PASS。
   写 history 的断言块自带清理（L-22 惯例）。
b) **T2.3 probe_ui_smoke 补两条 AI 区块行为用例**（D-145a 只断行为）：
   ai.block.renders_with_ai（LLM 可用时 .ai-polish 出现且标注「AI 生成」「仅供
   娱乐」常显）/ ai.block.separate_from_citations（AI 容器与 .cite-body 互不
   嵌套、类名零复用）。为离线可复现，probe 内置 stdlib mock OpenAI 兼容端点，
   经 BOOKS_LLM_BASE_URL 注入被测子进程（零外网、零新依赖）；mock 起不来时
   两用例如实转 SKIP。
c) **B-018 news.refresh 两层拆分**：见 OPTIMIZE_BACKLOG B-018 处置记录。
d) **B-013 check_poster 补长任务判据**：见 OPTIMIZE_BACKLOG B-013 处置记录。

### R132a-F1 子进程式探针硬编码 ROOT/.venv，audit worktree 下必然 FileNotFoundError（MAJOR→本轮已修，VERIFIED-R132a）

- 级别：MAJOR（审查轨的验收闸门在审查轨目录跑不起来——「闸门只在自己的
  目录有效」等于半残）
- 复现（修复前）：

      cd books-audit && BOOKS_LLM_DISABLE=1 <py> probes\probe_r128a_no_dup_citations.py
      # FileNotFoundError: [WinError 2]（PY = ROOT\.venv\Scripts\python.exe，
      # 而 audit worktree 无自己的 .venv——解释器借主 worktree）

- 波及：probe_r128a_no_dup_citations.py、web/check_poster.py、
  probe_llm_polish.py（三者的 PY 常量）
- 修复（审查轨领土内：probes/** 与 web/check_*.py 本就归我，直接修而非移交）：
  三处子进程一律改 `PY = sys.executable`；另给 books-audit 建 `.venv`
  directory junction 指向主 worktree 作环境兜底（`.venv/` 已 gitignored）
- 验证：三个探针在 audit worktree 下全部退出码 0（r128a 主+self、
  poster 主+self、llm_polish 主+self 共 8 条命令实测）
- 状态：VERIFIED-R132a

### R132a-F2 Windows 系统代理吞掉发往 127.0.0.1 的 httpx 请求（MINOR，登记 backlog）

- 复现（注册表 ProxyEnable=1、ProxyServer=127.0.0.1:7897 的机器上）：

      reg query "HKCU\...\Internet Settings" /v ProxyEnable   # = 0x1
      <py> -c "import httpx; print(httpx.post('http://127.0.0.1:<port>/v1/chat/completions', ...).status_code)"
      # → 502（请求根本没到本机 mock 服务；server 收到 0 个请求）
      # 设 NO_PROXY=127.0.0.1,localhost 后同一请求 → 200，polish() 正常出文

  根因：httpx trust_env 拾取 **Windows 注册表代理**（bash 里 HTTP_PROXY 等
  环境变量均为空），且不尊重 IE 的 ProxyOverride（其中明明有 127.*）
- **严重级订正（R132a 自纠）**：初判 MAJOR，实证后降 MINOR——真实用户的
  LLM 目标是远程 apihub，实测系统代理开着时 `https://apihub.agnes-ai.com` →
  401（可达未授权，正常路径），HN 同测 200。被代理吞掉的只有 **localhost
  目标**：影响面 = 本地 mock / 未来本地模型场景 + 本 probe 的注入链路，
  不影响线上用户。产品层加固仍值得做（llm_polish 对 localhost 豁免代理或
  trust_env=False），但不是用户当下在流血的洞
- 本轮处置：probe_ui_smoke 注入 env 显式加 NO_PROXY=127.0.0.1,localhost
  （只影响被测子进程），mock 链路稳定；登记 OPTIMIZE_BACKLOG B-020
- 状态：OPEN → B-020

### R132a-F3 probe_r131a_relevance 主用例写 history.db 不自带清理（MINOR）

- 级别：MINOR（进 backlog 不阻塞）
- 复现：跑一次主用例后 `data/history.db` 多出 8 条「感情运怎么样？」记录，
  探针内无 delete_record 清理逻辑——违反全仓探针的 L-22 惯例
- 附带事实：R132a 本轮复验电池因此留下残留，已手工按指纹精确清除
  （19 行：id 2124–2132、2145–2147、2167–2172、2185，删除前后行数核对）
- 处置：登记 OPTIMIZE_BACKLOG B-019，修法照抄 probe_ui_smoke.py:518 的
  baseline+delete+复验三段式
- 状态：OPEN → B-019

### R132a 闸门结论（措辞遵守 D-250b 后的新口径）

13 道宪法闸门退出码全 0；附加闸门（count_open_findings/selftest/probe_contract/
probe_dollar/baseline_voice/check_warm_voice/check_plain_first/check_xingzuo/
no_generated_in_corpus/selftest_regress/probe_first_screen）全 0；
新建 4 闸门主用例+--self-check 共 8 条全 0。**probe_ui_smoke 40/40 全 PASS、
退出码 0（B-018 修复后首次真全绿）**。日志 $LOCALAPPDATA/Temp/gates_r132a/。

---

## VERIFIED 归档

<!-- 复验通过的条目移到这里，保留完整原文 + 复验命令输出摘要 -->
