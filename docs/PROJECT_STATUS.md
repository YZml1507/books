# 项目状态

> 本文是**当轮实测快照**。长期计划见 `MASTER_PLAN.md`，
> **任务状态的唯一来源是 `TASK_LEDGER.md`**（含 REJECTED 清单，防止重做已否决方案），
> 工程教训见 `LESSONS.md`。
>
> **R228s 标注**：本文最后刷新于 R175b 时代（2026-08-17 快照块，数字已过期）；
> 当前实测快照见 `TASK_LEDGER.md` 末条判据行。

**更新时间**：2026-08-17（R78b，优化轨——快照块行 19 由 R78b 改为 T1-T11；前一次快照 2026-08-17 R49b，见文末历史节）
**当前阶段**：Phase 7（Optimization）——审查-修复循环 R5-R17 闭环后进入双窗口并行
（审查轨 `books-audit` worktree 审 scripts/probes/打包链；优化轨=本仓做差距分析+能力优化，
方案见 `OPTIMIZE_20260816_R18.md`）。

---

## 当前实测快照（2026-08-17——R78b 更新快照块行 19 T1-T11，历轮刷新见头部；复验命令 = TASK_LEDGER 开头 13 闸门，全部亲自实跑）

```
索引      47 部 → 62,109 单元 · 55.7 MB · 页锚点 13,954 · 有地址 57,315（92.3%）
G 判据    PASS 9 · PART 0 · FAIL 0（assess_goals.py 实测，含 G4 多跳/G8 三类知识隔离/G9 跨会话）
闸门      13 道全绿：verify_index T1-T11 ALL PASS · check_quality PASS（阴阳双对照）
          · 4 probes PASS · eval_g1 / eval_g4 / eval_g7 PASS
suspect   10 单元 / 5 地址（R17 修正归责：verdict 后缀定作品，EXPECTED 非缺陷不入列）
地址体系  zhouyi · bcv · yilin · booksec · play（幕/场）· euclid（卷/命题）等六类已入索引
链接      源文印出互见 link 表零悬空，2-hop 可组合（G4）
质量      quality_report 10 个低覆盖地址全部分类归责；OCR 损坏控制项 卦61上九 持续检出（T11）
安全      web 层 XSS/SSRF/编码红线 R5-R16 修复 17 commit；remote URL 已无明文 PAT（R17）
研究模式  八模式全落地（R18b-R27b）：Quick/Deep/Book Study/Chapter/Comparative
          （两书对照 compare_works）/Cross-book/Book Summary/Concept
发布面    web 9 研究 tab 全接线（检索/深度研究/定位/比对/书目/线程/读书/两书对照/
          概念研究，R25b/R26b/R29b）+ 书目→读书一键 + 语料统计（/api/stats，
          R40b）；MCP 12 工具 stdio 同源发布（R22b-R38b：含协议级 --selftest
          自测、add_local_work_tool 本地加书、record_claim_tool 写线程 +
          threads 读回 claims/evidence，记忆闭环 web/MCP 双端齐；R165b 补
          research_tool 协议级断言——G7 拒绝 + 正常检索，与 web 侧
          R144b/R146b research 断言同源；R167b 补 search/addr/compare/
          concept 四条协议级断言——12 工具协议级调用 6→10 个；R168b
          补 book_summary_tool/bookstudy_structure/bookstudy_chapter 三
          条错误路径协议级断言——work_id 不存在显式返回错误文本；R169b
          补 search/addr/compare/concept 五条边界路径协议级断言——空
          查询/非法 scheme/无 gua/超范围 gua 宽容返回）
记忆闭环  研究→记录→跨会话恢复（愿景 §8/§9）：web POST /api/threads + 三个
          研究 tab「记入线程」+ 记入后列表自动刷新（R34b/R35b/R41b）；MCP
          record_claim_tool 写 + threads(tid) 读回（R36b/R42b）；长期研究
          续接（viewThread「在此线程续接研究」+ 深度研究 tab 徽标可取消，
          R45b/R46b）
治理      双窗口边界：R44b 反驳审查轨 R24a 越界指控（git 铁证）→ R25a 亲核实
          后撤回（R47b 记录闭环）；R21a 委托待审查轨合入 main（移交项）
自测      各层 standing 自测全齐：sources/bookstudy/research/mcp `--selftest`
          + web `python -m app --selftest`（123 checks，R175b 同步——R49b 12
          checks 起，R53b 补数术端点、R54b 补研究/历史/线程/健康端点、R61b
          补首页 /、R69b 补 bazi.semantic 语义路径、R110b-R115b 功能轮 +11、
          R118b/R119b 各 +2：liuyao.time/huangli.affair/bazi.lunar/
          bazi.lunar_leap、R121b +1：hehun、R124b +5：错误路径断言 err.*、
          R126b +2：bazi.range/bazi.life、R128b +2：search.layer/search.work、
          R130b +2：compare_works.refuse/bookstudy.chapter.nullscheme、
          R132b +1：research.allow_damaged、R134b +1：bookstudy.summary.missing、
          R136b +1：history.detail.missing（R137b 误删 R138b 恢复）、
          R137b +1：addr.zhouyi.yao、R138b +1：hehun.dayun、R139b +3：
          err.bazi.calendar/scope/gender、R140b +2：err.qiming.gender/year、
          R141b +3：err.liuyao.time.year/month/missing、R142b +3：
          err.huangli.date/year/illegal、R143b +3：err.taohua.year/gender/
          calendar、R144b +3：err.compare_works.missing/err.concept.empty/
          err.research.max_addresses、R145b +1：err.search.empty、R146b +2：
          err.concept.too_long/err.research.too_long、R147b +1：
          err.compare.gua_range、R148b +3：err.addr.zhouyi.no_gua/
          err.bookstudy.structure.empty/err.bookstudy.chapter.empty、
          R149b +5：err.liuyao.time.day/hour/err.qiming.month/day/hour、
          R150b +6：err.bazi.lunar_missing/month/day/err.hehun.b_year/
          b_month/b_day、R151b +4：err.bazi.ask_hour/ask_date/
          range_missing/range_format、R152b +4：err.bazi.range_order/
          range_span/err.bookstudy.chapter.scheme/err.qiming.calc_fail、
          R153b +2：err.research.empty/err.compare_works.q_empty、
          R154b +4：err.hehun.a_month/a_day/a_hour/b_hour、
          R156b +1：err.bazi.lunar_year、
          R157b +1：err.liuyao.time.convert_fail、
          R158b +1：err.bazi.lunar_solar_range、
          R159b +1：err.threads.kind（500→400 修复）、
          R162b +5：err.huangli.month/day + err.bazi.month/day/hour
          （承接并行窗口）、
          R163b +1：err.bazi.paipan_fail（422）、
          R164b +2：err.taohua.paipan_fail/err.hehun.paipan_fail（422）、
          R169b +1：err.threads.detail.missing（并行窗口提交）+ MCP
          search/addr/compare/concept 五条边界路径协议级断言（承接
          并行窗口 595635d 并入）、
          R170b +2：err.ask.q_empty/q_too_short（并行窗口提交）、
          R171b +1：err.compare_works.q_too_long（并行窗口 3dc5dbb 提交，
          R172b d06ab16 去重修正——compare_works q_empty 与 R153b 重复
          删除，checks 121）、
          R174b +1：err.bazi.ask_date_year（承接并行窗口半成品）、
          R176b +1：err.ask.q_too_long（随 R174b 提交 678aea3 夹带入
          HEAD，并行窗口半成品））
```

