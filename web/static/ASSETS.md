# 静态资产来源登记（R230n·R26-P3）

## AI 生图（cream/ink 系列）

`web/static/cream/` 下的插画为本项目用文生图模型生成的原创资产
（旧水墨 `ink/` 与出图原稿 `cream/*-full.png` 已于 R233o 移到仓库内
`assets_src/`——仍在 git，但不再挂在 /static 公开分发）：

- 生成后端：`agnes-image-2.x-flash`（apihub.agnes-ai.com）与
  image.pollinations.ai（早期批次）
- 生成脚本：`scripts/image_gen.py`（AGNES_API_KEY/AGNES_KEY_FILE 驱动）
- 生成时间：2026-08 前后（见 .hermes 台账记录）
- 口径：AI 生成图无第三方版权负担；页内展示均带「仅供娱乐」语境。
- R3251 批次（scripts/gen_r3250_assets.py，agnes-image-2.1-flash）：
  - `persona-{wood,fire,earth,metal,water}.jpg` 五行人格拟人熊——
    木=抱树苗/火=举星火/土=坐山丘/金=托星钻/水=乘水滴；
  - `icon-renge.jpg` 五花图标——五行人格功能卡图标
    （与 cream-icon-bazi.jpg 解复用）。
- R3252 批次（同脚本同后端）：
  - `sign-*.jpg` 9 张签面小插画——开运蛋/吃瓜/摸鱼/破水逆/暴富/
    甜甜/上岸/顺顺/生日签各一张同 IP 熊图（亮面态卡面+分享图）；
  - `hehun-bear.jpg` 双熊牵手——合婚结果页顶部插画。
- R3253 批次（同脚本同后端）：
  - `dream-*.jpg` 13 张梦境符号缩略图——掉牙/被追/坠落/飞翔/
    考试/前任/心动/蛇/水海/迷路/婚礼/猫 + 兜底月熊 dream-bear；
  - `scene-*.jpg` 6 张黄历「我打算」场景小图——搬家/开业/约会/
    面试/出行/签约。
- R3255 批次（`scripts/gen_r3255_dream1.py`，同后端）：
  - `dream-*.jpg` 再补 15 张噩梦/情绪向——鬼压床走 dream-frozen
    （被窝压影）、去世的人走 dream-gone（望星）、鬼怪 dream-ghost、
    大哭/掉发/分手/吵架/出轨/赶不上车/被困/上班/丢手机/已读不回/
    捡钱/着火各一张；累计 27/52 符号覆盖，余者仍回落 dream-bear。
- R3256 批次（`scripts/gen_r3256_dream2.py`，同后端）：
  - `dream-*.jpg` 最后 25 张补齐——亲人出事/自己出事/家人/没穿衣/
    电梯/怀孕/血伤/狗/老家/回学校/聚餐/镜子/虫子/找厕所/亲密/生理期/
    偶像/开车/剪发/丢东西/钓鱼/被孤立/丧尸末日/梦中梦/长痘变丑；
    **52 个梦境符号 100% 专图覆盖**，dream-bear 退居纯兜底。
- R3257 批次（`scripts/gen_r3257_scenes.py`）：
  - `bear-scene-{good,sml,mid,bad}.jpg` 4 张日签场景横幅——
    吉=向阳山坡/小吉=暖灯茶席/平=灰窗静坐/凶=雨窗毯堡可可；
    daily-level 由 80px 圆盘改 160×108 横幅，图本身承载档位。

## 其它来源

| 目录 | 内容 | 来源/许可 |
|---|---|---|
| `fonts/` | 得意黑/霞鹜文楷/站酷快乐体子集 | SIL OFL 1.1，见 `fonts/licenses/` |
| `tarot/` | 塔罗韦特牌面扫描 | 公版（1909 Rider-Waite，版权已过期） |
| `animotion/` | 动画库 vendored | 见 `data/catalog/external_manifest.json` |
| `assets_src/candidates/` | 出图候选/原稿（不随静态分发） | 同 AI 生图口径 |
| `assets_src/ink/` | 旧水墨主题资产（退役，存档） | 同 AI 生图口径 |
| `assets_src/cream-full/` | cream 系列全尺寸原稿 | 同 AI 生图口径 |
