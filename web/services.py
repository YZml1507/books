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

import functools
import hashlib
import json
import os
import random
import logging
import re
import sqlite3
from datetime import date, datetime, timedelta

_logger = logging.getLogger("books")

from guji import external as external_feed
# R219b（P0-4）：`from guji import history as history_db` 随历史记录功能删除
# ——web 层不再有任何 history_db 调用点（模块文件本体保留，见文件下方注释）。
from guji import huangli as huangli_mod
from guji import hehun as hehun_mod
from guji import interpreter
from guji import liuyao as liuyao_mod
from guji import llm_polish
from guji import lunar
from guji import paipan_history
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


def _require_q(q: str | None, *, what: str = "查询词不能为空") -> str:
    q = (q or "").strip()
    if not q:
        raise ValidationError(what)
    if len(q) > 200:
        raise ValidationError("查询词过长（≤200 字符）")
    return q


def _friendly_calc_err(exc: Exception) -> str:
    """把已知的 Python 日期/历法 ValueError 翻成人话（R229c，R5 审计 P1）。

    此前 `排盘失败：{exc}` 把 'day is out of range for month' 这种原文直接
    上屏——非法日期组合（2 月 31 日）走的是这条路。其它未知异常仍带原文
    便排查，但包住的是英文时用户看到的是乱码感。"""
    s = str(exc)
    if "day is out of range for month" in s or "day is out of range" in s:
        return "这一天不存在，换个日期试试"
    if "month must be in" in s:
        return "月份须在 1-12"
    if "year is out of range" in s or "date value out of range" in s:
        return "这个年份超出可算范围了"
    if "hour" in s.lower() and "range" in s.lower():
        return "时辰不对，换个时间试试"
    # R229n（R6-#12）：未匹配的异常原文不再上屏——用户只见泛化中文，
    # 原文进日志便排查（异常含堆栈外信息时尤其不能吐）。
    _logger.warning("calc error not humanized: %s", s)
    return "这一步没算成，换个日期或输入再试试"


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
        # R228p：农历 2100 年腊月换算到公历会溢出到 2101-01/02——
        # 下游干支/节气走天文算法（不受农历表 2100 界限制），此处按
        # YEAR_HI+1 放行；农历输入年本身仍由 lunar_to_solar 的表界把守。
        if not (YEAR_LO <= d.year <= YEAR_HI + 1):
            raise ValidationError(
                f"换算后公历年份需在 {YEAR_LO}-{YEAR_HI + 1} 之间")
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
        raise ComputeError(f"排盘失败：{_friendly_calc_err(exc)}") from exc

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
    # 排盘历史台账（2026-08-28，additive）：组装完整响应后异步落库，
    # 绝不影响主响应；BOOKS_PAIPAN_HISTORY_DISABLE=1 或写库失败均静默。
    out = {
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
        # R220b：太阳星座按【出生月日】判定，不再拿日支当本命星座。
        # 必须用 resolve_birth 换算后的公历 bm/bd——农历输入下 req.month/req.day
        # 是农历值，直接拿去查黄道边界会算错座。
        "cross_ref": _cross_ref_bazi(b, req.gender, bm, bd),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }
    paipan_history.save_async({
        "year": req.year, "month": req.month, "day": req.day,
        "hour": req.hour, "gender": req.gender,
        "calendar_type": req.calendar_type,
        "lunar_year": req.lunar_year, "lunar_month": req.lunar_month,
        "lunar_day": req.lunar_day, "lunar_leap": req.lunar_leap,
        "scope": req.scope, "question": req.question,
    }, out)
    return out


def taohua(req) -> dict:
    """八字桃花运：咸池/红鸾/天喜 纯坐标计算（固定生日 → 固定输出）。"""
    req.validate_ranges()
    by, bm, bd = resolve_birth(req)
    try:
        b = bazi_compute(by, bm, bd, req.hour, req.gender)
        t = taohua_mod.compute(b)
        dayun = taohua_mod.dayun_hits(b, by)
    except Exception as exc:
        raise ComputeError(f"排盘失败：{_friendly_calc_err(exc)}") from exc
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
        # R220b：交叉引用铺到桃花——星座桃花信号 × 八字强度叠加
        "cross_ref": _cross_ref_taohua(bm, bd, t.strength),
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
        raise ComputeError(f"排盘失败：{_friendly_calc_err(exc)}") from exc
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
        # R220b：按双方出生月日取真实太阳星座（原来用日支，配对结论是假的）
        "cross_ref": _cross_ref_hehun(ba, bb,
                                     (req.a_month, req.a_day),
                                     (req.b_month, req.b_day)),
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
            seed=req.seed, style=getattr(req, "style", "all"))
    except Exception as exc:
        raise ValidationError(f"起名计算失败：{_friendly_calc_err(exc)}") from exc
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(llm_polish.facts_qiming(out, req.gender))
    out["ai_polish"] = ai_polish
    # R220b：交叉引用铺到起名——太阳星座气质给挑名字一个参考角度
    out["cross_ref"] = _cross_ref_qiming(req.month, req.day)
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    return out


