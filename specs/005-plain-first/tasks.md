# 任务清单：005-plain-first（优化轨执行文档）

状态列：`TODO` / `DOING` / `DONE(命令)` / `BLOCKED(原因)`。
宪法第一条：**没有命令的 DONE 等于没做。** 完成即改状态并附实测输出摘要。
`<py>` = `.\.venv\Scripts\python.exe`。

**唯一验收命令**：`<py> probes\probe_first_screen.py` 退出码 0 即达标。
每个里程碑收尾都要跑它并附退出码。

**领土纪律（宪法第五条）**：本轨只写 `src/guji/**`、`web/**`。
`probes/` 与 `scripts/` 一字不改；需要对方改的写进 M0 的移交清单。

**设计已实测选定**（依据见 `plan.md` §1/§3，不在实施阶段重新讨论）：
古籍区用 **V6 按书两级折叠**（44px 组头 + `hidden` 正文），
白话内容**一段都不折**；`styles.css` 必须加 `[hidden]{display:none!important}`。

---

## M0 交接与自证（不改任何产品代码）

- [ ] T0.1 移交审查轨（台账 §121）：判据 1 量的是**文档绝对 y**，
  而 `#result` 的绝对 y 实测 **3,005px**（`.brand` 55 + `#dailyCard` 577 +
  `#funcGrid` 618 + 两个 `.recent-section` 467/133 + `h2` 43 + `#form` 888）。
  附我方处置（提交后 `focusResult` 上浮，实测 3,005 → 136px），
  请对方确认这不算「规避判据」　状态：TODO
- [ ] T0.2 移交审查轨（台账 §121）：`probe_first_screen.py` 的 5 条
  「原文/出处缺失」是**假阳性**。契约侧 `CASE` = 1998-07-20 14 女
  （`:58`），浏览器侧只填 `#question` 就提交（`:230-231`）→ 页面实际用
  HTML 默认 1990-05-15 10 男；两案 `evidence` 交集实测 **3/12**。
  needle 未暴露此事是因为两案 `one_liner` 恰同为「感情这块，盘里有着落点」
  （由提问主题决定，与生日无关；1990 案无提问时为「决断底子，金偏多」）。
  建议浏览器侧补填 `#year/#month/#day/#hour/#gender`。
  我方自证：填对生日后原文与出处 **12/12 可取**　状态：TODO
- [ ] T0.3 `docs/DECISIONS.md` 落 **D-238b**（折叠机制）：`<details>` 关闭态
  内层 `rect.height` 实测 **6,040px**、`offsetParent` 非 null → 不满足
  probe 的隐藏判据；`hidden` / `display:none` 均 0px + `offsetParent===null`；
  四机制下 `textContent` 都可取全文。**选 `hidden`**。
  附第二个实测：`hidden` 被作者 CSS 覆盖（`.brand` flex、`#funcGrid` grid
  设 hidden 后 computed display 不变、仍占 55/618px），故必须配
  `[hidden]{display:none!important}`——漏这条会有 ~700px 误差　状态：TODO
- [ ] T0.4 `docs/DECISIONS.md` 落 **D-239b**（V6 选型）：7 种配置扫描表
  （V1 3,276px FAIL / V2 3,036 +212 / V3 2,883 +365 / V4 2,507 +741 /
  V5 2,630 +618 / **V6 3,036 +212** / V7 3,565 FAIL），
  选 V6 的理由是「**唯一不折叠 004 白话内容且带余量**」；
  D-150a 抗漂移核验：8 案实测 `evidence` 恒 12 段、书数 6–8，
  V6 最坏（8 书）2,960px 仍余 288px　状态：TODO
- [ ] T0.5 台账登记版面构成实测（`.ev-item` 24 个 = 79,528px / 100,294px
  = **79%**；单段最高 12,219px = 15 屏；非古籍部分 2,608–2,643px）
  状态：TODO
- [ ] T0.6 `web/baselines/plain_first_fixture.json`：冻结两案
  （CASE 1998-07-20 14 女 + 感情运；HTML 默认 1990-05-15 10 男）的
  `evidence[].citation` / `text` 全文 / `why`，供判据 6/7/8 逐字节比对
  状态：TODO

**移交清单**（写台账，不改对方文件）：T0.1、T0.2。
按 D-145a：只描述**行为与实测数字**，不钉死对方的内部命名。

---

## M1 判据 5/6/7/8：去重 + V6 折叠件（清偿 R128a-01）

- [ ] T1.1 `web/static/styles.css` 加 `[hidden]{display:none!important}`
  （D-238b 的第二条实测；先加这条，后面所有折叠都依赖它）　状态：TODO
