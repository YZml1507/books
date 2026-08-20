# 任务清单：004-warm-voice（优化轨执行文档）

状态列：`TODO` / `DOING` / `DONE(命令)` / `BLOCKED(原因)`。
每任务完成即改状态并附实测命令输出摘要；宪法第一条：没有命令的 DONE 等于没做。
里程碑收尾义务：判据 15–19 全绿（plan.md §2 表尾四行）。

**领土更正（R182b，D-236b）**：初版把验证脚本写在 `probes/` 下，违反宪法第五条
（`probes/` 审查轨独占写、优化轨禁改，constitution.md:164）。已按宪法 Governance
「改 tasks 而非稀释原则」全部迁到 `web/` 下，并把三项探针扩展改为**移交审查轨**。
对照表见 `plan.md` §0.1。`<py>` = `.venv\Scripts\python.exe`。

---

## M0 基线冻结（判据 9 的前提，未完成不得动 src/web 产品代码）

- [x] T0.1 固定输入集：八字 day/life/range（含提问/不含提问）、六爻（含提问）、
  塔罗 3 张、research 四类，输出落 `web/baselines/voice_baseline.json`
  （text + sections + citations 全量快照）
  状态：DONE(`<py> web\baseline_voice.py --freeze` → 14 cases, sha256 written)
- [x] T0.2 `web/baseline_voice.py`：重跑同输入，逐字节比对 fixture；
  阳性对照（篡改一字 → 退出码 1）；实测两次运行退出码 0
  状态：DONE(`<py> web\baseline_voice.py` → 退出码 0；`--self-check` 阳性对照 → 捕获)
- [x] T0.3 前端专业分支渲染现状快照 `web/baselines/pro_render_baseline.json`
  （DOM 结构+文本指纹，供判据 9 的「渲染层未变」辅证）
  状态：DONE(`<py> web\baseline_voice.py --freeze-dom` → 3 视图快照)

## M1 US1+US2+US3：voice 层 + 双模式（P1）

- [ ] T1.1 `src/guji/voice.py` 骨架：纯函数、自测入口、
  `python -m guji.voice` 先行（模板表空跑通）　状态：TODO
- [ ] T1.2 warm 四层结构实现（L0/L1/reply/details/badge）；
  L0 ≤20 字、模板注明来源字段　状态：TODO
- [ ] T1.3 幸运项规则表（河图数/五色/时辰）+ 锚点 fixture 初版
  （锚点可用台账 §115 命令复现；M2 再钉死十二宫部分）　状态：TODO
- [ ] T1.4 六爻/八字 reply 模板（64 卦白话表 + 6 爻位白话表 +
  提问关键词映射重写）；禁用词表落 `web/check_warm_voice.py`
  （含阳性对照：注入「你会脱单」→ 退出码 1）　状态：TODO
- [ ] T1.5 路由附加 `"warm"` 键（additive）；前端 warm 读取点登记进台账
  供审查轨 `probe_contract.py` 同步　状态：TODO
- [ ] T1.6 前端：renderInterpretation warm 分支、模式切换控件
  （localStorage `voiceMode`）、`<details>` 折叠依据、badge 不压轴　状态：TODO
- [ ] T1.7 `web/check_warm_voice.py` 全量：判据 1/2/3/4/5/6/7/8
  （术语表与禁用词表写死脚本内）　状态：TODO
- [ ] T1.8 `web/selftest.py` 新增 ≥8 断言（warm 存在/确定性/内容）；
  新断言名单写进台账供审查轨同步 `probe_selftest_regress` baseline　状态：TODO
- [ ] T1.9 里程碑回归：13 闸门 + 附加 5–9 + `web\baseline_voice.py` +
  `probes\probe_ui_smoke.py` 只增不减　状态：TODO

## M2 US4：幸运项 + 十二宫 + 今日运势聚合（P3 前半）

- [ ] T2.1 `src/guji/xingzuo.py`：今名↔古籍名映射、日干支×宫规则、
  12 宫文案块；`python -m guji.xingzuo` 自测　状态：TODO
- [ ] T2.2 引文锚点钉死：12 宫分野句 + 河图 + 五色 + 时辰五行，
  逐条断言在 corpus 逐字命中，落 `web/baselines/xingzuo_fixture.json`　状态：TODO
- [ ] T2.3 `GET /api/xingzuo`；`web/check_xingzuo.py`：
  判据 10（100% 可追溯）/ 11（12×同日逐字节复现）　状态：TODO
- [ ] T2.4 首页「今日运势」聚合入口卡（黄历口吻版 + 日运 L0/L1 +
  十二宫入口）；新增 UI 用例的**行为描述**写进台账，移交审查轨扩展
  `probe_ui_smoke`（按 D-145a 只断言行为不钉内部命名）　状态：TODO
- [ ] T2.5 voice/xingzuo 文案表路径写进台账，移交审查轨扩展
  `probe_no_generated_in_corpus`（判据 14）；本轨自测先行断言不入库　状态：TODO
- [ ] T2.6 里程碑回归（同 T1.9 清单）　状态：TODO

## M3 US5：分享海报（P3 后半）

- [ ] T3.1 `drawPoster()` 原生 Canvas 1080×1440：L0+能量卡+幸运项+
  日期+站名+「仅供娱乐」水印；`toBlob` 下载　状态：TODO
- [ ] T3.2 `web/check_poster.py`：判据 12（toDataURL 长度阈值）/
  13（静态扫描零外链，含阳性对照）　状态：TODO
- [ ] T3.3 reduced-motion 下出图无动画；低端降级 750×1000（长任务 >50ms 时）
  　状态：TODO
- [ ] T3.4 里程碑回归（同 T1.9 清单）　状态：TODO

## M4 收尾

- [ ] T4.1 全量回归：判据 1–19 逐条实测，输出摘要登记台账　状态：TODO
- [ ] T4.2 003 协调复测：`probes\probe_ui_baseline.py` 重跑（只读调用），
  plan §4 五项逐条比对（判据 19）　状态：TODO
- [ ] T4.3 `docs/DECISIONS.md` 落 D-234b（零依赖海报）、D-235b
  （文案方向候选与否决）、D-236b（领土更正）；台账登记　状态：TODO
- [ ] T4.4 移交审查轨：本文件状态列全 DONE(命令) + 移交清单
  （三项探针扩展 + 新断言名单 + UI 用例行为描述；按 D-145a 教训：
  断言对方行为而非内部命名）　状态：TODO

---

## 明确不做（spec Out of Scope 对齐）

- MBTI（D-147a REJECTED）；BYOK（D-146a 边界已存，用户未拍板）；
- html2canvas（除非用户明确授权，届时仅替换 drawPoster 内部实现）；
- 新语料入库；改计算层语义；小程序/App。
- **不写 `probes/` 与 `scripts/`**（宪法第五条；需对方配合的写进台账移交）。
