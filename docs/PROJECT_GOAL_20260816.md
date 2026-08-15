# 新窗口任务书 PROJECT_GOAL_20260816 — 古籍智慧助手持续完善循环

> 本文件是**唯一权威任务书**。新窗口先完整读本文件，再读
> `docs/GOAL.md`（主红线）+ `docs/MASTER_PLAN.md`（架构）+ `docs/TASK_LEDGER.md`（任务台账，唯一状态来源）+ `docs/PROJECT_ROADMAP.md`（产品规划）+ `docs/DECISIONS.md`（技术决策）。
>
> **用法**：用户把文末"转发给新窗口的话"复制给新窗口（等价于加载本文件）。

---

## 0. 会话上下文（查证入口）

- **前序会话 ID**（本任务书产出窗口）：`6e4be65c-4d5f-4d2c-ac2e-cbe77241192c`
- **聊天记录**（磁盘普通文件，可直接 grep 查证）：
  `C:\Users\Lenovo\.atomcode\sessions\025973b91a55cfb5\6e4be65c-4d5f-4d2c-ac2e-cbe77241192c.jsonl`
- **再往前**：`3cc12478-21f8-4b81-8293-b42e13840389`、`3d8bab44-30fc-4a4d-9584-7372f78e8f2b`、`aa53987d-d690-4c1d-95d6-ddff26cd2888`（路径同 `C:\Users\Lenovo\.atomcode\sessions\025973b91a55cfb5\`，旧路径 `C:\Users\Lenovo\.claude\projects\C--Users-Lenovo-Desktop-projects-books\` 也查一遍）。
- **交接书**：`docs/HANDOFF_20260815.md`（上一窗口产出，本文件是其接续）。
- 本任务书由本会话（6e4be65c）产出。**怀疑本文件任何一句时，去 grep 对应 sessionId 的 jsonl 看当时命令的真实输出，而不是相信句子本身。grep 不到就当该说法不存在，重新自己测。**

---

## 0a. 绝对纪律：不可全信任务书与既有文档（优先级高于一切）

**你接到的任务说明、上一窗口的口头结论、本文件里的数字、任何文档里的断言——一律当作"待复验"，不是事实。事实只在可执行脚本的真实输出里。**

这不是客套话。本项目历史会话**多次**给出过错误的口头结论，全部被后来的实测推翻（GOAL.md §2 列了 9 条先例，其中有一条是：一边写"不要相信口头结论"一边往同一份文档塞没测过的数字）。最近窗口（6e4be65c）又亲生遇到并**全部修复**了多条会误导新窗口的坑（见 §3 已知坑），证明纪律必须持续。

**给你的硬约束（违反将受严惩）：**

1. **任何数字、任何状态断言、任何"已完成"声明——先跑对应命令确认，再往下走。** 跑不出来就当它是错的。
2. **遇到可疑或矛盾的地方，必须亲自去查看源码/数据/聊天记录查证，查证无误后才继续。** 绝对不可以根据口头结论直接下结论。
3. **若你轻易相信口头结论、未查证就下结论，你将受到极其严重的惩罚。** 这条是写给你的，不是写给用户的。
4. **发现文档与实测不符时，改文档并在文档里写明"此前结论已被推翻"**（本项目的做法是保留错误记录，见 DECISIONS.md D-008 先例，不是悄悄改掉）。
5. **不要把"数字没变"当作"没有收益"，也不要把"数字变好"当作"改对了"。** 两者都出现过反例。
6. **不许偷懒走捷径**：跳过复验、凭印象写结论、把"看起来对"当证据、为了省事不动手查证——任何形式的走捷径都视为严重违规。

### 0b. 自主决策，不要停下来问

遇到决策：自己列 2–3 个方案，用本仓库实测数据比较，选最优直接执行，把比较过程写进 `docs/DECISIONS.md`。例外只在红线三类（§5）：那不是"停下来问"，是"跳过并记录，直接开始下一个任务"。

**关于 commit 和 push**：完成一个有意义的单元（一个缺口修复、一个优化完成）即 commit；用户已授权 push 到 `github.com/YZml1507/books` main（代理 `127.0.0.1:7897`）。commit message 末尾加 trailer（见下方模板）。**不要停下来问"要不要 commit/push"**，自己判定后直接执行。

```
Co-Authored-By: AtomCode (GLM-5.2) <noreply@atomgit.com>
```

---

## 1. 当前实测状态（先自己复验，不要相信这张表）

复验命令（照 GOAL.md §3，任一改动后必须全过；注意顺序：`check_quality.py` 必须在 `build_index.py` **之前**跑）：

```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe scripts\check_quality.py
.\.venv\Scripts\python.exe scripts\build_index.py
.\.venv\Scripts\python.exe scripts\verify_index.py
.\.venv\Scripts\python.exe scripts\validate_alignment.py
.\.venv\Scripts\python.exe probes\probe_conservation.py
.\.venv\Scripts\python.exe scripts\assess_goals.py
.\.venv\Scripts\python.exe scripts\check_provenance.py
.\.venv\Scripts\python.exe probes\probe_bcv.py
.\.venv\Scripts\python.exe scripts\eval_g1.py
.\.venv\Scripts\python.exe scripts\eval_g4.py
.\.venv\Scripts\python.exe scripts\eval_g7.py
.\.venv\Scripts\python.exe probes\probe_g8_isolation.py
.\.venv\Scripts\python.exe probes\probe_booksec.py
```

本窗口（6e4be65c）末尾实测快照（**全部 PASS，零回退**）：

```
works 45 · units 51,636 · corpus.db 46.3 MB
scheme: bcv 35,787 · zhouyi 5,088 · yilin 5,032 · None 3,457 · booksec 819 · play 817 · euclid 174
命理书 27 部（旧 20 部 KR3g + 新 7 部：兰台妙选/命理探原/命理约言/三命通会/五行大义/五行精纪/子平真诠）
闸门    check_quality PASS · build_index PASS · verify_index ALL PASS · validate_alignment 1824/1872 = 97.4%
G 判据  assess_goals PASS 9 · PART 0 · FAIL 0（G1–G9 全 PASS）
其余    probe_conservation ratio 1.0000 · check_provenance 0/38 · probe_bcv PASS · eval_g1/g4/g7 全 PASS · probe_g8 PASS · probe_booksec PASS
web     /api/bazi 200 · /api/search 200（3 hits）· /api/liuyao 200（本卦豐→变卦乾）· /api/huangli 200（建除=开）· /api/qiming 200（缺木→林/森/桐/柏/栋）· /api/external/news 200（2 源）
打包    dist/books_app.exe 218 MB（PyInstaller 单文件，含 torch+fastapi+uvicorn）
git     8891be7 feat(p3/p4/pack): P3 六爻占卜+黄历择日 · P4 五行起名 · PyInstaller 单文件打包
        6dc77d9 feat(web/bazi/p2): P1 读书网页化 + bazi 大运起运 + P2 命理语料落盘
