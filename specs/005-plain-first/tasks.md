# 任务清单：005-plain-first（优化轨执行文档）

状态列：`TODO` / `DOING` / `DONE(命令)` / `BLOCKED(原因)`。
宪法第一条：**没有命令的 DONE 等于没做。** 完成即改状态并附实测输出摘要。
`<py>` = `.\.venv\Scripts\python.exe`。

**唯一验收命令**：`<py> probes\probe_first_screen.py` 退出码 0 即达标。
每个里程碑收尾都要跑它并附退出码。

**领土纪律（宪法第五条）**：只写 `src/guji/**`、`web/**`。
`probes/` 与 `scripts/` 一字不改。

**R185b 修订说明**：初版 tasks 基于旧探针。审查轨 R129a（`8858107`）修了探针
三个 bug 并订正判据 1 口径，我的三条前提失效，已按 `plan.md` §0 重算：
初版的 `focusResult`（藏首页各块）**取消**、`[hidden]!important` hack **取消**、
古籍形态从 L1 按书平铺改为 **L2 单层总折叠**（L1 在 6 书用例实测 3,288px = 5 屏 FAIL）。
初版的 M0 两条移交项**已由 R129a 处理完毕**，无需再移交。

**设计已实测选定**（依据 `plan.md` §1–§4，实施阶段不重开）：
古籍区 **L2 三级折叠**（总入口 44px → 按书分组 → 每段），机制用 `hidden` + `button`，
判据 1 靠**提交后显式滚动**到结果区顶部，首页各块一个都不藏。

---

## M0 台账与决策记录（不改产品代码）

- [x] T0.1 `docs/DECISIONS.md` 落 **D-238b**（折叠机制为何仍选 `hidden`）：
  R129a 后探针已识别关闭态 `<details>`，两机制都「过」，但实测
  `<details>` 下探针**定位到 0 段古籍**（关闭态 `innerText` 为空，
  定位器全不命中）→ 判据 4 的 0% 是**空过**，无法区分「折叠成功」与
  「原文被删」；`hidden` 下探针报「定位 12 段 / 折叠 12 段」，是正面证据。
  **同一判据下 `hidden` 的通过可核验、`<details>` 的通过是空的**。⚠ R130a 已把定位改成 textContent，两机制现在都能正面核验——最终仍选 hidden 的理由改为「样式/摘要/键盘语义更直白」，与探针无关　状态：DONE(D-238b 已落，附四机制实测表)
- [x] T0.2 `docs/DECISIONS.md` 落 **D-240b**（L1 按书平铺被推翻）：
  三形态 × 三用例实测——L1 在 7 书 2,991px(+257)、8 书 3,187px(+61)、
  **6 书 3,288px(−40) = 5 屏 FAIL**；L2/L3 三案分别 2,607/2,739/2,968px。
  L1 翻车根因：组头文本在 375px 下换行（实测 492/8 = 61px 而非设计的 44px），
  且 6 书那案白话段本身更长——**高度不随书数单调**。
  记我自己的错：初版只测 7/8 书就把单调性当理所当然，正是 D-150a 说的
  「判据不能建立在会漂移的量上」　状态：DONE(D-240b 已落，附三形态×三用例表)
- [x] T0.3 `docs/DECISIONS.md` 落 **D-239b**（判据 1 用滚动而非隐藏首页）：
  R129a 口径订正后，「什么都不做」实测 L0 视口 y = 587–793px 也能过，
  但那取决于表单高度、属偶然；显式滚到结果区顶部实测恒 **353px**。
  选滚动的附加收益：首页 `.brand`/`#dailyCard`/`#funcGrid` 一个不藏，
  spec 那条「不得把今日入口永久藏死」天然满足　状态：DONE(D-239b 已落，附三种定位方式实测)
- [x] T0.4 台账 §123 登记本轮实测：新探针输出（4 项未达标、可核验性
  两项 ✅、古籍 92%）+ 目标形态五案表（判据 1/2/3/4 全绿，最小余量 280px）
  状态：DONE(台账 §123 已登记，含施工前后对比与全部回归命令)
