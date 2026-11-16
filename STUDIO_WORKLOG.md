# Studio 优化工作台账（S 轮）

> 本文件是 StepFun Studio agent 侧的工作记录，与项目自带 `docs/TASK_LEDGER.md` 互不覆盖。
> 纪律照项目宪法：状态以脚本输出为准；环境性不可用记 SKIP(env)；缺陷带根因与复验命令。

## S0 · 环境基线（2026-11-15）

**环境实测**：2 核 / 1.9G 内存（可用 ~1.6G）/ 系统盘余 9.9G / Python 3.13.14。
沙箱预装 torch 2.15.0+cpu + sentence-transformers 6.3.0 + transformers 5.23.0。
`/workspace` 在网络存储上，**venv 不可用**（symlink 不支持），依赖直装系统 Python。

**踩坑与修复**：
1. venv 创建失败（Errno 95）→ 改系统 pip。
2. **缺陷-1（已修）**：`web/selftest.py` F-01 提交引入 `_SKIPPED` 未定义 → 整套 selftest
   在 bge LFS 未拉环境下必崩。补模块级 `_SKIPPED: list[str] = []`。
   复验：`BOOKS_LLM_DISABLE=1 python3 web/selftest.py` → 457 checks PASS。
3. **缺陷-2（已修）**：`web/app.py` ?key= 直通分支白名单跑在**未解码**的
   `request.url.path` 上，`/%5C%5Cevil.com?key=…` 的 `%5C` 骗过正则，浏览器解码后
   `//evil.com` = 开放跳转。改白名单判定在 `unquote(target)` 上（与 POST 分支的
   parse_qs 解码口径对齐），通过则 Location 仍用原始 target。
   复验：selftest 内 `?key= 白名单漏放` 用例转绿。
4. **环境损坏（已复原）**：某路径把 LFS 指针当权重加载，拉了个 16MB 半截
   model.safetensors 并被超时杀掉，留下比指针更糟的截断态。
   `git checkout` 还原指针；后台经 hf-mirror 拉真权重（95.8MB，oid 354763b9…）。

**闸门基线（BOOKS_LLM_DISABLE=1）**：

| 闸门 | 结果 |
|---|---|
| check_quality | PASS（30 works 有 junk 标记，suspect 10 units） |
| build_index | 47 works / 62,109 units / 55.6MB / 22.1s |
| verify_index | ALL PASS |
| validate_alignment | PASS |
| probe_conservation | PASS |
| check_provenance | PASS |
| probe_bcv | PASS |
| probe_g8_isolation | PASS |
| probe_booksec | PASS |
| assess_goals | G1–G9 全评出 |
| eval_g4 | PASS |
| eval_g7 | PASS |
| web/selftest | **457 PASS** + SKIP(env) bazi.semantic |
| probe_contract | 811 读点全在（SOFT=117） |
| probe_ui_smoke | **SKIP(env)**：沙箱→Playwright CDN 下载不通，chromium 装不上 |
| eval_g1 | SKIP(env)→尝试修复中：bge 权重 LFS 指针，后台拉真权重 |
| probe_dup_keys / date_parity / dollar_misuse / no_generated_in_corpus / liuyao_najia / internal_witness | 全 PASS |

## S1 · 待办

- [ ] bge 真权重落地后跑 eval_g1 补齐最后一闸
- [ ] 调研 #1：代码审计（app.js 31,609 行单文件 / 前端性能 / 后端热点 / 死代码）
- [ ] 按「收益×风险」出优化清单并实施

## S2 · HEAD 红探针普查 + 陈钉刷新轮（2026-11-15 晚）

**触发**：S1 收尾时对 probes/ 全量 51 个探针做了一遍 sweep，发现 **10 个探针 22 项
检查在 HEAD 上就是红的**。逐项鉴定后确认**全部为陈钉/测试基建问题，无一是真实回归**
（证据：每个失败针钉的文件都不被我 S1/S2 编辑触碰；唯一读我改过的文件的 r2522，
其 bazi_lookup 检查照过）。

### 关键调研发现

