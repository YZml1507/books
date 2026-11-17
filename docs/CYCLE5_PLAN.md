# 周期五方案：账号前置 / 未来信入口 / 日卡 meta 药丸流

调研基准：服务器现役 `app.js`（1,650,492B / 31,784 行，md5 `24497948…`）、
`styles.css`（279,956B）、`index.html`（109,108B）——`/workspace/books/ref/`。
全部结论均以现役代码行号为准，非本地过期副本。

---

## 任务一：登录/注册前置 + 注册即收生日 + 登录即开礼物

### 1.1 调研结论（链路其实是通的，缺的只是「注册时收生日」）

| 环节 | 现役实现 | 判定 |
|---|---|---|
| 账号卡位置 | `#accountCard` 在 `#view-history`（排盘历史视图）内，`index.html:1364`，夹在工具栏/小锁面板与 `memoryCard` 之间 | ❌ 用户直报：入口埋在「排盘历史」里 |
| 开礼物的生日门槛 | `app.js:17831` `_tryReveal`：`var _meR = _meGet('me'); if (_meR && _meR.y && _meR.m && _meR.d) { _reveal(); return; }` | ✅ **已支持「有完整档案→直接拆」**，不必改门槛 |
| 表单门 | `_bindDailyAsk`（`app.js:17867`）：`_ask.hidden = _hasMe` | ✅ 有档案时表单自动隐藏 |
| 生日档存储 | `_meSave('me', rec)`（24835，合并写+昵称清洗+未来年拒收+时辰 0–23 闸）；`_meSaveFromBirth('me',{y,m,d,h,lunar,leap,n})`（24905，含农历换算、换人清旧名） | ✅ 现成，直接复用 |
| 云端备份是否带生日 | `_DATA_RE`（`app.js:29281`）含 `me$` 与 `me:partner$`；`_buildBackupBundle`（29350）按此白名单打包 | ✅ **登录拉回即还原生日档案** |
| 生日修改入口 | `_renderMeStrip`（25056）档案行「改」钮 → `showView('xingzuo')` + 开 `#birthDrawer` | ✅ 已存在，保留 |

**结论：只要让「注册」把生日写进 `me`，整条「注册→落档→直接开礼物」就通了；
「换设备登录→拉回备份→`me` 还原→直接开礼物」也本来就是通的。**
不需要新造门槛、不需要改礼物逻辑、不需要改备份白名单。

### 1.2 处方

**A. 注册表单收生日（核心）**
- `#acctForm` 增加「生辰」三字段：年 `data-k="y"`、月 `data-k="m"`、日 `data-k="d"`（必填），时辰 `data-k="h"`（选填）。
- 注册成功分支里，在原有 `_saveCreds` / `_push(false,true)` 之外，调用现成的
  `await _meSaveFromBirth('me', { y, m, d, h, n })`。
- 复用既有校验：未来年拒收（`_meSave` R3320）、时辰 0–23 归一（`_meSave` R4706a）、
  昵称清洗（R2345）、农历换算失败即不落档（`_meSaveFromBirth` 内 `if (!cj || !cj.solar) return`）。
  **不新写任何校验逻辑，零新规则。**
- 落档后重刷首页日卡（`_mountDailyCover` + `loadDaily`），封面若已被 `dailyRevealed:` 记过则直接呈现，
  否则下次点封面即 `_reveal()` 直拆（因为 `me` 已完整）。

**B. 账号入口前置（UI）**
- 把 `#accountCard` 从 `#view-history` **整体搬出**，新建 `#view-account` 视图承载（纯 markup 迁移，JS 全部按 `getElementById('accountCard')` 绑定，不依赖父容器）。
- 日卡顶行 `.daily-top` 增加一枚紧凑账号钮（未登录：「🔐 登录/注册」；已登录：显示昵称），
  位于日期与礼盒之间——**首页第一屏、拆礼物之前就够得着**，直接解决「埋在排盘历史里」。
