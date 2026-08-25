# R213b 前置方案：面向 15-25 岁年轻女性用户的产品改造（2026-08-24）

> 状态：**方案稿，未接线任何代码**。所有图片候选在
> `web/static/_candidates/r212b/`，待用户过目批准后才接入正式引用（用户职权条款）。

## 一、资产盘点回答

- `share-bg-night.png` **有被引用**：`web/static/app.js:2216`
  `POSTER_BG.night.src = '/static/_candidates/share-bg-night.png'`——但
  `_paintSharePoster()`（app.js:860）实际只画 `POSTER_BG.warm`，
  night 处于「加载了但没用上」的半空转状态。
- 其余三张（chat-avatar / share-bg-warm / daily-box）均已接线。

## 二、调研结论（信源：36氪 2026-08 prompt 占星报道、小红书 2025 活跃用户
报告转述、千瓜/数英趋势稿、Agent-Reach xiaohongshu 渠道源码）

1. **人群画像**：小红书 3 亿月活，女性 72%，18-24 岁超 43%——与产品目标
   完全重合。消费决策三特征：颜值驱动、功能刚需、情绪共鸣。
2. **赛道现状**：#deepseek算命 话题浏览 5,608 万、讨论 35.4 万。用户正在
   用「复制粘贴 prompt 到 chatbot」手搓占卜工作流，痛点是：
   - 现有 App 只「给答案」，不「陪用户解释自己」（Co-Star 模板感强）；
   - 缺上下文记忆，无法承接「我上周和老板吵架了，这周适合提涨薪吗」；
   - 真人咨询贵且有表达压力（AstroTalk $0.99-5/分钟）。
   → **结论：用户要的是「记得住来龙去脉的随身占卜闺蜜」**。本产品的
   agnes AI 聊天正是对的方向，但要把「上下文连续性」做实。
3. **可玩性 > 直接给答案**：prompt 流行的本质是占卜从一次性结果消费变成
   可反复参与的过程。产品应强化「抽卡感/仪式感」（每日一签、翻牌动效）
   而不是把结果更快地糊到脸上。
4. **内容偏好**（知乎塔罗推广分析）：日运类、情感类、招财玄学好物分享
   与日常生活场景结合的帖子流量最大——对应本产品的 daily/taohua/hehun
   卡片应做成可截图传播的小红书卡片样式。
5. **视觉语言**：低饱和莫兰迪粉紫、新中式国潮混搭、kawaii 贴纸风、
   圆角厚描边、云朵月亮星星桃花意象；拒绝工具感表单和术语。

## 三、改造方案（分四期，每期一轮 R<n>b）

### P1 视觉皮肤（低成本高感知，建议先做）
- 全站色板从「米黄宣纸」迁到「莫兰迪粉紫渐变 + 奶油白卡片」，
  CSS 令牌层替换（已有 legacy 回退主题机制，天然留退路）。
- 卡片圆角加大（16→20px）、厚软阴影、贴纸式描边。
- 图标/徽章换候选图风格（badge-level-star.png 已达标 8/10）。
- 新海报背景二选一接线：poster-bg-dream.png（粉月夜）或
  poster-bg-peach.png（新中式桃枝，中央大留白最适合排版）。

### P2 聊天体验 = 核心差异化（对应调研结论 2）
- 小满头像升级为 avatar-xiaoman.png（9/10，已验证无水印）。
- **上下文记忆**：会话内记住用户问过的领域（事业/感情/学业），
  追问时主动引用上一轮（agnes API 侧加 system prompt 摘要注入）。
- 回复结构改为「一句共情 → 一个比喻 → 一条可执行小建议 → 反问收尾」，
  拉近闺蜜感；禁排比句和术语。
- 空状态配 icon-set-moon-cat.png（睡觉猫=等待中，语义完美）。

### P3 仪式感与可玩性
- 今日卡改「翻牌」交互：先见牌背（daily-box-gift.png 礼盒），点击翻转
  出结果（只动 transform，符合 check_plain_first 判据 2 余量纪律）。
- 分享海报全面重绘：用新背景图 + 三行内大字 + 贴纸徽章，输出即小红书
  成图（1080×1440 已满足）。

### P4 传播闭环
- 海报角落加二维码/口令位；文案模板按小红书标题习惯写
 （「准到心慌」「今日宜…」体），由 warm_voice 判据家族加新闸门约束。

### 工具链备注（本次调研实测）
- Agent-Reach-main：15 渠道互联网接入框架。**小红书渠道当前 off**
 （需 OpenCLI 复用桌面 Chrome 登录态，或 xiaohongshu-mcp + Cookie-Editor
 手工导出）。若用户希望直接抓小红书笔记做竞品/素材分析，需其手动配置
 cookie（agent-reach configure xhs-cookies）；宪法红线不自动登录。
- deer-flow-main：字节开源 super-agent harness（子代理编排/沙箱/skills）。
 对本项目参考价值主要在其 skills 组织方式；引入整套 harness 收益存疑，
 建议仅借鉴其 skill 目录规范。

## 四、本轮已产出（待批准清单）

| 文件 | 用途 | 目测评分 |
|---|---|---|
| r212b/poster-bg-dream.png | 夜间/粉月海报背景 | 8.5 |
| r212b/poster-bg-night.png | 星空宝塔夜间海报背景 | 9 |
| r212b/poster-bg-peach.png | 新中式暖色海报背景 | 9 |
| r212b/avatar-xiaoman.png | 小满聊天头像 | 9 |
| r212b/daily-box-gift.png | 今日卡礼盒插画 | 9 |
| r212b/badge-level-star.png | 等级徽章/图标 | 8 |
| r212b/icon-set-moon-cat.png | 空状态/装饰 | 9 |

来源说明：FLUX 3 免费期结束不可用，本批图片经 Pollinations.ai
（免 key 公开生图 API）生成，均为 AI 生成素材、无文字水印。