1. **StepFun 凭证注入只覆盖 /studio/ 前缀**（决定性证据）：
   `POST /v1/chat/completions` 与 `GET /v1/models` → 401 `Incorrect API key
   provided`；`POST /studio/v1/audio/speech` → 400 `voice_id does not exist`
   （认证已过、只是 voice_id 错）。结论：**AI 对话层要用户真钥匙**（配置脚手架已备
   `web/llm_config.json`，占位 REPLACE_ 前缀被 llm_polish 当禁用处理）；
   TTS 可用但需有效 voice_id。
2. **OSS 存储拖慢 SQLite 读 250×**（环境性，不优化）：同一查询 corpus.db 在
   /workspace p50=58.61ms vs /tmp tmpfs 0.23ms。六爻 113ms 的根因是存储不是代码。
3. **HEAD 提交 R4940 归档 probe_t7r_concept 时打断了 3 个 import 入口**
   （scripts/derive_eval_g1.py、probes/probe_embed_bge.py、probe/probe_embed_tfidf.py
   裸 import 变 ModuleNotFoundError）。补 archive 显式路径修复（不撤销归档决定）。
4. **probe_embed_tfidf 在 1.5G 限额下被 OOM kill**：全量 `np.linalg.svd` 的 Vt
   (2319×44930) float64 = 833MB + M 417MB。改 **doc-doc Gram 特征分解取 top-100**
   （恒等式 MMᵀ=US²Uᵀ，eigh 后 Vt_k=diag(1/S)UᵀM），峰值 ~460MB、2.4s，
   **hit rate 67.3% 与 D-031 历史判词逐位一致**——数值正确性实证。
   （方案 C 的 FAIL 是其被否决的结论本身，非回归。）
5. **rememberVoice/rebindFn 架构已退役**：R3242e 起脏广播收口进 rememberResult
   按 _PH_BUILDERS 品类统一发，rebindFn 参数从 remember* 签名移除，六品类改各自
   结果路径内 _rbXxx 闭包首绑 + 复看 #phShareBtn 显式监听（R231d）。

### 修复清单（全部带 S2 勘注释）

| # | 文件 | 修复 |
|---|---|---|
| 3 | src/guji/bazi_lookup.py | load_bge()：LFS 指针签名检查 + HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE + try/except→可读 RuntimeError |
| 4 | scripts/eval_g1.py | _load_bge 委托 bazi_lookup.load_bge（web/eval 同口径） |
| 5 | probes/probe_r2504.py | 2 个海报钉刷新（R3398/R3406 重构） |
| 6 | probes/probe_r2508.py | wishbottle 备份针改钉 _DATA_RE（R3421 删 _EXACT 表）；app.js 缓存针改钉 ETag 协商缓存（R3341），styles.css 仍验 3600 |
| 7 | probes/probe_r2510.py | _navF 提取 + 匹配窗 2400→3000（R3405-F10 补写链） |
| 8 | probes/probe_r2511.py | _session_lock→_held_session_lock 上下文管理器（锁内打标不变量不变） |
| 9 | probes/probe_r2512.py | 10 钉全部重钉现行机制：_PH_BUILDERS 七品类 + _rbXxx 首绑、R3244 _outP.hidden、R2350e paint 摘标+_STALE_MAP 标脏 |
| 10 | probes/probe_r2514.py | .hl-pill-ji 颜色针 →#8E2F4C（R3324 加深） |
| 11 | probes/probe_r2517.py | addr 存在性检查针 →c.has_value()（R3241/R3305 缓存集+分桶） |
| 12 | probes/probe_r2518.py | 文案破折号→逗号（语气轮漂移，行为不变） |
| 13 | probes/probe_r2519.py | 起名两步针改钉现行文案（两步都在） |
| 14 | probes/probe_r2522.py | cookie _eq 针改钉多行现行式；restore_scroll 窗 500→900（R3201 长大） |
| 15 | probes/probe_r2524.py | sanitize 针补 _sf2（R3069）；罐头行检查传显式配置（cfg=None 时 spawn 先返 None，罐头路径空转——前端镜像表接禁用态，R233r） |
| 16 | probes/probe_embed_tfidf.py | import sys + Gram top-k SVD（OOM 修复） |
| 17 | probes/probe_embed_bge.py | import sys + archive 路径 |
| 18 | scripts/derive_eval_g1.py | archive 路径 |

