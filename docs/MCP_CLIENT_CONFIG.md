# MCP 客户端配置（guji-books）

R22b 落地了 stdio MCP server（`src/guji/mcp_server.py`，愿景 §11 最后一块）。
本文给各类 MCP 客户端接入该 server 的最小配置样例。

## 服务端事实（以代码为准，勿凭文档）

- **server 名**：`guji-books`（`mcp_server.py` 中 `MCPServer(name="guji-books")`）。
- **协议**：stdio JSON-RPC（官方 `mcp` 包 2.0.0，`mcp.server.mcpserver.MCPServer`）。
- **启动命令**（项目根目录下）：

  ```powershell
  cd C:\Users\Lenovo\Desktop\projects\books
  PYTHONPATH=src .\.venv\Scripts\python.exe -m guji.mcp_server
  ```

  - 必须用项目 venv 的 python（依赖 `mcp` 装在其中）。
  - 必须让 `guji` 包可导入：`PYTHONPATH=src` 或工作目录为项目根。
  - 语料/知识库路径由 `__file__` 推导（`data/index/corpus.db`、`data/index/knowledge.db`），
    与工作目录无关。

## 十一工具（全部复用既有内核，零新能力）

| 工具 | 作用 | 对应内核 |
|---|---|---|
| `search` | FTS 短语检索（異體字折叠），引文随附 | `Corpus.search` |
| `addr` | 六地址体系单址阅读（zhouyi/bcv/yilin/booksec/play/euclid） | `Corpus.at_address` / `at_scheme` |
| `compare` | 同址多版本对照 + 校勘级差异摘要 | `compare_address` |
| `concept` | 跨书概念普查（每书命中/层次/共享地址） | `concept_census` |
| `research_tool` | 确定性深研循环（步骤链 + 证据集 + 差异），无证据拒绝（G7） | `research` |
| `threads` | G9 研究线程：列表 / 转录 | `KnowledgeBase` |
| `bookstudy_structure` | 整书结构地图（节序/体量/经注层次/样本+真实引文） | `bookstudy.structure` |
| `bookstudy_chapter` | 单节阅读视图（原书顺序、层+引文；NULL-scheme 书用 scheme='file' + file=） | `bookstudy.chapter` |
| `compare_works_tool` | 两书对照（并排证据 + 层分布 + 同址披露，双 0 拒绝 G7） | `research.compare_works` |
| `book_summary_tool` | 整本书结构化知识卡（层分布/损坏披露/体量极端节） | `bookstudy.book_summary` |
| `add_local_work_tool` | 把本地 txt 目录加为新作品（愿景 §10/§18；**仅本地 stdio 信任边界**——参数含本地路径，web 层不暴露此类写操作） | `sources.add_local_work` |

纪律与 web/CLI 同源：引文一律服务器端渲染（G2 防伪页码）、损坏区带标记披露
（X-11）、`research_tool` 拒绝不绕过（G7）、`add_local_work_tool` 只处理
本地路径且不联网（红线第 3 类不触发）。

## 配置样例

### Claude Desktop（claude_desktop_config.json）

路径：`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "guji-books": {
      "command": "C:\\Users\\Lenovo\\Desktop\\projects\\books\\.venv\\Scripts\\python.exe",
      "args": ["-m", "guji.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\Users\\Lenovo\\Desktop\\projects\\books\\src"
      }
    }
  }
}
```

### Claude Code（CLI）

```bash
claude mcp add guji-books --env PYTHONPATH=C:/Users/Lenovo/Desktop/projects/books/src \
  -- C:/Users/Lenovo/Desktop/projects/books/.venv/Scripts/python.exe -m guji.mcp_server
```

### 其他 stdio 客户端（Cursor / 自定义）

通用三要素：`command` = venv python 绝对路径，`args` = `["-m", "guji.mcp_server"]`，
`env` 至少含 `PYTHONPATH=<项目根>/src`。若客户端不支持 `env`，把 `cwd` 设为项目根亦可
（`-m` 会把 cwd 加入 `sys.path`）。

## 验证

接入后跑一次冒烟：`tools/list` 应返回 **11** 个工具；`tools/call search`（如
`潛龍勿用`）应返回带 书名/层/卦爻地址/页锚点/源文件 的可核验引文。
（服务端自带协议级自测：`PYTHONPATH=src python -m guji.mcp_server --selftest`，
断言 tools/list 全 11 名 + 各新工具 tools/call 一例，外部客户端可据此复验。）