- IA 入口组补一张 `data-view="account"` 卡（排在抽屉组末位，不破坏 R3249i「renge 首位」与 R3210 起名前移的既定次序）。
- **009 非目标遵守**：`/api/account/*` 路由、备份/同步/小锁、判档显隐全部不动；只搬入口与视图归属。
- selftest `home.ia.count` 17→18、`home.ia.drawer` 末位补 `"account"`（有意的 IA 变更，非回归）。

**C. 生日修改入口（已存在，只补一句文案）**
- 档案行「改」→ `#birthDrawer` 保持原样。注册成功后 toast 里点明「生辰可在『你的小档案 · 改』里随时改」。

### 1.3 风险
- 注册多三个必填字段 → 门槛变高。**对策**：文案明说「生日用来把礼物包成你的，随时能改」，时辰保持选填。
- `_meSaveFromBirth` 是 async，注册链里 await 失败不能让注册整体失败 → `try/catch` 兜底，落档失败只提示、不阻塞注册。
- `#accountCard` 迁移后历史视图少一块 → 保留原位的「小满账号」文字链跳 `#view-account`，不出现死胡同。

---

## 任务二：「✉️ 写给未来的自己」下划线 + 空盒排版

### 2.1 调研结论（下划线是上一轮刻意留的，你现在判它难看）

`styles.css:4310-4316`：
```css
/* R12：打卡区唯一裸文本行……补 ck-quest 同族软卡底归队；下划线/文案不动。 */
.fl-entry{display:flex; align-items:center; gap:10px;
  margin:8px 0 2px; padding:8px 12px; flex-wrap:wrap;
  background:var(--accent-soft); border:1px dashed var(--border);
  border-radius:10px;}
.fl-write{background:none; border:0; padding:0; font-size:12.5px;
  color:var(--primary-ink); cursor:pointer; text-decoration:underline;
  text-underline-offset:3px;}
```
- 下划线来自 `.fl-write` 的 `text-decoration:underline`（**R12 当轮注释白纸黑字「下划线/文案不动」**——
  是刻意的历史决策，不是漏复位）。用户本轮直接判它难看 → 依「先去掉」执行。
- 空盒成因：`.fl-entry` 给了软卡底 + 虚线框，实测高 **82px**，里面只有一个 **44px** 的按钮
  （`.fl-pend` 恒空 h=0），上下各空 ~29px/9px → 「悬在大空盒左上角」。
  而同族 `.checkin-quest`/`.ck-quest` 兄弟块都有实内容，只有它是个空壳卡。
- DOM 结构（`app.js:23632`）：`<div class="fl-entry"><button class="fl-write" id="flWrite">✉️ 写给未来的自己</button><span class="fl-pend" id="flPend"></span></div>`。

### 2.2 处方

**A. 先去掉横线（用户点名第一项）**
- `.fl-write` 删 `text-decoration:underline` / `text-underline-offset`。
  按钮已有 `cursor:pointer` + 主色 `--primary-ink`，可点性不靠下划线表达。

**B. 排版归队（去掉「空盒」观感）**
- `.fl-entry` 去掉虚线框与软卡底，改成与 `.checkin-q` 同族的**quiet 行**：
  `padding:6px 0; border:0; background:none`，高度随内容收缩（44px → ~40px，消除 38px 空悬）。
- 保留 `.fl-pend`（待送达计数）——有内容时才有信息量，不删功能。
- 悬停/焦点给 `.fl-write` 一个 subtle 反馈（`color` 加深），替代下划线承担的「这是可点的」语义。

### 2.3 风险
- 去掉下划线后「可点性」是否还认得 → 用主色 + hover 补偿；视觉上它仍是行内唯一带 ✉️ 的按钮。
- 软卡底是 R12 为「唯一裸文本行」补的 → 本轮改为 quiet 行仍解决同一诉求（不再裸悬），
  且与 `.checkin-q`（21px 纯文本行）同族，一致性更好。

---

## 任务三：`.daily-meta` 药丸流排版 + 展开/收起钮

### 3.1 调研结论（实测几何，1440×900）

`_dailyMetaCap()`（`app.js:22573`）：取 `.daily-meta` 下全部 `.daily-meta-item`（除 `#dailyMetaMore`），
可见非 pin 粒 >5 时把第 6 粒起打 `data-capped="1"`（`styles.css:705` 隐藏），
并 **`_metaRow.appendChild(_more)`** 把「收起 / +N 条」钮塞进药丸流末尾，且它
**与内容粒共用同一个 class `daily-meta-item`**。