**复验**：r2508/r2510/r2511/r2512/r2514/r2517/r2518/r2519/r2522/r2524 全绿；
embed_tfidf 跑到完成且复现 67.3% 历史判词；derive_eval_g1 出 274 题。

**环境遗留（非代码）**：bge 权重被 LFS smudge 写成「指针文本+错位二进制」损坏态
（sha256 不符 354763b9…），已弃用该文件、后台从 media.githubusercontent.com
干净重下（网速 22KB/s→1MB/s 波动，续传中）。

---

## S2 续 · 收尾三项（本轮审计最后清理）

### 1. probe_generality_crossref：超时是环境，逻辑无罪（已确认 PASS）
- 现象：150s 扫描窗内 exit 124。
- 根因：3a 段对 558 条链接逐条 `db.execute`，OSS 网络存储上 p50=58.61ms
  （本地盘同查询 0.23ms，250×），仅 3a 就 ≈130s，加 3b/3c 必然超 150s。
- 处置：`timeout 1500` 后台重跑 → **EXIT=0 全过**：
  - 558 条易林链接，跨 scheme 引用 0；卦地址 scheme-leak 0；
  - 三链一致性：卦名未印在源文 0/558、目标地址 round-trip 0、FTS 不自指 0；
  - 附加段：play 6,141 单元最近 body-ACT 与声称 ACT 不符 0（寻址正确性未被证伪）。
- 结论：与 OSS 250× 同因，代码侧不优化探针逻辑。

### 2. 51 探针 + 457 自检基线现状（bge 权重落地前最后状态）
- 全绿；唯二非 PASS：probe_ui_smoke（SKIP(env)，沙箱无 chromium）、
  probe_embed_tfidf（exit=1 是其设计判词：D-031 方案 C 以 67.3% < 80% 被否决，
  Gram 数值路线逐位复现了该历史结论）。
- bge 权重（95,827,648 B，sha256 354763b9…）下载中（OSS 仓库 LFS 文件经
  media.githubusercontent.com 续传，速度 ~1MB/s 波动）；落地后补跑
  scripts/eval_g1.py 与 probes/probe_embed_bge.py，关闭最后两个待验闸。

### 3. 部署交付物 · Tier A 静态展示站（已发布）
- 位置：`/workspace/sites/books-showcase/`（index + tarot 两页，85 文件 3.1MB）。
- 内容：项目定位（确定性内核 × 克制的 AI 层）、八视图实测延迟、两层架构、
  质检台账（本轮六项发现）、塔罗互动演示。
- 塔罗演示 = 服务端 `guji/tarot.py` 的浏览器移植：
  - `assets/deck.json` 由 DECK / SPREADS / NAMED_SPREADS **从 Python 导出**（78 张全牌桌 + 9 牌阵）；
  - 牌面资产用仓库自带 `web/static/tarot/`（78 图 + 牌背 + manifest.json 权威映射，3.1MB）；
  - 抽牌逻辑同构（洗牌 → 逐张定正逆位），随机源换 mulberry32 并在页面上明示
    「演示内同 seed 同牌面；服务端用 Python 随机源，两边牌面不必相同——规则一致，各自可复验」。
  - 验证：node 复刻 draw 逻辑——seed42 时间流三张固定、同 seed 幂等、异 seed 不同、
    凯尔特十字 10 张正常；deck×manifest×文件三方对齐（78/78/0 missing）；
    `node --check` 通过；ZIP 内引用 12 条全部可解析。
- 发布：site_id `310953908818608128`（ZIP 内 index.html 在根、全部资产按相对路径入包）。

---

## S2 终局 · bge 权重落地，全闸关闭（2026-08-28）

### 权重修复过程
- 仓库自带 LFS 指针 + 首次 curl `-C -` 续传把指针文本与真实二进制缝在一起
  （95,827,648 B 但 sha256=`eb0b45c0…` ≠ 指针记录的 `354763b9…`，safetensors
  反序列化直接报 "header too large"）。
- 改用 media.githubusercontent.com 干净续传到 /tmp，逐轮校验大小，
  最终 sha256 **逐位匹配** LFS 指针记录值后 `mv` 落位
  （不 `git checkout`，避免再触发 smudge 生成指针）。
