# 文档漂移审查清单 —— YZml1507/books @ devin/1789836976-opt-loop-r1 (HEAD 0d8f9e9)

审查方式：只读。全部数字由本分支实跑得出（`BOOKS_LLM_DISABLE=1`）：selftest **176 checks PASS**、probe_ui_smoke **43/43 PASS**、probe_dollar_misuse **PASS(154 函数 0 命中)**、probe_selftest_regress **PASS(基线 178→176，已审核改名 2)**、probe_contract **FAIL(HARD=12, exit 1)**、count_open_findings **0 OPEN exit 0**、13 道语料闸门除 assess_goals 外全 exit 0、assess_goals **exit 1（G9 FAIL）**。

按严重度排序：命令失效 > 行为漂移 > 数字过期。

---

## docs/TASK_LEDGER.md

1. **[末段 R228o/R228p 判据行] 声称「contract PASS 381 读点」「全绿」，实测 `probes/probe_contract.py` exit 1、HARD=12。**
   证据：实跑输出 `probe_contract: 29 个 handler 块，381 个字段读取点 → FAIL: HARD=12`；归因：读点 url 为方法分键形式 `"POST /api/chat"`，而 `CONDITIONAL_FIELDS`（probe_contract.py:196-219）键是不带方法前缀的路径，`CONDITIONAL_FIELDS.get("POST /api/chat")` 查空 → R228g/R191b 登记的豁免失效（R228o 方法分键重构引入的回归）。
   建议改法：台账补记本轮 contract FAIL 实况，探针里 CONDITIONAL_FIELDS 匹配前剥掉 `POST ` 前缀。

2. **[头部闸门清单，~line 27] 声称 `check_provenance`「须 0/28 缺失」，实测 47 部（输出 `index works: 47`）。**
   建议：改「0/47」或直接写「末行 verdict=0」不带分母。

3. **[头部闸门清单，~line 26] 声称 `verify_index`「现为 20 项」；[§5, ~line 186] 声称「12 项断言」——两处互相矛盾且都过期，实测 `check(` 调用 23 处（T1–T11）。**
   建议：统一改 23，或照 L-23 改成「以 verify_index 输出为准」。

4. **[头部闸门清单] 声称 `eval_g1`「G1 评测集 193 题」，实测 `data/catalog/eval_g1.json` questions=248（eval_g1 PASS）。**
   建议：改为 248 或去硬编码。

5. **[头部闸门清单] 声称 `build_index`「重建（约 5 秒）」；本仓自己后来测的是 62,109 单元 14.5s（PHASE.md R118a 登记行），随语料还会涨。**
   建议：改「约 15 秒（47 部全量）」或写「秒级~十几秒」。

6. **[使用约定 ~line 16] 声称「已有 4 条 REJECTED」——§4 表确为 R-01..R-04，但全文 REJECTED 已散到十余条（MBTI/html2canvas/T5 N1-N3/方案C/P-11 等），GOAL_NEXT_SESSION §3 就列了 11 行。**
   建议：把后来各条 REJECTED 归并进 §4 表，或改写成「§4 为首批，后续见各轮 §」。

7. **[R228o 收口/R228p 判据行] 声称 regress「174→176」「177→176」，实测基线 `probes/selftest_baseline.json` checks=178 → 当前 176、renames=2。**
   建议：两行基线数字都改成 178→176。

8. **[头部「全部复验」清单（~line 22-39）] 只列 13 道语料闸门——当前标准闸门集合另有 web 侧 selftest/ui_smoke/contract/dollar/regress/no_generated/scripts_importable/first_screen 等（本文件 R228o 段自己就在用）。**
   建议：清单补 web 层闸门段，或注明「语料闸门」+ 指向 PHASE.md。

9. **[结构] 使用约定与 §4/§5 在 ~line 8045/8201 各有一份重复拷贝（merge 残留），且 §1-§24 的旧快照数字（37 部 51,000 单元等）与新轮次并存——头部旧快照未标注存档。**
   建议：去重 + 给旧快照块加「历史存档」标头（GOAL.md §7 已有此先例可照抄）。

## docs/HANDOFF.md

10. **[全文] 工作流说明停留在 REPAIR 前时代：让新窗口读 GOAL.md §4 按 T1-T7 执行——§4 任务已全部 DONE（GOAL.md 自带 R101b-R109b 标注）；对 `docs/PHASE.md`（CURRENT_PHASE: OPTIMIZE）、双轨制、`specs/`、`AUDIT_FINDINGS.md`、`OPTIMIZE_BACKLOG.md`、web 闸门套件 **零提及**（全文 grep 无 PHASE/specs/selftest/probe 命中）。**
    建议：开头加「先读 PHASE.md 的 CURRENT_PHASE 决定轨道」并把闸门集合指向 PHASE.md 闸门表。

