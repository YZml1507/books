# 方案书：T7-r CPU embedding 可行性实测与 G1 概念层接入

**版本** 1.0 · 2026-08-14 · 状态：**待用户确认，确认前不动代码**

> 本文是**方案书**，不是已落地的决策。照 GOAL.md §1，技术决策及实测依据写入 `DECISIONS.md`
> 才成立；本方案在用户确认 + 实测产出第一条数据后，才会追加为 D-031。
> MASTER_PLAN.md §2 当前把"向量检索与 embedding"列在**明确不在当前范围**（无 CUDA，
> CPU 方案未评估）。本方案的目的就是**做这次评估**——评估后可能把它移出"不在范围"，也可能
> 确认"不在范围"是对的，两种结论都合法。

---

## 1. 这个任务要回答什么问题

**一句话**：本机无 CUDA、7.4 GB 内存、纯 CPU，能否对 51,174 个中文单元建向量索引，
使"给定白话转述/概念描述，检索到正确的卦爻地址"的命中率 ≥ 80%？

这是 G1 概念层唯一的可能解法（D-030 已确认公版白话释义不存在，联网抓取路径 BLOCKED）。
若 CPU embedding 不可行，G1 维持 PART（逐字层 225/225 PASS，概念层未覆盖）——
那也是正确的状态，不虚升、不降级。

**本方案不是**：建一个生产级语义检索系统。可行性实测的产出是一个**基线数字**（hit rate%
+ 建向量耗时 + 单次查询延迟 + 内存峰值），照 MASTER_PLAN.md §8「先有可执行的复验命令，
再谈质量」的先例。

---

## 2. 架构与约束对照（为什么这个方案不违反红线）

| 约束来源 | 约束 | 本方案如何处置 |
|---|---|---|---|
| MASTER_PLAN §2 | 向量检索不在当前范围，CPU 方案**未评估** | 本方案就是这次评估。评估结论可能是"不可行"——那等于确认"不在范围"是对的 |
| MASTER_PLAN §9 | GPU embedding 不可用（无 CUDA） | 用 CPU 推理；若 CPU 不可行，照 §9 先例记否决，不动代码 |
| MASTER_PLAN §9 | Neo4j/Milvus 不采用（独立进程，7.4 GB 内存） | 用 SQLite 存认的存储（向量存 blob），无新进程 |
| GOAL §1 红线 1 | 破坏性不可逆：删语料/git push/重写历史 | 本方案不删任何东西；向量索引是 5 秒可重建的产物（照 corpus.db 先例），属"随便重建"类 |
| GOAL §1 红线 2 | 为让数字变好而放宽闸门 | embedding 的闸门**先定后测**（§5），达不到就记 BLOCKED，不调闸门 |
| GOAL §1 红线 3 | 联网抓取新语料/外部依赖 | embedding 模型是**新外部依赖**——但不是"语料"，是推理工具。照 §1 授权范围：**引入新外部依赖属红线第 3 类，跳过并记录**，不是自主执行。**这是本方案需要用户确认的核心点**（§7） |
| MASTER_PLAN §6 | G8 三类隔离：Derived 不与 Source 共生命周期 | embedding 向量属 **Derived**（AI 推导），存 `data/index/knowledge.db`（已有），**永不进 corpus.db**。corpus.db 每次 build 被 `os.remove` 删掉重建，向量不能跟着死 |
| MASTER_PLAN §7 | 第 5 步（G1 评测集）后才建知识图谱 | G1 评测集已完成（225 题），本方案在它之后 |
| MASTER_PLAN §7 | 建图前须确认 differs 类異文不被实体抽取抹平 | 本方案不做实体抽取，只做 unit→vector。異文保留照 G5 现有机制，不触碰 |

**关键约束**：**引入 embedding 模型是新外部依赖**（红线第 3 类）。本方案**不自主执行**，
写成方案书交用户确认。这是本文件存在的理由。

---

## 3. 数据范围

**只对周易语料建向量**，不对 51,174 全量建。理由：

