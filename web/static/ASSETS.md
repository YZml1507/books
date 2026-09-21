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

## 其它来源

| 目录 | 内容 | 来源/许可 |
|---|---|---|
| `fonts/` | 得意黑/霞鹜文楷/站酷快乐体子集 | SIL OFL 1.1，见 `fonts/licenses/` |
| `tarot/` | 塔罗韦特牌面扫描 | 公版（1909 Rider-Waite，版权已过期） |
| `animotion/` | 动画库 vendored | 见 `data/catalog/external_manifest.json` |
| `assets_src/candidates/` | 出图候选/原稿（不随静态分发） | 同 AI 生图口径 |
| `assets_src/ink/` | 旧水墨主题资产（退役，存档） | 同 AI 生图口径 |
| `assets_src/cream-full/` | cream 系列全尺寸原稿 | 同 AI 生图口径 |
