# 小满的解忧铺（books）

古籍语料库 + 传统命理计算（八字 / 六爻 / 黄历 / 合婚 / 起名 / 塔罗 / 星座 / 每日运势）
的本地单页应用。FastAPI 后端 + 纯静态前端，SQLite FTS5 检索，可选 LLM 陪伴层（小满）
——无 API key 时全自动降级为确定性输出，离线可用。

## 跑起来（本地）

```bash
python3 -m venv .venv
.venv/bin/pip install fastapi 'uvicorn[standard]' httpx pydantic numpy
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install sentence-transformers          # bge 语义检索（命理书证据）
.venv/bin/pip install playwright                     # 仅浏览器探针需要
.venv/bin/python -m playwright install chromium

# 语料索引（data/index/corpus.db，gitignored，约 5 分钟可重建）
.venv/bin/python scripts/check_quality.py
.venv/bin/python scripts/build_index.py
```

然后：

```bash
.venv/bin/python -m uvicorn web.app:app --port 8123
# 打开 http://127.0.0.1:8123
```

Windows 桌面一键入口：`web_launcher.py` / `start_web.bat`（自拉起服务、开浏览器、
关浏览器自动停服务）。

### LLM 陪伴层（可选）

不配 key 也能用全部确定性功能。要小满开口聊天：建 `web/llm_config.json`
（gitignored）或设环境变量 `BOOKS_LLM_API_KEY` / `BOOKS_LLM_BASE_URL` /
`BOOKS_LLM_MODEL`；`BOOKS_LLM_DISABLE=1` 强制离线。

## 闸门（全部须 PASS）

```bash
BOOKS_LLM_DISABLE=1 .venv/bin/python web/selftest.py            # 主闸门 181 项
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_contract.py   # 契约 386 读点
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_ui_smoke.py   # 浏览器冒烟 44 用例
.venv/bin/python probes/probe_dollar_misuse.py                  # 静态探针
.venv/bin/python probes/probe_selftest_regress.py               # 断言只增不减
BOOKS_LLM_DISABLE=1 .venv/bin/python probes/probe_first_screen.py  # 首屏抵达成本
```

CI（`.github/workflows/selftest.yml`）在 push/PR 上自动跑以上全部 + corpus 数据闸门
（check_booksec / check_dual_engine / check_provenance / verify_index / assess_goals）。

## 结构

- `src/guji/` — 语料解析与命理计算核心（无任何 web 依赖）
- `web/` — FastAPI 应用（`routers/` 薄路由 → `services.py` → `src/guji/`）
- `web/static/` — 单页前端（app.js / styles.css / index.html + PWA）
- `scripts/` — 索引构建、质量与数据闸门（13 道）
- `probes/` — 回归探针；`probes/archive/` 是已完成使命的一次性探针
- `data/` — 原始语料与外部资源；`data/index/*.db` 均为可重建产物（gitignored）
- `docs/` — 架构/决策/台账（`TASK_LEDGER.md` 按 §追加，每行带可复验命令）

## 红线（改代码前先看）

宪法三条 + 派生纪律都写在 `docs/`：所有状态声明必须带可复验命令；引文可核验
（折叠 ≠ 删除）；语料不做远端抓取；前端数据一律 `esc()`/`renderRichText`
/`fmtScalar` 渲染，`innerHTML` 不许插未转义数据；LLM 只润色不承重，必须能静默降级。
