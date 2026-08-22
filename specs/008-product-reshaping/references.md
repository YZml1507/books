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

## B. 素材策略（用户问「要不要去找素材」的答案：要，按三类分治）

### B1 字体（优先级最高，性价比最大）
- 只接受 **SIL OFL** 许可：思源黑体（Noto Sans SC）/ 思源宋体（Noto Serif SC）。
- 必须 `fonttools` 子集化到页面实际字符集（目标 ≤300KB/字重），
  woff2 本地打包进 web/static/fonts/（不引 CDN，外链=0 不破）。
- 判据：selftest 断言 fonts 目录零 http 引用；FCP 不慢于基线（003 判据 7）。
- 禁：任何「免费可商用」但许可不明的中文字体（侵权风险不可逆）。

### B2 卡牌与插画
- 主路线（默认）：**程序化 SVG v2**——底纹 + 意象构图 + 数字/花色徽记，
  完全自有版权、随 seed 变化的独占风格（US2）。
- 备选路线（需用户拍板）：公版 Rider-Waite 扫描图（1909，Pamela Colman Smith，
  Wikimedia Commons 公版）——辨识度即正义但全网同款；仅 78 张主牌可用，
  小牌仍需自绘补齐。
- 禁：开源项目自带的卡牌图/贴纸素材（许可几乎全部不明）；任何 AI 生图服务
  的输出入库（训练数据来源不可审计，与宪法第一条事实第一冲突）。

### B3 背景/纹理
- 不引入位图。CSS 渐变（时辰感知，US4）+ 内联 SVG 纹理（噪点/星点，
  data URI 内联，体积≈0，可被 003 判据 12 一键回滚覆盖）。

## C. 挂账闭环声明

「10 个开源项目参考未闭环」（§131/§133/§134 多轮移交）自本附录起闭环：
两轮调研合并归档于此，逐项目给了许可裁定与借鉴点，后续 US 实施时
按表对照执行。skill zip 零融入仍挂账（与本议题无关）。