def xingzuo(date_str: str | None = None) -> dict:
    """十二宫日运（004 M2 T2.3）：当日日支查宫 + 12 宫一句话 + 语料锚点。

    纯坐标 + 写死文案 + 真实引文锚点（fixture 逐字命中，判据 10/11）。
    """
    if date_str is not None:
        try:
            _parsed = date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError(
                f"日期需为 YYYY-MM-DD 格式，收到 {date_str}") from None
        # R228b：星历表有覆盖区间——极值年份（如 9999）会一路炸进
        # bazi_compute 报 ValueError → 未映射 500。边界即拒为 400。
        if not (YEAR_LO <= _parsed.year <= YEAR_HI):
            raise ValidationError(
                f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {_parsed.year}")
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
    q = _require_q(q, what="查询词不能为空——检索需要查询词；找某个地址请用 /api/addr")
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
        raise ValidationError(f"编址类型只能是 {'/'.join(deps.SCHEME_LABELS)}")
    limit = min(max(limit, 1), 100)
    with deps.corpus() as c:
        if scheme == "zhouyi":
            if gua is None:
                raise ValidationError("zhouyi 定位需提供卦号（1–64）")
            hits = c.at_address(gua, yao, layer=layer, limit=limit)
        else:
            hits = c.at_scheme(scheme, addr_name=addr_name, addr1=addr1,
                               addr2=addr2, layer=layer, limit=limit)
        return {"scheme": scheme, "count": len(hits),
                "hits": [hit_dict(h) for h in hits]}


def compare(gua: int, yao: str = "九三", layer: str = "經") -> dict:
    """跨版本同址比对 + 差异摘要（复用 compare.compare_address）。"""
    if not (1 <= gua <= 64):
        raise ValidationError("卦号需在 1–64")
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
        raise ValidationError("地址数需在 1-6")
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
        raise ValidationError("两本书的书号不能为空")
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
    """写入一条 derived claim（G8 纪律：断言型 kind 必须带证据）。

    R228s（线程创建语义修复）：thread_id 缺席时自动开新线程并把 claim
    绑上去——此前不落 thread_id 的 claim 是孤儿行，GET /api/threads 只列
    thread 表，前端「新建线程」按钮创建了永远不出现在列表里的幽灵 claim。
    """
    from guji.knowledge import ASSERTING, Evidence

    # R229n（R6-#2）：先校验后开线程——此前 open_thread/add_turn 各自
    # commit 落库后 record() 才校验 kind 抛 400，留下永不回收的孤儿
    # thread+turn（selftest kind=bogus 用例实测留行）。
    if req.kind not in ASSERTING + ("refusal",):
        raise ValidationError("记录被拒绝：类型或内容不合规")
    if req.kind in ASSERTING and not req.evidence:
        raise ValidationError("记录被拒绝：断言型记录需要至少一条证据")

    with deps.knowledge() as kb:
        tid = req.thread_id
        if tid is None:
            topic = (req.topic or req.claim[:50] or "新线程").strip()[:100]
            tid = kb.open_thread(topic)
            kb.add_turn(tid, "user", "开题：" + topic)
        ev = [Evidence(work_id=e.work_id, file=e.file,
                       raw_start=e.raw_start if e.raw_start is not None else -1,
                       raw_end=e.raw_end if e.raw_end is not None else -1,
                       quote=e.quote, page_anchor=e.page_anchor,
                       scheme=e.scheme, addr1=e.addr1, addr2=e.addr2,
                       role=e.role)
              for e in req.evidence]
        try:
            did = kb.record(req.kind, req.claim, req.method, ev,
                            confidence=req.confidence, thread_id=tid)
        except (ValueError, sqlite3.IntegrityError) as exc:
            # 非法 kind 触发 DB CHECK 约束的 IntegrityError；与其余端点
            # 「非法参数 → 400」纪律一致（R159b/D-205b）。
            # R228j：不把 sqlite 原文（"CHECK constraint failed: ..."）吐给用户，
            # 内部约束名属实现细节——翻成中文人话。
            raise ValidationError("记录被拒绝：类型或内容不合规") from exc
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
        raise ValidationError("书号不能为空")
    with deps.corpus() as c:
        return structure(c, work_id, sample_chars=min(max(sample_chars, 20), 200))


def book_summary(work_id: str) -> dict:
    from guji.bookstudy import book_summary as summary

    work_id = (work_id or "").strip()
    if not work_id:
        raise ValidationError("书号不能为空")
    with deps.corpus() as c:
        return summary(c, work_id)


def book_chapter(work_id: str, scheme: str, *, addr_name: str | None = None,
                 addr1: int | None = None, file: str | None = None,
                 limit: int = 60) -> dict:
    from guji.bookstudy import chapter

    work_id, scheme = (work_id or "").strip(), (scheme or "").strip()
    if not work_id:
        raise ValidationError("书号不能为空")
    if not scheme:
        raise ValidationError("编址类型不能为空")
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
        # R221b：交叉引用收口 7/7——六爻不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_liuyao(ben.moving_lines),
    }


def huangli(date_str: str | None = None, affair: str | None = None,
            days: int = 1) -> dict:
    """黄历择日（本地纯计算）。

    - date=YYYY-MM-DD：单日宜忌坐标（建除/二十八宿/彭祖百忌）
    - affair=婚嫁&days=30：在 [date, date+days) 内找宜该事项的日子
    """
    # R228p：手写 split('-') 校准器退役——与 xingzuo/daily 同走
    # _parse_iso_date（fromisoformat 对月日越界天然 400，三段校验不再需要）。
    dt = (datetime(_d.year, _d.month, _d.day)
          if (_d := _parse_iso_date(date_str) if date_str else None)
          else datetime.now())

    if affair:
        # R228b：days 不设上限时 find_good_days 逐日扫描线性放大
        # （实测 365 天≈21s）——服务层兜底钳位，与路由 Query(le=92) 同值。
        days = max(1, min(int(days), 92))
        end = dt + timedelta(days=days - 1)
        # R228x：口语词归一——「理发/养猫」不在宜忌词表里，精确匹配恒空；
        # 与聊天/问一嘴同走 _CHAT_SCENE_TERMS 拿规范词集合，逐词找日
        # 后按日期并集（一事项多规范词：搬家→移徙+入宅+修造）。
        terms = _CHAT_SCENE_TERMS.get(affair) or [affair]
        by_date: dict[str, dict] = {}
        for _t in terms:
            for _q in huangli_mod.find_good_days(dt, end, _t):
                by_date.setdefault(_q["date"], _q)
        good = [by_date[k] for k in sorted(by_date)]
        return {"affair": affair, "terms": terms,
                "start": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
                "days": days, "good_days": good, "count": len(good)}

    q = huangli_mod.day_query(dt)
    # R216b 续6（V-001）：透传农历与冲煞（additive，既有键零改动）。
    # R228p：jianchu/xiu/pengzu/shensha 本来就算好了却被丢掉——单日响应
    # 补透传（additive）。它们是传统黄历的核心坐标，前端将来可直接取。
    return {"date": q["date"], "yi": q["yi"], "ji": q["ji"],
            "jianchu": q.get("jianchu"), "xiu": q.get("xiu"),
            "pengzu": q.get("pengzu"), "shensha": q.get("shensha"),
            **({"cross_ref": _cross_ref_huangli(date_str)}),  # C-003：黄历交叉引用
            **({"lunar": q["lunar"]} if q.get("lunar") else {}),
            **({"chongsha": q["chongsha"]} if q.get("chongsha") else {})}


