# OPTIMIZE BACKLOG — 优化待办池

**所有权（宪法第五条）**：审查轨独占写。优化轨只读。

**本文件的存在理由**：给 MINOR / NIT 一个不阻塞阶段推进的去处。
若允许体验瑕疵和纯偏好进 `AUDIT_FINDINGS.md` 的 OPEN 清单，
`REPAIR → OPTIMIZE` 闸门将永远打不开——审查轨只要还在跑，
总能找出下一个「这里可以更好」。这是本协作模型唯一会死锁的地方。

REPAIR 阶段只**收集**不实施。翻到 OPTIMIZE 后，本池条目由审查轨
汇编进 `specs/003-youth-ui-revamp/spec.md`。

---

## 条目格式

```markdown
### B-<seq> 一句话标题
- 类型：性能 | 视觉 | 交互 | 无障碍 | 功能扩展
- 现状：<实测事实，附命令>
- 设想：<想达到什么，不写怎么实现>
- 可测量性：<如何客观验证；无法测量则写「需回滚保障」>
- 来源：R<n>a 轮次 / MINOR 降级 / 主动勘查
```

## spec 准入门槛（宪法第六条 + 全自动纪律）

写进 `spec.md` 的每条要求必须满足其一，否则不许写：

**(a) 可自动测量。** 首屏渲染时间、API p95 延迟、静态资源体积、
375px 视口无横向滚动、点击目标 ≥44px、对比度符合 WCAG AA、
尊重 `prefers-reduced-motion`、动画期间无 >50ms 长任务。

注意后几条看似「体验」实为**精致感的客观代理指标**：
廉价感往往就来自对比度不足、点击区过小、动画掉帧。

**(b) 可回滚。** 视觉方案必须能一键切回旧样式（如 CSS 变量主题切换）。
这样审查轨自主选定的审美方向即使用户事后不认可，也不构成损失——
这是「全自动决策」得以成立的前提。

审美类决策由审查轨自主拍板，但必须在 `docs/DECISIONS.md` 用 `D-<n>a`
记录至少两个候选与否决理由。不记录就等于剥夺了用户的事后否决权。

---

## 双轨环境注意事项（交接窗口实测）

- **`.venv` 不在 worktree 里。** `.gitignore` 忽略 `.venv/`，所以
  `books-audit/` 没有自己的虚拟环境。审查轨直接用主 worktree 的解释器：
  `C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`
  实测确认：它会正确加载 `books-audit/src/guji`（各轨跑各自的源码副本），
  `TestClient(web.app)` 在 audit 侧返回 200、47 部书可读。
- **运行期 db 不再随 git 走。** 三个 db 已从索引摘除（见 main 提交 71d2658），
  两轨各自持有磁盘副本、互不干扰。若 audit 侧 `data/index/` 为空，
  从主 worktree 拷贝，或按宪法第二条重建 corpus.db（5 秒可重建）。
- **别把 db 写脏当成缺陷。** `/api/bazi` 会往 `history.db` 写记录
  （D-039 已授权）。审查轨自测后应清理本轮新增记录（L-22 教训）。

## 现成素材（交接窗口实测，可直接用）

- **`web/static/animotion/` 有 287KB 动画 CSS 完全没接线。**
  `animotion.css` 84KB、`keyframes.css` 115KB、`keyframes-part2.css` 84KB、
  `utilities.css` 5.8KB。实测 `index.html` **零个外部资源引用**
  （`grep '<link\|<script src' web/static/index.html` 无命中）。
  已在仓库内，用它**不算引入新外部依赖**（不撞宪法第二条红线第 3 项）。
- **`vendor/ui-ux-pro-max/`** 是一整套 UI/UX 设计 skill 集合（含
  banner-design 等子 skill 与中英文 README），可作设计参考。
- `specs/` 现有 `001-books-audit-merge`、`002-product-rebrand`，下一编号 `003`。

## 已知可优化项（交接窗口勘查，未验证优先级）

