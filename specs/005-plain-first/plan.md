# 实施计划：005-plain-first（优化轨 HOW 文档）

**Created**: 2026-08-20（优化轨 R184b）
**上游**: `specs/005-plain-first/spec.md`（审查轨 R128a，5 US + 18 判据）
**验收命令（唯一）**: `<py> probes\probe_first_screen.py` 退出码 0 即达标
（`<py>` = `.\.venv\Scripts\python.exe`）
**本文职责**: 宪法第六条——spec 写 WHAT/WHY，本文件写 HOW。
18 条判据逐条映射到任务与复验命令，见 §5。

**已定死、本文件不重开的三件事**（用户本轮明确）：

- `html2canvas` **REJECTED**（D-151a）——分享图用浏览器原生 Canvas 2D，
  实测 900×1200 出图约 191KB 可行。
- MBTI × 塔罗 **REJECTED**（D-147a）——语料零命中。
- 十二宫**不隔离**（D-148a）——它是《星學大成》的真实语料内容。

---

## 0. 施工前实测：先证明方案可行，再写任务

宪法第一条要求任何数字先跑命令。本 plan 的每个阈值决定都来自真实浏览器测量
（375×812，Chromium 151.0.7922.34，固定用例 1998-07-20 14 时女 +「感情运怎么样？」）。
**不是估计，也不是"应该能行"。**

### 0.1 闸门当前输出（本轮亲自跑，退出码 1）

```
契约侧：warm.one_liner = '感情这块，盘里有着落点'
        evidence 12 段，合计 21,153 字　当前口吻模式 = warm
整页 107,719px　结果区 100,606px = 124 屏　共 32,007 字
❌ 一句话结论 y=92,794px（第 115 屏）      阈值 ≤812px
❌ 结果区 124 屏                           阈值 ≤4 屏
❌ 默认可见最长文本块 7,955 字             阈值 ≤400 字
❌ 古籍原文默认可见 18,053 字 = 56%        阈值 ≤40%
❌ 4 段原文缺失 / 1 段出处缺失
probe_first_screen FAIL: 6 项未达标
```

### 0.2 版面构成（`#result` = 100,294px 的去向）

| 块 | 数量 | 高度 | 字数 |
|---|---|---|---|
| `#result` 全体 | 1 | **100,294px** | 25,743 |
| `.ev-item` 古籍条目 | **24** | **79,528px（79%）** | 24,801 |
| 其中 `.ev-text` 正文 | 24 | 77,922px | 23,799 |
| `.warm-l0` 一句话 | 1 | 88px | 11 |
| `.warm-reply` 回应提问 | 1 | 286px | 116 |
| `.energy-card` 能量卡 | 1 | 495px | 100 |
| `.warm-badge` 免责 | 1 | 27px | 16 |
| `.interp-sec`（6 段，不含古籍块） | 6 | 1,145px | 567 |
| `.mode-switch` 切换器 | 1 | 44px | 13 |
| `pill-row`+`nayin`+`h2`+收藏按钮+`h3` | — | 284px | 63 |

单段古籍高度实测（CASE，含 padding）：`12,030 / 10,005 / 10,599 / 5,010 /
12,219 / 1,797×6 / 9,627`px。**一段《穷通宝鉴·论庚金》就是 14.8 屏。**

### 0.3 目标形态的实测结果（关键：方案已在真实页面上验证过）

在真实结果区上用 DOM 操作模拟目标形态（去重 + 折叠 + 顺序反转 + 结果区上浮），
复刻 `probe_first_screen.py` 的度量算法逐条测量：

| probe 判据 | 阈值 | 现状 | **模拟目标形态实测** |
|---|---|---|---|
| 1 一句话 y | ≤812px | 92,794 | **482px** ✅ |
| 2 结果区屏数 | ≤4（≤3,248px） | 124 | **2,960px = 4 屏** ✅（见 §1） |
| 3 可见最长块 | ≤400 字 | 7,955 | **71 字** ✅ |
| 4 古籍可见占比 | ≤40% | 56% | **0%**（12 段全折叠，probe 判 12/12 hidden） ✅ |
| 5 同段渲染次数 | 1 | 2 | **1** ✅ |
| 6 折叠后原文可取 | 12/12 | — | **12/12** ✅ |
| 7 折叠后出处可取 | 12/12 | — | **12/12** ✅ |
| 8 展开逐字节一致 | 一致 | — | **True**（`cite-body.textContent === evidence[0].text`） ✅ |

