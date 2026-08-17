# 项目路线图 PROJECT_ROADMAP — 读书 + 算命 + 算八字 完整产品规划

> 状态：方案（2026-08-15，会话 3cc12478）。用户需求还原：
> ① 桌面启动无弹窗、自动开浏览器、关浏览器后服务自动关闭（**已实现** web_launcher.py）；
> ② 项目最初目标是**帮我读书**，算命/算八字只是其中一部分——要从产品全局规划；
> ③ 梯子已开，走代理 `127.0.0.1:7897`，需要什么直接拉取；
> ④ 可借助 Agent-Reach 平台通道（Twitter/GitHub/RSS 等）获取最新消息、browser-use 控制浏览器。
> 本文档为完整规划：现状盘点（实测）→ 产品愿景 → 分阶段方案 → 依赖拉取清单 → 验证标准 → 红线。

---

## 0. 一句话定位

把「古籍研究基础设施」（GOAL.md G1–G9）变成**一个统一入口的桌面应用**：既能**读书**
（检索/比对/注家/研究线程），也能**算命/算八字**（排盘/运算/古籍依据/大白话解读），
未来扩展占卜、择日、起名，并通过 Agent-Reach 通道获得外部最新资讯。

---

## 1. 现状盘点（全部实测，非口头）

### 1.1 读书模块（项目原始目标，已网页化——2026-08-16 R25b/R26b/R29b 落地）

| 能力 | 实现 | 实测状态 |
|---|---|---|
| 语料 | 47 部书 / 62,109 单元（R20b 加道家 3 部） | bcv 35,787 · zhouyi 5,088 · yilin 5,032 · booksec 4,247 · play 6,512 · euclid 649 · None 4,794（scheme 分布以 `SELECT scheme, count(*) FROM unit GROUP BY scheme` 实测为准，R56b 刷新） |
| 检索 | FTS5 + bge 双路径（`src/guji/search.py`/`bazi_lookup.py`） | eval_g1 100% 命中 |
| 引用 | 每结果带 文件+页锚点，G2 字符串可核验 | verify_index ALL PASS |
| 回答 | `answer.py` G7：有据才答，无据拒答 | eval_g7 PASS（FABRICATIONS 0） |
| 比对 | `compare` 跨版本同址比对 + 两书对照 compare_works | 繫辞 1824/1882 = 96.9%（5 部書实测汇总，以 `scripts/validate_alignment.py` 为准；R58b 刷新） |
| 研究线程 | `research_thread.py` G9 跨会话恢复 + web POST/GET | 已落地，web 可记可读 |
| 入口 | **web 古籍读书面板 9 个研究 tab**（检索/深度研究/定位/比对/书目/线程/读书/两书对照/概念研究）+ CLI 同源 | R25b/R26b/R29b 已接线 |

**读书能力已网页化**（2026-08-16 核实）：Book Study 结构地图/章节阅读、
两书对照、概念研究、Book Summary、记入线程（POST /api/threads）全部在
`web/static/index.html` 可用；MCP 侧 12 工具同源发布（见 MASTER_PLAN
Agent 侧段）。

### 1.2 算命 / 算八字模块（2026-08-15 建成）

| 模块 | 功能 |
|---|---|
| `bazi.py` | 公历排盘（Meeus 黄经节气），四柱/日主/纳音/大运方向/起运岁数/大运干支 |
| `lunar.py` | 农历↔公历（1900-2100，5 春节+4 闰月基准全过） |
| `bazi_calc.py` | 运算层：十神/五行/冲合刑害/流日流时/**日期范围**/**生平大运表** |
| `bazi_lookup.py` | 18 部命理书 FTS+bge 检索（KR3g 9 + P2 子平 9，R20b 扩充；书名显示已修） |
| `llm_reader.py` | 结论优先大白话解读（禁止"无法计算"式回答，已实测达标） |
| `history.py` | 历史记录库 `data/history.db` + API + 前端面板 |
| web 端 | 公历/农历切换、单日/一段日期/一生三种 scope、历史回看 |

