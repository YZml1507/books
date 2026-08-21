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

---

## R190b 轮次新增（2026-08-21，双轨对账轮实测）

以下 6 条全部由 R190b **自己跑命令**发现，不是转述任何一侧的报告。
`<py>` = `C:\Users\Lenovo\Desktop\projects\books\.venv\Scripts\python.exe`。
B-012/B-013 此前只写在 main 台账正文里、从未进本池（两侧 backlog 都搜不到），
本轮补登记，其中 B-012 已被 R189b 修掉，登记为已闭环的历史条目。

### B-012 baseline_voice 的 CASES 未钉 ask_date，跨日必然假漂移【已修 R189b】
- 类型：功能扩展（验收基建）
- 现状：R187b 实测「15 处漂移」，stash 全部改动后复跑同样 15 处——是流日
  丙寅→丁卯的日期漂移，不是代码漂移。R189b 已给全部 day 用例补
  `ask_date="2026-08-20"`。本轮复验：`<py> web\baseline_voice.py` 退出码 0，
  `14 用例逐字节一致 sha 97f0681e…`
- 设想：已闭环。保留条目是为了让「基线报 FAIL 先查日期」成为可检索的先例
- 可测量性：跨日裸跑退出码 0
- 来源：R187b 发现 → R189b 修 → R190b 复验闭环

### B-013 分享海报的长任务未在真机实测（判据 T3.3 空缺）
- 类型：性能
- 现状：`<py> web\check_poster.py`（R190b 新建）证明出图正确——PNG 249,688
  字节、1080×1440、水印实绘、零外链；但**没有任何判据测量绘制耗时**。
  spec 准入门槛 (a) 明确把「动画期间无 >50ms 长任务」列为可自动测量项
- 设想：在 check_poster 里加 `performance.measure` 断言，或用 CDP
  `Performance.getMetrics` 记录 drawPoster 的同步耗时上限
- 可测量性：drawPoster 单次同步耗时 <50ms（或明确给出低端机放宽阈值并写理由）
- 来源：R188b 自报移交 → R190b 确认判据仍空缺

### B-014 LLM 开启时四端点同步阻塞 29–32 秒，用户实际体验是长时间白屏
- 类型：性能（**本池当前最高优先级**：直接对撞用户原话「治愈、低门槛」）
- 现状（R190b 实测，未设 BOOKS_LLM_DISABLE）：

      <py> -c "...TestClient(app).post('/api/bazi', json={...})"
      call0: 29.0s ai=有
      call1: 31.8s ai=有

  根因三重叠加：`web/services.py:174` 在**请求线程内串行**调 `llm_polish.polish()`；
  `polish()` 内部 `_attempts=3` 重试；`web/llm_config.json` 的 `timeout_s=30`。
  最坏情况 3×30=90s。闸门看不见这条，因为闸门统一设 `BOOKS_LLM_DISABLE=1`
  （D-245a）——**开关把问题从闸门视野里挡掉了，不是解决了**
- 设想：AI 段落改为二次请求/流式（先出确定性结果，AI 到了再插进 `.ai-polish`
  容器），或给首个 attempt 设 3–5s 短超时后台续跑。无论哪种，确定性主体
  必须立刻上屏
- 可测量性：`/api/bazi` p95 端到端 <2s（LLM 开启时）；AI 段落到达时间单独计量；
  且 `ai_polish` 的降级语义不变（拿不到就整块不渲染）
- 来源：R190b 主动实测

### B-015 起名的完整名推荐里性别偏好实质失效，女生缺金只会得到「林鑫铭/林鑫钰/林鑫鉴」
- 类型：功能扩展（**对撞用户原话**「取名的没给出完整名字」的后半——给了，但不可用）
- 现状（R190b 实测）：

      <py> -c "from guji import qiming as q; print([f['full_name']
               for f in q.name_candidates('林',1998,7,20,14,'女')['full_names']])"
      → ['林鑫铭','林鑫铮','林鑫锦','林鑫钟','林鑫钦','林鑫钰','林鑫银','林鑫鉴']
      金字池 20 字（鑫锋铭铮锦钟钦镇钰银锐钢鉴钧铂铠镜铜铁锡）中
      FEMININE_CHARS 命中 **0**；女性向字全在木/火/土/水四行

  两个叠加原因：(a) `_full_name_combos` 排序键是
  `(-缺行命中数, -性别分, 表序)`——缺行命中优先级**高于**性别分，双字全命中
  缺行的组合永远排在前面，性别分只在同命中数内起作用；(b) 金行字池本身零
  女性向字，无论怎么排都出不来女名