11. **[~line 50-53 已知待办] 列 P-05（易林未入 G1 题库）、P-06（tier2/3 五书未动）为「未验证」待办——台账 §8818/8819 实测均 DONE（eval_g1 已含 32 道易林题，现 248 题；五书全入索引）。W-04「59/62 PART」仍属实。**
    建议：删 P-05/P-06 或标 DONE；W-04 保留。

12. **[~line 82/90] 「当前闸门状态」只点名 `scripts/assess_goals.py`——实测该脚本现在 exit 1（G9 FAIL，见下）；且 web 闸门一套完全没提。**
    建议：闸门状态命令补 `web/selftest.py` 与 probes 三件套。

## docs/PHASE.md

13. **[闸门表 ~line 40-46 + 附加闸门表 ~line 73-77] 命令本身全部成立（逐一实跑：count_open_findings exit 0=0 OPEN、selftest 176 PASS、ui_smoke 43 PASS、contract/dollar 见条目 1）；但「附加闸门」枚举停在 #5/#6——R120a 登记段已用到 #7-#9（selftest_regress/no_generated/scripts_importable），后续还新增 probe_first_screen、baseline_voice、check_poster、check_async_ai、check_warm_voice、check_xingzuo、check_plain_first（均在仓库可跑）。**
    建议：附加闸门表补齐 #7-#9 及后建检查脚本，或改写法为「附加闸门以台账最近一轮判据行为准」。

14. **[~line 43] 闸门 4 指向「`constitution.md` §IV」——仓库根部无此文件，实际在 `.specify/memory/constitution.md`。**
    建议：补全路径。

15. **（自证正确项）** ~line 58-64 R190b 订正「web/app.py --selftest 会起服务挂住、真入口是 web/selftest.py」与现状一致（app.py:98 `uvicorn.run`）；本条非漂移。

## docs/DECISIONS.md（抽查）

16. **[D-260b ~line 5802] 裁决「删历史 UI 留后端：/api/history* 后端、selftest history 用例、probe 清理判据全保留（零删除原则）」——已被 R219b 实质推翻：`/api/history*` 端点整批删除（app.js:4349 注释、probe_contract.py:584 行为断言、selftest_baseline.json removed 区块），且 DECISIONS 无后续订正条目。**
    建议：按 D-008 先例在 D-260b 加订正行「/api/history 后端已于 R219b 实际删除，台账 §172」。

17. **抽查一致项（非漂移）**：D-251b 异步轮询管道与现状一致（spawn + `GET /api/ai/{tid}` 在位）；D-258b/D-259b AI 陪伴层复用异步管道、对话不写库，与 bazi.py:62-80 `/api/chat` 实现一致；D-261b 快乐体接线已落实（ui.font.zcool_applied PASS）。

## docs/GOAL.md

18. **[§8 文档职责表 ~line 368-369] 「DECISIONS.md（D-001…D-018）」「LESSONS.md（L-01…L-16）」编号范围过期——实测 DECISIONS 已到 D-261b，LESSONS 到 L-26。**
    建议：范围改「见文件末条」或不写编号区间。

19. **[§1 ~line 39]「重建 corpus.db 不属于破坏性操作，它 5 秒可重建」——47 部 62,109 单元实测 ~14.5s（PHASE.md R118a 行）；数量级结论仍成立，数字过期。GOAL_NEXT_SESSION §4 同句同问题。**
    建议：改「十几秒可重建」。

20. **（自证正确项）**：§3 闸门 13 个脚本全部存在且本机复跑通过（除 assess_goals 的 G9，见条目 22）；「verify_index T1–T11 共 23 断言」属实；「check_provenance 0/47」与 verdict 一致；§2 推翻表 8 行与 HANDOFF 引用一致；§7 已自标历史存档。

## docs/GOAL_NEXT_SESSION.md / docs/GOAL_NEW_SESSION.md / docs/PROJECT_STATUS.md

21. **[GOAL_NEXT_SESSION §1 命令块 ~line 95] `cd web; PYTHONPATH=src:. python -m app --selftest` 是死命令——`web/app.py` __main__ 现在直接 `uvicorn.run`（起 8123 服务挂住），真自测是 `web/selftest.py`。PHASE.md 已订正过此事但本文没跟上。**
    建议：命令改为 `web/selftest.py`。

