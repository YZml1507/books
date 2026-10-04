# R3495 「盘里小惊喜」八件域全链终扫（亲审）

范围：saZone 折叠区 8 件（方位/图腾/水晶/色谱/prompt/角色/纹样/名片）+ sa 锚族 EFGCPSRN + 海报管线 + 排队链。

## 逐项结论
- 初始化顺序 PASS：全部依赖表（_FD_DIR@17488/_WX_*@17515/_GD_BEAST@17646/_CR_GEM@17743/_IC_FIGURE@17990/_EMB@18055）先于各自 pick 函数；_ncCard@18271 居尾；open 函数均为 function 声明提升安全。
- 同源口径 PASS：名片行与单件卡同一 _pick 输出（_fdPick 与 _fdPickTopic('all') 同结果）。
- 锚族 PASS：services.py 8 anchor（saF/G/C/S/R/E/N/P）↔ 正则 /^sa[EFGCPSRN]$/ ↔ _openSaByKey 8 键分发，零死键。
- 排队链 PASS：saPending 单槽「最后者胜」（语义合理）；无盘时 _openSaByKey→false→排队；?sa= 深链渲染时消费。
- 海报六件套 PASS：8 件 titles/bg/alias/shareText/lineCap 全齐，bg 全在有效集；soulquiz→oracle、namecard→bazi 别名正确。
- 健壮性 PASS：counts 全零→日主兜底；bands 空→「五行空白」；_saPctList 均分/单元素/空全过。

## 修复
1. **P1 _SA_SHARE_KEY 漏 namecard**：名片海报分享链不带 sa=N 锚，受邀者落 bazi 表单不自动开同款，钩主件沉底。已补 `namecard:'N'`。
2. （交叠 R3494a）sq 海报「合拍」行整条判词超 20 字行帽被截剩名字串——海报行只带判词本体。
3. P2 「磨刀石」对目标用户偏糙 → 改「磨合型」（_sqRelTxt/_sqPairTxt 两处）。
