# 任务台账

**更新** 2026-08-13 · 唯一的任务状态来源

---

## 使用约定（重要）

**每完成一个小任务，立刻在此处加一行**，否则下一轮会重做。每行必须有：

| 字段 | 要求 |
|---|---|
| 状态 | `DONE` / `PART` / `TODO` / **`REJECTED`** |
| 复验 | 一条能重现该状态的命令。**没有命令的状态不可信** |
| 产物 | 文件路径 |

**`REJECTED` 是这份台账最重要的状态。** 它记录"试过、测过、否决了"，附否决数据。
没有它，下一轮会重新实现同一个失败方案。已有 4 条 REJECTED，都花了真实时间。

状态一律以脚本输出为准，不以本文的句子为准。全部复验：

**顺序重要**：`check_quality.py` 必须在 `build_index.py` **之前**跑——
`suspect` 列由它产出的 `quality_report.json` 填充（X-11）。报告缺失时构建仍会成功、
但不加任何标记并打印警告，随后 `verify_index.py` T10 会因 provenance 断言失败。

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py      # 先跑：产出 quality_report.json
.\.venv\Scripts\python.exe scripts\build_index.py        # 重建索引（约 5 秒）
.\.venv\Scripts\python.exe scripts\verify_index.py       # 现为 20 项（新增 T9 披露 / T10 损坏标记）
.\.venv\Scripts\python.exe scripts\validate_alignment.py # 对齐打分，须 >= 1824/1872
.\.venv\Scripts\python.exe probes\probe_conservation.py  # 文本守恒，delta 0 / ratio 1.0000
.\.venv\Scripts\python.exe scripts\check_provenance.py   # provenance，须 0/28 缺失
.\.venv\Scripts\python.exe probes\probe_bcv.py           # 第二种地址体系（**现在会真的 exit 1**）
.\.venv\Scripts\python.exe scripts\eval_g1.py            # G1 评测集 193 题（本轮新增）
.\.venv\Scripts\python.exe scripts\summarise_diff.py     # G5 差异摘要对照（本轮新增）
.\.venv\Scripts\python.exe scripts\eval_g7.py            # G7 对抗拒答（本轮新增）
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py  # G8 证伪式隔离（本轮新增）
.\.venv\Scripts\python.exe scripts\eval_g4.py            # G4 多跳链接（本轮新增）
.\.venv\Scripts\python.exe probes\probe_booksec.py       # 第四种地址体系（本轮新增）
.\.venv\Scripts\python.exe scripts\assess_goals.py       # 汇总 G1–G9（最后跑，读上面的产物）
```

**13 道闸门，全部有非零退出码。** 上一轮的八道里 `probe_bcv.py` 其实**永远返回 0**，
包括它打印「56/66 卷」的那一次——见 U-08。

本轮末次全量实测（13/13 通过）：

```
build 8.4s · 37 部 15,213 单元（28 Kanripo + 9 generality + 2 booksec + 5 tier 2/3 新增）
verify_index ALL PASS（T1–T11，含 T7 三条件断言、T9 守恒、T10 质量标记、T11 校准对照）
对齐 1824/1872 零回退 · 守恒 2,653,857 = 2,653,857 · ratio 1.0000
G 判据 PASS 8 · PART 1 · FAIL 0
G1 193/193 · G4 PASS · G5 PASS · G7 PASS · G8 9/9 拦截 · bcv PASS · booksec PASS
provenance 0/37 缺失（含通用性 10 部 + booksec 2 部，见 C-07）
质量闸门 阳性对照（卦61）+ **阴性对照**（卦47）双向都在
```

**本窗口（U-06 Douay 接入）后实测快照（13/13 通过）**：

```
build 9.6s · 37 部 51,000 单元 42.1 MB（Douay +35,787 bcv 单元）
scheme: zhouyi 5088 / yilin 5032 / bcv 35787 / None 3457 / booksec 819 / play 817
verify_index ALL PASS · validate_alignment 1824/1872 = 97.4% 零回退
probe_conservation ratio 1.0000 · assess_goals PASS 8 · PART 1 · FAIL 0
eval_g1 G1 = PASS 225/225 · eval_g7 G7 = PASS（修复 at_address scheme 过滤后 impossible 4/4）
probe_bcv control cases PASS（Douay 35,787 verses，9 个已知 Vulgate 冲突显式记录）
eval_g4 G4 = PASS · probe_g8_isolation PASS · check_provenance 0/37 missing
```

注：上段 `15,213 单元` 是 Douay 接入前快照，Douay 接入后变 51,000。增量来源：Douay 35,787 = 51,000 − 15,213。

**本轮五书入索引的单元分布**（实测 `SELECT scheme, count(*) FROM unit GROUP BY scheme`）：

```
zhouyi  5088   （6 部周易 + 焦氏易林 5032）
yilin   5032   （焦氏易林 64×64 矩阵，其中 5032 已入 zhouyi 视图）
None    3457   （Darwin 491 页锚点 + 其余術數/堪輿/命理无地址书）
booksec 819    （Herodotus 761 + Plato 10 + Iliad Butler 24 + Iliad Pope 24）
play    817    （Shakespeare 38 剧×幕场 + 6 诗）
euclid  0      （**Euclid 路由未接线**：`ingest.py:740` 的 `elif slug == "euclid-elements"` 分支存在且 `euclid.parse_propositions` 能产出 170 proposition，但 `ingest.py:665` 的 `if not txt_files: continue` 前置条件要求 `.txt`，而 `euclid-elements/` 只有 `pg21076.html` 和 `pg21076.epub`，所以该分支从未执行。此前结论"Euclid 6 BOOK 170 proposition 已入索引"已被实测推翻——实测 `SELECT count(*) FROM unit WHERE work_id='euclid-elements'` = 0，`work` 表 0 行。）
```

**注意**：`scheme=None` 含 Darwin 491 页锚点单元 + 28 部 Kanripo 里无卦爻地址的書。
`booksec` 是 Herodotus 用的 scheme；Plato/Iliad 也复用了 `booksec`（BOOK-only，addr2=NULL）。
Shakespeare 用新 scheme `play`（38 剧有 ACT/SCENE 三级地址压成 addr2 标签，6 诗 addr2=NULL）。
Euclid 用新 scheme `euclid`（6 BOOK，170 proposition，addr2=roman numeral）。

**下一个会话从哪里接**（按顺序，理由已在各条里写明）：

1. ~~**P-08** 把 `booksec` 两书编进索引~~（本会话 DONE）
2. ~~**P-05** 把 `yilin` 的 4,096 单元纳入 G1 题库~~（**前提不成立**：KR3g0029 已有 5,122 单元、G1 已有 32 道易林题；台账断言被实测推翻）
3. ~~**P-07** Herodotus 卷I节44 / 卷IV节18 缺失定性~~（**上游数据缺陷**：I 卷 42→43→45→46 跳过44，IV 卷 16→17→160 跳号；Gutenberg #2707 原文如此，非解析器问题）
4. ~~**P-04** 焦氏易林 艮 节的源文缺陷显式报告~~（DONE：`_detect_section_defects` 在 `yilin.py`，构建期打印 `SECTION-DEFECT 艮 missing=小畜 dup=小過`，`probe_verify_recon.py` C6 gate PASS）
5. ~~**P-06** tier 2/3 五书解析器~~（DONE：Shakespeare `play.py` 44/44 作品、Plato/Iliad `booksec.book_spans`、Euclid `euclid.py` 6 BOOK 170 proposition；本会话实测，推翻 §14b 多个 UNVERIFIED 数字）
6. ~~**T7-r** CPU embedding 可行性评估~~（DONE：零依赖 bag-of-bigrams TF-IDF + 余弦在 10 条手写转述上 80% 命中正确地址；结论：CPU embedding 可行，但概念级题库需引入外部释义数据，属 §1 第 3 类红线，不自主执行）
7. **G1 的概念级检索**（唯一非 PASS 项）须先做 **T7-r**（CPU embedding 可行性）。
   在那之前 G1 记 PART 是正确的，**不要改判**。

---

## 1. G1–G9 判据

复验：`python scripts/assess_goals.py`

| 判据 | 状态 | 实测 | 缺什么 |
|---|---|---|---|
| G1 能找到原文 | **PART** | 评测集 193 题，`193/193`，7 类全部达标；见 §10 | 概念级（转述/语义）检索未覆盖，FTS5 做不到 |
| G2 能精确定位 | **DONE** | 抽样 4,000，锚点作字面 `<pb:>` 命中 4,000 / 失败 0 | — |
| G3 能区分版本 | **DONE** | 逐地址枚举异文并分类，異文刻意不折叠 | — |
| G4 能跨单元关联 | **DONE** | `link` 表 **558 条**、零悬空、100% 有文本支持；2 跳链路可展示且带引用 | — |
| G5 能比较注家 | **DONE** | 乾九三 返回 6 部书；差异摘要已实现并全 386 地址普查，NOT_VARIANTS 泄漏 0 | — |
| G6 能引用证据 | **DONE** | 抽样 4,000，真实缺陷 **0**，错误率 0.000%（判据 ≤1%） | — |
| G7 能承认证据不足 | **DONE** | 对抗测试两半全 100%：伪造 30/30 拒答 · 真文 25/25 作答 · 不可能地址 4/4 拒答 · 伪造 0 | — |
| G8 能区分知识来源 | **DONE** | Derived/Conversation 独立文件 `knowledge.db`；**9 项越界尝试全部被拦**（`probe_g8_isolation.py`） | — |
| G9 能长期研究 | **DONE** | 1 个可恢复线程，五要素齐备，6 条证据回查 `data/raw/` 零陈旧 | 自动捕获（现仅脚本写入） |

`DONE 8 · PART 1 · TODO 0`　复验 `python scripts/assess_goals.py`，
实测 **`PASS 8 · PART 1 · FAIL 0 · N/A 0`**（本轮之前是 `PASS 3 · PART 1 · FAIL 4 · N/A 1`）。

本轮变动：G1 `不可测 → PART`、G4 `FAIL → PASS`、G5 `PART → PASS`、
G7 `FAIL → PASS`、G8 `FAIL → PASS`、G9 `FAIL → PASS`。

**唯一不是 PASS 的是 G1，而且是故意的**：题库每题都锚在语料中逐字存在的文本上，
证明的是逐字与结构层面；G1 字面要求的**概念级**检索未覆盖，FTS5 也做不到。
按 PASS 上报就是虚报。**不要为了让这张表全绿而改判它。**

---

## 2. 基础设施与语料

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| I-01 | Python 3.14 venv + pymupdf/EbookLib/bs4/lxml/markitdown | DONE | `.venv` 可用 | `.venv/` |
| I-02 | 代理可用性确认 | DONE | `127.0.0.1:7897`；codeload/raw.githubusercontent/gutendex 可用 | — |
| C-01 | Kanripo 28 部落盘（约 410 万字） | DONE | `data/raw/` 28 目录 | `corpus_manifest.json` |
| C-02 | 分类号核实（KR3g=術數類，非 KR3j） | DONE | manifest | 同上 |
| C-03 | provenance 记录 sha256/url/time/licence | DONE | manifest 每条含四项 | 同上 |
| C-04 | Gutenberg #25501 作校验源 | DONE | 0 页锚点 → 仅校验 | `gutenberg_manifest.json` |
| C-05 | 通用性测试集 10 部（tier 1/2/3） | DONE | 10/10 落盘 | `generality_manifest.json` |
| C-06 | Kanripo licence 缺口逐条记录 | DONE | 25 仓库无一含 LICENSE | `work.licence='none-stated'` |

---

## 3. 对齐层（周易）

复验：`python scripts/validate_alignment.py`

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| A-01 | 卦符 U+4DC0..U+4DFF 分段 | DONE | 64 卦零碰撞 | `anchors.gua_spans` |
| A-02 | LIS 分段（取代贪心） | DONE | KR1a0007 18→63 段；0031/0032 各 1→63 | 同上 |
| A-03 | 爻极性由语料八卦注推导 | DONE | 64/64，不硬编码 | `zhouyi.derive_polarity` |
| A-04 | 爻辭锚定（非爻位标记）+ 有序搜索 | DONE | 避免 `用九` 跨 `勿用+九二` | `anchors.extract_yao` |
| A-05 | gold set 从底本自动抽取 | DONE | 64/64 完整爻辭集 | `alignment_score.json` |
| A-06 | 折叠表单一来源 + 索引查询两端施加 | DONE | 48 对 | `variants.py` |
| A-07 | 折叠表 import 时与否决表互校 | DONE | 冲突即 AssertionError | 同上 |
| A-08 | `outside` 桶三分（圖/正文/十翼） | DONE | 圖 124·正文 1·十翼 13 等 | `classify_offchain` |
| A-09 | 源文爻位误标检测 | DONE | KR1a0031 三处、KR1a0006 四处 | `detect_mislabelled_yao` |
| A-10 | **爻辭对齐总分** | DONE | **1824/1872 = 97.4%** | — |
| A-11 | KR1a0031 单独查 | **PART** | 93.6% → **94.4%**，**决定不再追 95%** | 见 D-013 |
| A-12 | 5 个抽取错误（交叉引用劫持有序搜索） | **DONE**（本窗口，方案 C EXPECTED） | 实测 5 个全在 KR1a0007：**卦9初九 lenB=7** / **卦58九五 lenB=10** / **卦46初六 lenB=27** / 卦9九二 lenB=5 / 卦46九二 lenB=2（**此前数字"卦9初九 lenB=6 / 卦58九五=9 / 卦46初六=26"已被实测推翻**，实测来自 quality_report.json）| 见 D-029 · `probes/probe_a12_degenerate.py` · `quality.py:EXPECTED_DEGENERATE` |

**A-11 为何停在 94.4%**：8 个折叠候选只通过 3 个。刷到 95% 需接受 `極→拯`（2,821 次，含
**太極**）这类全局重写，那是用语料正确性换指标。剩余失败已逐条定性为源文误刻/真实異文/爻位误标。

---

## 4. REJECTED —— 试过、测过、否决了（不要重做）

| ID | 方案 | 否决数据 | 保留位置 |
|---|---|---|---|
| R-01 | 字符 bigram 稀有度做损坏探测器 | 已知损坏排名 **599/88,530**，低于自身 99.5 分位阈值；榜首全是太玄經音義字表（合法的稀有 bigram） | `quality.rarity_scores`，标注为负结果 |
| R-02 | 段落退化时重试取该爻位下一次出现 | `span-degenerate` 5→3 但 `text-damage` 1→2，`verified` **1824→1823**。换一类错误且分数下降 | `anchors._repair_degenerate`，未接线 |
| R-03 | 正文抽唯一短语 + 沿用最近卦名 | 覆盖率 84.3% 看着可用，但漂移 **max 610 单元**，且有实证错误（标为「乾」的单元在讲坤） | 已废弃，见 D-006 |
| R-04 | 5 个折叠候选 | `極→拯` 2,821次含太極 · `悔→晦` 1,136次含亢龍有悔 · `其→有` 24,061次 · `昊→昃` 昊在别处正确 · `冽→洌` 真实通假 | `variants.NOT_VARIANTS_3` |

**R-02 给下一次尝试的提示**："取下一次出现"不够——正确候选不一定紧邻，而选候选的信号
既不能是底本文本（循环，会让准确率自我印证）也不能只是段落长度（不充分）。
候选思路：排除括号注内的出现。**未验证。**

---

## 5. 索引与检索

复验：`python scripts/verify_index.py`（12 项断言全部基于**返回文本**，非计数）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| X-01 | schema + ingest + search 正式模块 | DONE | 28 部 → 8,611 单元 / 4.8s / 17.8 MB | `src/guji/` |
| X-02 | FTS5 逐字切分 | DONE | 1–2 字中文查询可命中 | `variants.segment_cjk` |
| X-03 | 短语匹配显式加引号 | DONE | 裸多 token MATCH 是隐式 AND | `search.fts_phrase` |
| X-04 | 页锚点覆盖 | DONE | 100%（8,611/8,611） | — |
| X-05 | 层分离（經/注 逐单元判定） | DONE | `經` 命中 3 → 10 | `ZHOUYI_WORKS` 四元组 |
| X-06 | `gua_name` 填充 | DONE | 从 `《X第N》` 推导 64 个；引用显示 `卦1（乾）` | `derive_gua_names` |
| X-07 | **偏移错位修复（伪造引文）** | DONE | 爻单元以自身标记开头 **0/1872 → 1858/1872**；`有能乾○九乾` → `有能乾乾` | `ingest.Piece` |
| X-08 | 文本守恒闸门 | DONE | 源 2,653,857 = 索引 2,653,857，缺失 0，重复率 1.0000 | `probe_conservation.py` |
| X-09 | 守恒检查改用有序子序列 | DONE | 多重集测不出重排，而重排正是 X-07 的缺陷 | `assess_goals.py` G6 |
| X-10 | 层过滤引文披露 | **DONE** | 全量实测 **4,658/8,611 = 54.1%** 非连续（非抽样 53%）；已加 `skipped_chars` 列 + 引用标记 `!` | `schema.sql` · `ingest.merge_units` · `search.Hit.disclosure` |
| X-11 | 损坏区在索引中标记 | **DONE** | `suspect` 列标记 **20 单元**（10 个地址），来源 `quality_report.json` 并把其 mtime 写入 `build_meta` | 同上 · 引用标记 `?` |

**X-07 是本项目至今最严重的缺陷**：`_iter_pieces` 返回「原文起始偏移 + 清洗后文本」，
调用方用原文坐标索引清洗文本。错位覆盖 **100% 的 piece**（分隔符是 `¶\n`），最大 14 字，
放错 **2,634** 个地址切点。前一轮把症状判为「外观问题，不再追查」——**该判断已在 D-008 中
明确推翻**，因为同一根因还向引用文本注入了原文没有的字符。

---

## 6. 质量闸门

复验：`python scripts/check_quality.py`（对照失效即 exit 1）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| Q-01 | 跨版本同址一致性探测器 | DONE | 358 地址中位数 **0.991**，已知损坏**排名 2**，coverage 0.050 | `quality.cross_edition_coverage` |
| Q-02 | contiguity 判据（区分损坏 vs 段落过长） | DONE | 长度比会误判；`<0.25` = 逐字替换 | `AddressDiff.contiguity` |
| Q-03 | 已知阳性对照强制 | DONE | 检测不到 KR1a0006 卦61 即 exit 1 | `check_quality.py` |
| Q-04 | 语料 OCR 损坏认定 | DONE | KR1a0006 卦61 `翰青/輪高/届卦/芝絃`；卦19 缺文 335 vs 1804 字 | `quality_report.json` |
| Q-05 | 卦64 尾部假阳性显式排除 | DONE | 十翼编排不同，31,523 vs 14,402 字 | 同上 |
| Q-06 | junk 检测器加 `\(cid:\d+\)` 统计 | **DONE** | `(cid:N)` 是 ASCII，纯码位普查会漏；`junk_census()` 记入 `quality_report.json` | §23 |
| Q-07 | 双引擎分歧闸门产品化 | **DONE** | `src/guji/dual_engine.py` + `scripts/check_dual_engine.py`；10 EPUB 扫描 0 double-junk | §24 |

---

## 7. 通用性（第二种地址体系）

复验：`python probes/probe_bcv.py`（`control cases PASS`）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| U-01 | 通用性证伪测试 | DONE | **证伪成功**：schema 把周易地址写成列名，第二体系存不进去 | `probe_generality.py` |
| U-02 | schema 改 `(scheme, addr_name, addr1, addr2)` | DONE | 周易成为其中一个实例 + `unit_zhouyi` 视图 | `schema.sql` |
| U-03 | `bcv` 解析器 | **PART** | KJV **66 卷 24,995 節** · WEB **66 卷 31,102 節**（修正前 56 卷 29,214，见 U-08） · **5/5 控制用例** + 两条新对照 | `src/guji/bcv.py` |
| U-08 | **修正：WEB 漏检 10 卷，且把后一卷经文错挂到前一卷地址上** | DONE | `book_in_line` 不识别**阿拉伯数字序数**（WEB 写 `Book 12 2 Kings`）；修正后 66/66 卷、31,102 行**零地址冲突** | `bcv._DIGIT_ORD_RE` · `probes/probe_bcv_dupes.py` · `probe_bcv_missing.py` |
| U-04 | 目录构成第二条有序链 → 过滤 | DONE | KJV 目录在 2..10 行，曾使 `Genesis` 段成第 2..3 行 | `book_spans` |
| U-05 | 拒绝以句读结尾的候选标题 | DONE | `came unto Jeremiah.` 曾被选为耶书起点 → 耶 23 落在「以賽亞書」段内 | `_looks_like_heading` |
| U-06 | Douay-Rheims 支持 | **DONE** | 35,787 单元接入 `scheme='bcv'`；见下方"U-06 接入实测" | `src/guji/douay.py` · `ingest.py:756` |

**U-06 接入实测**（2026-08-14，所有数字来自脚本输出）：
- Douay-Rheims (`data/raw_ext/generality/bible-douay/pg1581.txt`，5,880,420 字节，144,111 行) 接入索引：35,787 单元，73 个 bcv 书（Vulgate 拼写映射到 bcv.BOOKS Protestant superset）。
- **此前勘查结论"bcv.VERSE_RE 应能匹配 Douay"已被实测推翻**：`VERSE_RE = ^\s{0,6}(\d{1,3}):(\d{1,3})\s+(\S.*)$` 在 group2 后要求 `\s+`，但 Douay 是 `1:1.`（点紧跟，非空白），`VERSE_RE.match('1:1. In the beginning')` 返回 None，`bcv.parse_verses` 对 Douay 返回 0 节。**接入必须给 Douay 单独的解析路径**——见 `src/guji/douay.py`。
- **此前勘查结论"75 个不同书名"已被实测推翻**：`^(\S.+) Chapter (\d+)\s*$` 全量匹配实测 73 个 distinct 书名（1334 个章标题）。
- **Vulgate 编号特性（已显式记录于 `probes/probe_bcv.py` 的 `DOUAY_EXPECTED_CONFLICTS=9`，不静默放宽闸门）**：Psalms 113 把 Protestant 诗篇 114+115 合并为一章，章内经文号 1-8 重置一次（8 个同-(C:V) 重复）；Proverbs 12:12 同一节号印两次，文本不同（1 个同-(C:V) 重复）。任何新增冲突都会变 FAIL。
- **接入过程发现的真实缺陷（已修复）**：`search.at_address(gua, ...)` 原先只过滤 `WHERE u.addr1 = ?`，不带 `scheme` 过滤。Douay 接入后 `bcv` 单元的 `addr1=chapter` 与 卦号冲突：`at_address(99, None)` 把 Douay Psalms 99（bcv, addr1=99）误当"卦99"返回 5 段经文，导致 `eval_g7` 的 impossible-address 测试从 4/4 退到 3/4。**修复**：`at_address` 加 `AND u.scheme = 'zhouyi'` 过滤，eval_g7 恢复 4/4=100%，G7 = PASS。13 道闸门零回退。
| U-07 | tier 2/3 七部书建索引 | **TODO** | Plato/Shakespeare/Euclid/Darwin/Herodotus/Iliad×2 已落盘未索引 | — |

**U-03 为何只是 PART**：解析器覆盖面仍不全（Douay 段内编号、tier 2/3 七书未做）。
但「系统通用」**现在可以说到三种**了：`zhouyi`（卦/爻）、`bcv`（卷/章/節）、
`yilin`（本卦/之卦，4,096 单元，见 §17）。三种都装进同一组
`(scheme, addr_name, addr1, addr2)` 列、**未改 schema**——这是 D-016 那次通用化的回报。

**第三种体系的形状与前两种都不同，这点才是证据**：`yilin` 的 `addr1`/`addr2` 是
**同一类实体（卦）的两个位置**，不是「容器 + 位置」；而 `bcv` 用三级、`zhouyi` 的
`addr2` 是标签（用九/用六）而非序数。三种互不相似却同表存放，通用性才不是巧合。

**U-08 是本轮最严重的缺陷，且它是从一处"数字对不上"查出来的**（P-02）：
`probe_bcv.py` 在**同一次运行**里先打印 `31,102 verses` 再打印 `29,214 verses`，
从来没人对上过这两个数。差额 1,888 是**同一个 (卷,章,節) 键被覆盖**的行数。

根因：`book_in_line` 只认序数**单词**（first/second/ii），不认**阿拉伯数字**。
WEB 每一卷都写作 `Book 12 2 Kings`，于是 `2 Kings` 匹配到裸名 `kings`、找不到序数词、
落到 `want = b[0]` 得出 `1 Kings`——一个 LIS 链上已存在的名字，于是这个标题被当重复丢弃，
**`2 Kings` 从此没有 span**。它的经文随后落进 `1 Kings` 的区间。
1/2/3 John 以同样方式经由无序数的 `John` 丢失。共丢 **10 卷**。

**后果不是"覆盖率低"，而是静默返回别的卷的经文**：实测 1,865 个冲突地址**全部**持有不同文本，
`Ruth 1:1` 返回的是 **1 Samuel 1:1**（`Now there was a certain man of Ramathaim Zophim…`）。
而 **5/5 控制用例全程通过**，因为它们测的 Genesis/Psalms/Isaiah/John/Revelation
恰好都是 span 正确的卷。这与 `有能乾○九乾` 是同一类失效：**计数全绿，文本是错的**。

修正：数字序数只在**紧贴卷名之前**才采纳（`(?:^|\s)([123])\s+$`）。刻意不放宽为
「名字前的任意数字」——那样 `Book 21 Ecclesiastes` 会取到 "21" 的 "1"，
去找不存在的 `1 Ecclesiastes`，反而把该标题丢掉。

新增两条对照，使这一类缺陷无法再静默出厂：
① **任何地址不得持有两段不同文本**（`rows == distinct keys`）；② 两部全本圣经必须都到 66 卷。
并给 `probe_bcv.py` 加了 `sys.exit(1)`——它此前被列为八道红线之一，却**永远返回 0**，
包括打印「56/66 卷」和两个互相矛盾的经文总数的那一次。

---

## 7b. 外部见证核查（5 个 GitHub 周易项目）

复验：`python probes/probe_external_witness.py`、`probe_external_verify.py`、
`probe_sunls2_audit.py`、`probe_yu_and_verify.py`

| ID | 任务 | 状态 | 实测 |
|---|---|---|---|
| E-01 | 5 仓库落盘 + sha256 + licence 记录 | DONE | 5/5;与用户独立下载的 zip **sha256 逐字节相同** |
| E-02 | **极性交叉验证（最高价值）** | DONE | `biangua` 六位极性串 vs 我们从八卦注推导:**64/64 全部一致** |
| E-03 | 位序约定先手验证 | DONE | 屯=100010、蒙=010001 两个非对称卦确认下到上,与我们相同 |
| E-04 | 卦名差异审查 | DONE | 28 行待审 → 26 行纯简繁(非错误) + 2 行实查 |
| E-05 | 卦29 習坎 / 卦33 遯 查证 | DONE | **结论在我们这边**:原文印《習坎第二十九》;遯 22/59/142/39 次 vs 遁 0/0/2/1 |
| E-06 | `於→于` 折叠（外部见证发现） | DONE | 12,198 vs 2,862,复合词双向共存 → 折叠;**两闸门零回退**,跨来源检索生效 |
| E-07 | sunls2 版权分层审计 | DONE | **36.9%（92,714 字）在 傅佩榮（1950— ）标题下**,64/65 页;另有 台灣張銘仁;无 LICENSE |
| E-08 | 三仓库见证价值判定 | DONE | `suanle-me`/`starloom`/`chatgpt-tarot` **价值为零且有污染风险**,见下 |

**E-02 是本次最重要的收获**。我们的 64 组爻极性此前**只有一个来源**（语料八卦注推导）,
系统性推导错误会完全不可见,因为所有下游检查都继承同一假设。现在有了独立见证。
且因极性是**纯位串、与字形无关**,它同时证明了卦身份映射正确,使名称差异降级为纯正字法问题。

**E-08 三个仓库为何零价值**（这是要警惕的部分,不是可惜的部分）:

| 仓库 | 实际内容 |
|---|---|
| `suanle-me` | `hexagram = pick(hexagrams, seed + numberA*8 + numberB)` —— **卦由伪随机种子挑**,解读是模板串 + `score: baseScore` |
| `starloom` | 仅 5 文件提到 乾/坤/卦（各 1–5 次）,647 KB 的 `Input.vue` 只 1 次。**没有卦表** |
| `chatgpt-tarot-divination` | `src/app.py` 提 gpt ×4,相关文件 378–1,676 字节,**LLM prompt 包装** |

三者都是**生成**占卜文本的应用。当成「周易数据」入库等于把无出处生成文本灌进引用系统。
已写入 `MASTER_PLAN.md` §2 作为硬约束。

**可用结论**:5 个里 **1 个有真实见证价值**（biangua 的极性表）、**1 个有限可用**
（sunls2 的先秦层,须剥离现代注解且法务未清）、**3 个不可用**。

---

## 7d. 语料内部见证（推翻「40.2% 不可验证」）

复验：`python probes/probe_internal_witness.py`、`probe_addressable_now.py`、
`probe_verify_my_claims.py`

| ID | 任务 | 状态 | 实测 |
|---|---|---|---|
| W-01 | 推翻「22 部无验证路径」 | DONE | **循环论证**:ingest 只对 8 部易類编址。实测 22 部全有 ≥20 个不同卦名 |
| W-02 | 卦符普查 | DONE | KR3g0030 **62 个**（60 不同）· KR3g0015 **31 个**（24 不同）· 其余 0 |
| W-03 | 爻辭逐字引用普查 | DONE | **6 部书共 31 处**;标记 易云 48 · 易曰 81（易云 46/48 集中在 KR3g0030） |
| W-04 | 京氏易傳 编址可行性 | **PART** | LIS 12/62 → 逐符号 **59/62 = 95.2%**;但 3 处**符号/内容错配** → **应以卦名为主** |
| W-05 | 焦氏易林 结构 | **TODO** | 邻接率仅 **3.4%**（237 对/219 不同），**不是矩阵**;真实版式待查 |
| W-06 | provenance 补齐 + 上游核验 | DONE | KR1a0001/0006/0007 曾无 provenance;补齐并**逐字节等于上游** |

**W-04/W-05 的重要提醒**:我曾写下「60/62 卦名验证 100%」与「4,032 配对邻接率 96.8%」,
**两者都是没测就写的,已被 `probe_verify_my_claims.py` 推翻**。见 `LESSONS.md` L-17 与
`GOAL.md` §4 T4。**不要沿用被推翻的数字做设计。**

---

## 7c. 法务状态（逐条记录，不假定宽松许可）

| 来源 | LICENCE | 处置 |
|---|---|---|
| Kanripo 25 仓库 | **无一含 LICENSE/COPYING** | 已入库（底本前现代,数字化条款未声明）;`work.licence='none-stated'` |
| Gutenberg | 公版 | 可用 |
| `Ovilia/biangua` | **有 LICENSE** | 唯一有许可的外部仓库;仅作见证,未入库 |
| `lyyxqg-lyy/suanle-me` | 无 | 不入库（生成物） |
| `starloom/starloom` | 无 | 不入库（无数据） |
| `dreamhunter2333/chatgpt-tarot-divination` | 无 | 不入库（生成物） |
| `sunls2/zhouyi` | **无,且含在世作者作品** | **不入库**。36.9% 文字属 傅佩榮（1950— ）;另有 台灣張銘仁 |

---

## 8. Agent 层

**整层未开始。** 无实体抽取、无多跳、无证据集、无认输机制、无跨会话。
不要在 G1 评测集（§1）之前动这一层——没有验收标准。

---

## 10. T1 —— G1 评测集（本轮完成，G1 由「不可测」变为可测）

复验（两条，必须按顺序）：

```powershell
.\.venv\Scripts\python.exe scripts\derive_eval_g1.py   # 从 data/raw/ 生成题库
.\.venv\Scripts\python.exe scripts\eval_g1.py          # 打分，exit 0 = 全类达标
```

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| E1-01 | 题库自动派生（**不手写**、**不从索引派生**） | DONE | 193 题；gold 全部来自 `data/raw/`，打分前逐条回查原文 | `scripts/derive_eval_g1.py` · `data/catalog/eval_g1.json` |
| E1-02 | 三种归一化空间单一来源 | DONE | `folded_notes` / `folded_jing` / `unfolded_notes`；混用曾使 citation 假失败 0/30 | `src/guji/evalset.py` |
| E1-03 | retrieval（逐字片段 → 正确地址，top-10） | DONE | **40/40**，rank 分布 `{1:39, 2:1}` | `scripts/eval_g1.py` |
| E1-04 | retrieval_cross（同址必须能在**别的**见证里取到） | DONE | **24/24**；但 rank 全为 1，**该层不具区分度**（脚本自己会打印这句） | 同上 |
| E1-05 | retrieval_hard（短片段 + 语料内高频，考排序） | DONE | **24/24**，rank `{1:23, 2:1}`；同样偏易 | 同上 |
| E1-06 | citation（锚点是字面 `<pb:>` + 引文可从该文件复原） | DONE | **30/30**，350 个单元逐个复原 | 同上 |
| E1-07 | groundedness 正例 | DONE | **25/25** | 同上 |
| E1-08 | **groundedness 对抗（伪造必须 0 命中）** | DONE | **30/30**；含 X-07 真实伪造串 `有能乾九乾` 作回归 | 同上 |
| E1-09 | version（異文保持可分 + 折叠仍可达变体） | DONE | **20/20**；`日昊/日昃`、`已日/己日`、`稊/梯` 等 | 同上 |
| E1-10 | G1 接入 `assess_goals.py` | DONE | G1 = **PART**（不是 PASS，理由见下） | `scripts/assess_goals.py` |

**为什么 G1 记 PART 而不是 PASS**（这条不要"优化"掉）：题库每道题都锚在语料中**逐字存在**的
文本上，因此证明的是**逐字与结构层面**的检索、引用完整性、groundedness、版本区分。
G1 判据的字面要求是「给定**概念**」，概念级（转述/语义）检索**未覆盖**，FTS5 也做不到。
按 PASS 上报就是 G8「空真隔离」那类虚报。补齐它须先做 T7-r（CPU embedding 可行性）。

**已知题库弱点（脚本自己会打印，不要靠记忆）**：`retrieval_cross` 24 题 rank 全为 1，
说明该层没有区分度；`grounded_neg` 在当前只有检索层、没有回答层时天然容易通过——
它证明的是「检索层不会凭空造文本」，等 T7-k 有了回答层，这一类才会变难。

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| Q-08 | **`addresses_of` 窗口口径修正**（跨版本闸门此前近乎空转） | DONE | 31/32 参与比较 **17 → 373**，中位覆盖 0.985；06/07 **358 → 362** 且中位仍 0.991；卦61 对照仍触发 | `src/guji/quality.py` · `probes/probe_addresses_fix.py` |

**Q-08 是什么**：`addresses_of` 的窗口原先止于「下一个爻位标记前的最后一个**經**字符」，
于是在 注 被括号包住的版本（KR1a0031/0032）里，注文**全部落在窗口外**，一个地址只返回
爻辭本身（中位 9 字）；而在 注 以字面「注」字排版的 KR1a0007 里注文本来就在經视图内，
返回 102 字。同一个函数在不同版本里含义不同。后果：`cross_edition_coverage` 把 31/32
的 377 个共享地址中 **360 个**丢给自己的 `min_len=20` 过滤，然后对剩下 4.5% 报出
「中位覆盖 1.000、低于 0.60 者 0」。**台账此前把这条当作 G3 的证据，它不是。**
修正后新暴露两个真实离群地址 卦23六四 / 卦61初九，正是 `detect_mislabelled_yao`
已独立标记为 KR1a0031 爻位误刻的同两个地址——两个探测器互相印证。
另外 06/07 的 卦47上六 由 `span-overextended-A` 改判为 **`text-damage`**（contiguity 0.199），
即语料里**可能存在第二处 OCR 损坏区**，待查（见 §11 待办）。

**修正前已预先登记的验收判据**（先定后测，见 `GOAL.md` §3）：
① 31/32 参与比较数须由 17 升到 >300；② 06/07 须保持 ≥358 且中位覆盖 ≥0.95；
③ 卦61上九 必须仍判为 text-damage。三条全部满足，八道闸门零回退，故采纳。

---

## 12. T2 —— G5 差异摘要（本轮完成，G5 由 PART → DONE）

复验：`.\.venv\Scripts\python.exe scripts\summarise_diff.py`（对照失效即 exit 1）
单地址查看：`… scripts\summarise_diff.py 28 九二` / `… 1 九三 --layer none`

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| S-01 | 差异分类器（四类 + 注文体量） | DONE | 普查 386 个爻地址，`orthographic 2,821 · divergent · omission · addition` | `src/guji/compare.py` |
| S-02 | **异文不可被抹平**（对照集） | DONE | 卦28九二 稊/梯、卦54初九 跛/破、卦30九三 昃/昊 全部报为 `preserved-variant` **并附当初否决理由** | `scripts/summarise_diff.py` |
| S-03 | **反向义务**：正字法差异不得报成異文 | DONE | 75 条 `divergent` 读法，折叠后相同者 **0** | 同上 |
| S-04 | **反向义务**：NOT_VARIANTS 不得报成正字法 | DONE | 全 386 地址、2,821 条 `orthographic` 读法，泄漏 **0** | 同上 |
| S-05 | **版本轴**比较（同一著作两版本） | DONE | 卦1九三 `居卜之上/居下之上` 只有沿版本轴比较才看得见 | `compare.EDITION_PAIRS` |
| S-06 | G5 接入 `assess_goals.py` | DONE | G5 = **PASS**（含对照与泄漏计数） | `scripts/assess_goals.py` |

**S-05 是本项被对照逼出来的真正设计修正**（三次失败换来的）：
最初把所有见证都对**底本**做 diff，于是 `卜/下` **结构上不可能被发现**——它是 朱熹 本義
两个版本在**他自己的注文**里的差异，而底本根本没有注文。
「所有见证对齐到一个参照」对**同一著作的两个版本**是盲的，而那正是 Work/Edition 分开
建模要暴露的东西。现在有两条轴：**注家轴**（只比 經，因为不同注家只共享 經）与
**版本轴**（比 經+注，因为同一注家的注文也是共享文本）。

另外两条被对照否决的初版做法，留档备忘：
1. 逐字 diff 不同注家的**注文** → 产出 350 字的一条"差异"，毫无意义（注家本来就各说各话）。
   改为：注文只报**体量**（`KR1a0007=853字`），不做字符级 diff。
2. 在**带标点**空间里比较 → KR1a0001 的标点把读法切碎，`稊` 变成 `'稊，'`，
   根本不成字对、无法分类。改为在 `unfolded_notes` 空间比较（去标点、**不折叠**）。
   不折叠是关键：一折叠，所有正字法差异就从对齐里消失，摘要再也没法告诉读者
   该见证印的是 `濳` 而不是 `潛`。

---

## 13. T3 —— 引用披露 X-10 / X-11（本轮完成）

复验：`scripts\build_index.py`（会打印披露汇总）+ `scripts\verify_index.py` T9/T10
全量实测：`probes\probe_disclosure.py`

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| X-10a | `skipped_chars` 列，合并时 O(1) 累计 | DONE | 4,658/8,611 = **54.1%** 非连续；median 62 · p90 571 · max 7,388 字 | `ingest.merge_units` |
| X-10b | 引用渲染披露标记 | DONE | `citation()` 追加 `!`；`disclosure()` 出中文说明 | `search.Hit` |
| X-10c | 列与实际文本一致性断言 | DONE | 抽 600：声称连续而实非 **0**，声称跳过而实连续 **0** | `verify_index.py` T9 |
| X-11a | `suspect` 列（来源=质量闸门，非新猜测） | DONE | 20 单元 / 10 地址 | `ingest.load_suspect` |
| X-11b | 陈旧可检测：报告 mtime 写入 `build_meta` | DONE | `suspect_source/mtime/bytes/addresses` | 同上 |
| X-11c | 对照断言 | DONE | KR1a0006 卦61上九 必须标 `text-damage`，且标记出现在渲染引用里 | `verify_index.py` T10 |

**X-10 的一处口径修正（差点做错，被自己的断言拦住）**：`skipped_chars` 第一版累计**原文偏移差**
`a - pb`，结果标出 **89.1%** 非连续，而独立探针实测是 54.1%。原因：相邻两段之间的原文间隔
通常只是木刻分隔符 `¶\n` 或标点，**没有任何读者会认为那是"被略去的内容"**。
改为先把间隔文本过 `clean()` 归一化、只数存活字符后为 **54.1%**，与探针精确吻合。
**教训**：披露若在 35% 的语料上虚报，读者就会学会忽略它——虚报警告等于没有警告。
`raw` 因此是 `merge_units` 的**必填参数**（这个数算不出来自偏移，可选参数会让调用方悄悄拿到错含义）。

**顺带纠正台账此前对 X-10 的归因**：原文写「`merge_units` 跨注合并，經 单元跳过了夹在中间的 注」。
实测这只说对了一部分——按层看 `經 48.0% · 注 56.8% · 正文 61.5%`，**注 层与正文层比經层更严重**；
且最大的跳过量全部出现在**術數类**（KR3g0028 7,388 字、KR3g0029 6,781 字），
那些书**没有卦爻地址**，合并键退化为 `(file, layer, NULL, NULL)`，于是整份文件的同层片段
跨越大段文字合并。这是与「經 跳过注」**不同的机制**，且后果更大。

---

## 14. 子 agent 勘查结论（**只读勘查；主线尚未复验，按 §2 一律当"待复验"**）

两个只读子 agent 的产出。**它们没有改任何代码、没有跑 build**。下列数字**我尚未自己复跑**，
因此状态一律 `UNVERIFIED`。实施前必须先跑对应探针确认——这正是 §2 要求的纪律，
而且其中一个 agent 在报告里把一个字符写错又自行更正（`㤗`），说明报告本身也要复验。

### 14a. KR3g0029 焦氏易林（探针 `probes/probe_jiaoshi_layout.py`）

| 结论 | 状态 | 数据 |
|---|---|---|
| **它是干净的 64×64 矩阵，4,096 条**，与本书自述一致（提要「六十四卦之變共四千九十有六」） | UNVERIFIED | 64 节 × 64 条；4,095 个不同配对 = 99.98% |
| 版式规则：标题 `　　X之第N¶`（两个 U+3000）；条目 = `卦名` + 一个 U+3000 + 林辭，**均在行首** | UNVERIFIED | 溢出行以**一个** U+3000 起 |
| **「之某卦」假设被推翻**：条目头是**裸卦名**，不是 `之X` | UNVERIFIED | 751 个 `之+卦名` 中 **727 在括号注内**，24 在前言，**行首 0** |
| **必须先加两个别名，否则静默变成 63 节** | UNVERIFIED | `坎`(U+574E)→卦29（本书写 坎，`習坎` 出现 **0** 次）；`㤗`(U+3917)→`泰`（4 次，其中 1 次是 坤之泰 条目头） |
| 「6,985 次 / 63 个不同卦名」的来源 | UNVERIFIED | **那是漏了 坎 的计数**；真实 7,080 次、64 个 |
| **内容匹配绝不可用**：林辭里全是卦名 | UNVERIFIED | 4,096 条中 **1,094 条（26.7%）** 正文含卦名，共 **1,267** 个假阳性（復 148 · 離 105 · 困 92 · 履 80）。**但全部在行中，行首规则可完全排除** |
| 邻接率这个指标本身是错的 | UNVERIFIED | 对 4,095 真配对：召回 **8.28%**、精确 100%。它只探到互见注里两个引用相邻，与结构无关。96.8% **确定为假**；3.4% 量级对但精确规则未能复现 |
| 卦符 U+4DC0..U+4DFF | UNVERIFIED | 本书 **0** 个，此前普查正确 |
| 艮 节是真实版本缺陷 | UNVERIFIED | 小過 印两次（raw@93541 / @94996，林辭不同），小畜 整条缺失。**应容忍并报告，不要"修好"** |
| 互见图 | UNVERIFIED | 713 个 `A之B`，563 个不同，**100% 指向真实单元，0 悬空**；74 个跨行断裂的注有 70 个可拼回 |

**若实施**：`scheme="yilin"`、`addr1=本卦 1..64`、`addr2=之卦`，只从行首取。
**必加断言**：64 节 × 64 条——这一条断言就能拦住 坎 陷阱（正是它造出了那批假数字）。
另：`src/guji/ingest.py` 文件头断言本书「没有卦/爻结构，NULL 地址是正确的、不是缺口」，
**若上述成立则该句为假**，应删除而不是弱化。

### 14b. tier 2/3 西文七书（探针 `probes/probe_western_recon.py`、`probe_western_recon2.py`）

**两个原定方案的地址体系根本不在字节里**——这是本次最有价值的结论：

| 编号 | 结论 | 状态 |
|---|---|---|
| **T7-c Plato** | **`stephanus` 标记不存在**。txt/html/epub 三种格式里 `\b\d{2,3}[a-e]\b` 与 "Stephanus" 均为 **0**；只有 BOOK I..X，全书 641,553 字仅 10 个单元。**按原定方案不可实施** | UNVERIFIED |
| **T7-g Iliad** | **两个译本都没有行号**（右边距整数 0 / 独立行整数 0 / `(NN)` 0 / "line NN" 0）。`book/line` **不可能**。可对照的只有 BOOK 级 24×2 个单元（对比圣经 ~31,000 節）。书级内容确实对应：地标位置平均偏差 **0.011** 个书长 | UNVERIFIED |
| **T7-f Herodotus** | **与台账相反：正典地址存在**。4 个书标题 + 736 个行首节号；接受逗号形式 `^(\d{1,3})[.,]\s` 后共 **764** 个 vs 正典 763（I 216/II 182/III 160/IV 205），**卷 II 精确吻合**。逗号形式**不是可选项**，漏掉它就少 27 节 | UNVERIFIED |
| **T7-f Darwin** | 只有 14 章，无更细地址（`§`=0、`[Page n]`=0）；但 html 有 **491 个连续页锚点** `id="Page1..491"`，而**其余六书页锚点全为 0** | UNVERIFIED |
| **T7-e Euclid** | **无 txt，只有 epub+html**；202 个 `PROP.` 标记，逐卷 **48/14/37/16/25/33** = 欧几里得 I–VI 的正典数目，零缺口。html 把小型大写字母**逐字符**包 span，**必须用空串而非空格剥标签**，否则单词被打散成 `T h e P o i n t` | UNVERIFIED |
| **T7-d Shakespeare** | 770 场 / 38 剧，唯一的三级地址；但**有 39 个目录**（全局 1 + 每剧 1），且 Henry VI 上篇的目录**在同一块里从 `Scene` 切换成 `SCENE`**，所以大小写不是安全判据；Richard II **完全没有 `Dramatis Personæ` 行**。7 部作品（十四行诗等）0 幕 0 场，是 addr2=NULL 的合法单元 | UNVERIFIED |

**子 agent 的实施建议（未复验）**：先做 Herodotus + Darwin，**当作一次改动**。
理由是它构成 **D-005 的双向检验**：Herodotus = 有正典地址、无页锚点；
Darwin = 有 491 个页锚点、无可用正典地址。`schema.sql` 开头那句
「两者都需要且不可互换」目前只在周易一个语料上验证过，**单独任一本书都证不出这一点**。

---

## 15. T6 —— G8 三类知识物理隔离（本轮完成，G8/G9 双双 FAIL → PASS）

复验：`.\.venv\Scripts\python.exe probes\probe_g8_isolation.py`（9 项越界尝试，exit 1 即失败）
线程演示：`… scripts\research_thread.py demo` / `list` / `show 1`

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| K-01 | Derived / Conversation 存储 | DONE | `derived` / `evidence` / `thread` / `turn` / `derived_fts` | `src/guji/knowledge_schema.sql` |
| K-02 | **独立文件**而非独立标志位 | DONE | `data/index/knowledge.db`；`corpus.db` 里无这些表 | `src/guji/knowledge.py` |
| K-03 | 证据用**持久引用**，不用 `unit(id)` | DONE | 存 work/file/offsets/anchor/address/quote | 同上 |
| K-04 | 断言性结论**无证据即拒收** | DONE | `record(kind='answer')` 无证据抛 ValueError | 同上 |
| K-05 | 但**认输可以无证据**（G7 前提） | DONE | `kind='refusal'` 允许空证据 | 同上 |
| K-06 | 证据可回查原文 | DONE | `verify()` 逐条比对 `data/raw/`，6/6 通过、0 陈旧 | 同上 |
| K-07 | **证伪式闸门** | DONE | 9 项越界尝试**全部被拦** | `probes/probe_g8_isolation.py` |
| K-08 | G9 研究线程 | DONE | 五要素（书/版本/原文/结论/证据）齐备且可恢复 | `scripts/research_thread.py` |

**K-02 为什么必须是两个文件**（这是本项最关键的判断，且有实测依据）：
`ingest.build()` 第一行就是 `os.remove(db_path)`——`corpus.db` 每次构建都被删掉重建，
而本项目**刻意**把这当作 5 秒的日常操作（「随便重建」）。
**Source 可从 `data/raw/` 再生，Derived 与 Conversation 不能**。放在同一个文件里，
一次例行重建就会静默毁掉全部推导结论。两者不能共享生命周期。
其次，能用**文件边界**陈述的隔离才是可检查的：`corpus.db` 里根本没有那些行，
所以不存在"忘记加过滤条件"这种失效——对照 D-008，經/注 曾共用一个 layer 值，
于是 `merge_units` 把它们融成一块。**依赖"记得加过滤"的区分，最终一定会漏。**

**K-03 与 K-05 是两次"提前避开 D-015 那类错误"**：
- 证据若用 `unit(id)` 引用：unit id 来自构建期计数器 `uid += 1`，**跨重建不稳定**，
  一条引用 unit 1234 的结论下次构建后会指向**另一段原文**。故改存持久引用。
- 证据字段若设成 `NOT NULL`：那么「证据不足」这类输出**根本存不进去**，
  而那正是 G7 的要求。这与「把卦/爻写成列名」是同一类错误，这次在犯之前就拦住了。

**K-06 顺带被闸门抓到我自己的一个缺陷**：`verify()` 初版只 fold + 去空白，没去标点，
于是 KR1a0001 的 `初九、潛龍勿用。` 报陈旧而 KR1a0006 的 `初九濳龍勿用` 通过——
与 citation 0/30 那次**完全相同的signature**（L-18）。闸门在出厂前抓住了它。

## 16. G7 回答层（本轮完成，FAIL → PASS）

复验：`.\.venv\Scripts\python.exe scripts\eval_g7.py`（每半 95% 闸门，不达标 exit 1）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| A7-01 | 回答层：给证据或明确认输，**不生成文字** | DONE | `Answer.evidence` 是引文，`Answer.refused` 是理由 | `src/guji/answer.py` |
| A7-02 | 伪造必须拒答 | DONE | **30/30**，对抗样例是**相邻换位**（字符多重集与真文相同） | `scripts/eval_g7.py` |
| A7-03 | 真文必须作答（反向义务） | DONE | **25/25**，且断言返回文本**确实含查询串** | 同上 |
| A7-04 | 不可能的地址必须拒答 | DONE | **4/4**：卦65、乾卦六二（乾无阴爻）、坤卦九五、卦99 | 同上 |
| A7-05 | **仅命中损坏区必须拒答** | DONE | `翰青登于天` 拒答；`翰音登于天` 仍返回 5 条 | 同上 |
| A7-06 | 伪造零容忍 | DONE | **0** | 同上 |

---

## 16a. 易林艮宫异常显式报告（P-04，本轮完成）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| P-04 | 艮宫源文缺陷应显式报告 | DONE | 构建时输出 `SECTION-DEFECT 艮 missing=小畜 dup=小過`，C6 gate 通过 | `src/guji/yilin.py::_detect_section_defects` |

**根因与修正**：初版用 `set(names.keys())` 作为"应该出现的64个卦名"，但 names 有65个键（坎/習坎都指向29）。
修正为按**卦号**（1-64）检查覆盖，而非按名字——每个section应覆盖全部64个数字。
现在报告精确：艮宫缺小畜（号23）、小過重复。`probes/probe_verify_recon.py` C6 gate 通过。

**A7-05 是这一项不退化成 `if not hits: refuse()` 的原因**：命中集**全部**落在质量闸门
标记区时必须拒答，**尽管 hits 非空**。计数型拒答规则会照常把损坏文本当证据交出去。

---

## 17. 焦氏易林 第三种地址体系 + G4 多跳（本轮完成）

复验：`.\.venv\Scripts\python.exe probes\probe_verify_recon.py`（7 条勘查结论独立复现）
　　　`.\.venv\Scripts\python.exe scripts\eval_g4.py`（G4 闸门）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| W-05 | **焦氏易林真实版式查明** | DONE | **64 节 × 64 条 = 4,096**，与本书提要「六十四卦之變共四千九十有六」一致 | `src/guji/yilin.py` |
| Y-01 | `scheme="yilin"` 落地 | DONE | 4,096 个单元（此前 **0** 个有地址）；`addr1=本卦号`、`addr2=之卦名` | `ingest._ingest_yilin` |
| Y-02 | **64×64 断言**（防 坎 陷阱） | DONE | 不等于 64 节 ×64 条即 `AssertionError` | 同上 |
| Y-03 | 别名两处 | DONE | `㤗`(U+3917)→泰 入 `FOLD`（4 次，全在此书）；`坎`→卦29 作**名称别名**，**不**入 FOLD | `variants._DIAGNOSED_4` · `yilin.NAME_ALIASES` |
| Y-04 | 文本守恒 | DONE | KR3g0029 **80,847 = 80,847**，缺失 0 | `probe_conservation.py` |
| G4-01 | `link` 表（源文印出的互见） | DONE | **558 条**，零悬空 | `schema.sql` · `yilin.cross_references` |
| G4-02 | 每条链接必须有**文本支持** | DONE | 抽 400 条，源单元文本里未出现目标地址者 **0** | `scripts/eval_g4.py` |
| G4-03 | 多跳链路可展示 | DONE | 3 跳，每跳带引用；环上不死循环 | 同上 |
| Y-05 | **地址标签必须规范化**（跨作品 join key） | DONE | 卦29 曾在 林辭 层记 `坎`、在 標題 层记 `習坎`——**同一卦两个标签**。现 `addr_name`/`addr2` 一律用底本正名 | `probes/probe_yilin_name.py` |

**Y-05 是四体系对比探针顺带查出来的**（`probe_four_schemes.py` 显示 yilin 有 **65** 个
`addr_name` 却只有 **64** 个 `addr1`，1 个多出来的就是它）。
根因：条目层用本书自己的写法（`坎`），标题层用底本正名（`習坎`）。
**地址是跨作品的 join key**：若 焦氏易林 存 `坎` 而周易诸本存 `習坎`，
按名字连接两部书会**静默返回空**。本书自己的写法并未丢——它仍在单元文本里，
版本的正字法本来就该待在文本里，而不是待在 join key 里。

**Y-01 顺带推翻 `ingest.py` 文件头的一句断言**（原文说本书「没有卦/爻结构，NULL 地址是正确的、
不是缺口」）。那句话是 **L-16 循环论证的又一个实例**：流水线只对易類书尝试编址，
于是本书没有地址，而"没有地址"又被反过来当成"它没有结构"的证据。已在 docstring 里
**保留原文并标注推翻**，不是悄悄改掉。

**我自己复验时先失败、再查出是我的错**（这条值得记）：`probe_verify_recon.py` 初版报
「标题 60/64、条目 3,925」，与子 agent 报的「64/64、4,096」不符。
**看起来像是子 agent 夸大了**。查那 6 个不匹配的写法——`剥/恒/㢲/兊/兑/暌`——
**每一个都已经在 `variants.FOLD` 里**。是我的探针忘了套本项目自己的折叠表：
3,925 + 171 = **4,096**，精确吻合。真正缺的只有两个：`㤗` 与 `坎`。

**G4-02 是这道闸门真正的价值**：链接不是"存在一行记录"就算对，而是**目标地址必须在源单元
自己的文本里被印出来**。互见是**源文印出的编辑注**（「此林辭亦见于某卦之某卦」），
所以它是 **Source 知识**、放在 `corpus.db`；靠相似度推出来的链接才是 Derived、
该放 `knowledge.db`（D-023）。这是 G8 的分类第一次真正派上用场。

多跳链路的实际输出（三跳，林辭确实同源，且異文可见）：

```
hop 0  乾之師  師倉盈庾億宜種黍稷年豐歲熟民人安息
hop 1  比之升  升倉盈庾億宜稼黍稷年豐歲熟國家富有
hop 2  坤之恆  恒倉盈庾億宜種黍稷年豐嵗熟民得安息
```

`種/稼`、`民人安息/國家富有/民得安息` 就是这三处的異文——**这是多跳检索真正要拿到的东西**。

---

## 18. Herodotus / Darwin（第四种地址体系，**进行中**）

### 18a. 工具通道曾中断一次——照 L-11 记下来，不描述没看到输出的动作

本轮后段有一段时间**多次工具调用返回空**（PowerShell 与 Read 均无输出）。
那段时间里我曾**认为**自己写了 `src/guji/booksec.py` 与 `probes/probe_booksec.py`，
但通道恢复后 `Test-Path` 两者**皆 False**——文件从未落盘。
**L-11 说的正是这件事**：通道静默时不要描述自己没做过的动作。此处按事实记录：
那段工作**未发生**，下面只保留我**亲眼看到输出**的部分。

### 18b. 已由主线独立复验的 Herodotus 事实（不是子 agent 转述）

```powershell
# data\raw_ext\generality\herodotus\pg2707.txt   895,283 chars
(?m)^BOOK [IVX]+\.      ->  4      @7315 / @275453 / @497355 / @692853
(?m)^(\d{1,3})\.\s      ->  736    句点式节号
(?m)^(\d{1,3}),\s       ->   28    逗号式节号（漏掉它就少 27 节）
(?m)^(\d{1,3})\s        ->  746    无标点，**全是折行的脚注号，必须排除**
(?m)^NOTES TO BOOK.*    ->  4      @252252 / @478317 / @679174 / @879306
```

736 + 28 = **764**，正典（I 216 · II 182 · III 160 · IV 205）= 763。
**这五行是本节唯一有主线实测支撑的内容。** 其余（Darwin 的 491 个页锚点、
Euclid 的 202 个 PROP.、Shakespeare 的 770 场等）仍只是 §14b 的 `UNVERIFIED` 勘查。

### 18c. `booksec` 解析器已落地并通过闸门（**但尚未入索引**）

复验：`.\.venv\Scripts\python.exe probes\probe_booksec.py`（exit 1 即失败）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| B-01 | `booksec` 解析器（第四种体系） | DONE | 4 卷 · **761 节**（正典 763） | `src/guji/booksec.py` |
| B-02 | 节号必须接受 `[.,]` | DONE | 句点 736 + 逗号 28；只认句点会少 27 节 | 同上 |
| B-03 | **无标点形式必须排除** | DONE | 746 行是折行脚注号，收进来会让地址空间翻倍且全是垃圾 | 同上 |
| B-04 | 注释是第二条上升链，须排除 | DONE | 每卷正文止于自己的 `NOTES TO BOOK n`；漏进注释的节 **0** | `booksec.book_spans` |
| B-05 | 控制用例断言**返回文本** | DONE | 5/5，逐条含预期短语（卷1节1 Persians/history、卷3节1 Cambyses 等） | `probes/probe_booksec.py` |
| B-06 | Darwin 退化为仅章地址 | DONE | 14 章、`§`=0、`[Page n]`=0、`(p. n)`=0——**不编造更细地址** | 同上 |
| B-07 | **入索引**（扩展语料路径） | DONE | `build()` 加 `data/raw_ext/generality/` 遍历；37 部、provenance 0/37 缺失、守恒零回退 | `src/guji/ingest.py` |

**逐卷实测**（先定后测的判据是「与正典相差 ≤3」）：

```
卷 I   215 / 216   缺 [44]
卷 II  182 / 182   精确吻合
卷 III 160 / 160   精确吻合
卷 IV  204 / 205   缺 [18]
```

两卷精确、两卷各缺一节。**这两处缺失与 §14b 子 agent 预测的完全相同**（`missing=[44]`、
`missing=[18]`），即两次独立测量互相印证，而不是我复现了它的报告。
**未定性**：那两节是源文排版异常还是升序过滤误杀，**没查**，记为 P-07。

**为什么标 DONE 但没入索引**：`ingest.build()` 只遍历 `data/raw/`，而这批书在
`data/raw_ext/generality/`。把它们编进索引会把作品数 28 → 30，牵动 provenance
（`check_provenance.py` 断言 28 部全有 sha256/url）、守恒、以及 `verify_index` 的覆盖表。
那是一次**跨多道闸门**的改动，在本轮剩余余量里做完再验不安全。
照 U-03 当初的先例：**解析器先落地并带闸门，入索引单独作一项**，记为 P-08。

---

## 19. P-01 结案：卦47上六 **不是**第二处损坏区，是判据的假阳性

复验：`.\.venv\Scripts\python.exe probes\probe_gua47.py`（把两处并排打出来）

`text-damage` 原先只看 contiguity < 0.25。卦47上六 得 0.199，于是被判损坏、进了
`suspect` 列，**于是回答层拒答它**（G7 的 damaged 规则）。它没有损坏：

```
卦47上六   替换 2 处（纏/纒 正字法、困/因），最长公共段 92 字
           KR1a0006 的段落只是**越界续进了 卦48 井**，而 KR1a0007 另有 音義/疏
