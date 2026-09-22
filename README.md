# 小满的解忧铺（books）

古籍语料库 + 传统命理计算（八字 / 六爻 / 黄历 / 合婚 / 起名 / 塔罗 / 星座 / 每日运势）
的本地单页应用。FastAPI 后端 + 纯静态前端，SQLite FTS5 检索，可选 LLM 陪伴层（小满）
——无 API key 时全自动降级为确定性输出，离线可用。

## 跑起来（本地）

```bash
python3 -m venv .venv
.venv/bin/pip install fastapi 'uvicorn[standard]' httpx pydantic numpy feedparser   # feedparser：/api/external/* 资讯源（R229x 补声明）
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install sentence-transformers          # bge 语义检索（命理书证据）
.venv/bin/pip install playwright                     # 仅浏览器探针需要
.venv/bin/pip install mcp                            # 可选：Claude Desktop 集成（python -m guji.mcp_server）
.venv/bin/python -m playwright install chromium

# 语料索引（data/index/corpus.db，gitignored，实测重建 ~10 秒，约 55MB）
.venv/bin/python scripts/check_quality.py
.venv/bin/python scripts/build_index.py

# knowledge.db 种子：selftest 的 threads.detail/share.bazi 需要线程 id=1
# 与一条带证据的 derived——首次建库后跑一次（幂等，已有数据则跳过）。
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.'); sys.path.insert(0, 'src')
from guji.knowledge import KnowledgeBase, Evidence
kb = KnowledgeBase('data/index/knowledge.db')
if kb.db.execute("SELECT count(*) c FROM thread").fetchone()["c"] == 0:
    tid = kb.open_thread('env-seed: 本地环境种子线程')
    kb.add_turn(tid, 'user', '环境自检种子')
else:
    tid = kb.db.execute("SELECT id FROM thread ORDER BY id LIMIT 1").fetchone()["id"]
if kb.db.execute("SELECT count(*) c FROM derived").fetchone()["c"] == 0:
    kb.record('summary', '天下之至柔，驰骋于天下之至坚', 'env-seed',
              evidence=[Evidence(work_id='KR5c0057', file='KR5c0057_043.txt',
                                 raw_start=6918, raw_end=6994,
                                 quote='第四十三章 天下之至柔',
                                 page_anchor='KR5c0057_tls_043-1a')],
              thread_id=tid)
kb.close()
PY
```

> **前置：git lfs**——`data/external/bge-small-zh-v1.5` 的模型权重在 LFS
> 里。clone 后跑 `git lfs pull`；没拉的话 `bazi.semantic` 闸门与
> `scripts/ask_bazi.py --sem` 会拿到指针文件直接挂（web 主路径不走语义
> 检索，不受影响）。

然后：

```bash
.venv/bin/python -m uvicorn web.app:app --port 8123 --no-access-log
# 打开 http://127.0.0.1:8123
# （R87-P1-4：uvicorn access log 会把 ?bday=/邀请链等含生辰的 query
#  写进 stdout——对外部署/反代场景务必关掉）
```

**TLS 反代后部署**（nginx/Caddy/网关终结 HTTPS）：务必加
`--proxy-headers --forwarded-allow-ips <反代网段>`——og:image/og:url 的绝对
URL 按 `request.base_url` 生成，不开 proxy-headers 会落成 `http://` 内网
地址，微信/推特种爬虫静默抓不到卡片图，且无任何报错面（R2350b / R99-P2）。

### 公网部署（Railway/Render/Fly.io/Docker）

仓库自带 `Dockerfile` + `requirements-runtime.txt` + `.python-version`（R2357）：

```bash
docker build -t books . && docker run -p 8123:8123 books
# 平台形态：装 requirements-runtime.txt，启动命令
uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8123} \
  --proxy-headers --forwarded-allow-ips '*' --no-access-log --workers 1
```

**多访客公开站必须开的环境变量**（这站按本地单用户设计——排盘台账
自动记生辰，knowledge.db 全部共享）：

```bash
BOOKS_PAIPAN_HISTORY_DISABLE=1   # 排盘台账整体关闭（否则所有人生日互见互删）
BOOKS_WRITE_DISABLE=1            # 共享库写面拒绝（prefs/favorites/threads/import）
BOOKS_EXTERNAL_DISABLE=1         # 服务器上没 GUJI_PROXY 时关 RSS 外呼
```

- **不要装 `requirements-ci.txt`**——里面的 sentence-transformers 会拖
  torch ~2GB，免费档直接炸；运行时只需 `requirements-runtime.txt`。
- **必须单实例单 worker**（`--workers 1`）：限流/AI 任务/聊天会话全在
  进程内存里，多 worker 下任务会 404。
- 数据不持久：paipan_history.db / knowledge.db 写在容器盘，免费档重启
  即清零（要留存就挂卷到 `data/`）。
- 建索引是构建期步骤（Dockerfile 已固化 `build_index.py`）；缺
  `data/index/corpus.db` 时古籍端点返回 503 但站点其余功能正常。