- [x] T0.5 `web/baselines/plain_first_fixture.json`：冻结 5 个用例
  （1998-07-20 女感情 / 1990-05-15 男感情 / 1985-12-03 女事业 /
  1976-09-09 女健康 / 1990-05-15 男无提问）的 `evidence[].citation` /
  `text` 全文 / `why`，供判据 6/7/8 逐字节比对。
  **必须是多用例**——单用例正是 L1 翻车的原因　状态：DONE(`<py> web\check_plain_first.py --freeze` → frozen 5 cases，12 段/案)

---

## M1 判据 5/6/7/8：去重 + 三级折叠件（清偿 R128a-01）

- [x] T1.1 `web/static/app.js` 新增 `renderCiteTree(items)`：三级结构
  ——总入口 `button.cite-toggle`（「📜 古籍原文依据 · 12 段 / 7 部书 ▾」）
  + `div.cite-top-body[hidden]`；内按 `citation` 书名前缀分组（实测 6–8 组）
  → 组头按钮 + `div.cite-group-body[hidden]`；组内每段 → 摘要按钮
  （出处 + `why` + 字数）+ `div.cite-body[hidden]` 存原文全文。
  三级 `aria-expanded`/`aria-controls` 成对，点击切 `el.hidden`　状态：DONE(实测 .cite-toggle 20 个 / .cite-body 12 个)
- [x] T1.2 `styles.css` 加 `.cite-wrap/.cite-top/.cite-top-body/.cite-group/
  .cite-group-body/.cite-item/.cite-toggle/.cite-body`：
  `min-height:var(--tap)`（44×44）、AA 对比度令牌、**无动画**（判据 18）、
  `.cite-body{white-space:pre-wrap}` 保留原文换行（判据 8）。
  **不加** `[hidden]{display:none!important}`——实测不需要（被 hidden 的都是
  普通 div，`getComputedStyle().display === 'none'` 直接成立）　状态：DONE(styles.css .cite-* 已加；`probe_ui_baseline` 固定点击目标 0 / 对比度 0 / 动画 reduced-motion 归零)
- [x] T1.3 去重（判据 5，清偿 R128a-01）：`renderWarm` 不再渲染
  `warm.citations`；warm 的古籍由 `buildBaziResult` 调
  `renderCiteTree(j.evidence)` 渲染**一次**。
  用 `j.evidence`（全文）而非 `warm.citations`——后者是
  `interpreter.py:308` 的 `[:220]` 截断版，展开无法满足判据 8。
  实测前提：`citations[i].text === evidence[i].text[:220]`、
  `citation` 12/12 逐条相等、页面 `.ev-item` 24 个而 API 12 段　状态：DONE(warm 实测 .ev-item 0 个、.cite-body 12 个 == API 12 段)
- [x] T1.4 `buildLiuyaoResult`：`j.ben_jing` / `j.bian_jing` 改走
  `renderCiteTree`（现为 `renderHits` 全展开）　状态：DONE(`probe_ui_smoke` btn:liuyao PASS，warm 下經文进折叠树)
- [x] T1.5 专业模式零改动核验：`renderInterpretation` 及其 citations 渲染
  一字不改；`voiceMode()==='pro'` 时 `renderCalc` 位置不变　状态：DONE(切 pro 实测 .ev-item 24 / .calc-grid 存在 / h3 顺序与 pro_render_baseline 一致)
- [x] T1.6 新建 `web/check_plain_first.py`，先实现判据 5/6/7/8：
  `.cite-body` 数量 == API `evidence` 段数（判据 5）；
  折叠态 `#result.textContent` 含 12/12 原文与 12/12 出处（判据 6/7）；
  展开后与 `plain_first_fixture.json` 逐字节相等（判据 8）。
  **5 个用例全跑** + **阳性对照**（篡改一字须退出码 1，宪法第三条偏离 4）
  状态：DONE(`<py> web\check_plain_first.py` → 5 用例 PASS；`--self-check` 三注入全被抓)
