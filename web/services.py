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
from guji.search import s2t_retry
from guji import tarot as tarot_mod
from guji import voice
from guji import xingzuo as xingzuo_mod
from guji.bazi import compute as bazi_compute
from guji.bazi import day_ganzhi as _bazi_day_ganzhi
from guji.bazi_calc import LIU_HE
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
    # R230r（R30-#10）：纯零宽字符（ZWSP 等）strip() 不掉——读路径
    # （fts_phrase）会剥，空判定要先剥再判，不然「%E2%80%8B」走到 200+空表
    # 而不是如实 400。
    q = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]",
               "", q).strip()
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
        except ValueError:
            raise ValidationError("农历日期没换算成——查查是不是填错了月日") from None
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
        b = bazi_compute(by, bm, bd, req.hour, req.gender,
                             minute=(req.minute or 0))
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
    # R232a（R40-B1）：day_master 正名——前端此前靠正则从 render 文本里
    # 抠日主（格式一改静默丢事实）。显式给字段消掉这个脆弱点。
    paipan_out = {"render": b.render(), "nayin": b.nayin, "warn": b.warn,
                  "day_master": b.day[0]}
    interpretation = interpreter.interpret_bazi(paipan_out, calc_out,
                                               evidence, req.question)
    # R182b（004 M1）：warm 视图 **additive** 附加——不动 interpretation 一个
    # 字节。判据 9 要求专业模式逐字节等于基线，由 web/baseline_voice.py 把关。
    # R230a-7（R13-P2-1）：gender 透传——感情类落点按性别分星。
    warm = voice.warm_bazi(paipan_out, calc_out, interpretation,
                           req.question, gender=req.gender)

    # R230a-7（R13-P1-3）：时辰留空 → warm reply 首部明示时柱是默认午时，
    # 响应带 hour_known 供前端卡面标注。此前静默按午时排。
    if req.hour_known is False:
        warm["reply"] = ["没填时辰——时柱这条按中午 12 点算的，"
                          "前三柱（年/月/日）不受影响，照样准。"] + list(
                              warm.get("reply") or [])

    # R187b（specs/006）：AI 润色层，additive 附加。失败/关闭 → None，
    # 前端整块不渲染；LLM 永远不是承重墙（D-244a）。
    # R191b（B-014，D-251b）：同步 polish 改后台任务——确定性主体立即返回，
    # 响应附 ai_task_id 供前端轮询 /api/ai/{id}；DISABLE/关闭时无此键
    # （响应与旧版逐字节一致，specs/006 判据 11）。
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_bazi(paipan_out, warm, req.question,
                              gender=req.gender),
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
        # R230m：cross_ref 的「今天」锚起问日（前端已传 todayIso()）。
        "cross_ref": _cross_ref_bazi(b, req.gender, bm, bd,
                                     today_iso=req.ask_date),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
        **({"hour_known": req.hour_known} if req.hour_known is False else {}),
    }
    paipan_history.save_async({
        "year": req.year, "month": req.month, "day": req.day,
        "hour": req.hour, "gender": req.gender,
        # R230h（R20-F9）：minute/hour_known 进台账——节气分钟级边界与
        # 「时辰未知」标记将来做按原参重测/导出分析时不能丢。
        "minute": req.minute, "hour_known": req.hour_known,
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
        b = bazi_compute(by, bm, bd, req.hour, req.gender,
                             minute=(req.minute or 0))
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
    out = {
        **t_dict,
        "warm": warm,
        "ai_polish": ai_polish,
        # R220b：交叉引用铺到桃花——星座桃花信号 × 八字强度叠加
        "cross_ref": _cross_ref_taohua(bm, bd, t.strength),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }
    # R230z（R36-P1-1）：桃花也进排盘历史台账（原来只有 bazi 落库）
    paipan_history.save_async({
        "year": req.year, "month": req.month, "day": req.day,
        "hour": req.hour, "gender": req.gender,
    }, out, rtype="taohua")
    return out


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
        # R233u（R53-P1-1）：one_liner 盐键接线——此前 day_zhi_* 恒 None，
        # 同桶所有 CP 抽到同一句判词。
        "day_zhi_a": h.day_zhi_a, "day_zhi_b": h.day_zhi_b,
        "day_zhi_rel": h.day_zhi_rel,
        "nayin_a": h.nayin_a, "nayin_b": h.nayin_b, "nayin_rel": h.nayin_rel,
        "year_zhi_rel": h.year_zhi_rel,
        "year_zhi_a": h.year_zhi_a, "year_zhi_b": h.year_zhi_b,
        "clash": h.clash, "combine": h.combine,
        "day_wx_a": h.day_wx_a, "day_wx_b": h.day_wx_b,
        "day_wx_sheng": h.day_wx_sheng,
        "day_wx_same": h.day_wx_same,   # R230a-7（R13-P0-2）：同五行比和
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
    out = {
        **h_dict,
        "warm": warm,
        "ai_polish": ai_polish,
        # R230z（R36-P1-2）：昵称不进响应（selftest 钉死响应键集）——
        # 前端本地注入；存进台账的 result 副本带昵称供复看。
        # C-003：交叉引用——合婚结果页增加星座配对维度
        # R220b：按双方出生月日取真实太阳星座（原来用日支，配对结论是假的）
        "cross_ref": _cross_ref_hehun(ba, bb,
                                     (req.a_month, req.a_day),
                                     (req.b_month, req.b_day)),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }
    # R230z（R36-P1-1）：合婚进台账；name 用昵称对（缺省 我 × TA）
    _an, _bn = req.a_name or "我", req.b_name or "TA"
    paipan_history.save_async({
        "a_year": req.a_year, "a_month": req.a_month, "a_day": req.a_day,
        "a_hour": req.a_hour, "a_gender": req.a_gender,
        "b_year": req.b_year, "b_month": req.b_month, "b_day": req.b_day,
        "b_hour": req.b_hour, "b_gender": req.b_gender,
        "a_name": req.a_name, "b_name": req.b_name,
    }, {**out, "a_name": req.a_name, "b_name": req.b_name},
       rtype="hehun", name=f"{_an} × {_bn}")
    return out


def qiming(req) -> dict:
    """五行起名：八字 → 五行缺行 → 古籍典故取名 + 候选字（R217a 重构）。"""
    req.validate_ranges()
    # R229x（R7 审计 #3）：打包漏带 classical_names.json 时典故库静默
    # 为空、起名返回 0 候选——显式报错让用户知道缺资源，而非空结果。
    # 注意放 try 外：except Exception 会把 ComputeError 包成「起名计算失败」。
    from guji import classical_names
    if not classical_names._CLASSICAL_DB:
        raise ComputeError("起名典故库文件缺失（classical_names.json），"
                           "重新下载完整版本试试")
    try:
        out = classical_names.generate_classical_names(
            surname=req.surname, year=req.year, month=req.month,
            day=req.day, hour=req.hour, gender=req.gender,
            top_n=min(max(req.top_n, 1), 100),
            seed=req.seed, style=getattr(req, "style", "all"))
    except Exception as exc:
        raise ValidationError(f"起名计算失败：{_friendly_calc_err(exc)}") from exc
    ai_polish = None
    # R233j（R46-P1）：copy_bank.qiming_one_liners 死池接线——按
    # 姓氏+日柱确定性抽一条暖句当卡面 hook（同输入同输出）。
    _ql = _COPY_BANK.get("qiming_one_liners") or []
    if _ql:
        out["one_liner"] = _pick(_ql, req.surname,
                                 (out.get("bazi") or {}).get("render", ""), "qm")
    # R233w（R53-P3-3）：起名补 warm 层——其余功能都有 warm.reply 多行，
    # 起名 LLM 挂了只剩裸名单。
    out["warm"] = voice.warm_qiming(out, req.surname, req.gender)
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_qiming(out, req.gender, warm=out["warm"]))
    out["ai_polish"] = ai_polish
    # R220b：交叉引用铺到起名——太阳星座气质给挑名字一个参考角度
    out["cross_ref"] = _cross_ref_qiming(req.month, req.day)
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    # R230z（R36-P1-1）：起名进台账（原来只有 bazi 落库）
    paipan_history.save_async({
        "surname": req.surname, "year": req.year, "month": req.month,
        "day": req.day, "hour": req.hour, "gender": req.gender,
        "seed": req.seed, "style": req.style,
    }, out, rtype="qiming", name=f"起名 · {req.surname}×")
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
                "日期没看懂——照着 2026-01-01 这样填试试") from None
        # R228b：星历表有覆盖区间——极值年份（如 9999）会一路炸进
        # bazi_compute 报 ValueError → 未映射 500。边界即拒为 400。
        if not (YEAR_LO <= _parsed.year <= YEAR_HI):
            raise ValidationError(
                f"年份要在 {YEAR_LO}–{YEAR_HI} 之间")
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
    # R230s（R30-#9）：limit<=0 此前静默钳成 1——如实 400。
    if limit < 1:
        raise ValidationError("一次最多取 50 条")
    limit = min(limit, 50)
    with deps.corpus() as c:
        # R230a-33（R14-P3-6）：scheme 与 addr 同纪律——未知值 400 而非静默零命中。
        if scheme is not None and scheme not in deps.SCHEME_LABELS:
            raise ValidationError(
                f"这种编址方式不支持——可选：{' / '.join(deps.SCHEME_NAMES.values())}")
        # 'none' 哨兵原样下传，由 Corpus._search_where 翻成 IS NULL。
        # R230r（R30-#11）：过滤参数拼错/不存在时如实 400——work=NOSUCH
        # 此前静默 200 零命中，看起来像「语料里没有这个词」。
        if work and not c.db.execute(
                "SELECT 1 FROM work WHERE id=?", (work,)).fetchone():
            raise ValidationError(f"这本书库里暂时没有（{work}）——先去书目页翻翻")
        if layer and not c.db.execute(
                "SELECT 1 FROM unit WHERE layer=? LIMIT 1",
                (layer,)).fetchone():
            raise ValidationError(f"这个分类库里没有（{layer}），换一个试试")
        kw = dict(layer=layer, work_id=work, genre=genre, scheme=scheme)
        hits = c.search(q, limit=limit, **kw)
        hint = None
        if not hits:
            # R230a-30（R14-P1-1）：语料是繁体，简体问句零命中时用保守映射
            # 重试一次——「潜龙勿用」→「潛龍勿用」。只对查询词生效，不动语料。
            q2 = s2t_retry(q)
            if q2 != q:
                hits = c.search(q2, limit=limit, **kw)
                if hits:
                    hint = f"已按繁体重试「{q2}」"
        total = c.search_count(q if hint is None else q2, **kw) \
            if hits else 0
        return {"query": q, "count": len(hits), "total": total,
                "truncated": total > len(hits), "hint": hint,
                "hits": [hit_dict(h) for h in hits]}