### B-001 web/app.py 单文件 2108 行，其中 912 行是塞在 __main__ 的自测
- 类型：性能（可维护性）
- 现状：`(Get-Content web/app.py | Measure-Object -Line).Lines` = 2108；
  `__main__` 块从 1365 行到 2277 行
- 设想：已在 REPAIR 阶段作为重构任务派给优化轨，非本池条目，此处仅登记
- 可测量性：单文件行数 < 300；`web/selftest.py` 独立可跑
- 来源：主动勘查

### B-002 index.html 单文件 1485 行（CSS 396 行 + JS 643 行内联）
- 类型：性能
- 现状：`web/static/index.html` 74KB 单文件，无缓存分离
- 设想：拆 `app.js` + `styles.css`，浏览器可独立缓存
- 可测量性：首屏 HTML 体积下降；重复访问命中缓存
- 来源：主动勘查（REPAIR 阶段已派给优化轨）

### B-003 每日运势 noble 字段用出生年生肖，语义可疑
- 类型：功能扩展
- 现状：`web/app.py` `api_daily` 调 `_chinese_zodiac(d.year)`，
  `d` 是**当天日期**而非用户生日——「贵人属相」取的是今年的生肖
- 设想：明确「贵人属相」的定义并与算法对齐，或改名为准确的措辞
- 可测量性：需先定义正确语义，属需求澄清而非纯审美
- 来源：主动勘查

---

## R118a 轮次新增（2026-08-19，审查轨首轮实测）

以下 7 条均为 MINOR / NIT 降级项，**不进 AUDIT_FINDINGS 的 OPEN 清单、
不阻塞阶段推进**（PHASE.md：这是本协作模型唯一会死锁的地方）。
`<py>` = `C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`。

### B-004 黄历宜忌是数组，被 esc() 渲染成逗号串
- 类型：视觉
- 现状：`<py> probes\probe_contract.py`（SOFT 段）实测
  `index.html:1201 读 j.yi 实测值类型=list 渲染为 逗号拼接
  ["嫁娶","捕捉","求嗣","狩猎","祭祀"]`；`:1202 读 j.ji` 同理
  `["安葬","开市","立券"]`。JS `String(["a","b"])` === `"a,b"`——数据都在、
  可读，只是丢了列表结构
- 设想：宜/忌各项做成独立标签（pill），一眼看清有几条
- 可测量性：DOM 断言 `.calc-block` 内子元素数 == 数组长度
- 来源：R118a probe_contract SOFT 段（**降级理由见 D-130a**：dict 渲染成
  `[object Object]` 是数据显示错误卡闸门，array 逗号拼接是体验瑕疵不卡）

### B-005 研究线程创建成功后只回一行 id，不显示线程内容
- 类型：交互
- 现状：`index.html:1143` 成功分支只渲染
  `线程已创建：${esc(j.thread_id||j.id||'')}`；`probe_contract` 实测
  `POST /api/threads` 真实响应键为
  `['claim','derived_id','kind','n_evidence','thread_id']`——`derived_id`、
  `kind`、`n_evidence` 三个字段前端一个都没用
- 设想：创建后展示这条 claim 与证据条数，用户能确认"记下了什么"
- 可测量性：DOM 断言结果区含 claim 文本与证据计数
- 来源：R118a 主动勘查

### B-006 /api/compare 的 findings 只渲染 f.text，丢掉 kind/at/note/line
- 类型：视觉
- 现状：`<py> probes\probe_contract.py` 实测 `index.html:1092 读 j.findings.text`
  为 SOFT（有 `||''` 兜底）。真实 findings 元素键为
  `['at','base','base_id','kind','line','note','others']`——**没有 `text`**，
  且后端已提供 `line()` 渲染好的整行。即当前比对结果区**每条都渲染成空串**，
  只剩彩色边框
- 设想：改用 `f.line`（后端既有渲染），并按 `kind`
  （divergent / addition / omission / preserved-variant）着色