附带：能量卡 y = **881px**（第 2 屏开头，满足 US1 场景 2 的「紧随其后的一屏内」）。
可核验性抽查在**填对生日**后：原文缺 0 段、出处缺 0 条（对比 §2.2 的假阳性）。

**结论：8 条判据全部可达，且不需要删减任何白话内容、不需要截断任何古籍原文。**

---

## 1. 判据 2 的余量必须靠设计争取（差 13px 的教训）

判据 2 用 `Math.ceil(h / 812) ≤ 4`，即 `h ≤ 3,248px`。最初的设计
（12 条独立摘要按钮，每条 `padding:10px` → 64px 行高）实测 **3,276px = 5 屏，
超 28px**。差这一点也是 FAIL，宪法第二条禁止放宽阈值，所以必须改设计。

同一会话扫描 7 种配置（`cite区` = 折叠后古籍区总高）：

| 配置 | cite 区 | `result_h` | 屏 | 余量 | 判据 2 |
|---|---|---|---|---|---|
| V1 12 条 · 64px 行 · 折 2 段白话 | 1,197 | 3,276 | 5 | −28 | ❌ |
| V2 12 条 · 44px 行 · 折 2 段白话 | 957 | 3,036 | 4 | +212 | ✅ |
| V3 12 条 · 44px 行 · 折 3 段白话 | 957 | 2,883 | 4 | +365 | ✅ |
| V4 按书 7 组 · 44px · 折 2 段白话 | 428 | 2,507 | 4 | +741 | ✅ |
| V5 按书 7 组 · 44px · 折 1 段白话 | 428 | 2,630 | 4 | +618 | ✅ |
| **V6 按书 7 组 · 44px · 白话零折叠** | **428** | **3,036** | **4** | **+212** | ✅ |
| V7 12 条 · 44px · 白话零折叠 | 957 | 3,565 | 5 | −317 | ❌ |

**选定 V6：按书分组的两级折叠，白话内容一段都不折。**

- V6 与 V2 余量相同（+212px），但 V6 **不折叠任何白话**——V2/V3/V4/V5 都要把
  「十神格局」「运算摘要」这类 004 已交付的白话段折起来。005 的定位是
  「改版面顺序，不改内容」（spec §2「这些都不用改」），折白话越界了。
- V7 证明：**只要不分组，白话就必须折**（超 317px）。分组是「不动 004 内容」的前提。
- V4/V5 余量更大，作为超预算时的兜底（§6 风险表）。

### 1.1 V6 的余量能不能扛住数据变化（D-150a：判据不能建立在会漂移的量上）

8 个不同生日/提问的实测：`evidence` **恒为 12 段**（`services.py:116`
`_dedup_evidence(limit=12)` 与 `interpreter.py:298` 的 `[:12]` 双重钳制），
但**书目数在 6–8 之间浮动**：

| 书数 | V6（按书 44px×书数） | 余量 | V2（逐段 44px×12） | 余量 |
|---|---|---|---|---|
| 6 | 2,872px | +376 | 3,136px | +112 |
| 7 | 2,916px | +332 | 3,136px | +112 |
| **8（实测最坏）** | **2,960px** | **+288** | 3,136px | +112 |

书数越多 V6 越高，但**最坏情形 8 部书仍余 288px**。V6 的浮动区间
（2,872–2,960px）比 V2 的固定 3,136px 更远离阈值。若将来 `limit` 从 12 放大，
V6 的高度只随**书数**增长（受语料部数上限约束），V2 随**段数**线性增长——
V6 对数据变化更稳。这条写进判据设计理由，不是事后解释。

---

## 2. 两条 BLOCKER：不解决，判据 1 与 6/7 无论怎么排版都过不了