def addr(scheme: str = "zhouyi", *, gua: int | None = None,
         yao: str | None = None, layer: str | None = None,
         addr_name: str | None = None, addr1: int | None = None,
         addr2: str | None = None, limit: int = 20) -> dict:
    """地址定位。scheme 显式声明，杜绝 Psalms-99 == 卦99 类跨体系碰撞（D-005）。"""
    if scheme not in deps.SCHEME_LABELS:
        raise ValidationError(
            f"这种编址方式不支持——可选：{' / '.join(deps.SCHEME_NAMES.values())}")
    if limit < 1:
        raise ValidationError("一次最多取 100 条")
    limit = min(limit, 100)
    # R230s（R30-#14）：与所选 scheme 不相干的参数如实披露，不静默吞。
    if scheme == "zhouyi":
        _ignored = [n for n, v in (("addr_name", addr_name),
                                   ("addr1", addr1), ("addr2", addr2))
                    if v is not None]
    else:
        _ignored = [n for n, v in (("gua", gua), ("yao", yao))
                    if v is not None]
    hint = (f"你传的 {'/'.join(_ignored)} 这项在{deps.SCHEME_NAMES.get(scheme, scheme)}用不上，帮你忽略了"
            if _ignored else None)
    with deps.corpus() as c:
        if scheme == "zhouyi":
            if gua is None:
                raise ValidationError("用周易定位得给个卦号（1–64）")
            # R230a-33（R14-P3-6）：gua=99 此前 200 空集——与 compare 同判 400。
            if not (1 <= gua <= 64):
                raise ValidationError("卦号填 1 到 64")
            hits = c.at_address(gua, yao, layer=layer, limit=limit)
            # R230r（R30-#6）：披露总量——默认 limit=20 只回前 20 条时，
            # 此前用户以为该卦只有 20 条材料。
            _w = "addr1=? AND scheme='zhouyi'"
            _p: list = [gua]
            if yao:
                _w += " AND addr2=?"; _p.append(yao)
            if layer:
                _w += " AND layer=?"; _p.append(layer)
            total = c.db.execute(f"SELECT count(*) n FROM unit u WHERE {_w}",
                                 _p).fetchone()["n"]
        else:
            # R230s（R30-#13）：yilin 候数与 zhouyi 同纪律 1–64 越界 400；
            # bcv/booksec/play/euclid 的 addr1 上界随卷/书目而异，无法
            # 全局校验——超界仍回空集（不算差异，算没那个地址）。
            if scheme == "yilin" and addr1 is not None \
                    and not (1 <= addr1 <= 64):
                raise ValidationError("候数填 1 到 64")
            hits = c.at_scheme(None if scheme == "none" else scheme,
                               addr_name=addr_name, addr1=addr1,
                               addr2=addr2, layer=layer, limit=limit)
            _sn = None if scheme == "none" else scheme
            _w = "scheme IS NULL" if _sn is None else "scheme = ?"
            _p = [] if _sn is None else [_sn]
            for col, val in (("addr_name", addr_name), ("addr1", addr1),
                             ("addr2", addr2), ("layer", layer)):
                if val is not None:
                    _w += f" AND {col} = ?"; _p.append(val)
            total = c.db.execute(f"SELECT count(*) n FROM unit u WHERE {_w}",
                                 _p).fetchone()["n"]
        return {"scheme": scheme, "count": len(hits), "total": total,
                "truncated": total > len(hits), "hint": hint,
                "hits": [hit_dict(h) for h in hits]}


def compare(gua: int, yao: str = "九三", layer: str = "經",
            allow_damaged: bool = False) -> dict:
    """跨版本同址比对 + 差异摘要（复用 compare.compare_address）。"""
    if not (1 <= gua <= 64):
        raise ValidationError("卦号填 1 到 64")
    with deps.corpus() as c:
        cmp = compare_address(c, gua, yao, layer=layer,
                              allow_damaged=allow_damaged)
        return {
            "addr": cmp.addr,
            "reference": cmp.reference,
            "agree": cmp.agree,
            # R230r（R30-#7）：无见证时 agree=not evidential() 恒 False，
            # 前端渲染「存在差异」+「无差异发现」自相矛盾——单开字段披露
            # 「没找到可比对的材料」这个第三态。
            "no_witness": not cmp.witnesses,
            "counts": cmp.counts(),
            "witnesses": cmp.witnesses,
            "citations": cmp.citations,
            "commentary": cmp.commentary,
            # R230a-29（R14-P0-1）：受损见证披露不放行
            "flagged": cmp.flagged,
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
        raise ValidationError("最多选 6 条")
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
        raise ValidationError("两本书的书号都得填上")
    # R230a-34（R14-P3-7）：同书对照无意义——全部行恒等，纯烧 IO。
    if work_a == work_b:
        raise ValidationError("对照需要两本不同的书")
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
        # R230r（R30-#4）：manifest 没有 source 键——真实来源字段是
        # gutenberg_id / source_url；此前 47 部书全部标成 kanripo/内置，
        # Gutenberg 的 Bible/Euclid/Herodotus 也被误标。
        def _src_of(w):
            if w.get("source"):
                return w["source"]
            if w.get("gutenberg_id") or "gutenberg.org" in str(
                    w.get("source_url") or ""):
                return "gutenberg"
            return w.get("source_url") or None
        src = {w.get("id"): _src_of(w) for w in man.get("works", [])
               if w.get("id")}
    except (OSError, ValueError):
        src = {}
    for r in rows:
        r["source"] = src.get(r["id"]) or "kanripo/内置"
    return {"works": rows, "total": len(rows)}


def _corpus_index_stale() -> bool | None:
    """R230t（R31-P1-1）：corpus.db 比 data/raw 旧 = 索引过期。

    build_meta 记的是构建时刻；raw 文本之后被改动（修订/增量入库）不会
    回写 meta，唯一能信的对比是文件 mtime。raw 目录缺失/读取失败时
    返回 None（「不知道」，不谎报）。
    """
    try:
        db_mtime = os.path.getmtime(deps.CORPUS_DB)
        newest = 0.0
        for base in (deps.RAW_DIR, deps.RAW_DIR + "_ext"):
            if not os.path.isdir(base):
                continue
            for dirpath, _dirs, files in os.walk(base):
                for fn in files:
                    if fn.endswith(".txt"):
                        newest = max(newest, os.path.getmtime(
                            os.path.join(dirpath, fn)))
        if not newest:
            return None
        return newest > db_mtime
    except OSError:
        return None


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
            "index_stale": _corpus_index_stale(),
        }


def threads() -> dict:
    """研究线程列表（G9：可恢复的研究线索）。

    R230r（R30-#8）：resume() LIMIT 50 曾静默截断——超 50 条 open 线程后
    更老的永久消失。披露 total/limit/truncated，并支持 PATCH 改状态
    （open/parked/closed，收起的线程不再占列表位）。"""
    with deps.knowledge() as kb:
        rows = kb.resume()
        total = kb.db.execute(
            "SELECT count(*) n FROM thread WHERE status='open'").fetchone()["n"]
        return {"threads": [dict(r) for r in rows], "stats": kb.stats(),
                "total": total, "limit": 50, "truncated": total > 50}


def thread_set_status(tid: int, status: str) -> dict:
    """改线程状态（R230r / R30-#8：schema 早有 open/parked/closed CHECK，
    但没有任何写入路径能到 closed/parked）。"""
    if status not in ("open", "parked", "closed"):
        raise ValidationError("这条线程只能改成「进行中」「先收起」或「已结束」")
    with deps.knowledge() as kb:
        row = kb.db.execute(
            "SELECT id FROM thread WHERE id=?", (tid,)).fetchone()
        if row is None:
            raise NotFoundError("这条线程没找到——可能还没聊过")
        kb.db.execute("UPDATE thread SET status=? WHERE id=?",
                      (status, tid))
        kb.db.commit()
        return {"id": tid, "status": status}


def thread_detail(tid: int) -> dict:
    """单条线程：transcript + derived claims + 证据回查。"""
    with deps.knowledge() as kb:
        turns = [dict(r) for r in kb.thread_transcript(tid)]
        if not turns:
            raise NotFoundError("这条线程没找到——可能还没聊过")
        claims = []
        _claim_ids: list[int] = []
        for row in kb.db.execute(
                "SELECT id FROM derived WHERE thread_id=? ORDER BY id", (tid,)):
            _claim_ids.append(row["id"])
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
                # R8 P2-4：verify 从全表 evidence 收敛到本线程 claims
                "verify": kb.verify(deps.RAW_DIR, derived_ids=_claim_ids)}


def _drop_thread(kb, tid: int) -> None:
    """尽力删除新建空壳线程（R19-P2-2）：ENOSPC 等故障下补偿删除本身
    也可能失败——吞掉，让原始异常继续走 errors.py 的 503 人话。"""
    try:
        kb.db.execute("DELETE FROM turn WHERE thread_id=?", (tid,))
        kb.db.execute("DELETE FROM thread WHERE id=?", (tid,))
        kb.db.commit()
    except Exception:
        pass


