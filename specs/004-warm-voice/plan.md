# 实施计划：004-warm-voice（优化轨 HOW 文档）

**Created**: 2026-08-20（优化轨 R181b）
**上游**: `specs/004-warm-voice/spec.md`（审查轨 R123a 收编，5 US + 19 判据）；
处置依据 `docs/DECISIONS.md` D-146a（BYOK 七条）/ D-147a（MBTI REJECTED）/
D-148a（十二宫=语料内容，推翻隔离定性）。
**本文职责**: 宪法第六条——spec 写 WHAT/WHY，本文件写 HOW。
19 条判据逐条映射到任务与复验命令，见 §2（映射表）与 `tasks.md`。

---

## 0. 总原则：先量尺，后动刀（判据 9 决定的施工顺序）

判据 9 要求专业模式**逐字节等于**本 spec 创建时的输出。因此**第一个任务不是
写文案，是冻结基线**（照 D-143a 先例：验证脚本 + fixture，固定输入集合的
`interpret_*.text` / `sections` / `citations` 全量快照）。基线 fixture 落库后，
后续任何改动一旦碰出字节漂移，CI 式脚本立即退出码 1。

### 0.1 领土更正（D-236b）：验证脚本落 `web/`，不落 `probes/`

本文件与 `tasks.md` 初版把 M0 产物写在 `probes/` 目录下（probe_voice_baseline、
probe_warm_voice、xingzuo_fixture 等）——**这违反宪法第五条**：`probes/` 是审查轨
独占写、优化轨禁改（constitution.md:164），且仓库现存全部 probe 均由审查轨
R118a–R123a 创建。宪法 Governance 段规定「违反的解决方式是改 spec/plan/tasks，
而不是稀释原则」，故本轮更正如下（左列为初版路径，均在 `probes/` 下）：

| 初版（越界，`probes/…`） | 更正后（优化轨领土内） |
|---|---|
| `probe_voice_baseline.py` | `web/baseline_voice.py`（判据 9） |
| `voice_baseline.json` | `web/baselines/voice_baseline.json` |
| `probe_warm_voice.py` | `web/check_warm_voice.py`（判据 1–8） |
| `xingzuo_fixture.json` | `web/baselines/xingzuo_fixture.json` |
| `probe_xingzuo.py` | `web/check_xingzuo.py`（判据 10/11） |
| `probe_poster.py` | `web/check_poster.py`（判据 12/13） |
| 扩展 `probes/probe_no_generated_in_corpus.py`（判据 14） | **移交审查轨**：新文案表路径写进台账，由对方扩展其探针 |
| 扩展 `probes/probe_ui_smoke.py`（判据 16） | **移交审查轨**：新增用例的行为描述写进台账，由对方扩展 |
| 扩展 `probes/probe_selftest_regress.py` baseline（判据 17） | **移交审查轨**：`web/selftest.py` 新断言名单写进台账，由对方同步 baseline |

全部脚本仍满足「闸门必须有非零退出码」（PHASE.md 纪律）：失败退出 1、
成功退出 0、各带阳性对照。审查轨若要把它们纳入自己的闸门清单，
可直接调用或包一层 `probes/probe_*.py`——接口即命令行退出码，不需要改我的文件。

施工铁律：

1. **M0 基线冻结**先行，未跑绿 M0 不动任何 `src/` `web/` 文件。
2. 专业模式渲染代码路径**不重写**——warm 是新增分支，不是改造现有分支。
3. 每个里程碑（M1–M4）结束跑全量回归（判据 15–19），绿了才进下一个。

## 1. 架构

### 1.1 后端：新增 `src/guji/voice.py`（warm 视图层，独立于 interpreter）

```
src/guji/voice.py          ← 新模块：warm 视图构建器 + 规则表 + 引文锚点
src/guji/interpreter.py    ← 不改（专业模式输出即基线，动一行判据 9 就炸）
src/guji/xingzuo.py        ← 新模块：十二宫日运（七政四餘体系，带引文）
web/routers/*.py           ← 各解读端点响应体附加 "warm" 键（ additive，不动既有键）
web/static/app.js          ← renderInterpretation 增加模式分支 + 切换器 + details 折叠
web/static/index.html      ← 结果区头部加模式切换控件；首页加「今日运势」入口卡
```

要点：

- **interpreter.py 零改动**是判据 9 最省力的实现方式：专业模式输出天然不变，
  探针只需钉住「interpreter 的输出函数没被改 + 前端专业分支渲染逻辑没被改」。
- `voice.py` 是纯函数模块（无 IO、无随机、无网络），同输入必同输出（判据 5）。
  warm 文案模板全部写死在本模块；每条模板注明它转述的 calc 字段。
- 路由层组装：`{"interpretation": …(原样), "warm": voice.warm_bazi(calc, q)}`。
  前端按 `voiceMode` 决定渲染哪个。**API additive 变更**需过 `probe_contract`
  （前端读取点同步登记，防 R000a-04 类漂移）。

### 1.2 warm 视图结构（四层，对应 US1/US2）