- 头部字节 `b8 1e 00 00 … {"__meta` = 合法 safetensors（8 字节小端头长 + JSON）。

### 权重落地后的闸门（本机 2C/1.9Gi 沙箱）
| 闸 | 结果 |
|---|---|
| web/selftest.py | **PASS 458 checks**（原 457 + SKIP(env)；`bazi.semantic` 真激活并通过），峰值 715MB |
| scripts/eval_g1.py | **G1 = PASS** 272/274 = 99.3%；retrieval 52/52、cross 24/24、hard 24/24、version 20/20；**retrieval_concept 53/55 = 96.4%**（目标 80%） |
| probes/probe_embed_bge.py | **四闸全过**：hit 96.4% ≥80 ✓、median 63ms ≤2s ✓、build 45s ≤10min ✓、内存 4.7MB <4GB ✓ → 方案 A/B 可行 |
| probes/probe_generality_crossref.py | EXIT=0 全过（558 链接 / 6141 play 单元，0 证伪） |
| 51 探针全量扫描 | 全部 rc=0 |

### 两个「非 PASS」的最终定性
- **probe_embed_tfidf exit=1 是设计判词**：D-031 记录方案 C 因 67.3% < 80% 被否决。
  Gram 数值路线复现出逐位相同的 37/55，历史结论被实证。同批 bge 96.4% 通过，
  「TF-IDF 不够、语义向量够」成为有数字的结论，不是口号。
- **probe_ui_smoke SKIP(env)**：沙箱无 chromium（Playwright CDN 不可达），
  与代码无关。

### 一次虚警
扫描中 probe_llm_polish 曾 rc=1（判据8：子进程 selftest 被 OOM kill，exit -9）。
复测：单独 selftest 峰值 715MB、探针父子合并 771MB 均远低于 1.5Gi 可用，
判定为扫描期页缓存叠加的瞬态内存压力，非回归。重跑 PASS（458 checks）。

### 本轮审计最终状态
**51 个探针 + 457→458 项自检 + G1–G9 目标评估：全绿。**
自 S0 起累计：真实缺陷 5 处（开放跳转、selftest 未定义变量、t7r 归档断链×3、
tfidf 全量 SVD OOM、LFS 权重缝坏），过期钉扎 22 项（10 探针，零真实回归），
环境属性 3 项（OSS 250×、无 chromium、沙箱内存上限）——均有据可查。

---

## S2 附 · 沙箱环境事故与 SQLite 读写画像（2026-08-28 晚）

### 环境事故：运行时依赖被清
- 现象：下午还能跑通的 TestClient 探针，晚间 `import fastapi` 直接
  ModuleNotFoundError；site-packages 里 fastapi/uvicorn/starlette/httpx/
  jsmin/feedparser 全部消失（仅剩 pydantic；另有个 server 工具的自带
  venv 里有旧版 fastapi 0.111.0，不是我们的）。
- 处置：`pip3 install -r requirements-runtime.txt` 重装即恢复
  （fastapi 0.141.1 等全部就位）——这个文件就是为这种时刻写的。
- 教训：本沙箱的 Python 环境会在会话中途被部分回收；依赖以
  requirements-runtime.txt 为唯一事实源，掉了就重装，不要手拼。

### SQLite 读写画像（插桩 sqlite3 trace，逐条数真实执行的 SQL）
| 场景 | 读 | 写 |
|---|---|---|
| 纯读负载（9 类端点 × 2~3 轮） | 2912 | 1 |
| corpus.db（55.6MB 主索引） | 2894 | **0** |
| 发一条用户手记（POST /api/threads） | 17 | 15 |
结论：**读压倒性地多（约 2912:1）**。corpus.db 运行时严格只读（写入只在
build_index.py 构建期）；写只发生在 knowledge.db / users.db /
paipan_history.db 三个小库。journal 策略与之一致：两个大库用 delete 模式
（无 WAL 开销），两个常写小库用 WAL（写不挡读）。

---

## S3 · 真身部署到 uppcoder（2026-08-28）