def thread_delete(tid: int) -> dict:
    """删除一条研究线程（R230q / R28-P1-1b：此前没有任何删除入口，
    连按 Enter 刷出的空壳线程永久堆在列表里）。

    turns 随删；已产生的 derived claims 解绑保留（thread_id→NULL）——
    claims 是不可再生的研究笔记，线程消失不该连坐；contentless
    derived_fts 也因此不用碰删除路径。"""
    with deps.knowledge() as kb:
        row = kb.db.execute(
            "SELECT id FROM thread WHERE id=?", (tid,)).fetchone()
        if row is None:
            raise NotFoundError("这条线程没找到——可能已经删了")
        kb.db.execute("DELETE FROM turn WHERE thread_id=?", (tid,))
        kb.db.execute(
            "UPDATE derived SET thread_id=NULL WHERE thread_id=?", (tid,))
        kb.db.execute("DELETE FROM thread WHERE id=?", (tid,))
        kb.db.commit()
        return {"deleted": tid}


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
        raise ValidationError("这条记录没存上：内容不在支持的范围里")
    if req.kind in ASSERTING and not req.evidence:
        raise ValidationError("这条记录没存上：断言型记录得带至少一条证据")
    # R230a-31（R14-P2-3）：role 非法会拖到 record() 撞 CHECK 才 400，此时
    # open_thread/add_turn 已 commit——孤儿线程先在校验层拦死。
    for e in req.evidence:
        if e.role not in ("supports", "contradicts", "context"):
            raise ValidationError(
                "证据只能标成「支持」「反驳」或「背景」")

    with deps.knowledge() as kb:
        tid = req.thread_id
        created_tid = None   # R230g（R19-P2-2）：本次调用新开的线程，
        if tid is None:      # 后续步骤失败时要连带删掉（ENOSPC 实测留空壳）
            topic = (req.topic or req.claim[:50] or "新线程").strip()[:100]
            try:
                tid = created_tid = kb.open_thread(topic)
                kb.add_turn(tid, "user", "开题：" + topic)
            except Exception:
                # R230i（R21-P1-7）：add_turn 失败时 open_thread 已
                # commit——同样补偿删除，不留孤儿 thread 行。
                if created_tid is not None:
                    _drop_thread(kb, created_tid)
                raise
        else:
            # R230r（R30-#17）：绑到不存在的线程此前拖到 record() 撞 FK
            # →「类型或内容不合规」误导文案。存在性检查后如实 404。
            if not kb.db.execute("SELECT 1 FROM thread WHERE id=?",
                                 (tid,)).fetchone():
                raise NotFoundError("这条线程没找到——可能还没聊过")
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
            if created_tid is not None:
                _drop_thread(kb, created_tid)
            raise ValidationError("这条没存上——格式不对，检查一下再试") from exc
        except Exception:
            # R230g（R19-P2-2）：盘满/OperationalError 等底层失败同样
            # 把本调用新开的空壳线程清掉，再把异常交给 errors.py 翻 503。
            if created_tid is not None:
                _drop_thread(kb, created_tid)
            raise
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
        except ValueError:
            # R229z续23（R11-#22）：底层异常原文不透给前端
            raise ValidationError("这个日期没换成农历——可能超出历法表范围") from None
        hour_zhi = (req.hour + 1) // 2 % 12 + 1      # 0-23 → 子=1..亥=12
        ben = liuyao_mod.cast_time(lm["year"], lm["month"], lm["day"], hour_zhi)

    bian = liuyao_mod.changing_hexagram(ben)
    # R233u（R53-P0-4）：断卦坐标接线——纳甲/六亲/世应/六神此前只被
    # probe 调用，API 用户拿不到。六神按起卦日天干起（time 法用所给日，
    # coins 法用用户那边今天）。
    _pp = None
    try:
        if req.method != "coins" and req.year and req.month and req.day:
            _dd = datetime(req.year, req.month, req.day)
        else:
            _cd = getattr(req, "client_date", None)
            try:
                _dd = datetime.strptime(_cd, "%Y-%m-%d") if _cd else datetime.now()
            except (ValueError, TypeError):
                _dd = datetime.now()
        _pp = liuyao_mod.paipan(ben, _bazi_day_ganzhi(_dd)[0][0])
    except Exception:
        _pp = None
    # R230g（R19-P2-1）：引文是锦上添花，卦象本身不依赖语料——corpus
    # 缺失/损坏时降级为空引文继续 200（与 tarot/huangli 纯算端点同口径），
    # 不让一卦被语料库连坐打 503。
    try:
        with deps.corpus() as c:
            ben_jing = [hit_dict(h) for h in
                        c.at_address(ben.gua_number, layer="經", limit=10)]
            # R233u（R53-P0-4 连带）：动爻 1-2 个时定点取动爻辞——此前
            # 单动爻卦也整卦灌 10 条經文，用户得自己在原文堆里找。
            _ml = ben.moving_lines or []
            if 1 <= len(_ml) <= 2:
                _POS_NAME = {1: "初", 2: "二", 3: "三", 4: "四",
                             5: "五", 6: "上"}
                _yj: list = []
                for _p in _ml:
                    _yao = ben.lines[_p - 1]
                    _nm = f"{_POS_NAME[_p]}{'九' if _yao.yang else '六'}"
                    _yj += [hit_dict(h) for h in c.at_address(
                        ben.gua_number, yao=_nm, layer="經", limit=6)]
                if _yj:
                    ben_jing = _yj
            bian_jing = [hit_dict(h) for h in
                         c.at_address(bian.gua_number, layer="經", limit=10)]
    except Exception:
        ben_jing, bian_jing = [], []

    ben_out = liuyao_mod.render_hexagram(ben, "本卦")
    bian_out = liuyao_mod.render_hexagram(bian, "变卦")
    interpretation = interpreter.interpret_liuyao(
        ben_out, bian_out, ben.moving_lines, ben_jing + bian_jing, req.question)
    out = {
        "ben": ben_out,
        "bian": bian_out,
        "ben_jing": ben_jing,
        "bian_jing": bian_jing,
        "interpretation": interpretation,
        # 判据 8：六爻原本对提问只回「不代为断事」。warm 分支给出基于**已起出
        # 的卦象**的描述性回应（不预测结果），专业分支原文不动。
        "warm": voice.warm_liuyao(ben_out, bian_out, ben.moving_lines,
                                  interpretation, req.question,
                                  paipan=_pp),
        # R218a-巡2（N-01）：echo question 让前端 liuyaoQuestionHook 真生效
        "question": req.question,
        # R221b：交叉引用收口 7/7——六爻不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_liuyao(ben.moving_lines,
                                        today_iso=getattr(req, "client_date", None)),
    }
    # R230z（R36-P1-1）：六爻进台账；摘要用问题或本卦名
    paipan_history.save_async(
        {"method": req.method, "seed": req.seed, "year": req.year,
         "month": req.month, "day": req.day, "hour": req.hour,
         "question": req.question},
        out, rtype="liuyao",
        name=("六爻 · " + (req.question or ben_out.get("gua_name") or "起卦")))
    return out


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
        # R229z续8（R8 P1-1）：原实现对 terms 逐词跑 find_good_days（5 词×92
        # 天=460 次 day_query）——find_good_days 现直接收词列表，单日循环
        # 一次判定全部词（92 天恒 92 次）。
        good = [{"date": _q["date"], "yi": _q["yi"], "ji": _q["ji"]}
                # R8 P2-6：前端只读 date/yi/ji——pengzu/shensha/lunar/
                # chongsha 不随列表回吐（92天×12.9KB→~2KB）。
                for _q in huangli_mod.find_good_days(dt, end, terms)]
        return {"affair": affair, "terms": terms,
                "start": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
                "days": days, "good_days": good, "count": len(good)}

    q = huangli_mod.day_query(dt)
    # R229z续21c（R9-P1-3）：黄历卡干支年走春节口径、排盘年柱走立春口径，
    # 春节↔立春窗口期两值并存——只在真正错位的日子给提示键（窗口全落在
    # 公历 1-3 月，其余日子不算这笔账）。
    _ynote = {}
    _lunar_gz = (q.get("lunar") or {}).get("ganzhi_year_cn", "")
    if _lunar_gz and dt.month <= 3:
        try:
            _p = bazi_compute(dt.year, dt.month, dt.day, 12, "男")
            _bz_year = _p.year or ""
            _ln_year = _lunar_gz.replace("年", "")
            if _bz_year and _ln_year and _bz_year != _ln_year:
                _ynote["year_note"] = (
                    f"干支年双口径：民俗黄历按正月初一换年（{_lunar_gz}），"
                    f"排盘按立春换年（{_bz_year}年）——都正常，看哪个口径")
        except Exception:
            pass
    return {"date": q["date"], "yi": q["yi"], "ji": q["ji"],
            "jianchu": q.get("jianchu"), "xiu": q.get("xiu"),
            "pengzu": q.get("pengzu"), "shensha": q.get("shensha"),
            **({"conflict": q["conflict"]} if q.get("conflict") else {}),
            **_ynote,
            **({"cross_ref": _cross_ref_huangli(date_str)}),  # C-003：黄历交叉引用
            **({"lunar": q["lunar"]} if q.get("lunar") else {}),
            **({"chongsha": q["chongsha"]} if q.get("chongsha") else {}),
            **({"day_flags": q["day_flags"]} if q.get("day_flags") else {}),
            # R233w（R52-P3-9）：交节日透明化——「今日交节 XX，交在 HH:MM」
            **({"term_today": q["term_today"]}
               if q.get("term_today") else {})}


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
# R233r（R49-P2-2）：已成事实的口语标记（分手了/辞职了/怀孕了…）与
# 决策意图词表——高敏场景先判「这是倾诉还是问日子」。
_ALREADY_HAPPENED_PAT = re.compile(
    r"(分手|辞职|离职|离婚|退婚|毁约|怀孕|分居|复合|领证|再婚|生娃|"
    r"生子|手术|开刀|搬家|开业|装修|买车|买房|流产|堕胎|解约|被拒|"
    r"被裁|出轨|劈腿|订婚)了|已(经)?(分手|辞职|离职|离婚|怀孕|订婚)|"
    r"刚(分手|辞职|离职|离婚|怀孕|被裁|做完手术)")
_DECIDE_INTENT_PAT = re.compile(
    r"该不该|要不要|适不适合|适合吗|合适吗|行吗|行不行|好不好|好吗|"
    r"可以吗|能不能|哪天|何日|哪日|几日|几号|什么时候|何时|怎么办|"
    r"咋办|咋办呢|选日子|挑日子|择日|吉日|吉利|黄道|宜不宜|后悔吗|"
    r"还有机会|有救吗|值得吗")

_CHAT_SCENE_TERMS: dict[str, list[str]] = {
    "面试": ["上任"], "求职": ["上任"], "上班": ["上任"], "入职": ["上任"],
    "约会": ["嫁娶"], "表白": ["嫁娶"], "相亲": ["嫁娶"], "结婚": ["嫁娶"],
    "领证": ["嫁娶"],
    # R229q：与前端 HL_SCENE_ALIAS 逐键同构（probe_date_parity 钉扎）。
    # 「平整」入搬家系（整理归置），「远行」作词条映射到出行。
    "搬家": ["移徙", "移徒", "入宅", "修造", "平整"],
    "挪窝": ["移徙", "移徒"], "远行": ["出行"],
    "装修": ["修造", "动土"], "动工": ["动土", "破土"],
    "开业": ["开市", "纳财"], "开张": ["开市"],
    "签约": ["立券", "纳财"], "合同": ["立券"],
    "出行": ["出行", "远行"], "旅行": ["出行", "远行"],
    "旅游": ["出行", "远行"], "出差": ["出行", "远行"], "出游": ["出行", "远行"],
    "收款": ["纳财"], "理财": ["纳财"], "看病": ["求医", "治病", "求医疗病"],
    "种花": ["栽种"], "种菜": ["栽种"], "许愿": ["祈福", "求嗣"],
    "拜拜": ["祭祀"], "祭灶": ["祭祀"], "祭祖": ["祭祀"],
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
    # R229w：逛街/出去玩/购物本质是出门——映射到出行给真判定（比
    # 永远中性卡有用）；聚餐系映射到出行+谒贵（出门见人）。
    # 健身/唱歌无对应规范词，保留自映射走中性口径。
    "聚餐": ["出行", "谒贵"], "请客": ["出行", "谒贵"],
    "聚会": ["出行", "谒贵"], "饭局": ["出行", "谒贵"],
    "购物": ["出行"], "买东西": ["出行"], "逛街": ["出行"],
    "出去玩": ["出行", "远行"],
    "健身": ["健身"], "运动": ["健身"], "唱歌": ["唱歌"], "唱k": ["唱歌"],
    # R230h（R20-F1）：「备孕/求子」→求嗣——此前前端靠 YI_MAP 描述串
    # 撞出「宜」、后端中性，同问相反；进词表后两侧同源判定。
    "备孕": ["求嗣"], "求子": ["求嗣"], "要孩子": ["求嗣"],
    "生子": ["求嗣"], "怀孕": ["求嗣"],
    # R2349（R64-P1-5）：真实语料补词——小红书客群高频说法此前全落
    # 中性卡（120 条语料实测 80 条 P1 大头）。与前端 HL_SCENE_ALIAS
    # 逐键同构（probe_date_parity 钉扎）。
    # 考试/学业：考试祈福向——入学+祈福；答辩/复试面向评审→谒贵。
    "考研": ["入学", "祈福"], "期末考": ["入学", "祈福"],
    "期末": ["入学", "祈福"], "教资": ["入学", "祈福"],
    "科目二": ["入学", "祈福"], "科目三": ["入学", "祈福"],
    "考公": ["入学", "祈福"], "考证": ["入学", "祈福"],
    "考级": ["入学", "祈福"], "上岸": ["入学", "祈福"],
    "答辩": ["入学", "谒贵"], "复试": ["入学", "谒贵"],
    "报班": ["入学", "纳财"], "复习": ["入学"], "学习": ["入学"],
    "交论文": ["入学", "谒贵"], "论文": ["入学", "谒贵"],
    # 第二波补词：约饭/面基/奔现是见人→谒贵+出行；偶遇/自推/运气
    # 是心愿向→祈福；脱单/暧昧/crush 恋爱好感→嫁娶。
    "吃饭": ["出行", "谒贵"], "组局": ["出行", "谒贵"],
    "面基": ["出行", "谒贵"], "奔现": ["出行", "谒贵"],
    "偶遇": ["谒贵"], "自推": ["祈福"], "运气": ["祈福"],
    "脱单": ["嫁娶"], "暧昧": ["嫁娶"], "crush": ["嫁娶"],
    "异地恋": ["嫁娶"], "出门玩": ["出行", "远行"],
    # 抽卡/手气系：玄学仪式感→祈福，花钱→纳财。
    "抽卡": ["纳财", "祈福"], "抽盲盒": ["纳财", "祈福"],
    "盲盒": ["纳财", "祈福"], "彩票": ["纳财"], "谷子": ["纳财"],
    "买谷子": ["纳财"], "手气": ["祈福"], "开池": ["纳财"],
    "出金": ["纳财"],
    # 美发/医美：头发→冠笄（及笄礼本义）；动针动刀→求医（医疗口径
    # 免责声明由 _MED_SCENE_TERMS 自动叠）。
    "烫发": ["冠笄"], "染发": ["冠笄"], "染头": ["冠笄"],
    "剪刘海": ["冠笄"], "刘海": ["冠笄"], "美甲": ["冠笄"],
    "纹眉": ["冠笄"], "美容": ["冠笄"],
    "do脸": ["求医"], "水光针": ["求医"], "双眼皮": ["求医"],
    "微整": ["求医"],
    # 婚恋/家庭：见长辈→谒贵+嫁娶；喜事→嫁娶；产检动身体→求医。
    "见家长": ["谒贵", "嫁娶"], "见父母": ["谒贵", "嫁娶"],
    # R2349d：「见男朋友家长」里「见家长」不连续——补「家长」兜底。
    "家长": ["谒贵", "嫁娶"],
    "订婚": ["嫁娶"], "提亲": ["嫁娶"], "彩礼": ["纳财"],
    "产检": ["求医"], "求婚": ["嫁娶"], "离婚": ["解除"],
    # 追星/演出：到场→出行+谒贵；抢票开票是花钱事→纳财。
    "抢票": ["纳财"], "开票": ["纳财"], "演唱会": ["出行", "谒贵"],
    "签售会": ["出行", "谒贵"], "见爱豆": ["出行", "谒贵"],
    "音乐节": ["出行"], "应援": ["出行"],
    # 宠物：领进门→进人口；动身体→求医。
    "接猫": ["进人口"], "领养": ["进人口"], "接新猫": ["进人口"],
    "接小猫": ["进人口"], "绝育": ["求医"], "打疫苗": ["求医"],
    "疫苗": ["求医"],
    # 租房/搬家：看房→出行+入宅；续租→立券。
    "看房": ["出行", "入宅"], "搬新窝": ["移徙", "入宅"],
    "续租": ["立券", "移徙"], "租房": ["立券", "入宅"],
    # 求职：见工→谒贵/上任；被裁→解除；花钱方向→纳财。
    "找工作": ["上任", "谒贵"], "被裁": ["解除"], "裁员": ["解除"],
    "海投": ["上任"], "简历": ["上任"], "终面": ["上任", "谒贵"],
    "报到": ["上任"], "谈加薪": ["谒贵", "纳财"], "加薪": ["纳财", "谒贵"],
    # 复合/摊牌：破镜重圆→嫁娶；掰扯清楚→解除。
    "复合": ["嫁娶"], "和好": ["嫁娶"], "把话说开": ["解除"],
    "摊牌": ["解除"], "删好友": ["解除"],
    # 生意/副业：→开市+纳财。
    "开店": ["开市", "纳财"], "副业": ["开市", "纳财"],
    "上新": ["开市"], "摆摊": ["开市", "纳财"], "生意": ["开市", "纳财"],
    "网店": ["开市", "纳财"],
    # 出行变体：回家/团圆/出发/一日游/看电影。
    "回家": ["出行"], "团圆": ["出行", "谒贵"], "出发": ["出行"],
    "一日游": ["出行"], "自驾游": ["出行"], "看电影": ["出行"],
    # 杂项：要微信/发消息→嫁娶/谒贵；上香拜庙→祭祀；囤货→纳财。
    "要微信": ["嫁娶"], "发消息": ["谒贵"], "见面": ["谒贵"],
    "上香": ["祭祀"], "拜庙": ["祭祀"], "囤货": ["纳财"],
    # R2349f 第三波（R64 语料长尾）：考试细分→求名/入学；内容创业→开市+纳财；
    # 医美轻项目→求医/冠笄；娱乐社交→出行+谒贵；断联→解除。
    # 科目二/三、考公、教资、洗牙、体检、烫头已在上面词表（入学/祈福/求医/冠笄）。
    "雅思": ["求名", "入学"], "托福": ["求名", "入学"],
    "四六级": ["求名", "入学"], "驾考": ["求名"],
    "考编": ["求名", "上任"], "专升本": ["求名", "入学"],
    "直播": ["开市", "纳财"], "带货": ["纳财", "开市"],
    "自媒体": ["开市", "纳财"], "做号": ["开市"], "起号": ["开市"],
    "打耳洞": ["求医"],
    "种睫毛": ["冠笄"], "漂发": ["冠笄"],
    "剧本杀": ["出行", "谒贵"], "密室": ["出行"], "桌游": ["出行", "谒贵"],
    "露营": ["出行"], "爬山": ["出行", "登山"], "徒步": ["出行", "登山"],
    "野餐": ["出行"], "断联": ["解除", "祈福"], "冷战": ["解除"],
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
    # R229z：节日/农历问法常见繁体（中秋節/國慶/農曆/聖誕/兒童節/重陽/萬聖節/舊曆）
    "節": "节", "婦": "妇", "萬": "万", "兒": "儿", "誕": "诞",
    "慶": "庆", "陽": "阳", "舊": "旧", "農": "农", "陰": "阴", "號": "号", "餘": "余",
    # 节气繁体（驚蟄/穀雨——種處已在前面）
    "驚": "惊", "蟄": "蛰", "穀": "谷", "竈": "灶",
}


