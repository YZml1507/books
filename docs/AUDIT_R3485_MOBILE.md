# AUDIT_R3485_MOBILE — 移动端八审·深色模式专项（小惊喜族新增交互面）

- 日期：2026-10-04
- 分支：devin/1791113429-loop-r3424（审计只读，本文件为 docs/ 下唯一新增）
- 范围：web/static/app.js、styles.css、app_poster.js、app_wallpaper.js 中本季新增交互面——盘里小惊喜折叠区（saZone 五钮 + fdCard/gdCard/crCard/saCard）、色谱锁屏壁纸钮（saWap）、预告行「晒明天的穿搭」钮（dailyTomorrowShare）、sa 分享链落地承接条/toast。
- 方法：亲审静态读码 + Playwright CDP 360×740 实测（展开前后逐钮量尺寸、scrollWidth、深/浅双主题计算色、@media print 显隐）+ `?view=bazi&from=share&sa=S` 深链全链回放（落地→欢迎条承接→submit→开卡→开海报层→返回键）。

## 审点速览

| 审点 | 结论 |
|---|---|
| ①触控 ≥40/44px | 全达标（实测尺寸见下表） |
| ②深色硬编码浅色 | 干净——新增类全 token 化或已有 dark 覆写，零漏网 |
| ③360px 窄屏 | 无横向滚动（展开前后 scrollWidth=clientWidth=360）；五钮 flex-wrap 三行右排（2+2+1） |
| ④iOS 弹层键盘与安全区 | 新增弹层/承接面无输入控件，无键盘顶弹场景；海报层缺 env() 内边距 + img 未随 dvh 改造 → P2-2 |
| ⑤打印态 | 全部新钮被 `button` 通配+显式名单覆盖；`.sa-zone` 空容器留 ~6px 残渣 → P2-4 |

触控实测（360×740，CSS px）：

| 钮 | 实测 | 判定 |
|---|---|---|
| saZone 五钮（shareFortuneDir/shareGuardian/shareCrystal/shareSoulart/sharePrompt） | 各 44px 高 | ≥44 ✓ |
| fdShare | 166×46 | ✓ |
| gdShare | 194×64 | ✓ |
| crShare | 181×46 | ✓ |
| saShare | 166×46 | ✓ |
| saWap | 150×46 | ✓ |
| dailyTomorrowShare | 110×40 | ≥40 次级线 ✓ |
| posterCopyLink | 138×44 | ✓ |
| poster-modal-close | 44×44 | ✓ |
| toast-x / welcome-close（承接面） | 44×44（styles.css:3006、:2971） | ✓ |

sa 承接链路顺带终验：`?sa=` 不在剥参白名单（app.js:16463-16468）→ submitBazi 消费（:7656-7659）→ `_openSaByKey` 开卡（:17465-17480）→ `__shareSa`（:16037）供承接条点名（:16667-16675、:16763-16772）。链路通，但有下面两跳伤它。

## P0

无。

## P1

### P1-1 sa 消费时 `replaceState(null,…)` 清掉 state.view——开海报层后一次返回弹穿两层
- app.js:7659 `if (_saK) history.replaceState(null, '', '/?view=bazi')`——`?sa=` 深链消费时把当前历史项的 state 写成 **null**（本文件其余规范化全带 `{view}`：:16388、:16478）。实测落地 `history.state={"view":"bazi"}` → submit 后变 `null`。
- 后果链（已实测复现）：sa 落地 → submit → 点 saWap 开海报层，`showPosterModal` 的 pushState 读 `(history.state && history.state.view) || 'home'`（:4831-4832）→ 推入 `{view:'home',modal:'poster'}`；按一次返回键 → popstate 落回 state=null 的条目，`_sv` 解析为 `'home'`（:4014）→ 弹层关闭**且**视图被拽离结果页回首页——一次返回吃掉两层，与 R110-P2 的「返回先关弹层不翻页」契约直接冲突。聊天 chip 路径（`__saPending`）不走这段，仅 `?sa=` 深链中招——恰是承接链的主入口。
- 改法：`history.replaceState({ view: 'bazi' }, '', '/?view=bazi')`，与 :16388/:16478 同口径。

### P1-2 滚动接力竞争：深链落地停在折叠钮区，已开的卡被压出屏外
- app.js:7661-7666：`_openSaByKey(_saK)` 内部 `_fdOpen/_gdOpen/_crOpen/_saOpen` 各自 `scrollIntoView({behavior:'smooth',block:'center'})` 把刚开的卡滚中（:17126/:17212/:17298/:17395）；180ms 后 setTimeout 又 `_z4.scrollIntoView` 把**折叠钮区**滚中（:7664）。smooth 滚动后到者胜，最终视口停在钮区。
- 实测 360×740 sa=S 落地：saZone 位于屏内 449-597，已开 saCard 位于 609-941——只露顶部 ~131px（色带+一行图例），「📸 晒同款」「📱 做锁屏」两钮全在屏外。承接文案承诺「自动给你开同款」，客人落地只见一排钮、不见同款，最后一跳失约。
- 改法：去掉 :7664 的第二跳（卡内滚动已就位）；若要保「先见钮区再见卡」编排，把目标换成刚开的卡容器并推迟到滚动稳定后，别叠在 smooth 滚动中段。

