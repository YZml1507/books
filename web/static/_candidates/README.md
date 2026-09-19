# _candidates 资产登记（R228l）

本目录存放设计备选素材。**接线状态**逐文件登记，避免下一轮审查再把
备选资产当孤儿误删。

## 已接线（代码引用中）

| 文件 | 引用位置 |
| --- | --- |
| r212b/daily-box-gift.png | index.html 每日运势卡 |
| r212b/icon-set-moon-cat.png | app.js |
| r212b/poster-bg-peach.png | app.js `POSTER_BG`（海报「存成图」暖色底） |
| r212b/poster-bg-night.png | app.js `POSTER_BG`（夜版底） |

## 未接线备选（有意保留，零代码引用）

| 文件 | 说明 |
| --- | --- |
| chat-avatar.png | 小满头像候选（现用 cream/avatar） |
| daily-box.png | 每日运势礼盒候选（现用 daily-box-gift.png） |
| share-bg-night.png / share-bg-warm.png | 分享图底备选 |
| r212b/avatar-xiaoman.png | 小满头像 v2 候选 |
| r212b/badge-level-star.png | 等级徽章候选 |
| r212b/poster-bg-dream.png | 海报底第三方案 |

删除任一「未接线」文件前，先确认对应文件没有计划复用——这些是按
`_candidates` 命名规约存档的落选项，不是垃圾。

## 字体档案（R228p）

| 文件 | 状态 |
| --- | --- |
| `../fonts/smiley-sans.woff2` | 得意黑全量字体（1.15MB）——源档案；线上接线的是 `smiley-sans-subset.woff2`（2.1KB，子集：吉/平/缓/凶/digits，.daily-level 唯一消费）。若未来 Smiley Sans 要渲染更多文字，需重新生成子集（pyftsubset）。 |