**用户指令（本段为指令摘要，非原话）**：忘掉 swift-cedar 展示站，那是另一回事；
要把「小满的解忧铺」真身部署进 uppcoder；**部署完成后再继续整个项目的优化**。

### 平台勘察（qlbmx89w@…apps-6.websson.cloud:2222）

| 项 | 实测 |
|---|---|
| 系统 | Debian 12 容器（overlay），非 root 用户 uppcoder |
| 磁盘 | 438G 总量 / **135G 可用**——"2GB 不够"的旧结论作废 |
| 内存 | 3G 总量 / 2.7G 可用 |
| Python | pixi 管 3.13.18（`~/app/.pixi/envs/web-fastapi/bin/python3.13`），PATH 里没有 python3 |
| 启动链 | supervisor(pid1) → `[program:framework]` → `bash /opt/start-scripts/start-fastapi.sh` → `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`（APP_DIR=~/app，入口 main:app） |
| 反代 | nginx(80) `location /` → 127.0.0.1:8000，带 X-Forwarded-Proto/For |
| 门禁 | 平台 edge 302 → portal.uppcoder.com/login（应用自身另有 BOOKS_ACCESS_TOKEN 闸，本次未设） |

### 部署动作

1. **传包**：本地打精简 tar（排除 .git/data/external/assets_src/delivery/probes，67MB）→ `~/app/books/`（152MB 落盘，含预建 corpus.db，免去服务器重建索引）。
2. **依赖**：pixi 环境已有 fastapi 0.163.1/uvicorn 0.54.0/pydantic 2.14.3；`uv pip install` 补齐 httpx/feedparser/jsmin（uv 走 ~/.local/bin，ensurepip 亦可）。
3. **入口接线**（不动平台文件）：
   - 新写 `~/app/main.py`：把 `books/` 上 sys.path 后 `from web.app import app`；环境默认值全部 setdefault（BOOKS_TRUST_XFF=1 配 nginx 转发的 XFF 头、BOOKS_LLM_DISABLE=1 无钥匙走确定性、BOOKS_EXTERNAL_DISABLE=1 关 RSS 外呼）。
   - 新写 `~/app/startup-app.sh`：平台预留钩子（start-fastapi.sh 约定存在即取代默认 uvicorn 命令），按 docs/DEPLOY.md 口径加 `--no-access-log`（生辰参数不进访问日志）、去掉 --reload。
4. **重启**：`supervisorctl -c ~/.config/supervisord.conf restart framework`（程序名 framework；supervisorctl 不在 SSH 默认 PATH，用 `/opt/pixi/.pixi/envs/default/bin/supervisorctl`）。

### 部署即验证（全部实侧）

- `GET /` 200（109KB，19 视图 PWA）；`/api/health` → `{"ok":true,"engine":"guji.interpreter/1.0（本地规则，无 LLM）","index":true}`；`/static/app.js` 200 889,675B（与沙克斯实测一致）；nginx 层同样 200。
- 真实排盘：黄历宜/忌/建除/彭祖/神煞正确；八字 paipan+calc+**12 条 FTS 证据**（子平真诠/三命通会）；六爻賁卦动爻正确。
- **服务器自测 `web self-test PASS (457 checks)`**，bazi.semantic 按设计 SKIP（未装 sentence_transformers）。
- 延迟（本地磁盘，无 OSS 惩罚）：huangli 8-9ms、liuyao 10-18ms、bazi 9-12ms、search 7-10ms；**RSS 63MB**。沙箱同接口 liuyao 113ms → 服务器 10× 快，证实 OSS 250× 是环境产物而非代码问题。

### 真缺陷 #19（部署暴露，已修）：可选依赖缺失炸穿自测

`src/guji/bazi_lookup.py::load_bge` 的 `from sentence_transformers import ...` 在 try 块**外**——
S2 加固只兜住了"权重损坏"，没兜住"库没装"。requirements-runtime.txt 不含它是
预期状态（README：web 主路径不依赖它），缺库应优雅降级而不是 ModuleNotFoundError
炸穿 selftest。沙箱里一直装着依赖所以从未暴露，服务器首跑即现形。
**修法**：import 进 try，转译为可读 RuntimeError；`web/selftest.py` 的 SKIP 判据
同步放宽（"LFS" 或 "sentence_transformers" 都算环境不可用，其余 RuntimeError 照抛）。
副作用收益：沙箱环境本轮又被回收了 torch/ST，自测同样靠这个修复优雅 SKIP（457 全过）
而非崩栈。已同步服务器并重启 framework 加载。

