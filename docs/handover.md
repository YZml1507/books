# 交接文档（小满的解忧铺 · 奶油玄学风 v2）

更新：2026-08-28（v2 奶油玄学改版）。本文档面向"接手跑起来"的新人，覆盖启动、配置、目录、排障。

## 0. v2 改版速览（2026-08-28 下午）
- **风格**：水墨命理 → 奶油玄学（奶油白 #FFF8E7 + 香芋紫 #D4B5FF + 蜜桃粉/雾霾蓝/薄荷绿马卡龙分色），依据小红书风格模型三问结论 + 联网调研（`.cluster/research/qa_log.md`）。
- **星座页**：♈ emoji 网格 → 12 张 Q 版手绘星座卡（web/static/cream/zodiac-*.jpg）；新增「查我的本命盘」（生日→太阳星座性格+四柱+五行+小满解读）；年份范围 1900-2100（原只有今年±1）。
- **起名**：评分重写为可解释口径（五行补缺 0/16/30 + 典籍 +5/8 + 寓意 +5/9 + 音形 ± + 气质契合 +2~9），每名下显示明细 chip；修复了清一色 80 分（实测一组 8 名 87→80 全不同分）。
- **聊天**：「聊聊这件事」消息补上性别（「我是女生，」+ facts 首条「性别：女」，Playwright 抓包实测）。
- 资产归档：web/static/cream/（21 张，manifest.json 清单）；旧水墨资产保留在 web/static/ink/ 未删，可随时切回。

## 1. 启动项目

**日常启动（推荐）**：双击桌面「八字命理检索」快捷方式。
- 它调用 `web_launcher.py`：无黑窗启动服务（127.0.0.1:8123）→ 自动打开浏览器 → 关闭浏览器约 60 秒后服务自动退出。
- 启动日志：`logs\web_launcher.log`。

**开发模式（要看报错/改代码热验证）**：
```powershell
cd C:\Users\Lenovo\Desktop\projects\books
.\.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8123
# 浏览器打开 http://127.0.0.1:8123
```

**自测**：`.\.venv\Scripts\python.exe web\selftest.py`（standing 自测应全绿）。

依赖：Python 3.11+（.venv 已内置全部依赖：fastapi、uvicorn、pydantic、Pillow 等）。若 .venv 损坏：`python -m venv .venv` 后 `.\.venv\Scripts\pip install fastapi uvicorn pydantic`（其余按报错补）。

## 2. API key 配置与更换

所有外部能力配置集中在 `web\llm_config.json`（已被 .gitignore，不入库）：
```json
{
  "enabled": true,                          // 总开关；false = AI 聊天/润色入口整体隐藏
  "base_url": "https://apihub.agnes-ai.com/v1",
  "api_key": "sk-…",                        // Agnes 主通道（聊天/润色）
  "model": "agnes-2.5-flash",
  "dots": { "enabled": true, "base_url": "…askdiandian.com/v1", "api_key": "ak_…", "model": "dots3-note-prev", … }
}
```
- 更换 key：直接改这个文件，重启服务生效（无热加载）。
- 环境变量覆盖：`BOOKS_LLM_API_KEY` / `BOOKS_LLM_BASE_URL`；`BOOKS_LLM_DISABLE=1` 强制关闭全部 AI。
- key 失效表现：聊天发消息后一直"思考中"或入口消失（前端按 additive 语义降级，不影响排盘）。
- **文生图 key**（生成图标/图片用，与聊天同一家 Agnes）：脚本 `.cluster\gen_assets.py` 顶部 `KEY` 常量；改 key 后可重跑 `.\.venv\Scripts\python.exe .cluster\gen_assets.py --only all` 重新生成全套资产。
- 排盘/桃花/合婚/黄历等核心功能 **不依赖任何 key**，断网也可用。

## 3. 目录结构（改版后）