def _t2s(s: str) -> str:
    return "".join(_T2S.get(ch, ch) for ch in s)


# ── R229z：绝对日期 / 节日 / 农历表达 ────────────────────────────
# 「10月1日」「9-25」「25号」「下个月5号」「国庆」「中秋」「农历八月十五」
# 此前全部静默按今天判（R228r 同类伤：说错日期比不答更伤）。
# 统一口径——就近取：当年未过取当年；已过且有过去语标（那天/过了…）落当年
# （复盘口径能消化过去），无语标顺到下一个同档（明年/下个月）。

# 公历节日（固定月日）；「十一/五一/六一/五四」这类数字节需防「十一月」
# 误命中——匹配后紧跟计量字（月/日/号/天/个/年）时跳过。
_HOLIDAY_SOLAR = {
    "元旦": (1, 1), "新年": (1, 1), "情人节": (2, 14), "妇女节": (3, 8),
    "植树节": (3, 12), "愚人节": (4, 1), "劳动节": (5, 1), "五一": (5, 1),
    "青年节": (5, 4), "儿童节": (6, 1), "建党节": (7, 1), "建军节": (8, 1),
    "教师节": (9, 10), "国庆节": (10, 1), "国庆": (10, 1), "十一": (10, 1),
    "万圣节": (11, 1), "平安夜": (12, 24), "圣诞节": (12, 25),
    "圣诞": (12, 25), "跨年": (12, 31),
    # R230a-3：双十一/中元节/小年补洞——「双十一」带「十一」前缀需防
    # 「双十一月」式误命中，下方 same-digit 计量字防呆规则已覆盖
    # （节后紧跟 月/日/号/天/个/年 跳过）。
    "双十一": (11, 11), "光棍节": (11, 11),
    # R233v（R52-P2-5）：口语高频节别名补洞
    "三八节": (3, 8), "女生节": (3, 7), "520": (5, 20), "521": (5, 21),
    "网络情人节": (5, 20), "白色情人节": (3, 14), "圣诞夜": (12, 24),
}
# 农历节日（月, 日）；除夕单列（正月初一前一天）。
_HOLIDAY_LUNAR = {
    "大年初一": (1, 1), "春节": (1, 1), "元宵节": (1, 15), "元宵": (1, 15),
    "端午节": (5, 5), "端午": (5, 5), "七夕": (7, 7), "中秋节": (8, 15),
    "中秋": (8, 15), "重阳节": (9, 9), "重阳": (9, 9), "腊八节": (12, 8),
    "腊八": (12, 8), "中元节": (7, 15), "中元": (7, 15),
    # 小年按北方通行腊月廿三；南方廿四口径暂不强拆，spoken 仍回用户原词。
    "小年": (12, 23),
    # R233v（R52-P2-5）：民俗高频农历节补洞
    "龙抬头": (2, 2), "二月二": (2, 2), "上巳节": (3, 3), "三月三": (3, 3),
    "花朝节": (2, 15), "寒衣节": (10, 1), "十月朝": (10, 1),
    "下元节": (10, 15), "七夕节": (7, 7),
}
_CN_DIGIT = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def _lunar_md(mtxt: str, dtxt: str):
    """农历月日串（中文或数字）→ (month, day)；解不动返回 None。"""
    m_map = {"正": 1, "冬": 11, "腊": 12, "十一": 11, "十二": 12,
             **_CN_DIGIT}
    m = int(mtxt) if mtxt.isdigit() else m_map.get(mtxt)
    if m is None or not (1 <= m <= 12):
        return None
    if dtxt.isdigit():
        d = int(dtxt)
    elif dtxt.startswith("初"):                    # 初一..初十
        d = _CN_DIGIT.get(dtxt[1:], 0) if len(dtxt) == 2 else 0
        if dtxt[1:] == "十":
            d = 10
    elif dtxt.startswith("廿"):                    # 廿一..廿九
        # R233w（R52-P3-10）：裸「廿」「廿十」此前静默落成 20——
        # 「廿」是前缀不是数字，尾部必须是中文数字。
        if len(dtxt) != 2 or dtxt[1:] not in _CN_DIGIT:
            return None
        d = 20 + _CN_DIGIT[dtxt[1:]]
    elif dtxt == "二十":
        d = 20
    elif dtxt == "三十":
        d = 30
    elif dtxt.startswith("十"):                    # 十一..十九
        d = 10 + _CN_DIGIT.get(dtxt[1:], 0) if len(dtxt) > 1 else 10
    else:
        return None
    return (m, d) if 1 <= d <= 30 else None


def _nearest_day(cands: list, now: datetime, past: bool):
    """候选公历日里按口径挑一个：过去语标 → ≤今天的最近者；否则 →
    ≥今天的最近者；都没有 → 离今天最近。"""
    today = now.date()
    fut = sorted(d for d in cands if d >= today)
    pst = sorted((d for d in cands if d <= today), reverse=True)
    if past and pst:
        return pst[0]
    if not past and fut:
        return fut[0]
    pool = pst if past else fut
    if pool:
        return pool[0]
    return min(cands, key=lambda d: abs((d - today).days)) if cands else None


# 第 N 个周日类节日：(月, weekday[周一=0], 第几个)
_HOLIDAY_NTH = {
    "母亲节": (5, 6, 2), "父亲节": (6, 6, 3), "感恩节": (11, 3, 4),
}
# 节气也可当日期词（「冬至吃饺子」「立春后开工」）——term_time 走
# 天文算法。排除：小满（小满是本应用吉祥物名，「小满觉得我…」是在
# 叫它不是问节气）、大雪/小雪/大寒/小寒（天气语境歧义太大）。
_SOLAR_TERMS = {
    "立春", "雨水", "惊蛰", "春分", "谷雨", "立夏", "芒种", "夏至",
    "处暑", "白露", "秋分", "寒露", "霜降", "立冬", "冬至", "大暑",
    "小暑",
}


def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    """y 年 m 月第 n 个 weekday（周一=0）的公历日。"""
    first_wd = date(y, m, 1).weekday()
    return date(y, m, 1 + (wd - first_wd) % 7 + 7 * (n - 1))


# R233v（R52-P2-4）：法定节假日放假表（国务院办公厅通知口径，
# 写死可核验；「节后上班/收假/小长假」这类词此前静默按今天判）。
# 行：(节日名, 放假起, 放假止, 调班上班日 tuple)
_LEGAL_SPANS: list[tuple[str, date, date, tuple]] = [
    ("元旦", date(2024, 1, 1), date(2024, 1, 1), ()),
    ("春节", date(2024, 2, 10), date(2024, 2, 17),
     (date(2024, 2, 4), date(2024, 2, 18))),
    ("清明", date(2024, 4, 4), date(2024, 4, 6), (date(2024, 4, 7),)),
    ("劳动节", date(2024, 5, 1), date(2024, 5, 5),
     (date(2024, 4, 28), date(2024, 5, 11))),
    ("端午", date(2024, 6, 8), date(2024, 6, 10), ()),
    ("中秋", date(2024, 9, 15), date(2024, 9, 17), (date(2024, 9, 14),)),
    ("国庆", date(2024, 10, 1), date(2024, 10, 7),
     (date(2024, 9, 29), date(2024, 10, 12))),
    ("元旦", date(2025, 1, 1), date(2025, 1, 1), ()),
    ("春节", date(2025, 1, 28), date(2025, 2, 4),
     (date(2025, 1, 26), date(2025, 2, 8))),
    ("清明", date(2025, 4, 4), date(2025, 4, 6), ()),
    ("劳动节", date(2025, 5, 1), date(2025, 5, 5), (date(2025, 4, 27),)),
    ("端午", date(2025, 5, 31), date(2025, 6, 2), ()),
    ("国庆中秋", date(2025, 10, 1), date(2025, 10, 8),
     (date(2025, 9, 28), date(2025, 10, 11))),
    ("元旦", date(2026, 1, 1), date(2026, 1, 3), (date(2026, 1, 4),)),
    ("春节", date(2026, 2, 15), date(2026, 2, 23),
     (date(2026, 2, 14), date(2026, 2, 28))),
    ("清明", date(2026, 4, 4), date(2026, 4, 6), ()),
    ("劳动节", date(2026, 5, 1), date(2026, 5, 5), (date(2026, 5, 9),)),
    ("端午", date(2026, 6, 19), date(2026, 6, 21), ()),
    ("中秋", date(2026, 9, 25), date(2026, 9, 27), ()),
    ("国庆", date(2026, 10, 1), date(2026, 10, 7),
     (date(2026, 9, 20), date(2026, 10, 10))),
]


_SPAN_NAME = {"国庆": "国庆", "春节": "春节", "过年": "春节",
              "中秋": "中秋", "五一": "劳动节", "劳动": "劳动节",
              "端午": "端午", "清明": "清明", "元旦": "元旦"}


