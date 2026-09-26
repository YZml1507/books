#!/usr/bin/env python3
"""R2522 — 中间件/启动面审查钉扎（agent af7d1231 迟交报告的亲验落地）。

- P1：_access_gate 三处 compare_digest 改 bytes 比对——非 ASCII 口令/
  cookie/?key=/表单值在 ExceptionMiddleware 外侧抛 TypeError → 裸 500。
- P2：web_launcher port_ready 的「小满」字节标记 \\xe6\\bb\\xa1 原写成
  \\xe6\\bb(b)\\xa1（\\bb 解析成 \\x08+'b' 死标记），并补 /_gate 匹配——
  闸页下首页无 manifest/books → 探测健康服务恒超时误杀。
- P3-1：_INDEX_CACHE 键 (mtime_ns, size)——保 mtime 部署不再发旧壳。
- P3-4：CORS allow_credentials=True——分体部署+访问口令此前结构性不通。
- P3-6：pid_alive 词边界匹配——PID "123" 不再误配 "51230"。
- P3-14：services.py 重复 import time。
"""
import re
import sys

sys.path.insert(0, ".")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


_app = open("web/app.py", encoding="utf-8").read()
_lch = open("web_launcher.py", encoding="utf-8").read()
_svc = open("web/services.py", encoding="utf-8").read()

# ── P1：bytes 比对 + 三处全走 _eq ────────────────────────────────
ck("p1.eq_helper",
   'a.encode("utf-8", "replace")' in _app and
   'b.encode("utf-8", "replace")' in _app)
ck("p1.cookie_uses_eq",
   'good = _eq(request.cookies.get("books_key", ""), _ck)' in _app)
ck("p1.post_uses_eq",
   "if _eq(key, _tok):" in _app)
ck("p1.query_uses_eq",
   '_key_ok = _eq(request.query_params.get("key", ""), _tok)' in _app)
ck("p1.no_raw_str_compare",
   "compare_digest(request.cookies" not in _app and
   "compare_digest(key, _tok)" not in _app and
   "compare_digest(\n            request.query_params" not in _app)

# 行为级：非 ASCII 输入进 _eq 语义无异常（模拟同型比对）
import hmac as _h


def _eq(a, b):
    return _h.compare_digest(a.encode("utf-8", "replace"),
                             b.encode("utf-8", "replace"))
try:
    _eq("小满", "x" * 64); _eq("", "小满口令人")
    ck("p1.nonascii_no_raise", True)
except Exception as e:
    ck("p1.nonascii_no_raise", False, repr(e))
ck("p1.nonascii_token_match", _eq("小满口令", "小满口令") is True)
ck("p1.nonascii_token_miss", _eq("小满口令", "小满口令人") is False)

# ── P2：launcher 标记字节修复 ─────────────────────────────────────
ck("p2.xbb_fixed", b"\xe6\xbb\xa1" == "满".encode())
ck("p2.literal_fixed",
   re.search(r'b"\\xe5\\xb0\\x8f\\xe6\\xbb\\xa1"', _lch) is not None)
ck("p2.gate_marker", 'b"/_gate" in head' in _lch)

# ── P3-1：index 缓存签名 ─────────────────────────────────────────
ck("p3.index_sig",
   "sig = (st.st_mtime_ns, st.st_size)" in _app)

# ── P3-4：CORS credentials ───────────────────────────────────────
ck("p3.cors_credentials", "allow_credentials=True" in _app)

# ── P3-6：pid_alive 词边界 ───────────────────────────────────────
ck("p3.pid_word_boundary",
   're.search(r"\\b" + re.escape(str(pid)) + r"\\b", out)' in _lch)
import re as _re

_out = "chrome.exe  51230 Console  1  100,000 K"
ck("p3.pid_no_substring_false_pos",
   _re.search(r"\b" + _re.escape("123") + r"\b", _out) is None)
ck("p3.pid_hit",
   _re.search(r"\b" + _re.escape("51230") + r"\b", _out) is not None)

# ── P3-14：重复 import ───────────────────────────────────────────
ck("p3.no_dup_import_time",
   _svc.count("\nimport time\n") + _svc.startswith("import time\n") == 1)

# ── 前端审 P2-1：transcript 恢复批量滚 ──────────────────────────
_js = open("web/static/app.js", encoding="utf-8").read()
ck("fe.chatbubble_noscroll",
   "if (!opts || !opts.noscroll) flow.scrollTop = flow.scrollHeight;" in _js)
ck("fe.restore_noscroll",
   "{ nosave: true, noscroll: true }" in _js)
ck("fe.restore_scroll_once",
   re.search(r"_chatTsRestore[\s\S]{0,500}scrollTop = \w+\.scrollHeight",
             _js) is not None)
ck("fe.tarot_img_esc",
   '"<img src=\\"" + esc(img)' in _js or
   '\'<img src="\' + esc(img)' in _js or 'src="' + "' + esc(img)" in _js)

# ── R2523 续修：sid 'c-anon' 共享回退 → 记忆化随机 ───────────────
ck("fe.sid_no_shared_anon",
   "return 'c-anon';" not in _js and "_SID_MEMO" in _js and
   "'c-anon-'" in _js)

# ── R2523：search.py PRAGMA 校验收进坏库 try（db 泄漏微观口）────
_sch = open("src/guji/search.py", encoding="utf-8").read()
ck("be.search_pragma_in_try",
   "R2523（审-P3-10）" in _sch and
   _sch.index("PRAGMA table_info(unit)") <
   _sch.index("except sqlite3.DatabaseError"))

# ── R2523 services agent 三 P2 ────────────────────────────────────
_svc2 = _svc  # services.py 已读
ck("sv.search_total_zero_retry",
   "shown_extra = len(hits2)" in _svc2)
ck("sv.thread_detail_batch",
   "derived_id IN (" in _svc2 and "kb.get(row[\"id\"])" not in _svc2)
_bl = open("src/guji/bazi_lookup.py", encoding="utf-8").read()
ck("sv.lookup_conn_closing",
   _bl.count("contextlib.closing(sqlite3.connect(DB))") == 2 and
   "conn.close()" not in _bl and
   "json.dump(meta, _mf)" in _bl)

print(f"\n{len(PASS)} pass, {len(FAIL)} fail")
sys.exit(1 if FAIL else 0)