**相对第三轮快照（文末历史）的关键变化**（均为后续轮次实测落地，勿再引用旧状态）：

- Douay-Rheims 已支持（douay.py，R9；APPENDICES 巨型 verse 亦已切分）。
- tier 2/3 已入索引：play（Shakespeare 幕/场）、euclid、booksec（Herodotus/Darwin）、
  iliad 双译本（R8 giant-unit 二次切分后 max 全部达标）。
- `unit.suspect` 列已存在（X-11），且 R17 修正了 6/10 地址误归责（span-*-B 误标在
  A 作品导致健康文本被 answer 层扣留——L-20 危害类）。
- G1 概念级检索已覆盖（eval_g1 retrieval_concept **53/55 = 96.4% PASS**，
  目标 80%——2 条稳定失败 CP-02-02-六四 等为 bge top-10 边界案例，非检索
  缺陷，不修，照 D-031 留档防误修；bge 向量覆盖爻位单元 2,489，卦辞走
  FTS，R65b 记录）；G4/G8/G9 从未实现变为 PASS。
- 语料 28→47 部（+术数 8 部：三命通會等；+generality：plato/shakespeare/euclid/
  herodotus/iliad×2/douay；+道家 3 部：老子/莊子/莊子注，R20b）。
- 审查-修复循环 R5-R17 共 19 个 fix commit（6 红线级含 huangli 宿锚/ingest 巨型单元/
  douay 丢行/web XSS escAttr/llm_reader AttributeError/evalset 编码）。