22. **[PROJECT_STATUS.md 头部] 文档职责是「当轮实测快照」（GOAL.md §8），但停在 2026-08-17/R175b 时代（「web 自测 123 checks」、`python -m app --selftest` 命令、9 tab 发布面）；当前 R228p/176 checks。**
    建议：要么按职责刷新快照，要么文首标「最后刷新 R175b，当前快照见台账末条」。

23. **[GOAL_NEXT_SESSION §1 ~line 94] `python -m guji.mcp_server --selftest` 在本环境 exit 1（`ModuleNotFoundError: No module named 'mcp'`——.venv 未装 mcp）；同机 `python -m guji.sources --selftest` PASS。**
    建议：注明 mcp 层自测需要额外依赖，或在 initialize/文档补装包步骤。

24. **[GOAL_NEW_SESSION ~line 42 红线第 2 条] 写「GOAL.md §3 八条复验命令」——GOAL.md §3 现为 14 行/13+ 闸门，「八条」是更老版本数。**
    建议：改成「GOAL.md §3 全部闸门」。

## docs/OPTIMIZE_BACKLOG.md（开放条目前提已消失/已实现，未标注）

25. **B-003/B-017**（~line 88、347）声称 `api_daily` 用 `_chinese_zodiac(d.year)` 取当年生肖——`_chinese_zodiac` 已删，`noble` 现按当日日干天乙贵人（services.py:1034-1044，注释自引「B-017 R195b 清偿」）。→ 标已修。
26. **B-004**（~line 104）声称宜/忌数组「渲染为逗号拼接」——现为双色大卡+逐条 chip（app.js:4150+，ui_smoke 可见逐项）。→ 标已修。
27. **B-005**（~line 116）声称建线程「只回一行 id」——现在创建后即刷列表渲染 claim+证据数（app.js:2660+，ui_smoke btn:threads 输出可见「开题：…证据 0 条」）。→ 标已修。
28. **B-006**（~line 126）声称 findings 渲染空串——现在读 `f.line`（app.js:2502/2567）。→ 标已修。
29. **B-007**（~line 140）声称 research steps「前端完全没展示」——app.js:2487 已渲染步骤链（ui_smoke btn:research 输出含「检索链路 search…→found 12/kept 12」）。→ 标已修。
30. **B-008**（~line 150）声称 works 卡只靠 `||w.id` 兜底且不展示编址率——app.js:2591-2607 已展示 genre+编址率+锚定率（注释自引 B-008 R201b）。→ 标已修。
31. **B-009**（~line 161）前提「首屏打三次 /api/history」——端点 R219b 已整批删除，loadHistory/loadRecent 不存在。→ 条目关闭（被删除而非修复）。
32. **B-010**（~line 170）声称 animotion 287KB「零接线」——styles.css:17 `@import "./animotion/web-lite.css"` + :115 R201b 接线注释；且 R228k 发现原 @import 位置错误从未生效、置顶后才真加载。→ 标已修（可附 web-lite 子集事实）。
33. **（自证正确项）** B-011 仍属实：probe_disclosure.py 今跑仍崩 `:132 ValueError`；B-012~B-020 均带处置标注，与代码状态一致。

## .agents/skills/testing-xiaoman-e2e/SKILL.md

34. **[Known baselines ~line 39] 声称「`btn:huangli` perpetually unstable（font rendering）」——R228k 修复 @import 顺序后该用例转 PASS，本机实测 ui_smoke 43/43 全绿含 btn:huangli。**
    建议：删该基线行，或改为「曾基线抖动，R228k 后应 PASS；若再挂是真回归」。

35. **[同段] 声称「probe_contract/probe_dollar_misuse have existing FAILs」——dollar_misuse 实测 exit 0（154 函数 0 命中）；contract 确实 FAIL 但机制已是方法分键豁免失效（条目 1），不是写该句时的旧因。**
    建议：dollar_misuse 从基线删；contract 补注当前 FAIL 形态。

36. **[~line 40] 声称「冲煞：[object Object] 是 pre-existing bug，与 base commit 一致」——R228a 已修（app.js:4195-4203 处理 {chong,chong_animal,sha_fang} dict）。**
    建议：删除此已知 bug 行——再看到 [object Object] 应直接报回归。

37. **[~line 13/20] 引用 `/tmp/mock_llm.py`、`/tmp/type_cjk.sh`「if still present」——/tmp 已清空，新环境均无此二文件（句子有 hedge，但等于每个新会话都要重写 mock）。**
    建议：把两个脚本落进仓库（如 scripts/ 或 skill 目录）消除对 /tmp 的依赖。

