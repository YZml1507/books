# 水墨命理资产包清单（web/static/ink/）

生成方式：Agnes API `agnes-image-2.1-flash` 文生图（base：https://apihub.agnes-ai.com/v1），统一 prompt DNA = Neo Shen 水墨 + 深蓝/暖灰/柔金 + 诗意留白 + 无文字。生成脚本：`.cluster/gen_assets.py`（可重跑再生成）。机器可读清单：`web/static/ink/manifest.json`（含每张图的 prompt、原始尺寸、来源 URL）。

## 网页引用版（.jpg，压缩后）
| 文件 | 尺寸 | 大小 | 用途 | 引用位置 |
|---|---|---|---|---|
| ink-logo-square.jpg | 256×256 | 13KB | 品牌印/头像 | 首页品牌区、favicon 源 |
| ink-banner-hero.jpg | 1440×384 | 135KB | 首页 hero 横幅 | 首页顶部 |
| result-banner.jpg | 1440×384 | 138KB | 排盘结果顶图 | 排盘结果卡 |
| bg-ink-wash.jpg | 1280×1280 | 182KB | 全局背景纹理 | body 低透明度平铺 |
| icon-tarot.jpg | 256×256 | 18KB | 塔罗占卜入口 | func-card |
| icon-bazi.jpg | 256×256 | 19KB | 今日命盘入口 | func-card |
| icon-taohua.jpg | 256×256 | 18KB | 桃花运入口 | func-card |
| icon-hehun.jpg | 256×256 | 16KB | 八字合婚入口 | func-card |
| icon-huangli.jpg | 256×256 | 17KB | 黄历入口 | func-card |
| icon-xingzuo.jpg | 256×256 | 15KB | 星座入口 | func-card |
| icon-liuyao.jpg | 256×256 | 17KB | 六爻入口 | 老玩家抽屉 |
| icon-qiming.jpg | 256×256 | 18KB | 起名入口 | 老玩家抽屉 |
| avatar-xiaoman-v2.jpg | 256×256 | 21KB | 小满聊天头像 | 聊天侧栏 |
| favicon-64.png | 64×64 | 8KB | 浏览器标签图标 | index.html head |

## 源文件（-full.png，1024/1440 原图，替换或再加工用）
与上表同名的 `*-full.png` 共 13 张，每张 1.5-1.8MB。重新压图：改 `.cluster/compress_assets.py` 里的尺寸/质量参数重跑。

## 替换/新增资产的方法
1. 用 `.cluster/gen_assets.py` 里的 gen() 直接调 API（key 在脚本顶部，更换 key 改那一行）；
2. 或手动把新图放进 web/static/ink/，压成上表尺寸；
3. 同名替换 .jpg 后 bump sw.js 的 CACHE_NAME 版本号，用户刷新即生效。

## 质量抽查结论（AI vision 审图）
- ink-logo-square：禅圆 ensō + 金色泼墨，居中对称、无文字水印，适合品牌印/圆头像/favicon（评语：蓝金对比高级耐看）。
- icon-taohua：水墨桃枝 + 落金花瓣，圆角方构图贴合图标规范；48px 以下细节会糊，建议网格里保持 ≥56px 显示。
