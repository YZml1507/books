# _candidates 资产登记（R228l）

本目录存放设计备选素材与生成原稿。**接线状态**逐文件登记，避免下一轮审查再把
备选资产当孤儿误删。

**R233d 变动**：所有已接线资产迁出本目录 → `web/static/shared/`（接线资产不住
`_candidates`，本目录只放未接线候选与源稿）。

## 已接线（代码引用中）

本目录下**没有**已接线文件。当前接线图资产：

| 文件 | 引用位置 |
| --- | --- |
| `../shared/daily-box-gift.png` | index.html 每日运势卡（256px 版，原稿 1024px 已删） |
| `../shared/icon-set-moon-cat.jpg` | app.js 聊天空态图 |
| `../shared/poster-bg-peach.jpg` | app.js `POSTER_BG.warm`（暖色底） |
| `../shared/poster-bg-sakura.jpg` | app.js `POSTER_BG.sakura`（樱粉底） |
| `../shared/poster-bg-lilac.jpg` | app.js `POSTER_BG.lilac`（夜紫底） |
| `../shared/poster-bg-dream.jpg` | app.js `POSTER_BG.dream`（起名海报） |

## 未接线备选（有意保留，零代码引用）

| 文件 | 说明 |
| --- | --- |
| chat-avatar.png | 小满头像候选（现用 cream/avatar） |
| daily-box.png | 每日运势礼盒候选（现用 shared/daily-box-gift.png） |
| share-bg-night.png / share-bg-warm.png | 分享图底备选 |
| r212b/avatar-xiaoman.png（实为 JPEG） | 小满头像候选 |
| r212b/badge-level-star.png（实为 JPEG） | 等级徽章候选 |
| r212b/poster-bg-night.png（实为 JPEG） | 夜版海报底（R230r 摘掉预载，保留备选） |

## 生成源稿存档（有意保留）

| 目录/文件 | 说明 |
| --- | --- |
| `r212b/*-src.png` ×5 | v2 头像/卡背/hero/起名图标的 1024px 原稿（线上用缩小版） |
| `r231a/`（71MB，161 文件） | 塔罗 78 张源稿 + RWS 扫图 + v2 候选——台账 L10913+ 登记；迁移出 /static 与否属用户拍板项 |

删除任一文件前，先确认对应文件没有计划复用——这些是按
`_candidates` 命名规约存档的落选项，不是垃圾。

## 字体档案（R228p）

| 文件 | 状态 |
| --- | --- |
| `../fonts/smiley-sans.woff2` | 得意黑全量字体（1.15MB）——源档案；线上接线的是 `smiley-sans-subset.woff2`（2.1KB，子集：吉/平/缓/凶/digits，.daily-level 唯一消费）。若未来 Smiley Sans 要渲染更多文字，需重新生成子集（pyftsubset）。 |