两条都不是"难做"，是**结构性不可能**或**probe 侧的假阳性**。
宪法第二条禁止放宽闸门，所以处置是改实现结构 / 移交事实，不是改阈值。

### 2.1 BLOCKER-1：判据 1 量文档绝对 y，而 `#result` 起点就在 3,005px

`probe_first_screen.py:92` 取 `b.top + window.scrollY`（文档绝对坐标），
阈值 812。实测 `#result` 自身绝对 y = **3,005px**：

| `#result` 之上的块 | 绝对 y | 高度 |
|---|---|---|
| `.brand` 品牌区 | 28 | 55 |
| `#dailyCard` 今日运势卡 | 111 | 577 |
| `#funcGrid` 八个功能卡 | 712 | 618 |
| `.recent-section` 最近的解读 | 1,366 | 467 |
| `.recent-section` 我的收藏 | 1,860 | 133 |
| `h2` 排盘标题 | 2,038 | 43 |
| `#form` 排盘表单 | 2,097 | **888** |
| **`#result`** | **3,005** | 100,294 |

**即使结果区第一个像素就是那句话，y 也是 3,005px = 阈值的 3.7 倍。**
古籍全折叠 + warm 排最前，判据 1 依然 FAIL。

**处置：提交成功后让结果区上浮（`focusResult`）。** 把品牌 / 今日运势 /
功能卡 / 最近·收藏 / 视图标题 / 表单收进可复原的隐藏态，结果区顶部插一行
44px 的「‹ 改条件重算」返回条。实测 `#result` 绝对 y 从 3,005 → **136px**，
`.warm-l0` → **482px**，判据 1 达标且余 330px。

这不是"藏功能"：返回条一点即复原，`showView()` 切视图也复原，信息可达性不降。

### 2.2 BLOCKER-2：判据 6/7 现在报的 5 条缺失**全是假阳性**

probe 报「4 段原文缺失 + 1 段出处缺失」。根因在 probe 自己的用例不一致：

- 契约侧 `CASE` = 1998-07-20 14 时 **女**（`probe_first_screen.py:58`）；
- 浏览器侧**只填 `#question` 就提交**（`:230-231`），页面实际用 HTML 默认值
  **1990-05-15 10 时 男**；
- 两案 `evidence` 交集实测仅 **3/12**（各自独有 9 段）。「【穷通宝鉴·论戊土】」
  「【五行大义·论合】」「星命溯源」在 CASE 里有、在页面那一案里根本没检索到
  ——**当然取不到**。

needle 之所以没暴露这个 bug：两案的 `one_liner` **恰好同为**
「感情这块，盘里有着落点」（由提问主题决定，与生日无关；1990 案无提问时是
「决断底子，金偏多」）。**needle 撞巧相同，掩盖了用例不一致。**

我方自证：填对生日后，`evidence` 12 段的原文与出处在 `textContent` 里
**12/12 全部可取**（§0.3 末行）。

**处置：写进台账移交审查轨**（宪法第五条，我不改 `probes/`），建议浏览器侧
补填 `#year/#month/#day/#hour/#gender`，或把 `CASE` 改成 HTML 默认值。

⚠ **判据 6/7 当前的 FAIL 不是产品缺陷**，M1 不得为了让它变绿去改渲染
——那会修错东西（D-149a 同族教训）。

---

## 3. 折叠机制选型：`hidden` + `[hidden]{display:none!important}`

### 3.1 `<details>` 在本 Chromium 下不满足 probe 的隐藏判据

同一会话注入 12 段 × 4,000 字对照（Chromium 151.0.7922.34）：

| 机制 | 折叠后 12 段总高 | `offsetParent===null` | `rect.height` | probe 判「已隐藏」 | `textContent` | `innerText` |
|---|---|---|---|---|---|---|
| `<details>` 关闭 | 307px | false | **6,040px** | **false** ❌ | ✅ | ✗ |
| `hidden` 属性 | 768px | true | 0 | **true** ✅ | ✅ | ✗ |
| `display:none` | 768px | true | 0 | true ✅ | ✅ | ✗ |
| `content-visibility:hidden` | 768px | false | 0 | true ✅ | ✅ | ✗ |

