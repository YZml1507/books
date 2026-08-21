# 006-llm-polish 实施计划

**Written**: 2026-08-21（单轨轮）
**对应 spec**: `specs/006-llm-polish/spec.md`

## 架构（已定，见 spec §2）

```
src/guji/llm_polish.py   # 已建：配置加载/polish()/facts 组装器/_sanitize/离线自测
web/services.py          # 各 service 在 warm 之后 additive 附加 "ai_polish"
web/static/app.js        # 渲染 ai_polish（独立容器 + AI 标注样式）
web/static/styles.css    # .ai-polish 样式（与引文区视觉区分）
```

## 已实测钉死的事实（写代码前先测，照 D-143a 先例）

| 事实 | 复现 |
|---|---|
| agnes API 兼容 chat/completions | `httpx.post .../chat/completions` 200 |
| **agnes-2.5-flash 是推理模型**：max_tokens=200 时 reasoning_tokens 吃光全部配额，content 为空串、finish=length；1000 才稳定出文 | usage: `{'reasoning_tokens': 200, 'text_tokens': 0}` → max_tokens=1000 后 `{'reasoning_tokens': 310, 'text_tokens': 41}` |
| 延迟波动大：1.5s–45s 不等（含偶发 Server disconnected / ReadTimeout） | 多次实测；故 timeout=30s + 静默降级是必须的 |
| 空正文/断连是**随机**的，与提示词内容无关（长短 system 都出现过空返回） | 二分实验记录 |
| venv 有 httpx 无 openai 包 | `importlib.util.find_spec` |

## 任务清单

### M1 服务端接线（本轮）
- [x] T1.1 `src/guji/llm_polish.py` 模块 + 离线自测全过
- [x] T1.2 `web/llm_config.json`（gitignored）写入真实 key；`.gitignore` 加 `web/llm_config.json`
- [ ] T1.3 `web/services.py`：bazi/taohua/hehun/qiming 四个 service 在响应 dict 上
      additive 附加 `"ai_polish"` 键（值 = polish(facts_*) 或 None）。
      **不得改动任何现有键**。LLM 调用放 try/except 全兜底。
- [ ] T1.4 `probes/probe_llm_polish.py`：offline 用例（mock 超时→None 且 warm 不变）、
      online 用例（--online 开关才跑真网络）、三库零命中检查
- [ ] T1.5 selftest 增补 ≥3 条断言（只增不减）

### M2 前端渲染（本轮）
- [ ] T2.1 `app.js`：四个结果渲染函数里，若 `j.ai_polish` 非空则追加
      「✨ AI 解读」容器（含标注「AI 生成 · 仅供娱乐 · 再点一次可能不一样」）
- [ ] T2.2 `styles.css`：`.ai-polish` 与古籍引文区视觉不可混淆（不同底色+边框+图标）
- [ ] T2.3 UI smoke 新用例行为描述登记台账（审查轨惯例：只断言行为不断言内部命名）

### M3 判据验收（spec §4 表逐条）

## 明确不做

- 不让 LLM 参与排盘/检索/引文选取
- 不做流式/多轮/记忆
- 不装 openai SDK（httpx 直连）
- 奇门遁甲新功能（lunar_python 新依赖，红线第 3 项 REJECTED）