# ---------------------------------------------------------------------------
# 小满聊天的黄历上下文（R227b，用户反馈「不能照本宣科」）
#
# 用户在「聊聊这件事」里问「今天适合出行吗」时，原先的 facts 只有前端透传的
# 宜/忌原始列表——事项不在榜上时 LLM 只能照本宣科一句「黄历没提」。
# 这里在后端把判定**先算出来**再交给小满：命中宜→宜、命中忌→忌、都没列→
# 中性（不是不支持），并附「近 45 天宜该事的日子」——想要黄历背书有处可去。
# ---------------------------------------------------------------------------

# 口语事项 → 黄历规范词（与前端 app.js HL_SCENE_ALIAS 同源口径，各存一份：
# 前端管「问一嘴」即时判定，这里管小满聊天的事实供给）。
_CHAT_SCENE_TERMS: dict[str, list[str]] = {
    "面试": ["上任"], "求职": ["上任"], "上班": ["上任"], "入职": ["上任"],
    "约会": ["嫁娶"], "表白": ["嫁娶"], "相亲": ["嫁娶"], "结婚": ["嫁娶"],
    "领证": ["嫁娶"],
    "搬家": ["移徙", "移徒", "入宅", "修造"], "挪窝": ["移徙", "移徒"],
    "装修": ["修造", "动土"], "动工": ["动土", "破土"],
    "开业": ["开市", "纳财"], "开张": ["开市"],
    "签约": ["立券", "纳财"], "合同": ["立券"],
    "出行": ["出行", "远行"], "旅行": ["出行", "远行"],
    "旅游": ["出行", "远行"], "出差": ["出行", "远行"], "出游": ["出行", "远行"],
    "收款": ["纳财"], "理财": ["纳财"], "看病": ["求医", "治病", "求医疗病"],
    "种花": ["栽植", "栽种"], "种菜": ["栽种"], "许愿": ["祈福", "求嗣"],
    "拜拜": ["祭祀"],
    "考试": ["入学"], "上学": ["入学"], "开学": ["入学"],
    "和解": ["解除"], "打官司": ["诉讼"], "诉讼": ["诉讼"],
    # R228r：词表外口语补齐（审查轨 chat-flow）——词汇里没有对应规范词的，
    # 映射到自身，落进「没为它背书」的中性卡而不是裸跳 [] 让 LLM 空答。
    "理发": ["冠笄"], "剪发": ["冠笄"], "剪头": ["冠笄"], "剃头": ["冠笄"],
    "美发": ["冠笄"], "烫头": ["冠笄"],
    "手术": ["求医", "治病", "求医疗病"], "开刀": ["求医"],
    "体检": ["求医"], "洗牙": ["求医"], "拔牙": ["求医"],
    "医美": ["求医"], "整容": ["求医"],
    "借钱": ["纳财"], "讨债": ["纳财"], "还钱": ["纳财"], "还贷": ["纳财"],
    "辞职": ["解除"], "离职": ["解除"], "跳槽": ["解除"], "换工作": ["解除"],
    "解除合同": ["解除"], "毁约": ["解除"], "退婚": ["解除"], "分手": ["解除"],
    # 「说拜拜/拜拜了」口语是散伙不是祭祀（词表「拜拜」仍归祭祀——
    # 长键先中，「说拜拜」优先落这里）
    "说拜拜": ["解除"], "拜拜了": ["解除"], "再见": ["解除"],
    "出国": ["出行", "远行"], "出门": ["出行", "远行"],
    "宠物": ["进人口"], "养猫": ["进人口"], "养狗": ["进人口"],
    "钓鱼": ["捕捉"], "捕捞": ["捕捉"],
    "聚餐": ["聚餐"], "请客": ["请客"], "聚会": ["聚会"], "饭局": ["饭局"],
    "购物": ["购物"], "买东西": ["购物"], "逛街": ["逛街"],
    "健身": ["健身"], "运动": ["健身"], "唱歌": ["唱歌"], "唱k": ["唱歌"],
}

# 黄历宜忌规范词全集——直接命中这些词也按事项处理。词表由建除/宿值两张
# 通行规则表自动汇成（day_query 的 yi/ji 只出自这两张表），不另写死。
_HUANGLI_VOCAB: frozenset = frozenset(
    w for d in (*huangli_mod.ZHIRI_YIJI.values(), *huangli_mod.XIUXIU_YIJI.values())
    for w in (*d["yi"], *d["ji"]))
# R228m：frozenset 迭代序跨进程不稳定（PYTHONHASHSEED）——候选词表固定为
# 「长词优先、同长字典序」的 tuple，同一消息在不同进程必选同一事项词。
_HUANGLI_VOCAB_ORD: tuple = tuple(
    sorted(_HUANGLI_VOCAB, key=lambda t: (-len(t), t)))