1. G1 评测集建在周易上（GOAL.md §4 T1：语料最成熟、有 gold set、有跨版本见证）。
   embedding 是为 G1 概念层服务的，概念层题目也锚在周易。
2. 周易是**已验证可复制样板**（MASTER_PLAN §7：先把周易做透，再套到其他作品）。
3. 全量建向量是生产级需求，可行性实测不需要。

**周易单元实测**（复验命令）：
```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('data/index/corpus.db'); print(c.execute(\"SELECT count(*) FROM unit WHERE scheme='zhouyi'\").fetchone()[0])"
```
当前 5,088 个单元（scheme='zhouyi'）。向量维度 d，存储量 = 5,088 × d × 4 字节（float32）。
d=512 时 = 10 MB，d=768 时 = 15 MB——SQLite blob 完全可承载。

**query 侧**：概念层题目是"白话转述"，照 D-029 的 55 条手写转述先例。可行性实测用
**同一批 55 条**（hit rate 78.2% 那批，已在 `probes/probe_t7r_concept.py`），换 embedding
检索替 FTS5，看 hit rate 是否升过 80%。**不手写新题**——照 GOAL §4 T1「手写 gold 在本
项目错过两次」的先例，用已沉淀的 55 条。

---

## 4. 技术选型（三个方案，实测前不定）

照 GOAL §1「自己列 2–3 个方案，用本仓库的实测数据比较，选最优的直接执行」。

| 方案 | 模型 | 维度 | CPU 推理库 | 本地化 | 优点 | 风险 |
|---|---|---|---|---|---|---|
| A | BAAI/bge-small-zh-v1.5 | 512 | sentence-transformers + PyTorch CPU | 模型 ~100 MB | 中文专项、轻量、HF 社区主流 | PyTorch CPU 依赖重（~500 MB），推理慢 |
| B | BAAI/bge-base-zh-v1.5 | 768 | 同上 | ~400 MB | 维度高、精度好 | 更慢、内存占用更大 |
| C | 纯 Python � TF-IDF + SVD 降维 | 自定 | numpy/scipy（已在 venv） | 0 | 零新依赖、纯 CPU 快 | 不是真"语义"，只是主题模型；可能根本不顶 FTS5 |

**推荐先测方案 C**（零新依赖，5 分钟出基线），再测方案 A（真语义，但有新依赖）。
理由：若 C 都能过 80%，A 不需要做；若 C 不过，A 才有必要。这是**最小风险路径**，
照 LESSONS.md L-04「先试零成本否决」的先例。

**方案 A/B 的模型 licence**：BAAI/bge 系列是 MIT licence（模型权重 + 代码），可商用。
实测前会附 `sha256 / source_url / fetched_at / licence` 到 `data/catalog/model_provenance.json`，
照 W-06 先例。**模型权重不入 corpus.db**（它是 Derived 工具，不是 Source 语料）。

---

## 5. 闸门与判据（先定后测，照 GOAL §3）

**在跑任何 embedding 之前**先写下验收线，不事后合理化：

| 判据 | 阈值 | 测法 | 不过的处置 |
|---|---|---|---|---|
| hit rate | ≥ 80% | 55 条手写转述，embedding top-10 里含 gold 地址 | 记 BLOCKED，G1 维持 PART |
| 建向量耗时 | ≤ 10 分钟 | 5,088 单元全量编码 wall clock | 若超时但 hit rate 达标，仍可行（离线构建） |
| 单次查询延迟 | ≤ 2 秒 | 55 条转述各查一次取中位数 | 若超时但 hit rate 达标，记为"可离线不可在线" |
| 内存峰值 | ≤ 4 GB | `tracemalloc` 或 `psutil` 峰值 | 若超内存但 hit rate 达标，记为"可行但需换机" |
| 红线零回退 | 13 道闸门全过 | §3 的八道 + eval_g1 + eval_g4 + eval_g7 + probe_g8 | 任一回退立刻回退改动，不调闸门 |