38. **（自证正确项）**：DISABLE=1 降级语义、`/api/chat` 返回 {}、mock 端口/环境变量启动命令、CJK keysym 输入法、browser_console 单表达式限制、选择器清单（recentToggle/chatInput/hlChips data-hloffset 0/1/2/-1/hlAskInput/hlVerdict/nameReviewBtn/chatEntry）、_hlDayOffset 054f7e0 行为、1600×1200 真实分辨率——全部属实。

## web/static/_candidates/README.md

39. **零漂移。** 4 张已接线资产逐一在 index.html:53/app.js:655/3453-3454 命中；7 张未接线备选全部在盘；smiley-sans 段（源档案 1.15MB + subset 2.1KB 接线 .daily-level）与 styles.css:181-182、fonts/ 目录实测完全一致；chat 头像确为 cream/avatar-xiaoman-cream.jpg。

## 其余抽查

40. **[.specify/memory/constitution.md ~line 211+ 可复验命令清单] 仍写 `web/app.py --selftest`——死命令（会同条目 21 起服务挂住）。PHASE.md 的订正没同步到宪法本体。**
    建议：改 `web/selftest.py`。

41. **[docs/handover.md]** 结构/启动/排查声明基本属实（web_launcher.py、start_web.bat、cream/ink/ 资产、selftest.py 均在）；`web/llm_config.json` 本机不存在属 gitignore 正常。非漂移。

42. **[docs/PROJECT_ROADMAP.md/WEB_PLAN*.md]** 内部引用 `llm_reader`（已删）、`history.db` 写路径（已退役）——均为带日期的计划文档，属历史记录；未加过期标头，可酌情补一行「成文于 R1xx 时代」。

---

## 红线上报（超出文档漂移，但审计中抓到）

- **`scripts/assess_goals.py` 当前 exit 1：G9 FAIL**（PASS 8 · FAIL 1）。原因：`data/index/knowledge.db` 有 1 thread/1 derived/1 evidence 但 `derived.thread_id IS NOT NULL` = 0——本机库的 derived 行未绑线程。knowledge.db 是本地库不入 git，故在干净环境首跑 G9 恒 FAIL：闸门依赖了未入库的数据状态。多份文档声称「G1–G9 全 PASS」（PROJECT_STATUS/GOAL §1b 标注/PHASE 登记行）在本 checkout 复现不出。
- **`probes/probe_contract.py` 当前 exit 1**（见条目 1，疑似 R228o 引入的探针回归，非文档问题但使「contract 全绿」声明失真）。

## 附：仓库外同名漂移（环境 blueprint knowledge，非 docs/ 文件）

- 环境知识条写「主闸门（162 项）：`BOOKS_LLM_DISABLE=1 .venv/bin/python web/selftest.py`」——实测 176 checks；同条写「probe_ui_smoke 的 btn:huangli 为基线同挂」——该用例 R228k 起已转 PASS。建议 blueprint knowledge 同步刷新。

## 未发现漂移清单

- 闸门命令存在性：GOAL.md §3 的 13 脚本 + PHASE.md 闸门 1/2/3/5/6 + probe_selftest_regress/no_generated/scripts_importable/first_screen + web/check_* 六件 + baseline_voice——全部在库。除上列两条外逐一实跑 exit 0（selftest 176、ui_smoke 43、dollar、regress、count_open_findings、check_quality、validate_alignment、probe_conservation、check_provenance verdict 0、probe_bcv、eval_g1 248 题、summarise_diff、eval_g7、probe_g8_isolation、eval_g4、probe_booksec、verify_index ALL PASS）。
- 端点/文件存废：`/api/history*` 已删 ✓（ledger R219b 准确）；`_chinese_zodiac` 已删 ✓；smiley-sans 子集接线 ✓；5 个「僵尸端点」ask/stats/widget/share/external-fortune 全部仍在注册且 UNPINNED_ROUTES/注释口径=「有意保留」一致 ✓。
- 行为声明：「小满无 LLM 不可用/降级」（/api/chat DISABLE 下返回 {} 无 chat_task_id）✓；「AI 润色异步」（ai_task_id + GET /api/ai/{tid} 轮询）✓；「对话不写库」✓。
- MCP_CLIENT_CONFIG.md「当前 12 个工具」与 mcp_server.py @mcp.tool 计数一致 ✓。
- TASK_LEDGER 末段（R228j 起）的 selftest 173→176、contract 255→381、ui_smoke 41→43 演进与实测一致 ✓（仅 regress 基线数字错）。
- LESSONS.md 教训条目本身无对现状的虚假断言；GOAL.md §2 推翻档案与 PHASE.md 翻阶段登记为 append-only 历史，内容一致。
- data/external、data/raw_ext、*-full.png、cream/、ink/ 目录按任务说明属有意存档，未计入漂移。