### 闸门清扫：最后一个 SKIP(env) 在部署环境关闭

沙箱里 probe_ui_smoke 因无 chromium 永久 SKIP。服务器有外网且非 root，逐块拼出可用的
headless chromium：
- playwright 1.65.2 用 `uv pip install` 装进 pixi 环境；
- 驱动 node 缺 libatomic → 用平台自带的 openvscode node（v22.21.1）经
  `PLAYWRIGHT_NODEJS_PATH` 指定；
- chromium-headless-shell 缺 7 个 GUI 系统库（atk/atk-bridge/gbm/xcomposite/xdamage/
  atspi/xshmfence）→ 非 root 从 deb.debian.org 抓 bookworm .deb，`dpkg-deb -x`
  解压到 `~/chromium-syslibs/`，补软链后 `LD_LIBRARY_PATH` 指过去（libatspi 的 Debian
  包名是 libatspi2.0-0，不是 libatspi0——第一轮按 soname 猜包名扑空）。
- 结果：`ldd` 零缺失，**probe_ui_smoke PASS**（真加载 `/`、深链/375px 无横向溢出/
  ZCOOL 字体/pushstate 刷新回 view/跨年愿链全过，清理后 history 0→0）。

### 写入增长面审计（结论：无需处理）

- paipan_history：KEEP_MAX=500 滚动 DELETE（R228j）有界；
- chat sessions：selftest `chat.sessions.cap` 证明有 cap；
- corpus.db：运行期实测 0 写入（只读）；知识库/用户库按用户数有界。
- 135G 磁盘下增长根本不是风险面，记录备查。

### S3 结论

- **真身已在 uppcoder 上线**：https://qlbmx89w-fastapi-stepfun-studio-books.apps-6.websson.cloud/
  （平台 portal 登录后进入；应用级口令闸未设，需要可 BOOKS_ACCESS_TOKEN）。
- 本轮新增真缺陷 1 个（#19 可选依赖导入），修复后沙箱/服务器双绿。
- 展示站（swift-cedar）与本次部署无关，不再维护。

---

## S3 续 · 部署环境全闸扫描 + 语义检索上线（2026-08-28）

### 服务器全闸扫描（52 个活跃探针，部署环境）

首扫 **47 PASS / 5 FAIL**，逐个定性：

| 探针 | 原因 | 处置 |
|---|---|---|
| probe_embed_bge / probe_embed_tfidid | 未装 numpy | 环境 → 装栈后 bge 转 PASS；tfidf 的 exit=1 是 D-031 设计判决（67.3%<80%），不是缺陷 |
| probe_show | 脚本本身要命令行 PDF 参数（文档渲染工具，非自包含探针） | 人工工具，不计入扫描判决 |
| probe_r2522 | 传包遗漏根目录 `web_launcher.py`（探针读它做 pin） | 补传 → 26 pass 0 fail |
| probe_selftest_regress | 基线 460→458：服务器缺 torch 使 bazi.semantic 降级 SKIP | 装 torch 后 458 → PASS（探针自带改名审核机制，460→458 已审核） |

### 语义检索（bge）在部署实例上线

- `uv pip install`（pytorch CPU 源）torch 2.15.0+cpu + numpy 2.5.5 + sentence-transformers 6.3.0 + pymupdf；
- bge 权重（92MB，sha256 `354763b9…` 与 LFS 记录一致）补传至 `data/external/bge-small-zh-v1.5/`；
- **服务器 selftest 458 项全过，bazi.semantic 激活并通过**（此前 457 + SKIP）；
- probe_embed_bge：**hit_rate_top10 = 53/55 = 96.4%**（与沙箱一致；构建 126.9s，门限 10min 内）；
- **eval_g1：G1 = PASS 272/274（99.3%）**，与沙箱一致；
- 内存形态：常驻 **69MB**（torch 惰性加载，普通流量零成本）；bge 单载峰值 502MB（盒上 2.7G 可用，余量充足）；
- 概念检索实测：13 部典籍命中、周易註疏引文正常、热查询 3ms。