def _span_phrase(msg_n: str, now: datetime):
    """假期间隔词 → (date, spoken)。「国庆节后第一天上班」=国庆假止日
    +1（法定表口径，不是国庆日+1）；「收假/假期最后一天」=在进行的或
    下一个假期的止日；「小长假/什么时候放假」=下一个假期起日；
    「调班/补班」=下一个调班上班日。消息里带节日名时钉死那一档。"""
    td = now.date()
    spans = sorted(_LEGAL_SPANS, key=lambda r: r[1])
    # 消息限定的节日档（「国庆中秋」合档对 国庆/中秋 同名命中）
    named = next((v for w, v in _SPAN_NAME.items() if w in msg_n), None)
    pool = [r for r in spans if not named
            or named in r[0] or r[0] in named]
    # R2349（R64-P1-4）：「国庆后第一天上班」——「后第N天」挂到假止日
    # 后数 N 天（原写法漏匹配，落「国庆」+后缀错算成 10/2）。
    _afm = re.search(r"后第([一二三四五1-5])天", msg_n)
    _afn = 1
    if _afm:
        _afn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}.get(
            _afm.group(1)) or int(_afm.group(1))
    if re.search(r"(节后|假期后|过完节|收假|收心|假期结束|上班第一天)",
                 msg_n) or (_afm and named):
        nxt = [r for r in pool if r[2] >= td]
        _afw = ["", "一", "二", "三", "四", "五"][_afn]
        if nxt:
            return nxt[0][2] + timedelta(days=_afn), f"{nxt[0][0]}后第{_afw}天"
        done = [r for r in pool if r[2] < td]
        if done:
            return done[-1][2] + timedelta(days=_afn), f"{done[-1][0]}后第{_afw}天"
    if re.search(r"假期最后一天|最后一天假|假期的尾巴", msg_n):
        live = [r for r in pool if r[1] <= td <= r[2]]
        nxt = [r for r in pool if r[1] > td]
        done = [r for r in pool if r[2] < td]
        tgt = live[0] if live else (nxt[0] if nxt else
                                    (done[-1] if done else None))
        if tgt:
            return tgt[2], f"{tgt[0]}假期最后一天"
    if re.search(r"小长假|什么时候放假|啥时候放假|放假", msg_n):
        nxt = [r for r in pool if r[1] >= td or r[2] >= td]
        if nxt:
            name, _a, _b, _mk = nxt[0]
            return _a, f"{name}假期"
    if re.search(r"调班|调休上班|补班", msg_n):
        mk = sorted({d for _n, _a, _b, mks in spans for d in mks})
        nxt = [d for d in mk if d >= td]
        if nxt:
            return nxt[0], "调班上班日"
    return None


def _holiday_candidates(name: str, now: datetime,
                        yoff: int | None = None) -> list:
    """节日词 → 候选公历 date 列表。yoff=None 取相邻三年就近；
    有年前缀（去年/明年…）时钉死那一年。"""
    from guji import lunar as lunar_mod
    out: list = []
    if name in _HOLIDAY_SOLAR:
        m, d = _HOLIDAY_SOLAR[name]
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        return [date(y, m, d) for y in yrs]
    if name in _HOLIDAY_NTH:
        m, wd, n = _HOLIDAY_NTH[name]
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        return [_nth_weekday(y, m, wd, n) for y in yrs]
    if name in ("除夕", "大年三十", "大年夜", "年三十"):
        try:
            ly0 = lunar_mod.solar_to_lunar(now.year, now.month,
                                           now.day)["year"]
        except ValueError:
            ly0 = now.year
        lys = range(ly0 - 1, ly0 + 2) if yoff is None else [ly0 + yoff]
        for ly in lys:
            try:
                out.append(lunar_mod.lunar_to_solar(ly + 1, 1, 1)
                           - timedelta(days=1))
            except ValueError:
                pass
        return out
    if name == "寒食节":
        from guji import bazi as bazi_mod
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        for y in yrs:
            try:
                out.append((bazi_mod.term_time(y, "清明")
                            + timedelta(hours=8)).date()
                           - timedelta(days=1))
            except Exception:
                pass
        return out
    if name in ("入伏", "三伏"):
        from guji import bazi as bazi_mod
        # 夏至后第三个庚日入伏（庚=天干第7）——逐日数干支可核验。
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        for y in yrs:
            try:
                xz = (bazi_mod.term_time(y, "夏至") + timedelta(hours=8)).date()
                cnt = 0
                for k in range(0, 40):
                    dd = xz + timedelta(days=k)
                    if bazi_mod.day_ganzhi(datetime(dd.year, dd.month,
                                                    dd.day))[0][0] == "庚":
                        cnt += 1
                        if cnt == 3:
                            out.append(dd)
                            break
            except Exception:
                pass
        return out
    if name in ("数九", "入九"):
        from guji import bazi as bazi_mod
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        for y in yrs:
            try:
                out.append((bazi_mod.term_time(y, "冬至")
                            + timedelta(hours=8)).date())
            except Exception:
                pass
        return out
    if name == "清明":
        from guji import bazi as bazi_mod
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        for y in yrs:
            try:
                out.append((bazi_mod.term_time(y, "清明")
                            + timedelta(hours=8)).date())
            except Exception:
                pass
        return out
    if name in _SOLAR_TERMS:
        from guji import bazi as bazi_mod
        yrs = range(now.year - 1, now.year + 2) if yoff is None \
            else [now.year + yoff]
        for y in yrs:
            try:
                out.append((bazi_mod.term_time(y, name)
                            + timedelta(hours=8)).date())
            except Exception:
                pass
        return out
    if name in _HOLIDAY_LUNAR:
        lm, ld = _HOLIDAY_LUNAR[name]
        try:
            ly0 = lunar_mod.solar_to_lunar(now.year, now.month,
                                           now.day)["year"]
        except ValueError:
            ly0 = now.year
        lys = range(ly0 - 1, ly0 + 2) if yoff is None else [ly0 + yoff]
        for ly in lys:
            try:
                out.append(lunar_mod.lunar_to_solar(ly, lm, ld))
            except ValueError:
                pass
    return out


def _day_suffix(msg_n: str, end: int) -> tuple[int, int]:
    """日期词后紧跟的「前一天/前两天/后/次日…」→ (天数偏移, 吃掉字符数)。"""
    tail = msg_n[end:end + 6]
    for pat, d in (("大前天", -3), ("的前三天", -3), ("后第三天", 3),
                   ("后的第三天", 3), ("的后三天", 3), ("前三天", -3),
                   ("的前三天", -3), ("前两天", -2), ("头两天", -2),
                   ("的前两天", -2), ("后第二天", 2), ("的第二天", 2),
                   ("后两天", 2), ("前一天", -1), ("头一天", -1),
                   ("的前一天", -1), ("之后", 1), ("次日", 1),
                   ("第二天", 1), ("后一天", 1), ("之前", -1),
                   ("前", -1), ("后", 1)):
        if tail.startswith(pat):
            return d, len(pat)
    return 0, 0