## P2

### P2-1 sharePickZone 展开钮被 `id^="share"` 误染成 CTA，展开后无态可感
- styles.css:1433 区 `button.fav-btn[id^="share"], .fav-btn.share-cta` 的 id 前缀选择器把 `sharePickZone`（app.js:7007 建钮）也刷上「生成海报」同款 CTA 渐变——它是 disclosure 展开钮，却长了一张导出脸，与四枚真分享钮同排时语义混淆。
- app.js:7639-7642：`if (_z && _z.hidden)` 单向展开——展开后钮保持可点、再点静默无反应；无 `aria-expanded`/`aria-controls`，也无 disabled/dimmed 反馈。移动端无 hover 提示，客人连点两下「没反应」体感死。
- 改法：展开钮改非 `share` 前缀 id（如 `saZoneToggle`）或加白名单类排除 CTA 选择器；展开后设 `aria-expanded="true"` 并把钮置 disabled/隐藏（或干脆变成「收起」双态）。

### P2-2 海报弹层缺 iOS 安全区内边距；img 高度仍用 vh 未随 dvh 改造
- styles.css:2397 `.poster-modal-backdrop{padding:16px}`——固定 px，全仓其他贴屏件都走 `env(safe-area-inset-*)`（:982、:1018、:1036、:1130、:1313-1316、:2455），唯独它没跟上。竖屏实测弹层底边距 home 指示条只剩 ~37px（≈16px pad 吃掉后余额），横屏左右 47px 安全区无保护，刘海机圆角/手势区可贴脸。
- styles.css:2429 `.poster-modal-img{max-height:60vh}`——:2404 弹层本体已按 R2349m 修成 `90vh;90dvh` 双写法，img 漏改。iOS 动态工具栏展开态 dvh<vh：img 仍按大视口取 60%，可能超过当前可视 60%，body 区被迫内滚。
- 改法：backdrop padding 改 `calc(16px + env(safe-area-inset-*))` 四边写法（先纯 px 兜底行再覆盖，同 :980 双写法惯例）；img 补 `max-height:60vh;max-height:60dvh`。

### P2-3 `_openSaByKey` 先展折叠区后验键——非法 sa 键留下一个被点亮的钮区
- app.js:17465-17479：`_z.hidden=false`（:17469）在键校验之前，非法/空 `_saK` 走到 `else return false`（:17478）时折叠区已展开。submitBazi 侧（:7658-7659）则已把 `?sa=` 从地址栏剥掉——客人 URL 没了凭据、页面却多出一排钮。
- 改法：键校验前置（白名单 `FGCSP` 先判再 unhide）；或调用侧先 `_openSaByKey` 返 true 再剥参——当前顺序相反。

### P2-4（轻）`.sa-zone` 空容器漏打印隐藏表
- styles.css:2723-2740 @media print 名单收尽了全部新钮（`button` 通配 + `.share-cta`/`.poster-modal-actions` 显式），但容器 `.sa-zone` 不在列——展开过的 zone 打印时留下 ~6px 空盒残渣（无 border/bg，margin 4px/2px）。`.sm-card` 同样未入 `break-inside:avoid` 名单（:2734-2737），长卡可跨页切断。
- 改法：`.sa-zone` 补进打印隐藏表；`.sm-card` 并入 card 系防断行名单。

## 通过项留档（不必修）

- 深色：`.daily-tomorrow-share` 深色覆写在位（styles.css:3306-3308）；`ghost` 钮系全 token（color-mix/--primary-ink，:1399-1405）；`.poster-modal-body/head/tip`、`.poster-act`、`.toast-item`、`.welcome-bar` 深色覆写齐备（:3361-3364、:3394、:3405、:3217、:3303）。`.sa-seg` 色带与穿搭色点是行内数据色——属内容非皮肤。
- 360px：`.sa-zone` flex-wrap 右排三行（:4176-4179），无横向滚动；`.share-row` @≤520px 转静态换行（:3168-3178）。
- 打印：`daily-tomorrow-share` 属 `<button>` + 挂 `.daily-tomorrow` 域，双保险隐藏；`.sa-strip` 色带按内容打印=预期。
- iOS 键盘：海报层/承接条/折叠区均无 input/textarea，无键盘顶弹场景。