### 部署终态（2026-08-28）

- 线上：https://qlbmx89w-fastapi-stepfun-studio-books.apps-6.websson.cloud/ （平台 portal 登录后进入）
- 入口：`~/app/main.py`（sys.path 引导 + 三个 setdefault 环境默认值）+ `~/app/startup-app.sh`（平台钩子，`--no-access-log`、无 --reload）；平台文件零改动
- 闸门：selftest 458 ✓ / G1 PASS ✓ / embed_bge 96.4% ✓ / ui_smoke PASS ✓ / 52 探针除 tfidf（设计判决）与 show（人工工具）外全绿
- 延迟（本地磁盘）：huangli 8-9ms、liuyao 10-18ms、bazi 9-12ms、search 7-10ms
- 仍缺口：LLM 对话层（需用户提供 StepFun API key；配置脚手架 web/llm_config.json 就绪）
- 磁盘 129G 可用；日志由 supervisor 10MB×3 轮转封顶

### S3 轮次总结

- 新增真缺陷 1 个（#19：可选依赖 import 在 try 外，缺库炸穿自测）——沙箱/服务器双线修复验证；
- 传输遗漏 1 处（web_launcher.py）——补传后转绿；
- 环境补齐 4 项（numpy/torch/ST/pymupdf）+ 权重 92MB + chromium 七库拼接；
- **部署不是终点而是探伤器**：本轮的 5 个 FAIL 里 2 个是真问题（导入缺陷、传包遗漏），只有把闸门搬进真实环境才暴露得出来。

## S4 · LLM 层上线（AMD 开发端 · Qwen3.8-27B）

用户提供端点 `developer.amd.com.cn/radeon/api/v1` + key，配 `web/llm_config.json`
（gitignored，服务器同路径 600 权限；外网三条遍历路径实测 404 取不到）。

**端点实测（流式诊断）**：首内容 token ≈20s 前摇（10–35s 抖动，含排队），
之后 17.6 tok/s。关键发现：**默认烧推理 token**——同一请求 46s 生成 500 个
reasoning token、正文 0 字（finish=length），正是应用注释警告过的形态。
`chat_template_kwargs.enable_thinking=false` 一开：4s 直接出文、0 推理 token。

**改动**（commit `9737686`）：
- `llm_polish._merge_extra_body`：llm_config.json 的 `extra_body` 段透传进
  payload——端点专属参数走配置不硬编码（多 provider 形态下别家端点拒收
  陌生字段即白屏），polish/chat 两条构造路径都接；
- 时间预算按端点实测调参：`_POLL_BUDGET_S` 50→110、`_REVIEW_BUDGET_S`
  78→150；前端 `AI_POLL_CAP_S` 62→125、`NR_POLL_CAP_S` 88→165；
- 配置：timeout_s 60 / max_tokens 600（推理关停后正文直出，600 够用且
  留 4s+35s 的相位抖动余量）；app.js 轮询帽同步；sw.js bump 壳哈希
  （app.js 变动触发 selftest 的 sw.shell_hash 闸，跑 scripts/bump_sw.py）。

**验证链**：协议冒烟 200（OpenAI 兼容、模型名受理）→ polish 直路 4.0s
出文 → TestClient 异步回路 3.1s done → 打死端点 1.3s 优雅 None
（D-244a 降级不抛）→ **服务器生产回路 22.5s done**（慢相位，稳进预算窗）。

**闸门复跑**：服务器 selftest **PASS (458)**（含 ai_polish.key_present、
ai.async.task.roundtrip、bazi.semantic）；probe_ui_smoke **PASS**（真浏览器，
新 app.js）；沙箱 selftest **PASS (457)** + SKIP(env) bazi.semantic（沙箱
torch 被回收，#19 修复按设计优雅跳过）。

**已知观测**：端点相位抖动 3–22s，全部落在 110s 预算内；极端拥挤时 AI
段落静默缺席或后到，确定性主体不受影响（设计降级语义）。换任何
OpenAI 兼容端点只需改 llm_config.json 的 base_url/model/api_key 三字段。