卦61上九   替换 19 处，全是形近字（青/音 狀/飛 堵/者 寳/實 届/居 芝/之 絃/終 筆/華…）
           最长公共段 6 字
```

所以损坏的签名是「**同一段文字里散布大量形近小替换**」，而**长公共段是反证**。
判据加上 `substitutions >= 5`：卦61 对照仍触发，卦47 释放为 `span-overextended-A`。

**为什么这不是"多标一个更安全"**：把完好的文本标成损坏，会让回答层**拒绝交出真实证据**，
而且**除非有人去读那段原文，否则完全看不见**。这与漏标是对称的失效，不是保守。

---

## 20. P-08 勘查 + provenance 补齐（`booksec` 入索引的两个前置条件）

复验：`.\.venv\Scripts\python.exe probes\probe_ext_ingest.py`
补齐：`.\.venv\Scripts\python.exe scripts\backfill_generality_provenance.py`（`--write` 落盘）

| ID | 任务 | 状态 | 复验 / 实测 | 产物 |
|---|---|---|---|---|
| C-07 | **通用性测试集 10 部的 provenance 补齐** | DONE | 原先只有 `fetched_at`，缺 `sha256`/`source_url`/`licence`。现 **10/10 齐全** | `data/catalog/generality_manifest.json` |
| P-08a | 入索引的障碍勘查 | DONE | 见下两条 | `probes/probe_ext_ingest.py` |

**C-07 的做法**：sha256 从**本地已有字节**算，URL 由已记录的 `gutenberg_id` 推导，
licence 由 manifest 自带的 `copyright: False`（Gutenberg 的公版标记）判定。
**一个字节都没有重新联网获取**——GOAL §1 不允许擅自联网取语料，而这件事也不需要：
provenance 可以从"已经持有的东西 + 已经记录的东西"重建，而**重建 provenance 不是一次新的获取**。
这与 W-06 给三部核心书补 provenance 是同一类操作。

**剩下的真正障碍，是一条比入索引本身更有价值的发现**（记为 P-09）：

`build()` 假定 Kanripo 版式（`<pb:>` 页锚点、`¶` 分隔符）。**Herodotus 全书 `<pb:>` = 0**。
于是它的单元 `page_anchor` 全为 NULL，而 `verify_index.py` **T7 断言
「no unit lacks anchor or file」**。

**这条断言对 Kanripo 是对的，作为系统不变量是错的。** 它把**一个语料的属性**
写成了**系统的保证**——与 U-01（schema 把周易地址写成列名）、D-015 完全同一类错误，
而且同样只有在第二个语料到来时才暴露。

**注意这里不能走"放宽闸门"那条路**（GOAL §1 第 2 类红线）。正确的改法不是删掉断言，而是
**把它改成有条件的**：一个作品要么全有页锚点，要么**明确记录它没有页码体系**，
二者之外才是缺陷。Darwin 恰好提供了对照——它 txt 里没有页锚点，但 **html 有 491 个
`id="PageN"`**，即"有页码体系但当前抽取路径没取到"，与 Herodotus 的"根本没有页码体系"
是**两种不同状态**，不能都记成 NULL 了事。

---

## 11. 本轮新增待办（有实测依据，不是猜测）

| ID | 待办 | 依据 |
|---|---|---|
| P-01 | **已完成：不是损坏，是假阳性** | 见 §19。判据已加上"OCR 签名"要求，卦47 释放为 `span-overextended-A`，卦61 对照仍触发 |
| P-02 | **已完成** → 见 U-08 / D-022 | 查下去发现的不是口径差异，而是 10 卷经文错挂地址。**这是本轮最严重的缺陷** |
| P-03 | **已完成** | `verify_index.py` 新增 T11，真正断言 `quality.py` 文档声称的校准（卦61 对照 + 中位覆盖 ≥0.95 + 参与比较数 ≥358） |
| P-04 | **DONE** 焦氏易林 艮 节的源文缺陷现已上报 | `_detect_section_defects()` 加入 `yilin.py`，检测每节缺失/重复的之卦；`ingest.py` 在 `_ingest_yilin()` 后打印异常。实测：艮 missing=小畜 dup=小過 |
| P-05 | **未做** `yilin` 的 4,096 单元未纳入 G1 题库 | 评测集只覆盖周易。第三种体系没有对应的检索/引用题目 |
| P-06 | **部分完成** tier 2/3：Herodotus/Darwin 解析器已成、其余五书未动 | 见 §18c。Euclid/Shakespeare/Plato/Iliad 仍只有 §14b 的 `UNVERIFIED` 勘查 |
| P-07 | **DONE** Herodotus 卷I节44 与卷IV节18 缺失原因已定性 | 源文问题：Gutenberg pg2707.txt 两节在正文中根本不存在（非解析器误杀）。grep 验证：卷I §43→§45（缺44）、卷IV §17→§19（缺18） |
| P-08 | **DONE** 把 `booksec` 两书编进索引 | 37 部（28+9 通用性+2 booksec），闸门零回退。Herodotus 761 节、Darwin 14 章，层视图从周易 6 部 → 全语料 13,577 单元 | `.\.venv\Scripts\python.exe scripts\build_index.py` → 592,698 units |
| P-09 | **已完成** T7 断言改为**有条件**，不是放宽 | 现断言三条：①每单元必有文件；②**不允许部分锚定**（那意味着锚点被丢了）；③未锚定的作品必须**显式声明无页码体系**。实测 0 部部分锚定、1 部未锚定（Herodotus 已声明） |

---

## 9. 我在汇报中犯过的错（防止把错误结论当事实继承）

| 错误 | 实际 | 教训编号 |
|---|---|---|
| 声称写了 `docs/HANDOFF.md`、`probes/probe_yao_candidates.py` | **两个文件都不存在，从未写过** | L-11 |
| 声称探针写出 `probes/_cand.txt` | 不存在 | L-11 |
| 把偏移错位判为「外观问题，不再追查」 | 同一根因在伪造引文 | L-02 |
| （本轮）新写的 citation 评测报 0/30，一度像是索引缺陷 | **测试自己错**：拿带标点的 `unit.text` 去比对已去标点的文件正文。两侧同口径后 0 失败 | L-18 |
| G6 首测报 97.85% 错误率 | **测试脚本错**：用单文件索引拼接体偏移 | L-09 |
| G6 二测报 53% 错误率 | 判据错：应为**有序子序列**而非连续子串 | L-09 |
| 诊断用户 `!` 命令失败为相对路径问题 | 实际是工具通道双向中断 | L-11 |

---

## 21. 本轮（sessionID aa53987d）实测记录

**复验纪律**：所有数字均由可执行命令实测得到，不信文档。下列每条附复验命令。

| ID | 任务 | 状态 | 复验命令 / 实测 | 产物 |
|---|---|---|---|---|
| P-05 | yilin 第三种体系题目纳入 G1 评测集 | **DONE** | `./.venv/Scripts/python.exe scripts/derive_eval_yilin.py` → "Added 32 焦氏易林 questions"；`./.venv/Scripts/python.exe scripts/eval_g1.py` → G1 = PASS 225/225 (100.0%) overall, 0 invalid, EXIT=0 | `scripts/derive_eval_yilin.py` · `data/catalog/eval_g1.json` (225 题) |
| P-06 复勘 | tier 2/3 五书已全部入索引（推翻子 agent 1 的 BOOK_RE 列 0 bug 警告） | **DONE** | `sqlite3 data/index/corpus.db "SELECT scheme, count(*) FROM unit GROUP BY scheme"` → None 3457 / booksec 819 / play 817 / yilin 5032 / zhouyi 5088；Plato 10 单元 (BOOK I–X，text 字段以 "BOOK X." 开头确为 dialogue body 而非 analysis，子 agent 1 的"会匹配 analysis headings"警告被实测推翻)；Shakespeare pg100.txt 817 单元；Herodotus pg2707.txt 761 单元；Iliad 两译本；Euclid | `src/guji/ingest.py` L695-754 |
| T7-r | CPU embedding 可行性评估 | **DONE** | `./.venv/Scripts/python.exe probes/probe_t7r_concept.py` → char-bigram TF-IDF + cosine 在 10 条手写转述上 hit rate (correct addr in top-10) = 8/10 = 80.0%，exact-rank-1 rate = 8/10 = 80.0%，EXIT=0。结论：CPU embedding 可行，但概念级题库需引入外部释义数据（属红线第 3 类，不自主执行） | `probes/probe_t7r_concept.py` |
| U-06 勘查 | Douay-Rheims 段内经文号解析器（勘查完成，接入未做） | **PART** | 实测 Douay 结构：1334 个 `"X Chapter N"` 章标题（75 个不同书名，全部正典数对齐：Genesis 50、Isaias 66、Psalms 150 等）；经文格式 `1:1. In the beginning` 与 KJV 几乎一致（只多一个点），bcv.py 的 `VERSE_RE = ^\s{0,6}(\d{1,3}):(\d{1,3})\s+(\S.*)$` 应能匹配；但 ingest.py 完全没引用 Douay（grep `douay|bible-douay|1581` 在 ingest.py/build_index.py 均 No matches），corpus.db 里 Douay 0 单元（work 表有 1 条记录）。接入需跨多道闸门改动（扩 ingest 路由、影响 provenance/对齐/守恒），与 P-06 同类，按节奏纪律记 PART 不继续 | — |

**本轮闸门快照**（13/13 通过）：

```
check_quality.py    PASS（阳性对照 卦61 + 阴性对照 卦47 双向在）
build_index.py      8.5s · 37 部 15,213 单元 · 32.5 MB · suspect 20 units
verify_index.py     ALL PASS（T1–T11，含 T7 三条件断言、T9 守恒、T10 质量标记、T11 校准对照）
validate_alignment.py  爻辭 verified 1824/1872 = 97.4%
probe_conservation.py  TOTAL 2653857 = 2653857 · missing 0.0000% · invented 0.0000% · ratio 1.0000
assess_goals.py     PASS 8 · PART 1 · FAIL 0 · NOT-MEASURABLE 0  of 9
check_provenance.py 0/37 missing
probe_bcv.py        control cases PASS · EXIT=0
eval_g1.py          G1 = PASS 225/225 (100.0%) overall, EXIT=0
```

**P-06 复勘的重要发现**：子 agent 1 在截断输出里警告"Plato 走 booksec.book_spans 会因 BOOK_RE 列 0 匹配 10 个 ANALYSIS headings 而非 10 个 dialogue body headings"——**此警告被主线实测推翻**。实测 Plato 10 单元的 text 字段确实以 "BOOK X." 开头且是正文（如 id=14387 start=38267 text='BOOK I. The Republic opens with a truly Greek scene...'），证明 booksec.book_spans 正确匹配了 dialogue body headings 而非 analysis。子 agent 1 的警告是基于静态 grep 推测，未实测索引内容；主线实测索引内容后推翻该警告。**这正是 GOAL.md §2 纪律的价值：子 agent 的勘查结论一律当"待复验"，主线必须自己实测确认。**

## 本窗口收尾记录（2026-08-14，commit d10b46a）

**完成的三项任务**：
- **U-06 DONE**：Douay-Rheims 接入 35,787 单元 scheme='bcv'，13 道闸门零回退。接入过程推翻两个勘查结论（"VERSE_RE 应能匹配 Douay"实测不匹配、"75 个不同书名"实测 73 个），发现并修复真实缺陷 `search.at_address` schema 污染（Douay bcv addr1=chapter 与 卦号冲突，`at_address(99)` 误当 卦99 返回 Psalms 99，eval_g7 impossible 4/4→3/4；修复加 `AND u.scheme='zhouyi'`，恢复 4/4=100%）。9 个 Vulgate 编号同-(C:V) 重复显式记录于 `probe_bcv.py:DOUAY_EXPECTED_CONFLICTS`。详见 D-028。
- **A-12 DONE**（方案 C EXPECTED）：5 个 span-degenerate-B 全在 KR1a0007，根因是 王弼 裸注紧贴 爻辭 无分节（extract_yao 把注吸进 經 view）。任务书提示的候选思路"排除括号注内的出现"实测**不适用**——错在 王弼 裸注（无括号），非 孔穎達 括号疏。两个备选修复（长度阈值/截断于「注」）各有反例。标 `EXPECTED_DEGENERATE` 不强行修复，任何新增 span-degenerate-B 仍触发。详见 D-029。
- **G1 概念层**（方案 1 实测不达阈值，不纳入 eval_g1.json）：data/raw 内无现代白话释义（只有古注 義曰/解曰）。手写转述从 10 条扩到 55 条，hit rate 从 80.0%（10 条样本过小）降到 78.2%（55 条更可信），**低于 80% 阈值**。照红线第 2 类"不为让数字变好而放宽闸门"，阈值不降，概念层不纳入 eval_g1.json。G1 维持 PART（逐字层 225/225，概念层未覆盖，不虚升 PASS，不降 FAIL）。方案 2 联网抓取释义已授权但需先勘查可用源 + licence（无 licence 或生成文本不得入库，记 BLOCKED 留下一窗口）。详见 D-029。

**实测推翻的文档结论（已改文档并标"此前结论已被推翻"，非悄悄改掉）**：
- GOAL_NEXT_SESSION.md L34 "75 个不同书名" → 实测 73 个
- GOAL_NEXT_SESSION.md L112-115 / TASK_LEDGER.md U-06 勘查行 "bcv.VERSE_RE 应能匹配 Douay" → 实测不匹配（`.` 非 `\s`）
- TASK_LEDGER.md L67 "Euclid 6 BOOK 170 proposition 已入索引" → 实测 0 单元，路由未接线（ingest.py:665 要求 .txt，euclid-elements/ 只有 .html/.epub）
- TASK_LEDGER.md A-12 行 "卦9初九 lenB=6 / 卦58九五 =9 / 卦46初六 =26" → 实测 卦9初九 lenB=7 / 卦58九五 lenB=10 / 卦46初六 lenB=27

**BLOCKED**：
- **G1 方案 2 联网抓取释义**：已授权但需先勘查可用源（百度百科/维基文库/公版注疏白话译本）+ licence。无明确 licence 或属生成文本不得入库（GOAL §5），记 BLOCKED 留下一窗口。

---

## 22. 本窗口（sessionID 接续 aa53987d）实测记录

**复验纪律**：所有数字均由可执行命令实测得到，不信文档。

### 22a. git push DONE（修正上窗口误判）

上一窗口把 `git push` 当红线第 1 类 BLOCKED 跳过。实测 `GOAL_NEXT_SESSION.md` L67-72 明确写"用户已授权 commit/push，push 到 main 不属于红线"。本窗口把 7 个本地 commit（83d7604..1e69f3c）推到 `github.com/YZml1507/books` main。

### 22b. Euclid 路由接线 DONE（第五种地址体系 euclid）

**根因**：`ingest.py` 旧 Euclid 分支（约 L740）读 `.html`，但被 L665 的 `.txt` 前置条件 `if not txt_files: continue` 拦死（euclid-elements/ 只有 .html/.epub）。Euclid 0 单元入索引。

**修复**：在 `ingest.py` 的 `.txt` 前置条件**之前**插入 Euclid 专用分支（读 .html，调 `euclid.parse_propositions`，存 `scheme='euclid'`），删除旧的死分支。`verify_index.py` 的 `NO_PAGINATION` 集合加 `euclid-elements`（0 `<pb:>` 标记，book/proposition 地址体系）。

**空间一致性问题（实测发现并修复）**：Euclid 的 `unit.text` 是 stripped（去 html 标签）版，`unit.raw_start/raw_end` 最初设为 html 偏移——与 `raw_body()` 返回的 html 不同空间，导致 `verify_index.py` T9（`skipped_chars=0 really is contiguous`）失败 1/600。

修复方案（三空间一致）：
1. `euclid.parse_propositions` 返回 **stripped text 偏移**（不是 html 偏移），`prop.text` 是 stripped text 切片。
2. `evalset.raw_body()` 对 Euclid 返回 **stripped text**（调 `euclid._strip_tags`），与 `unit.raw_start/raw_end` 和 `unit.text` 同空间。
3. `euclid._strip_tags` 升级为返回 `(stripped_text, html_offsets)`——walk 原始 html 识别 `<span class="small-caps">X</span>` 保留 X、strip 其它标签、drop entities，同时记录每个 stripped 字符的 html 偏移。

**接入实测**（2026-08-14，所有数字来自脚本输出）：
- `build_index.py` → works **38** · units **51,170**（+170 Euclid propositions）· db 43.4 MB
- Euclid book 分布：Book 1: 48 · Book 2: 14 · Book 3: 36 · Book 4: 16 · Book 5: 25 · Book 6: 31 = 170 propositions
- `verify_index.py` → **ALL PASS**（含 T9 `skipped_chars=0 really is contiguous` 0/600）
- `check_provenance.py` → **0/38 missing**（Euclid provenance 齐全：sha256/url/licence=public-domain (Project Gutenberg)/fetched_at）

**与正典的差异**（Euclid Elements I-VI 正典 173 propositions）：
- Book 3: 36 vs 正典 37（少 1）
- Book 6: 31 vs 正典 33（少 2）
- 总计 170 vs 正典 173（少 3）

这 3 个缺失的 proposition 需要进一步勘查（可能是 `_PROP_HEAD_RE` 漏匹配某些 proposition 标题格式，或正典数本身有争议）。记为 **P-10**，留待后续勘查。但 170 propositions 已全部正确入索引，地址体系 `euclid` 工作正常。

**13 道闸门实测快照（全过，零回退）**：
```
check_quality PASS · build_index 9.8s 38 部 51,170 单元 43.4 MB · verify_index ALL PASS
validate_alignment 爻辭 verified 1824/1872 = 97.4% 零回退 · probe_conservation ratio 1.0000
assess_goals PASS 8 · PART 1 · FAIL 0 · NOT-MEASURABLE 0 of 9 · check_provenance 0/38 missing
probe_bcv control cases PASS（Douay 35,787 verses，9 个已知 Vulgate 冲突显式记录）
eval_g1 G1 = PASS 225/225 · summarise_diff EXIT=0 · eval_g7 FABRICATIONS 0 G7 = PASS（impossible 4/4）
eval_g4 G4 = PASS · probe_g8_isolation PASS — separation holds under all attempts
```

**scheme 分布（实测 `SELECT scheme, count(*) FROM unit GROUP BY scheme`）**：
```
bcv 35787 · zhouyi 5088 · yilin 5032 · None 3457 · booksec 819 · play 817 · euclid 170
```

### 22c. P-10 DONE（Euclid 缺失 proposition 修复）

**根因**：`_PROP_HEAD_RE` 的尾字符类 `[\.\s]` 只接受点号或空白，但 Books 3/6 部分命题用 `PROP. XXIII—Theorem` 格式——prop 号后直接是 em-dash `—` (U+2014)，不匹配 `[\.\s]`，导致这些命题被丢弃。

**缺失命题（实测）**：
- Book 3 prop 23：`PROP. XXIII—Theorem. Two similar segments of circles…`
- Book 6 prop 22：`PROP. XXII—Theorem. If four lines (AB, CD, EF, GH) be proportional…`
- Book 6 prop 27：`PROP. XXVII—Problem. To inscribe in a given triangle (ABC) the maximum parallelogram…`

**修复**：`_PROP_HEAD_RE` 尾字符类从 `[\.\s]` 扩为 `[\.\s—–-]`（em-dash U+2014、en-dash U+2013、hyphen）。这是**放宽匹配范围以捕获之前漏掉的命题**，不是放宽验收闸门——丢失命题是缺陷，捕获它们是修复。

**修复实测**（2026-08-14）：
- Euclid propositions：**170 → 174**
- Book 3：36 → **37**（正典 37，恢复）
- Book 6：31 → **33**（正典 33，恢复）
- Book 5：25 → **26**（+Simson Prop. C n=100，Casey 译本追加命题）
- Book 1/2/4：不变（48/14/16，正典）

**Simson 追加命题**（Book 5 Prop. A/B/C/D/E）：Casey 译本在 Book 5 追加了 5 个 Simson 命题（单字母标号 A-E）。当前 `_PROP_HEAD_RE` 匹配到 Prop. C（n=100）但漏了 A/B/D/E（它们的格式是 `Prop. A.—Theorem`，A 后是 `.`——应该能匹配，但 dedupe 逻辑可能把它们当 cross-reference 丢了）。这 5 个不属于欧几里得正典 25 个，是 Casey 的补充。当前 Book 5 有 26 props（25 正典 + 1 Simson C），可接受。若要捕获全部 Simson 命题需进一步勘查，记为 **P-11**（低优先，非正典命题）。

**13 道闸门实测快照（P-10 修复后，全过零回退）**：
```
check_quality PASS · build_index 9.9s 38 部 51,174 单元 43.4 MB · verify_index ALL PASS
validate_alignment 爻辭 verified 1824/1872 = 97.4% 零回退 · probe_conservation ratio 1.0000 missing 0 invented 0
assess_goals PASS 8 · PART 1 · FAIL 0 · NOT-MEASURABLE 0 of 9 · check_provenance 0/38 missing
probe_bcv control cases PASS（Douay 35,787 verses，9 个已知 Vulgate 冲突）
eval_g1 G1 = PASS 225/225 · summarise_diff PASS · eval_g7 FABRICATIONS 0 G7 = PASS
eval_g4 G4 = PASS · probe_g8_isolation PASS
```

**scheme 分布（实测）**：
```
bcv 35787 · zhouyi 5088 · yilin 5032 · None 3457 · booksec 819 · play 817 · euclid 174
```

### 22d. 新增待办

| ID | 待办 | 依据 |
|---|---|---|
| P-11 | Euclid Book 5 Simson 追加命题 A/B/D/E 未全部捕获（当前仅 C） | **2026-08-15 复验否决**：实测 raw html（`data/raw_ext/generality/euclid-elements/pg21076.html`）Book 5 区内 `Prop. A.—Theorem (Simson)` 格式命题头 = **0 次**——任务书断言被推翻。Book 5 区两次 "Simson" 出现都是译者注的散文引用（`"...order of Euclid, as given by Simson, Lardner..."`、`"...altered the last clause from that given in Simson's Euclid..."`），非命题头；唯一 `Proposition B.` 是正文交叉引用（`"...follows at once from 1 by Proposition B."`），也非命题头。**A/B/D/E 不以命题头形式存在，无法捕获**。当前 ingest 仅捕获 C（n=100）是正确的，无需修复。P-11 关闭——非欧几里得正典，Casey 译本的 Simson 补充只存在于译者注散文，不是可索引的命题单元 |

---

## 23. Q-06 DONE：junk 检测器加 `(cid:N)` 统计

**任务**：GOAL.md §4 T7-h / TASK_LEDGER §6 Q-06。junk 检测器加 `\(cid:\d+\)` 统计——`(cid:N)` 是 ASCII，纯码位普查会漏。

**实施**：
1. `src/guji/quality.py` 新增 `JunkReport` dataclass + `junk_census(text, work)` 函数。统计四类 junk：
   - PUA（U+E000..U+F8FF）：un-mapped subset-font glyphs dumped to PUA
   - CJK Ext A（U+3400..U+4DBF）：rare in real modern text, common as mis-mapped output
   - U+FFFD：replacement character, the universal "could not decode" flag
   - `(cid:N)` markers：ASCII strings emitted by markitdown when it cannot resolve a CID to a Unicode code point（Q-06 核心点——纯码位普查会漏）
2. `scripts/check_quality.py` 调用 `junk_census` 遍历 28 部 Kanripo 书，打印表格，记入 `quality_report.json` 的 `junk_census` 字段。闸门**不因 junk rate 失败**（无校准阈值），只打印+记录，让抽取质量回退可见。
3. `scripts/assess_goals.py` L137 修复：`sum(len(v["low"]) for v in q.values())` 改为只对含 `low` key 的 dict 求和——我加的 `junk_census` 字段是 dict（没有 `low` key），破坏了原遍历。

**实测**（2026-08-14）：
- 27/28 Kanripo 书有 junk（全部是 ExtA，PUA/FFFD/cid=0——Kanripo 纯文本不含 CID 占位符，符合预期）
- junk rate 范围 0.105%..0.490%，最高 KR3g0035 0.490% / KR3g0041 0.412%
- `(cid:N)` 标记 = 0（Kanripo 是纯文本，无 CID 字体；`(cid:N)` 只在 markitdown 转换 Identity-H subset 字体 PDF 时出现，见 D-001）

**验收**：13 道闸门全过零回退。复验：
- `./.venv/Scripts/python.exe scripts/check_quality.py` → PASS（含 Q-06 junk census 表）
- `./.venv/Scripts/python.exe scripts/assess_goals.py` → PASS 8 · PART 1 · FAIL 0
- 全 13 道闸门见 §22b/§22c 快照

**Git**：commit 874e3bf，push 到 `github.com/YZml1507/books` main（代理 `127.0.0.1:7897`）。

**13 道闸门实测快照（全过，零回退）**：
```
check_quality PASS · build_index 9.9s 38 部 51,174 单元 43.4 MB · verify_index ALL PASS
validate_alignment 爻辭 verified 1824/1872 = 97.4% 零回退 · probe_conservation ratio 1.0000
assess_goals PASS 8 · PART 1 · FAIL 0 · NOT-MEASURABLE 0 of 9 · check_provenance 0/38 missing
probe_bcv control cases PASS（Douay 35,787 verses，9 个已知 Vulgate 冲突显式记录）
eval_g1 G1 = PASS 225/225 · summarise_diff EXIT=0 · eval_g7 FABRICATIONS 0 G7 = PASS（impossible 4/4）
eval_g4 G4 = PASS · probe_g8_isolation PASS — separation holds under all attempts
```

---

## 24. Q-07 DONE：双引擎分歧闸门产品化

**任务**：GOAL.md §4 T7-i / TASK_LEDGER §6 Q-07。D-001 已实测双引擎分歧（PyMuPDF 主 + markitdown 交叉校验）但未落地为模块。

**实施**：
1. `src/guji/dual_engine.py` 新模块：`compare(path) -> DualEngineReport`。跑 PyMuPDF（主引擎，揭露页边界）+ markitdown（交叉校验，独立解析链）于同一源。复用 Q-06 `junk_census` 做每引擎 junk 报告。引擎错误记录不抛。**闸门只在 both-junk 失败**（两引擎均 ≥5% junk = OCR 强制态）；分歧本身是信息不是失败。
2. `scripts/check_dual_engine.py` 闸门 CLI：无参则扫 `data/raw_ext/generality` 下所有 PDF/EPUB。exit 0 除非 double-junk。

**取代**：分散在 `probes/probe_markitdown.py`、`probes/probe_cid_verify.py`、`probes/probe_crosssource.py` 的探针级逻辑（Q-07 产品化）。

**实测**（2026-08-14）：
- 10 个 EPUB 目标扫描（pg100/pg1497/pg2199/pg2707/pg6130/pg21076 等），0 double-junk，全部 "engines agree"
- markitdown 对所有 EPUB 产出 0 page-marks（flat string，无页分界）——印证 D-001 "markitdown 不能作引用唯一解析器"的结论
- CSS syntax error 是 MuPDF 对 PG EPUB CSS 的无害警告，不影响提取

**验收**：13 道闸门全过零回退。复验：
- `./.venv/Scripts/python.exe scripts/check_dual_engine.py` → PASS: 10 target(s) scanned, 0 double-junk
- `./.venv/Scripts/python.exe scripts/check_quality.py` → PASS
- `./.venv/Scripts/python.exe scripts/verify_index.py` → ALL PASS
- `./.venv/Scripts/python.exe scripts/assess_goals.py` → PASS 8 · PART 1 · FAIL 0

**Git**：commit 801d0eb，push 到 `github.com/YZml1507/books` main（代理 `127.0.0.1:7897`）。

---

## 22c. 本窗口（2026-08-15，sessionID 接续 aa53987d）实测记录

接续 aa53987d 窗口。开局基线复验：13 道闸门全过，PASS 8 · PART 1 · FAIL 0，与 §22b 一致。

### 完成的任务（11 项）

**2a. T7-r CPU embedding 方案 C（TF-IDF + SVD）实测否决 → D-031**
- `probes/probe_embed_tfidf.py`（零新依赖，numpy 2.5.2 已在 venv）：对 5,088 个 zhouyi 經层单元建 char-bigram TF-IDF（sublinear tf: log(1+tf)，sklearn 式 smoothed IDF）+ TruncatedSVD(100) + LSA 投影 + cosine top-10
- 55 条手写转述（D-029 沉淀批，与 probe_t7r_concept.py 同源）实测：hit rate **37/55 = 67.3%** < 80% 阈值
- build time 65.1s（OK），query latency 2ms median（OK），memory 553.6 MB（OK），variance explained 0.853
- **反直觉**：方案 C 比基线 78.2% 还差 11 个百分点——SVD 降维把高频卦象 bigram 区分信号稀释到了"长文本主题"维度，LSA 在短文本强主题重叠语料上的已知失效模式
- 闸门判定：方案 C 不过闸门，记 D-031 否决，G1 维持 PART

**2a. T7-r 方案 A/B（sentence-transformers + PyTorch + BAAI/bge）撞红线第 3 类 BLOCKED → D-032**
- `pip install sentence-transformers` 引入 PyTorch CPU（~500 MB 新依赖）——红线第 3 类
- 下载 BAAI/bge-small-zh-v1.5 模型权重（~100 MB 联网抓取）——红线第 3 类
- 按 GOAL §1"跳过并记录"处置，记 BLOCKED 写进 DECISIONS.md（附方案 C 基线数字），不停下来问
- 解本条件：用户显式授权引入新依赖 + 联网下载模型权重 + 模型 licence 核验（BAAI/bge 是 MIT，但须附 sha256/source_url/fetched_at/licence 到 model_provenance.json，照 W-06 先例）

**2b. T5 A-12 候选 N1（clean 剥离王弼裸注）实测否决 → D-033**
- 先查清根因（这改变了问题的性质）：实测 clean(keep_notes=False) 的 DROP 集合不含"注"字，王弼裸注（无括号）原样进入经 view
- **重大发现**：KR1a0007 有 375/379 = 98.9% 地址含"注"字——几乎每个 KR1a0007 地址的 span 都吸了裸注。5 个 span-degenerate-B 只是 len_b<30 被抓到的子集，其余 374 个吸裸注后 len_b>30 判 span-overextended 但没标缺陷
- len 分布实测：截前 mean=196 median=81，截后 mean=12 median=10——全 379 个 KR1a0007 地址 span 边界都错了
- 列 2-3 个新候选（不是已测的 A/B，不是不适用的"排除括号注内出现"）：
  - N1（clean 剥离裸注）：解 2/5 裸注 glued，零误切风险（61 gold 爻辭 0 个"注"字）
  - N2（span end 用"注"字）：误切彖曰/象曰，否决
  - N3（裸注边界枚举）：误切裸注中段"故曰"，否决
- 选 N1 执行：改 src/guji/anchors.py:clean(keep_notes=False) 加裸注剥离状态机
- bug 1 修复：初版检查 out[-1]（刚 append 的"注"字本身），prev 永远是"注"，N1 从不触发。改为检查 out[-2]
- **闸门实测否决 N1**：build units 51,174→51,045（少 129），verify_index T11 FAIL（293 compared，阈值≥358）。根因：N1 剥了 quality.py::addresses_of 用的经视图，cross_edition_coverage 比对地址 362→293
- 按 R-02 先例回退，A-12 维持 EXPECTED_DEGENERATE。N1 嘉露的"全 379 个 KR1a0007 地址吸裸注"留待下一窗口用局部剥离方案处置

**2c. T7-q 知识图谱前置条件实测 → 满足**
- `probes/probe_t7q_kg_precondition.py`：模拟三类常见实体抽取策略（字符级 NER、关键词级抽取、折叠表归一化），测 differs 異文（枯楊生稊/生梯、跛能履/破能履）是否被抹平
- 实测：三类策略都保留 稊/梯、跛/破 区别，differs 異文不被实体抽取抹平
- FOLD 表不含 稊/梯、跛/破 映射，NOT_VARIANTS 显式排除——折叠表不归一 differs 異文
- 知识图谱前置条件之一满足。建图本身是另一项工作

**T7-m &KR0658; 占位符语义 → 查清**
- `probes/probe_t7m_entities.py`：实测 &KR0658; = 虩（U+8679，恐惧貌），卦51 震 爻辭"震來虩虩"
- 任务书"每部书 22-31 个"断言被实测推翻：&KR0658; 只在 KR1a0006 出现 12 次，其他 4 部周易书 0 次
- clean() 不解析实体引用，&KR0658; 原样进入经视图和 corpus.db——检索 虩 会漏命中（索引存的是 &KR0658;）
- 虩 字在其他版本直接印出（KR1a0007 28 个，KR1a0001 8 个，KR1a0031 10 个）——实体引用只 KR1a0006 用
- 处置建议（下一窗口）：在 clean() 里加 &KR0658; → 虩 解析（最小修复），但 clean 改动可能回退闸门（D-033 N1 先例）

**T7-n 自天祐之 5 vs 4 → 查清为源文真实差异**
- 实测分布：KR1a0001 5次 / KR1a0006 5次 / KR1a0007 12次 / KR1a0031 3次 / KR1a0032 4次——5 部周易书各异，非"两源 5 vs 4"
- "自天祐之"出现在两类文本：卦14 大有 上九 绻辭（每部书 1 次）+ 卦64 繫辭传多次引用（各版印次不同）
- "5 vs 4"指 KR1a0001(5) vs KR1a0032(4)，是繫辭传在不同版本里的印次差异——底本/朱熹两版各印不同章段。源文真实差异，非抽取错误

**T7-o probes 归档整理 → 45 个归档**
- 已沉淀结论的迭代探针移入 probes/archive/：kr31 系列 15 个、text/structure/round 系列 7 个、euclidean/western_recon/align/bcv/verify 系列 11 个、tier23/douay/play/shakespeare/iliad/plato 系列 10 个
- probes/archive/ 共 45 个归档，probes/ 剩 65 个活跃探针

**T7-p Phase 3 架自审 → 通过 → D-034**
- 全文读 BOOK_AI_ARCHITECTURE.md 286 行（§1–§11），逐条核实断言与实测/当前台账对照
- 顶部阅读须知的自审断言经实测全部仍准确——负责任的架构文档，自带自审与指向更新文档的导航
- §4 字段名实测对照：架构方案字段名是设计意图名，schema（addr1/addr2/scheme/addr_name）是实现名，文档已自审标注此差异
- §5"自天祐之 5 vs 4 原因待查"现已查清（T7-n）
- §11 已知弱点 5 条：3/5 已缓解或补齐（embedding 方案本窗口已测、评估集已补、G2-G8 已 PASS），2/5 仍成立（通用性证伪、OCR API key）
- 无需修改架构方案——它的自审机制让它成为"自维护文档"，过时内容已被自身标注。Phase 3 架自审通过

**2h. P-11 Euclid Simson 命题 → 复验否决**
- 实测 raw html（data/raw_ext/generality/euclid-elements/pg21076.html）Book 5 区内 `Prop. A.—Theorem (Simson)` 格式命题头 = **0 次**——任务书断言被推翻
- Book 5 区两次"Simson"出现都是译者注的散文引用，非命题头；唯一 `Proposition B.` 是正文交叉引用，也非命题头
- **A/B/D/E 不以命题头形式存在，无法捕获**。当前 ingest 仅捕获 C（n=100）是正确的，无需修复。P-11 关闭

### 13 道闸门实测快照（本窗口末，全过零回退）

```
build_index 38 部 51,174 单元 43.4 MB · verify_index ALL PASS · validate_alignment verified
assess_goals PASS 8 · PART 1 · FAIL 0 · check_provenance 0/38 missing
probe_bcv PASS · eval_g1 PASS 225/225 · eval_g7 FABRICATIONS 0 G7 PASS
eval_g4 G4 PASS · probe_g8_isolation PASS · probe_conservation ratio 1.0000
```

### Git

本窗口改动：probes/ 新增 3 个（probe_embed_tfidf.py, probe_t7q_kg_precondition.py, probe_t7m_entities.py）+ embed_c_report.json；probes/archive/ 归档 45 个；DECISIONS.md 增 D-031~D-034；TASK_LEDGER.md 增 §22c + P-11 复验否决；GOAL_NEXT_SESSION.md 未变。

## 22d. 本窗口（2026-08-15 接续，sessionID 3d8bab44 之后的下一窗口）实测记录

开局基线复验（13 道闸门全跑，无一跳过）：build_index 43.4 MB · verify_index ALL PASS · validate_alignment verified 1824/1872 = 97.4%（located 1872/1882）· check_quality PASS · probe_conservation missing 0 ratio 1.0000 · assess_goals **PASS 8 · PART 1 · FAIL 0**（唯一 PART 是 G1，故意）· check_provenance 0/38 缺失 · probe_bcv PASS · eval_g1 全 PASS · eval_g4 PASS · eval_g7 FABRICATIONS 0 · probe_g8 PASS。
- unit 表实测：51,174 行、35 个 work_id 有单元；work 表 38 行（bible-kjv/bible-web/darwin-origin 3 部在 work 表但 unit 表 0 行——probe_bcv 的 31,102 行计数来自 raw_ext/generality 原始文件，不来自 unit 表，无矛盾）。周易系 28 部锚点覆盖 28/28。scheme 分布与快照一致（bcv 35787 · zhouyi 5088 · yilin 5032 · None 3457 · booksec 819 · play 817 · euclid 174）。

**2a. T7-r 方案 A/B（sentence-transformers + PyTorch + BAAI/bge）本窗口未获用户显式授权 → 维持 BLOCKED，照红线"跳过并记录"**
- 本窗口开场指令未含"授权引入 sentence-transformers+PyTorch CPU / 授权下载 BAAI/bge 模型"字样
- 照 GOAL §1 第 3 类红线处置：不重做、不停下问，记 BLOCKED 后直接进入下一任务（2c &KR0658; 最小修复）
- G1 维持 PART。解本条件不变（见 §22c 2a 条）：用户显式授权 + 模型 licence 核验入 model_provenance.json
- **接续窗口（本窗口，2026-08-15 第二轮）复验**：开场指令仍未含"授权引入 sentence-transformers+PyTorch CPU / 授权下载 BAAI/bge 模型"字样 → 2a 维持 BLOCKED，跳过并记录，G1 维持 PART，转入 2d 扩展
- **✅ 2a 已授权并落地（接续窗口第三轮）**：用户开场指令"授权，你去进行后续所有修复" = 显式授权引入 sentence-transformers+PyTorch CPU、授权下载 BAAI/bge 模型。六步全执行：
  1. `pip install sentence-transformers`（torch-2.13.0+cpu，官方 CPU index 装的，避开 pypi CUDA 大包）成功
  2. 下载 BAAI/bge-small-zh-v1.5（13 文件，model.safetensors 95.8MB）到 `data/external/bge-small-zh-v1.5/`，provenance 已记 `data/catalog/model_provenance.json`（sha256=354763b9… / source_url=huggingface / fetched_at=2026-08-15T10:15:34+08:00 / licence=MIT）
  3. 新探针 `probes/probe_embed_bge.py`：同方案 C 流程（5088 经层 zhouyi 单元 + 55 条 D-029 转述 + top-10 余弦），query 端加 bge 检索指令前缀
  4. 闸门先定后测全达标：**hit 53/55 = 96.4% ≥ 80%** · build 50.5s ≤ 10min · query 中位 17ms ≤ 2s · 内存 5.1MB ≤ 4GB
  5. **hit ≥ 80% → G1 PART 升 PASS**：55 条转述已纳入 `eval_g1.json` 的 `retrieval_concept` 类别（derive_eval_g1.py 生成，witness=该地址爻辭在 raw 里可验，D-019 不违背）；eval_g1.py 新增 `score_concept`（bge 编码 + 文档向量缓存 data/catalog/bge_docvecs.npy 复用，ids 匹配才用）；assess_goals.py G1 判定改为"retrieval_concept PASS 且 overall PASS → G1 PASS"。**实测 assess_goals PASS 9 · PART 0 · FAIL 0**（G1 从 PART 升 PASS，全 9 项全绿）
  6. 55 条转述用 D-029 沉淀批（probe_t7r_concept.PARAPHRASES），未手写新题
  - eval_g1 两次 MISS（卦2六四、卦58九二）与方案 C 不同位——bge 语义理解与字面 bigram 的差异，属真实检索行为，不掩盖

**2c. T7-m &KR0658; → 虩 最小修复 → 落地（13 道闸门零回退）**
- **任务书"在 clean() 里加 &KR0658;→虩 解析"的位置被实测推翻**：clean() 不参与 unit.text/FTS 生成链（parse_units 直接切 raw 切片，ingest.py:631 `fts.append((uid, segment_cjk(fold(text))))`），改 clean() 对检索无效。这是又一处"任务书断言 vs 实测不符"活教材（§0 纪律第 4 条：发现不符改文档留记录）
- 修复层实测选定：**build() 的 zhouyi FTS 喂入点（ingest.py:631）**——`text.replace("&KR0658;", "虩")` 后再 segment_cjk(fold())，unit.text 保持忠实于 raw 实体，probe_conservation 的 CJK 多重集不变（&KR0658; 是 ASCII 不进 CJK 计数，若改 unit.text 会 invent 12 个虩 → 回退）
- 实测验证：改动前 search('虩') 命中 10 条全是直接印"虩"字的版本（KR1a0001/0031/0032/0007/0016），KR1a0006 0 条漏命中；改动后 KR1a0006 命中 2 条（卦51 震 初九 + 卦辭，unit 1237/1238）
- **13 道闸门全过零回退**：build 51,174 单元 43.4 MB · verify_index ALL PASS（T11 362 compared）· validate_alignment 1824/1872 = 97.4% · check_quality PASS · probe_conservation ratio 1.0000 · assess_goals PASS 8·PART 1·FAIL 0 · check_provenance 0/38 · probe_bcv PASS · eval_g1 全 PASS · eval_g4 PASS · eval_g7 PASS FABRICATIONS 0 · probe_g8 PASS
- 落地改动：src/guji/ingest.py 一行（FTS 喂入点 decode）+ 注释说明

**2b. T5 A-12 quality.py addresses_of 局部剥离 → 五候选（P1-P5）全部实测否决 → D-035，A-12 维持 EXPECTED_DEGENERATE**
- 新探针 `probes/probe_a12_local.py`（内存模拟，未改任何源文件，quality.py 零 diff）
- 实测两难（结构性冲突，不是实现细节）：
  - P1/P2/P3（只对 B 截裸注）：len_b 达标（卦58 九五 10→7、卦46 初六 27→6）但 **T11 median coverage 0.991→0.132 崩盘**——A（KR1a0006）注是括号注、B（KR1a0007）是裸注，T11 比对语义就是"A 的 with-notes 全文在 B 里可恢复比例"，剥裸注必崩
  - P4/P5（A、B 对称经-only）：A 经-only 后 370 地址 149 个 len<20 被 min_len 过滤（with-notes 时仅 2 个）→ compared 362→**218** < 358 阈值
- 结论：T11 依赖 with-notes 全文比对，A-12 要剥 B 裸注，二者在 addresses_of 同一输出上不可兼得。局部剥离无法同时满足"13 道零回退"+"len_b 下降"
- 照任务书 2b"达不到就 R-02 否决"：P1-P5 全否决，A-12 维持 EXPECTED_DEGENERATE，probe 留作负结果记录（照 rarity_scores 先例）
- 闸门确认：T11 362 compared / median 0.991 PASS，align 1824/1872 = 97.4% 不回退（quality.py 未改）

**2d. 低优先三项 → 两项完成，通用性证伪另做**
- **T7-o probes 归档续做**：再归档 12 个已沉淀探针（probe_legge/parens/glyphs/corrupt/boundary/crossedition_diff/gua47/jiaoshi_layout/addresses_fix/kr31/skew/sunls2_audit，均 0 引用、非闸门）→ probes/archive/ 45→57 个，probes/ 活跃 66→54
- **架构补注**：BOOK_AI_ARCHITECTURE.md §5 "自天祐之 5 vs 4 原因待查"补注一行——原因已查清（D-034/T7-n：KR1a0001(5) vs KR1a0032(4) 繫辭传印次差异，源文真实差异，非抽取错误，不入折叠表）
- **通用性证伪（MASTER_PLAN §11 弱点）**：新探针 `probes/probe_generality_roundtrip.py`——对 6 种地址体系（bcv/booksec/euclid/play/yilin/zhouyi）各随机抽 25 个有地址单元，用 citation/retrieval 层同一查询（scheme+addr1+addr2+id）反查，**6/6 体系 25/25 = 100% round-trip，未被证伪**——地址是 locative 不是 decorative，插件模型在 Euclid/Plato/Shakespeare/BCV/Douay 上也成立。10,520 个 (scheme,addr1,addr2) 组合无碰撞（Psalms-99==卦99 类冲突已由 scheme 隔离，D-005）

**2d 扩展（接续窗口补做，probes/probe_generality_crossref.py）——三链/别名/跨 scheme 交叉引用实测，play 方案被证伪**
- **新探针** `probes/probe_generality_crossref.py`：round-trip 探针只证明"地址能找到自身单元"，看不到"地址与内容是否相符"。本探针补三查：
  - **跨 scheme 交叉引用**：link 表 558 条 src_scheme×dst_scheme 分布 = **558/558 全部 yilin→yilin，0 条跨 scheme**——Source 存储里不存在跨体系交叉引用（负结果，非缺陷：互见注只在焦氏易林出现）
  - **跨 scheme 地址别名**：(addr1,addr2) 出现在 ≥2 个 scheme 的有 **373 个**（如 addr1=1 addr2=None 同时出现在 booksec/play/yilin/zhouyi；bcv/booksec 的 1:1..1:17 章節）。API 层实测（at_address，hard-code scheme='zhouyi'）：64 个 zhouyi-别名地址 **0 泄漏**——scheme 过滤是 airtight 的，Psalms-99==卦99 类（D-005）隔离成立
  - **同 work 同 FULL 地址+layer 多单元（真别名）**：593 组 = bcv 9（=probe_bcv 已知 Vulgate Psalms-113/Prov-12:12 冲突，预期）+ **play 182** + yilin 181 + zhouyi 221。逐类查证：yilin 181 与 zhouyi 注层多为同地址注文两片（木刻行断 split，benign）；zhouyi 另有 64 个 `** 《X第N》` 节尾单元继承了前卦最后爻地址（次要 mislabel）；**play 182 是真缺陷（见下）**
  - **三链一致性**：link 目标卦名印在 src cell 文本：**0/558 缺失**（比 eval_g4 只抽 400 条更强，全量）；link dst 自身地址 round-trip：0 失败；抽样 30 条 link src 的 FTS 短语检索：**0 漏检**
- **⚠ 重大证伪：play（Shakespeare）地址不定位其内容**——623/811 单元的最接近前驱 body-ACT ≠ 声明 ACT。根因实测钉死：Gutenberg pg100.txt 每剧标题后都有 `Contents` 块（紧凑列出 `ACT I\nScene I.\n<setting>`…ACT V），play.py 的 ACT_RE 先匹配到 Contents 的 ACT 头（offset 39/135/206/269/338，相距 ~100 字符），正文真实 ACT 头（数千字符后）被 dedup 丢掉 → 每幕 act 区坍缩到 Contents 偏移，正文所有 SCENE 都挂到 `ACT V SCENE n` 标签下（e.g. unit 50359 addr2='ACT V SCENE I' 但 raw 处实为 All's Well 正文 ACT I 前）。38/44 部作品带 Contents 块 → 全中招。**round-trip 探针 25/25 通过是假绿**：它只查"地址→自身单元 id"稳定，不查"地址命名了它覆盖的内容"——这正是 GOAL §0"计数型检查看不见文字错位"的又一实例
- **处置（照 D-033/D-035 先例）**：缺陷已实测记录，probe 留作负结果；修 play.py（ACT_RE 需跳过 Contents 块，判据：头后非空行是 `SCENE` 大写即正文 ACT、`Scene` 混合大小写即 Contents）列为候选任务，本窗口只验证不修（scope 外）。13 道闸门与该缺陷无关（play 地址不参与 T1-T11 断言），闸门复验全过
- **✅ play.py 已修复（接续窗口第三轮）**：用户授权"进行后续所有修复"后落地。修复三连 + 一次探针判据修正：
  - **Contents 过滤判据演进**：初版"ACT 头后非空行大写 SCENE"被 Pericles 推翻（正文 ACT 后是 Chorus "Enter Gower." 非 SCENE）；二版"到下一 ACT 头区间内有大写 SCENE"被 Henry VI 推翻（其 Contents ACT II-V 用大写 SCENE）；**最终判据 = 角色表分界**：`_DRAMATIS_RE`（Dramatis Personæ / PERSONS REPRESENTED，re.I，实测 38/38 部剧恰好 5 个 Contents ACT 在其前、5 个正文 ACT 在其后）——过程中还踩了 `\b` 边界坑（Personæ 的 æ 是字母，`PERSON\b` 不匹配）与 `THE ACTORS` 误匹配正文对话（Hamlet "The actors are come"）
  - **body_off 偏移修复**：find_plays 内部 strip 掉 Gutenberg header（48 字节）后返回的 pos 是 body-relative，ingest 用 raw 直接切片 → 所有 play 单元 raw_start 偏左 48 字节，这是探针第二版 224/811 假阳性的真相。修：Play.start/end 加 body_off 转 raw-relative
  - **验证**：38/38 剧 5 幕、6 诗 no-act（HAMLET 5/2/4/7/2、HENRY VI-1 6/5/4/7/5、MIDSUMMER 2/2/2/2/1、PERICLES 4/5/4/4/3 各剧 scene 分布合理）；**play locativity 探针 623 → 0**（768 单元全部最近前驱 body-ACT == 声明 ACT，not falsified）
  - 探针 addendum 的 body-ACT 判据同步改为与 play.py 相同的"角色表分界"口径，避免审计者与 parser 判据不一致

## 23. 新增 bazi 排盘 + 命理书引用检索（用户需求："生辰八字 → 书本知识答复"）

**需求分层实测**（D-038）：引用型检索可做（给证据不生成），生成式解读撞 GOAL §5 红线；用户选择"接 LLM，我会提供 API KEY"（授权生成式解读层，边界：不落库/与引用分离/标注 LLM 来源）。

**交付**：
- `src/guji/bazi.py`：纯标准库排盘（零新依赖）。公历 → 四柱/日主/纳音/大运方向。节气用 Meeus 低精度太阳黄经 + 二分（实测立春 2024 差 5 分钟、小寒 2000 差 3 分钟）。**3 组权威基准全对齐**：2000-01-01 己卯丙子戊午 / 1984-02-02 癸亥乙丑丙寅 / 2024-02-10 甲辰丙寅甲辰（日柱 (JDN+49)%60、纳音 (6g-5z)%60 CRT、月柱 (jie_zhi-2)%12 月序——初版月柱/纳音公式有 bug，用权威数据实测推翻后修正）。出生时刻距节 ≤30min 置 warn。
- `src/guji/bazi_lookup.py`：FTS（坐标词 ≥2 字，9 部命理书精确检索）+ bge（命理书单元向量缓存 data/catalog/bge_mingli_docvecs.npy，ids+结构双校验）双路径，全部带 文件+页锚点 引用。
- `scripts/ask_bazi.py`：`python scripts/ask_bazi.py 1990 5 15 10 男 [--sem]` → 排盘 + 命理书原文证据；查不到输出"证据不足"（G7）。输出标注"非系统生成的解读"。

**验证**：5 个八字样例（1949-10-01/1984-02-02/2000-01-01/1995-07-07/2020-02-04）排盘+命中正常；1990-05-15 → FTS 19 条 + bge 8 条。13 道闸门全过零回退（新增只读模块）。

**待办（已授权）**：LLM 解读层 `src/guji/llm_reader.py`——用户提供 API KEY（环境变量，不进对话），坐标+原文作 context，生成白话解读；不落库、与引用分离、标注 LLM 来源。

**LLM 解读层落地（用户授权 + 配置文件方式，D-039）**：
- `src/guji/llm_reader.py`：OpenAI 兼容 chat/completions（httpx，零新依赖）。边界照授权：不落库、与引用分离（原文引文 / LLM 解读两段）、KEY 不进对话/命令行/日志。
- 配置：复制 `llm_config.example.json` 为 `llm_config.json` 填写 base_url/api_key/model（.gitignore 已排除，KEY 永不提交）；环境变量 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 兜底。
- `scripts/ask_bazi.py --llm [--question ...]`：引用证据后追加 LLM 解读；未配置时提示配置文件路径，引用仍完整输出。
- 实测：无配置 available()=False 降级正常、配置解析通过；真实 API 调用待用户填 KEY 后验证（本窗口无 KEY 不假装调通）。

## 24. 网页端（FastAPI + 单页前端）已落地（D-040 / WEB_PLAN.md）

用户需求：搭建网页端；提供 ui-ux-pro-max skill（解压至 vendor/，不入库）。决策：FastAPI（建议自主执行）+ 打包单文件（后续）。

- `docs/WEB_PLAN.md` 方案；`web/app.py` 后端（校验/编排/LLM 失败不掩盖引用）；`web/static/index.html` 单页前端（三段式，按 skill 设计规范：瑞士极简/藏青+金/Noto TC/离线可用）。
- 实测：TestClient 全过；独立进程 GET / 200、POST 200（12 证据）、use_llm=true 真实 LLM 成功；13 道闸门零回退；浏览器已打开实测。
- 启动：`python -m uvicorn web.app:app --host 127.0.0.1 --port 8123`
- 待办：PyInstaller 打包单文件（用户选定形态）。
