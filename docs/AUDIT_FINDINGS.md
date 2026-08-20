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
- 状态：OPEN

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

## VERIFIED 归档

<!-- 复验通过的条目移到这里，保留完整原文 + 复验命令输出摘要 -->
