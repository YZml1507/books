# R3496 灵魂原型小测（sq）全链终扫（亲审）

范围：oracle 页 #sqPanel 8 题小测、sq=/sqb= 链、对对碰卡、委托顺序、NO_CASE 豁免、复制降级。

## 逐项结论
- 解析时捕获 PASS：_SQ_PEER_KEY/_SQ_PAIR 在 script parse 时捕获（同 __shareBy/__saPending 模式）。
- sqb 合法性 PASS：正则 [mfegw]{2} 天然过滤单键/错键/超长；ff 同款键→「同款灵魂」判词正确。
- 五行关系表 PASS：_SQ_SHWO/_SQ_KEWO/_SQ_WOKE 自包含（R3493 修过的 init 时序坑不复发）；任意 (me,peer) 组合必命中四分支之一，无 undefined。
- 委托顺序 PASS：.sq-opt 先于 .or-chip 早退（R3493 修法未被后续编辑破坏）。
- NO_CASE PASS：sqShare/sqInvite/sqAgain/sqTell/sqbCopy 豁免表理由成立（幂等复制类，无可断言 DOM 变化）。
- 复制降级 PASS：sqInvite/sqTell/sqbCopy 三处均有 clipboard→execCommand→_showTextExportModal 三级降级。
- 边界 PASS：sq+sqb 同存时 _sqPeer 取 PAIR[2]（最近测者）；出题人自点链→同款判词（可接受，链给外人用）。

## 修复
- P2 「磨刀石」措辞 → 「磨合型」（两处），对 XHS 目标用户更顺耳。