- [x] T1.7 里程碑闸门：`<py> probes\probe_first_screen.py`
  （判据 5 转绿，6/7 保持 ✅）+ `<py> web\baseline_voice.py` 退出码 0
  + 复核「折叠后古籍区 = 44px」（实测目标值）　状态：DONE(probe_first_screen 退出码 0；baseline_voice sha256 b0461df2… 一致——R190b 订正：该值已被 R189b 合法重冻为 97f0681e…，本条当时的结论仍有效)

---

## M2 判据 1/2/3/4：顺序反转 + 提交后滚动定位

- [x] T2.1 顺序反转（**仅 warm 分支**）：`buildBaziResult` 改为
  `h2 → 收藏 → pill-row → nayin → renderVoice → 古籍总折叠 → (pro)renderCalc`。
  pro 分支顺序保持现状——`pro_render_baseline.json` 的 `h3` 顺序
  （`ten_gods/five_elements/relations/day_luck/📜 古籍依据/📖 解读`）钉死了它
  状态：DONE(pro h3 实测 = 基线数组，逐项一致)
- [x] T2.2 `app.js` 新增 `revealResult(containerId)`：提交**成功后**
  `window.scrollTo({top: resultTop - 8, behavior:'auto'})`。
  用 `auto` 不用 `smooth`（reduced-motion 判据 18 + 避免探针取中间值）。
  **不隐藏首页任何块**（初版 `focusResult` 已取消）。
  目标实测值：L0 相对视口 y = 353px、能量卡 637–880px　状态：DONE(五案 L0 视口 y 恒 353px；能量卡 637–880px)
- [x] T2.3 六爻/塔罗/桃花/合婚/起名/黄历也调 `revealResult`（判据 1 场景 5）。
  后四者实测无 `warm` 键（004 M2 未开工），本轮只保证提交后可见结果 +
  无文本墙 + 不横向溢出，**不新建 warm 文案**　状态：DONE(七视图全接入 revealResult；`probe_ui_smoke` 19 个按钮用例全 PASS、横向溢出 0px)
- [x] T2.4 `web/check_plain_first.py` 扩到判据 1/2/3/4，**5 个用例全跑**：
  L0 相对视口 y ∈ [0,812]；`#result` ≤3,248px；可见最长块 ≤400 字；
  可见古籍占比 ≤40%。额外断言**余量** `3248 - result_h ≥ 200`
  （防 L1 那种 −40/+61px 的边缘通过）　状态：DONE(五案余量 268–807px，全 ≥200px)
- [x] T2.5 里程碑闸门：`<py> probes\probe_first_screen.py` **退出码 0**
  + `<py> probes\probe_ui_smoke.py` **37 用例不减**（判据 13）　状态：DONE(probe_first_screen 退出码 0；probe_ui_smoke PASS)

---

## M3 回归防线（判据 9 / 13–18）

- [x] T3.1 `<py> web\baseline_voice.py`（判据 9，sha256 `b0461df2…`——R190b 订正：现值 `97f0681e…`，R189b 合法重冻）　状态：DONE(14 用例逐字节一致，退出码 0；R190b 复跑仍退出码 0)
- [x] T3.2 `<py> web\selftest.py` ≥149 断言（判据 14）　状态：DONE(149 checks PASS)
- [x] T3.3 `<py> web\check_warm_voice.py` 判据 1–8 全绿（005 判据 17）　状态：DONE(10 用例 × 8 判据 PASS)
- [ ] T3.4 `<py> probes\probe_ui_baseline.py` 只读复跑：对比度 0 /
  固定点击目标 0 / 长任务 >50ms = 0 / reduced-motion 归零 / 横向溢出 0px
  （005 判据 16/18）　状态：DONE(三视口：对比度 0 / 固定点击目标 0 / 长任务 0 / reduced-motion 动画 0 / 横向溢出 0px)
- [ ] T3.5 13 道闸门全绿（宪法 §IV；`check_quality` 必在 `build_index` 前）
  状态：DONE(13/13 exit=0，顺序照宪法 §IV)
- [ ] T3.6 `<py> probes\probe_contract.py`：本轮后端零改动，应天然通过；
  跑它是为了证明「零改动」不是口头声明　状态：DONE(164 个字段读取点全部存在，SOFT=11)