```
L0  one_liner     一句话 ≤20 字（判据 2），有提问时直接回应提问（判据 1）
L1  energy_card   {本命元素, 幸运色[], 幸运数字[], 幸运时段, 今日关键词[]}（US4）
L1.5 reply        对提问的描述性回应：坐标落点白话化 + 开放式提示，3–5 行
L2  details       现有 sections 的口吻改写版；「依据：…」推导链放 <details> 折叠（判据 4）
L3  citations     逐字节复用 interpreter 的 citations（判据 15）
badge disclaimer  「仅供娱乐 · 详细依据见专业模式」置于 L1 卡片下方，不压轴（判据 7）
```

六爻的 `reply` 模板（判据 8）：卦名白话（写死 64 卦一句话性格）+ 动爻位置含义
（写死 6 爻位白话）+ 变卦方向 + 「卦爻辞原文如下，可对照你问的事」。
引文与出处逐字节不动（判据 15）。

### 1.3 十二宫日运：`src/guji/xingzuo.py`（US4，判据 10/11）

- **今名↔古籍名映射**（语料用传统名，用户看今名）：
  天秤↔秤宫、天蝎↔蝎、射手↔人馬、摩羯↔磨蝎、水瓶↔瓶、双子↔隂陽、
  处女↔雙女，白羊/金牛/巨蟹/獅子/雙魚同名（@KR3g0041_WYG_001-1a 十二宫神表）。
- **日运推导**（零随机）：日干支五行（`huangli.day_ganzhi` 已有）× 宫对应
  二十八宿分野的五行属性 → 写死的文案块选择；幸运色/数字同 §1.4 规则。
- **每宫必带引文**：分野表句（如白羊→「奎婁白羊魯國戌」@KR3g0041_WYG_001-1a）
  + 当日五行相关的河图/五色引文。实现时用台账 §115 的检索命令钉死每个锚点的
  work_id + addr + text 进 `web/baselines/xingzuo_fixture.json`，探针断言引文在
  corpus 逐字命中（照 `probe_no_generated_in_corpus` 的阳性对照做法）。
- API：`GET /api/xingzuo?sign=白羊&date=2026-08-20`；12 宫 × 同日全量输出
  逐字节可复现（判据 11）。
- 首页「今日运势」聚合入口卡（黄历宜忌口吻版 + 本命日运 L0/L1 + 十二宫入口），
  复用 P0 文案层，不新建渲染管线。

### 1.4 幸运项规则（判据 1/2/10：写死映射 + 可引古籍）

| 项 | 规则（写死） | 出处锚点（实现时钉死进 fixture） |
|---|---|---|
| 幸运数字 | 河图数：水1·6 火2·7 木3·8 金4·9 土5·0；取「生日主之行」的河图数 | 「天一生水」类单元（台账 §115 命中 11 条，选經层） |
| 幸运色 | 五行配色：水黑蓝 火红紫 木青绿 金白金银 土黄棕；同上取行 | 「五色」类单元（命中 74 条） |
| 幸运时段 | 十二时辰五行（寅卯木 巳午火 申酉金 亥子水 辰戌丑未土）取生扶时辰 | 三命通会/星學大成时辰类单元 |
| 跨天变化 | 随日干支变化，规则明确（判据 US4.2「跨天变化有明确规则」） | 同上 |

### 1.5 分享海报（US5）：零依赖原生 Canvas，不用 html2canvas

**决策（待落 D-234b）**：原生 Canvas 2D 直绘固定版式卡片（1080×1440）——
L0 + 能量卡色块 + 幸运色/数字 + 日期 + 站名 +「仅供娱乐」水印，`toBlob` 下载。

理由：(a) US5.5 把 html2canvas 定为**须用户明确授权**，零依赖方案不需要授权、
不碰宪法红线第 3 项，今天就能做；(b) 海报版式本来就是固定设计稿，DOM 截图
的通用性用不上；(c) 少 48KB vendor 与一份 provenance 维护负担。
**若用户一句话授权 html2canvas**，仅替换 `drawPoster()` 内部实现，接口与
判据不变（对 US5 判据完全透明）。

### 1.6 前端模式切换（US3）

- 结果区头部切换控件（`voiceMode`: warm|pro），localStorage 持久化，加载时应用。
- 切换只重渲染结果区，不动表单与历史数据（US3.3）。
- 控件本身计入 003 判据（≥44×44、AA 对比度）——见 §4 协调点。

## 2. 判据 → 实现/验收映射（19 条全覆盖）

