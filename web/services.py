"""web/services.py — 业务编排层（返回纯 dict，不认识 HTTP）。

分层职责（宪法 III「分层架构不可越界」在 web 层的落地）：
    schemas.py    输入形状与值域校验，不碰业务、不碰 DB
    services.py   **本文件**：编排 src/guji 的业务模块，返回纯 dict
    routers/*.py  只做 HTTP 绑定：解析 → 调 service → 交给统一异常处理
    deps.py       路径常量与资源句柄（Corpus/KnowledgeBase 生命周期）

本层的硬约束：
  * **不 import fastapi**。抛业务异常（schemas.ValidationError /
    ComputeError / NotFoundError），由路由层统一映射成 400/422/404。
    这样每个 service 都能在没有 HTTP 栈的情况下被直接调用与复验。
  * **返回纯 dict / list**，不返回 Hit、Bazi、Corpus 等活对象——序列化
    边界收在本层，前端拿到的字段名即本层写出的字段名。
  * **不复制业务逻辑**：一切计算都在 src/guji 里，本层只负责调用顺序、
    参数换算、字段拼装。与 CLI（scripts/ask.py、scripts/ask_bazi.py）调
    同一批函数，保证两端输出一致。

解读层（R178b，D-226b）：全部解读走 `guji.interpreter` 确定性规则引擎
——零网络、零成本、同输入必同输出。原 `llm_reader` 生成式解读已移除，
响应字段统一为 `interpretation`（dict），不再有 `use_llm` 开关。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
from datetime import date, datetime, timedelta

from guji import external as external_feed
# R219b（P0-4）：`from guji import history as history_db` 随历史记录功能删除
# ——web 层不再有任何 history_db 调用点（模块文件本体保留，见文件下方注释）。
from guji import huangli as huangli_mod
from guji import hehun as hehun_mod
from guji import interpreter
from guji import liuyao as liuyao_mod
from guji import llm_polish
from guji import lunar
from guji import qiming as qiming_mod
from guji import taohua as taohua_mod
from guji import tarot as tarot_mod
from guji import voice
from guji import xingzuo as xingzuo_mod
from guji.bazi import compute as bazi_compute
from guji.bazi_calc import calc as bazi_calc
from guji.bazi_calc import calc_life, calc_range
from guji.bazi_lookup import retrieve_fast
from guji.compare import compare_address
from guji.research import compare_works as research_compare_works
from guji.research import concept_census, research

from . import deps
from .schemas import (
    YEAR_HI,
    YEAR_LO,
    ComputeError,
    NotFoundError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# 序列化边界：活对象 → 纯 dict
# ---------------------------------------------------------------------------


def hit_dict(h) -> dict:
    """Hit -> JSON-safe dict（citation/disclosure 为既有展示串，不做二次加工）。"""
    return {
        "work_id": h.work_id,
        "title": h.title,
        "attribution": h.attribution,
        "edition": h.edition,
        "page_anchor": h.page_anchor,
        "scheme": h.scheme,
        "addr_name": h.addr_name,
        "gua": h.gua,          # = addr1
        "yao": h.yao,          # = addr2
        "layer": h.layer,
        "text": h.text,
        "file": h.file,
        "score": h.score,
        "skipped_chars": h.skipped_chars,
        "suspect": h.suspect,
        "citation": h.citation(),
        "disclosure": h.disclosure(),
    }


def _require_q(q: str | None, *, what: str = "q 不能为空") -> str:
    q = (q or "").strip()
    if not q:
        raise ValidationError(what)
    if len(q) > 200:
        raise ValidationError("q 过长（≤200 字符）")
    return q


# ---------------------------------------------------------------------------
# 八字域：排盘 / 桃花 / 合婚 / 起名 / 历史
# ---------------------------------------------------------------------------


def resolve_birth(req) -> tuple[int, int, int]:
    """请求里的生日 -> 公历 (year, month, day)。农历输入在此换算。"""
    if req.calendar_type == "lunar":
        try:
            d = lunar.lunar_to_solar(req.lunar_year, req.lunar_month,
                                     req.lunar_day, req.lunar_leap)
        except ValueError as exc:
            raise ValidationError(f"农历换算失败：{exc}") from exc
        if not (YEAR_LO <= d.year <= YEAR_HI):
            raise ValidationError(
                f"换算后公历年份需在 {YEAR_LO}-{YEAR_HI} 之间")
        return d.year, d.month, d.day
    return req.year, req.month, req.day


def _dedup_evidence(evidence: list[dict], limit: int = 12) -> list[dict]:
    """同一单元 FTS 多词命中的去重，保留前 limit 条。"""
    seen, out = set(), []
    for e in evidence:
        k = (e["work_id"], e["page_anchor"], e["text"][:40])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
        if len(out) >= limit:
            break
    return out


def bazi(req) -> dict:
    """八字排盘 + 运算层（按 scope 分支）+ 古籍引文 + 确定性解读。

    scope: day 单日 / range 日期范围（≤31 天）/ life 生平大运。
    完整往返写入独立 history.db（D-039 用户授权，与语料库物理隔离）。
    """
    req.validate_ranges()
    by, bm, bd = resolve_birth(req)
    try:
        b = bazi_compute(by, bm, bd, req.hour, req.gender)
    except Exception as exc:                     # 节气表范围外等 → 422
        raise ComputeError(f"排盘失败：{exc}") from exc

    ask_date = req.ask_date or date.today().isoformat()
    if req.scope == "range":
        try:
            calc_out = calc_range(b, req.range_start, req.range_end, req.ask_hour)
        except ValueError as exc:                # 倒序 / 超 31 天 → 400
            raise ValidationError(str(exc)) from exc
        calc_out["scope"] = "range"
    elif req.scope == "life":
        calc_out = calc_life(b, by)
        calc_out["scope"] = "life"
    else:
        calc_out = bazi_calc(b, ask_date=ask_date, ask_hour=req.ask_hour)
        calc_out["scope"] = "day"
    if req.location:
        calc_out["location"] = req.location

    # R189b（清偿 R131a-01）：question 进检索——主题词追加在坐标词队尾，
    # 用户问什么，证据与之相关。无提问时检索行为与旧版逐字节一致。
    evidence = _dedup_evidence(retrieve_fast(b, per_query=2, per_work=1,
                                             question=req.question))
    paipan_out = {"render": b.render(), "nayin": b.nayin, "warn": b.warn}
    interpretation = interpreter.interpret_bazi(paipan_out, calc_out,
                                               evidence, req.question)
    # R182b（004 M1）：warm 视图 **additive** 附加——不动 interpretation 一个
    # 字节。判据 9 要求专业模式逐字节等于基线，由 web/baseline_voice.py 把关。
    warm = voice.warm_bazi(paipan_out, calc_out, interpretation, req.question)

    # R187b（specs/006）：AI 润色层，additive 附加。失败/关闭 → None，
    # 前端整块不渲染；LLM 永远不是承重墙（D-244a）。
    # R191b（B-014，D-251b）：同步 polish 改后台任务——确定性主体立即返回，
    # 响应附 ai_task_id 供前端轮询 /api/ai/{id}；DISABLE/关闭时无此键
    # （响应与旧版逐字节一致，specs/006 判据 11）。
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_bazi(paipan_out, warm, req.question),
        req.question)

    # R219b（P0-4 用户裁决）：不再把排盘写入 history.db——「我的解读」历史
    # 记录功能整体删除（用户原话：不记录，浪费内存，后续会建用户隔离数据库）。
    # 原 input_snapshot + history_db.save_record() 一并移除，/api/bazi 由此
    # 变成纯读端点（selftest/探针的 history 清理判据因此恒等于零新增）。
    return {
        "paipan": paipan_out,
        "calc": calc_out,
        "evidence": evidence,
        "interpretation": interpretation,
        "warm": warm,
        "ai_polish": ai_polish,
        # R218a-巡2（N-01）：echo 用户提问供前端 questionHook 使用
        # ——前端 buildBaziResult/buildLiuyaoResult/buildTarotResult 内
        # if (j.question) 钩子函数曾因后端不返回该字段而永远不触发。
        "question": req.question,
        # C-003：交叉引用——八字结果页增加星座维度
        "cross_ref": _cross_ref_bazi(b, req.gender),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }


def taohua(req) -> dict:
    """八字桃花运：咸池/红鸾/天喜 纯坐标计算（固定生日 → 固定输出）。"""
    req.validate_ranges()
    by, bm, bd = resolve_birth(req)
    try:
        b = bazi_compute(by, bm, bd, req.hour, req.gender)
        t = taohua_mod.compute(b)
        dayun = taohua_mod.dayun_hits(b, by)
    except Exception as exc:
        raise ComputeError(f"排盘失败：{exc}") from exc
    t_dict = {
        "bazi": {"year": b.year, "month": b.month, "day": b.day,
                 "hour": b.hour, "day_master": b.day_master},
        "year_zhi": t.year_zhi,
        "peach_zhi": t.peach_zhi,
        "hit_pillars": list(t.hit_pillars),
        "hongluan": t.hongluan,
        "hongluan_pillar": list(t.hongluan_pillar),
        "tianxi": t.tianxi,
        "tianxi_pillar": list(t.tianxi_pillar),
        "strength": t.strength,
        "dayun_hits": dayun,
        "birth_year": by,
        "notes": t.notes,
        "render": t.render(),
    }
    # R187b：人话视图 + AI 润色，均 additive（specs/005 US4 / specs/006）
    # R191b（B-014）：AI 段落改后台任务（D-251b），同 bazi。
    warm = voice.warm_taohua(t_dict)
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_taohua(t_dict, warm, gender=req.gender))
    return {
        **t_dict,
        "warm": warm,
        "ai_polish": ai_polish,
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }


def hehun(req) -> dict:
    """八字合婚：六冲/六合/日主五行/桃花支 + 大运冲合应期，全纯坐标。"""
    req.validate_ranges()
    try:
        ba = bazi_compute(req.a_year, req.a_month, req.a_day, req.a_hour,
                          req.a_gender)
        bb = bazi_compute(req.b_year, req.b_month, req.b_day, req.b_hour,
                          req.b_gender)
        h = hehun_mod.compute(ba, bb)
        dayun = hehun_mod.dayun_relation(ba, req.a_year, bb, req.b_year)
    except Exception as exc:
        raise ComputeError(f"排盘失败：{exc}") from exc
    h_dict = {
        "a_bazi": {"year": ba.year, "day": ba.day, "day_master": ba.day_master},
        "b_bazi": {"year": bb.year, "day": bb.day, "day_master": bb.day_master},
        "year_zhi_a": h.year_zhi_a, "year_zhi_b": h.year_zhi_b,
        "clash": h.clash, "combine": h.combine,
        "day_wx_a": h.day_wx_a, "day_wx_b": h.day_wx_b,
        "day_wx_sheng": h.day_wx_sheng,
        "peach_a": h.peach_a, "peach_b": h.peach_b, "peach_same": h.peach_same,
        # R204b（D-257b）：天干五合 + 日主十神互见（yinyuan skill 融入）
        "gan_he": h.gan_he,
        "god_a_sees_b": h.god_a_sees_b, "god_b_sees_a": h.god_b_sees_a,
        "dayun_hits": dayun,
        "notes": h.notes,
        "render": h.render(),
    }
    # R187b：人话视图 + AI 润色，均 additive（specs/005 US4 / specs/006）
    # R191b（B-014）：AI 段落改后台任务（D-251b），同 bazi。
    warm = voice.warm_hehun(h_dict)
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_hehun(h_dict, warm,
                               gender_a=req.a_gender, gender_b=req.b_gender))
    return {
        **h_dict,
        "warm": warm,
        "ai_polish": ai_polish,
        # C-003：交叉引用——合婚结果页增加星座配对维度
        "cross_ref": _cross_ref_hehun(ba, bb),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }


def qiming(req) -> dict:
    """五行起名：八字 → 五行缺行 → 古籍典故取名 + 候选字（R217a 重构）。"""
    req.validate_ranges()
    try:
        from guji import classical_names
        out = classical_names.generate_classical_names(
            surname=req.surname, year=req.year, month=req.month,
            day=req.day, hour=req.hour, gender=req.gender,
            top_n=min(max(req.top_n, 1), 100),
            seed=req.seed)
    except Exception as exc:
        raise ValidationError(f"起名计算失败：{exc}") from exc
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(llm_polish.facts_qiming(out, req.gender))
    out["ai_polish"] = ai_polish
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    return out


def xingzuo(date_str: str | None = None) -> dict:
    """十二宫日运（004 M2 T2.3）：当日日支查宫 + 12 宫一句话 + 语料锚点。

    纯坐标 + 写死文案 + 真实引文锚点（fixture 逐字命中，判据 10/11）。
    """
    if date_str is not None:
        try:
            date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError(
                f"date 需为 YYYY-MM-DD 格式，收到 {date_str}") from None
    d = date.fromisoformat(date_str) if date_str else date.today()
    b = bazi_compute(d.year, d.month, d.day, 12, "男")
    out = xingzuo_mod.daily_horoscope(b.day)
    out["date"] = d.isoformat()
    return out


# R219b（P0-4 用户裁决）：history_list / history_detail / history_delete 三个
# 服务函数随「我的解读」历史记录功能整体删除。用户原话：不记录，浪费内存，
# 后续会建用户隔离数据库。guji.history 模块本体保留（未删文件）——闸门脚本
# 与探针仍 import 它做清理判据，删模块会连带打断审查轨领土的判据本体。


# ---------------------------------------------------------------------------
# 读书域：检索 / 定位 / 比对 / 研究 / 书目 / 线程 / 读书视图
# ---------------------------------------------------------------------------


def search(q: str, *, layer: str | None = None, work: str | None = None,
           genre: str | None = None, scheme: str | None = None,
           limit: int = 10) -> dict:
    q = _require_q(q, what="q 不能为空——检索需要查询词；找某个地址请用 /api/addr")
    limit = min(max(limit, 1), 50)
    with deps.corpus() as c:
        hits = c.search(q, limit=limit, layer=layer, work_id=work,
                        genre=genre, scheme=scheme)
        return {"query": q, "count": len(hits),
                "hits": [hit_dict(h) for h in hits]}


def addr(scheme: str = "zhouyi", *, gua: int | None = None,
         yao: str | None = None, layer: str | None = None,
         addr_name: str | None = None, addr1: int | None = None,
         addr2: str | None = None, limit: int = 20) -> dict:
    """地址定位。scheme 显式声明，杜绝 Psalms-99 == 卦99 类跨体系碰撞（D-005）。"""
    if scheme not in deps.SCHEME_LABELS:
        raise ValidationError(f"scheme 只能是 {'/'.join(deps.SCHEME_LABELS)}")
    limit = min(max(limit, 1), 100)
    with deps.corpus() as c:
        if scheme == "zhouyi":
            if gua is None:
                raise ValidationError("zhouyi 定位需提供 gua（1-64）")
            hits = c.at_address(gua, yao, layer=layer, limit=limit)
        else:
            hits = c.at_scheme(scheme, addr_name=addr_name, addr1=addr1,
                               addr2=addr2, layer=layer, limit=limit)
        return {"scheme": scheme, "count": len(hits),
                "hits": [hit_dict(h) for h in hits]}


def compare(gua: int, yao: str = "九三", layer: str = "經") -> dict:
    """跨版本同址比对 + 差异摘要（复用 compare.compare_address）。"""
    if not (1 <= gua <= 64):
        raise ValidationError("gua 需在 1-64")
    with deps.corpus() as c:
        cmp = compare_address(c, gua, yao, layer=layer)
        return {
            "addr": cmp.addr,
            "reference": cmp.reference,
            "agree": cmp.agree,
            "counts": cmp.counts(),
            "witnesses": cmp.witnesses,
            "citations": cmp.citations,
            "commentary": cmp.commentary,
            "findings": [{
                "kind": f.kind, "at": f.at, "base": f.base,
                "others": f.others, "note": f.note, "base_id": f.base_id,
                "line": f.line(),
            } for f in cmp.findings],
        }


def deep_research(q: str, *, max_addresses: int = 3,
                  allow_damaged: bool = False) -> dict:
    """深度研究：检索→读地址→扩展的多轮循环，返回证据集 + 步骤链 + 差异摘要。"""
    q = _require_q(q)
    if not (1 <= max_addresses <= 6):
        raise ValidationError("max_addresses 需在 1-6")
    with deps.corpus() as c:
        r = research(c, q, max_addresses=max_addresses,
                     allow_damaged=allow_damaged)
        return {
            "question": r.question, "refused": r.refused, "reason": r.reason,
            "steps": r.step_dict(),
            "evidence": [hit_dict(h) for h in r.evidence],
            "flagged": [hit_dict(h) for h in r.flagged],
            "comparisons": r.comparisons,
        }


def ask(req) -> dict:
    """研究问答：deep_research 的证据集 + 确定性综合（不新增论断）。

    检索拒绝时不做综合（G7 不让解读层替语料编造）；引文由服务端从证据
    对象渲染，解读独立成 `interpretation` 字段。
    """
    q = _require_q(req.q)
    with deps.corpus() as c:
        r = research(c, q, max_addresses=req.max_addresses,
                     allow_damaged=req.allow_damaged)
        ev = [hit_dict(h) for h in r.evidence[:12]]
        resp = {
            "question": r.question, "refused": r.refused, "reason": r.reason,
            "steps": r.step_dict(),
            "evidence": ev,
            "evidence_citations": [h.citation() for h in r.evidence[:12]],
            "comparisons": r.comparisons,
            "interpretation": None,
        }
        if r.refused or not ev:
            return resp
        resp["interpretation"] = interpreter.interpret_research(
            q, ev, r.comparisons)
        return resp


def concept(q: str, per_work: int = 3) -> dict:
    """跨书概念研究：作品级普查 + 同址多见证地图。"""
    q = _require_q(q)
    with deps.corpus() as c:
        return concept_census(c, q, per_work=min(max(per_work, 1), 10))


def compare_works(work_a: str, work_b: str, q: str, per_work: int = 3) -> dict:
    """两书对照：两书 top 证据并排 + 层分布对照 + 同址命中地址。"""
    work_a, work_b = (work_a or "").strip(), (work_b or "").strip()
    if not work_a or not work_b:
        raise ValidationError("work_a / work_b 不能为空")
    q = _require_q(q)
    with deps.corpus() as c:
        return research_compare_works(c, work_a, work_b, q,
                                      per_work=min(max(per_work, 1), 10))


def works() -> dict:
    """语料书目（Corpus.coverage + manifest 的 source 标记）。"""
    with deps.corpus() as c:
        rows = [dict(r) for r in c.coverage()]
    src = {}
    try:
        with open(deps.CORPUS_MANIFEST, encoding="utf-8") as f:
            man = json.load(f)
        src = {w.get("id"): w.get("source") for w in man.get("works", [])
               if w.get("id")}
    except (OSError, ValueError):
        src = {}
    for r in rows:
        r["source"] = src.get(r["id"]) or "kanripo/内置"
    return {"works": rows, "total": len(rows)}


def stats() -> dict:
    with deps.corpus() as c:
        return {
            "stats": c.stats(),
            "layers": [dict(r) for r in c.db.execute(
                "SELECT layer, count(*) n FROM unit GROUP BY layer "
                "ORDER BY n DESC")],
            "meta": [dict(r) for r in c.db.execute(
                "SELECT key, value FROM build_meta")],
            "schemes": deps.SCHEME_LABELS,
        }


def threads() -> dict:
    """研究线程列表（G9：可恢复的研究线索）。"""
    with deps.knowledge() as kb:
        return {"threads": [dict(r) for r in kb.resume()], "stats": kb.stats()}


def thread_detail(tid: int) -> dict:
    """单条线程：transcript + derived claims + 证据回查。"""
    with deps.knowledge() as kb:
        turns = [dict(r) for r in kb.thread_transcript(tid)]
        if not turns:
            raise NotFoundError(f"线程 {tid} 不存在或暂无对话")
        claims = []
        for row in kb.db.execute(
                "SELECT id FROM derived WHERE thread_id=? ORDER BY id", (tid,)):
            d = kb.get(row["id"])
            if d is None:
                continue
            claims.append({
                "id": d.id, "kind": d.kind, "claim": d.claim,
                "method": d.method, "confidence": d.confidence,
                "created_at": d.created_at,
                "evidence": [{
                    "role": e.role, "work_id": e.work_id, "file": e.file,
                    "page_anchor": e.page_anchor, "scheme": e.scheme,
                    "addr1": e.addr1, "addr2": e.addr2, "quote": e.quote,
                } for e in d.evidence],
            })
        return {"turns": turns, "claims": claims,
                "verify": kb.verify(deps.RAW_DIR)}


def thread_record(req) -> dict:
    """写入一条 derived claim（G8 纪律：断言型 kind 必须带证据）。"""
    from guji.knowledge import Evidence

    with deps.knowledge() as kb:
        ev = [Evidence(work_id=e.work_id, file=e.file,
                       raw_start=e.raw_start if e.raw_start is not None else -1,
                       raw_end=e.raw_end if e.raw_end is not None else -1,
                       quote=e.quote, page_anchor=e.page_anchor,
                       scheme=e.scheme, addr1=e.addr1, addr2=e.addr2,
                       role=e.role)
              for e in req.evidence]
        try:
            did = kb.record(req.kind, req.claim, req.method, ev,
                            confidence=req.confidence, thread_id=req.thread_id)
        except (ValueError, sqlite3.IntegrityError) as exc:
            # 非法 kind 触发 DB CHECK 约束的 IntegrityError；与其余端点
            # 「非法参数 → 400」纪律一致（R159b/D-205b）。
            raise ValidationError(str(exc)) from exc
        row = kb.db.execute("SELECT thread_id FROM derived WHERE id = ?",
                            (did,)).fetchone()
        return {"derived_id": did,
                "thread_id": row["thread_id"] if row else None,
                "kind": req.kind, "claim": req.claim[:120],
                "n_evidence": len(ev)}


def book_structure(work_id: str, sample_chars: int = 60) -> dict:
    from guji.bookstudy import structure

    work_id = (work_id or "").strip()
    if not work_id:
        raise ValidationError("work_id 不能为空")
    with deps.corpus() as c:
        return structure(c, work_id, sample_chars=min(max(sample_chars, 20), 200))


def book_summary(work_id: str) -> dict:
    from guji.bookstudy import book_summary as summary

    work_id = (work_id or "").strip()
    if not work_id:
        raise ValidationError("work_id 不能为空")
    with deps.corpus() as c:
        return summary(c, work_id)


def book_chapter(work_id: str, scheme: str, *, addr_name: str | None = None,
                 addr1: int | None = None, file: str | None = None,
                 limit: int = 60) -> dict:
    from guji.bookstudy import chapter

    work_id, scheme = (work_id or "").strip(), (scheme or "").strip()
    if not work_id:
        raise ValidationError("work_id 不能为空")
    if not scheme:
        raise ValidationError("scheme 不能为空")
    with deps.corpus() as c:
        return chapter(c, work_id, scheme, addr_name=addr_name, addr1=addr1,
                       file=file, limit=min(max(limit, 1), 200))


# ---------------------------------------------------------------------------
# 占卜域：六爻 / 黄历 / 塔罗
# ---------------------------------------------------------------------------


def liuyao(req) -> dict:
    """六爻起卦（本地计算）+ 卦辞/爻辞引用（zhouyi 语料）+ 确定性解读。"""
    req.validate_ranges()
    if req.method == "coins":
        rng = random.Random(req.seed) if req.seed is not None else random.Random()
        ben = liuyao_mod.cast_coins(rng)
    else:
        try:
            lm = lunar.solar_to_lunar(req.year, req.month, req.day)
        except ValueError as exc:
            raise ValidationError(f"公历转农历失败：{exc}") from exc
        hour_zhi = (req.hour + 1) // 2 % 12 + 1      # 0-23 → 子=1..亥=12
        ben = liuyao_mod.cast_time(lm["year"], lm["month"], lm["day"], hour_zhi)

    bian = liuyao_mod.changing_hexagram(ben)
    with deps.corpus() as c:
        ben_jing = [hit_dict(h) for h in
                    c.at_address(ben.gua_number, layer="經", limit=10)]
        bian_jing = [hit_dict(h) for h in
                     c.at_address(bian.gua_number, layer="經", limit=10)]

    ben_out = liuyao_mod.render_hexagram(ben, "本卦")
    bian_out = liuyao_mod.render_hexagram(bian, "变卦")
    interpretation = interpreter.interpret_liuyao(
        ben_out, bian_out, ben.moving_lines, ben_jing + bian_jing, req.question)
    return {
        "ben": ben_out,
        "bian": bian_out,
        "ben_jing": ben_jing,
        "bian_jing": bian_jing,
        "interpretation": interpretation,
        # 判据 8：六爻原本对提问只回「不代为断事」。warm 分支给出基于**已起出
        # 的卦象**的描述性回应（不预测结果），专业分支原文不动。
        "warm": voice.warm_liuyao(ben_out, bian_out, ben.moving_lines,
                                  interpretation, req.question),
        # R218a-巡2（N-01）：echo question 让前端 liuyaoQuestionHook 真生效
        "question": req.question,
    }


def huangli(date_str: str | None = None, affair: str | None = None,
            days: int = 1) -> dict:
    """黄历择日（本地纯计算）。

    - date=YYYY-MM-DD：单日宜忌坐标（建除/二十八宿/彭祖百忌）
    - affair=婚嫁&days=30：在 [date, date+days) 内找宜该事项的日子
    """
    if date_str:
        try:
            y, m, d = (int(x) for x in date_str.split("-"))
        except Exception:
            raise ValidationError(
                f"date 格式应为 YYYY-MM-DD，收到 {date_str}") from None
        if not (YEAR_LO <= y <= YEAR_HI):
            raise ValidationError(f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {y}")
        if not (1 <= m <= 12):
            raise ValidationError(f"month 须在 1-12，收到 {m}")
        if not (1 <= d <= 31):
            raise ValidationError(f"day 须在 1-31，收到 {d}")
        try:
            dt = datetime(y, m, d)
        except ValueError:
            raise ValidationError(f"非法日期 y={y} m={m} d={d}") from None
    else:
        dt = datetime.now()

    if affair:
        end = dt + timedelta(days=max(days, 1) - 1)
        good = huangli_mod.find_good_days(dt, end, affair)
        return {"affair": affair,
                "start": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
                "days": days, "good_days": good, "count": len(good)}

    q = huangli_mod.day_query(dt)
    # R216b 续6（V-001）：透传农历与冲煞（additive，既有键零改动）。
    return {"date": q["date"], "yi": q["yi"], "ji": q["ji"],
            **({"cross_ref": _cross_ref_huangli(date_str)}),  # C-003：黄历交叉引用
            **({"lunar": q["lunar"]} if q.get("lunar") else {}),
            **({"chongsha": q["chongsha"]} if q.get("chongsha") else {})}


def _draw_dicts(draws) -> list[dict]:
    return [{"index": d.index, "name": d.name, "upright": d.upright,
             "upright_kw": d.upright_kw, "reversed_kw": d.reversed_kw,
             "meaning": d.meaning, "position": d.position,
             "render": d.render()} for d in draws]


def tarot(req) -> dict:
    """塔罗牌阵：78 张静态牌表 + seed 确定性抽牌（固定 seed → 固定牌面）。"""
    draws = tarot_mod.draw(seed=req.seed, n=req.n)
    cards = _draw_dicts(draws)
    interpretation = interpreter.interpret_tarot(cards, req.question)
    return {
        "seed": req.seed,
        "n": len(cards),
        "draws": cards,
        "interpretation": interpretation,
        "warm": voice.warm_tarot(cards, interpretation, req.question),
        # R218a-巡2（N-01）：echo question 让前端 tarotQuestionHook 真生效
        "question": req.question,
    }


def tarot_draw(req) -> dict:
    """单张抽牌 + 确定性关键词转述（首页快速入口用）。

    契约（R178b，D-228b）：顶层键保持与重构前一致的 `card` + `interpretation`
    两个。原第三个键 `model`（LLM 模型名）随 LLM 层移除而消失——引擎标识
    改由 `interpretation.engine` 携带，不再单独占一个顶层键。
    **不新增 `draws` 键**：多张牌阵是 `/api/tarot` 的职责，本端点只给单张，
    否则同一份牌面在两个键里各存一份，前端不知该信哪个。
    """
    draws = tarot_mod.draw(seed=req.seed, n=req.n)
    if not draws:
        raise ComputeError("抽牌失败")
    cards = _draw_dicts(draws)
    card = cards[0]
    interpretation = interpreter.interpret_tarot(cards, req.question)
    return {
        "card": {"name": card["name"], "upright": card["upright"],
                 "upright_kw": card["upright_kw"],
                 "reversed_kw": card["reversed_kw"],
                 "meaning": card["meaning"]},
        "interpretation": interpretation,
        "warm": voice.warm_tarot(cards, interpretation, req.question),
    }


# ---------------------------------------------------------------------------
# 产品域：每日运势 / 功能卡片 / 分享 / 偏好 / 收藏 / 外部资讯
# ---------------------------------------------------------------------------

ZODIAC = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")

# R214b：年轻化文案库（dots 生成 + 人工审校，确定性抽取——按日期哈希选条，
# 同一天全站同一句，可复现；无随机、不读时钟以外的 IO）。
_COPY_BANK_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src", "guji", "copy_bank.json")
try:
    with open(_COPY_BANK_PATH, encoding="utf-8") as _f:
        _COPY_BANK = json.load(_f)
except Exception:
    _COPY_BANK = {}


def _pick(seq, *salt) -> str:
    """从文案池确定性抽一条：sha1(盐) 稳定映射，同输入必同输出。"""
    if not seq:
        return ""
    h = hashlib.sha1("|".join(str(s) for s in salt).encode("utf-8")).hexdigest()
    return seq[int(h[:8], 16) % len(seq)]

_LEVEL_ADVICE = {
    "吉": ("宜合作、宜出行、宜做决定", "忌大意、忌拖延"),
    "凶": ("宜静养、宜守成、宜反思", "忌冲动、忌远行、忌争执"),
    "平": ("宜合作、宜静养、宜学习", "忌冲动、忌远行"),
}

_BAD_RELS = ("相害", "相刑", "自刑", "相冲")
_GOOD_RELS = ("六合", "三合", "半合")


def chinese_zodiac(year: int) -> str:
    return ZODIAC[(year - 4) % 12]


def fortune_level(calc_out: dict) -> str:
    """从运算事实推算运势等级（吉/平/凶）——结构化判断，非关键词匹配。"""
    if not calc_out:
        return "平"
    score = 0
    fe = calc_out.get("five_elements") or {}
    if len(fe.get("strong") or []) >= 2:
        score -= 1                                  # 两行偏旺，五行失衡
    if fe.get("missing"):
        score -= 1                                  # 缺行
    for r in calc_out.get("relations") or []:
        t = r.get("type", "")
        if t in _BAD_RELS:
            score -= 1
        elif t in _GOOD_RELS or t == "相生":
            score += 1
    for dr in (calc_out.get("day_luck") or {}).get("day_branch_rels") or []:
        t = dr.get("type", "")
        if t in ("相害", "相刑", "相冲"):
            score -= 1
        elif t in _GOOD_RELS:
            score += 1
    gods = [t.get("god", "") for t in calc_out.get("ten_gods") or []]
    if any(g in ("七杀", "伤官") for g in gods):
        score -= 1                                  # 压力大
    if any(g in ("正印", "偏印", "正官") for g in gods):
        score += 1                                  # 有贵人
    if score >= 2:
        return "吉"
    return "凶" if score <= -2 else "平"


def fortune_summary(calc_out: dict) -> str:
    """从运算事实转述运势一句话（纯坐标转述，不新增结论）。"""
    if not calc_out:
        return "今天运势数据暂不可用"
    # R216b 续3（UX 队列 U-010）：原版「五行中火土偏旺；有1处地支自刑，
    # 宜稳不宜争；今日日运：庚午」术语裸抛——每条跟一句人话短注。
    parts = []
    strong = (calc_out.get("five_elements") or {}).get("strong") or []
    if strong:
        parts.append(f"{'+'.join(strong)}气比较足——这方面的特质今天更明显")
    rels = calc_out.get("relations") or []
    bad = [r for r in rels if r.get("type") in _BAD_RELS]
    good = [r for r in rels if r.get("type") in _GOOD_RELS]
    if bad:
        parts.append(f"有{len(bad)}处别扭的小关系"
                     f"{'/'.join(r['type'] for r in bad[:2])}——"
                     f"容易自己跟自己较劲，稳一点就好")
    if good:
        parts.append(f"也有{len(good)}处顺劲"
                     f"{'/'.join(r['type'] for r in good[:2])}——有人搭把手，事情好推")
    day_gz = (calc_out.get("day_luck") or {}).get("day_ganzhi", "")
    if day_gz:
        parts.append(f"今天的干支是{day_gz}")
    if not parts:
        return "今天五行平和，无大冲大合，平平稳稳就是福 ✨"
    return "；".join(parts) + "。"


def daily(date_str: str | None = None) -> dict:
    """每日运势卡片：等级 + 一句话 + 贵人属相 + 宜忌，命中 daily_cache 表。

    R178b（D-229b）：`date` 现在是**查询参数**。重构前它声明为请求体模型
    （`req: DailyRequest = DailyRequest()`），于是 `GET /api/daily?date=…`
    的查询串被完全忽略——实测旧实现对 `?date=2026-03-03` 永远返回今天，
    只有往 GET 里塞 JSON body 才生效。那是 bug 不是契约，本轮修正为查询参数。

    非法日期在此**边界即拒**（400），不进入计算：否则 `?date=garbage` 会在
    `daily_cache` 里落一条 key 为 garbage 的脏行（旧实现因忽略参数而碰巧
    没有这个问题，改成查询参数后必须显式挡住）。
    """
    if date_str is not None:
        try:
            date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError(
                f"date 需为 YYYY-MM-DD 格式，收到 {date_str}") from None
    date_str = date_str or date.today().isoformat()
    with deps.knowledge() as kb:
        cached = kb.get_daily_cache(date_str)
        if cached and cached.get("bazi"):
            # R195b（B-017 缓存版本化）：daily_cache 无版本列，改用
            # 「值校验」识别旧语义缓存——noble 若不等于当日天乙贵人
            # （B-017 修复前存的是当年生肖），视为过期走下方重算覆盖。
            _c = cached["bazi"]
            try:
                _d0 = date.fromisoformat(date_str)
                _want = "/".join(huangli_mod.guiren(
                    datetime(_d0.year, _d0.month, _d0.day, 12)))
            except Exception:
                _want = None
            if not _want or _c.get("noble") == _want:
                return {"date": date_str, **_c, "cached": True}
    try:
        d = date.fromisoformat(date_str)
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        calc_out = bazi_calc(b)
        level = fortune_level(calc_out)
        do_str, dont_str = _LEVEL_ADVICE[level]
        # R214b：宜忌换年轻化表达（文案库优先，缺失回退旧表）。
        _db = _COPY_BANK.get("daily") or {}
        if _db:
            lvl_key = level if level in _db.get("levels", {}) else (
                "平" if level == "平" else level)
            summary = _pick(_db["levels"].get(lvl_key) or [], date_str, "sum")
            do_str = _pick(_db["yi"], date_str, "y") + "、" + \
                _pick(_db["yi"], date_str, "y2")
            dont_str = _pick(_db["ji"], date_str, "j") + "、" + \
                _pick(_db["ji"], date_str, "j2")
        # B-017（R195b 清偿）：旧值 chinese_zodiac(d.year) 是「今年的生肖」，
        # 与「贵人」无关（B-003 登记的语义缺陷）。改为当日日干的天乙贵人
        # （huangli.guiren，与黄历页同一算法、同一出处）——
        # 传统语义里「今日贵人」本就按日干推。键名仍为 noble（契约不变），
        # 值从单属相变为「丑/未」形式的双地支。
        try:
            _gr = huangli_mod.guiren(
                datetime(d.year, d.month, d.day, 12))
            noble_str = "/".join(_gr) if _gr else "—"
        except Exception:
            noble_str = "—"
        result = {
            "date": date_str,
            "level": level,
            "summary": (summary if (_db and level in (_db.get("levels") or {}))
                        else fortune_summary(calc_out)),
            "noble": noble_str,
            "do": do_str,
            "dont": dont_str,
            "cached": False,
        }
        with deps.knowledge() as kb:
            kb.set_daily_cache(date_str, bazi=result)
        return result
    except Exception as exc:                        # 计算失败降级为"平"，不 500
        return {"date": date_str, "level": "平", "summary": f"计算失败：{exc}",
                "noble": "—", "do": "—", "dont": "—", "cached": False}


MODULES = (
    {"id": "bazi", "icon": "🔮", "title": "八字排盘",
     "desc": "排出四柱 · 看五行大运流年", "recent": "八字排盘"},
    {"id": "book", "icon": "📜", "title": "古籍读书",
     "desc": "检索 47 部古籍 · 比对注家", "recent": "古籍检索"},
    {"id": "tarot", "icon": "✨", "title": "塔罗占卜",
     "desc": "抽牌看指引 · 解答心中疑问", "recent": "塔罗占卜"},
    {"id": "huangli", "icon": "🌙", "title": "黄历择日",
     "desc": "看建除神煞 · 选吉日", "recent": "黄历查询"},
    {"id": "qiming", "icon": "🌸", "title": "五行起名",
     "desc": "按五行补缺 · 起一个好名字", "recent": "起名"},
    {"id": "taohua", "icon": "🌺", "title": "桃花运",
     "desc": "看看近期桃花走势 🌹", "recent": "桃花"},
    {"id": "liuyao", "icon": "🔮", "title": "六爻占卜",
     "desc": "摇卦断事 · 看事情走向", "recent": "六爻"},
    {"id": "hehun", "icon": "💕", "title": "八字合婚",
     "desc": "两人八字合婚 · 看缘分", "recent": "合婚"},
)


def _recent_list(kb) -> list:
    try:
        return json.loads(kb.get_pref("recent_modules", "[]") or "[]")
    except (ValueError, TypeError):
        return []


def widget() -> dict:
    """首页功能卡片数据：各模块图标/标题/描述 + 最近使用标记。"""
    with deps.knowledge() as kb:
        recent = _recent_list(kb)
    modules = [dict(m, recent_used=m["id"] in recent) for m in MODULES]
    return {"modules": modules, "recent": recent}


SHARE_COLORS = {"bazi": "#B8860B", "tarot": "#9D4EDD",
                "book": "#5B8C5A", "thread": "#C43E3E"}


def share(share_type: str, share_id: str) -> dict:
    """分享卡片数据：可截图分享的结果摘要。"""
    today = date.today().isoformat()
    if share_type == "bazi":
        with deps.knowledge() as kb:
            try:
                d = kb.get(int(share_id))
            except (TypeError, ValueError):
                d = None
            if not d:
                raise NotFoundError("未找到")
            return {"title": "八字排盘结果", "subtitle": d.claim[:60],
                    "content": d.claim, "image_color": SHARE_COLORS["bazi"],
                    "created_at": d.created_at}
    if share_type == "tarot":
        return {"title": "塔罗占卜结果", "subtitle": share_id,
                "content": "塔罗牌阵解读", "image_color": SHARE_COLORS["tarot"],
                "created_at": today}
    if share_type == "book":
        return {"title": "读书笔记", "subtitle": share_id,
                "content": "古籍研究笔记", "image_color": SHARE_COLORS["book"],
                "created_at": today}
    raise NotFoundError(f"不支持的分享类型: {share_type}")


def user_prefs() -> dict:
    with deps.knowledge() as kb:
        return {"theme": kb.get_pref("theme", "cream"),
                "recent": _recent_list(kb),
                "favorites": [dict(r) for r in kb.list_favorites()]}


def set_user_prefs(payload: dict) -> dict:
    with deps.knowledge() as kb:
        for k, v in (payload or {}).items():
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            kb.set_pref(k, v)
    return {"ok": True}


def add_favorite(req) -> dict:
    with deps.knowledge() as kb:
        return {"id": kb.add_favorite(req.type, req.ref_id, req.title),
                "ok": True}


def remove_favorite(fid: int) -> dict:
    with deps.knowledge() as kb:
        kb.remove_favorite(fid)
    return {"ok": True}


def external_news() -> dict:
    """外部资讯通道：抓预置 RSS/Atom 源。不落库、不写 history——"最新消息"
    是即时信息，与古籍语料 Source 层严格隔离。单源失败自动降级。"""
    try:
        return external_feed.fetch_sources(max_sources=6)
    except Exception as exc:
        return {"fetched_at": None, "proxy": external_feed.PROXY,
                "sources": [], "error": f"{type(exc).__name__}: {exc}"}


def external_fortune() -> dict:
    """外部资讯的运势风格包装（每日运势卡片的外部资讯部分）。"""
    try:
        return external_feed.fortune_wrap(external_feed.fetch_sources(max_sources=4))
    except Exception as exc:
        return {"date": None, "ok": False, "items": [],
                "summary": f"外部资讯暂时 unavailable：{exc}"}


def health() -> dict:
    """健康检查：解读引擎恒可用（确定性规则，无 LLM、无网络、无 key）。"""
    return {"ok": True, "engine": interpreter.configured_model(),
            "index": os.path.exists(deps.CORPUS_DB)}


# C-003：交叉引用辅助函数
def _cross_ref_bazi(b, gender: str) -> dict:
    """八字结果页的星座交叉引用。"""
    from guji.xingzuo import daily_horoscope
    try:
        h = daily_horoscope(b.day)
        today = h.get("today_sign", "")
        return {
            "zodiac_sign": today,
            "zodiac_note": h.get("today_note", ""),
            "message": f"你的太阳星座是{today}，今天{h.get('today_note', '')}"
        }
    except Exception:
        return {}


def _cross_ref_hehun(ba, bb) -> dict:
    """合婚结果页的星座配对引用。"""
    from guji.xingzuo import daily_horoscope
    try:
        ha = daily_horoscope(ba.day)
        hb = daily_horoscope(bb.day)
        return {
            "zodiac_a": ha.get("today_sign", ""),
            "zodiac_b": hb.get("today_sign", ""),
            "message": f"你们太阳星座是{ha.get('today_sign', '')}与{hb.get('today_sign', '')}，星座相处建议：{ha.get('today_note', '')}"
        }
    except Exception:
        return {}


def _cross_ref_huangli(date_str: str) -> dict:
    """黄历结果页的八字个性化引用。"""
    from guji.xingzuo import daily_horoscope
    try:
        from datetime import date as _date
        d = _date.fromisoformat(date_str) if date_str else _date.today()
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        h = daily_horoscope(b.day)
        return {
            "zodiac_sign": h.get("today_sign", ""),
            "zodiac_note": h.get("today_note", ""),
            "message": f"今天{h.get('today_sign', '')}当值，{h.get('today_note', '')}"
        }
    except Exception:
        return {}