- 可测量性：DOM 断言每条 `.finding` 文本非空；`kind` 四类各有独立配色
- 来源：R118a probe_contract。**注意**：这条渲染出的是空白而非错误数据，
  且比对功能当前被 R000a-03 挡在不可见面板后，用户根本到不了——
  故判 MINOR 不卡闸门；R000a-03 修完后若仍空白，应升级重判

### B-007 /api/research 的 steps 步骤链前端完全没展示
- 类型：功能扩展
- 现状：真实响应含 `steps`（元素键 `['action','found','kept','note','query']`）
  与 `comparisons`，`web/app.py:484` 注释明写这是 G4「链路可展示」的实现；
  前端 `index.html:1034-1042` 只渲染证据条目，`steps` 零引用
- 设想：把检索→读地址→扩展的每一步显示出来，这是本项目「检索即推理」
  的差异化卖点
- 可测量性：DOM 断言步骤数 == 响应 `steps` 长度
- 来源：R118a 主动勘查

### B-008 works 卡片读 w.work_id 但真实字段是 id
- 类型：交互
- 现状：`index.html:1112-1115` 写 `w.work_id||w.id`、`w.units||w.count`、
  `esc(w.source||'')`。`/api/works` 真实元素键为
  `['addressed','anchored','genre','id','source','title','units','yao_addressed']`
  ——`work_id` 不存在，靠 `||w.id` 兜底才没坏
- 设想：直接读 `id`，并把已有的 `addressed`/`anchored`/`genre` 显示出来
  （47 部书的可编址率是本项目的核心质量指标）
- 可测量性：`probe_contract` SOFT 计数下降；DOM 断言卡片含编址率
- 来源：R118a probe_contract SOFT 段

### B-009 首屏三个列表并发打三次 /api/history（其中两次同一响应）
- 类型：性能
- 现状：`loadHistory()`（:1362）与 `loadRecent()`（:1387）各自 `fetch
  '/api/history'`，`loadFavorites()` 另打 `/api/user/prefs`；
  `probe_ui_smoke` 的 request 监听实测首屏即发出重复请求
- 设想：一次取回、两处渲染
- 可测量性：首屏 `/api/history` 请求数从 2 降到 1（playwright request 计数）
- 来源：R118a probe_ui_smoke 观测

### B-010 287KB animotion 动画 CSS 仍零接线（承接 B-002 的素材侧）
- 类型：视觉
- 现状：`web/static/animotion/` 四个文件共 287KB；
  `<py> -c "print(open('web/static/index.html',encoding='utf-8').read().count('<link'))"`
  → **0**。index.html 零外部资源引用，实测确认
- 设想：OPTIMIZE 阶段的年轻化视觉直接取用这套现成关键帧
- 可测量性：接线后动画期间无 >50ms 长任务；`prefers-reduced-motion` 下动画
  全部停用（两条都可自动测量，符合 spec 准入门槛 (a)）
- 来源：交接窗口勘查 + R118a 复核。**已在仓库内，用它不算引入新外部依赖**
  （不撞宪法第二条红线第 3 项）

### B-011 probes/probe_disclosure.py 自 initial commit 起即崩（与 web/ 无关）
- 类型：性能（可维护性）
- 现状：`<py> probes\probe_disclosure.py` → 退出码 1，
  `ValueError: not enough values to unpack (expected 2, got 1)`（`:132`
  `a, b = pair.split("|")`）。`git log -1` 确认最后一次改动是 initial commit
  83d7604（2026-08-14）；该文件不 import web、不在宪法第四条 13 闸门清单内。
  优化轨 R186b stash 自身改动后复跑，报同样失败——**与本轮无关，属历史遗留**。
- 设想：修好或明确标为一次性勘查脚本（与 `probe_coverage.py` /
  `probe_show.py` 的 BOM 问题同族，那两个已在 `probe_scripts_importable`
  的 KNOWN_BAD 里排除）
- 可测量性：退出码 0；或从 probes/ 移出、不再被误当闸门
- 来源：R131a 复核优化轨移交项（它主动报了这条，且自证与本轮无关）