```

**以上数字一律要自己复跑确认。** 跑不出对应命令就当该说法是错的。

---

## 2. 项目全貌与已完成工作

### 2.1 项目定位

古籍智慧助手：一个桌面入口（自动开浏览器），既能**读书**（检索/比对/注家/研究线程，CLI + web 已落地），也能**算命/算八字**（排盘/运算/古籍依据/大白话解读，web 已落地），扩展占卜/择日/起名/外部资讯（P3-P5 已落地）。

### 2.2 已完成（先自行复验，尤其 web 相关）

| 模块 | 说明 | 状态 |
|---|---|---|
| web_launcher.py | pythonw 无弹窗启动 + 杀旧实例 + 自动开浏览器 + 关浏览器自动关服务 | ✅ 确定性注入验证 PASS |
| 闸门 | 13 道闸门 | ✅ 零回退（见 §1 快照） |
| 读书（P1） | web/app.py 新增 /api/search /api/addr /api/compare /api/works /api/stats /api/threads，复用 src/guji；前端「古籍读书」tab 五子视图 | ✅ CLI/web 10 例一致 |
| 八字（核心） | bazi.py 排盘 + bazi_calc.py 运算层（十神/五行/冲合/流日/范围/大运）+ bazi_lookup.py 命理书检索 + llm_reader.py LLM 解读 | ✅ |
| 命理语料（P2） | 27 部命理书（旧 20 部 KR3g + 新 7 部子平经典），"大运/起运/用神/调候/格局/行运/交运"全部从 0 命中→有命中 | ✅ |
| 六爻占卜（P3） | liuyao.py 铜钱法/时间起卦，本卦/变卦/动爻；/api/liuyao + 前端「六爻占卜」tab | ✅ 坐标层完成，**运算层未做**（见 §4 缺口 4） |
| 黄历择日（P3） | huangli.py 建除/二十八宿/彭祖百忌；/api/huangli + 前端「黄历择日」tab | ✅ 三层完成，**神煞层未做**（见 §4 缺口 5） |
| 五行起名（P4） | qiming.py 部首五行表选字；/api/qiming + 前端「五行起名」tab | ✅ |
| 外部资讯（P5） | external.py feedparser，BBC 代理 + Solidot 直连；/api/external/news + 前端「最新消息」面板 | ✅ |
| PyInstaller 打包 | books_app.spec，dist/books_app.exe 218MB 单文件 | ✅ 构建成功，**端到端实机验证未做**（见 §4 缺口 3） |
| browser-use | vendor/browser-use-main/ 已解压，playwright + 本机 Edge 最小链路跑通 | ✅ 最小链路，完整 Agent 化待 LLM key |

### 2.3 既有核心模块（勿动，除非有实测依据）

- 读书：`src/guji/`（search/bazi_lookup/answer/research_thread/compare/knowledge 等）+ `scripts/ask.py`；语料 45 部 / 51,636 单元，六种地址体系（zhouyi/bcv/yilin/booksec/play/euclid）。
- 八字：`src/guji/bazi.py`（排盘）、`lunar.py`（农历↔公历 1900-2100）、`bazi_calc.py`（十神/五行/冲合刑害/流日流时/范围/大运）、`bazi_lookup.py`（27 部命理书 FTS+bge）、`llm_reader.py`（结论优先解读）、`history.py`（data/history.db）。
- 新功能：`liuyao.py`（六爻）、`huangli.py`（黄历）、`qiming.py`（起名）、`external.py`（RSS）。
- web：`web/app.py`（FastAPI :8123）+ `web/static/index.html`（六 tab：八字排盘/古籍读书/六爻占卜/黄历择日/五行起名/最新消息）；LLM KEY 只在服务端 llm_config.json（已 gitignore）。
- 打包：`books_app.spec` + `web_launcher.py`（frozen 分支：线程 in-process 跑 uvicorn）。

---

## 3. 已知坑（实测过，别再踩，但**仍要自己复验**）

| 坑 | 实测结论 | 处置 |
|---|---|---|
| e2e_launcher_test.py | Windows 上 netstat/tasklist 热循环 + 测试自身 socket 探测污染监控判定 → 反复超时，**是脚本竞态不是 launcher 缺陷** | 已删除；验证用全注入确定性脚本（不落盘 scripts/） |
| `github.com/*.atom` | 本网络代理与直连均 SSL UNEXPECTED_EOF | 不预置 github commit feed |
| `api.github.com` | 直连可用但共享 IP 易 403 rate limit | 不预置，留用户自定义 |
| `www.gov.cn` RSS | 404 | 删除 |
| pip 装大包走 7897 代理 | 会 SSL 中断（playwright 38MB 下到一半断） | 换清华镜像 `-i https://pypi.tunaartsinghua.edu.cn/simple` |
| playwright 浏览器内核 | 下载大且慢 | 用本机已装 Edge：`chromium.launch(channel="msedge")` 免下载内核 |
| 报错 "stream timeout after partial response" / "响应中断" / "unexpected EOF" | AtomCode 运行时保护机制：单次工具调用/响应超阈值即截断，**不自动重放**（避免重复副作用） | �拆小命令、显式 timeout、大文件分段读、脚本内自管服务生命周期；新开窗口不根治 |
| 后台 uvicorn 随 bash 命令结束被回收 | `(cmd &)` 起的服务在命令返回后消失，导致 playwright goto 报 ERR_CONNECTION_REFUSED | 测试用"脚本内 Popen 起 uvicorn → 用完 terminate"自管生命周期 |
| `logs/p2_tmp/` 82MB 临时下载 | 上个窗口为 P2 下载的三个 git 仓库（mingli/mymmsc/xuanxue），不该入库 | 已 gitignore（logs/ 整体） |
| `browser-use-main.zip` 在根目录 | 不该入库 | 已 gitignore（browser-use-main/ + .zip） |
| 任务书断言 "clean() 里加 &KR0658;→虩 解析" | 实测推翻：clean() 不参与 unit.text/FTS 生成链，改 clean() 对检索无效 | 修复层实测选定 build() 的 zhouyi FTS 喂入点（ingest.py:631） |
| 任务书断言 "Euclid 6 BOOK 170 proposition 已入索引" | 实测推翻：`SELECT count(*) FROM unit WHERE work_id='euclid-elements'` = 0 | Euclid 路由未接线，ingest.py:665 的 `if not txt_files: continue` 前置要求 .txt，但 euclid-elements/ 只有 html/epub |
| 任务书断言 "probe_bcv.py 永远返回 0" | 实测：它曾被列为八道红线之一却永远返回 0，包括打印"56/66 卷"那一次 | 已加 sys.exit(1)，现在真的会 FAIL |

---

## 4. 你的剩余任务：5 个实测缺口（按优先级，理由见各条）

### 缺口 1：命理语料的"核心子平四书"仍有遗漏（优先级最高）

实测发现：
- ✅ "大运/起运/用神/调候/格局/行运/交运" 全部有命中
- ❌ 但 **滴天髓**（任铁樵注本）和 **穷通宝鉴** 没有独立入库

`logs/p2_probe_report.md` 显示上个窗口勘查过 `Banny-Gao/mingli-research`（含滴天髓阐微/穷通宝鉴 source.md），但只落盘了 7 部 txt，**滴天髓和穷通宝鉴没拉全**。滴天髓是子平派仅次于渊海子平的核心经典，穷通宝鉴是"调候用神"的唯一权威古籍依据。

| 任务 | 产物 | 验证 |
|---|---|---|
| A1. 拉 `Banny-Gao/mingli-research`，提取滴天髓 + 穷通宝鉴 source.md | `data/raw/ditiansui/ditiansui_001.txt` + `data/raw/qiongtongbaojian/qiongtongbaojian_001.txt` | 文件存在 + 行数 > 100 |
| A2. 过三道判定，入库建索引 | manifest 条目 + build_index | verify_index ALL PASS |
| A3. bazi_lookup.MINGLI_WORKS 追加 2 本 | 改 MINGLI_WORKS | 检索"滴天髓/穷通/调候"有命中 |

拉取方式：走 7897 代理 `git clone`，过三道判定（文献 vs 生成物 / 版权分层 / 白话经文分离），**只入 source.md 层**（原文），不要 interpretation.md（现代注解，版权风险）。

### 缺口 2：PyInstaller exe 体积过大（218MB）

实测：`dist/books_app.exe` 218MB，原因是 torch（sentence-transformers 依赖）被打进去了。

| 方案 | 体积 | 代价 |
|---|---|---|
| 拆分 core exe + bge 插件 | core < 50MB | 两个文件，稍复杂 |
| 按需加载 torch（lazy import） | core < 50MB | 首次 bge 检索稍慢 |
| 不优化 | 218MB | 太大 |

### 缺口 3：exe 未做端到端实机验证

`dist/books_app.exe` 构建成功，但**还没在干净的 Windows 环境双击运行验证**。需要确认：双击无弹窗 → 自动开浏览器 → 关浏览器自动退出。

### 缺口 4：六爻占卜的"纳甲/六亲/世应/六神"运算层未实现

当前 `liuyao.py` 只做了**本卦/变卦/动爻**的坐标计算（纯卦象层），但没有：
- 纳甲（天干地支配卦爻）
- 六亲（父母/兄弟/妻财/官鬼/子孙，按八宫归属）
- 世应（世爻/应爻定位，每宫八卦世爻位不同）
- 六神（青龙/朱雀/勾陈/螣蛇/白虎/玄武，按日干起）

这些是六爻断卦的**核心运算层**，缺它们等于"起了卦但没法断"。

### 缺口 5：黄历的"神煞"层未实现

当前 `huangli.py` 做了建除/二十八宿/彭祖百忌三层，但传统黄历还有：
- 天德/月德/天赦（吉神）
- 劫煞/灾煞/月厌（凶煞）
- 驿马贵人（命贵人位）

没有神煞层，黄历宜忌的**判定维度不够**，宜忌表会过于粗略。

---

## 5. 你的工作流程：审查-修复-优化 循环（用户明确要求，不得偏离）

**用户原话**："先将当前任务写为一个文档内容（即本文件），这个任务文档结束后，再次对整个项目做一个审查，看看有没有什么问题，如果有问题，则问题进入台账和修复列表并解决掉，还有就是修复途中如果发现新的问题，新的问题也要入台账和任务列表并被解决掉，如果问题都被解决掉后，再去思考整个项目是否还有什么地方值得再去优化和完善的地方，然后再写一份优化文档出来，优化文档写出来后再去对项目进行优化。然后就一直像我刚刚说的那个流程一样，反复循环，除非我明确给出提示，否则不得停止。"

用流程图表示：

```
[阶段 0] 读本任务书 + 项目文档（GOAL/MASTER_PLAN/TASK_LEDGER/ROADMAP/DECISIONS）
    ↓
[阶段 1] 先把 §4 的 5 个缺口逐个解决（按优先级 A→B→C→D→E）
    ↓  每解决一个即写 TASK_LEDGER.md（状态/复验命令/产物）+ commit
[阶段 2] 缺口全完后，对整个项目做一次完整审查
    ↓  审查维度：① 13 道闸门是否真过 ② web 6 tab 是否真能用 ③ 文档与实测是否一致 ④ 红线是否被破 ⑤ 边界输入是否报错
    ↓  发现的问题 → 进 TASK_LEDGER.md（新增条目，状态 TODO）+ 进修复列表
[阶段 3] 逐个修复审查发现的问题
    ↓  修复途中发现的新问题 → 也入台账 + 修复列表，一并解决
    ↓  每修复一个即写 TASK_LEDGER.md + commit
[阶段 4] 问题全完后，思考"还有什么地方值得优化和完善"
    ↓  写一份优化文档（docs/OPTIMIZATION_<日期>.md），列出候选优化项 + 实测比对 + 优先级
    ↓  自主选最优直接执行，不停下来问
[阶段 5] 执行优化文档里的优化项
    ↓  每完成一个即写 TASK_LEDGER.md + commit
    ↓
[回到阶段 2] 优化完后再次审查 → 修复 → 优化 → 审查 → ... 反复循环
    ↓  **除非用户明确给出停止提示，否则不得停止**
```

**关键纪律**：
- 阶段 1 的 5 个缺口是**起点**，不是终点。缺口做完后必须进入阶段 2 的审查。
- 阶段 2-5 是**无限循环**，不要做完缺就停下汇报。每轮循环自己 commit + push。
- 阶段 2 的审查必须**实测**，不能"看起来没问题"。每个审查维度都要跑命令或读代码确认。
- 阶段 4 的优化文档必须**有实测数据支撑**，不能"我觉得该加 X"。每条优化项要列 2-3 个方案 + 实测比对。

---

## 6. 红线（不变，照 GOAL.md §3）

1. **运算层 = 纯坐标计算**：排盘/大运/卦象/黄历宜忌全是本地代码按写死规则表算出，可核验；summary 是模板拼接，不产生"新文本"。
2. **LLM = 生成文本**：结论优先大白话解读，标注模型来源，不落语料库（历史库 D-039 授权除外），与引文分离展示。
3. **入库三道判定**：文献 vs 生成物 / 版权分层 / 白话与经文分离——任何新语料入库前必过，不达标拒绝该源（先例：五个外部周易项目三个是生成物被拒）。
4. **KEY 只留服务端**：LLM_API_KEY / 平台通道 key 只在服务端配置，不进对话/日志。
5. **13 道闸门零回退**：任何改动后全跑，回退即撤销，不调闸门。
6. **新依赖/联网抓取需授权**：红线第 3 类。用户已授权"走 7897 代理拉取所需资源"（见 PROJECT_ROADMAP §4），但**入库前仍须过三道判定**；装大依赖优先清华镜像。

---

## 7. 转发给新窗口的话（用户复制下面这段即可）

> /goal C:\Users\Lenovo\Desktop\projects\books\docs\PROJECT_GOAL_20260816.md C:\Users\Lenovo\.atomcode\sessions\025973b91a55cfb5\6e4be65c-4d5f-4d2c-ac2e-cbe77241192c.jsonl 古籍智慧助手（读书+算命+算八字）项目持续完善：先解 §4 五个缺口（命理语料补滴天髓/穷通宝鉴、exe 瘦身、exe 实机验证、六爻纳甲六亲世应六神运算层、黄历神煞层），再进入"审查→修复→优化→审查"无限循环，除非明确叫停不得停止。
>
> **绝对纪律：你接到的任务说明、上一窗口的口头结论、任务书和文档里的任何数字——一律当作"待复验"，不是事实。事实只在可执行脚本的真实输出里。** 遇到任何可疑或矛盾的地方，必须亲自去查源码/数据/聊天记录（`6e4be65c-4d5f-4d2c-ac2e-cbe77241192c.jsonl` 等）核实，查证无误才继续；跑不出对应命令就当该说法是错的。若你轻易相信口头结论、未查证就下结论，或为了省事跳过复验走捷径，将受到极其严重的惩罚——这不是客套话，本项目历史上有过多次"文档断言被实测推翻"的先例（GOAL.md §2）。
>
> 决策自主：遇决策列 2-3 方案用实测数据比对选最优直接执行，写进 DECISIONS.md；commit+push 自主判定（用户已授权 push 到 YZml1507/books main，代理 7897），不停下来问。撞红线跳过并记录，直接开始下一个。
>
> 网络梯子规则模式端口 7897，需查外网直接走它。