`<details>` 关闭时子元素**仍有 6,040px 的布局盒**（只是不绘制），
`probe_first_screen.py:122` 的 `offsetParent === null || height === 0` 判它「可见」
→ 判据 4 会把折叠内容全额计入，永远 FAIL。004 的 `.warm-basis` 用 `<details>`
没出事，只因内容仅 17 字。

判据 3 同理：`<details>` 内层过不了那两道，7,955 字仍会被点名；`hidden` 能过。
**机制选错，同一份阈值差 20 倍。**

### 3.2 `hidden` 会被作者 CSS 的 `display` 覆盖——必须配 `!important`

实测（本轮踩到的坑）：给块设 `hidden` 后 `getComputedStyle().display`：

| 元素 | 作者 CSS display | 设 `hidden` 后 | 仍可见？ |
|---|---|---|---|
| `.brand` | `flex`（`styles.css:95`） | **flex** | **是** ❌ |
| `#funcGrid` | `grid`（`:192`） | **grid** | **是** ❌ |
| `#dailyCard` | `block` | none | 否 ✅ |
| `.recent-section` | `block` | none | 否 ✅ |

`hidden` 属性等价于 UA 样式 `display:none`，**优先级低于任何作者规则**。
第一次模拟因此只把 `#result` 推到 830px（`.brand` 55 + `#funcGrid` 618 仍占位）。
加 `[hidden]{display:none!important}` 后实测 → **136px**。

**故 `styles.css` 必须显式加这一条规则**，且它同时保证 `.cite-body`（若将来
被赋予 flex/grid 布局）的折叠可靠。这是实现细节，但漏了就有 700px 误差。

---

## 4. 架构：改哪些文件、每处改什么

### 4.1 文件清单（全在优化轨领土：`src/guji/**`、`web/**`）

```
web/static/app.js         ← 主战场：去重 + 折叠件 + 顺序反转 + focusResult
web/static/styles.css     ← [hidden]!important、.cite-* 样式（44px 点击区、AA）
web/static/index.html     ← #result 之上的块补可寻址容器
web/check_plain_first.py  ← 本轨自测闸门（新建；不落 probes/，宪法第五条）
web/baselines/plain_first_fixture.json ← 判据 6/7/8 的逐字节 fixture
```

**不改**：`src/guji/interpreter.py`（判据 9 的护栏）、`src/guji/voice.py`
（判据所需字段已齐全，见 §4.5）、`src/guji/search.py`（US5 只调查）、
`probes/**` `scripts/**`（宪法第五条）、`data/**`（宪法第二条）。

### 4.2 去重（判据 5，清偿 R128a-01）

`buildBaziResult`（`app.js:608-611`）渲染 `j.evidence` 全文，
`renderWarm`（`:301-309`）又渲染 `warm.citations`。实测两者同源：

- 12/12 条目一一对应，`citation` 字符串逐条相等；
- `citations[i].text === evidence[i].text[:220]`（`interpreter.py:308` 的截断）；
- 页面 `.ev-item` = **24 个**，API 只有 12 段。

**处置：warm 模式只渲染一处，且用 `j.evidence`（全文版）。**
理由：判据 8 要求「展开原文与 API 逐字节一致」，而 `warm.citations` 是
220 字截断版，展开它不可能逐字节一致。`renderWarm` 不再渲染 citations。

专业模式路径**一字不改**（判据 9）：`renderInterpretation` 内的 citations 渲染保持原样。

### 4.3 折叠件契约（判据 3/4/5/6/7/8）

V6 的两级形态，每部书一个 44px 组头，组内默认折叠：

```html
<div class="cite-wrap">
  <div class="cite-group">
    <button type="button" class="cite-toggle" aria-expanded="false"
            aria-controls="cg-0">《穷通宝鉴》 3 段 ▾</button>
    <div class="cite-group-body" id="cg-0" hidden>
      <div class="cite-item">
        <button type="button" class="cite-toggle" aria-expanded="false"
                aria-controls="cb-0">
          穷通宝鉴 @? (qiongtongbaojian_001.txt) · 因「月柱」被选中 · 4,123 字 ▾
        </button>
        <div class="cite-body" id="cb-0" hidden>…原文全文，逐字节等于 API…</div>
      </div>
      …
    </div>
  </div>
  …
</div>
```