**hit rate 80% 的由来**：D-029 那批 55 条手写转述在 FTS5 下 hit rate 78.2%，低于 80% 阬值
故不纳入 eval_g1.json。embedding 若能让**同一批**升过 80%，就把这批题纳入 eval_g1.json 的
新 `retrieval_concept` 类——这才算 G1 概念层落地。**不放宽 80%**（红线第 2 类）。

**对抗性对照**（照 eval_g7 先例）：造 10 条**原文里不存在的**白话转述（如把乾卦爻辞混编，
或用周易外的古文句），embedding 检索必须返回 top-10 里**不含**任何 gold 地址。这测的是
"embedding 会不会因为主题相近而凭空命中"——是 G1 groundedness 在概念层的对应物。

---

## 6. 实施步骤（确认后才执行）

每一步都**跑完 §3 全部闸门**，任一回退立刻回退。

### 6.1 方案 C 先测（零新依赖，约 30 分钟）

1. 新探针 `probes/probe_embed_tfidf.py`：对 5,088 zhouyi 单元建 TF-IDF + TruncatedSVD(512)，
   存 `data/index/knowledge.db` 的 `unit_vector` 表（unit_id, scheme, vec BLOB）。
2. 对 55 条手写转述建同空间向量，cosine top-10，记 hit rate / 耗时 / 内存。
3. 产出 `probes/embed_c_report.json`：基线数字 + 13 道闸门快照。
4. **判点**：hit rate ≥ 80% → 方案 A/B 不做，直接进 6.4 落地；< 80% → 进 6.2。

### 6.2 方案 A 测（新依赖，约 2 小时含下载）

1. `pip install sentence-transformers`（PyTorch CPU 版）。**这是红线第 3 类——本方案确认后
   才执行，照 §7 用户决策点**。
2. 下载 BAAI/bge-small-zh-v1.5，记 provenance。
3. 新探针 `probes/probe_embed_bge.py`：同 6.1 流程，换 bge encoder。
4. 产出 `probes/embed_a_report.json`。
5. **判点**：hit rate ≥ 80% → 进 6.4 落地；< 80% → 进 6.3。

### 6.3 方案 A 不过 → BLOCKED 记录

若 A 也不过 80%：在 `DECISIONS.md` 记 D-031「CPU embedding 可行性否决」，附两份 report。
G1 维持 PART。**不**硬升、不**硬降。照 D-030 先例。

### 6.4 落地（仅当 6.1 或 6.2 达标）

1. `src/guji/embedding.py` 新模块：`build_vectors(corpus, model)` + `search_concept(query, top_k)`。
   向量存 `knowledge.db`（Derived），**不进 corpus.db**。
2. `scripts/eval_g1.py` 新增 `retrieval_concept` 类 scorer，调 `search_concept`。
3. `data/catalog/eval_g1.json` 纳入 55 条转述为 `retrieval_concept` 题（gold 来自 D-029 �批）。
4. `scripts/assess_goals.py` 把 `retrieval_concept` 的 TARGETS 设 0.80。
5. `scripts/build_index.py` 末尾调用 `build_vectors`（离线构建，不阻塞主构建）。
6. 13 陓闸门全过 → commit + push + 台账 §25 记一行。

**不改** `search.py` 的 FTS5 路径——embedding 是**新通道**，不替旧通道。FTS5 仍管逐字层
（retrieval/citation/groundedness），embedding 只管概念层。两条通道并存，照 D-006"两地址并存"
的先例。

---

## 7. 需要用户确认的决策点

本方案有三处需用户显式确认，**不自主执行**：

| # | 决策 | 红线类别 | 默认（不确认时） |
|---|---|---|---|---|
| 1 | 引入 `sentence-transformers` + PyTorch CPU 新依赖（方案 A） | 红线 3（新外部依赖） | **不引入**，只跑方案 C |
| 2 | 下载 BAAI/bge 模型权重（~100 MB）到本机 | 红线 3（联网抓取） | **不下**，只跑方案 C |
| 3 | embedding 向量存 `knowledge.db`（Derived），与 corpus.db 物理隔离 | G8 已落地，属实施细节 | 已是默认，无需确认 |