- R23b-R29b 研究模式闭环：Book Study（structure/chapter，含 NULL-scheme file 节）、
  两书对照 compare_works、Book Summary 结构化知识卡、概念研究 tab；MCP 10 工具
  （含协议级 stdio `--selftest`）；前端 9 tab 全接线 + 书目→读书一键（localStorage
  记忆）。13 闸门每轮全绿（G1-G9 PASS 9 · PART 0 · FAIL 0）。
- R30b-R42b：Local File Adapter（本地 txt 书入库，CLI + MCP add_local_work_tool，
  愿景 §10/§18）；研究线程写入口（web POST /api/threads + 三研究 tab「记入
  线程」+ 列表自动刷新；MCP record_claim_tool + threads 读回 claims/evidence）；
  前端语料统计视图（/api/stats 接线）；MASTER_PLAN/ROADMAP/MCP_CLIENT_CONFIG
  文档对齐（数字去硬编码，以可执行自测为唯一权威）。MCP 12 工具。
- R44b-R49b：双窗口治理闭环（R44b 以 git 铁证反驳审查轨 R24a 越界指控 →
  R25a 亲核实后撤回，R47b 记录）；web 长期研究续接（viewThread 续接按钮 +
  深度研究 tab 徽标可取消，R45b/R46b）；书目来源可见化（/api/works 合并
  manifest source + 前端来源列，R48b）；web 层 standing 自测
  （`python -m app --selftest` 12 checks，R49b——各层自测至此全齐）。
- R50b-R54b：接续文档防误导（GOAL_NEXT_SESSION 刷新到当前状态 R51b；
  LESSONS 补录 R23b-R51b 教训 L-22..L-26，R52b）；web standing 自测扩展
  至 22 checks（R53b 补 4 个数术端点 bazi/liuyao/huangli/qiming、R54b 补
  研究/历史/线程/健康端点 research/ask/history/threads/health；external/
  news 联网端点明确排除，D-100b）；R53b 自纠 bazi check 污染 history.db
  （L-22 同族，改为调用后清理新增记录）。

---

## 第三轮实测快照（历史存档，2026-08-13——数字已过时，仅作演进对照；本轮头号发现：bcv 把 10 卷经文挂到别卷地址，已修 U-08/D-022/L-19）

```
索引      28 部 → 13,577 单元 · 5.5 秒 · 18.4 MB · 页锚点 100% · provenance 0/28 缺失
          有地址单元 10,120（74.5%），此前 5,088（59.1%）
G 判据    PASS 8 · PART 1 · FAIL 0        （上一轮 PASS 3 · PART 1 · FAIL 4 · N/A 1）
          唯一非 PASS 的是 G1，且是故意的：概念级检索未覆盖，不虚报
对齐      爻辭 verified 1824/1872 = 97.4%（本轮所有改动零回退）
守恒      源 2,653,857 = 索引 2,653,857 · 缺失 0 · 重复率 1.0000
地址体系  **三种**：zhouyi（卦/爻）· bcv（卷/章/節，KJV 66 卷 24,995 節 /
          WEB 66 卷 31,102 節）· yilin（本卦/之卦，4,096 单元）
引用披露  非连续引文 4,524（33.3%）已标 `skipped_chars` + `!`；损坏区 20 单元已标 `suspect` + `?`
链接      558 条源文印出的互见，零悬空，100% 有文本支持
折叠表    FOLD 88 对（新增 `㤗→泰`）· NOT_VARIANTS 23
```

**四种地址体系，且形状互不相似**（这才是通用性的证据，不是数量到四）：

| 体系 | addr1 / addr2 | 它压的是列模型的哪一处 |
|---|---|---|
| `zhouyi` | 卦號 / 爻位**标签** | `addr2` 不能是 INTEGER（用九/用六 无序数位置） |
| `bcv` | 章 / 節 | **三级**塞进两列 + 名字；`addr_name` 空间开放（66 卷） |
| `yilin` | 本卦號 / 之卦名 | **同一类实体的两个位置**——矩阵，不是层级 |
| `booksec` | 卷 / 节 | **同一体系两种深度**：Herodotus 763 节，Darwin `addr2` 全 NULL |

`booksec` 已有解析器与闸门，**但尚未入索引**（P-08）。