def _abs_or_holiday(msg: str, now: datetime):
    """绝对日期/节日/农历表达 → (datetime, 用户原词)；解不出返回 None。

    顺序就是特异性：农历先（不被公历数字式抢）、节日（长词优先且防
    「十一月」误命中）、下个月X号/这个月X号、M月D日/M-D/M/D、月底月初、
    裸 D号。过去的判定看语标（那天/过了/已经/当时/去了）。
    """
    msg_n = _t2s(msg)          # R229z：繁体节日/农历/语标先归一再匹配
    past = any(w in msg_n for w in ("那天", "过了", "已经", "当时", "去了"))
    # 「去年/明年/前年/后年」年前缀——约束节日与 M月D 的候选年
    # （「去年国庆」不能再就近到今年）。
    _ypre = {"前年": -2, "去年": -1, "今年": 0, "明年": 1, "后年": 2}
    yoff = next((v for w, v in _ypre.items() if w in msg_n), None)
    from guji import lunar as lunar_mod

    # 农历：可带「农历/阴历/旧历」前缀与「闰」标记；无前缀时只接
    # 正/冬/腊 三个纯农历月名（「八月十五」有歧义不放行）。
    lm = re.search(
        r"(农历|阴历|旧历)?(闰)?"
        r"([正一二两三四五六七八九十冬腊\d]{1,2})月"
        r"([初廿一二三四五六七八九十\d]{1,3})[日号]?", msg_n)
    if lm and not lm.group(1) and not lm.group(2) \
            and lm.group(3) not in ("正", "冬", "腊"):
        lm = None                     # 「八月十五」无前缀不猜农历
    if lm:
        md = _lunar_md(lm.group(3), lm.group(4))
        if md:
            is_leap = bool(lm.group(2))
            try:
                ly0 = lunar_mod.solar_to_lunar(now.year, now.month,
                                               now.day)["year"]
            except ValueError:
                ly0 = now.year
            lys = range(ly0 - 1, ly0 + 2) if yoff is None else [ly0 + yoff]
            # 闰月稀疏（1900-2100 间十多年才一闰）——放宽到 ±12 个农历年
            # 并让 leap_month 把守，找真正带这个闰月的年份。
            if is_leap and yoff is None:
                lys = [ly for ly in range(ly0 - 12, ly0 + 13)
                       if lunar_mod.leap_month(ly) == md[0]]
            cands = []
            for ly in lys:
                try:
                    cands.append(lunar_mod.lunar_to_solar(ly, *md, is_leap))
                except ValueError:
                    pass
            if is_leap and cands:
                # 闰月稀疏（常隔十几年）——「闰六月十五」多数在说记忆里
                # 的那一天，按绝对就近取（过去语标仍优先落过去）。
                if past:
                    _ps = [d for d in cands if d <= now.date()]
                    pick = _ps[-1] if _ps else min(
                        cands, key=lambda d: abs((d - now.date()).days))
                else:
                    pick = min(cands,
                               key=lambda d: abs((d - now.date()).days))
            else:
                pick = _nearest_day(cands, now, past)
            if pick:
                _dl, _ln = _day_suffix(msg_n, lm.end())
                return (datetime.combine(pick + timedelta(days=_dl),
                                         now.time()),
                        msg_n[lm.start():lm.end() + _ln])

    # 「腊月底/正月末」：农历月末——无前缀同样只放纯农历月名。
    lme = re.search(
        r"(农历|阴历|旧历)?([正冬腊一二两三四五六七八九十]{1,2})月"
        r"(底|末)", msg_n)
    if lme and (lme.group(1)
                or lme.group(2) in ("正", "冬", "腊")):
        _mm = _lunar_md(lme.group(2), "初一")
        if _mm:
            try:
                ly0 = lunar_mod.solar_to_lunar(now.year, now.month,
                                               now.day)["year"]
            except ValueError:
                ly0 = now.year
            lys = range(ly0 - 1, ly0 + 2) if yoff is None else [ly0 + yoff]
            cands = []
            for ly in lys:
                try:
                    cands.append(lunar_mod.lunar_to_solar(
                        ly, _mm[0], lunar_mod.month_days(ly, _mm[0])))
                except ValueError:
                    pass
            pick = _nearest_day(cands, now, past)
            if pick:
                _dl, _ln = _day_suffix(msg_n, lme.end())
                return (datetime.combine(pick + timedelta(days=_dl),
                                         now.time()),
                        msg_n[lme.start():lme.end() + _ln])

    for name in sorted(set(_HOLIDAY_SOLAR) | set(_HOLIDAY_LUNAR)
                       | set(_HOLIDAY_NTH) | _SOLAR_TERMS
                       | {"除夕", "清明", "清明節", "大年三十", "大年夜",
                          "年三十", "寒食节", "入伏", "三伏", "数九"},
                       key=len, reverse=True):
        w = "清明" if name == "清明節" else name
        if w not in msg_n:
            continue
        widx = msg_n.find(w)
        # 「双十一」误命中「十一」：数字节前一个字是数字/双 时跳过。
        if widx > 0 and msg_n[widx - 1] in "双十廿一二两三四五六七八九":
            continue
        idx = widx + len(w)
        if idx < len(msg_n) and msg_n[idx] in "月日号天個个年":
            # R233v：「三伏天/数九天」的「天」是词的一部分，不是计量字
            if not (w in ("三伏", "入伏", "数九") and msg_n[idx] == "天"):
                continue                  # 「十一月」之类误命中
        cands = _holiday_candidates("清明" if name == "清明節" else name,
                                  now, yoff)
        # R2349（R64-P0-B）：节日是年复一年的——「七夕那天领证」的「那天」
        # 只是回指节日，用户几乎总在问下一次；原 past 语标把她拽回今年
        # 已过的节日判忌。节日词对 past 免疫（yoff 年前缀仍钉死年份）。
        pick = _nearest_day(cands, now, False)
        if pick:
            _dl, _ln = _day_suffix(msg_n, idx)
            _sp = msg_n[widx:idx + _ln]
            return (datetime.combine(pick + timedelta(days=_dl),
                                     now.time()), _sp or w)

    nm = re.search(r"下[个個]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if nm:
        d = int(nm.group(1))
        ny, nmth = now.year + (now.month == 12), (now.month % 12) + 1
        try:
            _dl, _ln = _day_suffix(msg_n, nm.end())
            return (datetime(ny, nmth, d) + timedelta(days=_dl),
                    msg_n[nm.start():nm.end() + _ln])
        except ValueError:
            pass
    tm = re.search(r"这[个個]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if tm:
        try:
            _dl, _ln = _day_suffix(msg_n, tm.end())
            return (datetime(now.year, now.month, int(tm.group(1)))
                    + timedelta(days=_dl),
                    msg_n[tm.start():tm.end() + _ln])
        except ValueError:
            pass

    pm = re.search(r"上[个個]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if pm:
        d = int(pm.group(1))
        py_, pmth = (now.year - 1, 12) if now.month == 1 \
            else (now.year, now.month - 1)
        try:
            _dl, _ln = _day_suffix(msg_n, pm.end())
            return (datetime(py_, pmth, d) + timedelta(days=_dl),
                    msg_n[pm.start():pm.end() + _ln])
        except ValueError:
            pass

    am = (re.search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?(?![线楼室幢座栋层院门])", msg_n)
          or re.search(r"(?<!\d)(\d{1,2})\s*[/\-.](\d{1,2})(?!\d)", msg_n))
    if am:
        m, d = int(am.group(1)), int(am.group(2))
        cands = []
        for y in range(now.year - 1, now.year + 2):
            try:
                cands.append(date(y, m, d))
            except ValueError:
                pass
        if yoff is not None:
            cands = [dd for dd in cands if dd.year == now.year + yoff]
        pick = _nearest_day(cands, now, past)
        if pick:
            _dl, _ln = _day_suffix(msg_n, am.end())
            return (datetime.combine(pick + timedelta(days=_dl),
                                     now.time()),
                    msg_n[am.start():am.end() + _ln])

    if "月底" in msg or "月末" in msg:
        import calendar
        cands = [date(now.year + (now.month == 12), (now.month % 12) + 1,
                      calendar.monthrange(now.year + (now.month == 12),
                                          (now.month % 12) + 1)[1]),
                 date(now.year, now.month,
                      calendar.monthrange(now.year, now.month)[1])]
        pick = _nearest_day(cands, now, past)
        if pick:
            _w0 = msg_n.find("月底") if "月底" in msg_n else msg_n.find("月末")
            _dl, _ln = _day_suffix(msg_n, _w0 + 2)
            return (datetime.combine(pick + timedelta(days=_dl), now.time()),
                    msg_n[_w0:_w0 + 2 + _ln])
    # 「月初」须排除农历日语境——「五月初一」里的「月初」不是月初。
    _yc = re.search(r"月初(?!一|二|两|三|四|五|六|七|八|九|十|廿|\d)", msg_n)
    if _yc:
        cands = [date(now.year + (now.month == 12), (now.month % 12) + 1, 1),
                 date(now.year, now.month, 1)]
        pick = _nearest_day(cands, now, past)
        if pick:
            _w0 = _yc.start()
            _dl, _ln = _day_suffix(msg_n, _w0 + 2)
            return (datetime.combine(pick + timedelta(days=_dl), now.time()),
                    msg_n[_w0:_w0 + 2 + _ln])

    # 裸「D号/D日」：防「3号线/25号楼/8号院」误命中——后接线路/楼栋字跳过。
    bd = re.search(r"(?<![\d月/\-])(\d{1,2})\s*[号日](?![\d日线楼室幢座栋层院门])", msg_n)
    if bd:
        d = int(bd.group(1))
        cands = []
        for dy, dm in ((now.year, now.month),
                       (now.year + (now.month == 12), (now.month % 12) + 1)):
            try:
                cands.append(date(dy, dm, d))
            except ValueError:
                pass
        pick = _nearest_day(cands, now, past)
        if pick:
            _dl, _ln = _day_suffix(msg_n, bd.end())
            return (datetime.combine(pick + timedelta(days=_dl),
                                     now.time()),
                    msg_n[bd.start(1):bd.end() + _ln].lstrip())
    return None


def _hl_day_part(msg: str, now: datetime) -> tuple[datetime, str]:
    """消息里的相对日（明天/后天/昨天/下周X/周末…），默认今天。

    返回 (目标日期, 用户原词)——原词要写进事实行（「下周三（9/23）的黄历…」），
    否则 LLM 不知道用户说的「下周三」是哪一天，会自己换算出错误日期
    （R228w 实测：9/19 说「下周三」，模型答成 9/30）。

    R228r（chat-flow 审查）：原先只有明天/后天/大后天三档，昨天/下周X/周末
    静默按今天判——说错日期比不答更伤（用户拿「明天」的答案去安排「下周」）。
    """
    if "大后天" in msg or "大後天" in msg or "大后日" in msg:
        return now + timedelta(days=3), "大后天"
    if "大前天" in msg or "大前日" in msg:
        return now - timedelta(days=3), "大前天"
    # R230a-6（R12-P3-3）：「日」字辈（后日/前日）此前前端会解、后端不
    # 认——同一句问法两侧判定不同天（parity 探针已钉扎）。
    if "后天" in msg or "後天" in msg or "后日" in msg or "後日" in msg:
        return now + timedelta(days=2), "后天"
    if "过两天" in msg or "過兩天" in msg:
        return now + timedelta(days=2), "过两天"
    if "前天" in msg or "前日" in msg:
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
    # R229z：绝对日期 / 节日 / 农历表达——先接住再落「下周」等相对词，
    # 否则「国庆后第一天上班」之类会被曜日通配截胡。
    # R233v（R52-P2-4）：假期间隔词（节后上班/小长假/调班）走法定
    # 假表——比「节日名+第N天」更特异，必须先接（「国庆节后第一天上班」
    # 此前被「国庆」+后缀「后第一天」错算成 10/2）。
    _sp = _span_phrase(_t2s(msg), now)
    if _sp is not None:
        # _LEGAL_SPANS 存的是 date——归一成 datetime 再交给下游
        # （parity 探针/聊天事实行都吃 datetime.date() 语义）。
        _sd, _ss = _sp
        if not isinstance(_sd, datetime):
            _sd = datetime(_sd.year, _sd.month, _sd.day)
        return _sd, _ss
    _abs = _abs_or_holiday(msg, now)
    if _abs is not None:
        return _abs
    # R229f：「本周X/这周X」此前根本没解析——静默按今天判（R228r 同类：
    # 说错日期比不答更伤）。本周一=0 基准；结果为负即本周已过的日子。
    for anchor in ("本周", "这周", "本週", "這週", "这週", "這周"):
        if anchor in msg:
            idx = msg.find(anchor) + len(anchor)
            if idx < len(msg) and msg[idx] in _WEEKDAY:
                wd = _wd_idx(msg[idx])
                return now + timedelta(days=wd - now.weekday()), msg[msg.find(anchor):idx + 1]
            break  # 「本周」无曜日字 → 不落下面 周末/今天 兜底，交给默认今天
    # R229y续：「下下周X/下下周末」——"下下周一"自身含"下周"，会被下面
    # 的「下周」通配截胡按下周判（差整 7 天）。先接住：以「再下一个周一」
    # 为基准。
    for anchor in ("下下周末", "下下週末"):
        if anchor in msg:
            nn_mon = now + timedelta(days=(14 - now.weekday()))
            return nn_mon + timedelta(days=5), "下下周末"
    for anchor in ("下下周", "下下週", "下下礼拜", "下下禮拜"):
        if anchor in msg:
            idx = msg.find(anchor) + len(anchor)
            nn_mon = now + timedelta(days=(14 - now.weekday()))
            if idx < len(msg) and msg[idx] in _WEEKDAY:
                wd = _wd_idx(msg[idx])
                return nn_mon + timedelta(days=wd), msg[msg.find(anchor):idx + 1]
            return nn_mon, "下下周"
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
    # R2349（R64-P1-4）：「年底/年末/岁尾」——当年 12/31 代表日；
    # 已在 12 月下旬后说「年底」多半指明年收尾，顺下一年。
    if re.search(r"年底|年末|岁尾", msg):
        _ey = now.year + (1 if (now.month, now.day) > (12, 20) else 0)
        return datetime(_ey, 12, 31), "年底"
    # 周末：下一个周六（今天已是周末则指今天）——R233v（R52-P2-4）：
    # 此前周日问「周末」gap=(5-6)%7=6 整段跳到下周六，今天被漏掉。
    if "周末" in msg or "週末" in msg:
        gap = 0 if now.weekday() >= 5 else (5 - now.weekday()) % 7
        return now + timedelta(days=gap), "周末"
    # R229h：裸曜日词「周五/礼拜天/星期日」= 最近的那个（今天命中即今天），
    # 不落在下周/本周之后误判。负向词（下周/本周）已在上面消化，这里只接
    # 无前缀的写法。
    m = re.search(r"(周|週|礼拜|禮拜|星期)([一二三四五六日天])", msg)
    if m:
        wd = _wd_idx(m.group(2))
        return now + timedelta(days=(wd - now.weekday()) % 7), m.group(0)
    # R233r（R49-Top5-5）：「最近/近期/这几天」此前落默认——spoken 被
    # 写成「今天」，模型不知道用户说的是一段日子。以今天为代表日并把
    # 原词写进事实行。
    for w in ("最近", "近期", "这几天", "這幾天", "这段时间", "這段時間",
              "本周", "这周", "本週", "這週"):
        if w in msg:
            return now, w
    return now, "今天"


def resolve_huangli_date(q: str, now: datetime | None = None) -> dict:
    """GET /api/huangli/resolve_date：把任意日期表达解成公历日。

    前端 _hlDayOffset 只覆盖高频相对词（明天/下周X…），节日/农历这类
    本地解不动的词走这里兜底；解不出返回 date=None，前端回退显示日。
    """
    now = now or datetime.now()
    q = (q or "").strip()[:80]
    if not q:
        return {"date": None, "spoken": ""}
    dt, spoken = _hl_day_part(q, now)
    # 「无日期词」与「显式说今天」在返回值上不可分——spoken=='今天'
    # 且消息里没有今天系词才算没解出。
    if spoken == "今天" and not any(
            w in q for w in ("今天", "今日", "今晚", "今夜")):
        return {"date": None, "spoken": ""}
    return {"date": dt.date().isoformat(), "spoken": spoken}


def _hl_next_yi_days(dt: datetime, terms: list[str],
                   span: int = 45, limit: int = 4) -> list[str]:
    """[dt, dt+span) 内宜任一规范词的日子（并集），返回 "M/D" 列表。"""
    # R229z续8：走 find_good_days（单日循环一次判定全部词，R8 P1-1；
    # 含宜∩忌双标日剔除 R228m）。
    out = [f"{int(q['date'][5:7])}/{int(q['date'][8:10])}"
           for q in huangli_mod.find_good_days(dt, dt + timedelta(days=span - 1),
                                               terms)]
    return out[:limit]


# R230t（R32-P1-9）：每条聊天消息都过事项词表+忌/中性时扫 45 天吉日——
# 结果只随（归一化消息, 当日）变。同日重复问法直接命中缓存。
_CHAT_FACTS_CACHE: dict = {}


def chat_huangli_facts(message: str, now: datetime | None = None) -> list[str]:
    """小满聊天的黄历事实供给：先把「适不适合」算成判定再交给 LLM。

    消息提到黄历事项词（口语词或规范词）→ 当日宜忌 + 判定 + 近期吉日；
    只泛问黄历（「今天宜做什么」「看看黄历」）→ 当日宜忌 + 中性口径说明；
    都不沾 → []（调用方原样透传，零扰动）。
    """
    now = now or datetime.now()
    # R230v（R34-#24）：键含原文指纹——此前 [:200] 截断，两条 200 字
    # 前缀相同的同日长消息会串事实行（概率极低但语义错）。
    _msg_norm = _t2s((message or "").strip())
    _ck = (_msg_norm[:200] + "#" + hashlib.sha1(
        _msg_norm.encode("utf-8")).hexdigest()[:12],
           now.date().isoformat())
    if _ck in _CHAT_FACTS_CACHE:
        return list(_CHAT_FACTS_CACHE[_ck])
    facts = _chat_facts_inner(message, now)
    if len(_CHAT_FACTS_CACHE) >= 512:
        _CHAT_FACTS_CACHE.clear()   # 键带日期，粗清即够
    _CHAT_FACTS_CACHE[_ck] = facts
    return list(facts)


def _chat_facts_inner(message: str, now: datetime) -> list[str]:
    """chat_huangli_facts 的计算主体（缓存键之外的一切都不变）。"""
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
                             "择日", "适合做什么", "适合干什么",
                             # R229o：「今天宜做什么」「明天忌什么」裸问法
                             "宜做什么", "忌做什么", "宜什么", "忌什么",
                             "做什么好", "干点啥", "能干啥", "能干什么"))
    dt, spoken = _hl_day_part(msg, now)
    # R233r（R49-P2-2）：高敏事项（分手/辞职/怀孕/离婚→解除/求嗣/嫁娶）
    # 已成事实且不带择日/决策意图 → 是倾诉不是问日子，别塞判定句把
    # 共情话头带歪。「我分手了怎么办」的「怎么办」仍算决策词放行。
    if (set(terms) & {"解除", "求嗣", "嫁娶"}
            and _ALREADY_HAPPENED_PAT.search(msg_n)
            and not _DECIDE_INTENT_PAT.search(msg_n)):
        return []
    if not scene and not generic:
        # R229o：带日期词的泛问（「下周末出去玩行吗」「明晚聚餐行不行」）——
        # 没命中事项词也没命中泛问词，但用户在问某天的日子，给当日宜忌
        # 总表而不是零事实放手让模型瞎答。
        if spoken != "今天" or any(
                w in msg for w in ("今天", "今日", "今晚", "今夜")):
            generic = True
        else:
            return []
    q = huangli_mod.day_query(dt)
    yi, ji = q["yi"], q["ji"]
    date_cn = q["date"]
    # R229z续21（R9-P1-2）：约 22% 日子同词宜忌同见——引用列表里把打架
    # 词摘出来单独标注，免得小满嘴里念出「宜嫁娶；忌嫁娶」。
    _cfl = q.get("conflict") or []
    yi_str = "、".join(w for w in yi if w not in _cfl) or "无"
    ji_str = "、".join(w for w in ji if w not in _cfl) or "无"
    _cfl_note = (f"另有宜忌相冲项：{'、'.join(_cfl)}（这些黄历自己都打架，"
                 "按存疑处理，别当凭据念）。" if _cfl else "")
    # R229o：「这周五」按本周已过日判（9/19 说这话指向 9/18）——事实行
    # 提醒这天已经过去，免得模型照着宜忌去「建议」一个回不去的日子。
    past_note = "（这天已经过去了）" if dt.date() < now.date() else ""
    facts = [f"{spoken}（{date_cn}）的黄历：宜【{yi_str}】；忌【{ji_str}】。"
             + _cfl_note + past_note]

    # R2349（R64-P1-4）：「生日」——日期在用户本地档案，接口拿不到；
    # 明说解不动请她补日期，别拿今天替她判（实测静默按今天判成 P1）。
    if "生日" in msg_n:
        facts.append("用户说的「生日」缺具体日期（生日存在用户本地档案里，"
                     "这边拿不到）——温和请她补一下生日或具体日期，"
                     "别按今天替她算。")
        return facts

    # R2349（R64-P1-6）：「哪天/什么时候+事项」是找日问法——直接给
    # 近 45 天宜它的日子列表，别绕回今天的宜忌判定。
    # 但只改「无日期词」的：带着明确日期的（「分手后哪天复合」里的哪天
    # 是真问日）仍走正常判定 + 清单双给。
    _find_intent = bool(re.search(r"哪天|什么时候|啥时候|几时|几号", msg_n))
    _find_only = _find_intent and scene and spoken == "今天" \
        and not any(w in msg for w in ("今天", "今日", "今晚", "今夜"))
    if _find_only:
        _gd = _hl_next_yi_days(dt, terms)
        if _gd:
            facts.append(f"用户在问「哪天{scene}好」——近45天里宜「{scene}」"
                         f"的日子：{'、'.join(_gd)}。直接给日子清单，"
                         "别按今天答宜忌。")
        else:
            facts.append(f"用户在问「哪天{scene}好」——近45天没有宜"
                         f"「{scene}」的日子；给最近的次优安排口径。")
        return facts

    if generic:
        facts.append("没列入当日宜忌的事项属中性——不是不支持，只是黄历没"
                     "为它背书，可照常安排；想要背书就挑宜它的日子。")
        if past_note:
            facts.append("该日期已过去，请温和点出、按复盘口径回应，"
                         "不要再给择日建议。")
        return facts

    hit_yi = [t for t in terms if any(t in w or w in t for w in yi)]
    hit_ji = [t for t in terms if any(t in w or w in t for w in ji)]
    # R229z续2：已过去的日子不给「近45天宜X」——从过去日起扫的全是过去日，
    # 且与「不要再给择日建议」的复盘指令自相矛盾。
    # R229z续8（R8 P1-1）：good_part 只在忌/中性分支引用——宜判定的路径
    # 不再白扫 45 天。
    def _good_part() -> str:
        if past_note:
            return ""
        g = _hl_next_yi_days(dt, terms)
        # R2349（R64-P2）：「宜分手/宜解除」直译刺耳——换「适合办X」口径。
        return (f"近45天适合{scene}的日子：{'、'.join(g)}——"
                "想要黄历背书可挑这几天。" if g else "")
    # R229v：已过去的日子不能只靠宜忌行尾巴的括号——模型实测会漏看，
    # 对着 9/18 的「宜面试」说出「周五冲一把」。把标记嵌进判定句本体，
    # 并要求回复口径改为复盘/温和指出而非择日建议。
    past_mid = "（这天已经过去）" if past_note else ""
    if hit_yi and not hit_ji:
        verdict = (f"黄历判定：{date_cn}{past_mid} 宜「{scene}」"
                   f"（宜项含【{'、'.join(hit_yi)}】）。")
    elif hit_ji and not hit_yi:
        verdict = (f"黄历判定：{date_cn}{past_mid} 忌「{scene}」"
                   f"（忌项含【{'、'.join(hit_ji)}】）；"
                   f"已安排也不必慌，放缓节奏即可。{_good_part()}")
    elif hit_yi and hit_ji:
        verdict = (f"黄历判定：{date_cn}{past_mid} 「{scene}」宜忌都有——"
                   f"宜【{'、'.join(hit_yi)}】也忌【{'、'.join(hit_ji)}】；"
                   f"想做就把节奏放缓，不赶大动作。")
    else:
        that_day = "今天" if dt.date() == now.date() else f"{spoken}（{date_cn}）"
        verdict = (f"黄历判定：{date_cn}{past_mid} 宜忌都没直接提「{scene}」——中性，"
                   f"不是不支持，只是黄历{that_day}没为它背书，{scene}可照常安排。"
                   f"{_good_part()}")
    if past_mid:
        verdict += "（该日期已过去，请温和点出、按复盘口径回应，不要再给择日建议。）"
    # R233g（R44-P1-7）：医疗类事项（求医/治病/手术/体检等）判词必须带
    # 「听医生的」口径——不让黄历背书医疗决策。
    if set(terms) & _MED_SCENE_TERMS:
        verdict += "（医疗事项：请在回复里带一句「看病以医生为准，黄历不作数」的口径。）"
    facts.append(verdict)
    return facts


# R233g：映射到医疗类宜忌词的事项集合（问一嘴/chat 两侧同表）
_MED_SCENE_TERMS = {"求医", "治病", "求医疗病", "开刀"}


def _draw_dicts(draws) -> list[dict]:
    return [{"index": d.index, "name": d.name, "upright": d.upright,
             "upright_kw": d.upright_kw, "reversed_kw": d.reversed_kw,
             "meaning": d.meaning, "position": d.position,
             "render": d.render()} for d in draws]


def tarot(req) -> dict:
    """塔罗牌阵：78 张静态牌表 + seed 确定性抽牌（固定 seed → 固定牌面）。"""
    req.validate_ranges()   # R230m：client_date 校验入口
    draws = tarot_mod.draw(seed=req.seed, n=req.n)
    cards = _draw_dicts(draws)
    interpretation = interpreter.interpret_tarot(cards, req.question)
    out = {
        "seed": req.seed,
        "n": len(cards),
        "draws": cards,
        "interpretation": interpretation,
        "warm": voice.warm_tarot(cards, interpretation, req.question),
        # R218a-巡2（N-01）：echo question 让前端 tarotQuestionHook 真生效
        "question": req.question,
        # R221b：交叉引用收口 7/7——塔罗不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_tarot(cards, today_iso=req.client_date),
    }
    # R230z（R36-P1-1）：塔罗进台账；摘要用问题或张数
    paipan_history.save_async(
        {"seed": req.seed, "n": req.n, "question": req.question},
        out, rtype="tarot",
        name=(req.question or f"{req.n} 张牌阵"))
    return out


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
    # R2349g：补「小吉」档——缺这个键时 daily() 直接 KeyError 进降级
    # 分支（level=平 + 全字段'—'），R230y 起每个小吉日都在静默出空卡。
    "小吉": ("宜小步推进、宜开口、宜尝新", "忌想太多、忌宅到底"),
    "凶": ("宜静养、宜守成、宜反思", "忌冲动、忌远行、忌争执"),
    "平": ("宜合作、宜静养、宜学习", "忌冲动、忌远行"),
}