- 设想：金行补女性向候选字（如 锦/铃/钗/鑫 已有，可加 銮/钥/铄/鈺/锶 类
  柔和字或「金+柔字」组合），或把性别分提到与缺行命中同级/更高，或允许
  「一字补缺行 + 一字取女性向」的混合形态优先
- 可测量性：`gender="女"` 时前 8 个 full_names 中含 FEMININE_CHARS 的 ≥5 个；
  `gender="男"` 时含 MASCULINE_CHARS 的 ≥5 个；确定性与幂等不变
- 来源：R190b 主动实测

### B-016 AI 起名文案凭空称「林先生」——facts_qiming 没把性别喂给 LLM
- 类型：功能扩展（AI 层事实完整性）
- 现状（R190b `--online` 实测，入参 `gender="女"`）：

      <py> probes\probe_llm_polish.py --online
      判据1 /api/qiming ai_polish 非空
        「林先生的八字中土行能量丰盈…」   ← 入参是「女」

  根因：`src/guji/llm_polish.py:242 facts_qiming(q)` 只喂
  姓氏/五行分布/缺行/推荐名四项，**没有性别**；`name_candidates` 的返回
  dict 里也没回填 gender。模型于是自己猜了「先生」
- 设想：`facts_qiming` 补一行「性别：女/男」（需 `name_candidates` 回填
  gender，或 services 层把 req.gender 一并传入）
- 可测量性：`gender="女"` 时 ai_polish 中「先生」零命中、`gender="男"` 时
  「女士/小姐」零命中（写进 probe_llm_polish 的 --online 用例）
- 来源：R190b 用自己新建的 probe 跑 --online 时抓到

### B-018 probe_ui_smoke 的 news.refresh 用例把外网可达性当产品判据，闸门因此永绿不了
- 类型：功能扩展（闸门设计）
- 现状（R190b 实测，**含干净 HEAD 对照**）：

      <py> probes\probe_ui_smoke.py            → 退出码 1，37 用例 PASS 36 / FAIL 1
      [FAIL] btn:news.refresh: '暂无新闻（外部资讯需代理可用）'

      # 归因三步，全部实测：
      # 1) 设 GUJI_PROXY=http://127.0.0.1:7897 后复跑 → 仍 FAIL（不是没设代理）
      # 2) curl 直连与走代理都拿不到那两个源：
      #    curl -m10 https://feeds.bbci.co.uk/zhongwen/simp/rss.xml → 000
      #    curl -m10 https://www.solidot.org/index.rss              → 000
      #    （同一网络 curl https://news.ycombinator.com → 200，故非全网不通）
      # 3) git stash -u 清空本轮改动、用干净 HEAD 复跑 → **同样 36/37 同一条 FAIL**
      #    且 git log 2cbb1f8..HEAD 对 probe_ui_smoke.py / src/guji/external.py
      #    的改动数 = 0（这三轮从未碰过 news 路径）

  结论：这是**环境判据混进了产品闸门**。后端行为其实是正确的——取不到源就渲染
  「暂无新闻（外部资讯需代理可用）」降级文案；probe 却把「命中『暂无』」判为
  FAIL。于是只要用户网络到不了 BBC/Solidot，宪法第三条闸门（UI 冒烟）
  **在任何一轮都不可能全绿**，各轮只能反复口头说明「这条不算」——这正是
  「闸门永远返回非 0 等于没有闸门」的镜像问题
- 设想：把该用例拆成两条判据——(a) 端点返回 200 且结构合法（可离线）；
  (b) 外网可达时才断言有条目（用 `--online` 或探测可达性后 skip 并显式打印
  SKIP 而非 FAIL）。**不得**为了变绿删掉这个用例
- 可测量性：断网环境下 `probe_ui_smoke` 退出码 0 且打印 1 条 SKIP；
  联网环境下同一脚本对 news 条目做真实断言
- 来源：R190b 主动实测 + 干净 HEAD 阳性对照

### B-017 首页「今日运势」卡的贵人属相语义可疑（B-003 的复现确认）
- 类型：功能扩展
- 现状：B-003 早已登记，R190b 复核确认代码路径未变：`api_daily` 仍以
  **当天日期**算生肖，而 UI 文案写「🍀 贵人属相」——用户会理解为「与我相合的
  属相」。这条与 B-003 同源，此处仅登记「已复核仍在」，不重复开条目
- 可测量性：需先定义正确语义（属需求澄清），故仍留本池不进 spec
- 来源：R190b 复核 B-003