**本轮修掉的四个「闸门不是闸门」**，这四条比新增功能更重要：

1. `probe_bcv.py` 是八道红线之一，却**永远 exit 0**——包括它打印「56/66 卷」那一次。
2. `cross_edition_coverage` 对 KR1a0031/0032 只比较了 377 个共享地址中的 **17 个**
   （`min_len=20` 把 360 个滤掉），然后报「中位覆盖 1.000、低于 0.60 者 0」。
   台账曾把这条当作 G3 的证据。
3. `verify_index.py` 从未断言质量闸门的校准，尽管 `quality.py` 的文档说它断言了（P-03，已修，新增 T11）。
4. 质量闸门**只有阳性对照**，于是把完好的 卦47上六 判成损坏、连带让回答层拒答真实证据。
   已加**已知阴性对照**（D-027 / L-20）。

**本轮的方法论收获**（比数字更值得带走）：

- 同一份输出里两个对不上的数，就是一份缺陷报告——它查出 10 卷经文错挂地址（L-19）。
- 「同一段文本」有多个归一化空间，混用会**伪造**缺陷也会**掩盖**缺陷（L-18）。
- 质量标记的**假阳性与漏标对称**，且假阳性更难发现（L-20）。
- 修好一个缺陷会长出下一个：卦47 的误判是地址窗口修准之后才出现的，
  而那期间**八道闸门全绿**。

---

## 本轮做了什么（按重要性）

### 1. 修掉伪造引文的偏移错位缺陷 ⚠ 最严重

上一轮 D-008 把「单元开头落在爻位标记第二个字」判为**外观问题**并写下「不再追查」。
**这个判断是错的**，它和另一个症状同源：

```
错位 piece 占比 100%（8 部易類全部，6233/6233、9478/9478 …），最大 14 字
被放错的地址切点 2,634
爻单元以自身爻位标记开头： 0 / 1872  →  1858 / 1872
索引伪造的引文        ： 有能乾○九乾惕厲之象  →  有能乾乾惕厲之象（与原文一致）
```

根因：`_iter_pieces` 返回「原文起始偏移 + 清洗后文本」，调用方用原文坐标索引清洗文本。
修法：`Piece` 携带逐字偏移表，一律 `bisect` 换算。详见 D-011。

**守恒闸门**（新增 `probes/probe_conservation.py`）：

```
28 部 CJK 字符  源 2,653,857 = 索引 2,653,857   缺失 0   凭空多出 0   重复率 1.0000
raw_start..raw_end 越界单元 0 / 4985
```

单元数 35,978 → 8,611（跨注合并），**单元数本身分辨不出「合并」与「丢数据」**，所以这个
多重集检查是必需闸门。

### 2. 顺带修掉两个同源缺陷

- **层次语义塌陷**：王弼/程頤/朱熹被引的 **經** 与他们自己的 **注** 同标为 `注`，
  `--layer 經` 只能捞到一部书，且 merge 把經注融成一块打乱次序。现按位置交替发出，
  `經` 命中 3 → 10。
- **`gua_name` 是死字段**（全为 `""`），现从 KR1a0001 的 `《X第N》` 推导，引用显示为 `卦1（乾）`。

### 3. 语料本身有 OCR 损坏（此前当作干净 ground truth）

```
KR1a0006 卦61  翰青登于天貞凶輪高飛也狀音堵昔莊而寳才從之謂也届卦之上處信芝絃
KR1a0007 卦61  翰音登于天貞凶注翰高飛也飛音者音飛而實不從之謂也居卦之上處信之終
```

同书 卦19 臨 另有**缺文**（335 字 vs 注疏 1804 字，三爻整段缺失）。

**探测器对比（失败的那个更有信息量）**：

| 方法 | 结果 |
|---|---|
| 字符 bigram 稀有度 | **失败**：已知损坏排名 599/88,530，低于自身阈值；榜首全是太玄經音義字表 |
| 跨版本同址一致性 | **通过**：358 地址中位数 0.991，损坏处**排名 2**，coverage 0.050 |

新增 `src/guji/quality.py` + `scripts/check_quality.py`，**控制组失效即 exit 1**。
该闸门还暴露了**我自己的 5 个抽取错误**（`span-degenerate-B`，KR1a0007 有序搜索锁定了
交叉引用），而这些在 `validate_alignment` 里被计为 located——**覆盖率指标看不见它们**。

### 4. 通用性证伪测试（此前是最大的未验证假设）