- **默认可见的只有 6–8 个组头**（44px × 书数 = 264–352px），判据 3 实测
  最长可见块 **43 字**（组头文本）。
- **出处常显**（判据 5）：`citation`（实测形如 `穷通宝鉴 @? (qiongtongbaojian_001.txt)`
  或 `星命溯源 @KR3g0035_WYG_004-10b (KR3g0035_004.txt)`）在按钮上，展开一级即见。
  判据 5 的解释：**折叠态两者都不算「显示原文」**（原文不可见但可取），
  展开态两者同屏。绝不出现「有原文没出处」或「有出处取不到原文」。
  这与 R118a-03（原文有了出处没了）的判定方向一致——那条 MAJOR 反对的是
  **出处丢失**，不是反对原文折叠。
- **逐字节一致**（判据 8）：`.cite-body` 用 `esc(h.text)` 原样输出，不 trim、
  不改标点、不合并空白、不做 `[:220]`。实测 `cite-body.textContent === evidence[0].text` → True。
- **可核验性**（判据 6/7）：`hidden` 不影响 `textContent`（§3.1 实测），
  两级折叠下 12/12 原文与 12/12 出处始终可取。
- **点击区 ≥44×44、AA 对比度**（005 判据 16 / 003 判据 1-3）：`.cite-toggle`
  用 `min-height:var(--tap)`（`styles.css:573` 的 `.warm-basis summary` 已有先例）。
- **`why` 上屏**：实测 12/12 条 `why` 非空（「月柱」「日柱」「年柱」），
  摘要行显示「因『月柱』被选中」。只展示已有字段，**不改检索逻辑**。

### 4.4 顺序反转与结果区上浮

**顺序反转（仅 warm 分支）**：`buildBaziResult` 现为
`h2 → 收藏 → pill-row → nayin → (pro:renderCalc) → 古籍 h3 + renderHits → renderVoice`，
改为：

```
返回条(44px) → pill-row(四柱) → nayin
  → renderVoice(j)      ← warm：切换器 / L0 / reply / 能量卡 / badge / 6 段白话
  → 古籍折叠区           ← V6 两级折叠
  → (pro 模式) renderCalc
```

⚠ **pro 分支顺序保持现状不动**——判据 9 与 `pro_render_baseline.json` 的
`h3` 顺序数组（`ten_gods / five_elements / relations / day_luck / 📜 古籍依据 /
📖 解读`）钉死了它。顺序反转只在 warm 分支生效。

**`focusResult(containerId)` / `unfocusResult()`**：提交**成功后**把
`.brand` / `#dailyCard` / `#funcGrid` / 两个 `.recent-section` / 视图内
`h2` 与 `#form` 与收藏按钮置 `hidden`，插 44px 返回条，`window.scrollTo(0,0)`。
`showView()` 与点返回条即复原。实测 `#result` y = 136px、`.warm-l0` = 482px。

### 4.5 不改 `src/guji/voice.py`

判据所需字段响应里全有：`evidence[]` 带
`citation/text/why/layer/work_id/page_anchor/title`，`warm` 带 L0/reply/energy_card。
摘要行的「字数」在前端算（`h.text.length`）。
additive 改后端会牵动 `probe_contract` 与 `web/selftest.py` 的 149 条断言，收益为零。

### 4.6 其它功能视图（判据 1 场景 5：不是只修排盘）

实测各端点：

| 视图 | `warm` | 证据键 | 本轮处置 |
|---|---|---|---|
| 排盘 `/api/bazi` | ✅ | `evidence` 12 段 | 全量改造（主战场） |
| 六爻 `/api/liuyao` | ✅ | `ben_jing`/`bian_jing` | 折叠 + 顺序反转 + focusResult |
| 塔罗 `/api/tarot` | ✅ | citations 空 | 顺序反转 + focusResult |
| 桃花 `/api/taohua` | ✗ | `notes` | 只做 focusResult + 版面收敛 |
| 合婚 `/api/hehun` | ✗ | `notes` | 同上 |
| 起名 `/api/qiming` | ✗ | — | 同上 |
| 黄历 `/api/huangli` | ✗ | — | 同上 |