**缺口**：命理语料仅 9 部，**无子平经典**（渊海子平/滴天髓/子平真诠/穷通宝鉴）——
（已由 R20b 落地：9 部子平经典入库，见 P2 节 ✅；本行 R72b 标注防误读）
~~实测"大运/起运/行运/交运"在现有语料 0 命中~~ → **已被 R20b 推翻**（本行
R76b 复核）：实测 corpus.db 含 大运 48 单元、行运 120、起运 3、交运 6，
来源 ditiansui/mingli-tanyuan/sanming-tonghui/mingli-yueyan（子平经典，
P2 节）——"0 命中"是 R20b 前旧结论，大运已有古籍佐证；运算层自算保留。

### 1.3 启动体验（本轮已实现）

`web_launcher.py`：pythonw 静默运行 → 自动杀占用 8123 的旧实例 → 起 uvicorn →
端口就绪自动开浏览器 → 监控浏览器进程，全部浏览器退出且无连接持续 60s 后自动关服务。
`start_web.bat` 与桌面快捷方式已改为指向 pythonw（无弹窗）。验证：启动链路日志全通、
关闭判定逻辑 4 场景单测全过。

---

## 2. 产品愿景：一个入口，三件事

```
                古籍智慧助手（一个桌面入口，自动开浏览器）
                          │
        ┌─────────────────┼─────────────────┐
      读书                算命                算八字
  检索原文/跨版本比对/     排盘+运算+古籍依据   农历/公历、单日/范围/一生
  注家比较/研究线程        +大白话解读          大运流年、历史回看
        └─────────────────┼─────────────────┘
                 未来扩展（本路线图 P3-P5）
         六爻占卜 · 黄历择日 · 五行起名 · 最新消息（Agent-Reach 通道）
```

设计原则（延续项目红线）：
- **程序负责计算，LLM 负责表达**——坐标/卦象/黄历由本地代码算出（可核验），LLM 只做白话解读（标注生成）。
- **引用与生成分离**：古籍引文带出处，LLM 文本标注模型来源，永不混同。
- **原文与白话分离**：入库前剥离白话/注解层，读者要原文就给原文（GOAL §2 红线）。

---

## 3. 分阶段方案

### P0 启动体验收尾（已完成）
- ✅ web_launcher.py 静默启动 + 杀旧实例 + 自动开浏览器 + 关浏览器自动关服务
- ✅ start_web.bat / 桌面快捷方式指向 pythonw
- ✅ 本窗口确定性验证 PASS（kill_stale → uvicorn → 端口就绪 → 开浏览器 → 浏览器退出 → 自动关服务 → exit 0）
- ✅ 临时测试文件 e2e_launcher_test.py 已删除（其 Windows 竞态由确定性注入验证替代）
- ⏳ 唯一待办：用户双击图标实机确认"无弹窗 + 自动开 + 自动关"

### P1 读书模块网页化（最高优先——回归"帮我读书"）✅ 已完成（2026-08-16 R25b/R26b/R29b）

**目标**：把 CLI 的读书能力搬进现有 web（与算命同一入口）。
- 已落地（并入 `web/static/index.html` 多 tab，非独立 read.html）：
  - 全文检索框（`ask.py search` 同内核 search.py）→ 结果列表带书名/层/页锚点/可展开原文
  - 地址定位 `addr`（卦/爻/卷章，支持 zhouyi/bcv/yilin/booksec/euclid 五种地址体系）
  - 跨版本比对 `compare` 视图（同址多版本并排）
  - 研究线程 `research_thread` 视图（G9 线索列表/查看，POST /api/threads 写入）
  - 后续轮次追加：读书（structure/chapter）、两书对照、概念研究、Book Summary
- `web/app.py` 路由：`GET /api/search`、`GET /api/addr`、`GET /api/compare`、
  `GET /api/threads`、`POST /api/threads`、`/api/bookstudy/*`、
  `/api/compare_works`、`/api/concept`、`/api/bookstudy/summary`（复用
  src/guji，只编排不复制逻辑）
- **验证**：CLI 与 web 调同一检索函数，抽查一致；13 道闸门零回退（每轮全绿）。

