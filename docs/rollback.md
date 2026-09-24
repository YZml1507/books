# 回滚说明（一键恢复改版前状态）

> **v2 奶油玄学改版（2026-08-28 下午）另有两层回退：**
> ① 改码前快照：`C:\Users\Lenovo\Desktop\projects\books_backup_20260828_v2`（水墨 v1 完整状态），按下面同样步骤整目录恢复即可回到 v1；
> ② 仅回退风格不回退功能：v2 只改了 `web/static/styles.css` 的 `:root` 令牌值与背景层、`index.html` 的资源引用（cream→ink 路径互换）、`sw.js` 缓存名，把 `web/static/cream/` 引用换回 `web/static/ink/`（旧水墨资产未删）+ bump CACHE_NAME 即可切回水墨视觉，功能修复（星座/评分/聊天性别）不受影响；
> ③ git：`git stash` / `git checkout -- web` 可回到任意已提交状态（改码前工作树状态见快照）。
> **v4 交接修复（2026-08-29 凌晨）另有一层回退：**
> ④ 改码前快照：`C:\Users\Lenovo\Desktop\projects\books_backup_20260828_v4`
>（v3 修复后完整状态，已排除 .venv/.git/build/dist/logs/Temp/__pycache__ 等重目录）。
> 本轮只改了 `web\static\` 四个文件：`app.js`（恢复丢失常量块 + humanCite 正则 + 今日解读折叠
> + 黄历场景结论）、`index.html`（悬浮钮标签）、`styles.css`（chip 配色 + 新样式块）、
> `sw.js`（CACHE_NAME → books-shell-v4-fix1）。仅回退前端：把快照里这四个文件覆盖回
> `web\static\` 即可，回退后浏览器 Ctrl+F5 强刷一次（旧 CACHE_NAME 需要绕过 SW 缓存）。

改版时间：2026-08-28。改版前完整备份位于：
`C:\Users\Lenovo\Desktop\projects\books_backup_20260828`

## 方式一：整目录回滚（最稳，推荐）
1. 关闭服务：任务栏托盘无窗口；先在 PowerShell 执行
   `netstat -ano | findstr :8123` 找到监听 PID，再 `taskkill /f /pid <PID>`。
   若桌面快捷方式开着浏览器，先关浏览器（launcher 会自动关服）。
2. 把现目录改名保留现场（可选）：
   `Rename-Item 'C:\Users\Lenovo\Desktop\projects\books' 'books_ink_v2'`
3. 恢复备份：
   `Copy-Item 'C:\Users\Lenovo\Desktop\projects\books_backup_20260828' 'C:\Users\Lenovo\Desktop\projects\books' -Recurse`
4. 重建虚拟环境（备份不含 .venv，用它跑起来需要一次重建）：
   `cd C:\Users\Lenovo\Desktop\projects\books`
   `python -m venv .venv`（或把现 books_ink_v2\.venv 整个复制回来，二进制兼容最省事）
   `.venv\Scripts\pip install -r requirements-ci.txt playwright==1.63.0`；
   PyTorch CPU wheel 从阿里云 flat wheel 镜像解析：
   `.venv\Scripts\pip install "torch==2.14.0+cpu" --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/`；
   浏览器闸门再执行 `.venv\Scripts\python -m playwright install chromium`。
5. 双击桌面「八字命理检索」验证恢复。

> 简化路径：如果不想动 .venv，可只回滚被改的目录——把备份里的
> `web\static\`、`web\routers\`、`web\services.py`、`web\app.py`、`src\guji\` 覆盖回现目录，
> 再删除 `data\paipan_history.db`（新台账库）即可。

## 方式二：git 回滚（源码部分，最快）
项目是 git 仓库（main 分支，改版前工作树干净）：
```
cd C:\Users\Lenovo\Desktop\projects\books
git stash push -m "ink-v2 改版现场"            # 或 git checkout -- web src
git status                                     # 确认 web/ src/ 已还原
```
注意：git 不管理 `data\paipan_history.db`，需手动删除；`web\llm_config.json` 被 gitignore，不会被 git 还原（它本次未被改动，无需回滚）。

## 方式三：功能级开关（不回滚文件）
- 排盘历史台账整体关闭：设环境变量 `BOOKS_PAIPAN_HISTORY_DISABLE=1` 后重启服务。
- 历史数据清空：删除 `data\paipan_history.db` 文件，重启自动重建空库。
- AI 聊天/润色关闭：`web\llm_config.json` 里 `"enabled": false`。

## 回滚后验证
1. 双击桌面「八字命理检索」→ 浏览器自动打开 http://127.0.0.1:8123
2. 首页正常渲染、排盘一次出结果即恢复成功。

## 运维坑备忘（R58-P2-4）
`data/index/*.db`（knowledge.db / paipan_history.db 等 SQLite）被 chmod 只读后，
SQLite 会连带生成 `-shm`/`-wal` sidecar 且同为只读。**恢复时只 chmod 主文件不够**
——要三个文件一起恢复或直接删 sidecar 重建：
```
chmod 664 data/index/knowledge.db data/index/knowledge.db-shm data/index/knowledge.db-wal
# 或删掉 -shm/-wal，下次写时自动重建
```
