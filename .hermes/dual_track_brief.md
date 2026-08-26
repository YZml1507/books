# 双轨循环工作流 — R218a kickoff（2026-08-26）

## 用户原话
> "项目问题还很大，需要很多优化。新开两个窗口：审查轨负责模拟人去点击浏览器，指出不足，同时审查优化轨的修复；优化轨负责根据审查轨指出的问题去修复。两个窗口循环进行，直至明确中止。图片界面优化要考虑进去，图片由 M3 + agnes-image/Pollinations 生图。"

## 决策
- **范围**：全站 10+ 页（首页/八字/起名/桃花/合婚/六爻/塔罗/黄历/聊天/海报/分享图）
- **轮次**：无上限，用户发"中止"才停
- **隔离**：审查轨 strict_readonly（绝不跑 git checkout/restore/clean/stash/reset、rm、write_file/patch 到 src/、只能改 docs/UX_REVIEW_QUEUE.md）
- **生图路线**：M3 写 prompt + 双后端并行（agnes-image-2.1-flash 关键图 + Pollinations.ai 占位/批量）
- **闸门**：full_gate = selftest163 + probe_ui_smoke + baseline_voice + warm_voice + plain_first + check_poster + vision_analyze 复评

## 共享资源

### 路径
- 工作区根：`C:\Users\Lenovo\Desktop\projects\books`
- 审查轨产物：`docs/UX_REVIEW_QUEUE.md`（追加 `## R218a-巡<n>` 段，**这是审查轨唯一允许写的文件**）
- 优化轨产物：`docs/TASK_LEDGER.md`（追加段）+ git commit/push
- 巡检截图目录：`$LOCALAPPDATA\Temp\tour\R218a\`（01_home / form_* / result_* / 02b_chat / 02c_share）
- 闸门日志：`$LOCALAPPDATA\Temp\gates_r218a<n>.log`
- 生图脚本：`scripts/image_gen.py`（双后端，--backend agnes|pollinations|auto）

### 后台服务（已起）
- uvicorn `:8183`，`BOOKS_LLM_DISABLE=1`（降级路径，也是被审对象）

### 启动命令
```bash
cd "C:/Users/Lenovo/Desktop/projects/books"
BOOKS_LLM_DISABLE=1 ./.venv/Scripts/python.exe -m uvicorn web.app:app --port 8183 --host 127.0.0.1
```

### 闸门脚本（按顺序跑，~3min/轮）
```bash
./.venv/Scripts/python.exe scripts/selftest_163.py             # 163 断言
./.venv/Scripts/python.exe scripts/probe_ui_smoke.py            # 41 UI 用例
./.venv/Scripts/python.exe scripts/baseline_voice.py           # sha256 稳定
./.venv/Scripts/python.exe scripts/check_warm_voice.py         # 判据 1-8
./.venv/Scripts/python.exe scripts/check_plain_first.py        # 5x8
./.venv/Scripts/python.exe scripts/check_poster.py             # 海报
# 视觉复评：Playwright 截图 + vision_analyze
```

## 事故教训（review track 必读）
- 2026-08-24 R216b：审查轨误跑 `git checkout -- web/static/app.js`，丢 118 行未 commit 修复，全量重做
- 铁律：审查轨**绝不运行任何会改工作区的 git 命令**（checkout/restore/clean/stash/reset）
- 铁律：审查轨**绝不写代码**（write_file/patch 到 web/、scripts/、data/）
- 铁律：审查轨**只写** docs/UX_REVIEW_QUEUE.md
- 铁律：审查轨只用 read_file/search_files/terminal 只读命令 + vision_analyze + Playwright + image_generate（生图用于产出视觉建议）

## 一轮循环的契约
1. 审查轨跑 Playwright 全站巡检 → 写 UX_QUEUE.md（每页 1+ 条问题，标 MAJOR/HIGH/MED/LOW）
2. 优化轨读 UX_QUEUE.md → 修问题（aditive，API 契约与 pro 分支零改动）→ 跑 full_gate → commit/push → 写台账段
3. 审查轨再巡验证（同样入口同样问题点）→ 标 ✅ [已验证] 或 ❌ [未解决]
4. 收敛判断：3 轮无新增 MAJOR → 进入下一波次（不同区域/不同维度）

## 生图集成要求
- 每个结果页（八字/起名/桃花/合婚）**至少 1 张装饰图**（背景或小插画）
- 海报必须用 agnes-image（高质量）
- 占位/草图用 Pollinations（快）
- 审查轨**必须截图视觉一致性**（色调/构图/可读性/有无人设感）