```
books\
├─ web_launcher.py          桌面启动器（无窗+自动开浏览器+自动关服）
├─ start_web.bat            控制台模式启动（调试用）
├─ web\
│  ├─ app.py                FastAPI 应用工厂（静态挂载/异常/路由）
│  ├─ routers\              HTTP 绑定：bazi.py（排盘/桃花/合婚/起名/历史台账）、
│  │                        divination.py（塔罗/六爻）、product.py（黄历/星座）、reading.py（古籍）
│  ├─ services.py           编排层（调 src/guji，返回纯 dict）
│  ├─ schemas.py            入参校验（非法输入 → 中文 400）
│  ├─ errors.py             异常 → HTTP 映射
│  ├─ llm_config.json       AI 通道配置（gitignore）
│  └─ static\
│     ├─ index.html         单页前端（全部视图）
│     ├─ styles.css         主题令牌+全部样式（水墨命理色板在 :root）
│     ├─ app.js             前端逻辑（renderBazi 排盘渲染、历史 UI 在此）
│     ├─ sw.js              离线缓存（改静态资源后必须 bump CACHE_NAME）
│     ├─ ink\               水墨资产包（v1 改版产物，已不再引用，保留可回退）
│     ├─ cream\             ★ 奶油玄学资产包 v2（12 星座卡+8 功能图标+hero；
│     │                       manifest.json 清单；*-full.png 为原图）
│     ├─ tarot\             塔罗牌图 78 张（本地化，勿动）
│     └─ fonts\             内置字体 LXGW/站酷快乐/Smiley Sans（勿动）
├─ src\guji\                命理引擎（bazi_calc 排盘、lunar 农历、taohua/hehun/qiming/
│                           huangli/xingzuo/liuyao/tarot、interpreter 确定性解读、
│                           llm_polish AI 润色+聊天、paipan_history ★排盘历史台账）
├─ data\
│  ├─ paipan_history.db     ★ 排盘历史台账（新库，可随时删除重建）
│  └─ history.db            旧遗留库（已停用，仅存档勿删）
├─ docs\                    rollback.md 回滚 / assets-manifest.md 资产清单 / 本文档
├─ .cluster\                本次改版工作台（plan.md 方案、regression\ 回归记录、
│                           gen_assets.py 生图脚本、compress_assets.py 压图脚本）
└─ logs\                    运行日志
```

## 4. 新增后台功能：排盘历史台账

- 每次成功排盘自动记录（本地 SQLite `data\paipan_history.db`），刷新/重启不丢。
- 前端入口：首页「排盘历史」卡 → 列表（最新在前）→ 点开复看完整排盘 → 可删单条 → 一键导出 CSV（Excel 可直接打开）。
- API：`GET /api/paipan/history?limit=&offset=`、`GET|DELETE /api/paipan/history/{id}`、`GET /api/paipan/history/export`。
- 关闭/清空见 rollback.md 方式三。

## 5. 常见问题排查

| 症状 | 原因与处理 |
|---|---|
| 双击快捷方式没反应 | 查 `logs\web_launcher.log`；多为 8123 被占：`netstat -ano | findstr :8123` → `taskkill /f /pid <PID>` |
| 浏览器打开白屏 | 服务没起来（先看上一条）；或 sw 旧缓存：Ctrl+F5 强刷，仍不行再删 `web\static\sw.js` 里 CACHE_NAME 对应旧缓存（DevTools→Application） |
| 改了样式/图片没生效 | sw.js 缓存：bump `CACHE_NAME` 版本号或 Ctrl+F5 |
| 聊天/润色没反应 | llm_config.json 的 key 失效或断网；`"enabled": false` 可隐藏入口，不影响排盘 |
| 排盘结果和之前不一样 | 算法零改动；先核对输入（历法/闰月/时辰）。回归记录在 `.cluster\regression\regression_report.md` |
| 历史记录不见了 | 是否设过 `BOOKS_PAIPAN_HISTORY_DISABLE=1`；或误删 `data\paipan_history.db`（删除即清空，重启重建空库） |
| 生成新图片报 401/超额 | `.cluster/gen_cream.py` 顶部 KEY 失效（从 web/llm_config.json 读），更换后重跑 |
| 页面某图标破图 | 对应 `/static/cream/*.jpg` 或 `/static/ink/*.jpg` 缺失；用 `-full.png` 重压或看 manifest.json 重生成 |

## 6. 已知边界与注意事项

- 本应用面向本地单人使用，无鉴权，勿直接暴露公网。
- `probes\`、`web\selftest.py`、`web\baselines\` 是审查/自测设施：改前端时保留 `data-rsec2="bs-structure|bs-chapter|bs-summary"` 等选择器原样。
- 排盘历史含出生信息，属敏感数据：仅存本地，请勿把 `data\` 目录对外分享。