**最小确认版**：若用户只确认方案 C（零新依赖、零下载），我可立即跑 6.1，30 分钟出基线。
方案 A/B 待用户单独授权才跑。

---

## 8. 风险与否决先例

| 风险 | 先例 | 缓解 |
|---|---|---|---|---|
| embedding 主题相近凭空命中 | G7 grounded_neg 先例 | §5 对抗性对照 10 条伪造转述 |
| 维度膨胀吃满 7.4 GB 内存 | MASTER_PLAN §9 Milvus 否决 | 方案 C 用 SVD 降维，方案 A 用 bge-small(512) 不用 bge-large |
| PyTorch CPU 推理慢到不可用 | 无先例 | §5 单次查询延迟 ≤ 2 秒闸门拦住；超时记"可离线不可在线" |
| 向量与 corpus.db 共生命周期被删 | K-02 先例 | 向量只进 knowledge.db，照 K-02 独立文件先例 |
| 手写 55 条转述本身有偏 | D-029 已沉淀，非新写 | 用已沉淀批，不手写新题 |
| embedding 让 G1 虚升 PASS | G8 空真隔离先例 | retrieval_concept 闸门 0.80 不放宽；不过就 PART |

---

## 9. 复验命令（落地后每步都跑）

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\build_index.py         # 重建（含向量，若 6.4 落地）
.\.venv\Scripts\python.exe scripts\verify_index.py        # 12 项验收
.\.venv\Scripts\python.exe scripts\validate_alignment.py  # >= 1824/1872
.\.venv\Scripts\python.exe scripts\check_quality.py       # 含阳性对照
.\.venv\Scripts\python.exe probes\probe_conservation.py   # ratio 1.0000
.\.venv\Scripts\python.exe scripts\assess_goals.py        # G1–G9
.\.venv\Scripts\python.exe scripts\check_provenance.py    # 0/38
.\.venv\Scripts\python.exe probes\probe_bcv.py            # control cases PASS
.\.venv\Scripts\python.exe scripts\eval_g1.py             # 含 retrieval_concept（若落地）
.\.venv\Scripts\python.exe scripts\eval_g4.py             # 零回退
.\.venv\Scripts\python.exe scripts\eval_g7.py             # 零回退
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py   # 向量在 knowledge.db 不在 corpus.db
.\.venv\Scripts\python.exe probes\probe_embed_*.py        # 产出 report.json
```

---

## 10. 不做什么（照 §9 已否决组件先例）

- **不**用 GPU embedding（无 CUDA，§9 已否决）
- **不**用 Milvus/Neo4j（独立进程，§9 已否决）
- **不**把向量存 corpus.db（K-02 先例，corpus.db 每次构建被删）
- **不**手写新题（D-029 沉淀批，GOAL §4 T1 手写错过两次）
- **不**放宽 80% �闸门（红线 2）
- **不**碰实体抽取/知识图谱（§7 前置：须先确认 differs 不被抹平，本方案不触碰）
- **不**改 FTS5 路径（embedding 是新通道，不替旧通道）
- **不**自主引入 PyTorch/下载模型（红线 3，待用户确认）

---

## 11. 成功判据（整个任务完成的定义）

照 MASTER_PLAN §8 三条 + 本方案特有：

1. **有可执行的复验命令**：`probes/probe_embed_*.py` 产出 report.json + 13 道闸门全过。
2. **有已知阳性对照**：55 条手写转述（已沉淀），含 gold 地址。
3. **断言返回内容不是计数**：hit rate = top-10 含 gold 地址的比例，不是"命中数"。
4. **本方案特有**：若 hit rate ≥ 80%，`retrieval_concept` 进 eval_g1.json，G1 从 PART 升 PASS；
   若 < 80%，记 D-031 否决，G1 维持 PART——**两种结论都合法**，不预设结果。