- [ ] T1.2 `web/static/app.js` 新增 `renderCiteGroups(items)`：
  按 `citation` 的书名前缀分组（实测 6–8 组）→ 每组一个
  `button.cite-toggle`（「《穷通宝鉴》 3 段 ▾」，`min-height:var(--tap)`）
  + `div.cite-group-body[hidden]`；组内每段一个
  `button.cite-toggle`（出处 + `why` + 字数）+ `div.cite-body[hidden]`
  存原文全文。`aria-expanded`/`aria-controls` 成对，点击切 `el.hidden`
  状态：TODO
- [ ] T1.3 `styles.css` 加 `.cite-wrap/.cite-group/.cite-group-body/.cite-item/
  .cite-toggle/.cite-body`：44×44 点击区（`--tap`）、AA 对比度令牌、
  **无动画**（判据 18 / reduced-motion）、`.cite-body` 保留
  `white-space:pre-wrap` 以免原文换行被吞（判据 8）　状态：TODO
- [ ] T1.4 去重（判据 5，清偿 R128a-01）：`renderWarm` 不再渲染
  `warm.citations`；warm 的古籍统一由 `buildBaziResult` 调
  `renderCiteGroups(j.evidence)` 渲染**一次**。
  用 `j.evidence`（全文）而非 `warm.citations`，因为后者是
  `interpreter.py:308` 的 `[:220]` 截断版，展开它无法满足判据 8。
  实测前提：`citations[i].text === evidence[i].text[:220]`、
  `citation` 字符串 12/12 逐条相等　状态：TODO
- [ ] T1.5 `buildLiuyaoResult`：`j.ben_jing` / `j.bian_jing` 改走
  `renderCiteGroups`（现为 `renderHits` 全展开）　状态：TODO
- [ ] T1.6 专业模式零改动核验：`renderInterpretation` 及其 citations 渲染
  一字不改；`voiceMode()==='pro'` 时 `renderCalc` 位置不变　状态：TODO
- [ ] T1.7 新建 `web/check_plain_first.py`，先实现判据 5/6/7/8：
  `.cite-body` 数量 == API `evidence` 段数（判据 5）；
  折叠态 `#result.textContent` 含 12/12 原文与 12/12 出处（判据 6/7）；
  展开后与 `plain_first_fixture.json` 逐字节相等（判据 8）。
  **必须带阳性对照**（篡改一字须退出码 1，宪法第三条偏离 4）　状态：TODO
- [ ] T1.8 里程碑闸门：`<py> probes\probe_first_screen.py`
  （判据 5 应转绿；6/7 因 T0.2 的假阳性可能仍红，以我方 check 为准）
  + `<py> web\baseline_voice.py` 退出码 0
  + 复核「12 段折叠后古籍区 ≤800px」（实测目标 428px）　状态：TODO

---

## M2 判据 1/2/3/4：顺序反转 + 结果区上浮

- [ ] T2.1 顺序反转（**仅 warm 分支**）：`buildBaziResult` 改为
  `返回条 → pill-row → nayin → renderVoice → 古籍折叠区 → (pro)renderCalc`。
  pro 分支顺序保持现状——`pro_render_baseline.json` 的 `h3` 顺序数组
  （`ten_gods/five_elements/relations/day_luck/📜 古籍依据/📖 解读`）钉死了它
  状态：TODO
- [ ] T2.2 `web/static/index.html`：确认 `#result` 之上的块都可寻址
  （`.brand`、`#dailyCard`、`#funcGrid`、两个 `.recent-section`、
  视图内 `h2` 与 `#form`），缺 id 的补上　状态：TODO
- [ ] T2.3 `app.js` 新增 `focusResult(containerId)` / `unfocusResult()`：
  提交**成功后**把上述块 + 收藏按钮置 `hidden`，结果区顶部插 44px
  「‹ 改条件重算」返回条，`window.scrollTo(0,0)`；
  `showView()` 与点返回条即复原。目标实测值：`#result` y=136px、
  `.warm-l0` y=482px、能量卡 y=881px　状态：TODO
- [ ] T2.4 塔罗/桃花/合婚/起名/黄历也调 `focusResult`（判据 1 场景 5）。
  后四者实测无 `warm` 键（004 M2 未开工），本轮只保证上浮 + 无文本墙 +
  不横向溢出，**不新建 warm 文案**　状态：TODO
- [ ] T2.5 `web/check_plain_first.py` 扩到判据 1/2/3/4：
  `.warm-l0` 文档绝对 y ≤812；`#result` 高度 ≤3,248px（≤4 屏）；
  可见最长块 ≤400 字；可见古籍字数占比 ≤40%。
  额外断言**余量**：`3248 - result_h ≥ 200`（防 V1 那种差 28px 的边缘通过）
  状态：TODO