### P2 命理语料扩充（子平经典入库，走 7897 代理）✅ 已完成（R20b：9 部术数书入库，bazi_lookup MINGLI_WORKS 引用）
**目标**：补齐"大运/格局/用神"的古籍佐证（现有语料 0 命中）。
- 拉取源（已联网核实，均含**原文**，且原文/解读分离正合红线）：
  - `github.com/Banny-Gao/mingli-research`：滴天髓阐微（任铁樵注）/子平真诠（徐乐吾评）/
    三命通会/穷通宝鉴/渊海子平/千里命稿/紫微斗数全书，目录结构
    `books/<书名>/articles/<篇目>/source.md`（原文）与 `interpretation.md`（解读）分离
  - `github.com/youngzs/xuanxue`：mkdocs 玄学库（渊海子平原文/滴天髓原文/子平真诠/穷通宝鉴/神煞大全等）
  - `github.com/mymmsc/books`：`国学/八字-渊海子平.txt` 单文件
- 入库流程（照 GOAL §2 三道判定 + ingest 管线）：
  1. 判定文献 vs 生成物：只取能追溯到印本/底本的原文部分（mingli-research 的 source.md 合此）
  2. 版权分层：四库/公版原文可入 Source；在世作者解读一律**只进 Derived 或剥离**，不混入 Source
  3. 白话/注解与经文分离：只建原文层（layer=正文/注按来源标注）
  4. 建索引 → `bazi_lookup.MINGLI_WORKS` 追加新书 id → 检索词表补充（大运/起运/用神/格局/调候）
- **验证**：检索"大运/起运/用神/调候"命中从 0 → 有命中；eval_g1/g7 不回退；13 道闸门零回退。
- **风险**：若某库含在世作者注释混排，按先例剥离后再考虑，不达标即拒绝该库（不硬凑）。

### P3 新功能：六爻占卜 + 黄历择日（本地计算，参照 YiSphere 架构）✅ 已完成（liuyao/huangli tab 接线，R53b 端点 standing 自测覆盖）
**目标**：扩展"算命"到占卜与择日，延续"程序计算 + LLM 表达"。
- 六爻：本地实现三枚铜钱/时间起卦（纯计算：本卦/动爻/变卦，64 卦表复用 zhouyi 语料），
  卦象坐标 + 古籍引文（已入库的 周易 卦爻辞）+ LLM 白话解卦。
- 黄历择日：本地实现宜忌计算（建除十二值/二十八宿/彭祖百忌，规则写死可核验），
  输入事项（婚嫁/开业/出行…）→ 给出某日宜忌坐标 → LLM 白话说明。
  - 参考（联网核实）：`0xfnzero/YiSphere`（计算+LLM 架构）、`wouhao/lunar-calendar-service`
    （基于 lunar-python 的万年历，公农历/节气/宜忌/吉日）、`baranwang/mcp-tung-shing`（黄历 MCP）。
  - 本仓库已自实现农历表（lunar.py），可独立完成公农历/节气；宜忌规则表需新写（纯数据，写死可核验）。
- 前端：新增"占卜"与"择日" tab；历史库扩展 `history.db` 记录卦象/黄历查询（照 D-039 授权模式）。
- **验证**：起卦坐标与标准表对照（64 卦全对）；择日规则与权威黄历抽查 10 日一致；闸门零回退。

### P4 五行起名（可选，依赖 P2 语料）✅ 已完成（qiming tab 接线，R53b 端点 standing 自测覆盖）
- 输入：姓氏 + 出生（八字）→ 用 bazi_calc 五行缺行 → 从候选字库（部首五行表，写死数据）筛选补缺字 →
  给出字+五行+寓意坐标，LLM 白话解释。纯计算选字，不生成"新命理文本"。

### P5 外部资讯通道（Agent-Reach 平台 + browser-use）
**状态：已落地（2026-08-15 晚，D-042）**
**目标**：读书/算命之外，获取"最新消息"（用户明确要求纳入）。
- 探索 `Agent-Reach-main.zip`（已解压查看：`agent_reach/channels/` 含
  twitter/github/rss/reddit/youtube/exa_search 等平台通道，需各自 API key/配置）：
  - 优先级：`rss` 通道（零 key，可订阅新闻/古籍整理动态）、`github` 通道（跟进子平经典新整理版）
  - 其余平台（twitter/reddit 等）需 key，作为可配置项，不在首版承诺
