# 部署与运维手册（docs/DEPLOY.md）

README 保持产品向精简；部署/运维细节全部收在这里。

## 公网部署（Render / Railway / Fly.io / Docker）

仓库自带 `Dockerfile` + `requirements-runtime.txt` + `.python-version`：

```bash
docker build -t books . && docker run -p 8123:8123 books
# 平台形态：装 requirements-runtime.txt，启动命令
uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-7860} \
  --proxy-headers --forwarded-allow-ips '*' --no-access-log --workers 1
```

**TLS 反代后部署**（nginx/Caddy/网关终结 HTTPS）：务必加
`--proxy-headers --forwarded-allow-ips <反代网段>`——og:image/og:url 的绝对
URL 按 `request.base_url` 生成，不开 proxy-headers 会落成 `http://` 内网
地址，微信/推特种爬虫静默抓不到卡片图，且无任何报错面（R2350b / R99-P2）。

**uvicorn 必须 `--no-access-log`**——access log 会把 `?bday=` / 邀请链等
含生辰的 query 写进 stdout。

### Render 免费档参考步骤

1. render.com 注册 → New → Web Service → 连本仓库 → Runtime 选 Docker
2. Instance type 选 Free；环境变量加 `BOOKS_ACCESS_TOKEN`（私有口令）
   和 `BOOKS_LLM_API_KEY`（小满聊天要）
3. Deploy → 几分钟后 `https://<名字>.onrender.com` 开门输口令即进
   - 免费档 15 分钟无请求休眠、冷启动 ~30s；要常驻升 Starter。
   - Render 的 GitHub 连接默认自动部署（push main 即重建）。

### 私有站口令

```bash
BOOKS_ACCESS_TOKEN=你自己的口令   # 页面输一次口令写 Cookie 30 天；
                                 # 或带 ?key=口令 的链接直通
# /api/health 豁免（平台探活要用）。不设 = 全开放（本地单用户默认）。
```

### 多访客公开站必须开的环境变量

这站按本地单用户设计——排盘台账自动记生辰，knowledge.db 全部共享：

```bash
BOOKS_PAIPAN_HISTORY_DISABLE=1   # 排盘台账整体关闭（否则所有人生日互见互删）
BOOKS_WRITE_DISABLE=1            # 共享库写面拒绝（prefs/favorites/threads/import）
BOOKS_EXTERNAL_DISABLE=1         # 服务器上没 GUJI_PROXY 时关 RSS 外呼
# 公网演示还建议 BOOKS_LLM_DISABLE=1 或 BOOKS_ACCESS_TOKEN——
# 否则匿名访客可消耗 LLM 配额（虽有 120/min 全局限速+12 在途帽兜底）。
BOOKS_LLM_DISABLE=1              # 没配 LLM 凭据/不想给访客烧额度时开
```

### 平台部署坑位

- **不要装 `requirements-ci.txt`**——里面的 sentence-transformers 会拖
  torch ~2GB，免费档直接炸；运行时只需 `requirements-runtime.txt`。
- **必须单实例单 worker**（`--workers 1`）：限流/AI 任务/聊天会话全在
  进程内存里，多 worker 下任务会 404。
- 数据不持久：paipan_history.db / knowledge.db 写在容器盘，免费档重启
  即清零（要留存就挂卷到 `data/`）。
- 建索引是构建期步骤（Dockerfile 已固化 `build_index.py`）；缺
  `data/index/corpus.db` 时古籍端点返回 503 但站点其余功能正常。
- 部署后健康检查指 `GET /api/health`（返回 `engine` + `index` 就位标志）。

## 环境变量开关表

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
| `BOOKS_ACCESS_TOKEN` | 口令字符串 | 访问闸：页面输一次口令写 Cookie 30 天（公网部署必配） | 不设=全开放 |
| `BOOKS_TRUST_XFF` | `1/on/true/yes` | 限速桶信任 X-Forwarded-For 尾跳（仅受信代理部署开） | 关 |
| `GUJI_PROXY` | `http://…` | external 抓取出网代理 | 直连 |

## LLM 陪伴层配置

不配 key 也能用**全部**确定性功能——AI 是纯增量层。

`web/llm_config.json`（gitignored），OpenAI 兼容格式：

```jsonc
{
  "enabled": true,
  "base_url": "https://your-endpoint/v1",
  "api_key": "sk-…",
  "model": "your-model",
  "timeout_s": 24,
  "max_tokens": 1600,
  "fallbacks": [ { "base_url": "…", "api_key": "…", "model": "…",
                   "timeout_s": 20, "max_tokens": 1600 } ]
}
```

实测经验（本仓库就是按它调的）：

- **推理型模型**（Atria-Dawn-Preview、step-5-preview 这类会先思考再答的）
  `max_tokens` 要给到 1600+——推理会烧预算，给少了返回空正文。
- **timeout 让链留活路**：主节点 24s / 兜底 20s/22s 的比例下，
  三节点串行满载 ~68s——点评类链路后来改成了并发竞速。
- exe 形态：`llm_config.json` 放在 exe 同目录（或 exe 旁 `web/` 下），
  另需 `data/index/corpus.db`（缺了古籍端点 503）。

## 本地开发命令速查

```bash
# Windows 一键
web_launcher.py / start_web.bat        # 自拉起服务、开浏览器、关浏览器停服务

# 语料索引重建（data/index/corpus.db，gitignored，~10s）
.venv/bin/python scripts/check_quality.py
.venv/bin/python scripts/build_index.py

# knowledge.db 种子（selftest 的 threads.detail/share.bazi 需要——见 README 快速开始）
```

## 红线（改代码前先看）

宪法三条 + 派生纪律都在 `docs/`：所有状态声明必须带可复验命令；引文可核验
（折叠 ≠ 删除）；语料不做远端抓取；前端数据一律 `esc()`/`renderRichText`
/`fmtScalar` 渲染，`innerHTML` 不许插未转义数据；LLM 只润色不承重，必须能静默降级。