_WEEKDAY = "一二三四五六日天"


def _wd_idx(ch: str) -> int:
    """曜日字 → weekday 索引（一=0..日=6；「天」在串尾 index=7，同周日）。"""
    i = _WEEKDAY.find(ch)
    return 6 if i > 6 else i

# R229d：繁中问句归一——「明天適合簽約嗎」此前 _CHAT_SCENE_TERMS 全简体
# 打不中（事实行缺席 → LLM 自由发挥）。只映射问句域常见字，与前端
# app.js _T2S 同表；未映射字原样通过（宁缺毋滥不错转）。
_T2S = {
    "適": "适", "嗎": "吗", "麼": "么", "會": "会", "個": "个", "這": "这",
    "裡": "里", "裏": "里", "對": "对", "說": "说", "話": "话", "問": "问",
    "聽": "听", "來": "来", "時": "时", "現": "现", "點": "点", "頭": "头",
    "髮": "发", "換": "换", "簽": "签", "約": "约", "結": "结", "證": "证",
    "領": "领", "裝": "装", "張": "张", "業": "业", "職": "职", "學": "学",
    "試": "试", "遠": "远", "遊": "游", "國": "国", "門": "门", "間": "间",
    "錢": "钱", "財": "财", "買": "买", "賣": "卖", "價": "价", "醫": "医",
    "藥": "药", "養": "养", "貓": "猫", "魚": "鱼", "鳥": "鸟", "種": "种",
    "運": "运", "氣": "气", "勢": "势", "曆": "历", "歷": "历", "黃": "黄",
    "還": "还", "見": "见", "長": "长", "親": "亲", "屬": "属", "喪": "丧",
    "動": "动", "離": "离", "準": "准", "備": "备", "處": "处", "幾": "几",
    "緊": "紧", "擇": "择", "幹": "干", "臺": "台", "週": "周", "禮": "礼",
    "樣": "样",
}


def _t2s(s: str) -> str:
    return "".join(_T2S.get(ch, ch) for ch in s)


def _hl_day_part(msg: str, now: datetime) -> tuple[datetime, str]:
    """消息里的相对日（明天/后天/昨天/下周X/周末…），默认今天。

    返回 (目标日期, 用户原词)——原词要写进事实行（「下周三（9/23）的黄历…」），
    否则 LLM 不知道用户说的「下周三」是哪一天，会自己换算出错误日期
    （R228w 实测：9/19 说「下周三」，模型答成 9/30）。

    R228r（chat-flow 审查）：原先只有明天/后天/大后天三档，昨天/下周X/周末
    静默按今天判——说错日期比不答更伤（用户拿「明天」的答案去安排「下周」）。
    """
    if "大后天" in msg or "大後天" in msg:
        return now + timedelta(days=3), "大后天"
    if "大前天" in msg:
        return now - timedelta(days=3), "大前天"
    if "后天" in msg or "後天" in msg:
        return now + timedelta(days=2), "后天"
    if "过两天" in msg or "過兩天" in msg:
        return now + timedelta(days=2), "过两天"
    if "前天" in msg:
        return now - timedelta(days=2), "前天"
    if "明天" in msg or "明日" in msg:
        return now + timedelta(days=1), "明天"
    if "明儿" in msg or "明兒" in msg:
        return now + timedelta(days=1), "明儿"
    # R229h：晚字辈（明晚/后晚/今晚/昨晚）与对应「天」同档——黄历按天判。
    if "明晚" in msg:
        return now + timedelta(days=1), "明晚"
    if "后晚" in msg or "後晚" in msg:
        return now + timedelta(days=2), "后晚"
    if "今晚" in msg or "今夜" in msg:
        return now, "今晚"
    if "昨晚" in msg:
        return now - timedelta(days=1), "昨晚"
    if "昨天" in msg or "昨日" in msg:
        return now - timedelta(days=1), "昨天"
    # R229f：「本周X/这周X」此前根本没解析——静默按今天判（R228r 同类：
    # 说错日期比不答更伤）。本周一=0 基准；结果为负即本周已过的日子。
    for anchor in ("本周", "这周", "本週", "這週", "这週", "這周"):
        if anchor in msg:
            idx = msg.find(anchor) + len(anchor)
            if idx < len(msg) and msg[idx] in _WEEKDAY:
                wd = _wd_idx(msg[idx])
                return now + timedelta(days=wd - now.weekday()), msg[msg.find(anchor):idx + 1]
            break  # 「本周」无曜日字 → 不落下面 周末/今天 兜底，交给默认今天
    # R229e：「下周末/下週末」必须先于「下周」通配——否则「末」非曜日字，
    # 落进通用分支被吃成下周一，而用户说的是下周的周六。
    for anchor in ("下周末", "下週末"):
        if anchor in msg:
            next_mon = now + timedelta(days=(7 - now.weekday()))
            return next_mon + timedelta(days=5), "下周末"
    # 下周X / 下礼拜X：以下个周一为基准的 X 曜日
    for anchor in ("下周", "下週", "下礼拜", "下禮拜"):
        if anchor in msg:
            idx = msg.find(anchor) + len(anchor)
            if idx < len(msg) and msg[idx] in _WEEKDAY:
                wd = _wd_idx(msg[idx])
                next_mon = now + timedelta(days=(7 - now.weekday()))
                _d = next_mon + timedelta(days=wd)
                return _d, msg[msg.find(anchor):idx + 1]
            # 「下周」没跟曜日——按下个周一算
            return now + timedelta(days=(7 - now.weekday())), "下周"
    # 周末：下一个周六（今天已是周末则指今天）
    if "周末" in msg or "週末" in msg:
        gap = (5 - now.weekday()) % 7
        return now + timedelta(days=gap), "周末"
    # R229h：裸曜日词「周五/礼拜天/星期日」= 最近的那个（今天命中即今天），
    # 不落在下周/本周之后误判。负向词（下周/本周）已在上面消化，这里只接
    # 无前缀的写法。
    m = re.search(r"(周|週|礼拜|禮拜|星期)([一二三四五六日天])", msg)
    if m:
        wd = _wd_idx(m.group(2))
        return now + timedelta(days=(wd - now.weekday()) % 7), m.group(0)
    return now, "今天"