- 探索 `browser-use-main.zip`（browser_use，Python 库，pyproject 597 文件）：
  - 用途：需要"看网页渲染结果"时（如抓取动态渲染的命理网站/古籍在线阅读站）由 LLM 驱动浏览器操作
  - 依赖 playwright（需 `pip install` + 浏览器内核下载，走 7897 代理），**列为 P5 实验项**，
    红线第 3 类（新依赖）需用户授权后执行——本路线图即授权申请
- ✅ RSS 通道已实现（src/guji/external.py + GET /api/external/news + 前端「最新消息」面板）：BBC 中文（代理）与 Solidot（直连）各 8 条实测成功；github.com/*.atom 本网络 SSL 中断、api.github.com 共享 IP 限流、gov.cn RSS 404 均实测否决不预置
- ✅ browser-use 最小链路跑通：playwright 已装（清华镜像），chromium.launch(channel="msedge") 用本机 Edge 免下载内核打开本地 8123 页面，截图 logs/playwright_local_sample.png；完整 Agent 化（LLM 驱动）需 browser-use-core 全家桶 + LLM key，列为后续可选

---

## 4. 依赖与资源拉取清单（走代理 127.0.0.1:7897）

| 阶段 | 资源 | 形态 | 用途 |
|---|---|---|---|
| P2 | Banny-Gao/mingli-research | git clone（代理） | 子平四书原文（source.md 分离） |
| P2 | youngzs/xuanxue | git clone（代理） | 渊海子平/滴天髓原文补充 |
| P2 | mymmsc/books | git clone 或 raw 单文件 | 渊海子平 txt 备选 |
| P3 | YiSphere | 仅参考（架构思路） | 计算+LLM 表达先例 |
| P3 | lunar-python / 黄历 MCP 服务 | pip / 参考 | 宜忌规则对照（本仓库 lunar.py 已自实现，仅对照） |
| P5 已装 | feedparser 6.0.14 | pip（7897 代理安装失败，换清华镜像成功） | RSS 解析（src/guji/external.py） |
| P5 | Agent-Reach（用户提供 zip） | 本地已解压（vendor/Agent-Reach-main/） | 思路参考；零 key 的 RSS 通道已由 src/guji/external.py 落地（feedparser） |
| P5 | browser-use（用户提供 zip） | 本地已解压（vendor/browser-use-main/）+ playwright 已装 | 最小链路已跑通（Edge 打开本地页）；完整 Agent 待 LLM key |
| 通用 | pip 新依赖 | `pip install -i` 代理 | 按阶段需要（如 playwright） |

红线提示：新增外部依赖/联网抓取属 GOAL §3 第 3 类，需授权——**用户本会话已授权**
（"梯子已打开，走 7897，需要什么直接去搜索拉取"），本清单即授权执行项，但**入库前仍须过
三道判定**（文献/版权/白话分离），不达标不硬入。

---

## 5. 每阶段验证标准（先定后测，闸门不可放宽）

| 阶段 | 验证 |
|---|---|
| P0 | 双击快捷方式：无弹窗；自动开浏览器；关浏览器 ≤60s 服务自动退出（进程消失） |
| P1 | web 检索/比对/研究线程与 CLI 同一内核输出一致（抽 10 例）；verify_index/assess_goals 零回退 |
| P2 | 新增书入索引；检索 大运/起运/用神/调候 从 0 命中 → 有命中；eval_g1/g7 PASS；13 道闸门零回退 |
| P3 | 64 卦起卦与标准表全对；黄历宜忌抽查 10 日一致；history 扩展可用；闸门零回退 |
| P4 | 五行缺行 → 候选字五行补缺正确；闸门零回退 |
| P5 | RSS 拉取 1 源成功展示；browser-use 本地样例跑通 |

闸门定义：`scripts/build_index.py` + `verify_index.py` + `validate_alignment.py` +
`check_quality.py` + `probe_conservation.py` + `assess_goals.py` + `check_provenance.py` +
`probe_bcv.py` + `eval_g1/g4/g7.py` + `probe_g8_isolation.py`（13 道，任一回退即回退改动）。

---

## 6. 红线遵守（不变）

1. **运算层 = 纯坐标计算**：排盘/大运/卦象/黄历宜忌全是本地代码按写死规则表算出，可核验；
   summary 是模板拼接，不产生"新文本"。
2. **LLM = 生成文本**：结论优先白话解读，标注模型来源，不落语料库（历史库 D-039 授权除外），
   与引文分离展示。
3. **入库三道判定**：文献 vs 生成物 / 版权分层 / 白话与经文分离——任何新语料入库前必过，
   不达标拒绝该源（先例：五个外部周易项目三个是生成物被拒）。
4. **KEY 只留服务端**：LLM_API_KEY / 平台通道 key 只在服务端配置，不进对话/日志。
5. **13 道闸门零回退**：任何改动后全跑，回退即撤销，不调闸门。

---

## 7. 实施顺序建议（下一窗口可直接开工）

1. **P1 读书网页化**（回归最初目标，无新依赖、零风险，复用现有 src/guji）
2. **P2 命理语料扩充**（走 7897 拉 mingli-research，过三道判定入库）
3. **P3 六爻 + 黄历择日**（本地计算 + LLM 表达，扩展产品面）
4. **P5 RSS 通道**（✅ 已落地 2026-08-15，见 §P5；后续可加用户自定义源）
5. **P4 起名**（依赖 P2 语料，最后做）
6. **P5 browser-use**（✅ 最小链路已验证，本机 Edge 可用；完整 Agent 化需 LLM key 后评估）

每完成一小项即写 TASK_LEDGER.md / DECISIONS.md（照 §0 纪律：数字先实测再记录）。

---

## 8. 阶段2 审查-修复-优化无限循环（PROJECT_GOAL_20260816，2026-08-16 启动）

五缺口闭环后进入无限循环：审查全项目→问题入台账→修复→再审查→写优化文档→执行优化→再审查。
除非用户明确叫停不得停止；撞红线跳过并记录不停下问；决策自主列方案实测比对选最优直接执行含 commit 与 push。

### R1 首审查（2026-08-16，本轮）
- **五缺口闭环**：滴天髓+穷通宝鉴入库·exe 瘦身 218MB→26.6MB·exe 端到端验证·六爻纳甲运算层·黄历神煞层（TASK_LEDGER §27a）
- **红线级缺陷修复**：term_time 节气求解绕行（影响八字大运+黄历月支，2020-2026 全错→全对）·liuyao time solar_to_lunar 解包·web 边界输入验证缺失（TASK_LEDGER §27b，commit f81f18d/5369b8f）
- **13 闸门零回退**，web 6 tab 正确 schema 下全 200（TASK_LEDGER §27c/§27d）
- 决策记录：DECISIONS.md D-044（滴天髓穷通宝鉴三道判定）·D-045（六爻运算层）·D-046（神煞层）·D-047（term_time+边界+解包）

### R2 再审查（已完成，R71b 核实——审查循环已演进为优化循环，见 GOAL_NEXT_SESSION §2）
- ~~待查：wuxing-dayi 仅 1 单元入库失败~~ → **已修复**：颗粒度修复
  （1 单元 113,051 字 → 29 单元 avg 3,896 字，台账 §1278；实测 29 单元）。
- ~~bible-kjv/web/darwin-origin 0 单元遗留~~ → **非缺陷**：在 work 表但
  unit 表 0 行系设计——probe_bcv 的 31,102 行计数来自 raw_ext/generality
  原始文件，不来自 unit 表，无矛盾（台账 §1062）；孤儿 work 清除已处置
  （§1273）。
- ~~其他边界输入~~ → **已处置**：term_time 节气求解绕行/liuyao 解包/web
  边界输入验证（R1 首审查 §27b）。
- ~~文档与实测一致性全面核对~~ → **已完成**：R55b-R70b 十六轮逐项核对
  （快照数字/工具数/缓存/checks 数与实测一致）。