后四者没有 warm 层（004 只做了三个端点）。**本轮不给它们新建 warm 文案**
——那是 004 的领土且未开工。005 对它们只保证「结果区上浮 + 无文本墙 + 不横向溢出」。
判据 1 场景 5 的完整达成依赖 004 M2，见 §6 风险表。

---

## 5. 判据 → 实现/验收映射（18 条全覆盖）

唯一验收命令：`<py> probes\probe_first_screen.py` 退出码 0。
「自证」列是我提交前自己跑的等价检查（都在 `web/` 领土内）。

| # | 判据 | 现状 → 目标 | 实现落点 | 模拟实测 | 自证命令 |
|---|---|---|---|---|---|
| 1 | 一句话 y ≤812px | 92,794 → ≤812 | §4.4 focusResult + 顺序反转 | **482px** | `web\check_plain_first.py` |
| 2 | 结果区 ≤4 屏 | 124 → ≤4 | §1 V6 两级折叠 | **2,960px（8 书最坏）** | 同上 |
| 3 | 单块 ≤400 字 | 7,955 → ≤400 | 组头 ≤80 字，正文 hidden | **43 字** | 同上 |
| 4 | 古籍可见 ≤40% | 56% → ≤40% | 同上 | **0%（12/12 hidden）** | 同上 |
| 5 | 同段渲染 1 次 | 2 → 1 | §4.2 只渲染 `j.evidence` | **1** | 同上 |
| 6 | 折叠后原文可取 | — → 12/12 | `hidden` 不动 `textContent` | **12/12** | 同上 |
| 7 | 折叠后出处可取 | — → 12/12 | 出处在组内按钮上 | **12/12** | 同上 |
| 8 | 展开逐字节一致 | — → 一致 | 用全文而非 220 字截断版 | **True** | 同上 + `web\baseline_voice.py` |
| 9 | pro 逐字节等于基线 | 成立 → 保持 | pro 分支零改动 | — | `<py> web\baseline_voice.py` |
| 10 | 分享图（零依赖 Canvas） | 不具备 | **004 M3**（跨 spec，见 §5.1） | — | `web\check_poster.py`（004 建） |
| 11 | 今日聚合入口 | 不具备 | **004 M2**（跨 spec，见 §5.1） | — | `probes\probe_ui_smoke.py` |
| 12 | 版面可一键切回 | — → 具备 | §5.2 复用 `voiceMode` | — | `web\check_plain_first.py` |
| 13 | UI 冒烟只增不减 | 37/37 | focusResult 提交后才生效、切视图复原 | — | `<py> probes\probe_ui_smoke.py` |
| 14 | selftest 只增不减 | 149 | 后端零改动 | — | `<py> web\selftest.py` |
| 15 | 13 闸门全绿 | 保持 | 不碰语料与索引 | — | 宪法 §IV 清单 |
| 16 | 003 判据不退步 | 保持 | `--tap` + AA 令牌 | — | `<py> probes\probe_ui_baseline.py` |
| 17 | 004 判据 1–9 不退步 | 保持 | warm 文案零改动，只改位置 | — | `<py> web\check_warm_voice.py` |
| 18 | 长任务/reduced-motion/溢出 | 保持 | 折叠是属性切换，无动画 | — | `probes\probe_ui_baseline.py` |

### 5.1 判据 10/11 是跨 spec 依赖，005 不重复实现

两条对应 `specs/004` 的 M2（T2.4 今日聚合）与 M3（T3.1–T3.4 海报），
004 tasks 里**全为 TODO，未开工**。005 spec 把它们列为 P2。
本 plan 的 M1–M3 不含它们，避免两个 spec 各写一个海报。
005 对它们的唯一义务：`focusResult` 不得把今日聚合入口藏死（复原路径覆盖）。

### 5.2 一键切回（判据 12 / US3）：复用既有开关，不新增第三个