def _hl_next_yi_days(dt: datetime, terms: list[str],
                   span: int = 45, limit: int = 4) -> list[str]:
    """[dt, dt+span) 内宜任一规范词的日子（并集），返回 "M/D" 列表。"""
    out: list[str] = []
    cur = dt
    for _ in range(span):
        if any(t in huangli_mod.day_query(cur)["yi"] for t in terms):
            out.append(f"{cur.month}/{cur.day}")
            if len(out) >= limit:
                break
        cur += timedelta(days=1)
    return out


def chat_huangli_facts(message: str, now: datetime | None = None) -> list[str]:
    """小满聊天的黄历事实供给：先把「适不适合」算成判定再交给 LLM。

    消息提到黄历事项词（口语词或规范词）→ 当日宜忌 + 判定 + 近期吉日；
    只泛问黄历（「今天宜做什么」「看看黄历」）→ 当日宜忌 + 中性口径说明；
    都不沾 → []（调用方原样透传，零扰动）。
    """
    msg = (message or "").strip()
    if not msg:
        return []
    now = now or datetime.now()
    msg_n = _t2s(msg)   # R229d：繁中归一后再做事项词/泛问匹配（原文留给日期词）

    scene, terms = "", []
    # R228s：长词优先匹配——「解除合同」若先撞上「合同」会被误分到立券
    # （签约方向，与用户意图相反）。先扫长键再扫短键消歧。
    for k in sorted(_CHAT_SCENE_TERMS, key=len, reverse=True):
        if k in msg_n:
            scene, terms = k, _CHAT_SCENE_TERMS[k]
            break
    if not scene:
        for t in _HUANGLI_VOCAB_ORD:
            if t in msg_n:
                scene, terms = t, [t]
                break
    generic = not scene and any(
        k in msg_n for k in ("黄历", "宜忌", "吉日", "挑日子", "看日子",
                             "择日", "适合做什么", "适合干什么"))
    if not scene and not generic:
        return []

    dt, spoken = _hl_day_part(msg, now)
    q = huangli_mod.day_query(dt)
    yi, ji = q["yi"], q["ji"]
    date_cn = q["date"]
    yi_str = "、".join(yi) or "无"
    ji_str = "、".join(ji) or "无"
    facts = [f"{spoken}（{date_cn}）的黄历：宜【{yi_str}】；忌【{ji_str}】。"]

    if generic:
        facts.append("没列入当日宜忌的事项属中性——不是不支持，只是黄历没"
                     "为它背书，可照常安排；想要背书就挑宜它的日子。")
        return facts

    hit_yi = [t for t in terms if any(t in w or w in t for w in yi)]
    hit_ji = [t for t in terms if any(t in w or w in t for w in ji)]
    good = _hl_next_yi_days(dt, terms)
    good_str = "、".join(good)
    good_part = (f"近45天宜{scene}的日子：{good_str}——想要黄历背书可挑这几天。"
                 if good else "")
    if hit_yi and not hit_ji:
        verdict = f"黄历判定：{date_cn} 宜「{scene}」（宜项含【{'、'.join(hit_yi)}】）。"
    elif hit_ji and not hit_yi:
        verdict = (f"黄历判定：{date_cn} 忌「{scene}」（忌项含【{'、'.join(hit_ji)}】）；"
                   f"已安排也不必慌，放缓节奏即可。{good_part}")
    elif hit_yi and hit_ji:
        verdict = (f"黄历判定：{date_cn} 「{scene}」宜忌都有——宜【{'、'.join(hit_yi)}】"
                   f"也忌【{'、'.join(hit_ji)}】；想做就把节奏放缓，不赶大动作。")
    else:
        that_day = "今天" if dt.date() == now.date() else f"{spoken}（{date_cn}）"
        verdict = (f"黄历判定：{date_cn} 宜忌都没直接提「{scene}」——中性，"
                   f"不是不支持，只是黄历{that_day}没为它背书，{scene}可照常安排。"
                   f"{good_part}")
    facts.append(verdict)
    return facts


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
        # R221b：交叉引用收口 7/7——塔罗不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_tarot(cards),
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