- [ ] T2.6 里程碑闸门：`<py> probes\probe_first_screen.py` **退出码 0**
  + `<py> probes\probe_ui_smoke.py` **37 用例不减**（判据 13）　状态：TODO

---

## M3 回归防线（判据 9 / 13–18）

- [ ] T3.1 `<py> web\baseline_voice.py`（判据 9，sha256 `b0461df2…` 逐字节）
  状态：TODO
- [ ] T3.2 `<py> web\selftest.py` ≥149 断言（判据 14）　状态：TODO
- [ ] T3.3 `<py> web\check_warm_voice.py` 判据 1–8 全绿（005 判据 17）
  状态：TODO
- [ ] T3.4 `<py> probes\probe_ui_baseline.py` 只读复跑：对比度 0 /
  固定点击目标 0 / 长任务 >50ms = 0 / reduced-motion 归零 / 横向溢出 0px
  （005 判据 16/18）　状态：TODO
- [ ] T3.5 13 道闸门全绿（宪法 §IV；顺序：`check_quality` 必在 `build_index` 前）
  状态：TODO
- [ ] T3.6 `<py> probes\probe_contract.py`：本轮后端零改动，此条应天然通过；
  跑它是为了证明「零改动」不是口头声明　状态：TODO
- [ ] T3.7 判据 12 自证：切「专业版」= 切回旧版面（`plan.md` §5.2 的复用决定），
  实测切换后 pro 输出逐字节等于基线、`localStorage.voiceMode` 保持。
  若审查轨要求 pro 不上浮，加 `voiceMode()==='warm'` 门禁（一行）　状态：TODO

---

## M4 US5 引文相关性调查（P3，只测量不改 src/guji）

- [ ] T4.1 量化相关性：固定提问集（感情/事业/健康/学业/财运）统计每段引文的
  `why` 分布与「提问关键词 ↔ 引文命中」关系。已知实测：12/12 条 `why` 非空
  但取值是**盘上位置**（「月柱」「日柱」「年柱」），**不是与提问的关联**
  ——这正是要量化的落差。另已知：8 案里「遁甲演義」出现 5 次、
  「太乙金鏡式經」3 次，与八字提问关联很弱　状态：TODO
- [ ] T4.2 若确认有问题，写成**独立缺陷条目**（附命令与数字）交审查轨立项，
  **不自行改 `src/guji/search.py`**（spec US5：需先调查）　状态：TODO
- [ ] T4.3 `why` 上屏（唯一的零风险相关性改动）：组内摘要行显示
  「因『月柱』被选中」——只展示已有字段，不改检索　状态：TODO

---

## M5 收尾

- [ ] T5.1 判据 1–18 逐条实测，摘要登记台账 §121　状态：TODO
- [ ] T5.2 确认 D-238b / D-239b 已落 `docs/DECISIONS.md`（M0 已写则复核）
  状态：TODO
- [ ] T5.3 R128a-01 的状态由审查轨转——我方只在台账写「已清偿 + 复验命令」，
  **不改对方的 `AUDIT_FINDINGS.md` 条目**　状态：TODO
- [ ] T5.4 移交审查轨：本文件状态列全 DONE(命令) + M0 两条移交项的处理结果
  状态：TODO

---

## 跨 spec 依赖（005 判据 10/11 不在 M1–M5 内）

| 005 判据 | 内容 | 归属 | 现状 |
|---|---|---|---|
| 10 | 分享图（零依赖原生 Canvas + 娱乐标识 + 确定性） | `specs/004` M3（T3.1–T3.4） | TODO，未开工 |
| 11 | 今日聚合入口 | `specs/004` M2（T2.4） | TODO，未开工 |

两者已在 004 tasks 立项，005 **不重复实现**（避免两个 spec 各写一个海报）。
005 的唯一义务：`focusResult` 不得把今日聚合入口藏死（T2.3 的复原路径）。

---

## 明确不做（与 spec Out of Scope 对齐）

- `html2canvas`（D-151a REJECTED——原生 Canvas 实测 900×1200 约 191KB 可行）。
- MBTI × 塔罗（D-147a REJECTED——语料零命中）。
- 十二宫与古籍隔离（D-148a 已推翻——它是《星學大成》的真实语料内容）。
- 删除/改写/截断任何古籍原文与出处（宪法第三条；折叠 ≠ 删除）。
- 折叠 004 已交付的白话内容（V6 选型的核心理由）。
- 改 `src/guji/interpreter.py`（判据 9 护栏）、`src/guji/voice.py`（字段已齐全）、
  `src/guji/search.py`（US5 只调查）。
- 改 `probes/**`、`scripts/**`（宪法第五条）；改 `data/**`、引入依赖、联网
  （宪法第二条）。
- 给桃花/合婚/起名/黄历新建 warm 文案层（004 领土，未开工）。