取 10 部公版西文书专攻「只实现过一种地址体系」这一点。**结论：schema 结构性不通用**——
`gua/gua_name/yao` 是字面列名，第二种体系无法存储。已改为

```
(scheme, addr_name, addr1 INTEGER, addr2 TEXT)   + unit_zhouyi 视图 + gua=/yao= 别名
```

`addr2` 必须是 TEXT：周易的 `用九`/`用六` 是真实可寻址单元但**没有序号**，比圣经更苛刻。

并且真写了第二个解析器 `src/guji/bcv.py`：

```
KJV 66 卷 24,995 節    WEB 56 卷 29,214 節    5/5 控制用例正确
跨译本同址对照： John 3:16  KJV「only begotten Son」 / WEB「one and only Son」
```

**D-006 的三种失效模式在完全不同语料上原样复现**，另有两种周易没有的新模式
（目录构成第二条有序链；散文句通过命名占比测试）。详见 D-015/D-016。

### 5. KR1a0031 93.6% → 94.4%，并**决定不再追 95%**

8 个折叠候选只通过 3 个，其余按语料频次否决：`極→拯`（2,821 次，含**太極**）、
`悔→晦`（1,136 次，含**亢龍有悔**）、`其→有`（24,061 次）。
**刷到 95% 需要接受这些折叠，那是用语料正确性换指标。** 详见 D-013。

剩余失败已逐条定性：源文误刻、真实異文、爻位误标。新增 `detect_mislabelled_yao()`——
版本自己把爻位刻错时（如 中孚 印出 `九三`，而该卦三爻为阴，**此爻位不可能存在**），
报告为**源文异常**而非 unknown。详见 D-014。

---

## G1–G9 判据实测（`scripts/assess_goals.py`）

此前进度是凭印象报告的。现在逐条实测，不可测的明确标为不可测：

| 判据 | 结果 | 依据 |
|---|---|---|
| G1 能找到原文 | **不可测** | 无人工核验评测集。FTS5 命中 ≠ 该段回答了那个概念 |
| G2 能精确定位 | **PASS** | 抽样 4,000 单元，锚点作为字面 `<pb:>` 标签在其源文件中命中 4,000 / 0 失败 |
| G3 能区分版本 | **PASS** | `cross_edition_coverage()` 逐地址枚举异文并分类；異文刻意不折叠 |
| G4 能跨单元关联 | **FAIL** | 无实体层、无多跳、无链接表 |
| G5 能比较注家 | **PART** | 乾九三 返回 6 部书（經 6 · 注 4），引用可核验；**缺差异摘要** |
| G6 能引用证据 | **PASS** | 抽样 4,000，真实引用缺陷 **0**，错误率 0.000%（判据 ≤1%） |
| G7 能承认证据不足 | **FAIL** | 无回答层。数据层已尊重 unknown，那是 G7 的前提而非 G7 |
| G8 能区分知识来源 | **FAIL** | 只有 Source，没有 Derived / Conversation 存储，分离是空真 |
| G9 能长期研究 | **FAIL** | 无研究线程持久化。`build_meta` 记录构建，不记录探究 |

```
PASS 3   PART 1   FAIL 4   不可测 1
```

### 测 G6 时连踩两个坑，都记下来

1. 第一版报 **97.85% 引用错误率**。是**测试脚本错**：用「单文件」去索引「拼接体偏移」。
   `schema.sql` 明写 `raw_start` 是拼接体偏移，且 `probe_conservation.py` 早已用正确坐标
   系测出 0 失败——两个测量互相矛盾时，新的那个才是可疑的。
2. 改对坐标系后仍报 53%。这次暴露了**一个此前没人记录的事实**：

```
文本是其声称区间的连续子串        1,866 / 4,000
文本是其区间的有序子序列（合并跳过了交错层）  2,134 / 4,000   ← 53%
两者都不是（真实缺陷）              0
```

`merge_units` 按 key 跨注合并，所以一个 `經` 单元会**跳过夹在中间的 `注`**，
`raw_start..raw_end` 是**包络**而非连续引文。这对「只引經」是正当做法（校勘惯例），
**但必须向读者披露**——现在没有披露。新增 P1。

顺带：`probe_conservation.py` 用的是**多重集**检查，**测不出重排**，而重排正是本轮修掉的
那个缺陷。子序列检查严格更强，应作为主闸门。

---

## 当前实测数字（**历史存档，R17 前快照——28 部 8,611 单元已过时，现为 47 部 62,109 单元；R78b 标注**）