_BAD_RELS = ("相害", "相刑", "自刑", "六冲")   # R228m：产出侧枚举是「六冲」（bazi_calc.py:141）
_GOOD_RELS = ("六合", "三合", "半合")


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
        if t in ("相害", "相刑", "六冲"):
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
                     f"（{'/'.join(r['type'] for r in bad[:2])}）——"
                     f"容易自己跟自己较劲，稳一点就好")
    if good:
        parts.append(f"也有{len(good)}处顺劲"
                     f"（{'/'.join(r['type'] for r in good[:2])}）——有人搭把手，事情好推")
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
        _parse_iso_date(date_str)   # 边界即拒（R228p 统一解析口径）
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
            # R228m：cv=2 钉住「level 按请求日算」口径——cv 缺/旧（含 noble
            # 校验时代写的行）一律重算覆盖，杜绝「写入日口径」固化。
            if _c.get("cv") == 2 and (not _want or _c.get("noble") == _want):
                return {"date": date_str, **_c, "cached": True}
    try:
        d = date.fromisoformat(date_str)
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        # R228m：?date=X 的 level 必须按请求日算——原来 bazi_calc(b) 缺省
        # 回退 date.today()，73/400 天等级被「今天」口径改写且被
        # daily_cache 固化成「写入日口径」。
        calc_out = bazi_calc(b, ask_date=date_str)
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
        # B-017（R195b 清偿）：旧实现按公历年取生肖是「今年的生肖」，
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
            "cv": 2,                     # 缓存口径版本（R228m：level 按请求日）
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
    except Exception:                                 # 计算失败降级为"平"，不 500
        # R228b：不把 str(exc) 透传给用户——那是 Python 异常原文
        # （"year 10000 is out of range"），给固定中性文案。
        return {"date": date_str, "level": "平", "summary": "今天的运势卡暂时没算出来，稍后再看看～",
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
    """recent_modules 偏好：写入端是自由键值（可能落进 int/dict/字符串），
    读端只认 list，其余一律当空——不然 widget() 的 `m['id'] in recent`
    对非序列类型抛 TypeError → /api/widget 持久 500。"""
    try:
        v = json.loads(kb.get_pref("recent_modules", "[]") or "[]")
    except (ValueError, TypeError):
        return []
    return v if isinstance(v, list) else []


def widget() -> dict:
    """首页功能卡片数据：各模块图标/标题/描述 + 最近使用标记。"""
    with deps.knowledge() as kb:
        recent = _recent_list(kb)
    modules = [dict(m, recent_used=m["id"] in recent) for m in MODULES]
    return {"modules": modules, "recent": recent}


SHARE_COLORS = {"bazi": "#B8860B", "tarot": "#9D4EDD",
                "book": "#5B8C5A"}


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
            # R228r：derived 表存的是研究线程记录（kind 不定为 bazi）——标题
            # 按实际 kind 出，别一律误标「八字排盘结果」。
            kind_title = {"thread": "研究笔记", "summary": "古籍研究笔记",
                          "answer": "研究结论", "link": "关联笔记",
                          "diff": "比对笔记", "refusal": "存疑记录"}
            title = kind_title.get(getattr(d, "kind", ""), "八字排盘结果")
            return {"title": title, "subtitle": d.claim[:60],
                    "content": d.claim, "image_color": SHARE_COLORS["bazi"],
                    "created_at": d.created_at}
    if share_type in ("tarot", "book"):
        # R228r：这两个分享面无后端存档，share_id 原样回显——限长+拒控制字符
        # 守住上限，任意长串/HTML 片段不该被当分享标题直接回显。
        if not share_id or len(share_id) > 80 or not share_id.isprintable():
            raise NotFoundError("未找到")
        title, content = (("塔罗占卜结果", "塔罗牌阵解读") if share_type == "tarot"
                          else ("读书笔记", "古籍研究笔记"))
        return {"title": title, "subtitle": share_id, "content": content,
                "image_color": SHARE_COLORS[share_type], "created_at": today}
    raise NotFoundError(f"不支持的分享类型：{share_type}")


def user_prefs() -> dict:
    with deps.knowledge() as kb:
        return {"theme": kb.get_pref("theme", "cream"),
                "recent": _recent_list(kb),
                "favorites": [dict(r) for r in kb.list_favorites()]}


def set_user_prefs(payload: dict) -> dict:
    # R228j：自由键值≠无界——键数/键长/值长不设限就是 sqlite 无限写入面。
    payload = payload or {}
    if len(payload) > 64:
        raise ValidationError("偏好键最多 64 个")
    items = []
    for k, v in payload.items():
        if not isinstance(k, str) or not k or len(k) > 64:
            raise ValidationError("偏好键需为 1-64 字符")
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        v = str(v)
        if len(v) > 4000:
            raise ValidationError(f"偏好值过长（≤4000），键 {k}")
        items.append((k, v))
    with deps.knowledge() as kb:
        kb.set_prefs(items)   # 单事务——全部校验过后才落库
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
        # R229n（R6-#13）：异常原文不外泄——与 external_fortune 同纪律。
        return {"fetched_at": None, "proxy": external_feed.PROXY,
                "sources": [], "error": "外部资讯暂时取不到"}


def external_fortune() -> dict:
    """外部资讯的运势风格包装（每日运势卡片的外部资讯部分）。"""
    try:
        return external_feed.fortune_wrap(external_feed.fetch_sources(max_sources=4))
    except Exception:
        # R228e：异常原文不抛给用户（ConnectionError/timeout 是英文堆栈串）。
        return {"date": None, "ok": False, "items": [],
                "summary": "外部资讯暂时不可用，稍后再看看"}


def health() -> dict:
    """健康检查：解读引擎恒可用（确定性规则，无 LLM、无网络、无 key）。"""
    return {"ok": True, "engine": interpreter.configured_model(),
            "index": os.path.exists(deps.CORPUS_DB)}


# C-003：交叉引用辅助函数
#
# R220b 修 P0（太阳星座算错）：这几个函数原本用 `daily_horoscope(b.day)` 的
# `today_sign` 当用户的太阳星座——那是"今天哪一宫当值"（日支查表），不是本命
# 星座。实测 2005-06-06 生（真实双子）被告知"你的太阳星座是金牛"，且 06-06/07/
# 08/09 出生的人分别得到金牛/白羊/双鱼/水瓶（太阳星座一个月内本应稳定）。
# 现改用 `xingzuo.sun_sign(月, 日)` 按出生月日判定，并把"今日运势"与"本命星座"
# 两件事在文案里分开说，不再混为一谈。
@functools.lru_cache(maxsize=4)
def _today_horoscope_cached(iso_day: str) -> dict:
    """按日期键缓存的值宫卡——当日结果恒定，跨午夜自动换键失效。"""
    from datetime import date as _date

    from guji.xingzuo import daily_horoscope
    try:
        _t = _date.fromisoformat(iso_day)
        b = bazi_compute(_t.year, _t.month, _t.day, 12, "男")
        return daily_horoscope(b.day)
    except Exception:
        return {}


def _today_horoscope() -> dict:
    """今天的值宫卡（用于"今日运势"侧）。失败返回 {}。"""
    # R228b：原来每请求重算当日八字（~23ms，占 bazi() 三成）——进程内
    # memo。浅拷贝返回防调用方改写缓存对象。
    return dict(_today_horoscope_cached(date.today().isoformat()))


def _cross_ref_bazi(b, gender: str, month: int = 0, day: int = 0) -> dict:
    """八字结果页 → 你的太阳星座 + 今天的运势侧重。

    month/day 是**出生**月日（太阳星座的唯一依据）。缺省 0 时降级为只给
    今日值宫，不再瞎猜本命星座。
    """
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day) if month and day else {}
        today = _today_horoscope()
        sign = prof.get("sign", "")
        today_sign = today.get("today_sign", "")
        note = today.get("today_note", "")
        # 一句话只说一件事：本命座的长处 + 今天当值宫的节奏。两者撞车时
        # （旧文案"你是双子座…今天的整体节奏：节奏放慢一点"读起来自相矛盾）
        # 明确标出"今天是 X 宫的日子"，让用户知道这是两个不同维度。
        if sign and today_sign and note:
            if sign == today_sign:
                msg = f"你是{sign}座，今天正好是{sign}宫当值的日子——{note}"
            else:
                msg = f"你是{sign}座（{prof.get('love', '')}）今天是{today_sign}宫的日子：{note}"
        elif sign:
            msg = f"你是{sign}座，{prof.get('love', '')}"
        elif today_sign and note:
            msg = f"今天是{today_sign}宫的日子：{note}"
        else:
            return {}
        return {
            "zodiac_sign": sign,
            "zodiac_love": prof.get("love", ""),
            "zodiac_career": prof.get("career", ""),
            "zodiac_wealth": prof.get("wealth", ""),
            "today_sign": today.get("today_sign", ""),
            "today_note": note,
            "message": msg,
        }
    except Exception:
        return {}