| # | 判据 | 实现落点 | 验收命令 |
|---|---|---|---|
| 1 | 首节回应提问 | voice L0/reply 置顶；前端 warm 分支首节点 | `web/check_warm_voice.py` |
| 2 | 一句话 ≤20 字 | voice `one_liner` 生成器带长度截断 + 模板短句 | 同上 |
| 3 | 首屏术语 ≤3 | warm 首屏只渲染 L0/L1/badge；术语表写死探针 | 同上（浏览器实测首屏 DOM） |
| 4 | 依据折叠且逐字不变 | `<details>` 包裹 basis 行；文本取自原 sections 未改写 | 同上（展开后与基线 fixture 比对） |
| 5 | 同输入同输出 | voice 纯函数；两次调用逐字节断言 | `web/selftest.py` + check_warm_voice |
| 6 | 禁断言/指令 =0 | 模板写作守则 §3；禁用词表写死探针 | check_warm_voice（含阳性对照） |
| 7 | 免责含「仅供娱乐」不压轴 | badge 置于 L1 下方、L2 之前 | 同上 |
| 8 | 六爻描述性回应 | voice `reply` 模板（64 卦白话 + 爻位白话表） | 同上 |
| 9 | 专业模式逐字节等于当前 | M0 冻结 `web/baselines/voice_baseline.json` + `web/baseline_voice.py` | baseline_voice |
| 10 | 幸运项 100% 可追溯 | §1.4 规则表 + 锚点 fixture；探针断言引文在 corpus 命中 | `web/check_xingzuo.py` |
| 11 | 12 宫×同日逐字节复现 | xingzuo 纯函数 | 同上 |
| 12 | 分享图非空含娱乐标识 | `drawPoster()` + 下载按钮 | `web/check_poster.py`（toDataURL 长度阈值） |
| 13 | 运行时外链 =0 | 海报零依赖；静态扫描 | check_poster 内嵌静态检查 |
| 14 | 新文案不入库 | warm 只随响应返回、落 history.db；扩展隔离探针覆盖 voice/xingzuo 文案表 | 移交审查轨扩展（台账登记文案表路径） |
| 15 | 引文逐字节不变 | voice 不触碰 citations；复用 interpreter 输出 | baseline_voice + check_warm_voice |
| 16 | UI smoke 只增不减 | 新增用例：模式切换、分享出图、今日运势入口、十二宫 | 移交审查轨扩展（台账登记用例行为） |
| 17 | selftest 只增不减 | warm 存在性/确定性/内容断言 ≥8 条 | `web/selftest.py`（baseline 同步移交审查轨） |
| 18 | 13 闸门 + 5–9 全绿 | 每里程碑收尾全量跑 | PHASE.md 命令清单 |
| 19 | 003 的 14 条不退步 | §4 协调点清单 | `probes/probe_ui_baseline.py` 复测 |

## 3. warm 模板写作守则（US2 的下限与上限）

**下限（要像人话）**：第二人称；先回应情绪再给信息；每段 ≤3 行；
可用 emoji（能量卡限 3 个以内）；术语出现即白话化（「七杀」→「外部压力位」，
括号里保留原词供检索）。

**上限（不许断命）**：禁用词表（探针写死，含但不仅限于）：会脱单/一定会/
必然/该分手/该辞职/买/卖/投资/治病/必有贵人/命中注定。
句式只允许：**描述已算出的坐标**（「你的盘里 X 在 Y 位」）+
**开放式提示**（「适合…不妨…可以先…」）+
**把判断权交还**（「怎么对应，你比盘清楚」）。

**候选与否决记录**：措辞方向（闺蜜体 vs 治愈系短句体）实现时各出一样例，
按 spec Assumptions 记 `docs/DECISIONS.md`（D-235b 预留）。

## 4. 与 003 的同批协调点（判据 19）

1. 模式切换控件、分享按钮、今日运势入口卡：44×44、AA 对比度（003 判据 1–3）。
2. 海报生成是同步 Canvas 绘制，长任务采集纳入 003 判据 5（>50ms = 0）。
3. 切换/出图动效遵守 reduced-motion 归零（003 判据 6）。
4. warm 首屏新增色块（幸运色）计入 003 对比度扫描范围。
5. 两套模式各自过 003 的 14 条（003 US5.3 同款要求）。

## 5. 里程碑与顺序（对应 tasks.md）

```
M0 基线冻结（判据 9 的前提）        ← 不改任何产品代码
M1 US1+US2+US3：voice.py + 双模式切换（P1 三条 US）
M2 US4：幸运项规则 + xingzuo.py + 今日运势聚合（P3 前半）
M3 US5：drawPoster 零依赖海报（P3 后半）
M4 全量回归 + 003 协调复测 + 台账/D-entries 收尾
```

M1 结束即可给用户看真实效果（用户指示的核心痛点在 M1 就解除）；
M2/M3 依赖 M1 的文案层。若 M2 语料锚点钉死时发现某条引文定位不稳定
（OCR 异文等），按宪法第一条处置：换锚点并记录，不硬凑。

## 6. 风险与回退

| 风险 | 缓解 |
|---|---|
| warm 改动意外触碰专业输出 | 判据 9 探针在每次提交前跑（秒级，纯比对） |
| 文案风格用户不认可 | US3 一键切回 + D-235b 记录候选与否决 |
| 十二宫引文锚点不稳（OCR/異文） | fixture 逐字断言；失败即换锚点并记录，不放宽探针 |
| 新增 API 键造成契约漂移 | probe_contract 同步登记 warm 读取点 |
| 海报在低端机卡顿 | 1080×1440 单帧绘制，实测长任务；超 50ms 降 750×1000 |