- [ ] T3.7 判据 12 自证：切「专业版」= 切回旧版面（`plan.md` §5.2），
  实测切换后 pro 输出逐字节等于基线、`localStorage.voiceMode` 保持　状态：DONE(切 pro→旧版面完整回来 82,623px/.ev-item 24；刷新后 voiceMode=pro；切回 warm→2,619px/.cite-body 12)

---

## M4 US5 引文相关性调查（P3，只测量不改 src/guji）

- [ ] T4.1 量化相关性：固定提问集（感情/事业/健康/学业/财运）统计每段引文的
  `why` 分布与「提问关键词 ↔ 引文命中」关系。已知实测：12/12 条 `why` 非空
  但取值是**盘上位置**（「月柱」「日柱」「年柱」），**不是与提问的关联**
  ——这正是要量化的落差。另已知 8 案里「遁甲演義」出现 5 次、
  「太乙金鏡式經」3 次，与八字提问关联很弱　状态：DONE(台账 §124；六种提问逐位比对 12/12 完全一致——question 对检索零影响)
- [ ] T4.2 若确认有问题，写成**独立缺陷条目**（附命令与数字）交审查轨立项，
  **不自行改 `src/guji/search.py`**（spec US5：需先调查）　状态：DONE(缺陷条目已写台账 §124 移交审查轨，建议 MAJOR；根因 services.py:159 未传 req.question)
- [x] T4.3 `why` 上屏（唯一的零风险相关性改动）：第三级摘要行显示
  「因『月柱』被选中」——只展示已有字段，不改检索　状态：DONE(`app.js:236`；fixture 五案 60 条 why 全为年/月/日柱)

---

## M5 收尾

- [x] T5.1 判据 1–18 逐条实测，摘要登记台账 §123　状态：DONE(见 §123；判据 1-9/13-18 全绿，10/11 属 004 跨 spec 未开工)
- [x] T5.2 确认 D-238b / D-239b / D-240b / D-241b 已落 `docs/DECISIONS.md`
  状态：DONE(四条已 append，行 5327/5362/5389/5424)
- [x] T5.3 R128a-01 的状态由审查轨转——我方只在台账写「已清偿 + 复验命令」，
  **不改对方的 `AUDIT_FINDINGS.md` 条目**　状态：DONE(§123 已写清偿证据：warm 下 .ev-item 0 个、.cite-body 12 段 == API 12 段；`count_open_findings` 仍 exit=1 待对方转状态)

---

## 跨 spec 依赖（005 判据 10/11 不在 M1–M5 内）

| 005 判据 | 内容 | 归属 | 现状 |
|---|---|---|---|
| 10 | 分享图（零依赖原生 Canvas + 娱乐标识 + 确定性） | `specs/004` M3（T3.1–T3.4） | TODO，未开工 |
| 11 | 今日聚合入口 | `specs/004` M2（T2.4） | TODO，未开工 |

两者已在 004 tasks 立项，005 **不重复实现**。本方案不隐藏首页，
spec 那条「上浮不得把今日入口永久藏死」的边界天然满足。

---

## 明确不做（与 spec Out of Scope 对齐）

- 不隐藏首页任何块（初版 `focusResult` 取消）；不加
  `[hidden]{display:none!important}` 全局 hack（不再需要）。
- 不用 `<details>` 做古籍折叠（探针下是空过，无法区分折叠与删除，D-240b）。
- 不折叠 004 已交付的白话内容（005 只改顺序与层级）。
- `html2canvas`（D-151a REJECTED）、MBTI × 塔罗（D-147a REJECTED）、
  十二宫与古籍隔离（D-148a 已推翻）。
- 删除/改写/截断任何古籍原文与出处（宪法第三条；折叠 ≠ 删除）。
- 改 `src/guji/**`（字段已齐全，改后端牵动 149 条断言且收益为零）、
  `probes/**`、`scripts/**`（宪法第五条）、`data/**` / 引入依赖 / 联网（宪法第二条）。
- 给桃花/合婚/起名/黄历新建 warm 文案层（004 领土，未开工）。
