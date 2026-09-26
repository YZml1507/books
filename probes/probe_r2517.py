#!/usr/bin/env python3
"""R2517 — 路由审查挂账清偿钉扎。

- P2-2：422 英文 msg/url 不外流——_422_MSG_CN 模板 + value_error 剥前缀
  + url 剥除 + 英文兜底泛化（web/errors.py）。
- P2-3：addr 过滤参数存在性——layer/addr_name/addr2 拼错如实 400，
  与 search 同纪律（合法空集仍 200）。
- P3-5：xingzuo/daily 的 date 参数补 Query(max_length=10)。
- P3-7：qiming/review 限流哨兵 "__rate_limited__" → {"rate_limited": true}。
- P3-8：CSV 导出公式前缀（=+-@）加 ' 脱活。
- P3-9：台账禁用下 import 的 records 段如实披露 records_ignored。
- P3-10：tarot/draw n 收紧 le=1（契约自称单张）。
- P3-11：_corpus_index_stale 60s 记忆窗（每请求全树 os.walk → 进程内缓存）。
"""
import re
import sys

sys.path.insert(0, ".")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


_err_src = open("web/errors.py", encoding="utf-8").read()
_svc_src = open("web/services.py", encoding="utf-8").read()
_sch_src = open("web/schemas.py", encoding="utf-8").read()
_bz_src = open("web/routers/bazi.py", encoding="utf-8").read()
_pd_src = open("web/routers/product.py", encoding="utf-8").read()
_lp_src = open("src/guji/llm_polish.py", encoding="utf-8").read()

# --- P2-2: 422 中文模板 + url 剥除 ---
ck("err.msg_cn_table", "_422_MSG_CN" in _err_src
   and "less_than_equal" in _err_src and "int_parsing" in _err_src)
ck("err.url_stripped", 'e.pop("url", None)' in _err_src)
ck("err.value_error_prefix",
   '"Value error, "' in _err_src and 'startswith(' in _err_src)
ck("err.en_fallback",
   re.search(r'\[A-Za-z\]\{4,\}', _err_src) is not None)

# 活端点级：构造 pydantic 错误 dict 走 handler 同款逻辑不可行（handler 需
# Request），改为 schema 层实证——TarotDrawRequest n=2 现在该拒。
from web.schemas import TarotDrawRequest  # noqa: E402
try:
    TarotDrawRequest(n=2)
    ck("tarot.n_le1", False, "n=2 still accepted")
except Exception:
    ck("tarot.n_le1", True)
ck("tarot.n1_ok", TarotDrawRequest(n=1).n == 1)

# --- P2-3: addr 存在性校验 ---
ck("addr.exist_check",
   re.search(r"def addr[\s\S]{0,2200}SELECT 1 FROM unit WHERE", _svc_src)
   is not None)
ck("addr.err_cn", "库里没有" in _svc_src)

# --- P3-5: date max_length ---
ck("date.xz_bound",
   'def xingzuo(date: str | None = Query(None, max_length=10))'
   in _bz_src)
ck("date.daily_bound",
   "def daily(date: str | None = Query(None, max_length=10)," in _pd_src)

# --- P3-7: review 限流哨兵 ---
ck("review.sentinel_src",
   re.search(r'_rate_ok\("review"[\s\S]{0,300}return "__rate_limited__"',
             _lp_src) is not None)
ck("review.sentinel_route",
   re.search(r'qiming_review[\s\S]{0,600}rate_limited', _bz_src) is not None)

# --- P3-8: CSV 公式脱活 ---
ck("csv.sanitize",
   'startswith(' in _bz_src and '"=", "+", "-", "@"' in _bz_src
   and "'\" + str(v)" in _bz_src.replace("'", "'"))

# --- P3-9: import 披露 ---
ck("import.records_ignored", "records_ignored" in _bz_src)

# --- P3-11: stale 缓存 ---
ck("stale.cache",
   "_STALE_TTL" in _svc_src and "_stale_cache" in _svc_src)

# --- 功能性实证：addr 存在性走真 DB ---
from web import services  # noqa: E402
from web.schemas import ValidationError  # noqa: E402
try:
    services.addr("zhouyi", gua=1, layer="不存在的层-probe")
    ck("addr.typo_400", False, "typo layer returned 200")
except ValidationError as e:
    ck("addr.typo_400", "库里没有" in str(e))
_ok = services.addr("zhouyi", gua=1, yao="九三")
ck("addr.legit_ok", _ok.get("count", 0) > 0)

print(f"\n{len(PASS)} checks, {len(FAIL)} failed: {FAIL}")
sys.exit(1 if FAIL else 0)
