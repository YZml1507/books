# specs/008 附录：开源项目调研闭环 + 素材策略

**Created**: 2026-08-22（优化轨 R196b）
**输入**: 用户提供的两轮搜索大模型调研（2026-08-20 十项 → PROPOSAL_004；
2026-08-22 十二项 → 本附录）。仓库链接已逐一经 GitHub API 验证存在。
**政策**（沿 PROPOSAL_004 §5，继续生效）：
**借鉴交互与信息架构，不搬代码不搬数据。** 无许可证的项目连代码都不读入
实现参考；MIT 项目也只在「确认我们自己会写出同样结构」时才对照，
取用代码必须先记 provenance 并在台账声明。

## A. 项目清单（2026-08-22 API 实测）

| 项目 | ★ | 许可证 | 处置 |
|---|---|---|---|
| sy-vendor/FateAtelier | 33 | MIT | 参考：多玩法聚合 IA、响应式布局、本地历史 |
| uxiaohan/Tarot-Web | 109 | **无** | 只看交互不读码：AI 塔罗的轻量部署形态 |
| dxenia/astrology-app | 39 | **无** | 只看交互：明暗双主题切换 |
| tytsxai/bazi-master | 20 | MIT | 参考：多品类信息组织（不引其数据，宪法第三条） |
| anois/tarot | 2 | **NOASSERTION** | 只看交互：3D 牌桌仪式感（CSS 3D 重实现，不用 react-three-fiber） |
| MichaelWave369/GypsyAI | 2 | MIT | 远期参考 |
| adds9810/your-tarot-mbti | 1 | MIT | US3 远期：人格×塔罗混搭 + 结果图保存 |
| hristohstefanov-purpose/human-design-app | 1 | 无 | 远期：可分享 URL 形态 |
| riccio-ryu/todays-vibe | 0 | 无 | 仅记录 |
| WQone/wx-mini-program · zhenzhongfu/tarot · thomas-void0/mbti-mini | — | 未查 | 小程序方向，Web 版落地前不启动 |

**对搜索大模型建议的采信裁定**：
- ✅ 采信：用户画像（情绪驱动/轻量/可分享/多系统混搭）——与 PROPOSAL_004
  实测诊断互相印证；幸运色/数字（004 P3 已有河图数方案）。
- ❌ 不采信：React/Next.js/Tailwind/Framer Motion 技术栈迁移（违反 D-151a
  零构建链决策，重写成本无对应收益）；html2canvas（破坏外链=0 红线，
  原生 Canvas 海报管线已存在且更轻）。
- ⚠️ 半采信：MBTI 混搭（US3 远期候选，先验证核心盘留存再议）；「一次测多种」
  聚合（008-US3 功能谱系重组正是此方向）。

## B. 素材策略（R196b 定方向，R197b 按用户拍板修订）

### B1 字体（用户拍板：网红风，不要超正式）
三件套，全部 OFL、本地子集化打包（≤300KB/字重，woff2 入 web/static/fonts/）：
| 字体 | 角色 | 许可/来源 |
|---|---|---|
| 霞鹜文楷 LXGW WenKai | 正文/文案主字体——手写楷感、温软（「奶油感」） | OFL 1.1，lxgw/LxgwWenKai（FONTWORKS Klee One 衍生） |
| 得意黑 Smiley Sans | 标题/数字/海报大字——斜体几何黑，新媒体风 | OFL，atelier-anchor/smiley-sans |
| 思源黑体 Noto Sans SC | 表单/UI 兜底（可读性优先处） | OFL，Google Noto |
- 判据不变：零外链、FCP 不慢于基线、子集化后总体积入台账。

### B2 卡牌（用户拍板：自用/公益，不在意侵权——仍走合法最优路径）
- **主路线（采纳）**：Rider-Waite-Smith 1909 原版扫描——Pamela Colman Smith
  1942 年逝世，作品全球公版。图源：luciellaes 的 **CC0** 清理包
  （itch.io，源自 Wikipedia、已修边缩放、JPG+PNG 双格式，78 张全）；
  备用图源 Wikimedia Commons（PDM 标注）与 sacred-texts.com 扫描。
- 下载入库存 web/static/tarot/（压缩到 ~400px 宽 JPEG，总量控制 ≤4MB），
  **零热链**（外链=0 不破）。牌面版式：图占上部，中文牌名+关键词在下
  （v1 的 tname/tmeaning 结构保留）。
- SVG v2 降级为补齐方案：小阿卡纳数字牌 RWS 本就有场景图（全 78 张都有），
  仅当某图源缺失时用 v1 符号方案兜底。
- 台账记 provenance：图源 URL、CC0 声明、处理步骤（压缩参数）。

### B3 背景/纹理（不变）
不引入位图。CSS 渐变（时辰感知，US4）+ 内联 SVG 纹理（data URI，
体积≈0，可被 003 判据 12 一键回滚覆盖）。

## C. 挂账闭环声明

「10 个开源项目参考未闭环」（§131/§133/§134 多轮移交）自本附录起闭环：
两轮调研合并归档于此，逐项目给了许可裁定与借鉴点，后续 US 实施时
按表对照执行。skill zip 零融入仍挂账（与本议题无关）。
