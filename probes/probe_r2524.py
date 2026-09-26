#!/usr/bin/env python3
"""R2524 — llm_polish 深审钉扎（agent cde6e16a 报告的亲验落地）。

- P1-1：出侧禁语/内部串/外露闸改扫 _scan_form 归一形态——markdown
  还原前先剥记号/零宽/空白+繁折简，「注**定**」「注\u200b定」
  「你 应 该」「註定」式绕闸全拦；显示文本同步剥 _OUT_ZW。
- P1-2：危机/敏感短路走罐头任务行（_CANNED_TASK_IDS 覆盖写），
  未限流短路不再每请求造行 → 匿名洪泛灌满 _tasks 的 DoS 面关闭。
- P2-1：_PROMPT_LEAK_PAT 接入 _sanitize（此前定义后从未调用=死闸）。
- P2-2：_held_session_lock——拿锁后回表核对官方位，GC 逐出缝隙
  的双锁并行失效。
- P2-3：keep_citations 引文豁免补 _BANNED_QUOTE_PAT 窄表 + 候选名
  过滤补恐吓词族（「林注定」不再喂模型）。
- P2-4：两处 resp.json() 前 2MB 字节帽。
- P2-5：load_dots_config 补 load_config 同款 coercion（字符串
  enabled/坏类型 timeout/base_url/api_key 全收口），主配置补 <=0。
- P2-6：_CHAT_CTX 换 monotonic + 读即刷新 + pop-重插真 LRU——
  锚寿命对齐会话寿命，闲聊续聊不再丢场景锚。
- P3：polish 重试提示改 user 角色；fresh 采样挪到 GC 之后；
  _is_crisis/_is_sensitive 内部剥零宽。
"""
import re
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "src")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


from guji import llm_polish as lp

_lp = open("src/guji/llm_polish.py", encoding="utf-8").read()
_svc = open("web/services.py", encoding="utf-8").read()

# ── P1-1：归一形态扫描 ────────────────────────────────────────────
ck("p1.scan_form_def", "def _scan_form(s: str)" in _lp)
ck("p1.out_zw_def", "_OUT_ZW = re.compile(" in _lp)
ck("p1.sanitize_scans_sf",
   "_sf = _scan_form(text)" in _lp and
   "_BANNED_OUT_PAT.search(_sf)" in _lp and
   "_INTERNAL_OUT_PAT.search(_sf)" in _lp and
   "_PROMPT_LEAK_PAT.search(_sf)" in _lp)
ck("p1.zw_stripped_display", "text = _OUT_ZW.sub(\"\", text)" in _lp)
# 闸在 markdown 还原之后（顺序钉扎：strip 在前，_sf 在后）
_i_strip = _lp.find('text = re.sub(r"\\*{1,2}([^*\\n]+)\\*{1,2}"')
_i_sf = _lp.find("_sf = _scan_form(text)")
ck("p1.normalize_before_scan", 0 < _i_strip < _i_sf)

# 行为级：六种绕闸形态全拦，合法文本原样
for label, s, expect_none in [
    ("star_split", "注**定**孤独", True),
    ("zwsp", "注\u200b定", True),
    ("space_split", "你 应 该 分手", True),
    ("traditional", "註定", True),
    ("prompt_leak", "根据给定事实你的盘", True),
    ("internal", "SELECT * FROM users", True),
    ("legit", "今天适合主动一点，把人约出来", False),
]:
    ck(f"p1.evasion.{label}",
       (lp._sanitize(s) is None) == expect_none)

# keep_citations：引号内恐吓词拦、真引文放行
ck("p2.quote_banned_blocked",
   lp._sanitize("这名字出自《注定》", keep_citations=True) is None)
ck("p2.quote_classical_ok",
   lp._sanitize("出自《诗经·关雎》，寓意和睦", keep_citations=True)
   is not None)
ck("p2.quote_guci_ok",
   lp._sanitize("古书说「相克」之理在此", keep_citations=True) is not None)

# ── P1-2：罐头任务行 ─────────────────────────────────────────────
ck("p1.canned_ids", "_CANNED_TASK_IDS" in _lp and
   "__canned_crisis__" in _lp and "__canned_sensitive__" in _lp)
lp._tasks.clear()
for _ in range(300):
    lp.spawn_chat_task("probe-flood", "我想死", config=None)
for _ in range(300):
    lp.spawn_chat_task("probe-flood", "得了绝症怎么办", config=None)
ck("p1.flood_no_growth", len(lp._tasks) <= 2,
   f"rows={len(lp._tasks)}")
_row = lp._tasks.get("__canned_crisis__")
ck("p1.canned_row_done",
   _row is not None and _row["status"] == "done" and
   "12356" in (_row["text"] or ""))
lp._tasks.clear()

# ── P2-2：官方锁核对 ─────────────────────────────────────────────
ck("p2.held_lock_ctx", "_held_session_lock" in _lp and
   "with _held_session_lock(session_id):" in _lp)
ck("p2.held_lock_verifies",
   "_chat_call_locks.get(session_id) is lk" in _lp)

# ── P2-4：响应字节帽 ×2 ──────────────────────────────────────────
ck("p2.resp_size_caps",
   _lp.count("len(resp.content) > 2_000_000") == 2)

# ── P2-5：dots coercion + 主配置下界 ─────────────────────────────
ck("p2.dots_enabled_str",
   'if _en_l in ("0", "false", "off", "no"):' in _lp)
ck("p2.dots_int_coerce",
   'd[_k] = int(d[_k])' in _lp and 'd[_k] <= 0' in _lp)
ck("p2.cfg_lower_bound",
   'if cfg[_k] <= 0:' in _lp)

# ── P2-6：_CHAT_CTX LRU + monotonic ──────────────────────────────
_ctx_seg = _svc[_svc.find("def _chat_ctx_get"):_svc.find("def chat_huangli_facts")]
ck("p2.ctx_monotonic",
   "time.monotonic()" in _ctx_seg and "time.time()" not in _ctx_seg)
ck("p2.ctx_refresh_on_read",
   "_CHAT_CTX[sid] = _CHAT_CTX.pop(sid)" in _ctx_seg)
ck("p2.ctx_true_lru_put",
   "_CHAT_CTX.pop(sid, None)" in _ctx_seg)

# ── P3：retry user 角色 / crisis zw / fresh 采样序 ───────────────
ck("p3.retry_user_role",
   '"role": "user",\n            "content": "（系统提醒：上一次回复' in _lp)
_ck_seg = _lp[_lp.find("def _is_crisis"):_lp.find("def _is_sensitive")]
ck("p3.crisis_zw_strip", "_OUT_ZW.sub(\"\", msg" in _ck_seg)
_i_gc = _lp.find("_gc_chat_sessions()")
_i_mark = _lp.find("if _task_started is not None:")
ck("p3.fresh_after_gc", 0 < _i_gc < _i_mark)

# ── 回归不破：原有闸还在 ─────────────────────────────────────────
ck("reg.leak_pat_exists", "_PROMPT_LEAK_PAT = re.compile(" in _lp)
ck("reg.banned_quote_subset",
   "_BANNED_QUOTE_PAT = re.compile(" in _lp)
ck("reg.fact_ban_scare",
   "注定|必离|没戏|克夫|克妻|孤独终老" in _lp)
# 危机文案仍是固定串（罐头行语义不变）
ck("reg.crisis_text_constant",
   '_tasks[tid] = {"status": "done", "text": _CHAT_REFUSAL' in _lp)

print(f"\n{len(PASS)} pass, {len(FAIL)} fail")
sys.exit(1 if FAIL else 0)
