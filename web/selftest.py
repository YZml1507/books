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
  * 写端点（bazi 写 history.db、threads 写 knowledge.db）自测后必须清理
    本轮新增记录（L-22 教训：写端点自测不得污染真实库）。

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
        ok.append(name)

    # R163b（D-209b）：422 排盘失败分支断言辅助——400 参数校验断言不构成
    # 422 计算失败路径的覆盖（compute 抛异常→422，如 1990-02-30 不存在）。
    def _expect_422(name, resp):
        assert resp.status_code == 422, (name, resp.status_code, resp.text[:200])
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
    # bazi 端点会把查询写入真实 history.db（D-039 用户授权）——自测须清理
    # 本次新增记录（L-22 教训：写端点自测不得污染真实库）。
    from guji import history as history_db

    rows_before = history_db.list_records(limit=1)
    max_id_before = rows_before[0]["id"] if rows_before else 0
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
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
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
    check("huangli", client.get("/api/huangli", params={"date": "2026-08-17",
          "days": 1}),
          lambda j: j.get("date") and j.get("jianchu"))
    check("qiming", client.post("/api/qiming", json={"surname": "李",
          "year": 1990, "month": 1, "day": 1, "hour": 12, "gender": "男",
          "top_n": 5}),
          lambda j: j.get("candidates"))
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
    # R158b（D-204b）：bazi lunar 换算后公历年份范围（独立校验分支）400
    # standing 覆盖——lunar_to_solar **成功**但换算后公历年份越界。
    _expect_400("err.bazi.lunar_solar_range",
                client.post("/api/bazi", json={"year": 1990, "month": 5,
                                               "day": 15, "hour": 10,
                                               "calendar_type": "lunar",
                                               "lunar_year": 2100,
                                               "lunar_month": 12,
                                               "lunar_day": 15}))
    # R151b（D-197b）：bazi ask_hour / ask_date 格式 / range 缺失 / range 格式
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
    # 实测 q="甲"*201 → 400 "q 过长（≤200 字符）"。
    _expect_400("err.compare_works.q_too_long",
                client.get("/api/compare_works",
                           params={"work_a": "KR5c0057", "work_b": "KR5c0126",
                                   "q": "甲" * 201}))
    _expect_400("err.concept.empty", client.get("/api/concept", params={"q": ""}))
    _expect_400("err.research.max_addresses",
                client.get("/api/research", params={"q": "潛龍勿用",
                                                    "max_addresses": 0}))
    # R145b（D-191b）：search q 为空校验 standing 覆盖。实测 q="" → 400 +
    # detail "q 不能为空——检索需要查询词；找某个地址请用 /api/addr"。
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
    # min_length），q="   " → 400 "q 不能为空"（strip() 后空）。
    _ask_empty = client.post("/api/ask", json={"q": "   ", "max_addresses": 2})
    assert _ask_empty.status_code == 400, ("err.ask.q_empty",
                                           _ask_empty.status_code,
                                           _ask_empty.text[:200])
    assert _ask_empty.json().get("detail") == "q 不能为空", \
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
    check("history", client.get("/api/history", params={"limit": 3}),
          lambda j: "records" in j and isinstance(j["records"], list))
    # R126b（D-172b）：history.detail 断言的 id 来源——原用 count()（行数）
    # 当 id 查，历史库经删除后 id 不连续 → 404。改取最新记录真实 id。
    _latest = history_db.list_records(limit=1)
    check("history.detail",
          client.get(f"/api/history/{_latest[0]['id'] if _latest else 0}"),
          lambda j: j is None or "paipan" in j)
    # R138b（D-184b）：history.detail 缺失记录拒绝分支 standing 覆盖——
    # 现有 check 只测命中路径，404 拒绝分支零断言。实测 99999 → 404 + detail。
    _miss = client.get("/api/history/99999")
    assert _miss.status_code == 404, ("history.detail.missing",
                                      _miss.status_code, _miss.text[:200])
    assert _miss.json().get("detail"), ("history.detail.missing",
                                        _miss.text[:200])
    ok.append("history.detail.missing")
    check("threads.detail", client.get("/api/threads/1"),
          lambda j: "claims" in j and "turns" in j)
    # R169b（D-215b）：threads.detail 404 拒绝路径 standing 覆盖。
    # 实测 tid=99999 → 404 + detail "线程 99999 不存在或暂无对话"。
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
    ok.append("home")
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
    import re as _re
    _cards = _re.findall(r'class="func-card" data-view="([a-z]+)"', home.text)
    assert len(_cards) == 8, ("home.ia.count", len(_cards), _cards)
    assert _cards == ["bazi", "qiming", "hehun", "taohua",
                      "tarot", "liuyao", "huangli", "read"], \
        ("home.ia.order", _cards)
    assert _cards.index("hehun") + 1 == _cards.index("taohua"), \
        ("home.ia.pair", _cards)
    for _grp, _lab in (("ask", "测一测"), ("read", "读书")):
        assert f'<div class="ia-group" data-group="{_grp}">' in home.text, \
            ("home.ia.group", _grp)
        assert _lab in home.text, ("home.ia.label", _lab)
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
    _expect_400("err.daily.date",
                client.get("/api/daily", params={"date": "garbage"}))
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
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
    ok.append("llm.fields.absent")
    # R191b（T1.5 补建，B-014/D-251b）：AI 润色**异步层** standing 断言。
    # 闸门环境 DISABLE=1：端点响应必须无 ai_task_id 键（判据 11，与旧版
    # 逐字节一致）；异步机制本体用显式 config + 打桩 transport 离线验证
    # （显式 config 绕过总开关，零外网、确定性延迟）。
    import time as _time
    from guji import llm_polish as _L

    _max_id2 = max((rec["id"] for rec in history_db.list_records(limit=5)),
                   default=0)
    _b = client.post("/api/bazi", json={"year": 1990, "month": 5, "day": 15,
                                        "hour": 10, "gender": "男"}).json()
    assert "ai_task_id" not in _b and _b.get("ai_polish") is None, sorted(_b)
    for rec in history_db.list_records(limit=5):
        if rec["id"] > _max_id2:
            history_db.delete_record(rec["id"])
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
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
    assert isinstance(_bz["calc"]["five_elements"], dict), "five_elements must be dict"
    assert isinstance(_bz["calc"]["day_luck"], dict), "day_luck must be dict"
    _hl = client.get("/api/huangli", params={"date": "2026-08-19"}).json()
    assert isinstance(_hl["pengzu"], dict), "pengzu must be dict"
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

    # ── 004 warm 视图（R182b，M1）：判据 1/2/5/6/7/8/15 的 selftest 侧覆盖 ──
    # 完整判据由 web/check_warm_voice.py 把关（含术语表/禁用词表与阳性对照）；
    # 这里放**端点契约级**断言：warm 键存在、结构齐、确定性、引文复用。
    _wb = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                        "hour": 14, "gender": "女",
                                        "question": "感情运怎么样？"}).json()
    _wb2 = client.post("/api/bazi", json={"year": 1998, "month": 7, "day": 20,
                                         "hour": 14, "gender": "女",
                                         "question": "感情运怎么样？"}).json()
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
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
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
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
                      "warm", "ai_polish"},
        "/api/taohua": {"peach_zhi", "hongluan", "hongluan_pillar", "tianxi",
                        "tianxi_pillar", "strength", "render", "notes",
                        "dayun_hits", "hit_pillars", "warm", "bazi",
                        "year_zhi", "ai_polish"},
        "/api/hehun": {"clash", "combine", "render", "notes", "day_wx_a",
                       "day_wx_b", "day_wx_sheng", "peach_a", "peach_b",
                       "peach_same", "dayun_hits", "warm", "a_bazi", "b_bazi",
                       "year_zhi_a", "year_zhi_b", "ai_polish"},
        "/api/qiming": {"surname", "candidates", "summary", "five_elements",
                        "full_names", "bazi", "ai_polish"},
    }
    for _ep, _pl in _shapes.items():
        _got = set(client.post(_ep, json=_pl).json())
        assert _got == _expect_keys[_ep], \
            (_ep, sorted(_got), sorted(_expect_keys[_ep]))
    ok.append("ai_polish.additive")
    for rec in history_db.list_records(limit=20):
        if rec["id"] > max_id_before:
            history_db.delete_record(rec["id"])
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