```
索引     28 部 → 8,611 单元，4.8 秒，17.8 MB，页锚点覆盖 100%
对齐     爻辭 verified 1824/1872 = 97.4%
         KR1a0006 98.4  KR1a0007 97.9  KR1a0016 98.1  KR1a0031 94.4  KR1a0032 98.4
验收     scripts/verify_index.py    12 项全过
守恒     probes/probe_conservation.py  delta 0
质量     scripts/check_quality.py   控制组 PASS，1 处 text-damage、2 处 span-overextended、5 处 span-degenerate
圣经     KJV 66 卷 24,995 節 · WEB 56 卷 29,214 節 · 5/5 控制用例
```

---

## 未解决问题（按优先级）

### P1 53% 的单元是层过滤引文，但未向读者披露

`merge_units` 跨注合并后，`經` 单元跳过夹在中间的 `注`，因此 4,000 抽样中 2,134 个的文本
**不是其区间的连续子串**，而是有序子序列。引用是诚实的（校勘惯例即如此引經），
但读者无从得知这段引文中间被删去了注文。

修法候选：`unit` 增 `contiguous INTEGER`（构建时即可判定），引用渲染时对非连续者加标记
（如 `…` 或「經文，已滤注」）。

### P1 质量闸门暴露的 5 个抽取错误未修

`span-degenerate-B`：卦46九二(lenB=1)、卦9初九(6)、卦9九二(4)、卦58九五(9)、卦46初六(26)。
KR1a0007 有序爻位搜索锁定了孔穎達的交叉引用而非真正爻辭。

**注意循环风险**：用「跟随文本最接近底本爻辭」来选位置会让准确率指标自我印证。
候选非循环判据：段落长度不应退化到该卦中位数的极小比例——此判据不查底本文本。

### P1 Douay-Rheims 不支持

行首经文号仅 3 个，行内 35,905 个是互见。需段内编号解析器。

### P2 tier 2/3 七部书未建索引

Plato（Stephanus）、Shakespeare（幕/场）、Euclid（卷/命题）、Darwin、Herodotus、
Iliad 两译本。已落盘 + manifest（`data/catalog/generality_manifest.json`），
但 `bcv` 之外的 scheme 解析器都没写。**「系统通用」目前只能说到两种体系。**

### P2 KR1a0006 卦19 缺文、卦61 损坏未在索引中标记

已探测到，但 `unit` 表没有 `suspect` 列，检索结果不会提示「此段文本可疑」。
引用系统应当告知用户。

### P2 Kanripo 无 license 文件

25 个仓库无一含 LICENSE/COPYING。按 work 逐条记录，不假定宽松许可。

### P3 markitdown 零页边界

4 份 PDF + 1 份 EPUB 输出均为 0 个页标记 → 不能作为需引用文档的唯一解析器。

---

## TODO（较小项）

- [x] junk 检测器加入 `\(cid:\d+\)` 统计（**已实现**：src/guji/quality.py:283 `_CID_RE` + Detector 3 junk census，Q-06 已含 cid 列；R74b 核实）
- [x] `自天祐之` 在两源 5 vs 4 的真实差异，查明原因（**已查清**：D-034/T7-n 繫辞传印次差异 KR1a0001(5) vs KR1a0032(4)；R74b 核实）
- [x] `&KR0658;` 形式的无码位字形，设计占位符语义（`differs` 类失败里多次出现）（**已查清**：T7-m = 虩 U+8679，台账 §1017 probe_t7m_entities.py；R74b 核实）
- [x] 55 个 probes 已沉淀结论的可归档，避免与 `src/`+`scripts/` 混淆（**已做**：R51b 归档 57 个、活跃 54；R74b 核实）
- [x] Phase 3 Review：架构文档自审，找过度设计与技术债（**已完成**：D-034 即 Phase 3 架构自审，评审 BOOK_AI_ARCHITECTURE.md；R74b 核实）
- [x] 知识图谱：建图前须确认 `differs` 類異文不会被实体抽取抹平（**已处置**：probes/probe_t7q_kg_precondition.py 实跑 exit 0——三类实体抽取策略（字符级 NER/关键词级/折叠表归一化）均保留 稊/梯、跛/破 区别，differs 異文不被抹平，前置条件"满足（可建图）"；台账 §1011-1015 T7-q；建图本身是另一项工作，GOAL.md T7-q 红线 3 依赖；R75b 核实）