_BAD_RELS = ("相害", "相刑", "自刑", "六冲")   # R228m：产出侧枚举是「六冲」（bazi_calc.py:141）
_GOOD_RELS = ("六合", "三合", "半合")


def fortune_level(calc_out: dict, day: "datetime | None" = None) -> str:
    """从运算事实推算运势等级（吉/小吉/平/凶）——结构化判断，非关键词匹配。

    day: 当日 datetime（用于天德/月德/天赦吉神加分）；缺省不加分。
    """
    if not calc_out:
        return "平"
    score = 0
    fe = calc_out.get("five_elements") or {}
    if len(fe.get("strong") or []) >= 2:
        score -= 1                                  # 两行偏旺，五行失衡
    # R2349g（R68-P0-3）：缺 1 行是常态（120 天里约 4 成），不该扣分；
    # 缺 ≥2 行（8 字里只有 3 种五行）才算失衡。
    if len(fe.get("missing") or []) >= 2:
        score -= 1
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
    # R2349g（R68-P0-3）：天德/月德/天赦是传统历法的吉神坐标——原来
    # 神煞全没参与计分，扣分项天然压过加分项，120 天里「凶」占 48%。
    # 补上吉神加分后实测分布：吉13% 小吉33% 平30% 凶23%。
    try:
        if day is not None and (
                huangli_mod.tiande(day) or huangli_mod.yuede(day)):
            score += 1
        if day is not None and huangli_mod.tianshe(day):
            score += 1
    except Exception:
        pass
    if score >= 2:
        return "吉"
    # R230y（R36-P2-7）：score==1 归「小吉」——此前该档从未产出，
    # copy_bank 里 4 条小吉文案是死池；接上后等级粒度 3→4 档。
    # R2349g：小吉放宽到 score>=0——天平居中本就是小顺，不是平平无奇。
    if score >= 0:
        return "小吉"
    return "凶" if score <= -3 else "平"