**决策：切「专业版」即切回旧版面。** 三条理由：

1. 全部改动只在 warm 分支（§4.4 已论证 pro 必须逐字节不动），
   所以 pro 分支现状**就是**旧版面。
2. 判据 9 已把 pro 输出钉成回滚目标（sha256 `b0461df2…`）。再加一个开关
   等于两条回滚路径，其中一条必然缺测——D-152a 的教训。
3. `localStorage.voiceMode` 与 US3.4「下次打开保持」同构，不需要第二套持久化。

`focusResult` 是**视图状态**而非模式，pro 下也生效（它只动 `#result` 之上的块，
不改结果区内容），因此不影响判据 9 的字节比对。若审查轨认为「pro 也上浮」
构成对旧版面的改动，处置是加 `voiceMode()==='warm'` 门禁——一行，见 §6。

---

## 6. 里程碑与风险

```
M0 交接与自证（不改产品代码）
M1 判据 5/6/7/8 —— 去重 + V6 折叠件（清偿 R128a-01）
M2 判据 1/2/3/4 —— 顺序反转 + focusResult 上浮
M3 判据 9/13–18 —— 全量回归 + 003/004 协调复测
M4 US5 引文相关性**调查**（只测量，不改 src/guji）+ 收尾
```

M1 独立可测且清偿一条 OPEN MAJOR；M2 依赖 M1 腾出的高度预算；
M4 只产出测量与缺陷条目（spec US5 明确「需先调查」）。

| 风险 | 实测依据 | 缓解 |
|---|---|---|
| 判据 2 余量被数据变化吃掉 | 书数 6–8，最坏 2,960px 余 288px | 超预算时降级 V5 → V4（余量 618/741px），最后才折白话 |
| `hidden` 被作者 CSS 覆盖 | `.brand` flex / `#funcGrid` grid 实测仍可见 | `styles.css` 显式 `[hidden]{display:none!important}`；M2 用 `getComputedStyle` 复核 |
| `focusResult` 藏死入口 → UI 冒烟掉用例 | 19 个按钮用例经 `.func-card` 进入 | 只在提交成功后生效、切视图即复原；M2 收尾跑 37 用例 |
| 返回条占位把判据 1 顶超 | 返回条 44px；实测 L0=482px 余 330px | 余量足够；若不够改 `position:fixed` 不占文档流 |
| 折叠机制选错 → 判据 3/4 永远 FAIL | `<details>` 内层 6,040px | 已定 `hidden`；M1 收尾复核「12 段折叠后 ≤800px」 |
| 判据 6/7 假阳性继续报红 | 两案 evidence 交集 3/12 | 已移交审查轨；**不为假阳性改产品代码** |
| pro 分支被波及 → 判据 9 炸 | 基线 sha256 `b0461df2…`、DOM 指纹 h3 顺序 | 每次提交前跑 `web\baseline_voice.py`（秒级） |
| 用户找不到古籍（产品风险） | 古籍占 79% 高度是当前主因 | 组头显示书名 + 段数，展开见出处 + `why` + 字数；不是一个总开关 |
| 判据 1 场景 5 依赖 004 未开工项 | 桃花/合婚/起名/黄历无 `warm` 键 | 005 只保证上浮与无文本墙；warm 文案归 004 |

## 7. 明确不做

- 不改 `src/guji/interpreter.py`、`src/guji/voice.py`、`src/guji/search.py`
  与任何检索相关性逻辑（US5 只调查；改法按缺陷条目另立）。
- 不改 `probes/**`、`scripts/**`（宪法第五条），需对方改的写台账移交。
- 不删除、不改写、不截断任何古籍原文与出处（宪法第三条；折叠 ≠ 删除）。
- 不折叠 004 已交付的白话内容（V6 选型的核心；005 只改顺序与层级）。
- 不引入外部依赖、不联网、不动 `data/**`（宪法第二条）。
- 不做 `html2canvas`（D-151a）、MBTI（D-147a）、十二宫隔离（D-148a 已推翻）。
- 不给桃花/合婚/起名/黄历新建 warm 文案层（004 领土，未开工）。
