"""web/selftest.py — web 层 standing 自测（原 app.py `__main__` 那 912 行）。

复验命令（宪法第一条：任何状态断言必须附能复现它的命令）：
    .\\.venv\\Scripts\\python.exe web\\selftest.py

为什么独立成文件：自测塞在 `app.py` 的 `__main__` 里，等于把 912 行测试
代码压在 2277 行文件的尾部——`app.py` 的行数里 40% 是测试，谁读都先被
它挡住。分离后 `app.py` 是 76 行的应用工厂，本文件是唯一的 web 层测试
入口，`docs/PHASE.md` 闸门 2 直接指向它。

断言纪律（R178b 重构时逐条搬迁，不放宽）：
  * 每条 check/断言的**名字、固定输入、期望值**与重构前逐字一致。
  * `_expect_400` / `_expect_422` 断言状态码，不走 `check()`（它断言 200）。
  * 写端点（threads 写 knowledge.db）自测后必须清理本轮新增记录
    （L-22 教训：写端点自测不得污染真实库）。R219b（P0-4）：/api/bazi
    不再写 history.db——历史记录功能整体删除，相关清理与断言同批移除。

R178b 契约变更（唯一一处，D-226b）：LLM 生成式解读层已移除，`llm` 字段
→ `interpretation`（`guji.interpreter` 确定性输出）。因此原
`ask.llm.shape` 断言重命名为 `ask.interpretation.shape` 并改为断言
确定性解读的结构（sections/text/engine），其余 129 条断言原样保留。
"""
from __future__ import annotations

import os
import sys

# 直接跑本文件时（python web\selftest.py），项目根不在 sys.path，`import web`
# 会失败。先把项目根塞进去，再走包导入——web/__init__.py 负责 src/ 引导。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi.testclient import TestClient                       # noqa: E402

from web.app import app                                         # noqa: E402
from web.deps import KNOWLEDGE_DB                               # noqa: E402

# R68b：P2 子平书集合（bazi_lookup.MINGLI_WORKS 中的 9 部本地入库书）
ZI_PING_WORKS = {"ditiansui", "lantai-miaoxuan", "mingli-tanyuan",
                 "mingli-yueyan", "qiongtongbaojian", "sanming-tonghui",
                 "wuxing-dayi", "wuxing-jingji", "ziping-zhenquan"}


def run() -> list[str]:
    """跑完整 standing 自测，返回通过的检查名列表。失败即 AssertionError。"""
    # R228u：强制离线——session 环境可能注入 BOOKS_LLM_API_KEY（实测：宿主机
    # 全局 env 有 key 时，本套件每个端点 POST 都往外网真打 LLM，轻则
    # pending 撞 _MAX_PENDING 断言失败，重则整轮挂死在网络等待）。
    # 闸门语义就是确定性离线；显式 config 的打桩段（ai.async.*）不受此影响。
    _saved_disable = os.environ.get("BOOKS_LLM_DISABLE")
    os.environ["BOOKS_LLM_DISABLE"] = "1"
    # R229n（R6-#1）：bazi 流程的 save_async 会往真实台账写记录——
    # 本套件每轮 ~15 个 bazi POST 等于每次全量 +15 行假数据挤占
    # KEEP_MAX=500。selftest 不测历史功能（那是 ui_smoke 的地盘），禁用。
    _saved_ph = os.environ.get("BOOKS_PAIPAN_HISTORY_DISABLE")
    os.environ["BOOKS_PAIPAN_HISTORY_DISABLE"] = "1"
    try:
        return _run_inner()
    finally:
        if _saved_disable is None:
            os.environ.pop("BOOKS_LLM_DISABLE", None)
        else:
            os.environ["BOOKS_LLM_DISABLE"] = _saved_disable
        if _saved_ph is None:
            os.environ.pop("BOOKS_PAIPAN_HISTORY_DISABLE", None)
        else:
            os.environ["BOOKS_PAIPAN_HISTORY_DISABLE"] = _saved_ph