实测（1440，rowW=994）：

| 粒 | x | y | w | h |
|---|---|---|---|---|
| 🍀 今日贵人·合拍 | 223 | 0 | 241 | 52 |
| ✅ 宜试试 | 472 | 0 | 451 | 52 |
| ✅ 做完了 `dailyRitual` | 1030 | 8 | 87 | **44** |
| 📜 今日卦签+解签 `dailySignNo` | 223 | 60 | 235 | **78** |
| 🎨 开运色 `dailyLucky` | 466 | 60 | 375 | **78** |
| 👗 今日穿搭 `dailyOutfit` | 849 | 60 | 229 | **78** |
| **+5 条 `dailyMetaMore`** | 1086 | **80** | 74 | **58** |

**病灶（三条，全部有数）：**
1. **「收起/+N 条」与内容粒同 class、同在 flex 流里** → 它长得跟「开运色」一样是颗药丸，
   用户认不出它是控件；`appendChild` 到末尾意味着**展开态下它被埋到长长一串参差药丸的尽头**
   （截图里夹在「财神方位」与「下周早知道」中间），位置随 wrap 浮动 → 「怪怪的」。
2. **高度四种**：52 / 44 / 78 / 58 → 同视觉层里参差；
   `dailyMetaMore` h=58 且 y=80（比同行 78px 粒低 20px 起），**与同行不对齐**。
3. **390px 下 `.daily-meta` 是 `overflow-x:auto` + `nowrap` 横滚**（实测内容宽 ~1356px 进 284px 视口），
   此时「+N 条」在横滚尽头第 7 颗，要滑到底才看得见。

### 3.2 处方

**A. 把展开/收起钮移出药丸流（主刀，直击「怪怪的」）**
- `#dailyMetaMore` 不再 `appendChild` 进 `.daily-meta`，改为插到 `.daily-meta` **之后的自立行**
  （`_metaRow.parentNode.insertBefore(_more, _metaRow.nextSibling)`）。
- 样式从「药丸」改成**安静的文本钮**：`display:block; width:100%; text-align:left;
  background:none; border:0; padding:6px 2px; font-size:12px; color:var(--muted)`，
  前缀「＋」/「↑」明示方向。→ 与内容粒彻底分层，位置恒定在药丸流正下方，任何视口一致。
- 390px 横滚态同样受益：钮在横滚区**外面**，不用滑到底。

**B. 药丸高度归一（治「乱」）**
- `.daily-meta-item` 统一 `min-height`，使单行粒（52）与多行粒（78）同行时不再参差；
- `dailyRitual`（「✅ 做完了」，44）与同行内容粒对齐；
- `.sign-peek`（「解签」）在卦签粒内保持行内，但给固定 `min-height` 防被挤到第二行
  （截图里「解签」已被挤到 pill 内第二行）。

**C. 折叠语义不动**
- `data-capped` / `dataset.expanded` / `+N 条` 计数（`_unpin.length - 5`）逻辑零改动，
  只改容器归属与样式。pin 机制（R3412）不碰。

### 3.3 风险
- 钮移出 `.daily-meta` 后，`_dailyMetaCap` 里 `_kids` 过滤条件 `n.id !== 'dailyMetaMore'` 仍成立（双保险）。
- 横滚态（<640px）钮在容器外，需确认不引入横向溢出 → 实测 390 档 `overflowX`。
- `min-height` 可能让本就很满的行变高 → 以实测行高与 `#dailyCard` 总高为准，增幅 >12px 即回退该子项。

---

## 验收口径（三项共用）

1. `bump_sw.py` 刷新 SW 缓存名。
2. `web self-test PASS (458 checks)`（任务一因 IA 变更 17→18，改为 459）。
3. 五档实测：1440 / 1920 / 1024 / 390 / 暗色，每档出图 + `overflowX` 断言。
4. 落档 `docs/DECISIONS.md`（D-918…D-920）、`docs/TASK_LEDGER.md`。