- 部署后健康检查指 `GET /api/health`（返回 `engine` + `index` 就位标志）。

Windows 桌面一键入口：`web_launcher.py` / `start_web.bat`（自拉起服务、开浏览器、
关浏览器自动停服务）。

### LLM 陪伴层（可选）

不配 key 也能用全部确定性功能。要小满开口聊天：建 `web/llm_config.json`
（gitignored）或设环境变量覆盖（key 不落盘时用这个）。

### 环境变量开关表（R2349w / R93-P2-1 补全）

| 变量 | 取值 | 语义 | 默认 |
|---|---|---|---|
| `BOOKS_LLM_API_KEY` | key 字符串 | LLM key（替代配置文件） | 读 `web/llm_config.json` |
| `BOOKS_LLM_BASE_URL` | `https://…/v1` | LLM 端点 | 配置文件/内置默认 |
| `BOOKS_LLM_MODEL` | 模型名 | LLM 模型 | `agnes-2.5-flash` |
| `BOOKS_LLM_TIMEOUT_S` | 秒数 | LLM 超时 | `30` |
| `BOOKS_LLM_MAX_TOKENS` | 整数 | LLM token 上限 | `1000` |
| `BOOKS_LLM_DISABLE` | `1/on/true/yes` | 强制离线（所有 AI 层关掉） | 关 |
| `BOOKS_PAIPAN_HISTORY_DISABLE` | `1/on/true/yes` | 关排盘台账（隐私部署用） | 关 |
| `BOOKS_WRITE_DISABLE` | `1/on/true/yes` | 共享 knowledge.db 写面拒绝（公网演示） | 关 |
| `BOOKS_EXTERNAL_DISABLE` | `1/on/true/yes` | 关 external/* 外部资讯拉取 | 关 |
| `BOOKS_ALLOWED_HOSTS` | 逗号分隔域名 | TrustedHost 白名单（防 Host 投毒） | 放行全部 |
| `BOOKS_CORS_ORIGINS` | 逗号分隔 Origin | 分体部署的跨域白名单 | 不加 CORS 头 |
| `GUJI_PROXY` | `http://…` | external 抓取出网代理 | 直连 |

exe 形态：`llm_config.json` 放在 exe 同目录（或 exe 旁 `web/` 下）即可被读到；
exe 旁还必须放 `data/index/corpus.db`（缺了古籍相关端点会 503）。

## 闸门（全部须 PASS）

```bash
BOOKS_LLM_DISABLE=1 .venv/bin/python web/selftest.py            # 主闸门（当前 268 项，以 selftest 末行输出为准）
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_contract.py   # 契约（当前 566 读点，以末行为准）
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_ui_smoke.py   # 浏览器冒烟（当前 75 用例，以末行为准）
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_date_parity.py   # 前后端日期词/别名同构
.venv/bin/python probes/probe_dollar_misuse.py                  # 静态探针
.venv/bin/python probes/probe_selftest_regress.py               # 断言只增不减
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_first_screen.py  # 首屏抵达成本
```

CI（`.github/workflows/selftest.yml`）在 push/PR 上自动跑以上全部 + corpus 数据闸门
（check_booksec / check_dual_engine / check_provenance / verify_index / assess_goals） + baseline_voice/probe_llm_polish/check_xingzuo/check_warm_voice/check_async_ai/check_plain_first/check_poster/ruff——完整闸集以 `.github/workflows/selftest.yml` 为准。

## 结构

- `src/guji/` — 语料解析与命理计算核心（无任何 web 依赖）
- `web/` — FastAPI 应用（`routers/` 薄路由 → `services.py` → `src/guji/`）
- `web/static/` — 单页前端（app.js / styles.css / index.html + PWA）
- `scripts/` — 索引构建、质量与数据闸门（13 道）
- `probes/` — 回归探针；`probes/archive/` 是已完成使命的一次性探针
- `data/` — 原始语料与外部资源；`data/index/*.db` 均为可重建产物（gitignored）
- `specs/`、`.specify/` — 功能规格与治理宪法；`delivery/` — 交付物
- `books_app.spec`、`web_launcher.py`、`start_web.bat` — exe 打包与双击启动
- `requirements-ci.txt` / `requirements-packaging.txt` — CI 与打包依赖钉扎
- `docs/` — 架构/决策/台账（`TASK_LEDGER.md` 按 §追加，每行带可复验命令）

> 历史文档/台账里引用的 `probes/*.py` 若报不存在——多数已归档到
> `probes/archive/`，先查那里（R27-#1）。

## 红线（改代码前先看）

宪法三条 + 派生纪律都写在 `docs/`：所有状态声明必须带可复验命令；引文可核验
（折叠 ≠ 删除）；语料不做远端抓取；前端数据一律 `esc()`/`renderRichText`
/`fmtScalar` 渲染，`innerHTML` 不许插未转义数据；LLM 只润色不承重，必须能静默降级。