def _run_inner() -> list[str]:
    client = TestClient(app)
    ok: list[str] = []

    def check(name, resp, pred):
        assert resp.status_code == 200, (name, resp.status_code, resp.text[:200])
        body = resp.json()
        assert pred(body), (name, body)
        ok.append(name)

    # R124b（D-170b）：错误处理路径 standing 覆盖——check() 闭包只断言合法
    # 输入的 200，非法输入（应 400）此前零断言：若某端点把参数校验改回未捕获
    # 异常（400→500），selftest 全绿看不见。以下独立断言 400（不走闭包）。
    def _expect_400(name, resp):
        assert resp.status_code == 400, (name, resp.status_code, resp.text[:200])
        # R228o：状态码对还不够——detail 必须是非空人话字符串，
        # 否则前端拿到 {detail:{...}} 照样渲染出 [object Object]。
        _d = resp.json().get("detail")
        assert isinstance(_d, str) and _d.strip(), (name, _d)
        ok.append(name)

    # R163b（D-209b）：422 排盘失败分支断言辅助——400 参数校验断言不构成
    # 422 计算失败路径的覆盖（compute 抛异常→422，如 1990-02-30 不存在）。
    def _expect_422(name, resp):
        assert resp.status_code == 422, (name, resp.status_code, resp.text[:200])
        _d = resp.json().get("detail")
        assert isinstance(_d, str) and _d.strip(), (name, _d)
        ok.append(name)

    # ── 读书域：检索 / 定位 / 比对 / 书目 / 统计 ──────────────────
    check("search", client.get("/api/search", params={"q": "潛龍勿用"}),
          lambda j: j.get("hits"))
    # R128b（D-174b）：search 的 layer/work 过滤参数分支 standing 覆盖——
    # search check 只测裸 q，layer/work 过滤 SQL 零断言（若过滤拼接回归、
    # 返回未过滤全集则不可见）。固定输入实测：layer=經 → hits=10；
    # work=KR1a0001 → hits=2（过滤收窄生效）。
    check("search.layer", client.get("/api/search", params={"q": "潛龍勿用",
          "layer": "經"}),
          lambda j: (j.get("hits") and all(h.get("layer") == "經"
                                           for h in j["hits"])))
    check("search.work", client.get("/api/search", params={"q": "潛龍勿用",
          "work": "KR1a0001"}),
          lambda j: (j.get("hits") and all(h.get("work_id") == "KR1a0001"
                                           for h in j["hits"])))
    check("addr", client.get("/api/addr", params={"scheme": "zhouyi", "gua": 1}),
          lambda j: j.get("hits"))
    # R137b（D-183b）：addr zhouyi 的 yao 爻位过滤分支 standing 覆盖——
    # addr check 只测 gua=1 无 yao 参数，yao（addr2 爻位过滤）分支零断言。
    # 实测 gua=1&yao=初九 → 10 hits 全为初九。
    check("addr.zhouyi.yao", client.get("/api/addr", params={"scheme": "zhouyi",
          "gua": 1, "yao": "初九"}),
          lambda j: (j.get("hits") and all(h.get("yao") == "初九"
                                           for h in j["hits"])))
    # R110b（D-156b）：zhouyi 之外五类 scheme 走 at_scheme 通用路径，此前无
    # standing 断言——若该路径静默失效，13 闸门与五层自测都看不见。固定参数
    # 实测可稳定复现（bcv Proverbs 12:12 / yilin 中孚 61 / booksec addr1=10 /
    # play THE SONNETS 1 / euclid Book 1）。
    for _sch, _params in (
        ("addr.bcv", {"scheme": "bcv", "addr_name": "Proverbs", "addr1": 12,
                      "addr2": "12"}),
        ("addr.yilin", {"scheme": "yilin", "addr1": 61}),
        ("addr.booksec", {"scheme": "booksec", "addr1": 10}),
        ("addr.play", {"scheme": "play", "addr_name": "THE SONNETS", "addr1": 1}),
        ("addr.euclid", {"scheme": "euclid", "addr_name": "Book 1", "addr1": 1}),
    ):
        check(_sch, client.get("/api/addr", params=_params),
              lambda j, s=_params["scheme"]: j.get("hits") and j.get("scheme") == s)
    check("compare", client.get("/api/compare", params={"gua": 28, "yao": "九二"}),
          lambda j: "findings" in j)
    check("works", client.get("/api/works"),
          lambda j: j.get("works") and all("source" in w for w in j["works"]))
    check("stats", client.get("/api/stats"),
          lambda j: j.get("stats") and j.get("layers"))
    check("bookstudy.structure", client.get("/api/bookstudy/structure",
          params={"work_id": "KR1a0001"}),
          lambda j: j.get("sections") and j.get("scheme") == "zhouyi")
    check("bookstudy.chapter", client.get("/api/bookstudy/chapter",
          params={"work_id": "KR1a0001", "scheme": "zhouyi", "addr1": 1}),
          lambda j: j.get("units") and all(u.get("citation") for u in j["units"]))
    # R130b（D-176b）：bookstudy.chapter 的 NULL-scheme 文件节分支 standing
    # 覆盖——现有 check 只测 zhouyi（KR1a0001），无 scheme 文件节（老子）
    # 读取零断言。实测 work_id=老子&scheme=booksec&addr1=1 → 200 + error 键。
    check("bookstudy.chapter.nullscheme", client.get("/api/bookstudy/chapter",
          params={"work_id": "老子", "scheme": "booksec", "addr1": 1}),
          lambda j: j.get("error") is not None)
    check("bookstudy.summary", client.get("/api/bookstudy/summary",
          params={"work_id": "KR1a0001"}),
          lambda j: j.get("n_units") and j.get("layers"))
    # R134b（D-180b）：bookstudy.summary 缺失作品拒绝分支 standing 覆盖——
    # summary check 只测命中路径（KR1a0001）。实测 NO_SUCH_WORK → 200 + error。
    check("bookstudy.summary.missing", client.get("/api/bookstudy/summary",
          params={"work_id": "NO_SUCH_WORK"}),
          lambda j: j.get("error") is not None)
    check("compare_works", client.get("/api/compare_works",
          params={"work_a": "KR5c0057", "work_b": "KR5c0126", "q": "無爲"}),
          lambda j: j.get("works") and len(j["works"]) == 2)
    # R130b（D-176b）：compare_works 无命中拒绝分支（G7）standing 覆盖——
    # 实测无命中 q → 200 + error="「電話飛機電腦」在两书均无命中"。
    check("compare_works.refuse", client.get("/api/compare_works",
          params={"work_a": "KR5c0057", "work_b": "KR5c0126",
                  "q": "電話飛機電腦"}),
          lambda j: j.get("error") is not None)
    check("concept", client.get("/api/concept", params={"q": "無爲"}),
          lambda j: j.get("census"))
    check("threads.list", client.get("/api/threads"), lambda j: "threads" in j)

    # ── 数术主 tab 端点（R53b）：bazi/liuyao/huangli/qiming 确定性覆盖 ──
    # R219b（P0-4）：/api/bazi 曾把查询写入 history.db（D-039），历史记录
    # 功能整体删除后它是纯读端点——原 history_db import + max_id_before
    # 基线 + 各段清理循环一并移除（写端点污染纪律对本端点不再适用）。
    check("bazi", client.post("/api/bazi", json={"year": 1990, "month": 1,
          "day": 1, "hour": 12, "gender": "男"}),
          lambda j: (j.get("paipan") and j.get("calc")
                     # R68b 归因修正（R69b，D-115b）：web /api/bazi 的 evidence
                     # 来自 retrieve_fast（FTS 路径），此处断言 FTS 命中非空 +
                     # 含 P2 子平书——抓 FTS 检索静默失效。
                     and j.get("evidence")
                     and any(e.get("work_id") in ZI_PING_WORKS
                             for e in j.get("evidence", []))))
    # R178b（D-226b）：确定性解读层 standing 覆盖——原 llm 字段（生成文本，
    # 需 key + 网络、不可复现）替换为 interpretation（guji.interpreter 规则
    # 输出）。断言引擎标识 + sections 非空 + text 以「## 排盘坐标」开头，
    # 且**同输入两次调用输出逐字相同**（确定性，LLM 做不到这条）。
    _b1 = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男",
                                        "question": "事业运如何？"}).json()
    _b2 = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男",
                                        "question": "事业运如何？"}).json()
    assert _b1["interpretation"]["ok"] is True, _b1["interpretation"]
    assert "无 LLM" in _b1["interpretation"]["engine"], _b1["interpretation"]
    assert _b1["interpretation"]["text"].startswith("## 排盘坐标"), \
        _b1["interpretation"]["text"][:80]
    assert any(s["title"] == "针对「事业运如何？」"
               for s in _b1["interpretation"]["sections"]), \
        [s["title"] for s in _b1["interpretation"]["sections"]]
    assert _b1["interpretation"]["text"] == _b2["interpretation"]["text"], \
        "interpreter must be deterministic: same input -> same output"
    ok.append("bazi.interpretation.deterministic")
    # R179b（D-231b，审查轨 R118a-03）：/api/bazi 的 evidence 每条必须带
    # 可核验出处。该路径走 bazi_lookup.retrieve_fast（返回裸 dict，不经
    # Hit），此前**没有 citation 键**——前端 `esc(ev.citation||'')` 把出处
    # 静默渲染成空串：原文有了、出处没了。宪法第三条「引用与生成分离」
    # 要求原文必带出处，`||''` 兜底不构成合规。断言 citation 存在且非空、
    # 且含页锚点（@）与源文件名——抓「出处又变空」的静默回归。
    _ev = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男"}).json()["evidence"]
    assert _ev, "bazi evidence must be non-empty"
    for _e in _ev:
        assert _e.get("citation"), ("bazi.evidence.citation", sorted(_e))
        assert "@" in _e["citation"] and _e["file"] in _e["citation"], _e["citation"]
    ok.append("bazi.evidence.citation")
    # R119b（D-165b）：bazi lunar 农历换算路径 standing 覆盖——bazi check 只测
    # solar，calendar_type=lunar 走 resolve_birth→lunar_to_solar 零断言。固定
    # 农历生日 1990-05-15 男 → 200 + 日主癸（lunar_to_solar=1990-06-07）。
    check("bazi.lunar", client.post("/api/bazi", json={"calendar_type": "lunar",
          "lunar_year": 1990, "lunar_month": 5, "lunar_day": 15,
          "lunar_leap": False, "hour": 10, "gender": "男",
          "year": 1990, "month": 5, "day": 15}),
          lambda j: (j.get("paipan") and j["paipan"].get("render")
                     and j["paipan"]["render"].startswith("庚午年 壬午月 癸卯日")))
    check("bazi.lunar_leap", client.post("/api/bazi",
          json={"calendar_type": "lunar", "lunar_year": 1990, "lunar_month": 5,
                "lunar_day": 15, "lunar_leap": True, "hour": 10,
                "gender": "女", "year": 1990, "month": 5, "day": 15}),
          lambda j: j.get("paipan") and j["paipan"].get("render"))
    # R126b（D-172b）：bazi scope=range / scope=life 两分支 standing 覆盖——
    # bazi check 只测默认 scope=day，calc_range/calc_life 零断言。固定输入：
    # range 2026-01-01~05 → days=5；life → dayun 长度 8（实测稳定）。
    check("bazi.range", client.post("/api/bazi", json={"year": 1990, "month": 5,
          "day": 15, "hour": 10, "gender": "男", "scope": "range",
          "range_start": "2026-01-01", "range_end": "2026-01-05"}),
          lambda j: (j.get("calc", {}).get("scope") == "range"
                     and len(j.get("calc", {}).get("days", [])) == 5))
    check("bazi.life", client.post("/api/bazi", json={"year": 1990, "month": 5,
          "day": 15, "hour": 10, "gender": "男", "scope": "life"}),
          lambda j: (j.get("calc", {}).get("scope") == "life"
                     and len(j.get("calc", {}).get("dayun", [])) == 8))
    # R69b（D-115b）：retrieve_semantic（bge 语义路径）standing 覆盖——该路径
    # 只在 CLI（scripts/ask_bazi.py）调用，web /api/bazi 不经过它，13 闸门与
    # 五层自测此前均不覆盖。固定 Bazi 输入 → 语义命中非空 + 含 P2 子平书。
    from guji.bazi import compute as _bazi_compute
    from guji.bazi_lookup import retrieve_semantic as _retrieve_semantic

    sem = _retrieve_semantic(_bazi_compute(1990, 1, 1, 12, "男"), top_k=8)
    assert sem and any(e["work_id"] in ZI_PING_WORKS for e in sem), \
        "semantic retrieval must hit P2 books"
    ok.append("bazi.semantic")
    check("liuyao", client.post("/api/liuyao", json={"method": "coins",
          "seed": 42}),
          lambda j: j.get("ben") and j["ben"].get("gua_number") == 22)
    # R118b（D-164b）：liuyao time（梅花易数时间起卦）与 huangli affair（择日
    # 查找 find_good_days）两条已接线能力路径此前零 standing 断言——实测曾
    # 发现 affair 分支因 timedelta 未导入而 NameError 静默损坏。固定参数确定性
    # 可复验：time 起卦 2026-08-16 10:00 → 萃45；affair=婚嫁 30 天 → 非空。
    check("liuyao.time", client.post("/api/liuyao", json={"method": "time",
          "year": 2026, "month": 8, "day": 16, "hour": 10}),
          lambda j: j.get("ben") and j["ben"].get("gua_number") == 45)
    check("huangli.affair", client.get("/api/huangli", params={"affair": "婚嫁",
          "date": "2026-08-17", "days": 30}),
          lambda j: j.get("count", 0) > 0 and bool(j.get("good_days")))
    # R228x：口语事项归一——「理发」不在宜忌词表，不归一则 good_days 恒空；
    # 归一后落到冠笄（实测 2026-09-19 起 45 天内 4 天）。terms 回显供前端
    # 与用户确认「理发按冠笄查的」。
    check("huangli.affair.spoken", client.get("/api/huangli", params={
          "affair": "理发", "date": "2026-09-19", "days": 45}),
          lambda j: j.get("terms") == ["冠笄"] and j.get("count", 0) > 0)
    check("huangli", client.get("/api/huangli", params={"date": "2026-08-17",
          "days": 1}),
          lambda j: j.get("date") and j.get("yi") and j.get("ji"))
    check("qiming", client.post("/api/qiming", json={"surname": "李",
          "year": 1990, "month": 1, "day": 1, "hour": 12, "gender": "男",
          "top_n": 5}),
          lambda j: j.get("full_names") and len(j.get("full_names", [])) >= 3)
    # R221b-fix（审查轨 R221a vision 目视发现）：/api/qiming 的 candidates
    # 自 R217a 起写死 []，前端却渲染「单字候选池（0 字）」折叠区 = 永远空的
    # 空壳。闸门只断言 full_names 所以抓不到——**这类"字段存在但恒为空"的
    # 空壳只有目视能发现**，故补一条断言钉死它非空且键名齐全。
    _rc2 = client.post("/api/qiming", json={
        "surname": "李", "year": 2000, "month": 5, "day": 15,
        "hour": 10, "gender": "女", "top_n": 8, "seed": 1})
    assert _rc2.status_code == 200, ("qiming.candidates.http",
                                    _rc2.status_code)
    _cands = _rc2.json().get("candidates") or []
    assert len(_cands) >= 8, ("qiming.candidates.empty", len(_cands))
    for _c in _cands:
        # 键名必须与前端 app.js 读的一致，否则渲染出空白格子
        assert set(_c) == {"char", "element", "radical", "meaning"}, \
            ("qiming.candidates.keys", sorted(_c))
        assert _c["char"] and _c["element"], ("qiming.candidates.blank", _c)
    print(f"  qiming.candidates.filled PASS（候选池 {len(_cands)} 字，键名齐全）")
    ok.append("qiming.candidates.filled")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R226b-fix（审查轨 R226a 目视抓到）：典故库每条的**字必须真出现在「句」里**。
    # 前端把「句」直接展示给用户（"📜 <句> —— <出处>"），字不在句里就是露馅：
    # 实测曾有 14 条不自洽，如「澜」配"河伯过江海"、「苓」配"蒹葭苍苍"、
    # 「圯」配"白圭之玷"。这类错误纯数据层、闸门原先完全不查。
    # 顺带钉住：句/出处/意象都不许为空；倾向表里不许挂库中已不存在的字。
    import json as _json
    _dbp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "src", "guji", "classical_names.json")
    with open(_dbp, encoding="utf-8") as _f:
        _db = _json.load(_f)
    _db_chars, _n_entries = set(), 0
    for _el, _items in _db.items():
        if _el == "_meta":
            continue
        for _it in _items:
            _n_entries += 1
            _ch, _sent = _it.get("字", ""), _it.get("句", "")
            assert _ch, ("classical_db.empty_char", _el, _it)
            assert _sent and _it.get("出处") and _it.get("意象"), \
                ("classical_db.empty_field", _el, _ch, _it)
            assert _ch in _sent, \
                ("classical_db.char_not_in_sentence", _el, _ch, _sent,
                 "前端会把「句」直接展示，字不在句里=露馅")
            _db_chars.add(_ch)
    from guji.classical_names import (_AVOID_FEM as _AV2, _FEM_LEAN as _FL2,
                                     _MASC_LEAN as _ML2)
    for _tbl_name, _tbl in (("_FEM_LEAN", _FL2), ("_MASC_LEAN", _ML2),
                            ("_AVOID_FEM", _AV2)):
        _ghost = sorted(_tbl - _db_chars)
        assert not _ghost, \
            ("classical_db.ghost_chars", _tbl_name, _ghost,
             "倾向表里挂着典故库中已不存在的字——删条目时忘了同步表")
    print(f"  classical_db.integrity PASS（{_n_entries} 条：字在句中、"
          f"字段非空、倾向表无幽灵字）")
    ok.append("classical_db.integrity")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R221b：交叉引用收口 7/7。用户原话「各是各的，各干各的，没有交叉集」，
    # 每个结果页底部都要有「相关维度」。这里钉死**七个端点全覆盖**——
    # 少一个就 FAIL，防止后续改动悄悄漏掉某个端点。
    # 注意塔罗/六爻**不收生日**，只能引"今天的值宫"，不得编造本命星座
    # （八字/桃花/起名那三处才有出生月日可用）。
    _cr_cases = [
        ("/api/bazi", {"year": 2005, "month": 6, "day": 6, "hour": 10,
                       "gender": "女"}),
        ("/api/taohua", {"year": 2005, "month": 6, "day": 6, "hour": 10,
                         "gender": "女"}),
        ("/api/qiming", {"surname": "林", "year": 2005, "month": 6, "day": 6,
                         "hour": 10, "gender": "女", "top_n": 5}),
        ("/api/hehun", {"a_year": 2005, "a_month": 6, "a_day": 6,
                        "a_hour": 10, "a_gender": "男",
                        "b_year": 1990, "b_month": 5, "b_day": 15,
                        "b_hour": 14, "b_gender": "女"}),
        ("/api/tarot", {"seed": 42, "n": 3}),
        ("/api/liuyao", {"method": "coins", "seed": 42}),
    ]
    for _ep, _pl in _cr_cases:
        _rc = client.post(_ep, json=_pl)
        assert _rc.status_code == 200, ("cross_ref.http", _ep, _rc.status_code)
        _crm = (_rc.json().get("cross_ref") or {}).get("message", "")
        assert _crm, ("cross_ref.missing", _ep)
    # R224b（审查轨 R221a 抓到）：_cross_ref_taohua 的分支值原写 high/low，
    # 而 taohua.py 产出的是 **strong/mid/weak** → 分支永不命中，全掉 else，
    # "信号叠加"文案从 R220b 起从未生效。cross_ref.message 非空所以判据全绿。
    # 教训：**枚举分支必须钉住每个分支的实际输出**，只断言"非空"抓不到这类错。
    # 这里找出真能产出 strong 与 weak 的生日，断言对应文案真的出现。
    # 样本必须**三档全覆盖**，否则某个分支的文案永远没被验证过（strong 那句
    # 就是这么当了半轮死代码）。这三组是扫出来的：strength 由咸池命中柱数决定
    # （taohua.py:91-96，>=2 strong / ==1 mid / 0 weak），所以要带上时辰。
    _seen_strength: dict[str, str] = {}
    for _y, _m, _d, _h, _g in ((1985, 6, 24, 2, "女"),    # strong（命中 >=2 柱）
                               (1985, 1, 1, 18, "女"),    # mid（命中 1 柱）
                               (1985, 1, 1, 2, "女"),     # weak（0 柱）
                               (1990, 5, 15, 10, "女"),
                               (2003, 7, 7, 10, "女"),
                               (2005, 12, 3, 10, "女")):
        _rt = client.post("/api/taohua", json={
            "year": _y, "month": _m, "day": _d, "hour": _h, "gender": _g})
        assert _rt.status_code == 200, ("taohua.http", _y, _rt.status_code)
        _tj = _rt.json()
        _st = _tj.get("strength", "")
        assert _st in ("strong", "mid", "weak"), ("taohua.strength.enum", _st)
        _msg = (_tj.get("cross_ref") or {}).get("message", "")
        assert _msg, ("taohua.cross_ref.missing", _y, _m, _d)
        _seen_strength.setdefault(_st, _msg)
        # 分档文案必须与 strength 对应，不能所有档位都是同一句
        if _st == "strong":
            assert "叠一起" in _msg, ("taohua.cross_ref.strong", _st, _msg)
        elif _st == "weak":
            assert "偏淡" in _msg, ("taohua.cross_ref.weak", _st, _msg)
        else:
            assert "建议是" in _msg, ("taohua.cross_ref.mid", _st, _msg)
    assert set(_seen_strength) == {"strong", "mid", "weak"}, \
        ("taohua.strength.coverage",
         "样本只覆盖到 " + str(sorted(_seen_strength))
         + "——三档必须全覆盖，否则未覆盖分支的文案是没验证过的死代码")
    print(f"  taohua.cross_ref.strength PASS（覆盖 {sorted(_seen_strength)}，"
          f"分档文案与 strength 对应）")
    ok.append("taohua.cross_ref.strength")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # 黄历是 GET
    _rh2 = client.get("/api/huangli?date=2026-08-28")
    assert _rh2.status_code == 200, ("cross_ref.http", "/api/huangli")
    assert (_rh2.json().get("cross_ref") or {}).get("message"), \
        ("cross_ref.missing", "/api/huangli")
    print("  cross_ref.coverage PASS（7 端点全有相关维度段）")
    ok.append("cross_ref.coverage")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R226b（审查轨 R222a 点名）：塔罗/六爻的"两信号关系"原先只是牌面正逆/
    # 动爻数的纯函数——今天白羊还是金牛，逆位都输出同一句"和今天的节奏不
    # 完全一致"，**从没比较过两个信号**。修法是给 12 宫标方向倾向
    # （xingzuo.SIGN_DIRECTION）再做 3×3 真实比对。
    # 判据的关键：**同一牌面 × 不同值宫方向必须给出不同 relation**——
    # 这是"真的在比较"与"只是自说自话"的分水岭。只断言 message 非空抓不到。
    from web import services as _svc
    _rel_forward = _svc._signal_relation("forward", "forward", "牌面")
    _rel_hold = _svc._signal_relation("forward", "hold", "牌面")
    _rel_obs = _svc._signal_relation("forward", "observe", "牌面")
    assert len({_rel_forward, _rel_hold, _rel_obs}) == 3, \
        ("cross_ref.relation.not_comparing",
         "同一牌面方向遇到三种值宫方向却给出重复文案——relation 没在比较两个信号",
         [_rel_forward, _rel_hold, _rel_obs])
    # 反向也要成立：同一值宫 × 不同牌面方向
    _r2 = {_svc._signal_relation(_a, "hold", "牌面")
           for _a in ("forward", "hold", "mixed")}
    assert len(_r2) == 3, ("cross_ref.relation.card_side_ignored", sorted(_r2))
    # 9 种组合两两不同（防某两格文案撞车）
    _matrix = {(_a, _b): _svc._signal_relation(_a, _b, "牌面")
               for _a in ("forward", "hold", "mixed")
               for _b in ("forward", "hold", "observe")}
    assert len(set(_matrix.values())) == 9, \
        ("cross_ref.relation.matrix_collision",
         len(set(_matrix.values())), "9 格应各不相同")
    # 值宫方向缺失时要有兜底，不能抛
    assert _svc._signal_relation("forward", "", "牌面")
    # 端到端：塔罗/六爻响应必须带 today_direction 字段（证明真取了值宫方向）
    for _ep, _pl, _k in (("/api/tarot", {"seed": 42, "n": 3}, "card_direction"),
                         ("/api/liuyao", {"method": "coins", "seed": 42},
                          "gua_direction")):
        _rr = client.post(_ep, json=_pl).json()
        _cr = _rr.get("cross_ref") or {}
        assert _cr.get("today_direction") in ("forward", "hold", "observe"), \
            (_ep, "today_direction 缺失或非法", _cr.get("today_direction"))
        assert _cr.get(_k), (_ep, f"{_k} 缺失")
        # 塔罗/六爻不得出现本命星座字段（不收生日，编造即错）
        assert "zodiac_sign" not in _cr, (_ep, "不得编造本命星座", _cr)
    print("  cross_ref.relation PASS（3×3 矩阵 9 格各异，真在比较两个信号）")
    ok.append("cross_ref.relation")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R220b（P0-3 返工回归）：「换一批」连点三次必须零重复。
    # 历史：D-004-fix 相邻重叠 4/8 → R219b 改环形取段，**只报相邻对**
    # （1∩2=1、2∩3=1）就宣布通过，审查轨实测 1∩3=7/8、2∩4=7/8
    # （每隔一次几乎全重复）→ 选择性报数。真因是候选池只有 15 字、
    # top_n=8 时 8×2>15 数学上装不下三个互斥批次（兜底只取最弱 1 个元素）。
    # 判据必须覆盖**任意两批**，不能只看相邻——这是本条断言存在的理由。
    # R224b（审查轨 R221a 抓到本条判据的漏洞）：原来这里只测 top_n=8，
    # 而**真实前端发的是 top_n=20**（app.js:3003）→ 池 30 字时 30//20=1 段，
    # 第 2/3 批回到同一段，实测交集 13-14/20，判据却全绿。
    # 现在 ①前端降到 8 与后端能力对齐 ②这里断言"前端实际用的值"，
    # 并额外钉一条 `_QM_FRONTEND_TOP_N` 与前端源码一致，防止再次漂移。
    _QM_FRONTEND_TOP_N = 8
    _appjs = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static", "app.js")
    with open(_appjs, encoding="utf-8") as _f:
        _appsrc = _f.read()
    assert f"top_n: {_QM_FRONTEND_TOP_N}," in _appsrc, \
        ("qiming.frontend_top_n.drift", _QM_FRONTEND_TOP_N,
         "前端 top_n 与本判据不一致——改前端时必须同步这里，"
         "否则换一批去重判据测的是不存在的场景")
    # R224b 之二：**首屏那批也必须在轮次体系内**。前端 _qmSeed 初值原为 null，
    # 而 seed=None 在后端走「按性别打分排序」分支（不参与洗牌轮次）→ 首屏批
    # 与 seed=1/2 实测重叠 4 个和 2 个（而 seed1∩seed2=0）。也就是用户点第一次
    # 「换一批」仍会撞首屏。判据原先只测 seed=1/2/3，正好跳过首屏这个真实场景。
    assert "var _qmSeed = 1;" in _appsrc, \
        ("qiming.first_batch.not_seeded",
         "前端 _qmSeed 初值必须是 1（让首屏成为轮次第 1 批）；"
         "若为 null，首屏走非洗牌分支，与后续批次必然重叠")
    # 直接验证 seed=None 与 seed=1 是不同实现路径这件事仍然成立（防后端漂移）
    _r_none = client.post("/api/qiming", json={
        "surname": "李", "year": 2000, "month": 5, "day": 15, "hour": 10,
        "gender": "女", "top_n": _QM_FRONTEND_TOP_N})
    assert _r_none.status_code == 200, ("qiming.noseed.http",
                                       _r_none.status_code)
    _qm_batches: dict[int, set] = {}
    for _seed in (1, 2, 3):
        _rq = client.post("/api/qiming", json={
            "surname": "李", "year": 2000, "month": 5, "day": 15,
            "hour": 10, "gender": "女",
            "top_n": _QM_FRONTEND_TOP_N, "seed": _seed})
        assert _rq.status_code == 200, ("qiming.seed.http", _seed,
                                       _rq.status_code)
        _qm_batches[_seed] = {n["full_name"]
                              for n in _rq.json().get("full_names", [])}
        assert len(_qm_batches[_seed]) == _QM_FRONTEND_TOP_N, \
            ("qiming.seed.count", _seed, len(_qm_batches[_seed]))
    for _a in (1, 2, 3):
        for _b in (1, 2, 3):
            if _a < _b:
                _inter = _qm_batches[_a] & _qm_batches[_b]
                assert not _inter, \
                    ("qiming.rebatch.overlap", _a, _b, sorted(_inter))
    print("  qiming.rebatch.distinct PASS（连点 3 次换一批，任意两批零重复）")
    ok.append("qiming.rebatch.distinct")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R225b（审查轨 R222a 抓到 `典故库 ∩ FEMININE_CHARS = 0`）：
    # 女性加分从未触发过 → 给女生起名时排序无性别倾向，候选里冒出
    # 「鹜(野鸭)/茕(孤独)/苞/埙」。修法是典故库自带 _FEM_LEAN/_AVOID_FEM。
    # 判据钉三件事：① 排除字**一个都不许**出现在女性结果里；
    # ② 女性向占比必须达标（否则等于倾向表没接上）；③ 男女结果必须有差异
    # （防"两性同一套排序"这种静默失效重新出现）。
    from guji.classical_names import _AVOID_FEM as _AV, _FEM_LEAN as _FL
    _fem_names, _masc_names = [], []
    for _seed in (1, 2, 3):
        _rf = client.post("/api/qiming", json={
            "surname": "李", "year": 2000, "month": 5, "day": 15, "hour": 10,
            "gender": "女", "top_n": _QM_FRONTEND_TOP_N, "seed": _seed})
        assert _rf.status_code == 200, ("qiming.fem.http", _rf.status_code)
        _got = [n["full_name"] for n in _rf.json().get("full_names", [])]
        _fem_names += _got
        _chars = set("".join(n[1:] for n in _got))     # 去掉姓
        _bad = sorted(_chars & _AV)
        assert not _bad, ("qiming.female_pool.avoid_char", _seed, _bad,
                          "语义不佳/生僻字不得进女性结果")
        # v3（P3 三字名引入）：双字名的第二字来自互补五行池，允许中性字——
        # 口径改为「每个名字的首字（主字）必须女性向」；全字表占比不再硬钉。
        _first_chars = set(n[1] for n in _got if len(n) >= 2)
        _lean = len(_first_chars & _FL)
        assert _lean >= max(len(_first_chars) - 1, 1), \
            ("qiming.female_pool.lean_ratio", _seed, _lean, len(_first_chars),
             "女性向占比过低——性别倾向表可能没接上")
    _rm = client.post("/api/qiming", json={
        "surname": "李", "year": 2000, "month": 5, "day": 15, "hour": 10,
        "gender": "男", "top_n": _QM_FRONTEND_TOP_N, "seed": 1})
    assert _rm.status_code == 200, ("qiming.masc.http", _rm.status_code)
    _masc_names = [n["full_name"] for n in _rm.json().get("full_names", [])]
    assert set(_masc_names) != set(_fem_names[:_QM_FRONTEND_TOP_N]), \
        ("qiming.gender.no_diff",
         "男女同 seed 结果完全相同——性别偏好静默失效（R222a 抓到过一次）")
    print(f"  qiming.female_pool PASS（3 批共 {len(_fem_names)} 名零排除字，"
          f"男女结果有差异）")
    ok.append("qiming.female_pool")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R220b（P0 回归）：交叉引用的太阳星座必须按【出生月日】判定。
    # 旧实现拿日支查"今日值宫"当本命星座 → 2005-06-06 生（真实双子）被说成
    # 金牛，且连续四天出生得到四个不同座。这里把"生日→座"逐条钉死，
    # 并断言相邻两天出生必须同座（旧 bug 的直接反证）。
    for _y, _m, _d, _want in ((2005, 6, 6, "双子"), (2005, 6, 7, "双子"),
                              (1990, 5, 15, "金牛"), (1990, 1, 1, "摩羯"),
                              (2000, 12, 25, "摩羯"), (1999, 3, 21, "白羊")):
        _r = client.post("/api/bazi", json={
            "year": _y, "month": _m, "day": _d, "hour": 10, "gender": "女"})
        assert _r.status_code == 200, ("bazi.sunsign.http", _y, _m, _d,
                                       _r.status_code)
        _cr = _r.json().get("cross_ref") or {}
        assert _cr.get("zodiac_sign") == _want, \
            ("bazi.cross_ref.sun_sign", _y, _m, _d,
             _cr.get("zodiac_sign"), _want)
        # 文案不得再出现"你的太阳星座是<今日值宫>"这种混淆说法
        assert "太阳星座是" not in _cr.get("message", ""), \
            ("bazi.cross_ref.message.stale", _cr.get("message"))
    print("  bazi.cross_ref.sun_sign PASS（6 例生日 → 太阳星座逐条命中）")
    ok.append("bazi.cross_ref.sun_sign")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # 合婚双方星座同样按出生月日
    _rh = client.post("/api/hehun", json={
        "a_year": 2005, "a_month": 6, "a_day": 6, "a_hour": 10,
        "a_gender": "男", "b_year": 1990, "b_month": 5, "b_day": 15,
        "b_hour": 14, "b_gender": "女"})
    assert _rh.status_code == 200, ("hehun.sunsign.http", _rh.status_code)
    _crh = _rh.json().get("cross_ref") or {}
    assert (_crh.get("zodiac_a"), _crh.get("zodiac_b")) == ("双子", "金牛"), \
        ("hehun.cross_ref.sun_sign", _crh)
    print("  hehun.cross_ref.sun_sign PASS（双子 × 金牛）")
    ok.append("hehun.cross_ref.sun_sign")   # R228f：print-PASS 也进 ok[]（regress 闸门认这个表）
    # R111b（D-157b）：桃花运纯坐标计算 standing 覆盖——固定生日→固定输出，
    # 断言咸池/红鸾/天喜字段齐全且 render 含坐标事实。
    check("taohua", client.post("/api/taohua", json={"year": 1990, "month": 5,
          "day": 15, "hour": 10, "gender": "男"}),
          lambda j: (j.get("peach_zhi") and j.get("hongluan")
                     and j.get("tianxi") and j.get("strength")
                     and j.get("render") and j["bazi"]["year"] == "庚午"
                     and "dayun_hits" in j))
    # R113b（D-159b）：大运桃花应期 standing 覆盖——女命阳年逆排，大运第 2 运
    # 己卯（2003 起）地支卯 == 桃花支卯 → dayun_hits 非空且含己卯。
    check("taohua.dayun", client.post("/api/taohua", json={"year": 1990,
          "month": 5, "day": 15, "hour": 10, "gender": "女"}),
          lambda j: (isinstance(j.get("dayun_hits"), list)
                     and any(d.get("pillar") == "己卯"
                             and d.get("year_start") == 2003
                             for d in j.get("dayun_hits", []))))
    # R112b（D-158b）：塔罗牌 seed 确定性 standing 覆盖——固定 seed → 固定
    # 牌面（实测 seed=42 抽 3 张含 节制/皇后/权杖国王）。
    check("tarot", client.post("/api/tarot", json={"seed": 42, "n": 3}),
          lambda j: (j.get("n") == 3 and len(j.get("draws")) == 3
                     and all(d.get("name") and d.get("upright") is not None
                             and d.get("render") for d in j["draws"])
                     and j["draws"][0]["name"] == "节制"))
    # R114b（D-160b）：牌阵位置含义 standing 覆盖——seed=42 n=3 位置名恰为
    # 过去/现在/未来（实测稳定），n=5 为五张牌阵。
    check("tarot.spread", client.post("/api/tarot", json={"seed": 42, "n": 3}),
          lambda j: [d.get("position") for d in j.get("draws", [])]
                    == ["过去", "现在", "未来"])
    check("tarot.spread5", client.post("/api/tarot", json={"seed": 42, "n": 5}),
          lambda j: [d.get("position") for d in j.get("draws", [])]
                    == ["现状", "助力", "阻碍", "过去", "结果"])
    # R121b（D-167b）：八字合婚纯坐标 standing 覆盖——固定两人生日 → 固定
    # 输出（1990-05-15 男 vs 1992-08-20 女 → 无冲合/日主相生/桃花不同）。
    check("hehun", client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
          "a_day": 15, "a_hour": 10, "a_gender": "男",
          "b_year": 1992, "b_month": 8, "b_day": 20, "b_hour": 14,
          "b_gender": "女"}),
          lambda j: (j.get("clash") is False and j.get("combine") is False
                     and j.get("day_wx_sheng") is True
                     and j.get("peach_same") is False
                     and j.get("render") and j.get("notes")))
    # R204b（D-257b）：天干五合 + 十神互见 standing 覆盖——固定两生日，
    # 庚辰×戊辰：无五合（gan_he=False）、庚见戊=偏印/戊见庚=食神。
    check("hehun.gan_he_gods", client.post("/api/hehun", json={"a_year": 1990,
          "a_month": 5, "a_day": 15, "a_hour": 10, "a_gender": "男",
          "b_year": 1992, "b_month": 8, "b_day": 20, "b_hour": 14,
          "b_gender": "女"}),
          lambda j: (j.get("gan_he") is False
                     and j.get("god_a_sees_b") == "偏印"
                     and j.get("god_b_sees_a") == "食神"))
    # R138b（D-184b）：大运冲合应期 standing 覆盖——固定两人生日 → 8 运
    # 全"合"（壬午×丁未 1997 … 己丑×庚子 2067）。
    check("hehun.dayun", client.post("/api/hehun", json={"a_year": 1990,
          "a_month": 5, "a_day": 15, "a_hour": 10, "a_gender": "男",
          "b_year": 1992, "b_month": 8, "b_day": 20, "b_hour": 14,
          "b_gender": "女"}),
          lambda j: (isinstance(j.get("dayun_hits"), list)
                     and len(j.get("dayun_hits", [])) == 8
                     and j.get("dayun_hits", [])[0]["relation"] == "合"
                     and j["dayun_hits"][0]["year_start"] == 1997))

    # ── 错误路径：400 参数校验 / 422 计算失败 / 404 不存在 ────────────
    _expect_400("err.addr.scheme",
                client.get("/api/addr", params={"scheme": "nonsense", "gua": 1}))
    _expect_400("err.liuyao.method",
                client.post("/api/liuyao", json={"method": "dice", "seed": 42}))
    # R141b（D-187b）：liuyao time 起卦 year/month/missing 三条 400 校验分支
    # standing 覆盖——err.liuyao.method 只测非法 method。实测 year=1800→400、
    # month=13→400、missing y/m/d→400。
    _expect_400("err.liuyao.time.year",
                client.post("/api/liuyao", json={"method": "time",
                                                 "year": 1800, "month": 5,
                                                 "day": 15, "hour": 10}))
    _expect_400("err.liuyao.time.month",
                client.post("/api/liuyao", json={"method": "time",
                                                 "year": 1990, "month": 13,
                                                 "day": 15, "hour": 10}))
    _expect_400("err.liuyao.time.missing",
                client.post("/api/liuyao", json={"method": "time", "hour": 10}))
    # R149b（D-195b）：liuyao time 起卦 day/hour 两条 400 校验分支 standing
    # 覆盖。实测 day=32→400、hour=24→400。
    _expect_400("err.liuyao.time.day",
                client.post("/api/liuyao", json={"method": "time",
                                                 "year": 1990, "month": 5,
                                                 "day": 32, "hour": 10}))
    _expect_400("err.liuyao.time.hour",
                client.post("/api/liuyao", json={"method": "time",
                                                 "year": 1990, "month": 5,
                                                 "day": 15, "hour": 24}))
    # R157b（D-203b）：liuyao time 公历转农历失败（solar_to_lunar ValueError
    # 捕获分支）400 校验 standing 覆盖——形状校验断言不构成运行时换算失败的
    # 覆盖。实测 1900-01-01 → 400 "公历转农历失败：… 早于农历表起点"。
    _expect_400("err.liuyao.time.convert_fail",
                client.post("/api/liuyao", json={"method": "time",
                                                 "year": 1900, "month": 1,
                                                 "day": 1, "hour": 10}))
    _expect_400("err.hehun.year",
                client.post("/api/hehun", json={"a_year": 1800, "a_month": 5,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    # R150b（D-196b）：hehun 乙侧 b_year/b_month/b_day 三条 400 校验分支
    # standing 覆盖——甲侧先抛 400 时乙侧代码路径从未执行。
    _expect_400("err.hehun.b_year",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1800, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    _expect_400("err.hehun.b_month",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1992, "b_month": 13,
                                                "b_day": 20, "b_hour": 14}))
    _expect_400("err.hehun.b_day",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 0, "b_hour": 14}))
    # R154b（D-200b）：hehun 甲侧 a_month/a_day/a_hour + 乙侧 b_hour 四条
    # 400 校验分支 standing 覆盖（year 断言不构成 month/day/hour 的覆盖）。
    _expect_400("err.hehun.a_month",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 13,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    _expect_400("err.hehun.a_day",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 0, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    _expect_400("err.hehun.a_hour",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 15, "a_hour": 24,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    _expect_400("err.hehun.b_hour",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                "a_day": 15, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 24}))
    # R164b（D-210b）：hehun 端点 422 排盘失败分支 standing 覆盖——err.hehun.*
    # 全为 400 参数校验断言，422 是 compute 抛异常路径（a 侧 1990-02-30）。
    _expect_422("err.hehun.paipan_fail",
                client.post("/api/hehun", json={"a_year": 1990, "a_month": 2,
                                                "a_day": 30, "a_hour": 10,
                                                "b_year": 1992, "b_month": 8,
                                                "b_day": 20, "b_hour": 14}))
    # R142b（D-188b）：huangli date 格式/year 范围/非法日期三条 400 校验分支
    # standing 覆盖。实测 garbage/1800-01-01/2026-02-30 均 400。
    _expect_400("err.huangli.date",
                client.get("/api/huangli", params={"date": "garbage"}))
    _expect_400("err.huangli.year",
                client.get("/api/huangli", params={"date": "1800-01-01"}))
    _expect_400("err.huangli.illegal",
                client.get("/api/huangli", params={"date": "2026-02-30"}))
    # R162b（D-208b）：huangli month/day 两条 400 校验分支 standing 覆盖——
    # date=2026-13-01 走 month 校验、date=2026-01-32 走 day 校验，与
    # R142b 已覆盖的三条不同分支。
    _expect_400("err.huangli.month",
                client.get("/api/huangli", params={"date": "2026-13-01"}))
    _expect_400("err.huangli.day",
                client.get("/api/huangli", params={"date": "2026-01-32"}))
    _expect_400("err.bazi.year",
                client.post("/api/bazi", json={"year": 1800, "month": 5,
                                               "day": 15, "hour": 10}))
    # R161b（D-207b）：bazi month/day/hour 三条 400 校验分支 standing 覆盖
    # ——err.bazi.year 只测年份范围。实测 month=13/day=32/hour=25 均 400。
    _expect_400("err.bazi.month",
                client.post("/api/bazi", json={"year": 1990, "month": 13,
                                               "day": 15, "hour": 10}))
    _expect_400("err.bazi.day",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 32, "hour": 10}))
    _expect_400("err.bazi.hour",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 25}))
    # R163b（D-209b）：bazi 端点 422 排盘失败分支 standing 覆盖——err.bazi.*
    # 全为 400 参数校验断言，422 是 compute 抛异常路径（1990-02-30 不存在）。
    _expect_422("err.bazi.paipan_fail",
                client.post("/api/bazi", json={"year": 1990, "month": 2,
                                               "day": 30, "hour": 10}))
    # R229c/k：①非法日期的 422 detail 不许漏英文异常原文（人话化钉扎）；
    # ②question max_length=200 的 pydantic 422 钉扎（bazi/liuyao 各一）。
    _r = client.post("/api/bazi", json={"year": 1990, "month": 2,
                                        "day": 30, "hour": 10})
    assert "这一天不存在" in str(_r.json().get("detail", "")), (
        "err.bazi.paipan_friendly", _r.status_code, _r.text[:200])
    ok.append("err.bazi.paipan_friendly")
    # pydantic 层校验（max_length）的 422 detail 是 FastAPI 约定的 list 形状，
    # 前端 _humanize422 已人话化——这里只钉状态码与非空 detail，不走
    # _expect_422（它要求 detail 为业务异常字符串）。
    for _n, _resp in (
        ("err.bazi.question_too_long",
         client.post("/api/bazi", json={"year": 1990, "month": 5,
                                        "day": 15, "hour": 10,
                                        "question": "啊" * 300})),
        ("err.liuyao.question_too_long",
         client.post("/api/liuyao", json={"method": "coins",
                                          "question": "啊" * 300})),
    ):
        assert _resp.status_code == 422 and _resp.json().get("detail"), (
            _n, _resp.status_code, _resp.text[:200])
        ok.append(_n)
    # R139b（D-185b）：bazi calendar_type/scope/gender 三条 400 校验分支
    # standing 覆盖——err.bazi.year 只测年份范围。
    _expect_400("err.bazi.calendar",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "garbage"}))
    _expect_400("err.bazi.scope",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "scope": "garbage"}))
    _expect_400("err.bazi.gender",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "gender": "中"}))
    # R150b（D-196b）：bazi lunar 三条 400 校验分支 standing 覆盖——lunar
    # 缺失 / lunar_month=13 / lunar_day=31。
    _expect_400("err.bazi.lunar_missing",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "lunar"}))
    _expect_400("err.bazi.lunar_month",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "lunar",
                                               "lunar_year": 1990,
                                               "lunar_month": 13,
                                               "lunar_day": 15}))
    _expect_400("err.bazi.lunar_day",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "lunar",
                                               "lunar_year": 1990,
                                               "lunar_month": 5,
                                               "lunar_day": 31}))
    # R156b（D-202b）：bazi lunar_year 超范围（lunar_to_solar ValueError 捕获
    # 分支）400 校验 standing 覆盖——形状校验不构成运行时换算失败的覆盖。
    _expect_400("err.bazi.lunar_year",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "lunar",
                                               "lunar_year": 1800,
                                               "lunar_month": 1,
                                               "lunar_day": 1}))
    # R228p：农历 2100 腊月换算到公历 2101 曾在此被误拒（旧检查钉的就是
    # 这个 false rejection）。下游干支/节气是天文算法不受表界限制，现按
    # YEAR_HI+1 放行——钉正向契约：2100-12-15 → 200 且日柱干支非空。
    check("bazi.lunar_spillover_2101",
          client.post("/api/bazi", json={"year": 1990, "month": 5,
                                         "day": 15, "hour": 10,
                                         "calendar_type": "lunar",
                                         "lunar_year": 2100,
                                         "lunar_month": 12,
                                         "lunar_day": 15}),
          lambda j: bool((j.get("paipan") or {}).get("render")))
    # R151b（D-197b）：bazi ask_hour / ask_date 格式 / range 缺失 / range 格式
    # R228p续3：年柱双口径 warn——正月生且立春前的盘须带提示。
    check("bazi.year_pillar.caliber_hint",
          client.post("/api/bazi", json={"year": 2009, "month": 2,
                                         "day": 1, "hour": 12,
                                         "gender": "男"}),
          lambda j: any("立春" in w and "正月初一" in w
                        for w in (j.get("paipan") or {}).get("warn", [])))
    # R228q：节气落在整点后段（20:36 立春）时，hour=20 输入须带边界
    # warn——旧 ±30min 判据把 20:31-20:59 的真实跨节出生静默放过。
    check("bazi.term_warn.hour_bucket",
          client.post("/api/bazi", json={"year": 2000, "month": 2,
                                         "day": 4, "hour": 20,
                                         "gender": "男"}),
          lambda j: any("立春" in w for w in
                        (j.get("paipan") or {}).get("warn", [])))
    # 四条 400 校验分支 standing 覆盖。
    _expect_400("err.bazi.ask_hour",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "ask_hour": 24}))
    _expect_400("err.bazi.ask_date",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "ask_date": "garbage"}))
    # R174b（D-221b）：bazi ask_date 年份越界分支 standing 覆盖——
    # err.bazi.ask_date 只测格式错误（"garbage"）。实测 1800-01-01 → 400。
    _expect_400("err.bazi.ask_date_year",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "ask_date": "1800-01-01"}))
    _expect_400("err.bazi.range_missing",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "scope": "range"}))
    _expect_400("err.bazi.range_format",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "scope": "range",
                                               "range_start": "garbage",
                                               "range_end": "2026-01-01"}))
    # R152b（D-198b）：bazi range 运行时值域校验（calc_range 内 ValueError
    # →400）两条 standing 覆盖——倒序（end 早于 start）、超 31 天。
    _expect_400("err.bazi.range_order",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "scope": "range",
                                               "range_start": "2026-02-01",
                                               "range_end": "2026-01-01"}))
    _expect_400("err.bazi.range_span",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "scope": "range",
                                               "range_start": "2026-01-01",
                                               "range_end": "2026-03-15"}))
    _expect_400("err.qiming.surname",
                client.post("/api/qiming", json={"surname": "张伟",
                                                 "year": 1990, "month": 5,
                                                 "day": 15, "hour": 10}))
    # R140b（D-186b）：qiming gender/year 两条 400 校验分支 standing 覆盖。
    _expect_400("err.qiming.gender",
                client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                 "month": 1, "day": 1,
                                                 "hour": 12, "gender": "中"}))
    _expect_400("err.qiming.year",
                client.post("/api/qiming", json={"surname": "李", "year": 1800,
                                                 "month": 1, "day": 1,
                                                 "hour": 12, "gender": "男"}))
    # R149b（D-195b）：qiming month/day/hour 三条 400 校验分支 standing 覆盖。
    _expect_400("err.qiming.month",
                client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                 "month": 13, "day": 1,
                                                 "hour": 12, "gender": "男"}))
    _expect_400("err.qiming.day",
                client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                 "month": 5, "day": 0,
                                                 "hour": 12, "gender": "男"}))
    _expect_400("err.qiming.hour",
                client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                 "month": 5, "day": 15,
                                                 "hour": 24, "gender": "男"}))
    # R152b（D-198b）：qiming 计算失败分支（name_candidates 抛异常→400）
    # standing 覆盖。实测 month=2/day=30（不存在的日期）→ 400。
    _expect_400("err.qiming.calc_fail",
                client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                 "month": 2, "day": 30,
                                                 "hour": 12, "gender": "男"}))
    # R143b（D-189b）：taohua year/gender/calendar 三条 400 校验分支 standing
    # 覆盖——taohua 复用 BaziRequest 校验，但 err.bazi.* 只覆盖 bazi 端点，
    # 独立端点需独立断言（若 taohua 误移除 validate_ranges() 调用则不可见）。
    _expect_400("err.taohua.year",
                client.post("/api/taohua", json={"year": 1800, "month": 5,
                                                 "day": 15, "hour": 10,
                                                 "gender": "男"}))
    _expect_400("err.taohua.gender",
                client.post("/api/taohua", json={"year": 1990, "month": 5,
                                                 "day": 15, "hour": 10,
                                                 "gender": "中"}))
    _expect_400("err.taohua.calendar",
                client.post("/api/taohua", json={"year": 1990, "month": 5,
                                                 "day": 15, "hour": 10,
                                                 "gender": "男",
                                                 "calendar_type": "garbage"}))
    # R164b（D-210b）：taohua 端点 422 排盘失败分支 standing 覆盖。
    _expect_422("err.taohua.paipan_fail",
                client.post("/api/taohua", json={"year": 1990, "month": 2,
                                                 "day": 30, "hour": 10,
                                                 "gender": "男"}))
    # R144b（D-190b）：compare_works/concept/research 三条 400 校验分支
    # standing 覆盖。
    _expect_400("err.compare_works.missing",
                client.get("/api/compare_works",
                           params={"work_b": "KR5c0126", "q": "無爲"}))
    # R171b（D-216b）：/api/compare_works q 过长分支 standing 断言。
    # 实测 q="甲"*201 → 400 "查询词过长（≤200 字符）"。
    _expect_400("err.compare_works.q_too_long",
                client.get("/api/compare_works",
                           params={"work_a": "KR5c0057", "work_b": "KR5c0126",
                                   "q": "甲" * 201}))
    _expect_400("err.concept.empty", client.get("/api/concept", params={"q": ""}))
    _expect_400("err.research.max_addresses",
                client.get("/api/research", params={"q": "潛龍勿用",
                                                    "max_addresses": 0}))
    # R145b（D-191b）：search q 为空校验 standing 覆盖。实测 q="" → 400 +
    # detail "查询词不能为空——检索需要查询词；找某个地址请用 /api/addr"。
    _expect_400("err.search.empty", client.get("/api/search", params={"q": ""}))
    # R146b（D-192b）：concept/research q 过长校验 standing 覆盖。
    _expect_400("err.concept.too_long",
                client.get("/api/concept", params={"q": "甲" * 201}))
    _expect_400("err.research.too_long",
                client.get("/api/research", params={"q": "乙" * 201,
                                                    "max_addresses": 2}))
    # R153b（D-199b）：research/compare_works q 空校验 standing 覆盖。
    _expect_400("err.research.empty",
                client.get("/api/research", params={"q": "",
                                                    "max_addresses": 2}))
    _expect_400("err.compare_works.q_empty",
                client.get("/api/compare_works",
                           params={"work_a": "KR1a0001", "work_b": "KR1a0032",
                                   "q": ""}))
    # R147b（D-193b）：compare gua 范围校验 standing 覆盖。实测 gua=99 → 400。
    _expect_400("err.compare.gua_range",
                client.get("/api/compare", params={"gua": 99, "yao": "九二"}))
    # R148b（D-194b）：addr zhouyi 无 gua / bookstudy structure/chapter
    # work_id 为空三条 400 校验分支 standing 覆盖。
    _expect_400("err.addr.zhouyi.no_gua",
                client.get("/api/addr", params={"scheme": "zhouyi"}))
    _expect_400("err.bookstudy.structure.empty",
                client.get("/api/bookstudy/structure", params={"work_id": ""}))
    _expect_400("err.bookstudy.chapter.empty",
                client.get("/api/bookstudy/chapter",
                           params={"work_id": "", "scheme": "zhouyi",
                                   "addr1": 1}))
    # R152b（D-198b）：bookstudy chapter 的 scheme 空校验 standing 覆盖。
    _expect_400("err.bookstudy.chapter.scheme",
                client.get("/api/bookstudy/chapter",
                           params={"work_id": "KR1a0001", "scheme": "",
                                   "addr1": 1}))
    # R159b（D-205b）：/api/threads 非法 kind 400 校验 standing 覆盖——
    # kind=bogus 此前触发 knowledge.py INSERT 的 sqlite3.IntegrityError
    # （DB CHECK 约束）未被捕获 → 500 崩溃（真实 bug）。修复后断言 400。
    _expect_400("err.threads.kind",
                client.post("/api/threads", json={"kind": "bogus",
                                                  "claim": "测试",
                                                  "method": "probe"}))
    # R229n（R6-#2）：校验失败不得留孤儿 thread+turn——校验前置后，
    # kind=bogus 与「断言型无证据」都应在开线程之前被拒。
    from guji.knowledge import KnowledgeBase as _KBt
    _kbt = _KBt(KNOWLEDGE_DB)
    try:
        _tc0 = _kbt.db.execute("SELECT count(*) c FROM thread").fetchone()["c"]
        _bad = client.post("/api/threads", json={"kind": "summary",
                                                 "claim": "无证据断言",
                                                 "method": "probe"})
        assert _bad.status_code == 400, ("err.threads.no_evidence",
                                         _bad.status_code)
        ok.append("err.threads.no_evidence")
        _tc1 = _kbt.db.execute("SELECT count(*) c FROM thread").fetchone()["c"]
    finally:
        _kbt.close()
    assert _tc1 == _tc0, ("err.threads.orphan_free", _tc0, _tc1)
    ok.append("err.threads.orphan_free")
    # R229n（R6-#4）：evidence ≤64 写放大护栏——100 条须被 pydantic 422 拒。
    _ev_over = client.post("/api/threads", json={
        "kind": "refusal", "claim": "x", "method": "probe",
        "evidence": [{"work_id": "", "quote": "q"}] * 100})
    assert _ev_over.status_code == 422, ("err.threads.evidence_too_many",
                                         _ev_over.status_code)
    ok.append("err.threads.evidence_too_many")

    # ── 核心研究/历史/线程/健康端点（R54b）：全部确定性、无写副作用 ──
    # external/news 依赖代理与网络，明确不进 standing 自测（D-100b）。
    check("research", client.get("/api/research", params={"q": "潛龍勿用",
          "max_addresses": 2}),
          lambda j: j.get("evidence") and j.get("steps"))
    # R132b（D-178b）：research 的 allow_damaged 放行分支 standing 覆盖。
    # 实测 allow_damaged=true → 200 + refused=False + evidence 非空。
    check("research.allow_damaged", client.get("/api/research",
          params={"q": "潛龍勿用", "max_addresses": 2, "allow_damaged": True}),
          lambda j: j.get("refused") is False and bool(j.get("evidence")))
    # R170b（D-217b）：/api/ask q 校验两条分支——q="" → 422（Pydantic
    # min_length），q="   " → 400 "查询词不能为空"（strip() 后空）。
    _ask_empty = client.post("/api/ask", json={"q": "   ", "max_addresses": 2})
    assert _ask_empty.status_code == 400, ("err.ask.q_empty",
                                           _ask_empty.status_code,
                                           _ask_empty.text[:200])
    assert _ask_empty.json().get("detail") == "查询词不能为空", \
        ("err.ask.q_empty", _ask_empty.text[:200])
    ok.append("err.ask.q_empty")
    _ask_too_short = client.post("/api/ask", json={"q": "", "max_addresses": 2})
    assert _ask_too_short.status_code == 422, ("err.ask.q_too_short",
                                               _ask_too_short.status_code,
                                               _ask_too_short.text[:200])
    ok.append("err.ask.q_too_short")
    # R176b（D-223b）：/api/ask q 过长分支 standing 覆盖（Pydantic
    # max_length=200）。实测 q="甲"*201 → 422 "string_too_long"。
    _ask_too_long = client.post("/api/ask", json={"q": "甲" * 201,
                                                 "max_addresses": 2})
    assert _ask_too_long.status_code == 422, ("err.ask.q_too_long",
                                              _ask_too_long.status_code,
                                              _ask_too_long.text[:200])
    ok.append("err.ask.q_too_long")
    # R177b（D-225b）：/api/ask max_addresses 边界 standing 覆盖——Pydantic
    # Field(ge=1, le=6) 两条 422 分支。
    _ask_max_low = client.post("/api/ask", json={"q": "潛龍勿用",
                                                "max_addresses": 0})
    assert _ask_max_low.status_code == 422, ("err.ask.max_addresses_low",
                                             _ask_max_low.status_code,
                                             _ask_max_low.text[:200])
    ok.append("err.ask.max_addresses_low")
    _ask_max_high = client.post("/api/ask", json={"q": "潛龍勿用",
                                                 "max_addresses": 7})
    assert _ask_max_high.status_code == 422, ("err.ask.max_addresses_high",
                                              _ask_max_high.status_code,
                                              _ask_max_high.text[:200])
    ok.append("err.ask.max_addresses_high")
    check("ask", client.post("/api/ask", json={"q": "潛龍勿用",
          "max_addresses": 2}),
          lambda j: j.get("evidence_citations"))
    # R178b（D-226b）：ask 的解读字段结构 standing 覆盖（原 ask.llm.shape）。
    # 原断言 llm 为 None 或含 text+model 的 dict——LLM 移除后改断言确定性
    # interpretation：ok/engine/sections/text 齐全，且**同输入两次逐字相同**。
    _a1 = client.post("/api/ask", json={"q": "潛龍勿用",
                                        "max_addresses": 2}).json()
    _a2 = client.post("/api/ask", json={"q": "潛龍勿用",
                                        "max_addresses": 2}).json()
    _ai = _a1.get("interpretation")
    assert isinstance(_ai, dict) and _ai.get("ok") is True, _ai
    assert "无 LLM" in _ai.get("engine", ""), _ai
    assert _ai.get("sections") and _ai.get("citations"), _ai
    assert _ai["text"] == _a2["interpretation"]["text"], \
        "ask interpretation must be deterministic"
    ok.append("ask.interpretation.shape")
    # R219b（P0-4 用户裁决）：history / history.detail / history.detail.missing
    # 三条断言随 /api/history* 端点删除（历史记录功能整体移除）。改为**反向
    # 断言**：三个端点必须 404（路由已注销），防止端点被悄悄恢复。
    for _hp, _hm in (("/api/history", "GET"), ("/api/history/1", "GET"),
                     ("/api/history/1", "DELETE")):
        _hr = (client.get(_hp) if _hm == "GET" else client.delete(_hp))
        assert _hr.status_code == 404, ("history.removed", _hm, _hp,
                                        _hr.status_code)
    ok.append("history.removed")
    check("threads.detail", client.get("/api/threads/1"),
          lambda j: "claims" in j and "turns" in j)
    # R169b（D-215b）：threads.detail 404 拒绝路径 standing 覆盖。
    # 实测 tid=99999 → 404 + detail "线程 99999 不存在或暂无记录"。
    _td_miss = client.get("/api/threads/99999")
    assert _td_miss.status_code == 404, ("threads.detail.missing",
                                         _td_miss.status_code,
                                         _td_miss.text[:200])
    assert _td_miss.json().get("detail"), ("threads.detail.missing",
                                           _td_miss.text[:200])
    ok.append("threads.detail.missing")
    check("health", client.get("/api/health"), lambda j: j.get("ok") is True)
    # 首页 `/`（R61b）：单页前端入口，返回 HTML 非 JSON——单独断言状态码 +
    # content-type + 关键标记。
    home = client.get("/")
    assert home.status_code == 200, ("home", home.status_code, home.text[:200])
    assert "text/html" in (home.headers.get("content-type") or ""), \
        "home must be HTML"
    assert "<html" in home.text.lower(), "home must contain <html>"
    # R228t：安全响应头钉扎——中间件丢失会让 nosniff/DENY 静默消失
    for _h, _v in (("x-content-type-options", "nosniff"),
                   ("x-frame-options", "DENY"),
                   ("referrer-policy", "no-referrer")):
        assert home.headers.get(_h) == _v, f"missing header {_h}"
    ok.append("home")
    ok.append("sec.headers")
    # R178b（D-227b）：静态资源挂载 standing 覆盖——前端拆出 app.js/styles.css
    # 后，`/static/*` 是首屏必需资源；若 StaticFiles 挂载点丢失或文件被漏拷，
    # 首页仍返回 200 但页面全白（无样式无交互），selftest 全绿看不见。
    for _name, _ctype in (("styles.css", "css"), ("app.js", "javascript")):
        _st = client.get(f"/static/{_name}")
        assert _st.status_code == 200, (f"static.{_name}", _st.status_code)
        assert _ctype in (_st.headers.get("content-type") or ""), \
            (f"static.{_name}", _st.headers.get("content-type"))
        assert len(_st.content) > 1000, (f"static.{_name}", len(_st.content))
        ok.append(f"static.{_name}")

    # R194b（specs/007 首页 IA）：功能卡三簇语义分组——入口不减（8 张）、
    # 簇内序固定（八字族相邻→抽问族→黄历殿后，读书独立成簇）、
    # 双人意图的合婚与桃花相邻。只增不减：新名字自动入 regress 基线。
    # R200b（US3 方案①）：首页五张直达卡 + 排盘视图「相关功能」区三卡。
    # R206b（specs/009 US2 二剪）：首页五卡改小满刚需——tarot→bazi→taohua→
    # hehun→huangli（桃花/合婚提回首页）；六爻/读书/起名收进「高级入口」
    # pro-drawer 抽屉（默认折叠，功能零删除）；研究型关键词不得出现在
    # home-main 可见区（判据 a：检索/比对/书目/线程/书 ID 计数=0）。
    import re as _re
    _home_seg = home.text.split('id="view-divine"')[0]
    _cards = _re.findall(r'class="func-card[^"]*" data-view="([a-z]+)"', _home_seg)
    assert len(_cards) == 9, ("home.ia.count", len(_cards), _cards)  # 6 直达+3 抽屉（D-005 星座；2026-08-28 水墨改版新增 history 卡）
    # R208b：read 卡移除（用户裁决不提供读书渠道）→ 抽屉剩 liuyao/qiming
    assert _cards[:5] == ["tarot", "bazi", "taohua", "hehun", "huangli"], \
        ("home.ia.order", _cards)
    assert _cards[5:] == ["xingzuo", "history", "liuyao", "qiming"], \
        ("home.ia.drawer", _cards)
    # 判据 a：默认视线零研究型元素（抽屉 summary 文字除外——它本身是入口名）
    _visible = _home_seg.split('id="proDrawer"')[0]
    for _kw in ("检索", "比对", "书目", "研究线程", "书 ID", "编址"):
        assert _kw not in _visible, ("home.ia.no-research-kw", _kw)
    # 高级抽屉存在且默认折叠（无 open 属性）
    assert '<details class="pro-drawer" id="proDrawer">' in home.text \
        and 'pro-drawer" id="proDrawer" open' not in home.text, \
        ("home.ia.drawer-closed",)
    ok.append("home.ia")

    # threads POST：写一条带**真实引文**的 claim → 回读 → 清理
    # （R34b 教训：绝不在真实库里留测试行）
    from guji.knowledge import KnowledgeBase
    from guji.variants import fold, segment_cjk

    post = client.post("/api/threads", json={
        "kind": "summary",
        "claim": "web selftest: 無爲在老子中的可核验引文",
        "method": "app-selftest", "thread_id": 1,
        "evidence": [{"work_id": "KR5c0057", "file": "KR5c0057_043.txt",
                      "quote": "第四十三章 天下之至柔",
                      "page_anchor": "KR5c0057_tls_043-1a"}]})
    assert post.status_code == 200, post.text
    did = post.json()["derived_id"]
    assert post.json()["thread_id"] == 1
    detail = client.get("/api/threads/1").json()
    assert any(c["id"] == did and "無爲在老子中的可核验引文" in c["claim"]
               for c in detail["claims"]), \
        "thread readback must contain the bound claim"
    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        row = kb.db.execute("SELECT claim FROM derived WHERE id=?",
                            (did,)).fetchone()
        if row is not None:
            seg = segment_cjk(fold(row["claim"]))
            kb.db.execute("INSERT INTO derived_fts(derived_fts,rowid,seg) "
                          "VALUES('delete',?,?)", (did, seg))
            kb.db.execute("DELETE FROM evidence WHERE derived_id=?", (did,))
            kb.db.execute("DELETE FROM derived WHERE id=?", (did,))
            kb.db.commit()
    finally:
        kb.close()
    ok.append("threads.post+readback+cleanup")

    # ── 知命产品化 API 自测（R002） ────────────────────────────────
    check("daily", client.get("/api/daily"),
          lambda j: (j.get("level") in ("吉", "平", "凶")
                     and j.get("date") and "noble" in j))
    # R195b（B-017）：noble 语义 = 当日日干的天乙贵人（地支列表，1–2 个，
    # 「/」连接），不再是「今年的生肖」。与黄历 guiren 同算法互验。
    def _daily_noble_ok(j):
        from guji import huangli as _hl
        from datetime import date as _date, datetime as _dt
        _d = _date.fromisoformat(j["date"])
        _want = "/".join(_hl.guiren(_dt(_d.year, _d.month, _d.day, 12)))
        return j.get("noble") == _want and j.get("noble") not in ("", None)
    check("daily.noble.guiren", client.get("/api/daily"), _daily_noble_ok)
    check("widget", client.get("/api/widget"),
          lambda j: (isinstance(j.get("modules"), list)
                     and len(j["modules"]) >= 6
                     and all(m.get("icon") and m.get("title")
                             for m in j["modules"])))
    check("tarot.draw", client.post("/api/tarot/draw", json={"n": 1}),
          lambda j: (j.get("card") and j["card"].get("name")
                     and j["card"].get("meaning")))
    # R178b（D-228b）：tarot.draw 顶层键集合 standing 断言——重构中该端点
    # 一度多返回一个 `draws` 键（与 /api/tarot 的牌面重复，同一份数据两处
    # 存放）。此处钉死顶层契约，抓**未登记**的响应形状扩张（tarot.draw check
    # 只断言 card 内部字段，看不见多余键）。
    # R182b（004 M1）：`warm` 是 spec 004 登记的 additive 新键，加入白名单。
    # 用白名单而非删掉断言——未登记的键仍会被抓到，这条断言的价值正在于
    # 「新增顶层键必须先在此登记」，等于强制走一次 review。
    _td = client.post("/api/tarot/draw", json={"seed": 42, "n": 1}).json()
    assert set(_td) == {"card", "interpretation", "warm"}, sorted(_td)
    assert isinstance(_td["interpretation"], dict), type(_td["interpretation"])
    assert isinstance(_td["warm"], dict), type(_td["warm"])
    ok.append("tarot.draw.keys")
    # R178b（D-229b）：/api/daily 的 date **查询参数**生效 + 非法日期 400。
    # 重构前 date 声明为 GET 的请求体模型，`?date=…` 被完全忽略（永远返回
    # 今天）——那是 bug。改为查询参数后补两条断言：指定日期须被回显（否则
    # 参数又被吃掉了），非法日期须 400（否则 daily_cache 会落脏行）。
    check("daily.date", client.get("/api/daily", params={"date": "2026-03-03"}),
          lambda j: j.get("date") == "2026-03-03")
    # R229n（R6-#1）：daily.date 检查往 daily_cache 落了 2026-03-03 测试行
    # ——与 threads 清理同纪律（写端点自测不得污染真实库）。
    from guji.knowledge import KnowledgeBase as _KB
    _kbc = _KB(KNOWLEDGE_DB)
    try:
        _kbc.db.execute("DELETE FROM daily_cache WHERE date='2026-03-03'")
        _kbc.db.commit()
    finally:
        _kbc.close()
    _expect_400("err.daily.date",
                client.get("/api/daily", params={"date": "garbage"}))
    # R229n（R6-#1/#5）：本套件在 BOOKS_PAIPAN_HISTORY_DISABLE=1 下跑——
    # 顺手钉死禁用语义：list→空表，get/export/delete→404（此前只查 list）。
    check("paipan.disabled.list", client.get("/api/paipan/history"),
          lambda j: j.get("total") == 0 and j.get("items") == [])
    for _pp in ("/api/paipan/history/1", "/api/paipan/history/export"):
        _pr = client.get(_pp)
        assert _pr.status_code == 404, ("paipan.disabled", _pp,
                                        _pr.status_code)
    _pd = client.delete("/api/paipan/history/1")
    assert _pd.status_code == 404, ("paipan.disabled.delete", _pd.status_code)
    ok.append("paipan.disabled.read")
    check("share.bazi", client.get("/api/share/bazi/1"),
          lambda j: (j.get("title") and j.get("content")
                     and j.get("image_color")))
    check("user.prefs", client.get("/api/user/prefs"),
          lambda j: (j.get("theme") and isinstance(j.get("favorites"), list)))
    # R178b（D-230b）：LLM 层已整体移除——断言它**回不来**。`guji.llm_reader`
    # 必须不可导入，且响应里不得再出现 llm/llm_out/use_llm 字段（若哪轮把
    # 生成式解读悄悄接回来，此处立刻红）。
    try:
        __import__("guji.llm_reader")
        raise AssertionError("guji.llm_reader must not exist after R178b")
    except ModuleNotFoundError:
        ok.append("llm.removed")
    for _path, _payload in (("/api/bazi", {"year": 1990, "month": 5, "day": 15,
                                           "hour": 10, "gender": "男"}),
                            ("/api/liuyao", {"method": "coins", "seed": 42})):
        _body = client.post(_path, json=_payload).json()
        assert "llm" not in _body and "llm_out" not in _body, \
            (_path, sorted(_body))
        assert isinstance(_body.get("interpretation"), dict), _path
    ok.append("llm.fields.absent")
    # R191b（T1.5 补建，B-014/D-251b）：AI 润色**异步层** standing 断言。
    # 闸门环境 DISABLE=1：端点响应必须无 ai_task_id 键（判据 11，与旧版
    # 逐字节一致）；异步机制本体用显式 config + 打桩 transport 离线验证
    # （显式 config 绕过总开关，零外网、确定性延迟）。
    import time as _time
    from guji import llm_polish as _L

    _b = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男"}).json()
    assert "ai_task_id" not in _b and _b.get("ai_polish") is None, sorted(_b)
    ok.append("ai.async.disabled.no_task_id")

    def _stub_ok(payload, headers, url, timeout):
        _time.sleep(0.2)
        return {"choices": [{"message": {"content":
                "打桩文本：温柔的离线验收句，用于异步链路自测。"}}]}

    _cfg = dict(_L._DEFAULTS, api_key="k")
    _tid = _L.spawn_ai_task(["四柱：戊寅"], "感情？", config=_cfg,
                            _transport=_stub_ok)
    assert _tid, "spawn_ai_task 应返回任务 id"
    _st = None
    _t0 = _time.time()
    while _time.time() - _t0 < 5:
        _st = _L.ai_task_status(_tid)
        assert _st is not None, "任务在 TTL 内不得丢失"
        if _st["status"] != "pending":
            break
        _time.sleep(0.05)
    assert _st["status"] == "done" and _st["text"], _st
    ok.append("ai.async.task.roundtrip")

    def _stub_boom(payload, headers, url, timeout):
        raise OSError("selftest stub down")

    _tid2 = _L.spawn_ai_task(["四柱：戊寅"], config=_cfg,
                             _transport=_stub_boom)
    _st2 = None
    _t0 = _time.time()
    while _time.time() - _t0 < 5:
        _st2 = _L.ai_task_status(_tid2)
        if _st2["status"] != "pending":
            break
        _time.sleep(0.05)
    assert _st2["status"] == "failed" and not _st2["text"], _st2
    ok.append("ai.async.task.failed.degrade")

    _r404 = client.get("/api/ai/selftest-nonexistent")
    assert _r404.status_code == 404, _r404.status_code
    ok.append("ai.endpoint.unknown.404")
    # R206b（specs/009 US1；D-259b）：AI 陪伴层 standing 断言。
    # (1) DISABLE=1 下 /api/chat 响应零 chat_task_id 键（additive 判据 a，
    #     与四端点 no_task_id 同口径）；(2) 校验 400；(3) 危机关键词 →
    #   固定转介、输出禁语 → 固定兜底（判据 b，显式 config+打桩 transport
    #   离线验证）；(4) 轮数上限温和收尾（判据 c）。
    from guji import llm_polish as _LC
    _rc = client.post("/api/chat", json={"session_id": "st", "message": "最近好累"})
    assert _rc.status_code == 200 and "chat_task_id" not in _rc.json(), \
        sorted(_rc.json())
    ok.append("chat.disabled.no_task_id")
    _rc2 = client.post("/api/chat", json={"session_id": "", "message": "x"})
    assert _rc2.status_code == 400, _rc2.status_code
    _rc3 = client.post("/api/chat", json={"session_id": "st", "message": "x" * 501})
    assert _rc3.status_code == 400, _rc3.status_code
    ok.append("chat.validation.400")
    _ccfg = {"base_url": "http://127.0.0.1:1", "api_key": "x", "model": "m"}
    _crisis = _LC.chat("st-crisis", "不想活了", config=_ccfg)
    assert _crisis and "专业人士" in _crisis, _crisis
    ok.append("chat.crisis.refusal")
    _banned = _LC.chat(
        "st-banned", "他为什么不回我消息",
        _transport=lambda p, h, u, t: {"choices": [{"message": {
            "content": "你应该直接分手，别理他了"}}]}, config=_ccfg)
    assert _banned and "你自己舒服" in _banned, _banned
    ok.append("chat.banned.fallback")
    # R229t：sid 洪泛防护——_CHAT_MAX_SESSIONS 封顶后 GC 逐最旧会话，
    # 海量唯一 session_id 不能撑爆内存。直接灌表测 GC（不走 API，
    # 否则每个会话要真发请求）。危机词短路返回不产生 LLM 调用。
    _L._chat_sessions.clear()
    _L._chat_call_locks.clear()
    import time as _tm
    _t0 = _tm.monotonic()
    try:
        for _i in range(_L._CHAT_MAX_SESSIONS + 40):
            # updated 必须新鲜（否则被 TTL 先扫掉）但有序——flood-0 最旧
            _L._chat_sessions[f"flood-{_i}"] = {
                "messages": [], "updated": _t0 - 900 + _i * 0.001}
        _L._gc_chat_sessions()
        assert len(_L._chat_sessions) <= _L._CHAT_MAX_SESSIONS, \
            len(_L._chat_sessions)
        # 最旧 40 个应已被逐出，最新的还在
        assert "flood-0" not in _L._chat_sessions
        assert f"flood-{_L._CHAT_MAX_SESSIONS + 39}" in _L._chat_sessions
    finally:
        _L._chat_sessions.clear()
        _L._chat_call_locks.clear()
    ok.append("chat.sessions.cap")
    # R227b（用户反馈「不能照本宣科」）：黄历类提问后端先算「黄历判定」。
    # 判据：① 事项词命中 → facts 含当日宜忌 + 判定句（含「宜」「忌」或「中性」）；
    # ② 没列入宜忌的事项须按中性口径回（「不是不支持」），不许只回「没提」；
    # ③ 非黄历话题 → []（零扰动）。固定 now 保确定性。
    from web import services as _svc
    from datetime import datetime as _dt
    _hf = _svc.chat_huangli_facts("今天适合出行吗", now=_dt(2026, 9, 19))
    # R228w：事实行带用户原词——「今天（date）的黄历：…」让 LLM 能对上
    # 「下周三」=9/23 而不是自己换算出错日期。
    assert _hf and any("的黄历" in f and "2026-09-19" in f for f in _hf), _hf
    assert any("黄历判定" in f for f in _hf), _hf
    _hf2 = _svc.chat_huangli_facts("明天能搬家不", now=_dt(2026, 9, 19))
    assert _hf2 and any("中性" in f or "宜「" in f for f in _hf2), _hf2
    _hf3 = _svc.chat_huangli_facts("他为什么不回我消息", now=_dt(2026, 9, 19))
    assert _hf3 == [], _hf3
    ok.append("chat.huangli_facts")
    # R228r/s（chat-flow 审查轨）：词表扩展 + 相对日 + 消歧钉针。
    # ① 下周X：周六问「下周五」→ 判 9/25 而非今天（2026-09-19 是周六）。
    _hf4 = _svc.chat_huangli_facts("下周五签约可以吗", now=_dt(2026, 9, 19))
    assert _hf4 and any("2026-09-25" in f for f in _hf4), _hf4
    # ② 长键消歧：「解除合同」必须走解除方向，不许被「合同」抢到立券。
    _hf5 = _svc.chat_huangli_facts("明天要解除合同合适吗", now=_dt(2026, 9, 19))
    assert _hf5 and any("解除合同" in f and "立券" not in f for f in _hf5), _hf5
    # ③ 新事项词接住：理发→冠笄、宠物→进人口、手术→求医。
    for _m, _t in (("周末理发好吗", "理发"), ("我想养猫可以吗", "养猫"),
                   ("明天做手术行吗", "手术")):
        _hf6 = _svc.chat_huangli_facts(_m, now=_dt(2026, 9, 19))
        assert _hf6 and any(_t in f and "黄历判定" in f for f in _hf6), (_m, _hf6)
    # ④ R228w：非今日提问的中性卡说「原词（日期）」——「明天（2026-09-20）」
    # 比「那天」更精确，也让 LLM 能把用户的说法锚到正确日期。
    _hf7 = _svc.chat_huangli_facts("明天适合聚餐吗", now=_dt(2026, 9, 19))
    assert _hf7 and any("明天（2026-09-20）" in f for f in _hf7), _hf7
    # ⑤ R229v（真机 eval 抓到）：已过去的日子判定句本体必须带「已过去」
    # + 复盘指令——只靠宜忌行尾巴的括号模型会漏看（9/18 宜面试被答成
    # 「周五冲一把」）。
    _hf8 = _svc.chat_huangli_facts("这周五去面试好不好", now=_dt(2026, 9, 19))
    assert _hf8 and any("已过去" in f and "黄历判定" in f for f in _hf8), _hf8
    assert any("复盘" in f for f in _hf8), _hf8
    ok.append("chat.facts.dates_vocab")
    # R227b-fix（端到端审查抓到）：问一嘴输入的日期词必须参与判定——
    # 「明天适合出行吗」不许剥掉日期词后拿当前显示日充数答「今天…」。
    # 静态钉扎：抽日词函数存在、判定卡收到日词参数（不写死「今天」）。
    _appsrc2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "static", "app.js"), encoding="utf-8").read()
    assert "_hlDayOffset(q)" in _appsrc2 and "_HL.dayWord" in _appsrc2, \
        "问一嘴日期词偏移：_hlDayOffset/_HL.dayWord 必须在 app.js 里"
    assert ", _dayWord)" in _appsrc2, \
        "_hlVerdictHtml 调用必须带日词参数——否则判定卡写死「今天」"
    ok.append("frontend.hl_ask_dayoffset")
    # R179b（D-232b，审查轨 R118a-01/R118a-02）：`[object Object]` 静态闸门。
    # 两条 MAJOR 同一根因：前端渲染只分「数组」与「其他→esc(v)」两支，漏了
    # v 是 dict 的情形，JS `String({..})` 恒为 "[object Object]"。受害字段是
    # /api/bazi 的 five_elements+day_luck 与 /api/huangli 的 pengzu。
    # 前端已改为 fmtScalar() 递归展开，此处钉死两件事：
    #   (1) app.js 里不得再出现「把值直接 esc 而不判 object」的写法——用
    #       fmtScalar 覆盖率代理：所有 esc(v)/esc(item) 形态必须经 fmtScalar；
    #   (2) 真实响应里这三个字段确实是 dict（否则断言 (1) 就失去意义）。
    _bz = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男"}).json()
    assert isinstance(_bz["calc"]["five_elements"], dict), "five_elements must be dict"
    assert isinstance(_bz["calc"]["day_luck"], dict), "day_luck must be dict"
    # C-001：黄历移除文言展示（建除/二十八宿/彭祖百忌），改为年轻化宜忌词库
    _hl = client.get("/api/huangli", params={"date": "2026-08-19"}).json()
    assert isinstance(_hl["yi"], list) and isinstance(_hl["ji"], list), "yi/ji must be lists"
    import os as _os
    import re as _re

    _js = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "static", "app.js"), encoding="utf-8").read()
    # 裸 esc(v) / esc(item) / esc(iv)：这三个变量名在 renderCalc 里承载
    # 「可能是 dict」的值，必须经 fmtScalar 包一层。
    _bare = _re.findall(r"esc\((?:v|item|iv)\)", _js)
    assert not _bare, ("object-render guard: 发现裸 esc() 未过 fmtScalar", _bare)
    assert "function fmtScalar" in _js, "fmtScalar renderer must exist"
    ok.append("frontend.no_object_object")

    # R228h：on('id') 静态对表——on() 注册的 id 必须能在 index.html 或
    # app.js 的动态模板里找到，否则是死绑定（审查轨 ui_smoke BUTTON_CASES
    # 只能覆盖手列的按钮；这条静态闸把整个 on() 注册面一次兜住）。
    # 注意 `\bon\(` 词边界：没有它 `renderDecoration('bazi')` 会被误算。
    _html = open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                               "static", "index.html"), encoding="utf-8").read()
    _dom_ids = set(_re.findall(r'id="([\w-]+)"', _html)) | \
        set(_re.findall(r'id="([\w-]+)"', _js))
    _dead = sorted(set(_re.findall(r"(?<![\w.])on\('(\w+)'", _js)) - _dom_ids)
    assert not _dead, ("on() 死绑定：id 在 index.html 与 app.js 模板中均不存在",
                       _dead)
    ok.append("frontend.on_wiring")

    # ── 004 warm 视图（R182b，M1）：判据 1/2/5/6/7/8/15 的 selftest 侧覆盖 ──
    # 完整判据由 web/check_warm_voice.py 把关（含术语表/禁用词表与阳性对照）；
    # 这里放**端点契约级**断言：warm 键存在、结构齐、确定性、引文复用。
    _wb = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                        "hour": 14, "gender": "女",
                                        "question": "感情运怎么样？"}).json()
    _wb2 = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                         "hour": 14, "gender": "女",
                                         "question": "感情运怎么样？"}).json()
    _w = _wb.get("warm")
    assert isinstance(_w, dict) and _w.get("mode") == "warm", _w
    ok.append("warm.bazi.present")
    # 判据 2：一句话 ≤20 字且非空
    assert _w["one_liner"] and len(_w["one_liner"]) <= 20, _w["one_liner"]
    ok.append("warm.one_liner.len")
    # 判据 1：有提问时 reply 首行须回应该提问（不是坐标/纳音）
    assert _w["reply"] and "感情" in _w["reply"][0], _w["reply"][:1]
    ok.append("warm.reply.answers_question")
    # 判据 7：免责含「仅供娱乐」，且**不是最后一个字段**（badge 在 details 前）
    assert "仅供娱乐" in _w["badge"], _w["badge"]
    assert list(_w).index("badge") < list(_w).index("details"), list(_w)
    ok.append("warm.badge.not_last")
    # 判据 15：citations 逐字节复用 interpretation，不另生成
    assert _w["citations"] == (_wb["interpretation"].get("citations") or []), \
        "warm.citations 必须与 interpretation 逐字节相同"
    ok.append("warm.citations.reuse")
    # 判据 5：同输入两次逐字节相等（voice 是纯函数）
    assert _w == _wb2.get("warm"), "warm must be deterministic"
    ok.append("warm.deterministic")
    # 判据 10 前置：幸运项由规则推出且带出处说明（非随机）
    _ec = _w["energy_card"]
    assert _ec["lucky_numbers"] and _ec["lucky_colors"] and _ec["basis"], _ec
    ok.append("warm.energy_card.rules")
    # 判据 4：依据行被拆进 basis（可折叠），且**逐字未改写**
    _basis_all = "".join("".join(d["basis"]) for d in _w["details"])
    assert "依据：" in _basis_all, _basis_all[:120]
    assert "戊戊同为土" in _basis_all, _basis_all[:200]
    ok.append("warm.details.basis_verbatim")
    # 判据 8：六爻 warm 对提问给描述性回应，且专业分支原文仍在
    _wl = client.post("/api/liuyao", json={"method": "coins", "seed": 42,
                                          "question": "这事能成吗？"}).json()
    _wlw = _wl.get("warm")
    assert isinstance(_wlw, dict) and _wlw["reply"], _wlw
    assert "这事能成吗？" in _wlw["reply"][0], _wlw["reply"][0]
    assert "不代为断事" not in "".join(_wlw["reply"]), _wlw["reply"]
    _pro = " ".join(" ".join(s.get("lines") or [])
                    for s in _wl["interpretation"].get("sections") or [])
    assert "不代为断事" in _pro, "专业分支原文必须保持不变（判据 9）"
    ok.append("warm.liuyao.answers_not_refuse")

    # ── 006 AI 润色层（R132a，T1.5）：selftest 侧三条契约断言 ─────────────
    # 完整判据由 probes/probe_llm_polish.py 把关（降级矩阵/三库零命中/注入抵抗）；
    # 这里放**端点契约级**断言，闸门在 BOOKS_LLM_DISABLE=1 下可复现。
    from guji import llm_polish as _lp
    # 判据 key_present：四端点响应**永远带** ai_polish 键（关闭时是 None，
    # 不是缺键）——前端 renderAiPolish(j) 靠 `j.ai_polish` 取值，键缺失与
    # None 在语义上等价，但契约上键必须恒在，抓「哪天忘了附加」的静默回归。
    for _ep, _pl in (("/api/bazi", {"year": 1990, "month": 5, "day": 15,
                                    "hour": 10, "gender": "男"}),
                     ("/api/taohua", {"year": 1990, "month": 5, "day": 15,
                                      "hour": 10, "gender": "男"}),
                     ("/api/hehun", {"a_year": 1990, "a_month": 5, "a_day": 15,
                                     "a_hour": 10, "a_gender": "男",
                                     "b_year": 1992, "b_month": 8, "b_day": 20,
                                     "b_hour": 14, "b_gender": "女"}),
                     ("/api/qiming", {"surname": "李", "year": 1990,
                                      "month": 1, "day": 1, "hour": 12,
                                      "gender": "男", "top_n": 5})):
        _aj = client.post(_ep, json=_pl).json()
        assert "ai_polish" in _aj, (_ep, sorted(_aj))
    ok.append("ai_polish.key_present")
    # 判据 disabled_none：总开关开启时 polish() 必须返回 None 且不抛——
    # LLM 永远不是承重墙（D-244a），禁用路径必须是一条真实可走的路。
    # R192b 修正：finally 里 pop 掉环境变量会把「闸门环境的 DISABLE=1」一并
    # 抹掉——本进程后续所有端点调用（含下面的 additive 段）会因此拿到
    # ai_task_id，与 R191b 的 no_task_id 断言和判据 11 冲突（合并后首跑
    # 实测 AssertionError：/api/bazi 多出 ai_task_id 键）。改为**保存旧值、
    # 恢复旧值**：环境本来没设就恢复成没设，闸门设了就恢复成设了。
    _old_disable = os.environ.get("BOOKS_LLM_DISABLE")
    os.environ["BOOKS_LLM_DISABLE"] = "1"
    try:
        assert _lp.polish(["日主戊"], "感情？",
                          config={"base_url": "http://127.0.0.1:1",
                                  "api_key": "x", "model": "m"}) is None
    finally:
        if _old_disable is None:
            os.environ.pop("BOOKS_LLM_DISABLE", None)
        else:
            os.environ["BOOKS_LLM_DISABLE"] = _old_disable
    ok.append("ai_polish.disabled_none")
    # 判据 additive：四端点顶层键集合 = 「LLM 时代之前」的形状 + ai_polish
    # 一个键。additive 是 specs/006 的架构承诺：润色层只附加、不改写既有
    # 字段。钉死键集合 = 未登记的新键/被改掉的旧键都会被抓到（同 D-228b 先例）。
    _shapes = {
        "/api/bazi": {"year": 1990, "month": 5, "day": 15, "hour": 10,
                      "gender": "男"},
        "/api/taohua": {"year": 1990, "month": 5, "day": 15, "hour": 10,
                        "gender": "男"},
        "/api/hehun": {"a_year": 1990, "a_month": 5, "a_day": 15, "a_hour": 10,
                       "a_gender": "男", "b_year": 1992, "b_month": 8,
                       "b_day": 20, "b_hour": 14, "b_gender": "女"},
        "/api/qiming": {"surname": "李", "year": 1990, "month": 1, "day": 1,
                        "hour": 12, "gender": "男", "top_n": 5},
    }
    _expect_keys = {
        "/api/bazi": {"paipan", "calc", "evidence", "interpretation",
                      "warm", "ai_polish",
                      # R218a-巡2（N-01）：后端回写 question 供前端钩子使用
                      "question",
                      # C-003：交叉引用——八字结果页增加星座维度
                      "cross_ref"},
        "/api/taohua": {"peach_zhi", "hongluan", "hongluan_pillar", "tianxi",
                        "tianxi_pillar", "strength", "render", "notes",
                        "dayun_hits", "hit_pillars", "warm", "bazi",
                        "year_zhi", "birth_year", "ai_polish",
                        # R220b：交叉引用铺到桃花（星座桃花信号 × 八字强度）
                        "cross_ref"},
        "/api/hehun": {"clash", "combine", "render", "notes", "day_wx_a",
                       "day_wx_b", "day_wx_sheng", "peach_a", "peach_b",
                       "peach_same", "dayun_hits", "warm", "a_bazi", "b_bazi",
                       "year_zhi_a", "year_zhi_b", "ai_polish",
                       # R204b（D-257b）：天干五合 + 十神互见
                       "gan_he", "god_a_sees_b", "god_b_sees_a",
                       # C-003：交叉引用——合婚结果页增加星座配对维度
                       "cross_ref"},
        "/api/qiming": {"surname", "five_elements", "candidates", "bazi", "summary",
                        "full_names", "ai_polish",
                        # R220b：交叉引用铺到起名（太阳星座气质参考）
                        "cross_ref"},
    }
    for _ep, _pl in _shapes.items():
        _got = set(client.post(_ep, json=_pl).json())
        assert _got == _expect_keys[_ep], \
            (_ep, sorted(_got), sorted(_expect_keys[_ep]))
    ok.append("ai_polish.additive")

    # ── R228o 闸门盲区钉扎（审查轨 gate-blindspots 批）──────────────
    # 2a) styles.css：@import 必须位于全部普通规则之前——R228m 实测过
    #     @import 写在中段会被浏览器静默丢弃（字体/主题 import 失效零报错）。
    import os as _os
    import re as _re
    _css_path = _os.path.join(_os.path.dirname(__file__), "static",
                            "styles.css")
    # 逐行剥掉 /* */ 注释块后再判——注释正文行不是规则。
    _raw = open(_css_path, encoding="utf-8").read()
    _lines = _re.sub(r"/\*.*?\*/", "", _raw, flags=_re.S).splitlines()
    _seen_rule = False
    for _ln in _lines:
        _t = _ln.strip()
        if not _t or _t.startswith("//"):
            continue
        if _t.startswith("@import") or _t.startswith("@charset"):
            assert not _seen_rule, "styles.css: @import 出现在普通规则之后"
            continue
        _seen_rule = True
    ok.append("css.import.position")

    # 2b) sqlite3.OperationalError → 503（db 锁/坏页不许变 500 栈；
    #     errors.py 注册的 handler 必须真实在位）。
    import sqlite3 as _sq
    assert _sq.OperationalError in app.exception_handlers, \
        sorted(str(k) for k in app.exception_handlers)
    ok.append("err.sqlite.op.503")

    # 2c) SW 链路：/sw.js 200 + JS MIME + index.html 注册 +
    #     Service-Worker-Allowed 头（根作用域）——三段缺一 SW 就静默失效。
    _sw = client.get("/sw.js")
    assert _sw.status_code == 200, _sw.status_code
    assert "javascript" in _sw.headers.get("content-type", ""), \
        _sw.headers.get("content-type")
    assert _sw.headers.get("Service-Worker-Allowed") == "/", \
        dict(_sw.headers)
    _idx_path = _os.path.join(_os.path.dirname(__file__), "static",
                            "index.html")
    _idx = open(_idx_path, encoding="utf-8").read()
    assert "sw.js" in _idx and ("serviceWorker" in _idx), \
        "index.html 未见 SW 注册"
    ok.append("sw.chain")

    # R229r：请求体大小护栏——>512KB 的 POST 须 413 中文拒（不进 pydantic）。
    _big = client.post("/api/bazi", content="x" * (513 * 1024),
                       headers={"Content-Type": "application/json"})
    assert _big.status_code == 413 and "太大" in _big.json().get("detail", ""), \
        ("err.body_too_large", _big.status_code, _big.text[:120])
    ok.append("err.body_too_large")
    return ok


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ok = run()
    print(f"web self-test PASS ({len(ok)} checks): {', '.join(ok)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