def _cross_ref_hehun(ba, bb, a_md: tuple = (), b_md: tuple = ()) -> dict:
    """合婚结果页 → 双方太阳星座配对。a_md/b_md = (出生月, 出生日)。"""
    from guji.xingzuo import sun_sign
    try:
        sa = sun_sign(*a_md) if len(a_md) == 2 else ""
        sb = sun_sign(*b_md) if len(b_md) == 2 else ""
        if not (sa and sb):
            return {}
        if sa == sb:
            tip = f"都是{sa}座，同款脾气——合得来的时候特别合，别较劲就行。"
        else:
            tip = f"{sa}座配{sb}座，节奏不一样反而互补，谁先开口谁占便宜。"
        return {
            "zodiac_a": sa,
            "zodiac_b": sb,
            "message": f"你们是{sa}座和{sb}座。{tip}",
        }
    except Exception:
        return {}


def _parse_iso_date(date_str: str) -> "date":
    """YYYY-MM-DD 边界即拒（R228p 统一三处口径）。

    此前 huangli 手写 split('-')、daily/xingzuo 各写一遍
    fromisoformat+年份界——同一约束三套实现。统一在这里。"""
    try:
        parsed = date.fromisoformat(date_str)
    except ValueError:
        raise ValidationError(
            f"日期需为 YYYY-MM-DD 格式，收到 {date_str}") from None
    if not (YEAR_LO <= parsed.year <= YEAR_HI):
        raise ValidationError(
            f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {parsed.year}")
    return parsed


def _cross_ref_huangli(date_str: str) -> dict:
    """黄历结果页 → 今天的星座值宫（这一处本来就该用"今日"，逻辑成立）。"""
    from guji.xingzuo import daily_horoscope
    try:
        from datetime import date as _date
        d = _date.fromisoformat(date_str) if date_str else _date.today()
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        h = daily_horoscope(b.day)
        sign = h.get("today_sign", "")
        note = h.get("today_note", "")
        if not (sign and note):
            return {}
        # R228p：用户翻的是查询日，不一定是今天——文案跟着说"那天"。
        _when = "今天" if d == _date.today() else "那天"
        return {
            "zodiac_sign": sign,
            "zodiac_note": note,
            "message": f"{_when}{sign}宫当值：{note}",
        }
    except Exception:
        return {}


def _cross_ref_taohua(month: int, day: int, strength: str = "") -> dict:
    """桃花结果页 → 星座桃花信号，与八字强度叠加判断。"""
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day)
        if not prof:
            return {}
        sign, love = prof["sign"], prof.get("love", "")
        # R224b 修（审查轨 R221a 抓到）：这里原写 `high`/`low`，但 taohua.py:92-96
        # 产出的实际值是 **strong / mid / weak** → 两个分支永远不命中，
        # 所有强度都掉进 else，"信号叠加"逻辑从 R220b 起从未生效过。
        # 教训：分支值必须回源码核对枚举，不能凭语感写。
        if strength == "strong":
            head = f"{sign}座今天也在桃花档上，两边信号叠一起了"
        elif strength == "weak":
            head = f"八字这边桃花偏淡，但{sign}座的优势还在"
        else:                                  # mid（或未知值）走中性分支
            head = f"{sign}座这边给的建议是"
        return {
            "zodiac_sign": sign,
            "zodiac_love": love,
            "message": f"{head}：{love}",
        }
    except Exception:
        return {}