def fortune_summary(calc_out: dict) -> str:
    """从运算事实转述运势一句话（纯坐标转述，不新增结论）。

    R2349g（R68-P2）：copy_bank 的 levels 四档恒在时 daily() 不会走这里
    ——仅当 copy_bank 缺失/损坏时的兜底路径，保留勿删。
    """
    if not calc_out:
        return "今天的运势卡没算出来，稍后再看看～"
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
    # R231a（R36 口播残留）：「今天的干支是丁酉」是纯坐标转述，
    # 对普通用户无意义且日期词不随查询日漂移——整行删除，不补假锚点。
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
            # R2349g：cv=4——level 计分加了吉神项+小吉阈值放宽，
            # 且新增 noble_liuhe 字段；旧缓存一律重算覆盖。
            if _c.get("cv") == 4 and (not _want or _c.get("noble") == _want):
                return {"date": date_str, **_c, "cached": True}
    try:
        d = date.fromisoformat(date_str)
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        # R228m：?date=X 的 level 必须按请求日算——原来 bazi_calc(b) 缺省
        # 回退 date.today()，73/400 天等级被「今天」口径改写且被
        # daily_cache 固化成「写入日口径」。
        calc_out = bazi_calc(b, ask_date=date_str)
        level = fortune_level(calc_out, day=datetime(d.year, d.month, d.day, 12))
        do_str, dont_str = _LEVEL_ADVICE[level]
        # R214b：宜忌换年轻化表达（文案库优先，缺失回退旧表）。
        _db = _COPY_BANK.get("daily") or {}
        if _db:
            lvl_key = level if level in _db.get("levels", {}) else (
                "平" if level == "平" else level)
            summary = _pick(_db["levels"].get(lvl_key) or [], date_str, "sum")
            # R229z续4：同池两签会撞（实测"空腹喝冰美式、空腹喝冰美式"）——
            # 第二签从剔除首签的池子抽；池子只剩一条时允许原样。
            _y1 = _pick(_db["yi"], date_str, "y")
            _y2 = _pick([x for x in _db["yi"] if x != _y1] or _db["yi"],
                        date_str, "y2")
            do_str = _y1 + "、" + _y2
            _j1 = _pick(_db["ji"], date_str, "j")
            _j2 = _pick([x for x in _db["ji"] if x != _j1] or _db["ji"],
                        date_str, "j2")
            dont_str = _j1 + "、" + _j2
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
        # R2349g（R68-P0-2）：天乙贵人按日干推，10 干天然只有 ~5 组值，
        # 60 天必见大量重复。叠「日支六合」作第二层「合拍」生肖——
        # 日支 12 值轮转，组合丰富度翻倍且同为经典坐标（bazi_calc.LIU_HE）。
        try:
            _gan, _dz = huangli_mod.day_ganzhi(
                datetime(d.year, d.month, d.day, 12))
            noble_lh = LIU_HE.get(_dz, "")
        except Exception:
            noble_lh = ""
        result = {
            "date": date_str,
            "cv": 4,                     # 缓存口径版本（R2349g：吉神计分+合拍生肖）
            "level": level,
            "summary": (summary if (_db and level in (_db.get("levels") or {}))
                        else fortune_summary(calc_out)),
            "noble": noble_str,
            "noble_liuhe": noble_lh,
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
     # R229z续23（R11-#14）：widget 描述去术语，与首页卡口径对齐
     "desc": "生日一排 · 大白话解读", "recent": "八字排盘"},
    {"id": "book", "icon": "📜", "title": "古籍读书",
     "desc": "检索 47 部古籍 · 比对注家", "recent": "古籍检索"},
    {"id": "tarot", "icon": "✨", "title": "塔罗占卜",
     "desc": "抽牌看指引 · 解答心中疑问", "recent": "塔罗占卜"},
    {"id": "huangli", "icon": "🌙", "title": "黄历择日",
     "desc": "宜忌一览 · 轻决策", "recent": "黄历查询"},
    {"id": "qiming", "icon": "🌸", "title": "五行起名",
     "desc": "按五行补缺 · 起一个好名字", "recent": "起名"},
    {"id": "taohua", "icon": "🌺", "title": "桃花运",
     "desc": "看看近期桃花走势 🌹", "recent": "桃花"},
    # R229z续23（R11-#9）：🔮 与八字撞图标，六爻用钱币
    {"id": "liuyao", "icon": "🪙", "title": "六爻占卜",
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
                raise NotFoundError("这条没找到——可能被清掉了，刷新看看")
            # R228r：derived 表存的是研究线程记录（kind 不定为 bazi）——标题
            # 按实际 kind 出，别一律误标「八字排盘结果」。
            # R233y（R54-P1-44）：六种笔记名收敛成三个口径。
            kind_title = {"thread": "研究笔记", "summary": "研究笔记",
                          "answer": "研究笔记", "link": "研究笔记",
                          "diff": "比对笔记", "refusal": "存疑记录"}
            title = kind_title.get(getattr(d, "kind", ""), "八字排盘结果")
            return {"title": title, "subtitle": d.claim[:60],
                    "content": d.claim, "image_color": SHARE_COLORS["bazi"],
                    "created_at": d.created_at}
    if share_type in ("tarot", "book"):
        # R228r：这两个分享面无后端存档，share_id 原样回显——限长+拒控制字符
        # 守住上限，任意长串/HTML 片段不该被当分享标题直接回显。
        if not share_id or len(share_id) > 80 or not share_id.isprintable():
            raise NotFoundError("这条没找到——可能被清掉了，刷新看看")
        title, content = (("塔罗占卜结果", "塔罗牌阵解读") if share_type == "tarot"
                          else ("读书笔记", "古籍研究笔记"))
        return {"title": title, "subtitle": share_id, "content": content,
                "image_color": SHARE_COLORS[share_type], "created_at": today}
    raise NotFoundError(f"这个分享类型不认识：{share_type}")


def user_prefs() -> dict:
    with deps.knowledge() as kb:
        return {"theme": kb.get_pref("theme", "cream"),
                "recent": _recent_list(kb),
                "favorites": [dict(r) for r in kb.list_favorites()]}


def set_user_prefs(payload: dict) -> dict:
    # R228j：自由键值≠无界——键数/键长/值长不设限就是 sqlite 无限写入面。
    payload = payload or {}
    if len(payload) > 64:
        raise ValidationError("存的偏好太多了，先清一批再存")
    items = []
    for k, v in payload.items():
        if not isinstance(k, str) or not k or len(k) > 64:
            raise ValidationError("偏好名太长或为空——换短一点的")
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        v = str(v)
        if len(v) > 4000:
            raise ValidationError(f"这条偏好存不下（太长了）：{k}")
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


def clear_favorites() -> dict:
    """R2349（R65-P1-2）：清空收藏表——「忘掉我的数据」收口面。"""
    with deps.knowledge() as kb:
        kb.clear_favorites()
    return {"ok": True}


def external_news() -> dict:
    """外部资讯通道：抓预置 RSS/Atom 源。不落库、不写 history——"最新消息"
    是即时信息，与古籍语料 Source 层严格隔离。单源失败自动降级。"""
    # R229x（R7 #14）：这是全应用唯一外呼面——BOOKS_EXTERNAL_DISABLE=1
    # 给「彻底离线」姿态一个开关（BOOKS_LLM_DISABLE 只管 LLM 层）。
    if os.getenv("BOOKS_EXTERNAL_DISABLE", "").strip().lower() in (
            "1", "on", "true", "yes"):
        return {"fetched_at": None, "proxy": external_feed.PROXY,
                "sources": [], "error": "外面的资讯今天歇着",
                "disabled": True}
    try:
        return external_feed.fetch_sources(max_sources=6)
    except Exception:
        # R229n（R6-#13）：异常原文不外泄——与 external_fortune 同纪律。
        return {"fetched_at": None, "proxy": external_feed.PROXY,
                "sources": [], "error": "外面的消息暂时没拿到，稍后再看"}


def external_fortune() -> dict:
    """外部资讯的运势风格包装（每日运势卡片的外部资讯部分）。"""
    if os.getenv("BOOKS_EXTERNAL_DISABLE", "").strip().lower() in (
            "1", "on", "true", "yes"):
        return {"date": None, "ok": False, "items": [],
                "summary": "外面的资讯今天歇着", "disabled": True}
    try:
        return external_feed.fortune_wrap(external_feed.fetch_sources(max_sources=4))
    except Exception:
        # R228e：异常原文不抛给用户（ConnectionError/timeout 是英文堆栈串）。
        return {"date": None, "ok": False, "items": [],
                "summary": "外面的消息暂时没拿到，稍后再看"}


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


def _today_horoscope(iso_day: str | None = None) -> dict:
    """今天的值宫卡（用于"今日运势"侧）。失败返回 {}。"""
    # R228b：原来每请求重算当日八字（~23ms，占 bazi() 三成）——进程内
    # memo。浅拷贝返回防调用方改写缓存对象。
    # R230m：iso_day 让「今日值宫」可锚到客户端本地日（缺省服务器日）。
    return dict(_today_horoscope_cached(iso_day or date.today().isoformat()))


def _cross_ref_bazi(b, gender: str, month: int = 0, day: int = 0,
                    today_iso: str | None = None) -> dict:
    """八字结果页 → 你的太阳星座 + 今天的运势侧重。

    month/day 是**出生**月日（太阳星座的唯一依据）。缺省 0 时降级为只给
    今日值宫，不再瞎猜本命星座。
    """
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day) if month and day else {}
        today = _today_horoscope(today_iso)
        sign = prof.get("sign", "")
        today_sign = today.get("today_sign", "")
        note = today.get("today_note", "")
        # 一句话只说一件事：本命座的长处 + 今天当值宫的节奏。两者撞车时
        # （旧文案"你是双子座…今天的整体节奏：节奏放慢一点"读起来自相矛盾）
        # 明确标出"今天是 X 宫的日子"，让用户知道这是两个不同维度。
        if sign and today_sign and note:
            if sign == today_sign:
                msg = f"你是{sign}座，今天正好轮到你当班——{note}"
            else:
                # R229z续23（R11-#36）：「X宫的日子」术语 → 当班
                msg = f"你是{sign}座（{prof.get('love', '')}）；今天是{today_sign}座当班的日子：{note}"
        elif sign:
            msg = f"你是{sign}座，{prof.get('love', '')}"
        elif today_sign and note:
            msg = f"今天是{today_sign}座当班的日子：{note}"
        else:
            return {}
        # R230k（R23-P3-7）：zodiac_love/career/wealth/today_sign/today_note
        # 五个子字段零消费者（前端只读 .message，selftest 也只钉 message）——
        # 删，载荷不再白胖；message 拼装已在上方完成不受影响。
        return {
            "zodiac_sign": sign,
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
        # R230t（R33-P3-11）：2026-02-31 这种「格式对但日子不存在」
        # 此前被报成「格式不对」——文案误导。分开说。
        _msg = (f"这一天不存在，收到 {date_str}"
                if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", date_str or "")
                else f"日期需为 YYYY-MM-DD 格式，收到 {date_str}")
        raise ValidationError(_msg) from None
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
            # R233g（R44-P2-9）：与前端「X座当班」口径统一——「值宫」
            # 是生造术语，读屏/年轻用户都读不顺。
            "message": f"{_when}轮到{sign}座当班：{note}",
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


def _cross_ref_tarot(cards: list[dict],
                     today_iso: str | None = None) -> dict:
    """塔罗结果页 → 今天的星座值宫 × 牌面正逆方向是否同调。

    塔罗没有出生日期可用（不要求用户填生日），所以这里**只能**引"今天"，
    不能编造本命星座——这是与八字/桃花/起名那几处的关键区别。
    """
    from guji.xingzuo import sign_direction
    try:
        today = _today_horoscope(today_iso)
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


def _cross_ref_liuyao(moving_lines: list | tuple,
                      today_iso: str | None = None) -> dict:
    """六爻结果页 → 今天的星座值宫 × 动爻多寡（变数大小）是否同调。

    同塔罗：六爻不收生日，只能引"今天"。
    """
    from guji.xingzuo import sign_direction
    try:
        today = _today_horoscope(today_iso)
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