def _signal_relation(a_dir: str, b_dir: str, a_name: str) -> str:
    """两个信号方向的真实比较 → 一句可操作的关系判断。

    R226b：塔罗/六爻的"两信号关系"原先只看自己那一侧，等于没比较
    （审查轨 R222a 点名）。这里把 a（牌面/卦象）与 b（今日值宫）的
    forward/hold/observe/mixed 做真实比对，冲突时给缓冲方案而不是含糊其辞。
    a_name 用于文案主语（"牌面"／"卦象"）。
    """
    if not b_dir:                       # 值宫方向缺失 → 只说自己那一侧
        return "先按自己的节奏来"
    if a_dir == "mixed":
        return {"forward": "牌面没给死结论，那就顺着今天的劲儿往前一点",
                "hold": "牌面没给死结论，今天本来也适合慢一点",
                "observe": "两边都没催你做决定，今天可以先放一放"}[b_dir] \
            if a_name == "牌面" else \
            {"forward": "卦里没大动静，今天的劲儿可以用一用",
             "hold": "卦里没大动静，今天本来也适合稳着",
             "observe": "两边都没催你决定，今天先看看"}[b_dir]
    # 注意：外层文案已经写了「{a_name}这边{...}」，所以这里**不要再重复
    # a_name**，也不要再用破折号（否则出现"…—和今天是一个方向，牌面也在
    # 推你—想做就做"这种三连破折号 + 主语重复）。只回一句短判断。
    if a_dir == b_dir:                  # 同调：最强的一档，直接鼓励
        if a_dir == "forward":
            return "和今天是一个方向，想做就做"
        return "和今天一样都说慢着来，稳住就对了"
    if b_dir == "observe":              # 值宫本身偏观望
        return ("今天更适合先感受再动，"
                + ("那就把想做的事拆小一点起步" if a_dir == "forward"
                   else "顺势歇一天也不亏"))
    # 真冲突（forward × hold）：给缓冲方案，不含糊
    if a_dir == "forward" and b_dir == "hold":
        return "跟今天的慢节奏有点拧，挑一件最小的事试试水就好"
    return "今天倒是能推一把，那就只做有把握的那一步"


def _cross_ref_tarot(cards: list[dict]) -> dict:
    """塔罗结果页 → 今天的星座值宫 × 牌面正逆方向是否同调。

    塔罗没有出生日期可用（不要求用户填生日），所以这里**只能**引"今天"，
    不能编造本命星座——这是与八字/桃花/起名那几处的关键区别。
    """
    from guji.xingzuo import sign_direction
    try:
        today = _today_horoscope()
        sign = today.get("today_sign", "")
        note = today.get("today_note", "")
        if not (sign and note and cards):
            return {}
        _up = sum(1 for c in cards if c.get("upright"))
        _total = len(cards)
        # 牌面方向与今日值宫是**两个独立信号**，不能硬拼成因果句
        # （曾出现"牌面偏逆位，今天节奏更适合先稳一稳：今天适合把心里的话
        # 说出口"——前半句劝稳、后半句劝开口，自相矛盾）。
        #
        # R226b（审查轨 R222a 抓到）：上一版把两句分开陈述了，但那句
        # "两信号关系"**只是牌面正逆的纯函数** —— 今天白羊（劝你说出口）
        # 还是金牛（劝你放慢），逆位都输出同一句"和今天的节奏不完全一致"，
        # 从没真比较过。现在用 xingzuo.sign_direction() 取值宫的方向倾向，
        # 与牌面方向做真实的 3×3 比较（同调 / 相反 / 一方中性）。
        card_dir = ("forward" if _up * 2 > _total
                    else "hold" if _up * 2 < _total else "mixed")
        card_side = {"forward": "多数正位，是往前走的信号",
                     "hold": "偏逆位，提示先别急",
                     "mixed": "正逆各半"}[card_dir]
        relation = _signal_relation(card_dir, sign_direction(sign), "牌面")
        return {
            "today_sign": sign,
            "today_note": note,
            "today_direction": sign_direction(sign),
            "card_direction": card_dir,
            "upright_count": _up,
            "total": _total,
            "message": f"今天{sign}宫：{note}牌面这边{card_side}——{relation}。",
        }
    except Exception:
        return {}


def _cross_ref_liuyao(moving_lines: list | tuple) -> dict:
    """六爻结果页 → 今天的星座值宫 × 动爻多寡（变数大小）是否同调。

    同塔罗：六爻不收生日，只能引"今天"。
    """
    from guji.xingzuo import sign_direction
    try:
        today = _today_horoscope()
        sign = today.get("today_sign", "")
        note = today.get("today_note", "")
        if not (sign and note):
            return {}
        _n = len(moving_lines or ())
        # R226b：同塔罗——原 relation 只看动爻数，与"今天"无关（审查轨点名）。
        # 动爻多 = 局面在变（宜观望 observe）；无动爻 = 局面稳（宜守 hold）；
        # 1-2 个动爻 = 小步可动（forward）。再与值宫方向做真实比较。
        if _n >= 3:
            gua_side = f"有 {_n} 个动爻，变数不小"
            gua_dir = "observe"
        elif _n == 0:
            gua_side = "一个动爻都没有，局面挺稳"
            gua_dir = "hold"
        else:
            gua_side = f"有 {_n} 个动爻，小范围有变化"
            gua_dir = "forward"
        relation = _signal_relation(gua_dir, sign_direction(sign), "卦象")
        return {
            "today_sign": sign,
            "today_note": note,
            "today_direction": sign_direction(sign),
            "gua_direction": gua_dir,
            "moving_count": _n,
            "message": f"今天{sign}宫：{note}卦里{gua_side}——{relation}。",
        }
    except Exception:
        return {}


def _cross_ref_qiming(month: int, day: int) -> dict:
    """起名结果页 → 太阳星座气质，给挑名字的参考角度。"""
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day)
        if not prof:
            return {}
        sign = prof["sign"]
        return {
            "zodiac_sign": sign,
            "message": f"{sign}座的气质是「{prof.get('note', '')}」"
                       f"挑名字时可以往这个感觉上靠。",
        }
    except Exception:
        return {}
