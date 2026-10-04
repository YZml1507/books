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
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_logger = logging.getLogger("books")

# R2350g（R106-F4）：「今天」的参数缺省回落统一锚 UTC+8——用户全在中国
# 时区，UTC 部署机上裸 date.today()/datetime.now() 在早上 8 点前的请求
# 会被算成昨天（日签/黄历/起卦日干支整体换日）。主链路前端透传
# client_date，这里管的是缺参数直调（外链/爬虫/旧端）。
_CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def _today_cn() -> date:
    return _now_cn().date()

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
from guji import dream as dream_mod
from guji import taohua as taohua_mod
from guji.search import s2t_retry, AMBIG_S2T_CHARS
from guji import tarot as tarot_mod
from guji import voice
from guji import xingzuo as xingzuo_mod
from guji.bazi import compute as bazi_compute
from guji.bazi import day_ganzhi as _bazi_day_ganzhi
from guji.bazi_calc import LIU_HE
from guji.bazi_calc import GAN_ELEM
from guji.bazi_calc import calc as bazi_calc
from guji.bazi_calc import ten_god
# R3245：daily 个人修正层复用命局关系判函数（单源，不重复维护支表）。
from guji.bazi_calc import _rel_pair, _san_he
# R3314（R3311-高2）：犯太岁五档需要 冲/刑/害/破 全表。
from guji.bazi_calc import CHONG, XING, XIANG_HAI, XIANG_PO
from guji.bazi_calc import calc_kline, calc_life, calc_range
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

# 地支→方位（太岁位/岁破位用；通行十二支方位）
_ZHI_DIR = {"子": "正北", "丑": "东北", "寅": "东北", "卯": "正东",
            "辰": "东南", "巳": "东南", "午": "正南", "未": "西南",
            "申": "西南", "酉": "正西", "戌": "西北", "亥": "西北"}

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


# R3347（审-P3）：古籍域各端点空查询文案统一成带「定位」页指引的
# 这句——原来 /api/search 说有指引的话、/api/research 等只说半句。
_Q_EMPTY_HINT = "查询词不能为空，想找某个具体段落请用「定位」页"


def _require_q(q: str | None, *, what: str = _Q_EMPTY_HINT) -> str:
    q = (q or "").strip()
    # R230r（R30-#10）：纯零宽字符（ZWSP 等）strip() 不掉——读路径
    # （fts_phrase）会剥，空判定要先剥再判，不然「%E2%80%8B」走到 200+空表
    # 而不是如实 400。
    q = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]",
               "", q).strip()
    # R3369（审-低-2）：装饰引号统一剥掉——用户带「」『』""'' 搜的
    # 是内容不是标点，留着只会稀释命中。
    q = q.strip("「」『』\"'“”‘’〈〉《》").strip()
    if not q:
        raise ValidationError(what)
    if len(q) > 200:
        raise ValidationError("查询词过长（≤200 字符）")
    return q


def _clamp_limit(v: int, lo: int, hi: int, label: str) -> tuple[int, str | None]:
    """R3369（审-P2-2）：四处静默 clamp 统一——钳了必须如实披露，
    不再「传 200 给回 20 条以为是全量」。"""
    c = min(max(v, lo), hi)
    if v > hi:
        return c, f"{label}最多 {hi}，你要的 {v} 帮你收成 {hi} 了"
    if v < lo:
        return c, f"{label}最少 {lo}，帮你收成 {lo} 了"
    return c, None


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
            raise ValidationError("农历日期没换算成，可能是月日对不上，换个日子试试") from None
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

    ask_date = req.ask_date or _today_cn().isoformat()
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
    # R3393：流年K线全 scope 附带——只依赖出生年+命盘坐标，与范围无关。
    # day/range 用户也能拿到「人生走势」这块可晒件。
    calc_out["kline"] = calc_kline(b, by)
    if req.location:
        calc_out["location"] = req.location

    # R189b（清偿 R131a-01）：question 进检索——主题词追加在坐标词队尾，
    # 用户问什么，证据与之相关。无提问时检索行为与旧版逐字节一致。
    evidence = _dedup_evidence(retrieve_fast(b, per_query=2, per_work=1,
                                             question=req.question))
    # R232a（R40-B1）：day_master 正名——前端此前靠正则从 render 文本里
    # 抠日主（格式一改静默丢事实）。显式给字段消掉这个脆弱点。
    # R3308（审-中3）：sun_sign 也显式透出——前端自己的固定日期表判座
    # 在边界日错座（双鱼↔白羊 3/20 这类），让前端改用后端节气精判值。
    paipan_out = {"render": b.render(), "nayin": b.nayin, "warn": b.warn,
                  "day_master": b.day[0],
                  "sun_sign": xingzuo_mod.sun_sign(
                      bm, bd, year=by,
                      hour=(req.hour if req.hour_known is not False
                            else None))}
    interpretation = interpreter.interpret_bazi(paipan_out, calc_out,
                                               evidence, req.question)
    # R182b（004 M1）：warm 视图 **additive** 附加——不动 interpretation 一个
    # 字节。判据 9 要求专业模式逐字节等于基线，由 web/baseline_voice.py 把关。
    # R230a-7（R13-P2-1）：gender 透传——感情类落点按性别分星。
    # R3232：hour_known 透传——时柱白话行只在用户真填了时辰才说，
    # 默认午时不当时辰讲。
    warm = voice.warm_bazi(paipan_out, calc_out, interpretation,
                           req.question, gender=req.gender,
                           hour_known=(req.hour_known is not False))

    # R230a-7（R13-P1-3）：时辰留空 → warm reply 首部明示时柱是默认午时，
    # 响应带 hour_known 供前端卡面标注。此前静默按午时排。
    if req.hour_known is False:
        warm["reply"] = ["没填时辰：我按中午 12 点排的盘，"
                          "年/月/日三柱不受影响，大方向可参考。"] + list(
                              warm.get("reply") or [])

    # R187b（specs/006）：AI 润色层，additive 附加。失败/关闭 → None，
    # 前端整块不渲染；LLM 永远不是承重墙（D-244a）。
    # R191b（B-014，D-251b）：同步 polish 改后台任务——确定性主体立即返回，
    # 响应附 ai_task_id 供前端轮询 /api/ai/{id}；DISABLE/关闭时无此键
    # （响应与旧版逐字节一致，specs/006 判据 11）。
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_bazi(paipan_out, warm, req.question,
                              gender=req.gender,
                              hour_known=(req.hour_known is not False)),
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
                                     today_iso=req.ask_date,
                                     year=by, hour=req.hour),
        # R2350g（R106-F3）：回显换算后的公历生日——农历输入时前端拿着
        # 它才能落「我的生日」档案（banner/倒计时全走公历比对）。
        "birth_solar": {"y": by, "m": bm, "d": bd},
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
    # R3124b（specs/012-P0）：结果快照 ref——前端聊这张卡时带上，
    # 服务端按 ref 提取判词层进权威信道，小满口径=卡面口径。
    out["result_ref"] = _stash_result("bazi", out)
    return out


def taohua(req) -> dict:
    """八字桃花运：咸池/红鸾/天喜 纯坐标计算（固定生日 → 固定输出）。"""
    req.validate_ranges()
    by, bm, bd = resolve_birth(req)
    _hk = getattr(req, "hour_known", True) is not False
    try:
        b = bazi_compute(by, bm, bd, req.hour, req.gender,
                             minute=(req.minute or 0))
        # R3333（审-高4）：时辰不详 → 假午时柱不进命中/强度/落宫。
        t = taohua_mod.compute(b, hour_known=_hk)
        dayun = taohua_mod.dayun_hits(b, by)
    except Exception as exc:
        raise ComputeError(f"排盘失败：{_friendly_calc_err(exc)}") from exc
    t_dict = {
        "bazi": {"year": b.year, "month": b.month, "day": b.day,
                 "hour": b.hour, "day_master": b.day_master},
        # R3333（审-中7）：bazi.warn 透传——节气边界/晚子时警示此前
        # 在桃花响应整体丢掉。
        "warn": list(b.warn),
        "hour_known": _hk,
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
    # R2349s（R84-P1-12）：时辰未知明示——此前前端静默预填 10 点，
    # 用户以为排的是真时辰。
    if getattr(req, "hour_known", True) is False:
        warm["reply"] = ["没填时辰：我按中午 12 点排的盘，"
                         "桃花主要看年/月/日三柱，大方向不变。"] + list(
                             warm.get("reply") or [])
    ai_polish = None
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_taohua(t_dict, warm, gender=req.gender))
    out = {
        **t_dict,
        "warm": warm,
        "ai_polish": ai_polish,
        # R220b：交叉引用铺到桃花——星座桃花信号 × 八字强度叠加
        "cross_ref": _cross_ref_taohua(bm, bd, t.strength,
                                       year=by, hour=req.hour),
        **({"ai_task_id": ai_task_id} if ai_task_id else {}),
    }
    # R230z（R36-P1-1）：桃花也进排盘历史台账（原来只有 bazi 落库）
    paipan_history.save_async({
        "year": req.year, "month": req.month, "day": req.day,
        "hour": req.hour, "gender": req.gender,
    }, out, rtype="taohua")
    # R3124b：判词升格信道用结果 ref
    out["result_ref"] = _stash_result("taohua", out)
    return out


def _hehun_score(h) -> int:
    """合拍指数（R2349l/R73-P1-6）：写死权重的确定性打分。

    基准 55；日支关系是主轴（±18 档），年支减半；纳音/日主五行/桃花/
    天干五合/十神互见逐档加；钳 35–99（不给满分也不给零分——留余地
    本身就是娱乐向口径）。"""
    _rel = {"合": 18, "半合": 10, "冲": -16, "刑": -8, "害": -8, "破": -5}
    sc = 55.0
    sc += _rel.get(h.day_zhi_rel, 0)
    # R3333（审-高3）：害/刑/破此前只进 notes 零权重——次级扣分折进
    # 分数（日支档重于年支档），硬伤清单在 voice 层同口径收录。
    if getattr(h, "day_xing", False): sc += _rel["刑"]
    if getattr(h, "day_harm", False): sc += _rel["害"]
    if getattr(h, "day_break", False): sc += _rel["破"]
    if getattr(h, "year_xing", False): sc += _rel["刑"] * 0.5
    if getattr(h, "year_harm", False): sc += _rel["害"] * 0.5
    if getattr(h, "year_break", False): sc += _rel["破"] * 0.5
    # R2504（B-1）：year_zhi_rel 值域只有 '半合'——年支六冲/六合落在独立
    # bool（clash/combine）上，原读法让「年支减半」权项对两类关系恒为 0，
    # 同屏 notes 说冲、分数却装没看见。
    _yrel = "冲" if h.clash else ("合" if h.combine else h.year_zhi_rel)
    sc += _rel.get(_yrel, 0) * 0.6
    sc += {"相生": 10, "比和": 5, "相克": -9}.get(h.nayin_rel, 0)
    sc += 14 if h.day_wx_sheng else (8 if h.day_wx_same else -11)
    if h.peach_same:
        sc += 7
    if h.gan_he:
        sc += 9
    if getattr(h, "gan_chong", False):
        sc -= 7
    sc += 4 if h.god_a_sees_b else 0
    sc += 4 if h.god_b_sees_a else 0
    # R3333（审-中8）：99 天花板堆积——原先稍有助力就顶满，
    # 满大街 99 分显得像假的。日常顶 92；真满分档留给
    # 无硬伤且正信号叠厚的组合（≥6 个正信号且零负信号）。
    _pos = sum([
        h.day_zhi_rel in ("合", "半合"), bool(h.combine),
        h.nayin_rel == "相生", bool(h.day_wx_sheng),
        bool(h.day_wx_same), bool(h.peach_same), bool(h.gan_he),
        bool(h.god_a_sees_b), bool(h.god_b_sees_a)])
    _neg = any([
        h.day_zhi_rel == "冲", h.clash, h.nayin_rel == "相克",
        (not h.day_wx_sheng and not h.day_wx_same),
        getattr(h, "gan_chong", False),
        getattr(h, "day_xing", False), getattr(h, "day_harm", False),
        getattr(h, "day_break", False), getattr(h, "year_xing", False),
        getattr(h, "year_harm", False), getattr(h, "year_break", False)])
    _cap = 99 if (_pos >= 6 and not _neg) else 92
    return int(max(35, min(_cap, round(sc))))


def _hehun_plates(req):
    """合婚共享前置（R3425 抽取）：双侧生辰→农历换算→成年/同人闸
    →双盘+hehun 坐标+大运应期。hehun() 与 hehun_daily() 共用，
    闸口径改一处两边同步。
    抛 ValidationError（农历换算失败/未成年/同一人）/ComputeError。
    返回 (ba, bb, h, dayun, a_ymd, b_ymd)——后两项是换算后的公历
    坐标（农历输入下与 req.a_*/b_* 原值不同，判星座须用这组）。"""
    req.validate_ranges()
    # R2349s（R84-P0-1）：未成年边界——1900–2100 只验「是不是日期」，
    # 实测 8 岁盘正常出「并肩作战型情侣」配对文案，敏感失守。
    # R2350g（R106-F5）：年龄精确到日——纯年份差会让 17y11m 放行。
    _now_d = _today_cn()

    def _age(y, m, d):
        return _now_d.year - y - ((_now_d.month, _now_d.day) < (m, d))
    # R3206：双侧农历——换算失败是用户输错日期不是排盘故障，
    # 归 ValidationError（resolve_birth 认 req.calendar_type 命名，
    # hehun 双侧各一组 a_/b_ 前缀，这里手动换算）。
    _ay, _am, _ad = req.a_year, req.a_month, req.a_day
    _by, _bm, _bd = req.b_year, req.b_month, req.b_day
    try:
        if req.a_calendar == "lunar":
            _da = lunar.lunar_to_solar(req.a_lunar_year, req.a_lunar_month,
                                     req.a_lunar_day, req.a_lunar_leap)
            _ay, _am, _ad = _da.year, _da.month, _da.day
        if req.b_calendar == "lunar":
            _db = lunar.lunar_to_solar(req.b_lunar_year, req.b_lunar_month,
                                     req.b_lunar_day, req.b_lunar_leap)
            _by, _bm, _bd = _db.year, _db.month, _db.day
    except ValueError:
        raise ValidationError(
            "农历日期没换算成，可能是月日对不上，换个日子试试") from None
    # R3340（审-P3）：<18 闸挪到农历换算之后——此前用请求原值，
    # 农历生日边界月差会误拦/误放。
    if _age(_ay, _am, _ad) < 18 or _age(_by, _bm, _bd) < 18:
        raise ValidationError(
            "合婚是给成年人测的：有一方还没满 18 岁，把生日改对或长大点再来呀～")
    # R2349s（R84-P1-5）：同一盘填两遍出「并肩作战型情侣」——先提示。
    # R3340（审-P3）：时辰未知侧不带进比较——两侧都留空同填默认午时，
    # 不同人同一天生会被误判「同一个人」。任一侧未知即不比时辰。
    _ah_cmp = req.a_hour if req.a_hour_known is not False else None
    _bh_cmp = req.b_hour if req.b_hour_known is not False else None
    if ((_ay, _am, _ad, _ah_cmp, req.a_gender)
            == (_by, _bm, _bd, _bh_cmp, req.b_gender)):
        raise ValidationError("两边填的是同一个人呀：换上 TA 的生辰再测～")
    try:
        ba = bazi_compute(_ay, _am, _ad, req.a_hour, req.a_gender)
        bb = bazi_compute(_by, _bm, _bd, req.b_hour, req.b_gender)
        h = hehun_mod.compute(ba, bb)
        dayun = hehun_mod.dayun_relation(ba, _ay, bb, _by)
    except Exception as exc:
        raise ComputeError(f"排盘失败：{_friendly_calc_err(exc)}") from exc
    return ba, bb, h, dayun, (_ay, _am, _ad), (_by, _bm, _bd)


def hehun_daily(req) -> dict:
    """R3425 今日合拍指数：已存 CP 的「今天你们怎么样」日更留存钩。

    纯坐标确定性输出（同日重测同分）：今日日柱 vs 双方日支的合/冲/
    半合/害/刑信号 + 底子分（_hehun_score）混成 45–98 的当日分。
    判词按分档换句，附加日支信号标签（合→适合表态、冲→别翻旧账）。"""
    ba, bb, h, _dayun, _aymd, _bymd = _hehun_plates(req)
    base = _hehun_score(h)
    # R3431-P2（审）：锚浏览器本地日——缺省回退服务器 CST（旧端/
    # 直调兼容），海外用户零点前后不再错位一天。
    _cd = getattr(req, "client_date", None)
    _today = date.fromisoformat(_cd) if _cd else _today_cn()
    _tp, _ = _bazi_day_ganzhi(
        datetime(_today.year, _today.month, _today.day))
    _tz = _tp[1]

    def _sig(dz):
        if hehun_mod.SIX_COMBINE.get(_tz) == dz:
            return 7, "合"
        if hehun_mod.SIX_CLASH.get(_tz) == dz:
            return -9, "冲"
        if hehun_mod.half_combine(_tz, dz):
            return 3, "半合"
        if hehun_mod.is_harm(_tz, dz):
            return -4, "害"
        if hehun_mod.is_xing(_tz, dz):
            return -4, "刑"
        if hehun_mod.is_break(_tz, dz):
            return -3, "破"
        return 0, ""

    _sa, _ta = _sig(ba.day[1])
    _sb, _tb = _sig(bb.day[1])
    # 抖动盐：日期+双方日柱——同一对每天不同、同一天重测不变，
    # ±4 不破确定性也不让分数天天撞整数带。
    _jit = int(hashlib.md5(
        f"{_today.isoformat()}|{ba.day}{bb.day}".encode()
    ).hexdigest()[:4], 16) % 9 - 4
    score = int(max(45, min(98, round(
        0.55 * base + 24 + (_sa + _sb) * 1.5 + _jit))))
    _tag = ""
    # R3433-P1-1（审）：「日支逢冲/逢合」内码术语裸奔上屏——
    # 术语翻成感受，与全站随行翻译口径一致。
    if _ta == "冲" or _tb == "冲":
        _tag = "今天你们容易顶起来，别翻旧账"
    elif _ta == "合" or _tb == "合":
        _tag = "今天你们格外对味，适合把话说开"
    elif _ta == "半合" or _tb == "半合":
        _tag = "今天有点小合意，顺手撒个娇"
    if score >= 85:
        line = "今天你们频道特别对——想腻就腻着，想把话说开也顺。"
    elif score >= 70:
        line = "今天合拍在线，日常小事都顺，适合一起做点啥。"
    elif score >= 55:
        line = "今天平平也挺好，各忙各的、晚上唠两句就够。"
    else:
        # R3433-P2-5（审）：「有点顶」歧义（顶着/顶撞读不出）。
        line = "今天容易小顶牛——少讲道理多给台阶，晚点再说正事。"
    return {"date": _today.isoformat(), "ganzhi": _tp,
            "score": score, "line": line, "tag": _tag, "base": base}


def hehun(req) -> dict:
    """八字合婚：六冲/六合/日主五行/桃花支 + 大运冲合应期，全纯坐标。"""
    ba, bb, h, dayun, (_ay, _am, _ad), (_by, _bm, _bd) = _hehun_plates(req)
    h_dict = {
        # R2350b（R98-P2-13）：补 render——pro 模式「A 四柱」pill 读
        # a_bazi.render，此前键缺席恒 undefined（死 pill）；甲乙卡也
        # 用它做四柱悬停。
        "a_bazi": {"year": ba.year, "day": ba.day, "day_master": ba.day_master,
                   "render": ba.render()},
        "b_bazi": {"year": bb.year, "day": bb.day, "day_master": bb.day_master,
                   "render": bb.render()},
        # R3340（审-P2）：A/B 两盘的节气边界/夏令时/0点跨日警示
        # 此前在合婚响应整体丢掉——静默拿可能错的盘出判词。
        "warn": [f"A 盘：{w}" for w in (ba.warn or [])] +
                [f"B 盘：{w}" for w in (bb.warn or [])],
        # R233u（R53-P1-1）：one_liner 盐键接线——此前 day_zhi_* 恒 None，
        # 同桶所有 CP 抽到同一句判词。
        "day_zhi_a": h.day_zhi_a, "day_zhi_b": h.day_zhi_b,
        "day_zhi_rel": h.day_zhi_rel,
        # R3333（审-高3）：害/刑/破旗进 h_dict——voice 硬伤与分数同口径。
        "year_harm": h.year_harm, "year_xing": h.year_xing,
        "year_break": h.year_break,
        "day_harm": h.day_harm, "day_xing": h.day_xing,
        "day_break": h.day_break,
        "nayin_a": h.nayin_a, "nayin_b": h.nayin_b, "nayin_rel": h.nayin_rel,
        "year_zhi_rel": h.year_zhi_rel,
        "year_zhi_a": h.year_zhi_a, "year_zhi_b": h.year_zhi_b,
        "clash": h.clash, "combine": h.combine,
        "day_wx_a": h.day_wx_a, "day_wx_b": h.day_wx_b,
        "day_wx_sheng": h.day_wx_sheng,
        "day_wx_same": h.day_wx_same,   # R230a-7（R13-P0-2）：同五行比和
        "peach_a": h.peach_a, "peach_b": h.peach_b, "peach_same": h.peach_same,
        # R204b（D-257b）：天干五合 + 日主十神互见（yinyuan skill 融入）
        "gan_he": h.gan_he, "gan_chong": h.gan_chong,
        "god_a_sees_b": h.god_a_sees_b, "god_b_sees_a": h.god_b_sees_a,
        "dayun_hits": dayun,
        "notes": h.notes,
        "render": h.render(),
        # R2349l（R73-P1-6）：合拍指数——定性坐标转确定性分数。
        # 基准 55，日支/年支冲合按权重加减，相生/比和/相克逐级，
        # 桃花同支、日干五合、十神互见小幅加分；钳 35–99。
        "match_score": _hehun_score(h),
        # R3152：问句进卡——warm 层对着用户问的那句给定向行。
        "question": req.question,
    }
    # R187b：人话视图 + AI 润色，均 additive（specs/005 US4 / specs/006）
    # R191b（B-014）：AI 段落改后台任务（D-251b），同 bazi。
    # R3313（审-P1-5）：邀请态下提交/读盘的是乙侧（受邀者）——
    # 「我/TA」的指称整体换向，服务端判词不再贴反身份。
    _rb = bool(getattr(req, "reader_is_b", False))
    _alab, _blab = ("TA", "我") if _rb else ("我", "TA")
    warm = voice.warm_hehun(h_dict, viewer=("b" if _rb else "a"))
    # R2349s（R84-P1-12）：时辰不详侧明示——此前前端静默预填 10 点，
    # 「TA 的时辰」常被默认值冒充。
    _unk = [(_alab if req.a_hour_known is False else None),
            (_blab if req.b_hour_known is False else None)]
    _unk = [s for s in _unk if s]
    # R3206：农历换算明示——生日按农历换算成公历排的盘。
    _lun = [(_alab if req.a_calendar == "lunar" else None),
            (_blab if req.b_calendar == "lunar" else None)]
    _lun = [s for s in _lun if s]
    if _lun:
        warm["reply"] = [f"{'和'.join(_lun)}的生日按农历换算的。"
                         "换成公历排的盘，结果不受影响。"] + list(
                             warm.get("reply") or [])
    if _unk:
        warm["reply"] = [f"{'和'.join(_unk)}的时辰没填。"
                         "那边按中午 12 点排的，主线不受影响。"
                         ] + list(warm.get("reply") or [])
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
        # R3340（审-P1）：判座用换算后的公历坐标——农历输入下
        # req.a_*/b_* 是农历值，直接判座错座且配对判词整体翻转。
        "cross_ref": _cross_ref_hehun(ba, bb,
                                     (_ay, _am, _ad,
                                      getattr(req, "a_hour", None)),
                                     (_by, _bm, _bd,
                                      getattr(req, "b_hour", None))),
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
    # R3124b：判词升格信道用结果 ref
    out["result_ref"] = _stash_result("hehun", out)
    return out


def qiming(req) -> dict:
    """五行起名：八字 → 五行缺行 → 古籍典故取名 + 候选字（R217a 重构）。"""
    req.validate_ranges()
    # R229x（R7 审计 #3）：打包漏带 classical_names.json 时典故库静默
    # 为空、起名返回 0 候选——显式报错让用户知道缺资源，而非空结果。
    # 注意放 try 外：except Exception 会把 ComputeError 包成「起名计算失败」。
    from guji import classical_names
    if not classical_names._CLASSICAL_DB:
        raise ComputeError("起名的典故库没装进来，"
                           "重新下载完整版本试试")
    # R3206：农历生日——与 bazi 同走 resolve_birth 换算。
    _qy, _qm, _qd = resolve_birth(req)
    try:
        out = classical_names.generate_classical_names(
            surname=req.surname, year=_qy, month=_qm,
            day=_qd, hour=req.hour, gender=req.gender,
            top_n=min(max(req.top_n, 1), 100),
            seed=req.seed, style=getattr(req, "style", "all"),
            avoid_chars=getattr(req, "avoid_chars", "") or "")
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
    # R2349s（R84-P1-12）：时辰留空明示——不再静默按预填 12 点排。
    if getattr(req, "hour_known", True) is False:
        out["warm"]["reply"] = ["没填时辰：按中午 12 点排的盘，"
                                "五行分布按年/月/日三柱看，名字照挑。"] + list(
                                    out["warm"].get("reply") or [])
    if req.calendar_type == "lunar":   # R3206：农历换算明示
        out["warm"]["reply"] = ["填的是农历生日：已换算成公历排的盘。"] + list(
            out["warm"].get("reply") or [])
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_qiming(out, req.gender, warm=out["warm"]))
    out["ai_polish"] = ai_polish
    # R220b：交叉引用铺到起名——太阳星座气质给挑名字一个参考角度
    # R3340（审-P1）：判座用换算后公历坐标+年+时辰走节气精判——
    # 此前拿 req.month/day 原值（农历输入下是农历月日）且函数只
    # 吃 (m,d) 走民用粗表，与同响应 bazi 精判口径一页两分叉。
    out["cross_ref"] = _cross_ref_qiming(_qm, _qd, year=_qy, hour=req.hour)
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    # R230z（R36-P1-1）：起名进台账（原来只有 bazi 落库）
    paipan_history.save_async({
        "surname": req.surname, "year": req.year, "month": req.month,
        "day": req.day, "hour": req.hour, "gender": req.gender,
        "seed": req.seed, "style": req.style,
    }, out, rtype="qiming", name=f"起名 · {req.surname}×")
    # R3124b：判词升格信道用结果 ref
    out["result_ref"] = _stash_result("qiming", out)
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
                "日期没看懂，照着 2026-01-01 这样填试试") from None
        # R2506（审-F3）：与 _parse_iso_date 同口径——Py3.11+
        # fromisoformat 放宽的非规范形（20260101 等）拒掉。
        if _parsed.isoformat() != date_str:
            raise ValidationError(
                "日期没看懂，照着 2026-01-01 这样填试试")
        # R228b：星历表有覆盖区间——极值年份（如 9999）会一路炸进
        # bazi_compute 报 ValueError → 未映射 500。边界即拒为 400。
        if not (YEAR_LO <= _parsed.year <= YEAR_HI):
            raise ValidationError(
                f"年份要在 {YEAR_LO}–{YEAR_HI} 之间")
    d = date.fromisoformat(date_str) if date_str else _today_cn()
    b = bazi_compute(d.year, d.month, d.day, 12, "男")
    out = xingzuo_mod.daily_horoscope(b.day)
    out["date"] = d.isoformat()
    # R3150b：值宫卡接入 result_ref 快照——照「今天 XX 座当班」聊时
    # 小满手里有同一张卡的坐标+文案，不是泛泛的星运腔。
    out["result_ref"] = _stash_result("xingzuo", out)
    # R3193：星座日运接 AI 解读块——此前是唯一无 polish 的卡面。
    # GET 端点爬虫/预览器可达——独立小桶不占全局「ai」额度（照
    # xzmatch 同型先例 R3157）。
    _xz_tid = llm_polish.spawn_ai_task(
        llm_polish.facts_xingzuo(out), "今天星座日运",
        rate_key="ai_social", rate_limit=15)
    if _xz_tid:
        out["ai_task_id"] = _xz_tid
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
    q = _require_q(q, what="查询词不能为空，想找某个具体段落请用「定位」页")
    # R230s（R30-#9）：limit<=0 此前静默钳成 1——如实 400。
    if limit < 1:
        raise ValidationError("条数至少填 1，最多能取 50 条")
    limit = min(limit, 50)
    with deps.corpus() as c:
        # R230a-33（R14-P3-6）：scheme 与 addr 同纪律——未知值 400 而非静默零命中。
        if scheme is not None and scheme not in deps.SCHEME_LABELS:
            raise ValidationError(
                f"这种编址方式不支持，可选：{' / '.join(deps.SCHEME_NAMES.values())}")
        # 'none' 哨兵原样下传，由 Corpus._search_where 翻成 IS NULL。
        # R230r（R30-#11）：过滤参数拼错/不存在时如实 400——work=NOSUCH
        # 此前静默 200 零命中，看起来像「语料里没有这个词」。
        if work and not c.db.execute(
                "SELECT 1 FROM work WHERE id=?", (work,)).fetchone():
            raise ValidationError(f"这本书库里暂时没有（{work}），先去书目页翻翻")
        if layer and not c.db.execute(
                "SELECT 1 FROM unit WHERE layer=? LIMIT 1",
                (layer,)).fetchone():
            raise ValidationError(f"这个分类库里没有（{layer}），换一个试试")
        # R2502：genre 此前是唯一不进存在性校验的过滤——拼错类别静默
        # 零命中，像「语料里没有这个词」。与 work/layer 同口径如实 400。
        if genre and not c.db.execute(
                "SELECT 1 FROM work WHERE genre=? LIMIT 1",
                (genre,)).fetchone():
            raise ValidationError(f"这个类别库里没有（{genre}），先去书目页翻翻")
        kw = dict(layer=layer, work_id=work, genre=genre, scheme=scheme)
        hits = c.search(q, limit=limit, **kw)
        hint = None
        q2 = s2t_retry(q)
        extra: list = []
        shown_extra = 0
        if q2 != q:
            # R2400（R125-P1-2）：此前只在「零命中」时才按繁体重试——
            # 简体有部分命中时繁体形静默缺席（「无为」10 条 vs
            # 「無為」165 条），属误导性输出。现在两形并查、按
            # (work_id,text) 去重合并。
            hits2 = c.search(q2, limit=limit, **kw)
            if not hits:
                if hits2:
                    hits = hits2
                    # R2523（审-SV-1）：全量出自 q2——展示数计入
                    # shown_extra 而非 shown_q，否则 total = len+count2
                    # 把同批命中数两遍（实测 100 条命中报 110）。
                    shown_extra = len(hits2)
                    hint = f"已按繁体重试「{q2}」"
            elif hits2:
                seen = {(h.work_id, h.text) for h in hits}
                extra = [h for h in hits2
                         if (h.work_id, h.text) not in seen]
                if extra:
                    # R126-P1-7：简体装满上限时 extra 全被 [:limit] 切掉、
                    # hint 却谎称「已附」——简体侧让出名额给繁体，放不下的
                    # 如实写进 hint。
                    shown_extra = min(len(extra), max(3, limit // 3))
                    hits = (hits[:limit - shown_extra]
                            + extra[:shown_extra])
                    hint = f"已附繁体「{q2}」命中 {shown_extra} 条"
                    if len(extra) > shown_extra:
                        hint += (f"（另有 {len(extra) - shown_extra} 条"
                                 f"因上限没展示，想全看请直接搜「{q2}」）")
        # R3305（审-P1-1/P2-4）：两个披露缺口——
        # ① q 含一对多歧义字（刻意不收映射表）时简体侧可能漏命中，
        #    有命中也如实提醒「换繁体再查一次会更全」；
        # ② 零命中此前裸回，没有「语料范围+下一步出路」的引导
        #    （concept 已这么做，search 口径对齐）。
        _amb = [ch for ch in q if ch in AMBIG_S2T_CHARS]
        if hint is None and _amb:
            hint = (f"「{_amb[0]}」这类字简繁写法不止一种，本库以繁体为主"
                    f"——想查全可换繁体写法再搜一次")
        # total = 展示数 + 各形未展示的余量（两形的并集无法精确计数——
        # 窗口外的交集不可知，按各形总数直加，配合 hint 的分形口径）。
        shown_q = len(hits) - shown_extra
        total = len(hits) \
            + max(0, c.search_count(q, **kw) - shown_q) \
            + (max(0, c.search_count(q2, **kw) - shown_extra)
               if q2 != q else 0)
        if total == 0 and hint is None:
            hint = ("这库主要是周易、术数一类古籍——换个写法（或繁体）、"
                    "缩短词组再试试，也可以去「定位」按章回翻")
        return {"query": q, "count": len(hits), "total": total,
                "truncated": total > len(hits), "hint": hint,
                "hits": [hit_dict(h) for h in hits]}


def addr(scheme: str = "zhouyi", *, gua: int | None = None,
         yao: str | None = None, layer: str | None = None,
         addr_name: str | None = None, addr1: int | None = None,
         addr2: str | None = None, limit: int = 20,
         work: str | None = None) -> dict:
    """地址定位。scheme 显式声明，杜绝 Psalms-99 == 卦99 类跨体系碰撞（D-005）。"""
    if scheme not in deps.SCHEME_LABELS:
        raise ValidationError(
            f"这种编址方式不支持，可选：{' / '.join(deps.SCHEME_NAMES.values())}")
    if limit < 1:
        raise ValidationError("条数至少填 1，最多能取 100 条")
    limit = min(limit, 100)
    # R230s（R30-#14）：与所选 scheme 不相干的参数如实披露，不静默吞。
    if scheme == "zhouyi":
        _ignored = [n for n, v in (("addr_name", addr_name),
                                   ("addr1", addr1), ("addr2", addr2),
                                   ("work", work))
                    if v is not None]
    else:
        _ignored = [n for n, v in (("gua", gua), ("yao", yao))
                    if v is not None]
    hint = (f"你传的 {'/'.join(_ignored)} 这项在{deps.SCHEME_NAMES.get(scheme, scheme)}用不上，帮你忽略了"
            if _ignored else None)
    with deps.corpus() as c:
        # R2517（审-P2-3）：与 search 同纪律——过滤参数拼错/不存在如实
        # 400，此前静默零命中像「库里没有这条地址」。只查输入侧参数的
        # 全局存在性（typo 检测）；合法组合为空仍回 200 空集。
        # R3241：addr2/addr_name 单列无覆盖索引，原 LIMIT 1 是整索引扫
        # 5.6ms——has_value 用按库指纹缓存的 distinct 集等价判定。
        # R3305（审-P2-1）：typo 门此前用全局 DISTINCT——bcv 的节号
        # 会让 zhouyi 的爻校验误放行（跨 scheme 污染）。按 scheme 分桶。
        # work 参数存在性（typo 门同纪律——拼错书名静默零命中像「没这本书」）。
        if work is not None and not c.db.execute(
                "SELECT 1 FROM work WHERE id=? LIMIT 1",
                (work,)).fetchone():
            raise ValidationError(f"这本书库里没有（{work}），先去书目页翻翻")
        for _col, _v, _lbl in (
                ("layer", layer, "这个分类"),
                ("addr_name", addr_name, "这个地址名"),
                ("addr2", addr2 if scheme != "zhouyi" else yao,
                 "这个爻/小节")):
            if _v is not None and not c.has_value(
                    _col, _v,
                    scheme=None if _col == "layer" else
                    (scheme if scheme != "none" else "none")):
                # R3369（审-P1-2）：bcv 卷名是英文原名——填「创世记」
                # 报「库里没有」不指路等于把答案藏一半，点名用英文。
                if _col == "addr_name" and scheme == "bcv":
                    raise ValidationError(
                        f"这卷库里没有（{_v}）——卷名要用英文原名，"
                        "比如 Genesis、Exodus")
                raise ValidationError(
                    f"{_lbl}库里没有（{_v}），换一个试试")
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
                raise ValidationError("易林候序填 1 到 64（六十四候）")
            # R3305（审-P1-2）：bcv 的 addr1 是书内章号，缺 addr_name
            # 会把几十卷同号章揉成一页；booksec 各书卷号互撞（addr_name
            # 恒 NULL，区分靠 work_id）——如实拒绝，与 bookstudy.chapter
            # 同口径。
            if scheme == "bcv" and addr1 is not None \
                    and addr_name is None:
                raise ValidationError(
                    "章号是按每卷算的，得再给卷名（比如 Genesis）——"
                    "不然几十卷的同号章会揉到一页")
            if scheme == "booksec" and addr1 is not None \
                    and work is None:
                raise ValidationError(
                    "卷号是按每本书算的，得再给书名（work 参数，"
                    "比如 herodotus）——不然几本书的同号卷会揉到一页")
            hits = c.at_scheme(None if scheme == "none" else scheme,
                               addr_name=addr_name, addr1=addr1,
                               addr2=addr2, layer=layer, limit=limit,
                               work_id=work)
            _sn = None if scheme == "none" else scheme
            _w = "scheme IS NULL" if _sn is None else "scheme = ?"
            _p = [] if _sn is None else [_sn]
            for col, val in (("addr_name", addr_name), ("addr1", addr1),
                             ("addr2", addr2), ("layer", layer),
                             ("work_id", work)):
                if val is not None:
                    _w += f" AND {col} = ?"; _p.append(val)
            total = c.db.execute(f"SELECT count(*) n FROM unit u WHERE {_w}",
                                 _p).fetchone()["n"]
            # R3369（审-低-5）：bcv/booksec 的章/卷号上界随卷而异——
            # 0 命中时把「这卷只到 N 章」说出来，不再像没那条地址。
            if not hits and addr1 is not None and scheme in (
                    "bcv", "booksec", "play", "euclid"):
                _bw = "scheme=? AND addr1 IS NOT NULL"
                _bp: list = [scheme]
                if addr_name is not None:
                    _bw += " AND addr_name=?"; _bp.append(addr_name)
                if work is not None:
                    _bw += " AND work_id=?"; _bp.append(work)
                _mx = c.db.execute(
                    f"SELECT max(addr1) m FROM unit WHERE {_bw}",
                    _bp).fetchone()["m"]
                if _mx is not None and addr1 > _mx:
                    _note = (f"这一卷只到 {_mx}，你要的第 {addr1} 章"
                             "超界了")
                    hint = (hint + "；" + _note) if hint else _note
        return {"scheme": scheme, "count": len(hits), "total": total,
                "truncated": total > len(hits), "hint": hint,
                "hits": [hit_dict(h) for h in hits]}


def compare(gua: int, yao: str = "九三", layer: str = "經",
            allow_damaged: bool = False) -> dict:
    """跨版本同址比对 + 差异摘要（复用 compare.compare_address）。"""
    if not (1 <= gua <= 64):
        raise ValidationError("卦号填 1 到 64")
    with deps.corpus() as c:
        # R3305（审-P3）：compare 的 yao 此前无 typo 门——「二九」「abc」
        # 200 no_witness（合法但无比对材料）而不是 400 报错，与 /api/addr
        # 口径不一。同闸复用。
        if yao and not c.has_value("addr2", yao, scheme="zhouyi"):
            raise ValidationError(
                "爻名库里没有（{}）——写法是 初九/九二/上九 这类".format(yao))
        # R3369（审-P2-1）：compare 漏 layer typo 门——层名写错回
        # 200 no_witness，把「层名拼错」谎报成「这个地址没材料」。
        if layer and not c.has_value("layer", layer):
            raise ValidationError(
                f"这个分类库里没有（{layer}），换一个试试")
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
        raise ValidationError("一次最多读 6 条地址（最少 1 条），换个数再试")
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
        # R2400（R125-P1-2）：与 /api/search 同纪律——简体概念繁体形
        # 并查（「无为」普查 4 部 →「無為」21 部，此前后者静默缺席）。
        _pw, _note = _clamp_limit(per_work, 1, 10, "每书证据")
        r = concept_census(c, q, per_work=_pw, concept2=s2t_retry(q))
        if _note:
            r["limit_note"] = _note
        return r


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
        _pw, _note = _clamp_limit(per_work, 1, 10, "每书证据")
        r = research_compare_works(
            c, work_a, work_b, q,
            per_work=_pw,
            concept2=s2t_retry(q))
        if _note:
            r["limit_note"] = _note
        return r


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


_STALE_TTL = 60.0          # R2517（审-P3-11）：stats 每请求全树 os.walk
_stale_cache: dict = {"at": 0.0, "v": None}


def _corpus_index_stale() -> bool | None:
    """R230t（R31-P1-1）：corpus.db 比 data/raw 旧 = 索引过期。

    build_meta 记的是构建时刻；raw 文本之后被改动（修订/增量入库）不会
    回写 meta，唯一能信的对比是文件 mtime。raw 目录缺失/读取失败时
    返回 None（「不知道」，不谎报）。

    R2517（审-P3-11）：全目录树 os.walk 每请求一次太贵——60s 记忆窗，
    过期重扫；staleness 本身是天级概念，分钟级新鲜度足够。
    """
    _now = time.monotonic()
    if _now - _stale_cache["at"] < _STALE_TTL:
        return _stale_cache["v"]
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
        _stale_cache["v"] = (newest > db_mtime) if newest else None
    except OSError:
        _stale_cache["v"] = None
    _stale_cache["at"] = _now
    return _stale_cache["v"]


# R3239：stats 的语料派生三件套（c.stats 三次全扫 + layers GROUP BY +
# build_meta ≈ 18ms/请求）只在语料重建时变——按 (mtime_ns,size) 键控，
# 与 _stale_cache/_COVERAGE_CACHE 同模式；index_stale 另有 60s 窗。
_STATS_CACHE: dict = {"key": None, "v": None}


def stats() -> dict:
    try:
        _st = os.stat(deps.CORPUS_DB)
        _key = (_st.st_mtime_ns, _st.st_size)
    except OSError:
        _key = None
    if _key is not None and _STATS_CACHE["key"] == _key:
        base = _STATS_CACHE["v"]
    else:
        with deps.corpus() as c:
            base = {
                "stats": c.stats(),
                "layers": [dict(r) for r in c.db.execute(
                    "SELECT layer, count(*) n FROM unit GROUP BY layer "
                    "ORDER BY n DESC")],
                "meta": [dict(r) for r in c.db.execute(
                    "SELECT key, value FROM build_meta")],
            }
        if _key is not None:
            _STATS_CACHE["key"] = _key
            _STATS_CACHE["v"] = base
    return {**base,
            "schemes": deps.SCHEME_LABELS,
            "index_stale": _corpus_index_stale()}


def threads(status: str = "open", limit: int = 50) -> dict:
    """研究线程列表（G9：可恢复的研究线索）。

    R230r（R30-#8）：resume() LIMIT 50 曾静默截断——超 50 条 open 线程后
    更老的永久消失。披露 total/limit/truncated，并支持 PATCH 改状态
    （open/parked/closed，收起的线程不再占列表位）。
    R2500（R143-P1-3）：limit 参数（≤500）——备份导出/wipe 需要够到
    全部线程而非前 50。"""
    # R2349z（R96-P1-1）：status 过滤——收起的/聊完的不再从列表永久消失。
    if status not in ("open", "parked", "closed", "all"):
        raise ValidationError("线程列表只能按「进行中/先收起/已结束」筛")
    # R2502：limit=0 此前被 `or 50` 静默改 50——与 search/addr 的
    # limit<1→400 口径不一致。None 才走默认，显式 0/负如实拒。
    limit = 50 if limit is None else int(limit)
    if not 1 <= limit <= 500:
        raise ValidationError("条数要在 1-500 之间")
    with deps.knowledge() as kb:
        # R2502：resume() 内置 LIMIT 50 让 [:limit] 恒 False——limit>50
        # 时行数被截却报 truncated:false，备份导出静默丢线程。下推给 SQL。
        rows = kb.resume(status, limit)
        if status == "all":
            total = kb.db.execute(
                "SELECT count(*) n FROM thread").fetchone()["n"]
        else:
            total = kb.db.execute(
                "SELECT count(*) n FROM thread WHERE status=?",
                (status,)).fetchone()["n"]
        return {"threads": [dict(r) for r in rows], "stats": kb.stats(),
                "total": total, "limit": limit, "truncated": total > limit}


def threads_clear_all() -> dict:
    """R2500（R143-P1-3/P2-4）：「忘掉我的数据」全量清线程+手记——
    前端逐条 DELETE 只够到前 50 条，且 claims 原文留库；这里一次清
    全表（threads/turns/derived/evidence/fts）。"""
    with deps.knowledge() as kb:
        return {"deleted": kb.delete_all_threads()}


def thread_set_status(tid: int, status: str) -> dict:
    """改线程状态（R230r / R30-#8：schema 早有 open/parked/closed CHECK，
    但没有任何写入路径能到 closed/parked）。"""
    if status not in ("open", "parked", "closed"):
        raise ValidationError("这条线程只能改成「进行中」「先收起」或「已结束」")
    with deps.knowledge() as kb:
        row = kb.db.execute(
            "SELECT id FROM thread WHERE id=?", (tid,)).fetchone()
        if row is None:
            raise NotFoundError("这条线程没找到，可能还没聊过")
        kb.db.execute("UPDATE thread SET status=? WHERE id=?",
                      (status, tid))
        kb.db.commit()
        return {"id": tid, "status": status}


def thread_detail(tid: int) -> dict:
    """单条线程：transcript + derived claims + 证据回查。"""
    with deps.knowledge() as kb:
        turns = [dict(r) for r in kb.thread_transcript(tid)]
        if not turns:
            # R2500（R143-P2-6/G1）：0 轮线程是存在的（import_threads
            # 可产出空 turns 线程）——之前 404 让导出端整线丢弃、备份
            # 循环每轮悄悄掉一批。线程存在但 0 轮 → 空 transcript +
            # 照常带 claims；只有线程真不存在才 404。
            row = kb.db.execute(
                "SELECT 1 FROM thread WHERE id=?", (tid,)).fetchone()
            if not row:
                raise NotFoundError("这条线程没找到，可能还没聊过")
        claims = []
        _claim_ids: list[int] = []
        # R2523（审-SV-2）：原逐 claim kb.get()——每条 2 次往返
        # （derived+evidence 各一查），N 条 = 1+2N。改为两条批量查、
        # Python 侧按 derived_id 归组（与 verify() 同款 IN 模式）。
        _drows = kb.db.execute(
            "SELECT * FROM derived WHERE thread_id=? ORDER BY id",
            (tid,)).fetchall()
        _ev_by_did: dict[int, list] = {}
        if _drows:
            _evph = ",".join("?" * len(_drows))
            for _x in kb.db.execute(
                    f"SELECT * FROM evidence WHERE derived_id IN ({_evph})"
                    " ORDER BY id",
                    tuple(r["id"] for r in _drows)):
                _ev_by_did.setdefault(_x["derived_id"], []).append(_x)
        for r in _drows:
            _claim_ids.append(r["id"])
            claims.append({
                "id": r["id"], "kind": r["kind"], "claim": r["claim"],
                "method": r["method"], "confidence": r["confidence"],
                "created_at": r["created_at"],
                "evidence": [{
                    "role": e["role"], "work_id": e["work_id"],
                    "file": e["file"], "page_anchor": e["page_anchor"],
                    "scheme": e["scheme"], "addr1": e["addr1"],
                    "addr2": e["addr2"], "quote": e["quote"],
                } for e in _ev_by_did.get(r["id"], [])],
            })
        return {"turns": turns, "claims": claims,
                # R8 P2-4：verify 从全表 evidence 收敛到本线程 claims
                "verify": kb.verify(deps.RAW_DIR, derived_ids=_claim_ids)}


def claims(orphaned: bool | None = None, limit: int = 50) -> dict:
    """R3347（审-P2）：研究手记（derived claims）列表端点——删线程时
    claims 解绑保留（thread_id→NULL）此前无任何列表入口，手记写了就
    沉库看不见。orphaned=true 只列孤儿（删过线程的遗留），false 只列
    在册线程的，省略全列。返回 claims + n_total 截断披露。"""
    if limit < 1 or limit > 200:
        raise ValidationError("条数填 1 到 200")
    with deps.knowledge() as kb:
        where, params = "", []
        if orphaned is True:
            where, params = " WHERE d.thread_id IS NULL", []
        elif orphaned is False:
            where, params = " WHERE d.thread_id IS NOT NULL", []
        n_total = kb.db.execute(
            f"SELECT count(*) c FROM derived d{where}", params
        ).fetchone()["c"]
        rows = kb.db.execute(
            "SELECT d.id, d.kind, d.claim, d.method, d.confidence, "
            "d.thread_id, d.created_at, "
            "(SELECT count(*) FROM evidence e WHERE e.derived_id=d.id) ev "
            f"FROM derived d{where} ORDER BY d.id DESC LIMIT ?",
            params + [limit]).fetchall()
        return {
            "claims": [{
                "id": r["id"], "kind": r["kind"], "claim": r["claim"],
                "method": r["method"], "confidence": r["confidence"],
                "thread_id": r["thread_id"],
                "orphaned": r["thread_id"] is None,
                "created_at": r["created_at"],
                "n_evidence": r["ev"],
            } for r in rows],
            "n_total": n_total, "has_more": n_total > len(rows),
        }


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
            raise NotFoundError("这条线程没找到，可能已经删了")
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
    # R2349z（R96-P0-1）：'note' 用户手记——非断言，G8 放行无证据。
    if req.kind not in ASSERTING + ("refusal", "note"):
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
        # R3369（审-P1-3）：备份回灌的孤儿手记——orphan=true 时如实
        # 落 thread_id=NULL，不为它硬开空线程。
        if tid is None and not req.orphan:      # 后续步骤失败时要连带删掉（ENOSPC 实测留空壳）
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
        elif tid is not None:
            # R230r（R30-#17）：绑到不存在的线程此前拖到 record() 撞 FK
            # →「类型或内容不合规」误导文案。存在性检查后如实 404。
            # R3369（审-P1-3）：orphan 通道 tid=None 不进存在性检查。
            if not kb.db.execute("SELECT 1 FROM thread WHERE id=?",
                                 (tid,)).fetchone():
                raise NotFoundError("这条线程没找到，可能还没聊过")
        ev = [Evidence(work_id=e.work_id, file=e.file,
                       raw_start=e.raw_start if e.raw_start is not None else -1,
                       raw_end=e.raw_end if e.raw_end is not None else -1,
                       quote=e.quote, page_anchor=e.page_anchor,
                       scheme=e.scheme, addr1=e.addr1, addr2=e.addr2,
                       role=e.role)
              for e in req.evidence]
        # R3369（审-P1-3）：孤儿回灌去重——同一 claim+method 已落则
        # 幂等返回既有 id，重灌不翻倍。
        if tid is None and req.orphan:
            _dup = kb.db.execute(
                "SELECT id FROM derived WHERE claim=? AND method=? "
                "AND thread_id IS NULL LIMIT 1",
                (req.claim, req.method)).fetchone()
            if _dup:
                return {"recorded": _dup["id"], "duplicated": True}
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
            raise ValidationError("这条没存上：格式不对，检查一下再试") from exc
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
        _sc, _note = _clamp_limit(sample_chars, 20, 200, "抽样字数")
        r = structure(c, work_id, sample_chars=_sc)
        if _note:
            r["limit_note"] = _note
        return r


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
        _lm, _note = _clamp_limit(limit, 1, 200, "一次读条数")
        r = chapter(c, work_id, scheme, addr_name=addr_name, addr1=addr1,
                    file=file, limit=_lm)
        if _note:
            r["limit_note"] = _note
        return r


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
            raise ValidationError("这个日期没换成农历，可能超出历法表范围") from None
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
                _dd = datetime.strptime(_cd, "%Y-%m-%d") if _cd else _now_cn()
            except (ValueError, TypeError):
                _dd = _now_cn()
        _pp = liuyao_mod.paipan(ben, _bazi_day_ganzhi(_dd)[0][0])
        # R3168：月建/日辰坐标——传统断卦的旺衰锚此前没算进盘。
        # 月建取节气月支（八字月柱第二字），日辰取当日干支支。
        if _pp is not None:
            try:
                _dgz = _bazi_day_ganzhi(_dd)[0]
                _mpz = bazi_compute(_dd.year, _dd.month,
                                    _dd.day, 12).month
                if _mpz and len(_mpz) > 1 and _mpz != "??":
                    _pp["yuejian"] = _mpz[1]
                if _dgz and len(_dgz) > 1:
                    _pp["richen"] = _dgz[1]
                    # R3170：旬空——日干支定旬，旬外两支落空亡
                    # （甲子旬戌亥空…）。用神/世爻落空是「事未坐实」
                    # 的经典信号，此前盘上完全没有。
                    from guji.bazi import GAN as _XG, ZHI as _XZ
                    _gs, _zb2 = _XG.find(_dgz[0]), _XZ.find(_dgz[1])
                    if _gs >= 0 and _zb2 >= 0:
                        _xs = (_zb2 - _gs) % 12
                        _pp["xunkong"] = [_XZ[(_xs + 10) % 12],
                                          _XZ[(_xs + 11) % 12]]
                # R3172：卦级六合/六冲——八纯+无妄+大壮为六冲卦（主散主快），
                # 否泰困节旅贲复豫为六合卦（主缠主聚）。感情题最重的格局
                # 属性，此前盘上没算。
                _LH = {11, 12, 16, 22, 24, 47, 56, 60}
                _LC = {1, 2, 25, 29, 30, 34, 51, 52, 57, 58}
                for _gk in ("ben_gua", "bian_gua"):
                    _g2 = _pp.get(_gk) or {}
                    _gn2 = _g2.get("gua_number")
                    _g2["liuhe_chong"] = ("六合" if _gn2 in _LH else
                                          "六冲" if _gn2 in _LC else "")
                # R3173：伏神——六亲缺位时查本宫纯卦同位爻（藏在本卦
                # 爻下的星）。200 卦实测妻财缺位 23.5%、官鬼 12%——
                # 感情题用神四分之一概率不上卦，缺伏神就只能搪塞。
                _have_lq = {l.get("liuqin")
                            for l in (_pp["ben_gua"].get("lines") or [])}
                _miss_lq = {"父母", "兄弟", "子孙", "妻财", "官鬼"} \
                    - _have_lq - {""}
                if _miss_lq:
                    _GONG_PURE = {"乾": 1, "坤": 2, "震": 51, "巽": 57,
                                  "坎": 29, "离": 30, "艮": 52, "兑": 58}
                    _gn0 = _GONG_PURE.get(
                        (_pp["ben_gua"].get("gong") or ""))
                    if _gn0:
                        _tb = liuyao_mod.TRIGRAM_BITS[
                            _pp["ben_gua"]["gong"]]
                        _h0 = liuyao_mod.Hexagram(
                            lines=[liuyao_mod.Yao(
                                yang=bool((_tb | (_tb << 3)) >> (p - 1) & 1),
                                moving=False, position=p)
                                for p in range(1, 7)],
                            gua_number=_gn0,
                            gua_name=liuyao_mod.GUA_NAMES_64[_gn0 - 1],
                            moving_lines=[])
                        _fp = liuyao_mod.paipan(_h0, _dgz[0] if _dgz else "")
                        _pp["fushen"] = [
                            {"liuqin": fl.get("liuqin"),
                             "position": fl.get("position"),
                             "stem": fl.get("stem"),
                             "branch": fl.get("branch"),
                             "wuxing": fl.get("wuxing")}
                            for fl in (_fp.get("ben_gua", {})
                                       .get("lines") or [])
                            if fl.get("liuqin") in _miss_lq]
            except Exception:
                pass
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
    # R2350b（R98-P0-1 附带）：回显起卦时间——卡面此前不回显，
    # 表单默认值 bug 期间用户无从察觉卦是按哪天起的。
    if req.method == "time":
        _cast_at = f"{req.year}年{req.month}月{req.day}日 {req.hour}时"
    else:
        _cd0 = getattr(req, "client_date", None)
        try:
            _cd1 = datetime.strptime(_cd0, "%Y-%m-%d")
            _cast_at = f"{_cd1.year}年{_cd1.month}月{_cd1.day}日（铜钱摇）"
        except (ValueError, TypeError):
            _cast_at = "刚才（铜钱摇）"
    out = {
        "ben": ben_out,
        "bian": bian_out,
        "ben_jing": ben_jing,
        "bian_jing": bian_jing,
        "cast_at": _cast_at,
        # R2350f（R102-P1-1）：回显 seed——铜钱卦 seed 可复现同卦，分享链
        # 带 s= 让接收方翻到「TA 摇到的那卦」。时间起卦的 seed 不参与
        # 构造（卦面随日时走），回显无害。
        "seed": req.seed,
        "method": req.method,
        "interpretation": interpretation,
        # 判据 8：六爻原本对提问只回「不代为断事」。warm 分支给出基于**已起出
        # 的卦象**的描述性回应（不预测结果），专业分支原文不动。
        "warm": voice.warm_liuyao(ben_out, bian_out, ben.moving_lines,
                                  interpretation, req.question,
                                  paipan=_pp),
        # R218a-巡2（N-01）：echo question 让前端 liuyaoQuestionHook 真生效
        "question": req.question,
        # R2349q（R81-P2-14）：paipan（纳甲/六亲/世应/六神）算完只喂了
        # warm，API 拿不到——入响应让前端画出坐标层。
        "paipan": _pp,
        # R221b：交叉引用收口 7/7——六爻不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_liuyao(ben.moving_lines,
                                        today_iso=getattr(req, "client_date", None)),
        # R3154：与其他四面同契约——ai_polish 恒在（同步段永 None，
        # 解读走 ai_task_id 轮询），ai_task_id 仅 LLM 开启时追加。
        "ai_polish": None,
    }
    # R2349s（R83-P0-1）：时间起卦同一天同时辰卦族高度集中（梅花公式
    # 构造使然，60 天实测只出 8/64 卦）——如实披露并指铜钱路。
    if req.method == "time":
        _wr = out["warm"].get("reply")
        if isinstance(_wr, list):
            _wr.append("小提示：时间起卦的卦面跟着日时走，同一个时辰里"
                       "摇多少次都是同一卦：想要每次不同的卦面，"
                       "试试铜钱摇卦。")
    # R230z（R36-P1-1）：六爻进台账；摘要用问题或本卦名
    # R2350g（R104-P1-3）：record=false 的分享重放不进接收方台账。
    if getattr(req, "record", True):
        paipan_history.save_async(
            {"method": req.method, "seed": req.seed, "year": req.year,
             "month": req.month, "day": req.day, "hour": req.hour,
             "question": req.question},
            out, rtype="liuyao",
            name=("六爻 · " + (req.question or ben_out.get("gua_name") or "起卦")))
    # R3154：六爻接 AI 解读块——卦象坐标+判词行进 facts，与 bazi 同机制
    # R3157：record=False 是分享重放（爬虫/链接预览可达）——小桶限速
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_liuyao(out, out.get("warm"), req.question),
        req.question,
        rate_key=("ai" if getattr(req, "record", True) else "ai_replay"),
        rate_limit=(60 if getattr(req, "record", True) else 15))
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    # R3124b：判词升格信道用结果 ref
    out["result_ref"] = _stash_result("liuyao", out)
    return out


def huangli(date_str: str | None = None, affair: str | None = None,
            days: int = 1,
            # R2349k（R72-B3）：cross_ref 的「今天/那天」锚客户端本地日
            # （UTC 服务器日与中国用户差 8 小时）。
            today: str | None = None) -> dict:
    """黄历择日（本地纯计算）。

    - date=YYYY-MM-DD：单日宜忌坐标（建除/二十八宿/彭祖百忌）
    - affair=婚嫁&days=30：在 [date, date+days) 内找宜该事项的日子
    """
    # R228p：手写 split('-') 校准器退役——与 xingzuo/daily 同走
    # _parse_iso_date（fromisoformat 对月日越界天然 400，三段校验不再需要）。
    # R2349k（R72-B5）：?date= 空串此前静默当「没传」查今天——与
    # daily/xingzuo 的空串→400 口径对齐。
    if date_str == "":
        raise ValidationError("日期格式没看懂，照着 2026-01-01 这样填试试")
    # R2355（R111-P2-8）：today= 垃圾值此前在 cross_ref 内吞错回退服务器
    # 日——契约上悄悄吞错。与 date= 同口径：非法即 400。
    if today:
        try:
            _td = date.fromisoformat(today)
        except ValueError:
            raise ValidationError(
                "today 参数格式没看懂，照着 2026-01-01 这样填试试") from None
        # R2506（审-F3）：与 _parse_iso_date 同口径——非规范形拒掉，
        # 年份也钳到节气表适用界（此前 today=9999-12-31 静默 200）。
        if _td.isoformat() != today or not (YEAR_LO <= _td.year <= YEAR_HI):
            raise ValidationError(
                "today 参数格式没看懂，照着 2026-01-01 这样填试试")
    dt = (datetime(_d.year, _d.month, _d.day)
          if (_d := _parse_iso_date(date_str) if date_str else None)
          else _now_cn())

    if affair:
        # R228b：days 不设上限时 find_good_days 逐日扫描线性放大
        # （实测 365 天≈21s）——服务层兜底钳位，与路由 Query(le=92) 同值。
        days = max(1, min(int(days), 92))
        end = dt + timedelta(days=days - 1)
        # R2349n（R77-P1-1）：繁体 affair 归一——簽約/結婚直达 API 零命中。
        affair = _t2s(affair)
        # R228x：口语词归一——「理发/养猫」不在宜忌词表里，精确匹配恒空；
        # 与聊天/问一嘴同走 _CHAT_SCENE_TERMS 拿规范词集合，逐词找日
        # 后按日期并集（一事项多规范词：搬家→移徙+入宅+修造）。
        terms = _CHAT_SCENE_TERMS.get(affair)
        if terms is None:
            # R2400（R141-P2-3）：精确键未中时与聊天同走「子串最长命中」——
            # affair=签订合同/签合同此前 terms=[原词] 恒空。
            # R3323-P3-6：子串命中限「键贴尾/后跟日子缀」——家长会→家长
            # （谒贵+嫁娶）、约会所→约会这类前缀误配此前静默上榜。
            # 「搬家吉日」「领证好日子」这类日子缀仍放行。
            _sub = [k for k in _CHAT_SCENE_TERMS
                    if k in affair and (
                        affair.endswith(k)
                        or affair[affair.index(k) + len(k):] in (
                            "黄道吉日", "吉日", "日子", "好日子",
                            "的日子"))]
            terms = _CHAT_SCENE_TERMS[max(_sub, key=len)] if _sub else [affair]
        # R229z续8（R8 P1-1）：原实现对 terms 逐词跑 find_good_days（5 词×92
        # 天=460 次 day_query）——find_good_days 现直接收词列表，单日循环
        # 一次判定全部词（92 天恒 92 次）。
        good = [{"date": _q["date"], "yi": _q["yi"], "ji": _q["ji"],
                 # R2349l（R73-P1-5）：硬凶 flag（月破/四离/四绝/杨公忌）
                 # 透出——吉日榜排序把无凶日排在前面，前端给带凶日 ⚠ 标。
                 "flags": _q.get("day_flags", [])}
                # R8 P2-6：前端只读 date/yi/ji/flags——pengzu/shensha/lunar/
                # chongsha 不随列表回吐（92天×12.9KB→~2KB）。
                for _q in huangli_mod.find_good_days(dt, end, terms)]
        # R3317-B：月内稀有度补扫要用映射前的词表（与主扫同口径）。
        _terms_scan = list(terms)
        # R2349n（R77-P2-3）：回显归一后的 terms——affair=婚嫁实际按
        # 嫁娶查，回显原词会让 API 消费者拿 terms 对 yi 误判。
        terms = [huangli_mod.AFFAIR_ALIASES.get(t, t) for t in terms]
        # 排序：硬凶少的在前，同级按日期——「本月领证吉日榜」该有的榜感。
        good.sort(key=lambda g: (len(g["flags"]), g["date"]))
        # R2400（R141-P3-1）：days 回显实扫窗口（2100 域边钳位后不再是
        # 请求值）+截断标记；（R141-P3-2）整窗在过去时加 past 标记——
        # 裸 API 消费者此前拿无标记的过去吉日。
        _end_eff = min(end, datetime(2100, 12, 31, tzinfo=end.tzinfo))
        _scanned = max(0, (_end_eff - dt).days + 1)
        _unrec = (terms == [affair] and affair not in _HUANGLI_VOCAB
                  and affair not in huangli_mod.AFFAIR_ALIASES)
        out = {"affair": affair, "terms": terms,
               "start": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
               "days": _scanned, "good_days": good, "count": len(good)}
        if _scanned < days:
            out["truncated"] = True
        if _end_eff.date() < _now_cn().date():
            out["past"] = True
        # R3323-P2-4：unrecognized 只在真零命中时置位——「土」这类
        # 子串命中词 count>0 还带 unrecognized 是自相矛盾的旗。
        if _unrec and not good:
            out["unrecognized"] = True
        # R3323-P0-1：ji-only 词（破土/诉讼/求名/乘船/登山/开仓/出官/
        # 行丧/田猎——黄历只讲避不讲宜）恒空榜是死路，反向出避让榜。
        if not good and all(t in _HUANGLI_JI_VOCAB for t in terms):
            out["ji_only"] = True
            _bd = huangli_mod.find_bad_days(dt, _end_eff, terms)
            out["bad_days"] = [{"date": _q["date"], "ji": _q["ji"]}
                               for _q in _bd[:14]]
            out["bad_count"] = len(_bd)
            # R3330（审-中2）：避让榜之外补「相对清净日」副榜——
            # 只忌不宜的词，忌日之外等于隐性放行池，凶日也被隐性
            # 推成「可以的日子」。显式核过的干净日一起透出。
            _cd = huangli_mod.find_calm_days(dt, _end_eff, terms)
            out["calm_days"] = [{"date": _q["date"]} for _q in _cd[:14]]
            out["calm_count"] = len(_cd)
            if len(_bd) > 14 or len(_cd) > 14:
                out["list_truncated"] = True
        # R3323-P2-1：簇否决过而族口径冲突的「小有顾忌」日透出——
        # 榜说宜签约而卡判宜忌都有的分裂（92 天 48 日）得有标记者。
        if good:
            _fam_t: set[str] = set()
            for _t in terms:
                _fam_t |= set(huangli_mod.term_family(_t))
            for g in good:
                _sw = sorted({w for w in g["ji"]
                              if any(t in w or w in t for t in _fam_t)})
                if _sw:
                    g["soft_conflict"] = _sw
        # R3317-B：吉日稀有度——「本月第 N 个吉日（共 M 个）」的晒图句。
        # 需要月内完整排名，故按命中日所在月各跑一次月窗；只在小窗
        # （≤45 天，≤2 个月）补这笔账，大窗不动（成本封顶 ~60 次
        # day_query，与主扫同量级内）。扫失败月份静默不标。
        if good and _scanned <= 45:
            _mrank, _mtotal = {}, {}
            for _ym in {g["date"][:7] for g in good}:
                try:
                    _y0, _m0 = int(_ym[:4]), int(_ym[5:7])
                    _ms = datetime(_y0, _m0, 1,
                                   tzinfo=dt.tzinfo)
                    _me = (datetime(
                        _y0 + (1 if _m0 == 12 else 0),
                        1 if _m0 == 12 else _m0 + 1, 1,
                        tzinfo=dt.tzinfo) - timedelta(days=1))
                    _mg = huangli_mod.find_good_days(_ms, _me, _terms_scan)
                    _mrank[_ym] = {q["date"]: i + 1
                                   for i, q in enumerate(_mg)}
                    _mtotal[_ym] = len(_mg)
                except Exception:
                    pass
            for g in good:
                _tbl = _mrank.get(g["date"][:7]) or {}
                if g["date"] in _tbl:
                    g["month_rank"] = _tbl[g["date"]]
                    g["month_total"] = _mtotal[g["date"][:7]]
        return out

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
                    f"排盘按立春换年（{_bz_year}年），都正常，看哪个口径")
        except Exception:
            pass
    _out = {"date": q["date"], "yi": q["yi"], "ji": q["ji"],
            "jianchu": q.get("jianchu"), "xiu": q.get("xiu"),
            "pengzu": q.get("pengzu"), "shensha": q.get("shensha"),
            **({"conflict": q["conflict"]} if q.get("conflict") else {}),
            # R2349n（R77-P0-1）：跨字同义对冲透出（前端合入※标）
            **({"conflict_family": q["conflict_family"]}
               if q.get("conflict_family") else {}),
            **_ynote,
            **({"cross_ref": _cross_ref_huangli(date_str, today)}),  # C-003：黄历交叉引用
            **({"lunar": q["lunar"]} if q.get("lunar") else {}),
            **({"chongsha": q["chongsha"]} if q.get("chongsha") else {}),
            **({"day_flags": q["day_flags"]} if q.get("day_flags") else {}),
            # R2350a（R94-P1-4/P2-10）：值神+时辰吉凶+日干支透出。
            "zhishen": q.get("zhishen"), "zhishen_ji": q.get("zhishen_ji"),
            "hours": q.get("hours"), "ganzhi_day_cn": q.get("ganzhi_day_cn"),
            # R233w（R52-P3-9）：交节日透明化——「今日交节 XX，交在 HH:MM」
            **({"term_today": q["term_today"]}
               if q.get("term_today") else {}),
            # R2349k（R72-A2）：节日行——前端拿到显示「今天是中秋节」。
            "festival": _festival_for(
                dt.date(),
                (q.get("term_today") or {}).get("name", ""))}
    # R3189：黄历卡接 AI 解读块——宜忌/值神/冲煞坐标进 facts，
    # polish 串成「今天天气预报」式人话；与各面同契约 ai_task_id。
    _out["ai_polish"] = None
    _hl_tid = llm_polish.spawn_ai_task(
        llm_polish.facts_huangli(_out),
        "看看这天的黄历",
        rate_key="ai", rate_limit=60)
    if _hl_tid:
        _out["ai_task_id"] = _hl_tid
    return _out


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
# R2400（R123-P2-7）：情绪倾诉词表——无事项场景时命中即零事实供给
# （求安慰的上下文里不该塞当日宜忌，会把共情话头带歪）。
_MOOD_VENT_PAT = re.compile(
    r"心情|网抑云|emo|好丧|丧丧|难过|难受|想哭|郁闷|心烦|烦死|好烦|"
    r"心累|压力大|压力好大|低落|委屈|崩溃|破防|不开心|不高兴|emo了")

_CHAT_SCENE_TERMS: dict[str, list[str]] = {
    # R3084（巡#501）：面试/求职补谒贵腿——答辩早已是[入学,谒贵]
    # 双腿（应试+面见），面试/求职同属面对评审的场景，缺腿会让
    # 「宜谒贵」的见官日漏判成中性。上班/入职是单纯赴任保持单腿。
    "面试": ["上任", "谒贵"], "求职": ["上任", "谒贵"],
    "上班": ["上任"], "入职": ["上任"],
    # R3084（巡#501）：相亲/表白/约会补议亲/见面腿——与见家长
    # [谒贵,嫁娶]同构：相亲是议亲本义（纳采/订盟），表白是定盟约
    # 向，约会带见人腿。缺腿时「宜纳采+忌嫁娶」日判中性丢真实判定。
    "约会": ["嫁娶", "谒贵"], "表白": ["嫁娶", "订盟"],
    "相亲": ["嫁娶", "纳采", "订盟"], "结婚": ["嫁娶"],
    "领证": ["嫁娶"],
    # R229q：与前端 HL_SCENE_ALIAS 逐键同构（probe_date_parity 钉扎）。
    # 「平整」入搬家系（整理归置），「远行」作词条映射到出行。
    # R2349n（R77-P2-6）：「移徒」是异体字死词（词表统一为移徙）。
    "搬家": ["移徙", "入宅", "修造", "平整"],
    "挪窝": ["移徙"], "远行": ["出行"],
    # R2349s（R85-P1-1）：神煞层独贡献词「归家」此前两条路径都不在——
    # 聊天问「今天适合归家吗」退化成当日宜忌总表。补映射进出行系。
    "归家": ["出行", "远行"],
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
    "手术": ["求医", "治病", "求医疗病"],
    "开刀": ["求医", "治病", "求医疗病"],
    # R2349n（R77-P0-3）：医疗口径统一——「体检/洗牙/医美」此前只映
    # 求医一个词，比「看病」少一半候选日且全克破日；与看病同集。
    "体检": ["求医", "治病", "求医疗病"], "洗牙": ["求医", "治病", "求医疗病"],
    "拔牙": ["求医", "治病", "求医疗病"], "复诊": ["求医", "治病", "求医疗病"],
    "复查": ["求医", "治病", "求医疗病"],
    "医美": ["求医", "治病", "求医疗病"], "整容": ["求医", "治病", "求医疗病"],
    # R3370-P2-7：就医场景词与前端别名表同构（probe_date_parity 双端同键）。
    "医院": ["求医", "治病", "求医疗病"], "住院": ["求医", "治病", "求医疗病"],
    "诊所": ["求医", "治病", "求医疗病"], "门诊": ["求医", "治病", "求医疗病"],
    "急诊": ["求医", "治病", "求医疗病"], "出院": ["求医", "治病", "求医疗病"],
    "借钱": ["纳财"], "讨债": ["纳财"], "还钱": ["纳财"], "还贷": ["纳财"],
    "辞职": ["解除"], "离职": ["解除"],
    # R3083（巡#500）：跳槽/换工作是双腿行为——离开（解除）+赴任
    # （上任）。只映解除会把「宜解除+忌上任」的日子判成中性/宜，
    # 黄历说忌赴任却告诉用户跳槽照常——与买房（纳财+入宅）双腿
    # 同构补上任腿。辞职/离职是纯离开，解除单腿正确不动。
    "跳槽": ["解除", "上任"], "换工作": ["解除", "上任"],
    "解除合同": ["解除"], "毁约": ["解除"], "退婚": ["解除"], "分手": ["解除"],
    # 「说拜拜/拜拜了」口语是散伙不是祭祀（词表「拜拜」仍归祭祀——
    # 长键先中，「说拜拜」优先落这里）
    "说拜拜": ["解除"], "拜拜了": ["解除"], "再见": ["解除"],
    "出国": ["出行", "远行"], "出门": ["出行", "远行"],
    # R2574：买手机/签证实测落「不认得」——购物系与 1460 行
    # 「购物本质是出门」同口径归出行；签证是出门前置。
    "买手机": ["出行"], "签证": ["出行", "远行"],
    "宠物": ["进人口"], "养猫": ["进人口"], "养狗": ["进人口"],
    "钓鱼": ["捕捉"], "捕捞": ["捕捉"],
    # R229w：逛街/出去玩/购物本质是出门——映射到出行给真判定（比
    # 永远中性卡有用）；聚餐系映射到出行+谒贵（出门见人）。
    # 健身/唱歌无对应规范词，保留自映射走中性口径。
    "聚餐": ["出行", "谒贵"], "请客": ["出行", "谒贵"],
    "聚会": ["出行", "谒贵"], "饭局": ["出行", "谒贵"],
    "购物": ["出行"], "买东西": ["出行"], "逛街": ["出行"],
    "出去玩": ["出行", "远行"],
    # R2349q（R82-P2-6）：真实语料缺口——「买房」只在已成事实标记里，
    # 词表缺席走零事实泛句；买房=置产安家向（纳财+入宅）。
    # 蹦极归出行；打游戏/熬夜自映射走中性口径。
    "买房": ["纳财", "入宅"], "买房子": ["纳财", "入宅"], "置业": ["纳财", "入宅"],
    "蹦极": ["出行"],
    "打游戏": ["打游戏"], "玩游戏": ["打游戏"], "熬夜": ["熬夜"],
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
    "do脸": ["求医", "治病", "求医疗病"],
    "水光针": ["求医", "治病", "求医疗病"],
    "双眼皮": ["求医", "治病", "求医疗病"],
    "微整": ["求医", "治病", "求医疗病"],
    # 婚恋/家庭：见长辈→谒贵+嫁娶；喜事→嫁娶；产检动身体→求医。
    "见家长": ["谒贵", "嫁娶"], "见父母": ["谒贵", "嫁娶"],
    # R2349d：「见男朋友家长」里「见家长」不连续——补「家长」兜底。
    "家长": ["谒贵", "嫁娶"],
    "订婚": ["嫁娶"], "提亲": ["嫁娶"], "彩礼": ["纳财"],
    "产检": ["求医", "治病", "求医疗病"], "求婚": ["嫁娶"], "离婚": ["解除"],
    # 追星/演出：到场→出行+谒贵；抢票开票是花钱事→纳财。
    "抢票": ["纳财"], "开票": ["纳财"], "演唱会": ["出行", "谒贵"],
    "签售会": ["出行", "谒贵"], "见爱豆": ["出行", "谒贵"],
    "音乐节": ["出行"], "应援": ["出行"],
    # 宠物：领进门→进人口；动身体→求医。
    "接猫": ["进人口"], "领养": ["进人口"], "接新猫": ["进人口"],
    "接小猫": ["进人口"],
    "绝育": ["求医", "治病", "求医疗病"],
    "打疫苗": ["求医", "治病", "求医疗病"],
    "疫苗": ["求医", "治病", "求医疗病"],
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
    # R2349n（R77-P1-1）：API 层精确键裸奔的高频词——复诊/开工/乔迁/
    # 买车/会友/沐浴/纹身/直播 等此前直达 ?affair= 零命中。
    "开工": ["动土", "开市", "修造"], "开工大吉": ["动土", "开市"],
    "乔迁": ["移徙", "入宅"], "搬新家": ["移徙", "入宅"],
    "买车": ["纳财", "立券"], "提车": ["纳财", "立券"],
    "会友": ["谒贵", "出行"], "会亲友": ["谒贵", "出行"],
    "沐浴": ["沐浴"], "洗澡": ["沐浴"],
    "纹身": ["求医", "冠笄"],
    "割双眼皮": ["求医", "治病", "求医疗病"],
    # 直播系与前端已立的 开市+纳财 口径同构（主播开播=开张做生意）。
    "直播首秀": ["开市", "纳财"], "开播": ["开市", "纳财"],
    "上学报道": ["入学"], "报道": ["上任", "入学"],
    "成婚": ["嫁娶"], "出嫁": ["嫁娶"], "迎娶": ["嫁娶"],
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
    "打耳洞": ["求医", "治病", "求医疗病"],
    "种睫毛": ["冠笄"], "漂发": ["冠笄"],
    "剧本杀": ["出行", "谒贵"], "密室": ["出行"], "桌游": ["出行", "谒贵"],
    "露营": ["出行"], "爬山": ["出行", "登山"], "徒步": ["出行", "登山"],
    "野餐": ["出行"], "断联": ["解除", "祈福"], "冷战": ["解除"],
}

# 黄历宜忌规范词全集——直接命中这些词也按事项处理。词表由建除/宿值
# 通行规则表汇成；day_query 的 yi/ji 自 R233v 起还并入 shensha_yiji
# 神煞层（370 天窗口里仅此层独贡献「归家/远行」两词——显式补上）。
_HUANGLI_VOCAB: frozenset = frozenset(
    [w for d in (*huangli_mod.ZHIRI_YIJI.values(), *huangli_mod.XIUXIU_YIJI.values())
     for w in (*d["yi"], *d["ji"])] + ["归家", "远行"])
# R228m：frozenset 迭代序跨进程不稳定（PYTHONHASHSEED）——候选词表固定为
# 「长词优先、同长字典序」的 tuple，同一消息在不同进程必选同一事项词。
_HUANGLI_VOCAB_ORD: tuple = tuple(
    sorted(_HUANGLI_VOCAB, key=lambda t: (-len(t), t)))
# R3323-P0-1：忌侧词全集（建除/宿值/神煞三层的 ji 词并集）——
# 破土/诉讼/求名/乘船/登山/开仓/出官/行丧/田猎 这类「只有忌没有宜」
# 的词靠它识别：affair 全词落进这张表时反向出避让榜而不是恒空。
_HUANGLI_JI_VOCAB: frozenset = frozenset(
    [w for d in (*huangli_mod.ZHIRI_YIJI.values(),
                 *huangli_mod.XIUXIU_YIJI.values()) for w in d["ji"]] +
    [w for t in (huangli_mod._TIANSHA_YIJI, huangli_mod._TIAND_YIJI,
                 huangli_mod._YUEDE_YIJI, huangli_mod._JIESHA_YIJI,
                 huangli_mod._ZAISHA_YIJI, huangli_mod._YUESHA_YIJI,
                 huangli_mod._YUEYAN_YIJI) for w in t[1]])


_WEEKDAY = "一二三四五六日天"


def _wd_idx(ch: str) -> int:
    """曜日字 → weekday 索引（一=0..日=6；「天」在串尾 index=7，同周日）。"""
    i = _WEEKDAY.find(ch)
    return 6 if i > 6 else i


def _cn_num(s: str) -> int:
    """中文小数字→int：一/两/十/十一/二十/二十五（≤99）。解析不出 → 0。"""
    s = (s or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (_CN_DIGIT.get(a, 0) or 1) * 10 + _CN_DIGIT.get(b, 0)
    return _CN_DIGIT.get(s, 0)


def _add_months(dt: datetime, n: int) -> datetime:
    """按月份平移（日数钳到目标月月末）——「三个月后」用。"""
    import calendar as _cal
    y = dt.year + (dt.month - 1 + n) // 12
    m = (dt.month - 1 + n) % 12 + 1
    d = min(dt.day, _cal.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)

# R229d：繁中问句归一——「明天適合簽約嗎」此前 _CHAT_SCENE_TERMS 全简体
# 打不中（事实行缺席 → LLM 自由发挥）。只映射问句域常见字，与前端
# app.js _T2S 同表；未映射字原样通过（宁缺毋滥不错转）。
# R3265（R3247-P1-1）：手维护单字表必然漏——audit 实测 29 条繁体
# 梦境输入 MISS 15 条。改为 OpenCC TSCharacters 无歧义映射（4057 条里
# 剔多候选行——「乾→干/乾」这类一简对多繁的歧义项不收，保住「乾卦」；
# 再剔基本块外罕见字）并上手维护条目，共 2801 对，「繁简」紧邻成对空格
# 分隔。前端 app.js _T2S 与本表同源同串（parity 钉扎），改时两侧同步。
_T2S_PAIRS = "丟丢 並并 亂乱 亙亘 亞亚 佇伫 佈布 佔占 併并 來来 侖仑 侶侣 侷局 俁俣 係系 俔伣 俠侠 俥伡 俬私 倀伥 倆俩 倈俫 倉仓 個个 們们 倖幸 倫伦 偉伟 側侧 偵侦 偽伪 傑杰 傖伧 傘伞 備备 傢家 傭佣 傯偬 傳传 傴伛 債债 傷伤 傾倾 僂偻 僅仅 僉佥 僑侨 僕仆 僞伪 僥侥 僨偾 僱雇 價价 儀仪 儁俊 儂侬 億亿 儈侩 儉俭 儎傤 儐傧 儔俦 儕侪 償偿 優优 儲储 儷俪 儺傩 儻傥 儼俨 兇凶 兌兑 兒儿 兗兖 內内 兩两 冊册 冑胄 冪幂 凈净 凍冻 凜凛 凱凯 別别 刪删 剄刭 則则 剎刹 剗刬 剛刚 剝剥 剮剐 剴剀 創创 剷铲 劇剧 劉刘 劊刽 劌刿 劍剑 劑剂 勁劲 動动 務务 勛勋 勝胜 勞劳 勢势 勩勚 勱劢 勳勋 勵励 勸劝 勻匀 匭匦 匯汇 匱匮 區区 協协 卹恤 卻却 卽即 厙厍 厠厕 厤历 厭厌 厲厉 厴厣 參参 叄叁 叢丛 吒咤 吳吴 吶呐 呂吕 咼呙 員员 唄呗 唸念 問问 啓启 啞哑 啟启 啢唡 喚唤 喪丧 喫吃 喬乔 單单 喲哟 嗆呛 嗇啬 嗊唝 嗎吗 嗚呜 嗩唢 嗶哔 嘆叹 嘍喽 嘓啯 嘔呕 嘖啧 嘗尝 嘜唛 嘩哗 嘮唠 嘯啸 嘰叽 嘵哓 嘸呒 嘽啴 噓嘘 噝咝 噠哒 噥哝 噦哕 噯嗳 噲哙 噴喷 噸吨 嚀咛 嚇吓 嚌哜 嚐尝 嚕噜 嚙啮 嚥咽 嚦呖 嚨咙 嚮向 嚲亸 嚳喾 嚴严 嚶嘤 囀啭 囁嗫 囂嚣 囅冁 囈呓 囉啰 囌苏 囑嘱 囪囱 圇囵 國国 圍围 園园 圓圆 圖图 團团 垻坝 埡垭 埰采 執执 堅坚 堊垩 堖垴 堝埚 堯尧 報报 場场 塊块 塋茔 塏垲 塒埘 塗涂 塚冢 塢坞 塤埙 塵尘 塹堑 墊垫 墜坠 墮堕 墰坛 墳坟 墶垯 墻墙 墾垦 壇坛 壋垱 壎埙 壓压 壘垒 壙圹 壚垆 壜坛 壞坏 壟垄 壠垅 壢坜 壩坝 壪塆 壯壮 壺壶 壼壸 壽寿 夠够 夢梦 夾夹 奐奂 奧奥 奩奁 奪夺 奬奖 奮奋 奼姹 妝妆 姍姗 姦奸 娛娱 婁娄 婦妇 婭娅 媧娲 媯妫 媼媪 媽妈 嫋袅 嫗妪 嫵妩 嫺娴 嫻娴 嫿婳 嬀妫 嬃媭 嬈娆 嬋婵 嬌娇 嬙嫱 嬡嫒 嬤嬷 嬪嫔 嬰婴 嬸婶 孃娘 孌娈 孫孙 學学 孿孪 宮宫 寀采 寢寝 實实 寧宁 審审 寫写 寬宽 寵宠 寶宝 將将 專专 尋寻 對对 導导 尷尴 屆届 屍尸 屓屃 屜屉 屢屡 層层 屨屦 屬属 岡冈 峯峰 峴岘 島岛 峽峡 崍崃 崑昆 崗岗 崢峥 崬岽 嵐岚 嵗岁 嶁嵝 嶄崭 嶇岖 嶔嵚 嶗崂 嶠峤 嶢峣 嶧峄 嶨峃 嶮崄 嶸嵘 嶺岭 嶼屿 嶽岳 巋岿 巒峦 巔巅 巖岩 巰巯 巹卺 帥帅 師师 帳帐 帶带 幀帧 幃帏 幗帼 幘帻 幟帜 幣币 幫帮 幬帱 幹干 幾几 庫库 廁厕 廂厢 廄厩 廈厦 廎庼 廕荫 廚厨 廝厮 廟庙 廠厂 廡庑 廢废 廣广 廩廪 廳厅 弒弑 弔吊 弳弪 張张 強强 彆别 彈弹 彌弥 彎弯 彔录 彙汇 彠彟 彥彦 彫雕 彲彨 彿佛 後后 徑径 從从 徠徕 復复 徹彻 恆恒 恥耻 悅悦 悞悮 悵怅 悶闷 悽凄 惡恶 惱恼 惲恽 惻恻 愛爱 愜惬 愨悫 愴怆 愷恺 愾忾 慄栗 態态 慍愠 慘惨 慚惭 慟恸 慣惯 慤悫 慪怄 慫怂 慮虑 慳悭 慶庆 慼戚 慾欲 憂忧 憊惫 憐怜 憑凭 憒愦 憖慭 憚惮 憤愤 憫悯 憮怃 憲宪 憶忆 懇恳 應应 懌怿 懍懔 懞蒙 懟怼 懣懑 懨恹 懲惩 懶懒 懷怀 懸悬 懺忏 懼惧 懾慑 戀恋 戇戆 戔戋 戧戗 戩戬 戱戯 戲戏 戶户 拋抛 挩捝 挱挲 挾挟 捨舍 捫扪 捱挨 捲卷 掃扫 掄抡 掗挜 掙挣 掛挂 採采 揀拣 揚扬 換换 揮挥 揯搄 損损 搖摇 搗捣 搵揾 搶抢 摑掴 摜掼 摟搂 摯挚 摳抠 摶抟 摺折 摻掺 撈捞 撏挦 撐撑 撓挠 撟挢 撣掸 撥拨 撫抚 撲扑 撳揿 撻挞 撾挝 撿捡 擁拥 擄掳 擇择 擊击 擋挡 擔担 據据 擠挤 擬拟 擯摈 擰拧 擱搁 擲掷 擴扩 擷撷 擺摆 擻擞 擼撸 擾扰 攄摅 攆撵 攏拢 攔拦 攖撄 攙搀 攛撺 攜携 攝摄 攢攒 攣挛 攤摊 攪搅 攬揽 敎教 敓敚 敗败 敘叙 敵敌 數数 斂敛 斃毙 斆敩 斕斓 斬斩 斷断 旂旗 旣既 昇升 時时 晉晋 晝昼 暈晕 暉晖 暘旸 暢畅 暫暂 曄晔 曆历 曇昙 曉晓 曏向 曖暧 曠旷 曨昽 曬晒 書书 會会 朧胧 朮术 東东 枴拐 柵栅 柺拐 査查 桿杆 梔栀 梘枧 條条 梟枭 梲棁 棄弃 棊棋 棖枨 棗枣 棟栋 棧栈 棲栖 棶梾 椏桠 楊杨 楓枫 楨桢 業业 極极 榘矩 榦干 榪杩 榮荣 榲榅 榿桤 構构 槍枪 槓杠 槤梿 槧椠 槨椁 槮椮 槳桨 槶椢 槼椝 樁桩 樂乐 樅枞 樑梁 樓楼 標标 樞枢 樣样 樧榝 樳桪 樸朴 樹树 樺桦 樿椫 橈桡 橋桥 機机 橢椭 橫横 檁檩 檉柽 檔档 檜桧 檟槚 檢检 檣樯 檮梼 檯台 檳槟 檸柠 檻槛 櫃柜 櫓橹 櫚榈 櫛栉 櫝椟 櫞橼 櫟栎 櫥橱 櫧槠 櫨栌 櫪枥 櫫橥 櫬榇 櫱蘖 櫳栊 櫸榉 櫻樱 欄栏 欅榉 權权 欏椤 欒栾 欖榄 欞棂 欽钦 歎叹 歐欧 歟欤 歡欢 歲岁 歷历 歸归 歿殁 殘残 殞殒 殤殇 殫殚 殭僵 殮殓 殯殡 殲歼 殺杀 殻壳 殼壳 毀毁 毆殴 毿毵 氂牦 氈毡 氌氇 氣气 氫氢 氬氩 氳氲 氾泛 汎泛 汙污 決决 沒没 沖冲 況况 泝溯 洩泄 洶汹 浹浃 涇泾 涗涚 涼凉 淒凄 淚泪 淥渌 淨净 淩凌 淪沦 淵渊 淶涞 淺浅 渙涣 減减 渢沨 渦涡 測测 渾浑 湊凑 湞浈 湧涌 湯汤 溈沩 準准 溝沟 溫温 溮浉 溳涢 溼湿 滄沧 滅灭 滌涤 滎荥 滙汇 滬沪 滯滞 滲渗 滷卤 滸浒 滻浐 滾滚 滿满 漁渔 漊溇 漚沤 漢汉 漣涟 漬渍 漲涨 漵溆 漸渐 漿浆 潁颍 潑泼 潔洁 潙沩 潛潜 潤润 潯浔 潰溃 潷滗 潿涠 澀涩 澆浇 澇涝 澐沄 澗涧 澠渑 澤泽 澦滪 澩泶 澮浍 澱淀 濁浊 濃浓 濕湿 濘泞 濚溁 濛蒙 濜浕 濟济 濤涛 濫滥 濰潍 濱滨 濺溅 濼泺 濾滤 瀂澛 瀅滢 瀆渎 瀉泻 瀏浏 瀕濒 瀘泸 瀝沥 瀟潇 瀠潆 瀦潴 瀧泷 瀨濑 瀲潋 瀾澜 灃沣 灄滠 灑洒 灕漓 灘滩 灝灏 灣湾 灤滦 灧滟 灩滟 災灾 為为 烏乌 烴烃 無无 煉炼 煒炜 煙烟 煢茕 煥焕 煩烦 煬炀 熅煴 熒荧 熗炝 熱热 熲颎 熾炽 燁烨 燈灯 燉炖 燒烧 燙烫 燜焖 營营 燦灿 燬毁 燭烛 燴烩 燻熏 燼烬 燾焘 爍烁 爐炉 爛烂 爭争 爲为 爺爷 爾尔 牀床 牆墙 牘牍 牽牵 犖荦 犛牦 犢犊 犧牺 狀状 狹狭 狽狈 猙狰 猶犹 猻狲 獁犸 獃呆 獄狱 獅狮 獎奖 獨独 獪狯 獫猃 獮狝 獰狞 獲获 獵猎 獷犷 獸兽 獺獭 獻献 獼猕 玀猡 現现 琱雕 琺珐 琿珲 瑋玮 瑒玚 瑣琐 瑤瑶 瑩莹 瑪玛 瑲玱 璉琏 璡琎 璣玑 璦瑷 璫珰 環环 璵玙 璸瑸 璽玺 璿璇 瓊琼 瓏珑 瓔璎 瓚瓒 甌瓯 甕瓮 產产 産产 甦苏 甯宁 畝亩 畢毕 異异 畵画 當当 疇畴 疊叠 痙痉 痠酸 痾疴 瘂痖 瘋疯 瘍疡 瘓痪 瘞瘗 瘡疮 瘧疟 瘮瘆 瘲疭 瘺瘘 瘻瘘 療疗 癆痨 癇痫 癉瘅 癒愈 癘疠 癟瘪 癡痴 癢痒 癤疖 癥症 癧疬 癩癞 癬癣 癭瘿 癮瘾 癰痈 癱瘫 癲癫 發发 皁皂 皚皑 皰疱 皸皲 皺皱 盃杯 盜盗 盞盏 盡尽 監监 盤盘 盧卢 盪荡 眞真 眥眦 眾众 睏困 睜睁 睞睐 瞘眍 瞞瞒 瞶瞆 瞼睑 矇蒙 矓眬 矚瞩 矯矫 硃朱 硜硁 硤硖 硨砗 硯砚 碕埼 碩硕 碭砀 碸砜 確确 碼码 磑硙 磚砖 磠硵 磣碜 磧碛 磯矶 磽硗 礄硚 礆硷 礎础 礙碍 礦矿 礪砺 礫砾 礬矾 礱砻 祕秘 祿禄 禍祸 禎祯 禕祎 禡祃 禦御 禪禅 禮礼 禰祢 禱祷 禿秃 秈籼 稅税 稈秆 稜棱 稟禀 種种 稱称 穀谷 穌稣 積积 穎颖 穠秾 穡穑 穢秽 穩稳 穫获 穭穞 窩窝 窪洼 窮穷 窯窑 窵窎 窶窭 窺窥 竄窜 竅窍 竇窦 竈灶 竊窃 竪竖 競竞 筆笔 筍笋 筧笕 箇个 箋笺 箏筝 節节 範范 築筑 篋箧 篔筼 篠筿 篤笃 篩筛 篳筚 簀箦 簍篓 簑蓑 簞箪 簡简 簣篑 簫箫 簹筜 簽签 簾帘 籃篮 籌筹 籙箓 籛篯 籜箨 籟籁 籠笼 籤签 籩笾 籪簖 籬篱 籮箩 籲吁 粵粤 糉粽 糝糁 糞粪 糧粮 糰团 糲粝 糴籴 糶粜 糹纟 糾纠 紀纪 紂纣 約约 紅红 紆纡 紇纥 紈纨 紉纫 紋纹 納纳 紐纽 紓纾 純纯 紕纰 紖纼 紗纱 紘纮 紙纸 級级 紛纷 紜纭 紝纴 紡纺 紮扎 細细 紱绂 紲绁 紳绅 紵纻 紹绍 紺绀 紼绋 紿绐 絀绌 終终 絃弦 組组 絆绊 絎绗 結结 絕绝 絛绦 絝绔 絞绞 絡络 絢绚 給给 絨绒 絰绖 統统 絲丝 絳绛 絶绝 絹绢 綁绑 綃绡 綆绠 綈绨 綉绣 綌绤 綏绥 綑捆 經经 綜综 綞缍 綠绿 綢绸 綣绻 綫线 綬绶 維维 綯绹 綰绾 綱纲 網网 綳绷 綴缀 綸纶 綹绺 綺绮 綻绽 綽绰 綾绫 綿绵 緄绲 緇缁 緊紧 緋绯 緑绿 緒绪 緓绬 緔绱 緗缃 緘缄 緙缂 線线 緝缉 緞缎 締缔 緡缗 緣缘 緦缌 編编 緩缓 緬缅 緯纬 緱缑 緲缈 練练 緶缏 緹缇 緻致 緼缊 縈萦 縉缙 縊缢 縋缒 縐绉 縑缣 縕缊 縗缞 縛缚 縝缜 縞缟 縟缛 縣县 縧绦 縫缝 縭缡 縮缩 縱纵 縲缧 縴纤 縵缦 縶絷 縷缕 縹缥 總总 績绩 繃绷 繅缫 繆缪 繒缯 織织 繕缮 繚缭 繞绕 繡绣 繢缋 繩绳 繪绘 繫系 繭茧 繮缰 繯缳 繰缲 繳缴 繹绎 繼继 繽缤 繾缱 纇颣 纈缬 纊纩 續续 纍累 纏缠 纓缨 纔才 纖纤 纘缵 纜缆 缽钵 罈坛 罌罂 罎坛 罰罚 罵骂 罷罢 羅罗 羆罴 羈羁 羋芈 羣群 羥羟 羨羡 義义 羶膻 習习 翫玩 翬翚 翹翘 翽翙 耬耧 耮耢 聖圣 聞闻 聯联 聰聪 聲声 聳耸 聵聩 聶聂 職职 聹聍 聽听 聾聋 肅肃 脅胁 脈脉 脛胫 脣唇 脩修 脫脱 脹胀 腎肾 腖胨 腡脶 腦脑 腫肿 腳脚 腸肠 膃腽 膕腘 膚肤 膠胶 膩腻 膽胆 膾脍 膿脓 臉脸 臍脐 臏膑 臘腊 臚胪 臟脏 臠脔 臢臜 臥卧 臨临 臺台 與与 興兴 舉举 舊旧 舘馆 艙舱 艤舣 艦舰 艫舻 艱艰 艷艳 芻刍 苧苎 茲兹 荊荆 莊庄 莖茎 莢荚 莧苋 華华 菴庵 菸烟 萇苌 萊莱 萬万 萴荝 萵莴 葉叶 葒荭 著着 葤荮 葦苇 葯药 葷荤 蒐搜 蒓莼 蒔莳 蒕蒀 蒞莅 蒼苍 蓀荪 蓆席 蓋盖 蓮莲 蓯苁 蓴莼 蓽荜 蔔卜 蔘参 蔞蒌 蔣蒋 蔥葱 蔦茑 蔭荫 蕁荨 蕆蒇 蕎荞 蕒荬 蕓芸 蕕莸 蕘荛 蕢蒉 蕩荡 蕪芜 蕭萧 蕷蓣 薀蕰 薈荟 薊蓟 薌芗 薑姜 薔蔷 薘荙 薟莶 薦荐 薩萨 薴苧 薺荠 藍蓝 藎荩 藝艺 藥药 藪薮 藴蕴 藶苈 藹蔼 藺蔺 蘀萚 蘄蕲 蘆芦 蘇苏 蘊蕴 蘚藓 蘞蔹 蘢茏 蘭兰 蘺蓠 蘿萝 虆蔂 處处 虛虚 虜虏 號号 虧亏 虯虬 蛺蛱 蛻蜕 蜆蚬 蝕蚀 蝟猬 蝦虾 蝨虱 蝸蜗 螄蛳 螞蚂 螢萤 螻蝼 螿螀 蟄蛰 蟈蝈 蟎螨 蟣虮 蟬蝉 蟯蛲 蟲虫 蟶蛏 蟻蚁 蠁蚃 蠅蝇 蠆虿 蠍蝎 蠐蛴 蠑蝾 蠔蚝 蠟蜡 蠣蛎 蠨蟏 蠱蛊 蠶蚕 蠻蛮 衆众 衊蔑 術术 衕同 衚胡 衛卫 衝冲 袞衮 裊袅 裏里 補补 裝装 裡里 製制 複复 褌裈 褘袆 褲裤 褳裢 褸褛 褻亵 襇裥 襉裥 襏袯 襖袄 襝裣 襠裆 襤褴 襪袜 襯衬 襲袭 襴襕 覈核 見见 覎觃 規规 覓觅 視视 覘觇 覡觋 覥觍 覦觎 親亲 覬觊 覯觏 覲觐 覷觑 覺觉 覽览 覿觌 觀观 觴觞 觶觯 觸触 訁讠 訂订 訃讣 計计 訊讯 訌讧 討讨 訐讦 訒讱 訓训 訕讪 訖讫 記记 訛讹 訝讶 訟讼 訣诀 訥讷 訩讻 訪访 設设 許许 訴诉 訶诃 診诊 註注 証证 詁诂 詆诋 詎讵 詐诈 詒诒 詔诏 評评 詖诐 詗诇 詘诎 詛诅 詞词 詠咏 詡诩 詢询 詣诣 試试 詩诗 詫诧 詬诟 詭诡 詮诠 詰诘 話话 該该 詳详 詵诜 詼诙 詿诖 誄诔 誅诛 誆诓 誇夸 誌志 認认 誑诳 誒诶 誕诞 誘诱 誚诮 語语 誠诚 誡诫 誣诬 誤误 誥诰 誦诵 誨诲 說说 説说 誰谁 課课 誶谇 誹诽 誼谊 誾訚 調调 諂谄 諄谆 談谈 諉诿 請请 諍诤 諏诹 諑诼 諒谅 論论 諗谂 諛谀 諜谍 諝谞 諞谝 諡谥 諢诨 諤谔 諦谛 諧谐 諭谕 諱讳 諳谙 諶谌 諷讽 諸诸 諺谚 諼谖 諾诺 謀谋 謁谒 謂谓 謄誊 謅诌 謊谎 謎谜 謐谧 謔谑 謖谡 謗谤 謙谦 謚谥 講讲 謝谢 謠谣 謡谣 謨谟 謫谪 謬谬 謭谫 謳讴 謹谨 謾谩 譁哗 證证 譎谲 譏讥 譖谮 識识 譙谯 譚谭 譜谱 譟噪 譫谵 譭毁 譯译 議议 譴谴 護护 譸诪 譽誉 讀读 讅谉 變变 讋詟 讎雠 讒谗 讓让 讕谰 讖谶 讚赞 讜谠 讞谳 豈岂 豎竖 豐丰 豔艳 豬猪 豶豮 貓猫 貝贝 貞贞 貟贠 負负 財财 貢贡 貧贫 貨货 販贩 貪贪 貫贯 責责 貯贮 貰贳 貲赀 貳贰 貴贵 貶贬 買买 貸贷 貺贶 費费 貼贴 貽贻 貿贸 賀贺 賁贲 賂赂 賃赁 賄贿 賅赅 資资 賈贾 賊贼 賑赈 賒赊 賓宾 賕赇 賙赒 賚赉 賜赐 賞赏 賠赔 賡赓 賢贤 賣卖 賤贱 賦赋 賧赕 質质 賫赍 賬账 賭赌 賴赖 賵赗 賺赚 賻赙 購购 賽赛 賾赜 贄贽 贅赘 贇赟 贈赠 贊赞 贋赝 贍赡 贏赢 贐赆 贓赃 贔赑 贖赎 贗赝 贛赣 贜赃 赬赪 趕赶 趙赵 趨趋 趲趱 跡迹 踐践 踰逾 踴踊 蹌跄 蹕跸 蹟迹 蹠跖 蹣蹒 蹤踪 蹺跷 躂跶 躉趸 躊踌 躋跻 躍跃 躑踯 躒跞 躓踬 躕蹰 躚跹 躡蹑 躥蹿 躦躜 躪躏 軀躯 車车 軋轧 軌轨 軍军 軑轪 軒轩 軔轫 軛轭 軟软 軤轷 軫轸 軲轱 軸轴 軹轵 軺轺 軻轲 軼轶 軾轼 較较 輅辂 輇辁 輈辀 載载 輊轾 輒辄 輓挽 輔辅 輕轻 輛辆 輜辎 輝辉 輞辋 輟辍 輥辊 輦辇 輩辈 輪轮 輬辌 輯辑 輳辏 輸输 輻辐 輼辒 輾辗 輿舆 轀辒 轂毂 轄辖 轅辕 轆辘 轉转 轍辙 轎轿 轔辚 轟轰 轡辔 轢轹 轤轳 辦办 辭辞 辮辫 辯辩 農农 迴回 逕迳 這这 連连 週周 進进 遊游 運运 過过 達达 違违 遙遥 遜逊 遞递 遠远 遡溯 適适 遲迟 遷迁 選选 遺遗 遼辽 邁迈 還还 邇迩 邊边 邏逻 邐逦 郟郏 郵邮 鄆郓 鄉乡 鄒邹 鄔邬 鄖郧 鄧邓 鄭郑 鄰邻 鄲郸 鄴邺 鄶郐 鄺邝 酇酂 酈郦 醃腌 醖酝 醜丑 醞酝 醟蒏 醣糖 醫医 醬酱 醱酦 釀酿 釁衅 釃酾 釅酽 釋释 釐厘 釒钅 釓钆 釔钇 釕钌 釗钊 釘钉 釙钋 針针 釣钓 釤钐 釦扣 釧钏 釩钒 釵钗 釷钍 釹钕 釺钎 鈀钯 鈁钫 鈃钘 鈄钭 鈅钥 鈈钚 鈉钠 鈍钝 鈎钩 鈐钤 鈑钣 鈒钑 鈔钞 鈕钮 鈞钧 鈡钟 鈣钙 鈥钬 鈦钛 鈧钪 鈮铌 鈰铈 鈳钶 鈴铃 鈷钴 鈸钹 鈹铍 鈺钰 鈽钸 鈾铀 鈿钿 鉀钾 鉆钻 鉈铊 鉉铉 鉋铇 鉍铋 鉑铂 鉕钷 鉗钳 鉚铆 鉛铅 鉞钺 鉢钵 鉤钩 鉦钲 鉬钼 鉭钽 鉳锫 鉶铏 鉸铰 鉺铒 鉻铬 鉿铪 銀银 銃铳 銅铜 銍铚 銑铣 銓铨 銖铢 銘铭 銚铫 銛铦 銜衔 銠铑 銣铷 銥铱 銦铟 銨铵 銩铥 銪铕 銫铯 銬铐 銱铞 銳锐 銷销 銹锈 銻锑 銼锉 鋁铝 鋃锒 鋅锌 鋇钡 鋌铤 鋏铗 鋒锋 鋙铻 鋝锊 鋟锓 鋣铘 鋤锄 鋥锃 鋦锔 鋨锇 鋩铓 鋪铺 鋭锐 鋮铖 鋯锆 鋰锂 鋱铽 鋶锍 鋸锯 鋼钢 錁锞 錄录 錆锖 錇锫 錈锩 錏铔 錐锥 錒锕 錕锟 錘锤 錙锱 錚铮 錛锛 錟锬 錠锭 錡锜 錢钱 錦锦 錨锚 錩锠 錫锡 錮锢 錯错 録录 錳锰 錶表 錸铼 錼镎 鍀锝 鍁锨 鍃锪 鍅钫 鍆钔 鍇锴 鍈锳 鍋锅 鍍镀 鍔锷 鍘铡 鍚钖 鍛锻 鍠锽 鍤锸 鍥锲 鍩锘 鍬锹 鍰锾 鍵键 鍶锶 鍺锗 鍼针 鎂镁 鎄锿 鎇镅 鎊镑 鎌镰 鎔镕 鎖锁 鎘镉 鎚锤 鎛镈 鎡镃 鎢钨 鎣蓥 鎦镏 鎧铠 鎩铩 鎪锼 鎬镐 鎭镇 鎮镇 鎰镒 鎲镋 鎳镍 鎵镓 鎶鿔 鎸镌 鎿镎 鏃镞 鏈链 鏌镆 鏍镙 鏐镠 鏑镝 鏗铿 鏘锵 鏜镗 鏝镘 鏞镛 鏟铲 鏡镜 鏢镖 鏤镂 鏨錾 鏰镚 鏵铧 鏷镤 鏹镪 鏽锈 鐃铙 鐋铴 鐐镣 鐒铹 鐓镦 鐔镡 鐘钟 鐙镫 鐝镢 鐠镨 鐦锎 鐧锏 鐨镄 鐫镌 鐮镰 鐲镯 鐳镭 鐵铁 鐶镮 鐸铎 鐺铛 鐿镱 鑄铸 鑊镬 鑌镔 鑑鉴 鑒鉴 鑔镲 鑕锧 鑞镴 鑠铄 鑣镳 鑥镥 鑭镧 鑰钥 鑱镵 鑲镶 鑷镊 鑹镩 鑼锣 鑽钻 鑾銮 鑿凿 钂镋 長长 門门 閂闩 閃闪 閆闫 閈闬 閉闭 開开 閌闶 閎闳 閏闰 閑闲 間间 閔闵 閘闸 閡阂 閣阁 閤合 閥阀 閨闺 閩闽 閫阃 閬阆 閭闾 閱阅 閲阅 閶阊 閹阉 閻阎 閼阏 閽阍 閾阈 閿阌 闃阒 闆板 闇暗 闈闱 闊阔 闋阕 闌阑 闍阇 闐阗 闒阘 闓闿 闔阖 闕阙 闖闯 關关 闞阚 闠阓 闡阐 闢辟 闤阛 闥闼 陘陉 陝陕 陞升 陣阵 陰阴 陳陈 陸陆 陽阳 隉陧 隊队 階阶 隕陨 際际 隨随 險险 隯陦 隱隐 隴陇 隸隶 隻只 雋隽 雖虽 雙双 雛雏 雜杂 雞鸡 離离 難难 雲云 電电 霑沾 霢霡 霧雾 霽霁 靂雳 靄霭 靆叇 靈灵 靉叆 靚靓 靜静 靝靔 靨靥 鞏巩 鞝绱 鞦秋 鞽鞒 韁缰 韃鞑 韆千 韉鞯 韋韦 韌韧 韍韨 韓韩 韙韪 韜韬 韞韫 韻韵 響响 頁页 頂顶 頃顷 項项 順顺 頇顸 須须 頊顼 頌颂 頎颀 頏颃 預预 頑顽 頒颁 頓顿 頗颇 領领 頜颌 頡颉 頤颐 頦颏 頭头 頮颒 頰颊 頲颋 頴颕 頷颔 頸颈 頹颓 頻频 頽颓 顆颗 題题 額额 顎颚 顏颜 顒颙 顓颛 顔颜 顙颡 顛颠 類类 顢颟 顥颢 顧顾 顫颤 顬颥 顯显 顰颦 顱颅 顳颞 顴颧 風风 颭飐 颮飑 颯飒 颱台 颳刮 颶飓 颸飔 颺飏 颻飖 颼飕 飀飗 飄飘 飆飙 飈飚 飛飞 飠饣 飢饥 飣饤 飥饦 飩饨 飪饪 飫饫 飭饬 飯饭 飱飧 飲饮 飴饴 飼饲 飽饱 飾饰 飿饳 餃饺 餄饸 餅饼 餈糍 餉饷 養养 餌饵 餎饹 餏饻 餑饽 餒馁 餓饿 餕馂 餖饾 餘余 餚肴 餛馄 餜馃 餞饯 餡馅 館馆 餳饧 餶馉 餷馇 餺馎 餼饩 餾馏 餿馊 饁馌 饃馍 饅馒 饈馐 饉馑 饊馓 饋馈 饌馔 饑饥 饒饶 饗飨 饜餍 饞馋 饢馕 馬马 馭驭 馮冯 馱驮 馳驰 馴驯 馹驲 駁驳 駐驻 駑驽 駒驹 駔驵 駕驾 駘骀 駙驸 駛驶 駝驼 駟驷 駡骂 駢骈 駭骇 駰骃 駱骆 駸骎 駿骏 騁骋 騂骍 騅骓 騌骔 騍骒 騎骑 騏骐 騖骛 騙骗 騤骙 騫骞 騭骘 騮骝 騰腾 騶驺 騷骚 騸骟 騾骡 驀蓦 驁骜 驂骖 驃骠 驅驱 驊骅 驌骕 驍骁 驏骣 驕骄 驗验 驚惊 驛驿 驟骤 驢驴 驤骧 驥骥 驦骦 驪骊 驫骉 骯肮 髏髅 髒脏 體体 髕髌 髖髋 髮发 鬆松 鬍胡 鬚须 鬢鬓 鬥斗 鬧闹 鬨哄 鬩阋 鬮阄 鬱郁 鬹鬶 魎魉 魘魇 魚鱼 魛鱽 魢鱾 魨鲀 魯鲁 魴鲂 魷鱿 魺鲄 鮁鲅 鮃鲆 鮊鲌 鮋鲉 鮍鲏 鮎鲇 鮐鲐 鮑鲍 鮒鲋 鮓鲊 鮚鲒 鮜鲘 鮝鲞 鮞鲕 鮦鲖 鮪鲔 鮫鲛 鮭鲑 鮮鲜 鮳鲓 鮶鲪 鮺鲝 鯀鲧 鯁鲠 鯇鲩 鯉鲤 鯊鲨 鯒鲬 鯔鲻 鯕鲯 鯖鲭 鯗鲞 鯛鲷 鯝鲴 鯡鲱 鯢鲵 鯤鲲 鯧鲳 鯨鲸 鯪鲮 鯫鲰 鯰鲶 鯴鲺 鯷鳀 鯽鲫 鯿鳊 鰁鳈 鰂鲗 鰃鳂 鰈鲽 鰉鳇 鰍鳅 鰏鲾 鰐鳄 鰒鳆 鰓鳃 鰛鳁 鰜鳒 鰟鳑 鰠鳋 鰣鲥 鰥鳏 鰨鳎 鰩鳐 鰭鳍 鰮鳁 鰱鲢 鰲鳌 鰳鳓 鰵鳘 鰷鲦 鰹鲣 鰺鲹 鰻鳗 鰼鳛 鰾鳔 鱂鳉 鱅鳙 鱈鳕 鱉鳖 鱒鳟 鱔鳝 鱖鳜 鱗鳞 鱘鲟 鱝鲼 鱟鲎 鱠鲙 鱣鳣 鱤鳡 鱧鳢 鱨鲿 鱭鲚 鱯鳠 鱷鳄 鱸鲈 鱺鲡 鳥鸟 鳧凫 鳩鸠 鳬凫 鳲鸤 鳳凤 鳴鸣 鳶鸢 鴆鸩 鴇鸨 鴉鸦 鴒鸰 鴕鸵 鴛鸳 鴝鸲 鴞鸮 鴟鸱 鴣鸪 鴦鸯 鴨鸭 鴯鸸 鴰鸹 鴴鸻 鴻鸿 鴿鸽 鵂鸺 鵃鸼 鵐鹀 鵑鹃 鵒鹆 鵓鹁 鵜鹈 鵝鹅 鵠鹄 鵡鹉 鵪鹌 鵬鹏 鵮鹐 鵯鹎 鵲鹊 鵷鹓 鵾鹍 鶇鸫 鶉鹑 鶊鹒 鶓鹋 鶖鹙 鶘鹕 鶚鹗 鶡鹖 鶥鹛 鶩鹜 鶬鸧 鶯莺 鶲鹟 鶴鹤 鶹鹠 鶺鹡 鶻鹘 鶼鹣 鶿鹚 鷀鹚 鷁鹢 鷂鹞 鷄鸡 鷊鹝 鷓鹧 鷖鹥 鷗鸥 鷙鸷 鷚鹨 鷥鸶 鷦鹪 鷫鹔 鷯鹩 鷲鹫 鷳鹇 鷴鹇 鷸鹬 鷹鹰 鷺鹭 鷽鸴 鸇鹯 鸌鹱 鸏鹲 鸕鸬 鸘鹴 鸚鹦 鸛鹳 鸝鹂 鸞鸾 鹵卤 鹹咸 鹺鹾 鹼碱 鹽盐 麗丽 麥麦 麩麸 麫面 麯曲 麼么 黃黄 黌黉 點点 黨党 黲黪 黴霉 黶黡 黷黩 黽黾 黿鼋 鼂鼌 鼉鼍 鼕冬 鼴鼹 齊齐 齋斋 齎赍 齏齑 齒齿 齔龀 齕龁 齗龂 齙龅 齜龇 齟龃 齠龆 齡龄 齣出 齦龈 齪龊 齬龉 齲龋 齶腭 齷龌 龍龙 龎厐 龐庞 龔龚 龕龛 龜龟 鿓鿒"
_T2S = {p[0]: p[1] for p in _T2S_PAIRS.split()}


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
    # R3314（R3311-中2）：口碱高频节别名继续补——女神节=3.8（显示仍
    # 妇女节）、万圣夜=10.31、双十二/618=购物节。
    "女神节": (3, 8), "女王节": (3, 8), "万圣夜": (10, 31),
    "双十二": (12, 12), "双12": (12, 12), "618": (6, 18),
    "618购物节": (6, 18),
}
# 农历节日（月, 日）；除夕单列（正月初一前一天）。
_HOLIDAY_LUNAR = {
    "大年初一": (1, 1), "春节": (1, 1), "元宵节": (1, 15), "元宵": (1, 15),
    "端午节": (5, 5), "端午": (5, 5), "七夕": (7, 7), "中秋节": (8, 15),
    "中秋": (8, 15), "重阳节": (9, 9), "重阳": (9, 9), "腊八节": (12, 8),
    "腊八": (12, 8), "中元节": (7, 15), "中元": (7, 15),
    # R2359（R115-P2-4）：「农历/阴历/旧历新年」≡春节（正月初一），
    # 不带前缀的「新年」仍走公历元旦——前缀反转语义要接住。
    "农历新年": (1, 1), "阴历新年": (1, 1), "旧历新年": (1, 1),
    # 小年按北方通行腊月廿三；南方廿四口径暂不强拆，spoken 仍回用户原词。
    "小年": (12, 23),
    # R233v（R52-P2-5）：民俗高频农历节补洞
    "龙抬头": (2, 2), "二月二": (2, 2), "上巳节": (3, 3), "三月三": (3, 3),
    "花朝节": (2, 15), "寒衣节": (10, 1), "十月朝": (10, 1),
    "下元节": (10, 15), "七夕节": (7, 7),
    # R3314（R3311-中2）：民俗别名——破五/人日/填仓（正月初五/初七/廿五）。
    "破五": (1, 5), "人日": (1, 7), "人胜节": (1, 7),
    "填仓": (1, 25), "填仓节": (1, 25),
}
# R3230：零/兩补进唯一一份表——同名重定义会静默覆盖（本会话已踩：
# 在 _wd_idx 旁定义过一份带零/兩的被这里的覆盖）。_lunar_md 的
# m_map 展开它当月份别名——「兩月/零月」非月份写法，值域 1-12 恒滤掉。
_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "兩": 2, "三": 3,
             "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# R3366（审-P1）：「下个月十五号」这类中文数字公历日此前全哑——
# 数字组只接 \d，前后端一起静默按今天判。日号=阿拉伯或
# 十/十五/二十/三十一（单中文数字日不接——「一号楼」邻接歧义大）。
_CN_DAY_RE = r"(\d{1,2}|[一二三]?十[一二三四五六七八九]?)"


def _cn_day_int(s: str):
    """日号文本（阿拉伯或中文复合数字）→ int；解不动返回 None。"""
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"([一二三])?十([一二三四五六七八九])?", s)
    if m:
        tens = _CN_DIGIT.get(m.group(1), 1) if m.group(1) else 1
        return tens * 10 + (_CN_DIGIT.get(m.group(2), 0)
                            if m.group(2) else 0)
    return _CN_DIGIT.get(s)


def _lunar_md(mtxt: str, dtxt: str):
    """农历月日串（中文或数字）→ (month, day)；解不动返回 None。"""
    m_map = {"正": 1, "冬": 11, "腊": 12, "十一": 11, "十二": 12,
             # R3366（审-P1）：漏「十」——「农历十月十五」此前被判
             # "日子不存在"。
             "十": 10,
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
    elif dtxt.startswith("二十"):
        # R3323-P1-2：「腊月二十三/正月二十九」——「二十N/三十N」是
        # 农历日常写法，此前只有廿N 能解，同一天换个写法就「黄历里没有」。
        if len(dtxt) != 3 or dtxt[2:] not in _CN_DIGIT:
            return None
        d = 20 + _CN_DIGIT[dtxt[2:]]
    elif dtxt.startswith("三十"):
        if len(dtxt) != 3 or dtxt[2:] not in _CN_DIGIT:
            return None
        d = 30 + _CN_DIGIT[dtxt[2:]]
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
    # R3314：黑五=11 月第 4 个周五（感恩节次日通行口径）。
    "黑色星期五": (11, 4, 4),
}
# 查询词 → 显示名别名：匹配集里放别名，解析时换显示名查表。
_HOLIDAY_QUERY_ALIAS = {"黑五": "黑色星期五"}
# 节气也可当日期词（「冬至吃饺子」「立春后开工」）——term_time 走
# 天文算法。排除：小满（小满是本应用吉祥物名，「小满觉得我…」是在
# 叫它不是问节气）、大雪/小雪/大寒/小寒（天气语境歧义太大）。
_SOLAR_TERMS = {
    "立春", "雨水", "惊蛰", "春分", "谷雨", "立夏", "芒种", "夏至",
    # R2349k（R72-A1）：立秋曾是节气表里唯一缺词——「秋天第一杯奶茶」
    # 爆点日解不了，静默判当前日。
    "立秋", "处暑", "白露", "秋分", "寒露", "霜降", "立冬", "冬至",
    "大暑", "小暑",
}
# R3323-P0-2：语义双关节气——小满（吉祥物名）/大雪/小雪/大寒/小寒
# （天气语境歧义）不进 _SOLAR_TERMS 免误解；但带「那天/节气」语境时
# 该按节气解：「大寒那天开业吗」此前连 resolve 都不被调，静默拿
# 显示日替人判宜忌。
_SOLAR_TERMS_AMBI = {"大寒", "小寒", "大雪", "小雪", "小满"}


# R2349k（R72-A2）：反向查「这天是什么节」——黄历卡/今日卡的节日行。
# 词源与 _abs_or_holiday 同表（公历固定/农历固定/月第N个周几），另补
# 除夕（腊月最后一日）与节气（huangli() 用已算好的 term_today 叠上）。
_FEST_SOLAR = {
    (1, 1): "元旦", (2, 14): "情人节", (3, 7): "女生节",
    # R3314（R3311-低）：高频叫法并列——受众管 3.8 叫「女神节」
    # 的远多于「妇女节」。
    (3, 8): "妇女节·女神节", (3, 12): "植树节", (3, 14): "白色情人节",
    (4, 1): "愚人节", (5, 1): "劳动节", (5, 4): "青年节",
    (5, 20): "网络情人节", (5, 21): "521", (6, 1): "儿童节",
    (7, 1): "建党节", (8, 1): "建军节", (9, 10): "教师节",
    (10, 1): "国庆节", (11, 1): "万圣节", (11, 11): "双十一",
    (12, 24): "平安夜", (12, 25): "圣诞节", (12, 31): "跨年夜",
    # R3314（R3311-中2）：新收别名同日显示补洞。
    (6, 18): "618 购物节", (10, 31): "万圣夜", (12, 12): "双十二",
}
_FEST_LUNAR = {
    (1, 1): "春节", (1, 15): "元宵节", (2, 2): "龙抬头",
    (2, 15): "花朝节", (3, 3): "上巳节", (5, 5): "端午节",
    (7, 7): "七夕", (7, 15): "中元节", (8, 15): "中秋节",
    (9, 9): "重阳节", (10, 1): "寒衣节", (10, 15): "下元节",
    (12, 8): "腊八节", (12, 23): "小年",
    # R3314（R3311-中2）：民俗小节日也报到。
    (1, 5): "破五", (1, 7): "人日", (1, 25): "填仓节",
}


# R2349l（R73-P1-7）：星座速配——四象分组兼容表，确定性零 LLM。
_SIGN_ELEM: dict[str, str] = {
    "白羊": "火", "狮子": "火", "射手": "火",
    "金牛": "土", "处女": "土", "摩羯": "土",
    "双子": "风", "天秤": "风", "水瓶": "风",
    "巨蟹": "水", "天蝎": "水", "双鱼": "水",
}
# 相合象组：火借风势、土水相养
_SIGN_GOOD: frozenset[frozenset[str]] = frozenset(
    {frozenset({"火", "风"}), frozenset({"土", "水"})})
# 相冲象组：水火急、风土拧
_SIGN_HARD: frozenset[frozenset[str]] = frozenset(
    {frozenset({"火", "水"}), frozenset({"风", "土"})})


def xzmatch(sa: str, sb: str, rel: str = "") -> dict:
    """两星座速配：同象 88 / 相合象组 82 / 相冲 61 / 其余 74，附白话一句。

    四象兼容是通行口径（娱乐向，不涉命理断言）。未知星座名 → {}。
    rel=闺蜜/同事 追加语境尾巴（R73-P2-11）。
    """
    # 归一入参：裸名是表键（狮子/双鱼），用户手写/API 直调最自然的
    # 形态是「狮子座」——此前带「座」一律 400「没认出星座名」。
    # 输出文案用归一后的名字（「都是{sa}座」不吃「狮子座座」）。
    sa = (sa or "").strip()
    sb = (sb or "").strip()
    sa = sa[:-1] if sa.endswith("座") else sa
    sb = sb[:-1] if sb.endswith("座") else sb
    ea, eb = _SIGN_ELEM.get(sa), _SIGN_ELEM.get(sb)
    if not (ea and eb):
        return {}
    pair = frozenset({ea, eb})
    if sa == sb:
        score, label, line = 88, "同款", (
            f"都是{sa}座，脾气同一个模子刻的，合拍时特别合拍，"
            "闹别扭时谁也劝不动谁。")
    elif ea == eb:
        score, label, line = 88, "同象", \
            (f"{ea}象自家人，{sa}和{sb}频率天然接近，相处不费劲。")
    elif pair in _SIGN_GOOD:
        _w = {"火风": "风一吹火就旺，一个出主意一个敢行动，越处越有劲。",
              "土水": "水润土养：一个给安全感一个给柔软，慢热但长久。"}
        score, label, line = 82, "互补", \
            f"{sa}×{sb}：{_w.get(''.join(sorted([ea, eb])), '互补型组合。')}"
    elif pair in _SIGN_HARD:
        # R3101（specs/010）：相冲象组报具体吵点+相处处方——
        # 「多花心思听懂」仍是虚词。
        # 键序注意：''.join(sorted()) 按码位排——土<水<火<风。
        _h = {"水火": "一个急着往前冲、一个先要情绪被接住，最容易吵在"
                     "「你根本不懂我」；处方：急的那个先回应感受，"
                     "慢的那个直接说要什么，别让猜。",
              "土风": "一个想新鲜想变化、一个要稳定要落地，吵的点在"
                     "「靠谱不靠谱」；处方：大事听土象的定盘，"
                     "小事随风象的兴头。"}
        score, label, line = 61, "磨合", \
            f"{sa}和{sb}节奏差得有点大，{_h.get(''.join(sorted([ea, eb])), '要多花点心思听懂对方。')}"
    else:
        # R3101：随缘档（火土/风水）同样落到具体差档。
        _n = {"土火": "火急土稳，节奏差档，分工好了是互补："
                    "冲锋的归火象，收尾的归土象。",
              "水风": "风飘水深：一个想得远一个感受深，"
                    "聊得来要靠翻译：说感受别只说想法。"}
        score, label, line = 74, "随缘", \
            f"{sa}和{sb}，{_n.get(''.join(sorted([ea, eb])), '说不上天生一对，但各有趣味，处着看。')}"
    # R2349l.8（R73-P2-11）：关系维度——闺蜜/同事换一条语境尾巴，
    # 默认（恋人/空）不加，避免硬塞感情腔。
    _rel_tail = {
        "闺蜜": "闺蜜局里这种组合，一个闹一个笑刚刚好。",
        "同事": "共事的话分工比合拍更要紧，各管一段反而顺。",
    }
    if rel in _rel_tail:
        line = line + _rel_tail[rel]
    # R3130：合盘从一行升到判词级——补「相处场景+具体处方」两行，
    # 与合婚/桃花的「剧本+处方」结构同口径（lines 面，FE 逐行渲）。
    _pk = ''.join(sorted([ea, eb]))
    _scene = {
        "火风": "日常画风：一个灵光一闪说「要不现在就去」，另一个已经在"
                "查路线：合拍的时候是加速度，吵起来是一个嫌对方飘、"
                "一个嫌对方冲。",
        "土水": "日常画风：一个默默把事安排好，一个敏感接住所有情绪"
                "，甜的时候像回家，拧的时候是土象嫌水象想太多、"
                "水象嫌土象不开口。",
        "水火": "日常画风：水象情绪低落时要被接住，火象第一反应是"
                "「走，出去转转」，一个要抱抱一个给方案，"
                "两边都觉得自己尽力了对方不领情。",
        "土风": "日常画风：风象兴奋说新点子，土象第一句是「靠谱吗」"
                "，风象觉得被泼冷水，土象觉得对方不着调，"
                "其实一个管刹车一个管油门。",
        "土火": "日常画风：火象要马上动起来，土象要先看稳不稳"
                "，火象嫌土象拖，土象嫌火象莽，节奏岔半拍。",
        "水风": "日常画风：水象说「我难受」，风象开始分析原因"
                "，水象要的是陪不是解，风象给的是解不是陪，"
                "频道差一格。",
    }
    _fix = {
        "火风": "处方：风象出点子前先问一句「你现在接得住吗」，"
                "火象冲锋前给风象留两天消化期，加速度别变成独角戏。",
        "土水": "处方：土象每周主动说一次「我在想什么」别等水象猜，"
                "水象情绪上头时直接说「我要听安慰还是要建议」"
                "别让对面蒙着答题。",
        "水火": "处方：火象先学一招「先陪十分钟再出主意」，"
                "水象直接说「我现在只要抱抱」，猜是最费关系的。",
        "土风": "处方：约定「大事听土象的定盘，小事随风象的兴头」"
                "，谁也别全局接管，各管一段最省电。",
        "土火": "处方：火象给土象一个期限「这周想完就动」，"
                "土象给火象一个进度「想好了第一时间说」"
                "一个防拖死，一个防憋炸。",
        "水风": "处方：风象听到感受先复述一遍再分析，"
                "水象想要分析时明说「帮我想想」"
                "频道对上了什么都好谈。",
    }
    _same_scene = ("日常画风：你们太像了，优点是对方一个眼神就懂，"
                   "缺点是毛病也同款复制，吵架像对着镜子吵。")
    _same_fix = ("处方：同款组合最怕「你也这样凭什么说我」"
                 "谁先看到自己的毛病谁先说破，同款关系里先认账的那个赢。")
    _elem_scene = (f"日常画风：同是{ea}象，频道天然一致，舒服的时候"
                   "是真舒服，要留神的是舒服到不成长，一起原地打转。")
    _elem_fix = ("处方：同象组合要刻意引进点「不一样」"
                 "轮流做那个提反对意见的人，别让同温层越捂越厚。")
    lines = [line]
    if sa == sb:
        lines += [_same_scene, _same_fix]
    elif ea == eb:
        lines += [_elem_scene, _elem_fix]
    else:
        if _scene.get(_pk):
            lines.append(_scene[_pk])
        if _fix.get(_pk):
            lines.append(_fix[_pk])
    lines.append("星座合盘看的是相处节奏的底色，具体的人远比星座大，"
                 "这里给的是地图，路是你们走的。")
    out = {"a": sa, "b": sb, "elem_a": ea, "elem_b": eb,
           "score": score, "label": label, "line": line,
           "lines": lines,
           # R3155：ai_polish 恒在（同步段永 None），ai_task_id 条件追加
           "ai_polish": None}
    # R3155：合盘接 AI 解读块——闺蜜互测是分享场景，要口语段
    # R3157：GET 端点爬虫/预览器可达——独立小桶不占全局「ai」额度
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_xzmatch(out), rate_key="ai_social",
        rate_limit=15)
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    # R3150：合盘此前没进 result_ref 快照——照卡聊「我们配吗」时
    # 小满手里没有权威判词，82 分合拍能被说成「不太行」。
    out["result_ref"] = _stash_result("xzm", out)
    return out


def _festival_for(d: date, term_name: str = "") -> list[str]:
    """公历日 d → 当日节日名列表；无节返回 []。term_name 传当日交节名。"""
    out: list[str] = []
    nm = _FEST_SOLAR.get((d.month, d.day))
    if nm:
        out.append(nm)
    for name, (hm, wd, n) in _HOLIDAY_NTH.items():
        try:
            if _nth_weekday(d.year, hm, wd, n) == d:
                out.append(name)
        except Exception:
            pass
    try:
        from guji import lunar as lunar_mod
        l = lunar_mod.solar_to_lunar(d.year, d.month, d.day)
        if not l.get("is_leap"):
            lnm = _FEST_LUNAR.get((l["month"], l["day"]))
            if lnm:
                out.append(lnm)
            # 除夕 = 腊月最后一日（二十九或三十，随年走）
            if (l["month"] == 12
                    and l["day"] == lunar_mod.month_days(l["year"], 12)):
                out.append("除夕")
    except Exception:
        pass
    # R3314（R3311-中4）：节气从节日行去重——交节日 j.term 横幅与
    # term_today 行已各自报到，festival 行再塞「立秋（节气）」是同
    # 一屏三条重复。节日行只留真节日；节气显示走 term 通道。
    # R3314（R3311-中3）：时令节点——寒食（清明前一日）、入伏
    # （夏至后第三庚日）、数九（冬至起每九天一九，一九~九九首日）。
    try:
        from guji import bazi as bazi_mod
        _qm = (bazi_mod.term_time(d.year, "清明")
               + timedelta(hours=8)).date()
        if d == _qm - timedelta(days=1):
            out.append("寒食节")
        _xz = (bazi_mod.term_time(d.year, "夏至")
               + timedelta(hours=8)).date()
        _cnt = 0
        for _k in range(0, 40):
            _dd = _xz + timedelta(days=_k)
            if bazi_mod.day_ganzhi(
                    datetime(_dd.year, _dd.month, _dd.day))[0][0] == "庚":
                _cnt += 1
                if _cnt == 3:
                    if _dd == d:
                        out.append("入伏")
                    break
        # R3366（审-P2）：三九~九九落在次年 1-3 月——它们的冬至
        # 在上一年。当年冬至的周期没命中时回溯上一年冬至。
        for _dy in (d.year, d.year - 1):
            _dz = (bazi_mod.term_time(_dy, "冬至")
                   + timedelta(hours=8)).date()
            if not (_dz <= d <= _dz + timedelta(days=80)):
                continue
            for _k in range(0, 9):
                if d == _dz + timedelta(days=9 * _k):
                    out.append("数九·" + "一二三四五六七八九"[_k] + "九")
                    break
            break
    except Exception:
        pass
    return out


# R2349l（R73-P2-9）：水逆历表（公开天文历，station 到 station 日粒度，
# UTC；多源交叉核验 2024–2028）。表外年份静默无状态——不是「永不逆行」。
_MERCURY_RETRO: tuple[tuple[str, str], ...] = (
    ("2024-04-01", "2024-04-25"), ("2024-08-05", "2024-08-28"),
    ("2024-11-25", "2024-12-15"),
    ("2025-03-15", "2025-04-07"), ("2025-07-18", "2025-08-11"),
    ("2025-11-09", "2025-11-29"),
    ("2026-02-26", "2026-03-20"), ("2026-06-29", "2026-07-23"),
    ("2026-10-24", "2026-11-13"),
    ("2027-02-09", "2027-03-03"), ("2027-06-10", "2027-07-04"),
    ("2027-10-07", "2027-10-28"),
    ("2028-01-24", "2028-02-14"), ("2028-05-21", "2028-06-14"),
    ("2028-09-19", "2028-10-11"),
)


# R3502：金星/火星逆行历表（公开天文历 station 到 station 日粒度，
# UTC；Swiss Ephemeris 计算源多源交叉核验 2025–2029）。金逆周期
# 约 18 个月一次、火逆约 26 个月一次——表外年份静默无状态。
_VENUS_RETRO: tuple[tuple[str, str], ...] = (
    ("2025-03-01", "2025-04-12"),
    ("2026-10-03", "2026-11-14"),
    ("2028-05-10", "2028-06-22"),
)
_MARS_RETRO: tuple[tuple[str, str], ...] = (
    ("2024-12-06", "2025-02-23"),
    ("2027-01-10", "2027-04-01"),
    ("2029-02-14", "2029-05-05"),
)


# R2349l（R73-P2-10）：节气民俗一句池——交节日的首页仪式感。
_TERM_FOLK: dict[str, str] = {
    "立春": "打春吃春饼，新一年的开头宜立个小愿望",
    "雨水": "春雨贵如油：喝点热汤，养养脾气",
    "惊蛰": "雷声起万物醒，适合把拖延的事翻出来动一动",
    "春分": "昼夜平分：今天立个蛋讨个好彩头",
    "清明": "踏青扫墓日，也适合把心里的事清一清",
    "谷雨": "雨生百谷：春天最后一站，收住别贪凉",
    "立夏": "立夏称人吃蛋，夏天来了，换个轻快作息",
    "小满": "小满未满刚刚好：凡事留点余地就是圆满",
    "芒种": "忙着收也忙着种，手上的事先收个尾",
    "夏至": "一年最长的白天：吃个面，事情慢慢做",
    "小暑": "小暑不算热，心先静下来就不燥",
    "大暑": "一年最热的时候：冰的别贪，午觉要睡",
    "立秋": "贴秋膘的日子：给身体补点好的",
    "处暑": "暑气到此为止：换季的衣服可以翻出来了",
    "白露": "露从今夜白：早晚添件衣",
    "秋分": "昼夜又平分，收一半放一半，都挺好",
    "寒露": "脚别露了，从今天开始保暖优先",
    "霜降": "霜降吃柿子，甜的软的，养一养脾胃",
    "立冬": "立冬进补日：吃点热的，冬天正式开场",
    "小雪": "初雪将至：家里囤点暖的",
    "大雪": "大雪腌肉季：适合囤东西也适合囤计划",
    "冬至": "冬至大如年：吃饺子/汤圆，早点回家",
    "小寒": "小寒胜大寒，最冷的日子更要把被子和心都捂热",
    "大寒": "大寒到顶点，春就不远了，收尾迎新",
}


def _term_banner(d: date) -> dict:
    """当日交节 → {name, time, tip}；非交节日返回 {}。"""
    try:
        from guji.bazi import TERM_LONGITUDE, term_time
        for name in TERM_LONGITUDE:
            t = term_time(d.year, name) + timedelta(hours=8)
            if t.date() == d:
                return {"name": name, "time": t.strftime("%H:%M"),
                        "tip": _TERM_FOLK.get(name, "")}
    except Exception:
        pass
    return {}


def _liunian(d: date) -> tuple[str, int]:
    """R2349l（R73-P1-14）：流年干支+流年公历年——立春口径（子平法通行），
    立春前算上一岁。R2504（B-2）：回吐调整后的公历年——原来调用方
    拿日历年号配流年干支，立春前 ~35 天句首年号与干支自相矛盾。
    R3314（R3311-中1）：立春当日的差一天——旧比较用「该日零点 <
    交节时刻」，立春当天全天被判回上一年（bazi.compute 以当日午时
    为锚已是新年柱）。日粒度 API 以「交节落在本日内」为换年界，
    与 bazi.compute 同日口径对齐。"""
    y = d.year
    try:
        from guji.bazi import term_time
        from datetime import timedelta as _td
        _lc = term_time(y, "立春") + _td(hours=8)
        if datetime(d.year, d.month, d.day) + _td(days=1) <= _lc:
            y -= 1
    except Exception:
        pass
    from guji.bazi import GAN, ZHI
    return GAN[(y - 4) % 10] + ZHI[(y - 4) % 12], y


def _moon_for(d: date) -> dict:
    """R2349l（R73-P1-8）+ R3451：农历日 → 月相仪式行。

    不发明天文月相，只认农历日——黄历产品的「新月许愿/满月复盘」
    本来按农历节律走。R3451 起全月八相常驻（业界月相应用验证过
    月相日行是留存主钩），初一十五窗口仍挂许愿/复盘 action。
    """
    try:
        from guji import lunar as lunar_mod
        l = lunar_mod.solar_to_lunar(d.year, d.month, d.day)
        if l.get("is_leap"):
            return {}
        ld = l.get("day") or 0
        # R3314（R3311-低）：月相句日盐轮换（同一农历日每年同句会
        # 复读），并挂许愿瓶落点——action 让前端渲「丢进许愿瓶」。
        _rot = d.toordinal()
        if ld == 1:
            return {"phase": "新月", "label": "新月许愿",
                    "glyph": "🌑", "action": "wish",
                    "line": (
                        "今天新月：适合把愿望写下来，老话说「月初起念，月末收成」。",
                        "新月初一：写下来就算数——愿望落到字上比放心里转圈实在。",
                    )[_rot % 2]}
        if ld == 2:
            return {"phase": "新月", "label": "新月次日",
                    "glyph": "🌑", "action": "wish",
                    "line": (
                        "新月刚过，许愿的劲儿还在，想写愿望现在还来得及。",
                        "新月次日：昨天没写下的愿望今天补上，月初的念儿还没散。",
                    )[_rot % 2]}
        if ld == 15:
            return {"phase": "满月", "label": "满月复盘",
                    "glyph": "🌕", "action": "wish_review",
                    "line": (
                        "今天满月：适合回头看看这半个月，上次许的愿望有进展吗？",
                        "月圆十五：愿望不急着都兑现，翻出来看看哪条还在路上。",
                    )[_rot % 2]}
        if ld == 16:
            return {"phase": "满月", "label": "满月次日",
                    "glyph": "🌕", "action": "wish_review",
                    "line": (
                        "满月刚落，收尾盘点的好日子，没收完的尾巴今天清一清。",
                        "满月次日：半个月的努力盘一盘，该收的收、该续的续。",
                    )[_rot % 2]}
        # R3451：八相日行——每一天都有一句月相话（无 action 时行
        # 只读不点）。相位划分按农历日段 [lo,hi]，不求天文精度。
        _tab = [
            (3, 7, "娥眉月", "🌒",
             ("月牙冒尖儿了：想做的事起个头，今天只开个小口。",
              "娥眉月初上：新念头正冒芽，先轻轻记着就好。")),
            (8, 10, "上弦月", "🌓",
             ("上弦月半圆：往上走的日子，适合往前拱一小步。",
              "弦月半满：该使劲的事这两天别松手。")),
            (11, 14, "盈凸月", "🌔",
             ("月亮一天天鼓起来了——攒着的劲儿快圆了。",
              "盈凸月：快到顶的日子，收个尾冲一冲。")),
            (17, 22, "亏凸月", "🌖",
             ("月亮开始慢慢收了——该放的事松一松，不必都扛着。",
              "亏凸月：从满到收，盘点盘点手里这半月。")),
            (23, 25, "下弦月", "🌗",
             ("下弦月挂半边：收拾收拾上半月的尾巴，轻装走。",
              "弦月向西：旧事先清一清，别带进下个月。")),
            (26, 30, "残月", "🌘",
             ("残月将尽：这个月快到头了，歇口气等新月再来。",
              "月末残月：把没做完的轻轻放下，新月再开一页。")),
        ]
        for lo, hi, name, gl, lines in _tab:
            if lo <= ld <= hi:
                # R3452（审-P2-5）：凸月术语不直出——label 换白话，
                # phase 留术语给内部判据。
                _lbl = {"盈凸月": "月亮渐圆",
                        "亏凸月": "月亮渐收"}.get(name, name)
                return {"phase": name, "label": _lbl,
                        "glyph": gl, "action": None,
                        "line": lines[_rot % 2]}
    except Exception:
        pass
    return {}


def _retro_state(
        table: tuple[tuple[str, str], ...], d: date) -> dict:
    """d 这天的逆行状态：{on, day_no, until} / {on:False, next, days_to}。"""
    for s, e in table:
        ds, de = date.fromisoformat(s), date.fromisoformat(e)
        if ds <= d <= de:
            return {"on": True, "day_no": (d - ds).days + 1,
                    "until": e}
        if d < ds:
            return {"on": False, "next": s,
                    "days_to": (ds - d).days}
    return {"on": False, "next": "", "days_to": 0}


def _mercury_state(d: date) -> dict:
    return _retro_state(_MERCURY_RETRO, d)


# R3502：金逆（旧情复盘/审美重置话题）与火逆（行动力慢拍）同构状态。
def _venus_state(d: date) -> dict:
    return _retro_state(_VENUS_RETRO, d)


def _mars_state(d: date) -> dict:
    return _retro_state(_MARS_RETRO, d)


def _week_sky(d: date) -> list:
    """R3601：未来 7 天天象预告——初一/十五节点、逆行起止、节气日。

    全走确定性历表（lunar 农历日/逆行窗表/节气天文算法），
    表外年份/异常日静默略过该项。「下周早知道」行数据源。
    """
    evs = []
    try:
        for i in range(1, 8):
            dd = d + timedelta(days=i)
            lab = ("周" + _WEEKDAY[dd.weekday()] + " " + str(dd.month) +
                   "/" + str(dd.day))
            try:
                m = _moon_for(dd)
                # 只预告初一/十五两个仪式节点（次日不重复列）。
                if m.get("label") in ("新月许愿", "满月复盘"):
                    evs.append({"d": lab, "t": m["glyph"] + m["label"]})
            except Exception:
                pass
            try:
                tn = _term_name_for(dd)
                if tn:
                    evs.append({"d": lab, "t": "🍂 " + tn})
            except Exception:
                pass
            for tbl, nm in ((_MERCURY_RETRO, "水逆"),
                            (_VENUS_RETRO, "金逆"),
                            (_MARS_RETRO, "火逆")):
                for s, e in tbl:
                    if s == dd.isoformat():
                        evs.append({"d": lab, "t": "↩ " + nm + "起"})
                    if e == dd.isoformat():
                        evs.append({"d": lab, "t": "↩ " + nm + "止"})
    except Exception:
        pass
    return evs[:6]


# R2349l（R73-P1-4）：开运色/幸运数——当日日干五行为主轴，确定性可复验。
_LUCKY_COLOR = {"木": "青绿色", "火": "石榴红", "土": "鹅黄色",
              "金": "珍珠白", "水": "雾蓝色"}
_LUCKY_WORD = {"木": "发芽生长", "火": "热乎劲儿", "土": "厚稳托底",
             "金": "干脆利落", "水": "绕得开找得到"}


def _lucky_for(d: date) -> dict:
    """当日开运三件套：日干五行 → 色/意象词/河图幸运数。
    全部确定性派生（同一天同值，可复验）。
    R3314（R3312-P1-3）：num 原是「干支序号 %9+1」的逐日滚动器，
    与当日五行河图数无关也无出处（庚金日河图应 4·9 实给 2）——
    改成与命盘能量卡同祖的河图数口径。"""
    out = {"color": "", "color_word": "", "num": ""}
    try:
        _gz, _idx = _bazi_day_ganzhi(
            datetime(d.year, d.month, d.day, 12))
        _wx = GAN_ELEM.get(_gz[0], "")
        out["color"] = _LUCKY_COLOR.get(_wx, "")
        out["color_word"] = _LUCKY_WORD.get(_wx, "")
        _ht = voice.HETU_NUMBERS.get(_wx, ())
        out["num"] = " · ".join(str(n) for n in _ht)
    except Exception:
        pass
    return out


# R3325：今日穿搭——五行穿衣主流行法（以当日天干五行为基准）。
# 大吉=生我（贵人色）、次吉=同我、平=我克（招财色）、慎用=我生（泄）、
# 忌=克我。确定性派生，随日卡缓存同口径。
_WX_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_WX_GEN_BY = {_v: _k for _k, _v in _WX_SHENG.items()}
_WX_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
_WX_KE_BY = {_v: _k for _k, _v in _WX_KE.items()}
_WX_COLORS = {"木": "青·绿·翠", "火": "红·粉·紫", "土": "黄·棕·咖",
              "金": "白·金·银", "水": "黑·蓝·灰"}
_WX_HEX = {"木": "#6FAD8A", "火": "#D96A5F", "土": "#D9B36C",
           "金": "#E8E2D4", "水": "#5E7FA0"}


def _outfit_for(d: date) -> dict:
    """当日五行穿搭五档：大吉贵人/次吉幸运/平招财/慎用消耗/忌。
    全部确定性派生（同一天同值，可复验）。"""
    try:
        _gz, _idx = _bazi_day_ganzhi(datetime(d.year, d.month, d.day, 12))
        wx = GAN_ELEM.get(_gz[0], "")
        if not wx:
            return {}
        def _tier(tag, el, tip):
            return {"tag": tag, "wx": el, "colors": _WX_COLORS[el],
                    "hex": _WX_HEX[el], "tip": tip}
        return {
            "wx": wx,
            "tiers": [
                _tier("大吉", _WX_GEN_BY[wx], "贵人色：今天的主推，穿上省力"),
                _tier("次吉", wx, "幸运色：和今天同气，合作顺利"),
                _tier("平", _WX_KE[wx], "招财色：要主动点才见效"),
                _tier("慎用", _WX_SHENG[wx], "消耗色：当点缀就好，别主穿"),
                _tier("忌", _WX_KE_BY[wx], "不利色：今天先收进衣柜"),
            ],
        }
    except Exception:
        return {}


def _daily_lunar_str(d: date) -> str:
    """日卡农历锚行「农历八月廿三 · 庚戌日」。
    R3318（审-P1-2）：month_cn 已含「闰」前缀和「月」后缀——
    再拼一次是「八月月廿三」重字（日卡/壁纸/分享物全带）。"""
    try:
        _l2 = lunar.solar_to_lunar(d.year, d.month, d.day)
        _gz2, _i2 = _bazi_day_ganzhi(
            datetime(d.year, d.month, d.day, 12))
        return (f"农历{_l2.get('month_cn','')}{_l2.get('day_cn','')}"
                f" · {_gz2}日")
    except Exception:
        return ""


def _daily_card_for(d: date) -> dict:
    """R3317-G：今日牌——同日全站同一张大阿卡纳（含正/逆位）。
    确定性：seed=YYYYMMDD，牌位=seed%22、位向=seed//22 奇偶，
    与幸运三件套同口径（同日出同牌，不靠 LLM）。"""
    try:
        seed = d.year * 10000 + d.month * 100 + d.day
        n = len(tarot_mod.MAJOR_ARCANA)
        # seed+1→牌+1 是明晃晃的转盘序（今天恶魔明天必高塔）。
        # *7 跳步：gcd(7,22)=1 仍 22 天全覆盖，体感打散。
        name, up_kw, rev_kw, _desc = tarot_mod.MAJOR_ARCANA[(seed * 7) % n]
        # 位向不能再用 seed//22 奇偶——44 天才翻一次，半个月全是正位。
        # seed*31//22 的非整周期翻页，逐日近似随机交替且确定性。
        upright = ((seed * 31 // n) % 2) == 0
        # R3321-P1：meaning 一并下发——前端「牌意」展开不再另发
        # /api/tarot/draw（旧路径与 daily_card 不同 seed 会抽成另一张
        # 牌，且按同 id 覆写把「抽三张」入口抹掉）。
        return {"name": name, "upright": upright,
                "keywords": up_kw if upright else rev_kw,
                "meaning": _desc}
    except Exception:
        return {}


def _term_name_for(d: date) -> str:
    """公历日 d 当天交节的节气名（无 → ''）。term_time 有 lru_cache，
    单日调用近零成本。"""
    try:
        from guji.bazi import TERM_LONGITUDE, term_time
        for _tn in TERM_LONGITUDE:
            if (term_time(d.year, _tn) + timedelta(hours=8)).date() == d:
                return _tn
    except Exception:
        pass
    return ""


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
    # R3366（审-P2）：「节后一天」双口径——带上班/收假语标才走假表
    # 止日+1（「国庆节后第一天上班」）；裸「中秋节后一天」问的是节日
    # 次日，该交给 _abs_or_holiday 的 X+1 口径（此前一律按假止日判）。
    _worky = re.search(r"上班|收假|收心|复工|假期|开工|过完节", msg_n)
    if (_worky and re.search(
            r"(节后|假期后|过完节|收假|收心|假期结束|上班第一天)",
            msg_n)) or (_afm and named and _worky):
        nxt = [r for r in pool if r[2] >= td]
        _afw = ["", "一", "二", "三", "四", "五"][_afn]
        if nxt:
            return nxt[0][2] + timedelta(days=_afn), f"{nxt[0][0]}后第{_afw}天"
        done = [r for r in pool if r[2] < td]
        # R2359（R115-P1-3）：放假表有新鲜度——表外 >60 天的旧档不回，
        # 否则「春节后第一天上班」会拿一年前的复工日当答案。
        if done and (td - done[-1][2]).days <= 60:
            return done[-1][2] + timedelta(days=_afn), f"{done[-1][0]}后第{_afw}天"
    if re.search(r"假期最后一天|最后一天假|假期的尾巴", msg_n):
        live = [r for r in pool if r[1] <= td <= r[2]]
        nxt = [r for r in pool if r[1] > td]
        done = [r for r in pool if r[2] < td]
        # R2359（R115-P1-3）：done 档同样要新鲜度闸。
        tgt = live[0] if live else (nxt[0] if nxt else
                                    (done[-1] if done and
                                     (td - done[-1][2]).days <= 60 else None))
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
        # R2359（R115-P1-1）：年前缀指公历年，农历年下标会差一年
        #（1月~除夕窗）——一律按发生日所在公历年过滤；除夕本就落在
        # 下个公历年，候选放宽到 ly0+3 再按 d.year 收。
        lys = range(ly0 - 3, ly0 + 3)
        for ly in lys:
            try:
                out.append(lunar_mod.lunar_to_solar(ly + 1, 1, 1)
                           - timedelta(days=1))
            except ValueError:
                pass
        if yoff is not None:
            out = [d for d in out if d.year == now.year + yoff]
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
    if name in _SOLAR_TERMS or name in _SOLAR_TERMS_AMBI:
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
        # R2359（R115-P1-1）：同除夕——按公历年过滤。
        lys = range(ly0 - 3, ly0 + 4)
        for ly in lys:
            try:
                out.append(lunar_mod.lunar_to_solar(ly, lm, ld))
            except ValueError:
                pass
        if yoff is not None:
            out = [d for d in out if d.year == now.year + yoff]
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


def _abs_or_holiday(msg: str, now: datetime,
                    _yoff_force: int | None = None):
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
    yoff = (_yoff_force if _yoff_force is not None
            else next((v for w, v in _ypre.items() if w in msg_n), None))
    # R2355（R111-P1-3/P2-1）：显式 4 位年——「2099年12月31号」此前
    # 「年」被忽略就近解到当年同日（说错日比不答更伤）；「2027-02-29」
    # ISO 残片同理。显式年份按那一年解，越出历法表界/日子不存在
    # → None（交「黄历里没有这天」口径，不静默换日）。
    _xy = re.search(r"(?<!\d)(\d{4})\s*年", msg_n) or \
        re.search(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})",
                  msg_n)
    if _xy:
        _yy = int(_xy.group(1))
        if not (YEAR_LO <= _yy <= YEAR_HI):
            return None
        if _xy.re.pattern.endswith("年"):
            _md = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", msg_n)
            if not _md:
                # R2359（R115-P1-2）：显式年+节日/节气名（「2027年春节」）——
                # 剥掉年词走节日/农历通道，yoff 钉到该公历年；解不出才 None。
                _rest = (msg_n[:_xy.start()] + msg_n[_xy.end():]).strip()
                if _rest:
                    _rc = _abs_or_holiday(_rest, now, _yy - now.year)
                    if _rc is not None:
                        return _rc
                return None
            _mm2, _dd2 = int(_md.group(1)), int(_md.group(2))
        else:
            _mm2, _dd2 = int(_xy.group(2)), int(_xy.group(3))
        try:
            _xd = datetime(_yy, _mm2, _dd2, now.hour, now.minute)
        except ValueError:
            return None
        _spn = (msg_n[_xy.start():_md.end()] if _xy.re.pattern.endswith("年")
                else _xy.group(0))
        return _xd, _spn
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
            lys = range(max(1900, ly0 - 3), min(2101, ly0 + 4))
            # 闰月稀疏（1900-2100 间十多年才一闰）——放宽到 ±12 个农历年
            # 并让 leap_month 把守，找真正带这个闰月的年份。
            # R2505（C-1）：leap_month/month_days 对表外年份抛 IndexError
            # （lunar_to_solar 才是 ValueError——except ValueError 接不住），
            # ly0 贴近 2100 的 base= 用户链直接 500。两路 range 一律钳到
            # LUNAR_INFO 表界 [1900, 2101)——表外年本来也产不出候选。
            if is_leap:
                lys = [ly for ly in range(max(1900, ly0 - 12),
                                          min(2101, ly0 + 13))
                       if lunar_mod.leap_month(ly) == md[0]]
            cands = []
            for ly in lys:
                try:
                    cands.append(lunar_mod.lunar_to_solar(ly, *md, is_leap))
                except ValueError:
                    pass
            # R2359（R115-P1-1）：「明年正月初一」按发生日公历年过滤，
            # 农历年下标加 yoff 会差一年（1月~除夕窗）。
            if yoff is not None:
                cands = [d for d in cands if d.year == now.year + yoff]
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
            # R2505（C-1）：month_days 同 IndexError——钳 LUNAR_INFO 表界。
            lys = range(max(1900, ly0 - 3), min(2101, ly0 + 4))
            cands = []
            for ly in lys:
                try:
                    cands.append(lunar_mod.lunar_to_solar(
                        ly, _mm[0], lunar_mod.month_days(ly, _mm[0])))
                except ValueError:
                    pass
            # R2359（R115-P1-1）：同上按公历年过滤。
            if yoff is not None:
                cands = [d for d in cands if d.year == now.year + yoff]
            pick = _nearest_day(cands, now, past)
            if pick:
                _dl, _ln = _day_suffix(msg_n, lme.end())
                return (datetime.combine(pick + timedelta(days=_dl),
                                         now.time()),
                        msg_n[lme.start():lme.end() + _ln])

    for name in sorted(set(_HOLIDAY_SOLAR) | set(_HOLIDAY_LUNAR)
                       | set(_HOLIDAY_NTH) | _SOLAR_TERMS
                       | _SOLAR_TERMS_AMBI
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
        # R3323-P0-2：双关节气词要带语境才作日期解——「大雪纷飞」
        # 不翻页，「大雪那天/大雪节气/节气大雪」翻。
        if w in _SOLAR_TERMS_AMBI:
            # R3330（审-中3）：问日句式补白——「大雪是哪天/什么时候/
            # 几日/几号」此前被双关闸整句静默（after 不是节气语境词）。
            _after = msg_n[idx:idx + 4]
            if not (_after.startswith(("节气", "那天", "当日", "这天",
                                       "那一天", "前后", "是哪天",
                                       "是几号", "什么时候", "几日",
                                       "几号", "何时", "是哪一天"))
                    or msg_n[:widx].endswith("节气")):
                continue
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
        # R2359（R115-P2-5）：段期词段内问锚当前段起日——数九 81 天/
        # 三伏 40 天里「数九/入伏」说的是正在进行的这段，不是明年起日。
        if name in ("入伏", "三伏", "数九", "入九"):
            _span = 40 if name in ("入伏", "三伏") else 81
            _in = [s for s in cands
                   if s <= now.date() < s + timedelta(days=_span)]
            if _in:
                pick = _in[-1]
        if pick:
            _dl, _ln = _day_suffix(msg_n, idx)
            _sp = msg_n[widx:idx + _ln]
            return (datetime.combine(pick + timedelta(days=_dl),
                                     now.time()), _sp or w)

    # R2355（R111-P2-2）：「下下个月」先接——「下下」里的「下个月」
    # 会被下面通配截胡差整一月。基准 = 再下一个月。
    nnm = re.search(r"下下[个個]?月" + _CN_DAY_RE +
                    r"[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if nnm:
        d = _cn_day_int(nnm.group(1))
        _mo2 = now.month + 2
        ny, nmth = now.year + (_mo2 - 1) // 12, (_mo2 - 1) % 12 + 1
        try:
            _dl, _ln = _day_suffix(msg_n, nnm.end())
            return (datetime(ny, nmth, d) + timedelta(days=_dl),
                    msg_n[nnm.start():nnm.end() + _ln])
        except ValueError:
            # 「下下个月31号」而那个月只有 30 天——词命中但日子不存在；
            # 不许 fallthrough 让 nm 把「下个月31号」截胡成另一月。
            return None
    nm = re.search(r"下[个個]月" + _CN_DAY_RE +
                   r"[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if nm:
        d = _cn_day_int(nm.group(1))
        ny, nmth = now.year + (now.month == 12), (now.month % 12) + 1
        try:
            _dl, _ln = _day_suffix(msg_n, nm.end())
            return (datetime(ny, nmth, d) + timedelta(days=_dl),
                    msg_n[nm.start():nm.end() + _ln])
        except ValueError:
            pass
    tm = re.search(r"这[个個]月" + _CN_DAY_RE +
                   r"[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if tm:
        try:
            _dl, _ln = _day_suffix(msg_n, tm.end())
            return (datetime(now.year, now.month, _cn_day_int(tm.group(1)))
                    + timedelta(days=_dl),
                    msg_n[tm.start():tm.end() + _ln])
        except ValueError:
            pass

    pm = re.search(r"上[个個]月" + _CN_DAY_RE +
                   r"[号日]?(?![线楼室幢座栋层院门])", msg_n)
    if pm:
        d = _cn_day_int(pm.group(1))
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
        # R2359（R115-P3-6）：显式月前缀「12月底」——「12」不能被丢，
        # 1 月问时落当月月底是把十二月错读成本月。
        _mex = re.search(r"(?<!\d)(\d{1,2})\s*月(?:底|末)", msg_n)
        cands = []
        if _mex:
            _mm3 = int(_mex.group(1))
            if 1 <= _mm3 <= 12:
                for _yy3 in range(now.year - 1, now.year + 2):
                    cands.append(date(_yy3, _mm3,
                                      calendar.monthrange(_yy3, _mm3)[1]))
        else:
            cands = [date(now.year + (now.month == 12), (now.month % 12) + 1,
                          calendar.monthrange(now.year + (now.month == 12),
                                              (now.month % 12) + 1)[1]),
                     date(now.year, now.month,
                          calendar.monthrange(now.year, now.month)[1])]
        if yoff is not None:
            cands = [dd for dd in cands if dd.year == now.year + yoff]
        pick = _nearest_day(cands, now, past)
        if pick:
            if _mex:
                _dl, _ln = _day_suffix(msg_n, _mex.end())
                return (datetime.combine(pick + timedelta(days=_dl),
                                         now.time()),
                        msg_n[_mex.start():_mex.end() + _ln])
            _w0 = msg_n.find("月底") if "月底" in msg_n else msg_n.find("月末")
            _dl, _ln = _day_suffix(msg_n, _w0 + 2)
            return (datetime.combine(pick + timedelta(days=_dl), now.time()),
                    msg_n[_w0:_w0 + 2 + _ln])
    # 「月初」须排除农历日语境——「五月初一」里的「月初」不是月初。
    _yc = re.search(r"月初(?!一|二|两|三|四|五|六|七|八|九|十|廿|\d)", msg_n)
    if _yc:
        # R2359（R115-P3-6）：「12月初」同样不能丢显式月。
        _myx = re.search(r"(?<!\d)(\d{1,2})\s*月初", msg_n)
        if _myx and 1 <= int(_myx.group(1)) <= 12:
            cands = [date(_yy4, int(_myx.group(1)), 1)
                     for _yy4 in range(now.year - 1, now.year + 2)]
        else:
            cands = [date(now.year + (now.month == 12), (now.month % 12) + 1, 1),
                     date(now.year, now.month, 1)]
        if yoff is not None:
            cands = [dd for dd in cands if dd.year == now.year + yoff]
        pick = _nearest_day(cands, now, past)
        if pick:
            if _myx and 1 <= int(_myx.group(1)) <= 12:
                _dl, _ln = _day_suffix(msg_n, _myx.end())
                return (datetime.combine(pick + timedelta(days=_dl),
                                         now.time()),
                        msg_n[_myx.start():_myx.end() + _ln])
            _w0 = _yc.start()
            _dl, _ln = _day_suffix(msg_n, _w0 + 2)
            return (datetime.combine(pick + timedelta(days=_dl), now.time()),
                    msg_n[_w0:_w0 + 2 + _ln])

    # 裸「D号/D日」：防「3号线/25号楼/8号院」误命中——后接线路/楼栋字跳过。
    bd = re.search(r"(?<![\d月/\-一二两三四五六七八九十])" + _CN_DAY_RE +
                   r"\s*[号日](?![\d日线楼室幢座栋层院门])", msg_n)
    if bd:
        d = _cn_day_int(bd.group(1))
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
    # R2349q续：个/個 可选字（这个周五同锚）。
    _bw = re.search(r"(本|这|這)个?(?:周|週|礼拜|禮拜)([一二三四五六日天])|"
                    r"(本|这|這)個(?:周|週|礼拜|禮拜)([一二三四五六日天])", msg)
    if _bw:
        wd = _wd_idx(_bw.group(2) or _bw.group(4))
        return now + timedelta(days=wd - now.weekday()), _bw.group(0)
    for anchor in ("本周", "这周", "本週", "這週", "这週", "這周"):
        if anchor in msg:
            idx = msg.find(anchor) + len(anchor)
            if idx < len(msg) and msg[idx] in _WEEKDAY:
                wd = _wd_idx(msg[idx])
                return now + timedelta(days=wd - now.weekday()), msg[msg.find(anchor):idx + 1]
            break  # 「本周」无曜日字 → 不落下面 周末/今天 兜底，交给默认今天
    # R229y续：「下下周X/下下周末」——"下下周一"自身含"下周"，会被下面
    # 的「下周」通配截胡按下周判（差整 7 天）。先接住：以「再下一个周一」
    # 为基准。R2349q续：「下下个周X」的 个/個 为可选字。
    _nn = re.search(r"下下个?(?:周|週|礼拜|禮拜|星期)末|下下個(?:周|週|礼拜|禮拜|星期)末", msg)
    if _nn:
        nn_mon = now + timedelta(days=(14 - now.weekday()))
        return nn_mon + timedelta(days=5), _nn.group(0)
    _nnw = re.search(r"下下个?(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])|"
                     r"下下個(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])", msg)
    if _nnw:
        nn_mon = now + timedelta(days=(14 - now.weekday()))
        wd = _wd_idx(_nnw.group(1) or _nnw.group(2))
        return nn_mon + timedelta(days=wd), _nnw.group(0)
    _nnb = re.search(r"下下个?(?:周|週|礼拜|禮拜|星期)|下下個(?:周|週|礼拜|禮拜|星期)", msg)
    if _nnb:
        nn_mon = now + timedelta(days=(14 - now.weekday()))
        return nn_mon, _nnb.group(0)
    # R229e：「下周末/下週末」必须先于「下周」通配——否则「末」非曜日字，
    # 落进通用分支被吃成下周一，而用户说的是下周的周六。
    _nw = re.search(r"下个?(?:周|週|礼拜|禮拜|星期)末|下個(?:周|週|礼拜|禮拜|星期)末", msg)
    if _nw:
        next_mon = now + timedelta(days=(7 - now.weekday()))
        return next_mon + timedelta(days=5), _nw.group(0)
    # 下周X / 下礼拜X：以下个周一为基准的 X 曜日
    _nx = re.search(r"下个?(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])|"
                    r"下個(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])", msg)
    if _nx:
        next_mon = now + timedelta(days=(7 - now.weekday()))
        wd = _wd_idx(_nx.group(1) or _nx.group(2))
        return next_mon + timedelta(days=wd), _nx.group(0)
    _nb = re.search(r"下个?(?:周|週|礼拜|禮拜|星期)|下個(?:周|週|礼拜|禮拜|星期)", msg)
    if _nb:
        # 「下周」没跟曜日——按下个周一算
        return now + timedelta(days=(7 - now.weekday())), _nb.group(0)
    # R2349q（R82-P0-1）：「上周X/上礼拜X/上星期X」此前无锚点——
    # 裸曜日正则把它锚到未来的同名日（周一问「上周六」被按下周六判，
    # 过去日保护完全绕过）。基准=本周一-7d。续：个/個 为可选字。
    _lw = re.search(r"上个?(?:周|週|礼拜|禮拜|星期)末|上個(?:周|週|礼拜|禮拜|星期)末", msg)
    if _lw:
        last_mon = now - timedelta(days=now.weekday() + 7)
        return last_mon + timedelta(days=5), _lw.group(0)
    _lx = re.search(r"上个?(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])|"
                    r"上個(?:周|週|礼拜|禮拜|星期)([一二三四五六日天])", msg)
    if _lx:
        last_mon = now - timedelta(days=now.weekday() + 7)
        wd = _wd_idx(_lx.group(1) or _lx.group(2))
        return last_mon + timedelta(days=wd), _lx.group(0)
    _lb = re.search(r"上个?(?:周|週|礼拜|禮拜|星期)|上個(?:周|週|礼拜|禮拜|星期)", msg)
    if _lb:
        last_mon = now - timedelta(days=now.weekday() + 7)
        return last_mon, _lb.group(0)
    # R2349q（R82-P0-1 连带）：「上个月/上月」——上月 1 号为代表日。
    if re.search(r"上个月|上個月|上月", msg):
        _pm = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        return _pm, "上个月"
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
    # R3230：数字相对日「三天后/一周后/三个月前/半个月后」——此前静默
    # 按今天判（R228r 同类伤：用户拿今天的判词安排将来的事）。
    # 月单位必须带「个」——「十月后」是「十月以后」不是十个月后；
    # 半月按 15 天折算；放「最近/近期」兜底之前，上文各特则优先。
    _dr = re.search(
        r"(?:过|過)?(半|[0-9]{1,3}|[一二两三四五六七八九兩]?十"
        r"[一二三四五六七八九]?|[一二两三四五六七八九兩]+)"
        r"[个個]?(天|日|周|週|星期|礼拜|禮拜)(后|後|前)|"
        r"(?:过|過)?(半|[0-9]{1,2}|[一二两三四五六七八九兩]?十"
        r"[一二三四五六七八九]?|[一二两三四五六七八九兩]+)"
        r"[个個](月)(后|後|前)", msg)
    if _dr:
        _num_s = _dr.group(1) or _dr.group(4)
        _unit = _dr.group(2) or _dr.group(5)
        _d2 = _dr.group(3) or _dr.group(6)
        _sgn = -1 if _d2 == "前" else 1
        if _unit == "月":
            _mo_n = _cn_num(_num_s) if _num_s != "半" else 0
            if _mo_n:
                return _add_months(now, _sgn * _mo_n), _dr.group(0)
            _days = 15 * _sgn                # 半个月 ≈ 15 天
        elif _num_s == "半":
            _days = 0                        # 半天后 → 同日
        else:
            _days = _cn_num(_num_s) * _sgn
            if _unit not in ("天", "日"):
                _days *= 7
        return now + timedelta(days=_days), _dr.group(0)
    # 「过N天/过N周」无方向字同义——过两天已在上面特则，这里兜长尾。
    _dr2 = re.search(
        r"(?:过|過)([0-9]{1,3}|[一二两三四五六七八九兩]?十"
        r"[一二三四五六七八九]?|[一二两三四五六七八九兩]+)"
        r"[个個]?(天|日|周|週|星期|礼拜|禮拜)", msg)
    if _dr2:
        _nu2 = _cn_num(_dr2.group(1))
        if _nu2:
            if _dr2.group(2) not in ("天", "日"):
                _nu2 *= 7
            return now + timedelta(days=_nu2), _dr2.group(0)
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
    now = now or _now_cn()
    q = (q or "").strip()[:80]
    if not q:
        return {"date": None, "spoken": "", "invalid": ""}
    dt, spoken = _hl_day_part(q, now)
    # R2349k（R72-A3）：「下个月31号」这种「词命中但日子不存在」此前
    # 静默回落显示日——单独给 invalid 信号让前端说人话提示。
    # R2355（R111-P2-2）：「下下个月31号」的 下下 也要算——原来正则
    # 从第二个「下」起匹配成「下个月」，报错月差一整月。
    _mm = re.search(r"(下下|下|上|这|本)个?月\s*" + _CN_DAY_RE +
                    r"\s*[号日]", _t2s(q))
    if _mm and spoken == "今天":
        _mo = {"下下": 2, "下": 1, "上": -1, "这": 0, "本": 0}[_mm.group(1)]
        _yy = now.year + (now.month + _mo - 1) // 12
        _mth = (now.month + _mo - 1) % 12 + 1
        _dd = _cn_day_int(_mm.group(2))
        import calendar as _cal
        if _dd > _cal.monthrange(_yy, _mth)[1]:
            return {"date": None, "spoken": "",
                    "invalid": f"{_mm.group(1)}个月没有 {_dd} 号哦。"
                               f"它最多到 {_cal.monthrange(_yy, _mth)[1]} 号"}  # 常驻键（契约探针）
    # 「无日期词」与「显式说今天」在返回值上不可分——spoken=='今天'
    # 且消息里没有今天系词才算没解出。
    if spoken == "今天" and not any(
            w in q for w in ("今天", "今日", "今晚", "今夜")):
        # R2355（R111-P1-2/P2-3）：「说过但解不出」的日期词（农历13月/
        # 星期八/32号/越界年号）——invalid 如实说没有这天；继续静默
        # 回退显示日会把旧判定当新答案贴屏。
        if re.search(
                r"农历|阴历|旧历|闰|農曆|陰曆|舊曆|閏|\d{4}|"
                r"星期|礼拜|禮拜|周天|周日|周[一二三四五六八]|"
                # R2359（R115-P1-3/P3-6）：放假表界外词与裸农历月/
                # 过年前/段期词同属「说过但解不出」——invalid 如实说，
                # 别静默按今天判。
                r"放假|假期|收假|调班|节后|年后|过年前|"
                r"正月|腊月|冬月|数九|入伏|三伏|梅雨季|"
                # R3323-P0-2：双关节气无语境解不出时同样如实说，
                # 不许静默拿显示日判（「大寒开业吗」→ invalid）。
                r"大寒|小寒|大雪|小雪|小满|"
                r"[0-9]{1,2}\s*[号日]", q):
            return {"date": None, "spoken": "",
                    "invalid": "这个日子黄历里没有哦。"
                               "换个说法或换个日子再试试～"}
        # R3366（审-低）：无前缀中文「M月D」（八月十五/十月十五）——
        # 农历阳历都可能，猜哪边都可能答错，如实说拿不准。
        if re.search(
                r"[一二两三四五六七八九十]{1,2}月"
                r"[初廿一二三四五六七八九十]{1,3}[日号]?", q):
            return {"date": None, "spoken": "",
                    "invalid": "这个写法我拿不准是农历还是阳历——"
                               "说「农历八月十五」或「8月15号」我都认"}
        return {"date": None, "spoken": "", "invalid": ""}
    return {"date": dt.date().isoformat(), "spoken": spoken,
            "invalid": ""}


def _hl_next_yi_days(dt: datetime, terms: list[str],
                   span: int = 45, limit: int = 4) -> list[str]:
    """[dt, dt+span) 内宜任一规范词的日子（并集），返回 "M/D（周X）" 列表。

    R3315（审-P1-1）：原只给 "10/13"——模型复述时会自创「这周六/本周四」
    贴错周归属（实测 10/13 周二被念成「这周六」）。星期注记随事实下发，
    模型照念即对，system 侧另钉「不许自补周归属」。"""
    _WD = "一二三四五六日"
    out = []
    # R229z续8：走 find_good_days（单日循环一次判定全部词，R8 P1-1；
    # 含宜∩忌双标日剔除 R228m）。
    for q in huangli_mod.find_good_days(dt, dt + timedelta(days=span - 1),
                                        terms):
        try:
            _dd = datetime.strptime(str(q["date"]), "%Y-%m-%d")
            out.append(f"{_dd.month}/{_dd.day}（周{_WD[_dd.weekday()]}）")
        except (ValueError, TypeError, KeyError):
            out.append(str(q.get("date", "?")))
    return out[:limit]


def _hl_bad_days(dt: datetime, terms: list[str],
                 span: int = 45, limit: int = 6) -> list[str]:
    """[dt, dt+span) 内「忌侧写了这事」的日子——ji-only 事项避让榜。"""
    _WD = "一二三四五六日"
    out = []
    for q in huangli_mod.find_bad_days(dt, dt + timedelta(days=span - 1),
                                     terms):
        try:
            _dd = datetime.strptime(str(q["date"]), "%Y-%m-%d")
            out.append(f"{_dd.month}/{_dd.day}（周{_WD[_dd.weekday()]}）")
        except (ValueError, TypeError, KeyError):
            out.append(str(q.get("date", "?")))
    return out[:limit]


# R230t（R32-P1-9）：每条聊天消息都过事项词表+忌/中性时扫 45 天吉日——
# 结果只随（归一化消息, 当日）变。同日重复问法直接命中缓存。
_CHAT_FACTS_CACHE: dict = {}


# R2400（R123-P1-1/P1-4）：会话级日期/事项锚——「明天适合出行吗」→「那搬家呢」
# 沿用上一句说的日子按明天判（原按今天注入错误宜忌）；「那后天呢」
# 沿用上一句问的事项按出行判（原降级成原始宜忌总表）。
# 只在内存，随进程生灭；TTL 内才算同一段对话。
_CHAT_CTX: dict = {}
_CHAT_CTX_TTL = 1800   # 30 分钟


def _chat_ctx_get(sid: str | None) -> dict | None:
    if not sid:
        return None
    ent = _CHAT_CTX.get(sid)
    if ent and time.monotonic() - ent[0] < _CHAT_CTX_TTL:
        # R2524（审-LLM-P2-6）：读即刷新——锚寿命对齐会话寿命（会话
        # 每轮 updated 刷新，锚此前只在产出判定时写：判完聊 25 分钟
        # 闲话再问「那后天呢」，锚先死、会话还活着 → 追问降级成泛化
        # 判定）。命中的锚挪到末尾同步逐出序（真 LRU——普通 dict
        # 无 move_to_end，pop+重插等价）。
        _CHAT_CTX[sid] = (time.monotonic(), ent[1])
        _CHAT_CTX[sid] = _CHAT_CTX.pop(sid)
        return ent[1]
    return None


def _chat_ctx_put(sid: str | None, ctx: dict) -> None:
    if not sid:
        return
    # R2524：同 sid 重写先弹再插——dict 赋值不换插入序，老 sid 会
    # 按最初写入位被「最旧」误逐（伪 LRU bug）。
    _CHAT_CTX.pop(sid, None)
    if len(_CHAT_CTX) >= 512:
        # R2400（R128-P2-5）：全局清空会把所有在线会话的锚一起打飞——
        # 按写入序逐出最旧一条（dict 保序）。
        try:
            _CHAT_CTX.pop(next(iter(_CHAT_CTX)))
        except StopIteration:
            pass
    _CHAT_CTX[sid] = (time.monotonic(), ctx)


def chat_huangli_facts(message: str, now: datetime | None = None,
                       session_id: str | None = None) -> list[str]:
    """小满聊天的黄历事实供给：先把「适不适合」算成判定再交给 LLM。

    消息提到黄历事项词（口语词或规范词）→ 当日宜忌 + 判定 + 近期吉日；
    只泛问黄历（「今天宜做什么」「看看黄历」）→ 当日宜忌 + 中性口径说明；
    都不沾 → []（调用方原样透传，零扰动）。
    """
    now = now or _now_cn()
    # R230v（R34-#24）：键含原文指纹——此前 [:200] 截断，两条 200 字
    # 前缀相同的同日长消息会串事实行（概率极低但语义错）。
    _msg_norm = _t2s((message or "").strip())
    # R2400：锚是输入的一部分——不同锚态下同一消息产出不同事实行，
    # 缓存键必须带上生效锚，否则跨会话串味/同会话锚变后吃旧事实。
    _anchor = _chat_ctx_get(session_id)
    _ck = (_msg_norm[:200] + "#" + hashlib.sha1(
        _msg_norm.encode("utf-8")).hexdigest()[:12],
           now.date().isoformat(),
           (_anchor["dt"], _anchor["scene"]) if _anchor else None)
    # R2359（R114-P3-3）：get 原子取值——in 检查与 [] 取值之间另一线程
    # 的 clear() 落进来会 KeyError→task failed→用户看到「没接住」。
    _hit = _CHAT_FACTS_CACHE.get(_ck)
    if _hit is not None:
        # R2400（R128-P0-1）：记锚是副作用，不随 facts 一起被跳过——
        # 命中也要回放写锚（键已含锚态，存下的 ctx 直接放回原语义）。
        _f_hit, _c_hit = _hit
        if _f_hit and _c_hit:
            _chat_ctx_put(session_id, dict(_c_hit))
        return list(_f_hit)
    _ctx_out: dict = {}
    # R2400（R135-P2-8）：危机消息根本不该跑判定计算——chat() 先走
    # 转介回复，verdicts 不落档；facts 本体是浪费。提前短路（不写锚
    # 语义已由「空 facts 不写锚」覆盖）。
    if llm_polish._is_crisis(message or ""):
        _ctx_out["qk"] = "crisis"
        facts = []
    else:
        facts = _chat_facts_inner(message, now, _anchor, _ctx_out)
    # R2400（R128-P1-2/P2-4）：记锚只认判定/找日型供给——泛问/叙事
    # 插话（「我昨天去了医院」「今天天气怎样」）覆写日期锚会把下一问
    # 打飞；不存在日（badday）与危机拒答（crisis）根本不写。
    if facts and _ctx_out and _ctx_out.get("qk") not in ("badday", "crisis"):
        # 非判定型供给（泛问总表/生日提示）不改写日期锚——沿用旧锚
        # 的 dt/spoken；场景侧仍按「没新场景就沿用」合并。
        if _ctx_out.get("qk") not in ("scene", "findday") and _anchor \
                and _anchor.get("dt"):
            _ctx_out["dt"] = _anchor["dt"]
            _ctx_out["spoken"] = _anchor["spoken"]
        # R2400（R126-P2-5）：无场景插话（「今天天气怎样」这类泛问）
        # 记锚时 scene=None 会把事项锚清掉，下一问「那后天呢」接不回
        # 上一件事——新锚没事项时沿用旧锚的场景。
        if _ctx_out.get("scene") is None and _anchor \
                and _anchor.get("scene"):
            _ctx_out["scene"] = _anchor["scene"]
            _ctx_out["terms"] = list(_anchor.get("terms") or [])
        _chat_ctx_put(session_id, _ctx_out)
    if len(_CHAT_FACTS_CACHE) >= 512:
        _CHAT_FACTS_CACHE.clear()   # 键带日期，粗清即够
    _CHAT_FACTS_CACHE[_ck] = (
        list(facts),
        dict(_ctx_out) if (facts and _ctx_out
                         and _ctx_out.get("qk") not in ("badday", "crisis"))
        else None)
    return list(facts)


_BIRTHDAY_FACT_RE = re.compile(r"^生日[:：]\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})")
# R3126（specs/013-P2）：TA 的生日同款展开——partner 档案（合婚留下的
# me:partner）进 chat 后服务端确定性展开日主/星座，小满手里有 TA 的盘。
_BIRTHDAY_PARTNER_RE = re.compile(
    r"^TA的生日[:：]\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})")


# R3124b（specs/012-P0）：判词升格权威信道——结果快照服务端缓存。
# 客户端 facts 只是「话题参考」（可伪造，降权框），聊天要想跟小满
# 口径一致，必须让判词走权威道。做法：各测算端点出响应时把整份
# JSON 按随机 ref 存进内存缓存，前端聊天带上 ref，服务端从自己的
# 缓存里取真响应提取判词层——小满收到的就是卡面那句原话，伪造
# ref 只能拿到 404 等价空集，伪造内容进不来。
import threading as _threading
import secrets as _secrets
from collections import OrderedDict as _OrderedDict

_RESULT_LOCK = _threading.Lock()
_RESULT_CACHE: "_OrderedDict[str, tuple[float, str, dict]]" = _OrderedDict()
_RESULT_TTL = 7200          # 2h——聊这件事通常紧跟看卡
_RESULT_MAX = 256


def _stash_result(view: str, out: dict) -> str:
    """结果落缓存，返回 ref。只存引用不改造响应内容。"""
    ref = _secrets.token_urlsafe(9)
    now = time.time()
    with _RESULT_LOCK:
        _RESULT_CACHE[ref] = (now, view, out)
        # 过期先清，再按 LRU 逐到上限
        for _k in [k for k, (t, _v, _j) in _RESULT_CACHE.items()
                   if now - t > _RESULT_TTL]:
            _RESULT_CACHE.pop(_k, None)
        while len(_RESULT_CACHE) > _RESULT_MAX:
            _RESULT_CACHE.popitem(last=False)
    return ref


def _pop_result(ref: str | None) -> tuple[str, dict] | tuple[None, None]:
    """ref 查缓存。命中即续期（移到队尾）；miss/过期 → (None,None)。"""
    if not ref or not isinstance(ref, str) or len(ref) > 40:
        return None, None
    with _RESULT_LOCK:
        ent = _RESULT_CACHE.get(ref)
        if not ent:
            return None, None
        ts, view, j = ent
        if time.time() - ts > _RESULT_TTL:
            _RESULT_CACHE.pop(ref, None)
            return None, None
        _RESULT_CACHE.move_to_end(ref)
        return view, j


def chat_dream_facts(message: str) -> list[str]:
    """小满聊天的解梦册子供给（R3178）：消息里出现「梦见/梦到/
    做梦/昨晚梦」类词时，把写死词库的象征口径注成参考事实——
    不进 verdict 权威信道（梦册是参考不是判定），语义上更像
    「我查了册子」而不是「我算了命」。
    """
    _n = _t2s((message or ""))
    # 触发词在 _t2s 归一化后的简体面上比对——繁体/粤语口径
    # （夢見/惡夢/發夢）已被表转成简体等价，不用再备两份。
    if not any(k in _n for k in ("梦见", "梦到", "做梦", "梦里",
                                 "昨晚梦", "晚上梦", "有个梦",
                                 "我的梦", "梦过", "噩梦", "发梦",
                                 "做了个梦", "了个梦", "做了梦",
                                 "睡梦", "梦境", "梦中")):
        return []
    r = dream_mod.interpret_dream(_n)
    if not r.get("matched"):
        # 册子没对上也不空跑——给小满一条口径绳，防她自由发挥成预言。
        return ["她在讲一个梦，册子没对上：先听她说最清楚的画面，"
                "梦是情绪回声不是预言，别当判词念"]
    facts = []
    for s in (r.get("symbols") or [])[:2]:
        facts.append("解梦册子·{}：老话口径「{}」；回声读法「{}」".format(
            s.get("name"), s.get("trad"), s.get("echo")))
    facts.append("解梦口径：梦是情绪的回声不是预言，陪她聊心事，"
                 "别当判词念，更别吓人")
    return facts


# R3352（审-高）：明星名命中——铺子自己的 celeb.json 公开生日口径
# 直接注入，模型不用凭记忆答（答错会和选择器打架），顺带送合盘路标。
_CELEB_LIST: list[dict] | None = None


def _celeb_list() -> list[dict]:
    global _CELEB_LIST
    if _CELEB_LIST is None:
        try:
            _CELEB_LIST = json.loads(
                (Path(__file__).parent / "static" / "celeb.json")
                .read_text(encoding="utf-8"))
        except Exception:
            _CELEB_LIST = []
    return _CELEB_LIST


# R3195：路标从纯文字升级可点按钮——每条带 (facts行, 视图键, 按钮文案, 锚点)，
# /api/chat 响应附 action 给前端渲染跳转 chip。锚点=页内落点（折叠 details
# 名/id），前端点击后开详情+滚到门口（R3352「到街区没送到门口」修复）。
_CHAT_ACTIONS = [
    # R3370-P1-2：万圣营销窗（10/29–11/1）词族挂限定入口——
    # 此前「万圣节/万圣节快乐/trick or treat」全无路标，trQH
    # 限定卡在聊里零曝光。窗口外被 _chat_action 跳过落塔罗族。
    (("万圣节", "万圣夜", "trick or treat", "不给糖", "南瓜灯"),
     "她在万圣节点上——铺子里有万圣夜限定：塔罗页有「🎃 万圣夜"
     "限定」卡，能抽「那件她一直不敢问的事」，让她去那儿抽，"
     "抽完回来接着聊",
     "tarot", "🎃 去抽万圣夜限定", "trQH"),
    # R3435：圣诞心愿窗（12/20–12/25）词族挂限定入口——「圣诞
    # 节/平安夜/圣诞树/圣诞愿望」原无路标。窗口外落塔罗族。
    (("圣诞节", "平安夜", "圣诞快乐", "merry christmas",
      "圣诞树", "圣诞愿望", "圣诞心愿"),
     "她在圣诞心愿窗上——铺子里有圣诞心愿限定：塔罗页有「🎄 "
     "圣诞心愿限定」卡，默念心愿翻一张看它怎么来，让她去那儿"
     "抽，抽完回来接着聊",
     "tarot", "🎄 去抽圣诞心愿", "trQX"),
    # R3370-P2-8：「占卜」是塔罗的高频自然说法（「想占卜」
    # 「占卜一下感情」），此前全无路标。
    (("塔罗", "抽牌", "抽张牌", "抽一张", "抽个牌", "帮我抽",
      "翻张牌", "翻翻牌", "占卜"),
     "她想抽塔罗，铺子里有真入口：首页「塔罗」卡能真抽，"
     "让她去那儿抽，抽完回来接着聊；别在聊里替她假抽",
     "tarot", "🃏 去塔罗抽一把", None),
    (("起卦", "起个卦", "摇卦", "摇个卦", "算卦", "算一卦", "算个卦",
      "打个卦", "卜卦", "卜一卦", "六爻", "掷硬币算",
      # R3418-P1-4：「了/一」夹字形态——起了个卦/摇了一卦是
      # 最原生说法之一，原子串表零命中。
      "起了个卦", "起了一卦", "起了卦", "摇了一卦", "摇一卦",
      "卜了一卦", "算了一卦", "打了个卦"),
     "她想摇卦，铺子里有真入口：首页「六爻」卡能真摇，"
     "让她去那儿摇，出卦回来接着聊；别在聊里替她假断",
     "liuyao", "🪙 去六爻摇一卦", None),
    # R3352（审-高）：明星合盘词族——「合盘」裸词/明星/偶像此前全漏，
    # 「我和王嘉尔八字合吗」两头不沾（hehun 词无合盘、八字特例要动作词）。
    # R3356（审-中）：通用合婚词此前也锚 celeb——chip 写着「去测合盘」
    # 却把普通用户推进明星选择器。拆两族：通用词落 hehun 主表单
    # （anchor=None），只有明星向词族才进 celeb 抽屉。
    (("明星合", "和明星", "偶像", "爱豆"),
     "她想和明星合盘：合盘页里有「✨ 和明星合盘」选择器——挑偶像"
     "自动填公开生日，输她自己的生日就出合盘；看完回来接着聊",
     "hehun", "✨ 去和明星合盘", "celeb"),
    (("合婚", "合不合", "我和他的星", "星座合", "看看合盘", "合盘",
      "测测我们",
      # R3418-P2-5：「合个盘」夹「个」字——不含「合盘」子串也无
      # bazi 动作词，此前两头不沾。
      "合个盘", "合一盘"),
     "她想看合盘，铺子里有真入口：首页「合盘」卡输两人生日"
     "出真合盘，里面还有「✨ 和明星合盘」选择器——挑偶像自动填"
     "公开生日；看完回来接着聊",
     "hehun", "💞 去测合盘", None),
    # R3381：默契挑战词族——「懂不懂我」「测默契」「灵魂搭子」
    # 此前无路标。玩的是 hash 邀请链：答 5 题→发链→对方答完
    # 自动对分可晒图。
    (("默契", "懂不懂我", "有多懂", "灵魂搭子", "测测他懂", "了解程度"),
     "她想玩默契挑战：铺子里有「🥤 默契挑战」卡——答 5 题出一封"
     "挑战书链接发给朋友，对方答完自动算默契分还能晒图；"
     "让她去那儿出题，回来接着聊",
     "mochi", "🥤 去出默契题", None),
    (("起名字", "取名字", "起个名", "取名", "改名字"),
     "她想起名，铺子里有真入口：首页「起名」卡能出"
     "候选名单，挑完回来接着聊",
     "qiming", "📛 去起名看看", None),
    # R3388：每日一签路标——观音灵签百签真本。求签/抽签/灵签词族。
    # 「今日签」已属 home 日签族（在上面），这里收的是「求一支签」
    # 动作语义——心有所问才摇签，与看日签是两个意图。
    (("求签", "抽签", "灵签", "观音签", "每日一签", "求一签", "求一支签",
      "摇一签", "抽支签", "求了支签", "一支签", "摇签", "求支签",
      # R3418-P1-4：「个/了」夹字形态。P1-3+P2-3：福签（新春窗）
      # 与桃花签（双十一窗）——窗内高频词，窗外落 qian 主卡无错。
      "抽个签", "求了个签", "求了一支签", "摇了支签", "抽了支签",
      "福签", "新春签", "新年签", "桃花签"),
     "她想求一支签，铺子里有真入口：首页宫格「每日一签」卡是观音灵签"
     "百签真本——默念想问的事摇一支，今天的签不会变，签面可晒图；"
     "让她去那儿摇，抽完回来接着聊签上怎么说",
     "qian", "🎋 去摇今日签", None),
    # R3394：答案之书路标——「书/翻一页/给句准话」族。与 oracle 分开：
    # oracle 是掷筊出吉凶，答案之书是翻页出一句话+提示+小动作。
    (("答案之书", "翻书", "翻一页", "书上", "给句准话", "给句答案",
      "给个答案", "答案在哪", "听书的", "翻到一页"),
     "她想翻答案之书，铺子里有真入口：首页宫格「答案之书」卡——"
     "心里默念问题翻一页，出一句答案+一句提示+一个小动作，"
     "页可晒图；让她去那儿翻，翻完回来接着聊那句什么意思",
     "ansb", "📖 去翻一页", None),
    # R3424：敲敲木鱼——解压敲击词族。功德/木鱼/静不下这类自然
    # 说法此前全无路标；木鱼是真能敲的入口，别在聊里替她假敲。
    # 注：「心烦/烦死了」含「烦」子串归前面心情罐族管（先中先得），
    # 不倒灌进木鱼——想倒情绪进罐子、想敲压进木鱼，分工成立。
    (("敲木鱼", "敲敲木鱼", "敲一下木鱼", "电子木鱼", "功德",
      "积功德", "攒功德", "静不下", "静不下来", "心里乱", "解压"),
     "她心里烦想静一静，铺子里有真入口：首页宫格「敲敲木鱼」卡能"
     "真敲——点木鱼一下一声，攒「心安」还有全铺子共敲数；"
     "让她去那儿敲几下，敲完回来接着聊",
     "muyu", "🪵 去敲敲木鱼", None),
    # R3418-P2-2：星座/星盘路标——该客群最熟的入口之一此前零词。
    # 顺序：必须在「今日运势」族前面——「天蝎座今日运势」带
    # 今日运势子串，后置会被日签族先吃掉。
    (("星座", "十二星座", "星盘", "星座速配", "速配", "天蝎座",
      "双鱼座", "处女座", "狮子座", "白羊座", "摩羯座", "金牛座",
      "双子座", "巨蟹座", "天秤座", "水瓶座", "射手座"),
     "她问星座，铺子里有真入口：首页「星座速配」卡能查今日星座"
     "运势、打星座分数、还有星座配对；让她去那儿看，看完回来聊",
     "xingzuo", "♈ 去看星座", None),
    (("今日运势", "每日运势", "今日签", "看看今天运势"),
     "她问今日运势，铺子里有真入口：首页日签卡每天"
     "更新，看完回来接着聊",
     "home", "☀️ 看今日日签", None),
    # R3331（审-高）：壁纸路标——模型此前答「我这儿没有开运壁纸，
    # 去小红书找」把自家人导外流。首页日签卡下「开运壁纸」按钮
    # 每天出一张带幸运色+日签的图。
    (("开运壁纸", "壁纸", "换壁纸", "幸运壁纸", "每日壁纸", "开运图",
      "幸运色"),
     "她想换开运壁纸，铺子里有真入口：首页日签卡下面有"
     "「开运壁纸」按钮，每天一张带幸运色和日签的图，"
     "让她去那儿点，做好回来接着聊；别把她导去别处找",
     "home", "🖼️ 去换开运壁纸", None),
    # R3336：纠结路标——要不要/去不去/纠结类问句给掷筊真入口。
    # R3352（审-高）：「做个决定」夹个「个」字原词表全漏——补弹性词。
    (("帮我决定", "替我选", "替我决定", "做决定", "做个决定", "做个选择",
      "拿不定", "拿不准", "帮我选", "选不好", "纠结", "纠结死",
      "要不要去", "要不要做", "怎么选", "选哪个", "掷筊",
      # R3356（审-中低）：裸「要不要X」/「该不该X」/意向词——
      # oracle 页副题就是「要不要、去不去、说不说」，词表收齐。
      "要不要", "该不该", "想辞职", "想离职", "想跳槽", "想换工作",
      "想分手",
      # R3418-P1-4：筊杯夹字形态——掷个筊/掷了筊零命中。
      "掷个筊", "掷了筊", "掷个杯"),
     "她在纠结选择题，铺子里有真入口：首页宫格「替你决定」卡"
     "能掷筊出圣筊/笑筊/阴筊；先共情两句她的纠结，再让她去掷，"
     "掷完回来接着聊",
     "oracle", "✋ 去掷筊", None),
    # R3335：烦恼路标——倒苦水类高频句直接给粉碎机入口，
    # 别让模型干回「深呼吸/写下来」的空话。
    # R3352（审-中）：口语按「功能长相」描述——撕纸/碎纸/发泄族补上。
    (("烦恼", "烦心事", "压力大", "压力好大", "焦虑", "烦死",
      "心烦", "emo", "郁闷", "内耗", "好烦", "撕纸", "碎纸",
      "粉碎", "发泄", "出气"),
     "她在倒苦水，铺子里有真入口：首页日签卡上有「烦恼粉碎机」，"
     "把压着的事写进去当场碎掉不留档；安抚两句后让她去碎，"
     "碎完回来接着聊",
     "home", "🗑️ 去碎掉它", "shred"),
    # R3352（审-中）：成真集——「成了/还愿」方向词原词表全是「许」方向。
    # 放在许愿族前面：「愿望成真」含裸「愿望」，先判更具体的成真向。
    (("愿成真", "愿望实现", "愿望成真", "梦想成真", "还愿", "灵验"),
     "她的愿望成了——成真集在首页许愿瓶卡里，点「成真啦」"
     "收进集子还出还愿卡；让她去把这份好运收一收",
     "home", "✨ 去还愿", "wish"),
    # R3331（审-低）：愿望路标——她想许愿时给真入口：日签卡
    # 许愿瓶（新月还有提醒），别让模型干回「去树下许愿吧」。
    # R3351（审-P2）：「许个愿/新年愿望」自然说法——裸「愿望」
    # 收进词表（成真向已被上族拦截）。
    (("许愿", "许个愿", "心愿", "愿望瓶", "丢个愿望", "写愿望",
      "许下心愿", "愿望", "想个愿"),
     "她想许愿，铺子里有真入口：首页日签卡上有许愿瓶，"
     "把愿望丢进去会帮她存着；逢新月还会提醒她许，"
     "让她去那儿写，写完回来接着聊",
     "home", "🫙 去丢个愿望", "wish"),
    # R3352（审-高）：咒语册路标——view-mantra 格页真实存在。
    (("咒语册", "收咒语", "攒的咒语", "咒语收集", "咒语卡", "咒语"),
     "她问咒语册：铺子里有——每天日签那句开运咒语点旁边 ❤️ "
     "就收进「我的咒语册」（首页日签卡 meta 行小链直达）；"
     "册页里每句能「再念一遍」复制、能请出册。空册跟她说先收今天那句",
     "mantra", "📖 翻翻咒语册", None),
    # R3352（审-高）：心情周记路标——view-moodweek「这周的你」真实存在。
    (("这周心情", "心情周记", "这周的我", "一周心情", "本周心情",
      "最近的心情"),
     "她问心情周记：铺子里有——打卡区「📒 看看这周的你」把近 7 天"
     "心情罐聚成小卡（点阵/主心情/连续天数，还有上周对比和周记"
     "海报）；没记过心情的跟她说打卡时顺手点一个就攒起来了",
     "moodweek", "📒 看看这周的你", None),
    # R3523（亲审）：小规律路标——门槛如实说（记满 8 天心情才出声）。
    (("小规律", "我的规律", "心情规律", "规律观察", "小发现"),
     "她问小规律：首页打卡区会挂一条「📊 你的小规律」——她攒的"
     "心情×星期/周末/打卡次日/月相交叉出来的真实观察；记满 8 天"
     "心情才够出声，周记里也有同一行",
     "moodweek", "📒 去周记看小规律", None),
    # R3523：本周小功课路标。
    (("小功课", "本周功课", "这周功课", "每周功课"),
     "她问小功课：打卡区周一自动换一件够得着的小事，"
     "「做到了」盖戳攒功课章，打卡分享海报也会带上它",
     "home", "📜 去看本周小功课", "checkin"),
    # R3533：本周旺运/心情月历路标——新件入聊可查。
    (("本周旺运", "旺运", "本周幸运", "这周旺什么"),
     "她问旺运：打卡区每周换一套「本周旺运」——色·随身小物·吃口啥，"
     "图个乐呵的仪式感小抄，周记里也能翻到",
     "home", "🍀 去看本周旺运", "checkin"),
    (("心情月历", "心情日历", "上个月的心情", "以前记的心情"),
     "她问心情月历：周记里有当月热力格，记过的天按心情色染格、"
     "点格子能回看那天记的是啥，←→ 还能翻上个月",
     "moodweek", "📅 去翻心情月历", None),
    # R3543：连签对擂台路标。
    (("比连签", "连签对擂", "比打卡", "对擂", "比一比连签"),
     "她想跟朋友比连签：打卡区有「⚔️ 喊 TA 比连签」，"
     "点一下复制带自己天数的链接发给 TA——TA 点开就看到"
     "俩人的比分，不用注册不用加好友",
     "home", "⚔️ 去喊 TA 比连签", "checkin"),
    # R3597：月度复盘/晒月亮路标——新件入聊可查。
    (("晒这月", "上月复盘", "月度复盘", "月总结", "上个月的小满",
      "上个月过得怎么样"),
     "她问上月复盘：月初的打卡卡里有「📮 N 月的小满信」——"
     "上月的打卡/心情/小记都替你记成一封信，信尾「晒这月」"
     "能出一张上月小记海报",
     "home", "📮 去翻上月小满信", "checkin"),
    (("晒月亮", "今晚的月亮", "月相海报", "今天月亮", "晒今晚"),
     "她想晒月亮：首页月相行有「晒今晚 🌙」——"
     "今晚的盈亏直接画成一张月相海报，每天的月亮都不一样",
     "home", "🌙 去晒今晚", None),
    # R3567：递好运路标——温柔社交件（跟「比」互补）。
    (("递个好运", "递好运", "送好运", "送个好运", "给朋友好运",
      "为 TA 加油", "给 TA 打气"),
     "她想给朋友递个好运：打卡区有「🤗 递个好运给 TA」，"
     "点一下复制链接发过去——TA 点开就收到一句好运，"
     "不用注册不用加好友",
     "home", "🤗 去递个好运", "checkin"),
    # R3352（审-高）：合拍打卡——需先把 TA 生日存档案才出交集行。
    (("一起打卡", "跟对象打卡", "合拍打卡", "双人打卡", "和ta打卡",
      "和TA打卡", "情侣打卡"),
     "她想跟 TA 一起打卡：打卡区有 💞 合拍行，两边同天打卡会"
     "亮交集；先把 TA 生日存进档案（合盘页存 TA / 邀请链）才出这条",
     "home", "💞 去打卡区邀 TA", "checkin"),
    # R3352（审-中）：年报路标——门槛如实说，别让模型许诺现成报告。
    (("年度报告", "年报", "年度回顾"),
     "她问年度小满报告：打卡区有「📖 小满年报」——今年打卡攒满 "
     "8 天出年度报告海报（年末 12/15–1/31 降到 3 天）；"
     "没攒够按钮会显示还差几天",
     "home", "📖 去看小满年报", "annual"),
    (("解梦", "解个梦", "解一梦", "周公",
      # R3356（审-低）：自然说法「梦见X/梦到X/做了梦」补进词表。
      "梦见", "梦到", "做梦", "做了个梦"),
     "她想解梦，铺子里有真入口：首页「解梦」卡把梦讲给"
     "册子听，对完回来接着聊",
     "dream", "🌙 去解梦", None),
    # R3373：正缘/灵魂伴侣词族——全网爆款问句，落桃花页
    # （画像按钮在桃花结果卡上，需先出盘才有画像）。
    # 排在八字族前面：「八字看正缘」应先中画像路标。
    (("正缘", "灵魂伴侣", "对的人", "命中注定", "姻缘",
      "另一半", "良人", "未来对象", "男朋友什么样",
      "老公什么样", "未来老公", "未来男友"),
     "她在问正缘：铺子里有「正缘画像」——桃花页输她生日"
     "出盘后，结果卡上有「💘 看看 TA 的气质画像」，按她的"
     "盘推出气质型+相遇信号，还能晒图；让她先去桃花页看盘",
     "taohua", "💘 去看正缘画像", None),
    (("八字",),
     "她想排八字，铺子里有真入口：首页「八字」卡输生日"
     "出真盘，看完回来接着聊",
     "bazi", "📜 去排八字", None),
    # R3418-P2-1：人生K线路标——八字结果卡的折叠子件，词族直接
    # 指到折叠锚（kline-fold details 打开+滚到门口）。
    (("人生K线", "流年K线", "流年走势", "K线图", "人生k线", "运势K线"),
     "她想看人生K线，铺子里有真入口：首页「八字」卡输生日出盘后，"
     "结果卡上有「流年K线」折叠图——90 柱大运流年走势，标着"
     "本命年/冲太岁/换运；让她先去八字页出盘，折卡就在结果卡里",
     "bazi", "📈 去看流年K线", "kline"),
    # R3418-P2-4：未来信/跨年信路标——低流量但高辨识词。
    (("未来信", "写给未来的信", "跨年信", "时空信", "给未来的信"),
     "她想写未来信：打卡区有「写给未来的信」——写完存本地，"
     "到日子在打卡区浮出来；年末还有跨年信（写给明年的自己），"
     "让她去打卡区找",
     "home", "✉️ 去写未来信", "checkin"),
    # R3471：小惊喜族路标——sa* 锚直达排盘结果折叠区对应卡
    # （已出盘直开，未出盘存待启标记出盘自动展开）。
    (("旺我的方位", "旺我的方向", "哪个方向旺", "旺运方位", "幸运方位",
      "有利方位", "旺你的方位"),
     "她想看旺她的方位：铺子的排盘结果卡「✨ 盘里小惊喜」里有"
     "「🧭 旺你的方位」——喜用神推东南西北+城市气质+出行贴士；"
     "让她先去排盘，出盘自动展开那张卡",
     "bazi", "🧭 看旺我的方位", "saF"),
    (("守护兽", "守护灵兽", "守护图腾", "灵兽", "我的图腾",
      "灵魂动物", "灵魂图腾"),
     "她想看守护图腾：排盘结果卡「✨ 盘里小惊喜」里有「🐉 守护图腾」"
     "——日主+五行推灵兽原型+守护语；先排盘，出盘自动展开",
     "bazi", "🐉 看守护图腾", "saG"),
    (("守护水晶", "幸运水晶", "我的水晶", "戴什么水晶", "什么水晶旺"),
     "她想看守护水晶：排盘结果卡「✨ 盘里小惊喜」里有「🔮 守护水晶」"
     "——喜用神配色系晶石+佩戴贴士；先排盘，出盘自动展开",
     "bazi", "🔮 看守护水晶", "saC"),
    (("灵魂色谱", "命盘颜色", "我的色谱", "五行颜色", "盘是什么颜色"),
     "她想看灵魂色谱：排盘结果卡「✨ 盘里小惊喜」里有「🎨 灵魂色谱」"
     "——五行权重画成一人一版的星云图；先排盘，出盘自动展开",
     "bazi", "🎨 看灵魂色谱", "saS"),
    # R3490：灵魂角色路标——saR 锚直达。
    (("灵魂角色", "我的角色", "灵魂人物", "灵魂原型", "神话角色",
      "哪个神", "灵魂icon", "灵魂Icon", "soul icon"),
     "她想看灵魂角色：排盘结果卡「✨ 盘里小惊喜」里有「🎭 灵魂角色」"
     "——日主五行推她盘里住着的神话角色（女娲/祝融/后土/刑天/洛神）；"
     "先排盘，出盘自动展开",
     "bazi", "🎭 看灵魂角色", "saR"),
    # R3491：灵魂纹样路标——saE 锚直达。
    (("灵魂纹样", "我的纹样", "守护纹样", "纹样", "灵魂tattoo",
      "灵魂 tattoo", "soul tattoo", "几何纹", "印章纹"),
     "她想看灵魂纹样：排盘结果卡「✨ 盘里小惊喜」里有「🧿 灵魂纹样」"
     "——日主定纹样族、五行当种子画出一人一纹的徽章，可存原图当"
     "头像或锁屏；先排盘，出盘自动展开",
     "bazi", "🧿 看灵魂纹样", "saE"),
    # R3494：灵魂名片路标——saN 锚直达。
    (("灵魂名片", "我的名片", "灵魂名卡", "盘里都有什么",
      "六件小惊喜", "soul card", "灵魂汇总"),
     "她想看灵魂名片：排盘结果卡「✨ 盘里小惊喜」里有「📇 灵魂名片」"
     "——方位/图腾/晶石/色谱/纹样/角色六件派生件汇总一卡，可晒"
     "一张图的海报；先排盘，出盘自动展开",
     "bazi", "📇 看灵魂名片", "saN"),
    (("算命prompt", "算命 prompt", "贴给AI", "喂给AI", "给AI算",
      "deepseek算命", "DeepSeek算命", "prompt算命"),
     "她想把盘生成 prompt 贴给别的 AI：排盘结果卡「✨ 盘里小惊喜」里"
     "有「📋 算命 prompt」——生辰+命盘+五行摘要一键复制；先排盘，"
     # R3484-P1（审）：无手势环境承诺「自动复制好」兑不了现。
     "出盘后折叠区里那颗 📋 钮一键复制",
     "bazi", "📋 复制算命 prompt", "saP"),
]


def _chat_action(message: str):
    """路标匹配 → (facts行, 视图键, 按钮文案, 锚点) 或 None。"""
    _n = _t2s((message or ""))
    # R3352：明星名命中优先于词表——带铺子口径的生日事实。
    for c in _celeb_list():
        if c.get("n") and c["n"] in _n:
            return (
                "她提到 " + c["n"] + "：铺子里有明星合盘——合盘页的"
                "「✨ 和明星合盘」选择器里有 TA（公开生日 "
                f"{c['y']}-{c['m']:02d}-{c['d']:02d}，时辰未知按正午排），"
                "点一下 TA 侧自动填就能合；别凭记忆报生日，"
                "铺子里的口径是这份公开资料",
                "hehun", f"✨ 去和「{c['n']}」合盘", "celeb")
    for keys, line, view, label, anchor in _CHAT_ACTIONS:
        if view == "bazi" and keys == ("八字",):
            # 「八字」裸词过宽（「我八字软吗」是提问不是要排盘）——
            # 要求同句带动作词。R3370-P2-8：命盘/看盘/我的盘同族。
            # R3418-P2-1：其它 view=bazi 的条目（K线族）走正常
            # key 匹配，不吃动作词闸。
            # R3418-P2-5：排盘/个盘形态——产品自用术语不在盘词集，
            # 「帮我排盘」「合个盘」此前全漏。
            if (("八字" in _n or "命盘" in _n or "我的盘" in _n
                 or "看盘" in _n or "排盘" in _n or "个盘" in _n)
                    and any(k in _n for k in ("算", "看", "排", "测"))):
                return line, view, label, anchor
            continue
        if anchor == "trQH":
            # R3370-P1-2：万圣限定卡只在 10/29–11/1 现身——窗口外
            # 指路隐藏钮=死 chip，跳过落回塔罗族。
            # R3434（审）：裸 date.today() 是 UTC 日——窗口首日 0-8 点
            # CN 用户看不到卡、末日 CN 20-24 点多给 8h。改 _today_cn。
            _nd = _today_cn()
            if not ((_nd.month == 10 and _nd.day >= 29)
                    or (_nd.month == 11 and _nd.day <= 1)):
                continue
        if anchor == "trQX":
            # R3435：圣诞心愿限定卡只在 12/20–12/25 现身。
            _nd = _today_cn()
            if not (_nd.month == 12 and 20 <= _nd.day <= 25):
                continue
        if any(k in _n for k in keys):
            return line, view, label, anchor
    return None


def chat_action_facts(message: str) -> list[str]:
    """小满聊天的功能路标供给（R3180c）：「帮我抽张牌/起个卦」类
    请求——模型不知道产品里有真入口，会干说「我抽不了」。
    给她一条路标：真入口在哪、抽完可以回来接着聊。
    """
    _a = _chat_action(message)
    return [_a[0]] if _a else []


def chat_action_view(message: str) -> dict | None:
    """R3195：路标的可点跳转面，前端渲染「去 XX」chip。
    R3352：anchor=页内锚位（折叠 details 选择器名/id 键），
    前端落地时开详情+滚到位——「到了街区没送到门口」修复。"""
    _a = _chat_action(message)
    return {"view": _a[1], "label": _a[2], "anchor": _a[3]} if _a else None


# R3317-D 同款咒语池——服务端镜像（web/static/app.js _MANTRA_POOL
# 逐字同序）。同日同句是社群契约，改池子两边一起改。
_MANTRA_POOL = [
    '水逆退散，钱包回暖', '霉运清零，好事常来', '烦恼退退退',
    '好运充值成功', '今天也是被幸运点名的人', '诸事顺利，心想事成',
    '今日好运已到账', '难事先放一放，先吃饭', '小确幸浓度拉满',
    '今天走路都带风', '好运气从这里开始', '所求皆所愿，所行皆坦途',
    '今日份快乐已签收', '好事正在派送中', '今天不谈烦心事',
    '运气这回事，我信', '顺顺当当过今天', '小满即圆满',
    '今天的好事不止一件', '心宽的人运气不会差', '福气正在路上',
    '今天适合好好待自己', '困难退散，快乐翻倍', '愿望清单推进中',
    '今天的我是限量版', '好运会迟到但不会缺席', '日子一天天，越来越甜',
    '今天也为小目标蓄力', '好运与好心态双向奔赴', '不急不慌，好事不慌',
    '今天的快乐额度无限', '所愿皆成，所遇皆暖', '把烦恼调成静音',
    '今天是个好日子', '好心态是最好的好运', '小满未满，一切都刚好']


def _day_mantra(date_str: str) -> str:
    """今日咒语——与前端 _dayPick(_MANTRA_POOL,'mantra|'+date) 同哈希。

    JS 版：str = 'mantra|<j.date>|<todayIso>'，h=(h*31+code)>>>0，
    pool[h%len]。j.date/todayIso 在常规用法里都=当天，故键为
    'mantra|<d>|<d>'；任一日期盐都是 ASCII，charCode=字节值。
    """
    s = f"mantra|{date_str}|{date_str}"
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _MANTRA_POOL[h % len(_MANTRA_POOL)]


def chat_daily_facts(message: str, now: datetime | None = None) -> list[str]:
    """R3331（审-中2/3/4）：当日派生事实按问句主题注入——
    水逆/穿搭色/咒语问句此前零供给，小满自由发挥出口径分裂
    （答「今天没有水逆」当日正值水逆第 3 天；咒语每次现编
    与卡面不同句）。"""
    _n = _t2s((message or ""))
    if not _n.strip():
        return []
    _d = (now or _now_cn()).date()
    out: list[str] = []
    try:
        if any(k in _n for k in ("水逆", "水星逆行")):
            _m = _mercury_state(_d)
            if _m.get("on"):
                out.append(
                    f"今日水逆态：正在水逆，第{_m['day_no']}天，"
                    f"一直到{_m['until']}（日粒度历表）")
            elif _m.get("next"):
                out.append(
                    f"今日水逆态：今天不在水逆期，下一次"
                    f"{_m['next']}起（还有{_m['days_to']}天）")
            else:
                out.append("今日水逆态：今天不在水逆期")
        # R3502：金逆/火逆问句——同构状态行随问随行。
        if any(k in _n for k in ("金逆", "金星逆行")):
            _v = _venus_state(_d)
            if _v.get("on"):
                out.append(
                    f"今日金逆态：正在金星逆行，第{_v['day_no']}天，"
                    f"一直到{_v['until']}（日粒度历表）")
            elif _v.get("next"):
                out.append(
                    f"今日金逆态：今天不在金逆期，下一次"
                    f"{_v['next']}起（还有{_v['days_to']}天）")
            else:
                out.append("今日金逆态：今天不在金逆期")
        if any(k in _n for k in ("火逆", "火星逆行")):
            _r = _mars_state(_d)
            if _r.get("on"):
                out.append(
                    f"今日火逆态：正在火星逆行，第{_r['day_no']}天，"
                    f"一直到{_r['until']}（日粒度历表）")
            elif _r.get("next"):
                out.append(
                    f"今日火逆态：今天不在火逆期，下一次"
                    f"{_r['next']}起（还有{_r['days_to']}天）")
            else:
                out.append("今日火逆态：今天不在火逆期")
        if any(k in _n for k in ("穿搭", "穿什么", "穿啥", "幸运色",
                                 "幸运颜色", "开运色", "什么颜色", "配色")):
            _lk = _lucky_for(_d)
            _of = _outfit_for(_d)
            if _lk.get("color"):
                out.append(f"今日开运色：{_lk['color']}"
                           f"（{_lk.get('color_word', '')}）")
            _t0 = (_of.get("tiers") or [{}])[0]
            if _t0.get("colors"):
                out.append(f"今日穿搭大吉档：{_t0['colors']}"
                           f"（{_t0.get('tip', '')}）")
        if any(k in _n for k in ("咒语", "好运语", "转运语", "今日一句",
                                 "口号", "许愿语")):
            out.append(f"今日咒语：{_day_mantra(_d.isoformat())}"
                       "（与日签卡同句，可直接念）")
    except Exception:
        pass
    return out


def chat_result_verdicts(ref: str | None) -> list[str]:
    """从服务端结果快照提取判词层事实——供 chat 权威信道。

    全是自家生成的 warm.reply 原文+键字段，verbatim 可信。
    输出形如「判词：…」「合拍指数：43/99」≤8 行 ×≤120 字。
    """
    view, j = _pop_result(ref)
    if not view or not isinstance(j, dict):
        return []
    out: list[str] = []
    w = (j.get("warm") or {}).get("reply") or []
    # 每视图的锚定标量（判词主体之外的定位行）
    if view == "hehun":
        _sc = j.get("match_score")
        if _sc is not None:
            out.append(f"这张合婚卡的合拍指数：{_sc}/99")
    elif view == "taohua":
        if j.get("peach_zhi"):
            out.append(f"桃花支：{j['peach_zhi']}")
        if j.get("strength"):
            out.append(f"桃花强度：{j['strength']}")
    elif view == "bazi":
        _pp = ((j.get("paipan") or {}).get("render") or "")
        _seg = _pp.split("　")
        if _seg[0]:
            out.append(f"四柱：{_seg[0]}")
        _dm = (j.get("paipan") or {}).get("day_master")
        if _dm:
            out.append(f"日主：{_dm}")
    elif view == "liuyao":
        _bn = (j.get("ben") or {}).get("gua_name") or j.get("ben_name")
        if _bn:
            out.append(f"本卦：{_bn}")
        _bin = (j.get("bian") or {}).get("gua_name") or j.get("bian_name")
        if _bin:
            out.append(f"变卦：{_bin}")
    elif view == "tarot":
        _cs = [(d.get("name") or "") + ("（正位）" if d.get("upright")
               else "（逆位）") for d in (j.get("draws") or [])[:5]]
        if _cs:
            out.append("抽到的牌：" + "、".join(_cs))
    elif view == "qiming":
        _fn = j.get("full_names") or []
        if _fn and _fn[0].get("full_name"):
            out.append(f"首选名：{_fn[0]['full_name']}")
    elif view == "xzm":
        # R3150：合盘判词在 lines 键不在 warm.reply——分数+标签+
        # lines 逐行全收，权威块照拿「82 分·合拍」原口径。
        if j.get("score") is not None:
            out.append(f"这张合盘卡的合拍指数：{j['score']}"
                       f"（{j.get('label') or ''}）")
        for _l in (j.get("lines") or [])[:6]:
            if str(_l).strip():
                out.append("卡面判词行：" + str(_l)[:110])
        return out[:9]
    elif view == "daily":
        # R3150b：日签无 warm 块——summary 事实句/宜忌/等级是卡面原文。
        if j.get("level"):
            out.append(f"今日评级：{j['level']}")
        if j.get("do"):
            out.append(f"卡面宜：{str(j['do'])[:80]}")
        if j.get("dont"):
            out.append(f"卡面忌：{str(j['dont'])[:80]}")
        for _seg in str(j.get("summary") or "").split("；"):
            _seg = _seg.strip()
            if _seg:
                out.append("卡面判词行：" + _seg[:110])
        return out[:9]
    elif view == "xingzuo":
        if j.get("today_sign"):
            out.append(f"今日值宫：{j['today_sign']}座")
        if j.get("today_note"):
            out.append("卡面判词行：" + str(j["today_note"])[:110])
    elif view == "dream":
        # R3178：解梦卡——象征名行进权威信道；warm.reply 由尾部
        # 公共循环照收（老话/回声/微行动/免责全在里头）。
        _syms = [(s.get("name") or "") for s in (j.get("symbols") or [])]
        if _syms:
            out.append("梦里对上的画面：" + "、".join(_syms[:3]))
    if j.get("question"):
        out.append(f"她当时问的是：「{str(j['question'])[:60]}」")
    # warm.reply 原文逐条收——判词带/剧本/处方/倾向全在里面，
    # 服务端快照逐字一致，不存在被改的可能
    for _ln in w:
        _s = str(_ln).strip()
        if _s:
            out.append("卡面判词行：" + _s[:110])
    return out[:9]


def chat_profile_facts(facts: list[str]) -> list[str]:
    """小满聊天档案层：客户端「生日：YYYY-MM-DD」事实确定性展开。

    R3115（specs/011 P1-1）：me 档案生日此前只作昵称级事实透传，
    服务端手里能算日主却不算——小满知道「她生日」却不知道「她是谁」。
    现按 day_ganzhi + sun_sign_profile 纯函数展开（零 LLM、输入固定
    输出固定）：「她的日主：庚（五行属金）」「她的太阳星座：金牛」。
    非生日行原样透传；非法日期静默不展开。
    """
    out: list[str] = []
    for f in facts or []:
        out.append(f)
        _fs = str(f).strip()
        m = _BIRTHDAY_FACT_RE.match(_fs)
        mp = _BIRTHDAY_PARTNER_RE.match(_fs)
        if not m and not mp:
            continue
        try:
            _mm = m or mp
            y, mo, d = int(_mm.group(1)), int(_mm.group(2)), \
                int(_mm.group(3))
            gz, _idx = _bazi_day_ganzhi(datetime(y, mo, d))
            dm = gz[0]
            wx = GAN_ELEM.get(dm, "")
            from guji.xingzuo import sun_sign
            # R3308：年已知走节气精判（边界日不再错座）
            sign = sun_sign(mo, d, year=y) or ""
            _who = "TA" if mp else "她"
            out.append(f"{_who}的日主：{dm}"
                       + (f"（五行属{wx}）" if wx else ""))
            if sign:
                out.append(f"{_who}的太阳星座：{sign}")
        except (ValueError, TypeError):
            continue
    return out


def _chat_facts_inner(message: str, now: datetime,
                      anchor: dict | None = None,
                      ctx_out: dict | None = None,
                      _cmp: int = 0) -> list[str]:
    """chat_huangli_facts 的计算主体（缓存键之外的一切都不变）。"""
    msg = (message or "").strip()
    if not msg:
        return []
    now = now or _now_cn()
    msg_n = _t2s(msg)   # R229d：繁中归一后再做事项词/泛问匹配（原文留给日期词）
    # R2400（R123-P2-1+R126-P1-4/P2-3+R128-P1-1/P1-4/P1-5）：「再往后N天/
    # 往后挪一周」先匹配并把命中 span 从日词输入里摘掉——「再过两天」里
    # 含的「过两天」若再喂 _hl_day_part 会二次消费（实测判 +4 天）。
    # 自带基日的词（过N天/后一天/下一天）恒按今天+N；顺延类词没自带
    # 基日，优先本句日词、再借锚。单位补周/星期（×7），词表补 挪/延/
    # 推迟/推后/改后，覆盖简繁。
    _m_after = re.search(
        r"再?(?:往|向)[后後](?:挪|推)?"
        r"(半|[一二两三四五六七八九兩]?十[一二三四五六七八九]?|"
        r"[一二两三四五六七八九兩]+|\d+)?[个個]?"
        r"(天|日|周|週|星期|禮拜|礼拜|月)|"
        r"再?[过過]"
        r"(半|[一二两三四五六七八九兩]?十[一二三四五六七八九]?|"
        r"[一二两三四五六七八九兩]+|\d+)?[个個]?"
        r"(天|日|周|週|星期|禮拜|礼拜|月)|"
        r"(?:顺延|延後|延后|顺沿|推迟|推後|推后|改[后後]|[后後]延)"
        r"(半|[一二两三四五六七八九兩]?十[一二三四五六七八九]?|"
        r"[一二两三四五六七八九兩]+|\d+)?[个個]?"
        r"(天|日|周|週|星期|禮拜|礼拜|月)|"
        r"后一天|後一天|下一天", msg)
    _msg_dt = (msg[:_m_after.start()] + msg[_m_after.end():]
               if _m_after else msg)
    # R2400：日期解析提前——事项沿用判定（「那后天呢」继承上句场景）
    # 需要先知道本句带没带日期词。
    dt, spoken = _hl_day_part(_msg_dt, now)
    # R2400（R128-P1-3）：不存在日检测要用沿用/顺延覆写前的原始解析——
    # 锚沿用把 spoken 改成明天后「星期八」就被静默吞掉。
    _orig_spoken = spoken
    _explicit_day = (spoken != "今天" or any(
        w in _msg_dt for w in ("今天", "今日", "今晚", "今夜")))
    # R2400（R128-P1-8）：换话题/作罢排除在追问外——「换个话题」「还是
    # 算了吧」不该重放上一句判定。裸标点后缀单字（「？」「呢」）也不算。
    _topic_drop = bool(re.search(
        r"换个话题|换个别的|说说别的|聊点别的|不说这个|别聊了|不聊了|"
        r"算了|换个事聊", msg_n))
    _followup = not _topic_drop and len(msg_n) >= 2 and (
        bool(re.match(r"^(那|要不|还是|换|哎|诶|话说)", msg_n))
        or msg_n.endswith(("呢", "嘛", "?", "？")))
    if _m_after:
        _gs = [g for g in _m_after.groups() if g]
        # R3230续：数字位升复合数（十一/二十五/半月）——取首个能解析
        # 出数的组，缺省当 1（「再往后挪一天」省「一」）。
        _na = next((g for g in _gs if _cn_num(g) or g == "半"), "一")
        _unit = _gs[-1] if _gs else "天"
        _base = None
        _self_based = bool(re.match(
            r"再?[过過]|后一天|後一天|下一天", _m_after.group(0)))
        if _self_based:
            _base = now
        elif _explicit_day:
            _base = dt
        elif anchor and anchor.get("dt"):
            try:
                _base = datetime.fromisoformat(anchor["dt"])
            except (ValueError, TypeError):
                _base = None
        _b2 = _base or now
        if _unit == "月":
            # 半月≈15 天；整月走 _add_months（日数钳到月末）
            dt = _b2 + timedelta(days=15) if _na == "半" \
                else _add_months(_b2, _cn_num(_na) or 1)
        else:
            # 半周≈3 天；半天同日；整周×7
            _nd = (3 if _unit not in ("天", "日") else 0) \
                if _na == "半" else (_cn_num(_na) or 1)
            if _unit not in ("天", "日"):
                _nd *= 7
            dt = _b2 + timedelta(days=_nd)
        spoken = _m_after.group(0)
        _explicit_day = True
    # 「换个日期/换个日子」：想为上一句的事项另择日子——归入找日意图
    # （也作为场景沿用的触发条件之一）。
    _find_day_switch = bool(
        re.search(r"换[一个点]?(?:日子|日期|时间|天)|"
                  r"改[一个点]?(?:日子|日期)", msg_n))
    # R2400（R126-P1-2）：「哪天/什么时候+事项」同样是找日问法——沿用
    # 锚点日期会把 spoken 改写成锚那天，find-day 分支再也够不到
    # （「那搬家哪天好」实测被答成明天的单天判定）。意图词表与下面
    # _find_only 判定同源，提前到这里供沿用闸引用。
    # R3366（审-P1）：「时间段/时段/哪段」同样是找日问法——「今年
    # 适合换工作的时间段」此前被压成今天的单日判词。
    _find_intent = bool(re.search(
        r"哪天|什么时候|啥时候|几时|几号|时间段|时段|哪段|"
        r"换[一个点]?(?:日子|日期|时间|天)|改[一个点]?(?:日子|日期)", msg_n))

    scene, terms = "", []
    # R228s：长词优先匹配——「解除合同」若先撞上「合同」会被误分到立券
    # （签约方向，与用户意图相反）。先扫长键再扫短键消歧。
    # R2400（R126 跟进）：同长多命中时取句中最靠后者——意图词一般在
    # 句尾（「分手了哪天复合好」问的是复合不是分手；「复合后又想
    # 分手」问的是分手）。
    _hits = [(len(k), msg_n.rfind(k), k) for k in _CHAT_SCENE_TERMS
             if k in msg_n]
    if _hits:
        _k = max(_hits)[2]
        scene, terms = _k, _CHAT_SCENE_TERMS[_k]
        # R2400（R128-P1-9）：找日问法 + 多场景命中时，提问焦点在含
        # 找日词的分句里（「哪天搬家好，我分手了心情不好」问的是搬家，
        # 倾诉尾巴的「分手」不该当选）——场景限在找日词所在分句内取。
        if _find_intent and len(_hits) >= 2:
            _fi = re.search(
                r"哪天|什么时候|啥时候|几时|几号|"
                r"换[一个点]?(?:日子|日期|时间|天)|改[一个点]?(?:日子|日期)",
                msg_n)
            _fp = _fi.start() if _fi else 0
            _off = 0
            for _cl in re.split(r"[，。！？；,.!?;~～…\n]", msg_n):
                _ce = _off + len(_cl)
                if _off <= _fp <= _ce:
                    _cl_hits = [(msg_n.find(k, _off), k)
                                for k in _CHAT_SCENE_TERMS if k in _cl]
                    _cl_hits = [(p, k) for p, k in _cl_hits
                                if _off <= p <= _ce]
                    if _cl_hits:
                        _k2 = max(_cl_hits)[1]
                        scene, terms = _k2, _CHAT_SCENE_TERMS[_k2]
                    break
                _off = _ce + 1
    if not scene:
        for t in _HUANGLI_VOCAB_ORD:
            if t in msg_n:
                scene, terms = t, [t]
                break
    # R2400（R123-P1-4/P2-1 + R126-P1-1/P2-2 + R128-P1-5）：沿用锚点
    # 场景只给真追问——纯问天（那后天呢）、裸追问（那咋办）、换日问法
    # （换个日子）、顺延句（再往后两天）；换话题句不算追问。
    if (anchor and not scene and anchor.get("scene")
            and (_followup or _find_day_switch or _m_after)):
        scene, terms = anchor["scene"], list(anchor["terms"])
    generic = not scene and any(
        k in msg_n for k in ("黄历", "宜忌", "吉日", "挑日子", "看日子",
                             "择日", "适合做什么", "适合干什么",
                             # R229o：「今天宜做什么」「明天忌什么」裸问法
                             "宜做什么", "忌做什么", "宜什么", "忌什么",
                             "做什么好", "干点啥", "能干啥", "能干什么"))
    # R2400（R123-P1-1 + R126-P1-1/P1-2/P1-3/P2-2）：沿用锚点日期
    # 收窄——必须真追问且不找日。「那搬家呢」按明天判保留；「那搬家
    # 哪天好」走 find-day 另算近 45 天；「我分手了怎么办」不是追问
    # 不沿用；裸追问「那咋办」没自带场景也沿用（接着上一句答）。
    if (anchor and not _explicit_day and _followup
            and not _find_intent
            and anchor.get("dt")):
        try:
            dt = datetime.fromisoformat(anchor["dt"])
            spoken = anchor["spoken"]
        except (ValueError, TypeError):
            pass
    # R2400（R128-P2-3/P1-7）：多日对比句的主判日按句中首个日词定——
    # _hl_day_part 的命中序不是语序（「周五和下周六」原判下周六）。
    # 词位表也供 (日词,场景) 配对用。
    _cmp_words = [(m.start(), m.group(0)) for m in
                  _COMPARE_DAY_RE.finditer(msg_n)]
    _has_cmp = bool(re.search(
        r"和|跟|与|还是|或者|或|哪个|哪天|比谁|对比|比较", msg_n))
    if len(_cmp_words) >= 2 and _has_cmp:
        _d0, _s0 = _hl_day_part(_cmp_words[0][1], now)
        if _s0 != "今天" or any(
                w in _cmp_words[0][1] for w in ("今天", "今日", "今晚", "今夜")):
            dt, spoken = _d0, _s0
    if ctx_out is not None:
        ctx_out.update({"dt": dt.isoformat(), "spoken": spoken,
                        "scene": scene or None, "terms": list(terms)})
        # R2400（R128-P2-4）：危机拒答消息不参与锚维护。
        if llm_polish._is_crisis(msg):
            ctx_out["qk"] = "crisis"
    # R233r（R49-P2-2）+ R2400（R126-P1-3）：高敏事项（分手/辞职/
    # 怀孕/离婚→解除/求嗣/嫁娶）已成事实 → 是倾诉不是问日子，别塞
    # 判定句把共情话头带歪。决策词（「怎么办/该不该」）不再豁免——
    # 「我分手了怎么办」的「怎么办」是求安慰不是择日；真找日问法
    # （分手了哪天复合好）仍放行——她真的在问日子。
    if (set(terms) & {"解除", "求嗣", "嫁娶"}
            and _ALREADY_HAPPENED_PAT.search(msg_n)
            and not _find_intent):
        return []
    # R3323-P0-2/P1-3：双关节气无语境——「大寒开业吗」的「大寒」可能
    # 是节气也可能是冷天。它明明存在，不能说「没这天」；让模型温和
    # 确认「是问节气那天吗」（顺带把那天是几号递过去），不按今天判。
    if _orig_spoken == "今天" and not any(
            w in msg for w in ("今天", "今日", "今晚", "今夜")):
        _ambi = re.search(r"大寒|小寒|大雪|小雪", msg_n)
        if _ambi:
            _ad = ""
            try:
                _cd = [d for d in _holiday_candidates(_ambi.group(0),
                                                      now, None)
                       if d >= now.date()]
                if _cd:
                    _x = min(_cd)
                    _ad = f"{_x.month}月{_x.day}日"
            except Exception:
                pass
            if ctx_out is not None:
                ctx_out["qk"] = "badday"
            return [f"用户说的「{_ambi.group(0)}」可能是节气也可能是天气"
                    f"——温和问一句她是不是指节气那天"
                    f"{('（' + _ad + '）') if _ad else ''}，"
                    "没确认前别拿今天替她判宜忌。"]
    # R2355（R111-P2-3）：显式但解不出的日期词（星期八/32号/农历13月/
    # 越界年号）——_hl_day_part 回落「今天」且带这些标记 = 用户真在
    # 问一个不存在的日子。给「日子不存在」事实行，而不是拿今天的
    # 宜忌替她判（星期八判今天搬家、32号判今天开业都是错事实）。
    if _orig_spoken == "今天" and not any(
            w in msg for w in ("今天", "今日", "今晚", "今夜")) and \
            re.search(r"农历|阴历|旧历|闰|農曆|陰曆|舊曆|閏|"
                      r"星期[八九]|礼拜[八九]|禮拜[八九]|周[八九]|"
                      r"(3[2-9]|[4-9]\d)\s*[号日]|"
                      r"(下下|下|上|这|這|本)个?月\s*[0-9]{1,2}\s*[号日]|"
                      # R3323-P1-3：裸农历月名（腊月/冬月/正月不带「农历」
                      # 前缀）同样盖——「腊月祭灶好吗」月词无日落今天。
                      r"正月|冬月|腊月|臘月|"
                      r"\d{4}\s*年|\d{4}\s*[/\-.]", msg_n):
        # R2400（R128-P1-3）：不存在日不更新锚态——标 badday 让 commit
        # 跳过写锚（此前锚被覆成 {今天,场景}，下一问照样错判今天）。
        if ctx_out is not None:
            ctx_out["qk"] = "badday"
        return ["用户说的这个日子在黄历里不存在（比如星期八/32号/"
                "农历十三月/历法表界外的年份），温和点出它没这天，"
                "请她换个说法或换个日子；别按今天替她判宜忌。"]
    if not scene and not generic:
        # R229o：带日期词的泛问（「下周末出去玩行吗」「明晚聚餐行不行」）——
        # 没命中事项词也没命中泛问词，但用户在问某天的日子，给当日宜忌
        # 总表而不是零事实放手让模型瞎答。
        # R2400（R123-P2-7）：情绪倾诉（心情/网抑云/丧…）不是问日子——
        # 「最近心情不太好」「今晚网抑云」此前被时间词拖进当日宜忌总表，
        # 模型上下文塞着「宜嫁娶忌安葬」回共情，口径违和。倾诉求安慰零供给。
        if _MOOD_VENT_PAT.search(msg_n):
            return []
        # R3346（审-P1）：裸月日生问星座——「3月23日生的，是什么星座」
        # 原被日期词拖进择日通道，注入来年那天的宜忌（文不对题）。
        # 出生月日判座不需年份：直接给确定性星座事实行，不进宜忌通道。
        if "星座" in msg_n or re.search(r"出生|生[的了]", msg_n):
            _m_zd = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", msg)
            if _m_zd:
                try:
                    from guji.xingzuo import sun_sign as _ss
                    _sign = _ss(int(_m_zd.group(1)), int(_m_zd.group(2)))
                    if _sign:
                        return [
                            f"按公历{_m_zd.group(1)}月{_m_zd.group(2)}日出生，"
                            f"太阳星座是{_sign}（太阳星座看出生月日不看年份）；"
                            "按这个口径直接答，别引黄历宜忌。"]
                except Exception:
                    pass
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
    # R2349n（R77-P0-1）：同义族对冲词同样不作凭据（宜修造忌动土类）。
    _cfl = list(q.get("conflict") or [])
    _cfam = list(q.get("conflict_family") or [])
    _allcfl = sorted(set(_cfl) | set(_cfam))
    yi_str = "、".join(w for w in yi if w not in _allcfl) or "无"
    ji_str = "、".join(w for w in ji if w not in _allcfl) or "无"
    _cfl_note = (f"另有宜忌相冲项：{'、'.join(_allcfl)}（这些黄历自己都打架"
                 "（含同义词对冲，比如宜修造却忌动土），"
                 "按存疑处理，别当凭据念）。" if _allcfl else "")
    # R229o：「这周五」按本周已过日判（9/19 说这话指向 9/18）——事实行
    # 提醒这天已经过去，免得模型照着宜忌去「建议」一个回不去的日子。
    past_note = "（这天已经过去了）" if dt.date() < now.date() else ""
    # R3315（审-P2-1）：远日注记——「国庆」锚到明年 10/1 时，不点年份
    # 模型把它念得像刚过的那个。超 45 天的解析日在事实行里点明年份。
    _far_note = ""
    try:
        _dout = (dt.date() - now.date()).days
        if _dout > 45:
            _far_note = (f"（这天在{_dout}天后、已是{dt.year}年——"
                         "念日期时把年份或「明年」说清，"
                         "别让她以为在问近期）")
    except (TypeError, AttributeError):
        _far_note = ""
    facts = [f"{spoken}（{date_cn}）的黄历：宜【{yi_str}】；忌【{ji_str}】。"
             + _cfl_note + past_note + _far_note]

    # R2349（R64-P1-4）：「生日」——日期在用户本地档案，接口拿不到；
    # 明说解不动请她补日期，别拿今天替她判（实测静默按今天判成 P1）。
    if "生日" in msg_n:
        facts.append("用户说的「生日」缺具体日期（生日存在用户本地档案里，"
                     "这边拿不到），温和请她补一下生日或具体日期，"
                     "别按今天替她算。")
        if ctx_out is not None:
            ctx_out["qk"] = "generic"
        return facts

    # R2349（R64-P1-6）：「哪天/什么时候+事项」是找日问法——直接给
    # 近 45 天宜它的日子列表，别绕回今天的宜忌判定。
    # 但只改「无日期词」的：带着明确日期的（「分手后哪天复合」里的哪天
    # 是真问日）仍走正常判定 + 清单双给。
    _find_only = _find_intent and scene and spoken == "今天" \
        and not any(w in msg for w in ("今天", "今日", "今晚", "今夜"))
    if _find_only:
        # R3366（审-P1）：榜窗随问法前移/拉长——「下个月搬家的日子」
        # 榜窗从今天起算会把下月后半月腰斩；「今年适合X的时间段」该
        # 覆盖到年底（上限 92 天）。
        _fdt, _fspan, _flbl = dt, 45, "近45天"
        if "下个月" in msg_n or "下個月" in msg_n:
            _ny = dt.year + (dt.month == 12)
            _nm = (dt.month % 12) + 1
            _fdt = dt.replace(year=_ny, month=_nm, day=1)
            _flbl = "下个月起45天"
        elif "今年" in msg_n or "今年内" in msg_n:
            _fspan = min(92, (date(dt.year, 12, 31) - dt.date()).days)
            _flbl = "今年内"
        _gd = _hl_next_yi_days(_fdt, terms, span=_fspan)
        if _gd:
            facts.append(f"用户在问「哪天{scene}好」，{_flbl}里宜「{scene}」"
                         f"的日子：{'、'.join(_gd)}。直接给日子清单，"
                         "别按今天答宜忌。")
        else:
            # R3323-P0-1：ji-only 事项（诉讼/破土…历表只有忌没有宜）——
            # 「次优安排」是空话死路，历表的正确答案是避让榜。
            if all(t in _HUANGLI_JI_VOCAB for t in terms):
                _bd = _hl_bad_days(_fdt, terms, span=_fspan)
                facts.append(
                    f"用户在问「哪天{scene}好」——黄历对「{scene}」"
                    "只有忌没有宜，不存在吉日榜；正确口径是避开忌它的"
                    f"日子：{_flbl}里忌「{scene}」的日子有"
                    f"{('、'.join(_bd) + ' 等' if _bd else '零天')}。"
                    "温和说明这类事历表只讲避不讲宜，绕开就好。")
            else:
                facts.append(f"用户在问「哪天{scene}好」，{_flbl}没有宜"
                             f"「{scene}」的日子；给最近的次优安排口径。")
        if ctx_out is not None:
            ctx_out["qk"] = "findday"
        return facts

    # R2400（R128-P1-7）：(日词,场景) ≥2 组——按位置就近配对逐组判，
    # 旧逻辑拿最末场景配全部日子（「明天搬家和后天开业」判成后天开业+
    # 明天开业的鬼组合，搬家整条丢）。
    if (not _cmp and scene and len(_hits) >= 2
            and len(_cmp_words) >= 2 and _has_cmp):
        _sc_pos = sorted((msg_n.find(k), k) for _, _, k in _hits)
        _pairs, _seen_p = [], set()
        for _dp, _dw in _cmp_words:
            _sk = min(_sc_pos, key=lambda x: abs(x[0] - _dp))[1]
            if (_dw, _sk) not in _seen_p:
                _seen_p.add((_dw, _sk))
                _pairs.append((_dw, _sk))
        _out2 = [f"用户在对比 {len(_pairs)} 组「日子×事项」，逐组照实答，"
                 "别把她没问的组合拼起来："]
        for _dw, _sk in _pairs[:4]:
            _sub = _chat_facts_inner(_sk + _dw, now, None, None, _cmp=1)
            if _sub:
                _out2 += [f"「{_sk}·{_dw}」："] + _sub
        if ctx_out is not None:
            ctx_out["qk"] = "scene"
        return _out2

    if generic:
        facts.append("没列入当日宜忌的事项属中性，不是不支持，只是黄历没"
                     "为它背书，可照常安排；想要背书就挑宜它的日子。")
        if past_note:
            facts.append("该日期已过去，请温和点出、按复盘口径回应，"
                         "不要再给择日建议。")
        facts += _compare_extra_facts(msg, spoken, scene, now, _cmp)
        if ctx_out is not None:
            ctx_out["qk"] = "generic"
        return facts

    hit_yi = [t for t in terms if any(t in w or w in t for w in yi)]
    # R2349n（R77-P0-1）：忌侧按同义族判——只在宜侧真有命中时把
    # 「宜」降级为「宜忌都有」（宜修造忌动土的日子问搬家）。纯忌侧
    # 族命中（这天压根没提搬家）仍是中性，不当作忌——那是过度引申。
    hit_ji = [t for t in terms if any(t in w or w in t for w in ji)]
    if hit_yi:
        _fam = set()
        for _t in terms:
            _fam |= set(huangli_mod._veto_terms(_t))
        hit_ji = sorted(set(hit_ji) | {t for t in _fam
                        if any(t in w or w in t for w in ji)})
    # R229z续2：已过去的日子不给「近45天宜X」——从过去日起扫的全是过去日，
    # 且与「不要再给择日建议」的复盘指令自相矛盾。
    # R229z续8（R8 P1-1）：good_part 只在忌/中性分支引用——宜判定的路径
    # 不再白扫 45 天。
    def _good_part() -> str:
        if past_note:
            return ""
        g = _hl_next_yi_days(dt, terms)
        # R2349（R64-P2）：「宜分手/宜解除」直译刺耳——换「适合办X」口径。
        # R2349q（R82-P1-1）：45 天无宜日时给空串 → prompt 要求「报宜日」
        # 与「不许编日子」自相矛盾，模型只能违一条。事实行明说没有，
        # 让模型直说没翻到。
        return (f"近45天适合{scene}的日子：{'、'.join(g)}。"
                "想要黄历背书可挑这几天。" if g
                else f"近45天里没翻到宜「{scene}」的日子：直说没翻到，"
                     "不要自己编日子。")
    # R229v：已过去的日子不能只靠宜忌行尾巴的括号——模型实测会漏看，
    # 对着 9/18 的「宜面试」说出「周五冲一把」。把标记嵌进判定句本体，
    # 并要求回复口径改为复盘/温和指出而非择日建议。
    past_mid = "（这天已经过去）" if past_note else ""
    if hit_yi and not hit_ji:
        verdict = (f"黄历判定：{date_cn}{past_mid} 宜「{scene}」"
                   f"（宜项含【{'、'.join(hit_yi)}】）。")
    elif hit_ji and not hit_yi:
        # R3102（specs/010）：忌判定带「为什么忌」——月破/杨公忌/四离
        # 等硬凶日是把凭据摆给用户，不只是念忌项。
        _flags = [f for f in (q.get("day_flags") or []) if f]
        _why = (f"；且这天逢{'、'.join(_flags[:2])}，硬凶日凭据更实"
                if _flags else "")
        verdict = (f"黄历判定：{date_cn}{past_mid} 忌「{scene}」"
                   f"（忌项含【{'、'.join(hit_ji)}】{_why}）；"
                   f"已安排也不必慌，放缓节奏即可。{_good_part()}")
    elif hit_yi and hit_ji:
        # R2349r（R82-P2-5）：宜忌同现的词在显示侧被剔为「相冲存疑」，
        # 判定句却仍拿它当凭据——同框互搏。显式点名存疑口径对齐。
        _both = sorted(set(hit_yi) & set(hit_ji))
        _conf = (f"其中【{'、'.join(_both)}】宜忌同现、按存疑处理，"
                 "别当凭据念；" if _both else "")
        verdict = (f"黄历判定：{date_cn}{past_mid} 「{scene}」宜忌都有。"
                   f"宜【{'、'.join(hit_yi)}】也忌【{'、'.join(hit_ji)}】；"
                   f"{_conf}想做就把节奏放缓，不赶大动作。")
    else:
        that_day = "今天" if dt.date() == now.date() else f"{spoken}（{date_cn}）"
        verdict = (f"黄历判定：{date_cn}{past_mid} 宜忌都没直接提「{scene}」，中性，"
                   f"不是不支持，只是黄历{that_day}没为它背书，{scene}可照常安排。"
                   f"{_good_part()}")
    if past_mid:
        verdict += "（该日期已过去，请温和点出、按复盘口径回应，不要再给择日建议。）"
    # R233g（R44-P1-7）：医疗类事项（求医/治病/手术/体检等）判词必须带
    # 「听医生的」口径——不让黄历背书医疗决策。
    if set(terms) & _MED_SCENE_TERMS:
        verdict += "（医疗事项：请在回复里带一句「看病以医生为准，黄历不作数」的口径。）"
    facts.append(verdict)
    # R2400（R140-followup）：真机回归抓到模型口播日期口误——判定日
    # 09-25 被念成「10月25号」。补念法约束：照判词写的念不换算。
    facts.append("回复里念到上述日期时照判词里写的月日原样念，不要自己换算或改写。")
    facts += _compare_extra_facts(msg, spoken, scene, now, _cmp)
    if ctx_out is not None and "qk" not in ctx_out:
        ctx_out["qk"] = "scene"
    return facts


# R2400（R123-P2-2）：「明天和后天哪天好」——_hl_day_part if 链只回
# 首个命中词，对比的另一日此前静默丢弃（只判后天、明天当没提过）。
# 检出对比语境时，把另一日的判定一并供给，模型才能如实对比。
# R2400（R126-P1-6/P2-6）：换 regex 整体匹配修两个坑——①裸「周X/
# 星期X/礼拜X」（周五、下周一）收进来；②`w in msg` 子串碰撞
# （「下周五」先被「下周」截胡算错天）。长形优先排好序。
_COMPARE_DAY_RE = re.compile(
    r"下下周末|下下週末|下周末|下週末|下下周|下下週|大后天|大後天|"
    r"大前天|过两天|過兩天|下星期[一二三四五六日天一二]|"
    r"下礼拜[一二三四五六日天一二]|上星期[一二三四五六日天一二]|"
    r"上礼拜[一二三四五六日天一二]|下周[一二三四五六日天]|"
    r"下週[一二三四五六日天]|上周[一二三四五六日天]|上週[一二三四五六日天]|"
    # R2400（R128-P1-6）：「这周五/本週三」复合形必须排在裸「这周/本周」
    # 之前——旧表先吃上「这周」两字把「五」丢掉，造出幻日「这周=今天」。
    r"(?:这|這|本)个?(?:周|週|星期|禮拜|礼拜)[一二三四五六日天]|"
    r"本周|本週|这周|這週|本星期|星期[一二三四五六日天一二]|"
    r"礼拜[一二三四五六日天一二]|周[一二三四五六日天]|週[一二三四五六日天]|"
    r"后天|後天|前天|前日|明天|明日|明儿|明兒|明晚|后晚|後晚|今晚|"
    r"今夜|昨晚|昨夜|昨天|昨日|今天|今日|周末|週末|下周|下週|"
    # R3230：数字相对日——「三天后还是五天后」对比句的词位表缺它会
    # 静默吃掉前者（_compare 分支按句中首个日词定主判日）。
    r"(?:过|過)?(?:半|[0-9]{1,3}|[一二两三四五六七八九兩]?十"
    r"[一二三四五六七八九]?|[一二两三四五六七八九兩]+)[个個]?"
    r"(?:天|日|周|週|星期|礼拜|禮拜)(?:后|後|前)|"
    r"(?:半|[0-9]{1,2}|[一二两三四五六七八九兩]?十[一二三四五六七八九]?|"
    r"[一二两三四五六七八九兩]+)[个個]月(?:后|後|前)")


def _compare_extra_facts(msg: str, spoken: str, scene: str,
                         now: datetime, _cmp: int) -> list[str]:
    """对比语境检出后的「另一日」事实行（depth 防递归）。"""
    if _cmp:
        return []
    if not re.search(r"和|跟|与|还是|或者|或|哪个|哪天|比谁|对比|比较",
                     msg):
        return []
    # 按出现顺序收集全部「另一日」（spoken 当日已在主判定里）——
    # 「这周五和下周五和周六」只补首个的旧毛病顺手修掉。
    # R2400（R128-P2-2）：日词按分句过滤——日词所在分句没「在比日」
    # 语境（哪个/哪天/适合/吗/好/行/可以/宜/忌/?）的是叙事日期
    #（「昨天和我妈吵架了」里的昨天），不拉进对比。
    words: list[str] = []
    _seg_bounds = [m for m in
                   re.finditer(r"[^，。！？；,.!?;~～…\n]+", msg)]
    for m in _COMPARE_DAY_RE.finditer(msg):
        w = m.group(0)
        if w in ("这", "這") or w == spoken or w in words:
            continue
        _cl = next((_s.group(0) for _s in _seg_bounds
                    if _s.start() <= m.start() < _s.end()), "")
        if not re.search(
                r"哪[个家天]|适合|合适|可以|能|[宜忌]|好|行|成|[吗吧呢？?]|"
                r"怎么样|怎样|如何", _cl):
            continue
        words.append(w)
    out: list[str] = []
    for w in words[:3]:
        sub = _chat_facts_inner((scene or "") + w, now, None, None,
                                _cmp=1)
        if sub:
            out += [f"用户还在对比「{w}」，那天的口径："] + sub
    # R2400（R128-P2-1）：对比日超 3 个截断要有「等」提示，不是静默丢尾。
    if len(words) > 3:
        out.append(f"（她还提到 {len(words) - 3} 个日子没逐一展开。"
                   "口径上按「这些日子之外还有」说，别当只有这三个。）")
    return out


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
    # R2350l：命名牌阵——key 必须在库内，张数=牌阵长度。
    _positions = None
    _spread_name = ""
    if req.spread:
        _sp = tarot_mod.NAMED_SPREADS.get(req.spread)
        if _sp is None:
            raise ValidationError("没这个牌阵，换一个试试")
        _spread_name, _positions = _sp
    # R2350k：自点牌背——cards 给了就用选定下标成牌（越界/重复在
    # draw_picked 内收敛），否则照旧 seed 抽。
    if req.cards:
        # R2354（R112-P2-4/5）：静默瘦身防线——重复/越界原来悄悄
        # 丢弃出更少张；张数≠阵位数时半截结果顶着全阵名。显式拒。
        _seen: set[int] = set()
        _bad = False
        for _ci in req.cards:
            if (not isinstance(_ci, int) or _ci < 0
                    or _ci >= len(tarot_mod.DECK) or _ci in _seen):
                _bad = True
                break
            _seen.add(_ci)
        if _bad:
            raise ValidationError("选的牌里有重复或没对上号，再点一次试试")
        if _positions and len(req.cards) != len(_positions):
            raise ValidationError(
                _spread_name + "要 " + str(len(_positions)) +
                " 张牌：牌的数目对不上，再点一次试试")
        draws = tarot_mod.draw_picked(req.cards, req.seed,
                                      positions=_positions)
        if not draws:
            raise ComputeError("选的牌没对上号，再点一次试试")
    else:
        draws = tarot_mod.draw(seed=req.seed,
                               n=len(_positions) if _positions else req.n,
                               positions=_positions)
    cards = _draw_dicts(draws)
    interpretation = interpreter.interpret_tarot(cards, req.question)
    out = {
        "seed": req.seed,
        "n": len(cards),
        "draws": cards,
        # R2350l：牌阵名回显（默认空串，前端副标用）
        "spread": _spread_name,
        # R2354（R112-P1-2/3）：分享 replay 需要原样还原——
        # spread_key 让重放走同一牌阵；picked 标记自点牌（URL
        # 带 cards 索引重放 draw_picked 而非 seed 重抽）。
        "spread_key": req.spread if _positions else "",
        "picked": bool(req.cards),
        "interpretation": interpretation,
        # R3349（R3335-低）：picked 入 warm——自点牌首行「你自己挑的牌」
        "warm": voice.warm_tarot(cards, interpretation, req.question,
                                 picked=bool(req.cards) and
                                 getattr(req, "record", True)),
        # R218a-巡2（N-01）：echo question 让前端 tarotQuestionHook 真生效
        "question": req.question,
        # R221b：交叉引用收口 7/7——塔罗不收生日，只引"今天"的值宫
        "cross_ref": _cross_ref_tarot(cards, today_iso=req.client_date),
        # R3154：ai_polish 恒在（同步段永 None），ai_task_id 条件追加
        "ai_polish": None,
    }
    # R230z（R36-P1-1）：塔罗进台账；摘要用问题或张数
    # R2350g（R104-P1-3）：record=false 的分享重放不进接收方台账/牌册。
    if getattr(req, "record", True):
        paipan_history.save_async(
            {"seed": req.seed, "n": len(cards),
             "question": req.question, "spread": _spread_name},
            out, rtype="tarot",
            # R2354（R112-P3-6）：账本名原来按 req.n——celtic 记「3 张
            # 牌阵」实抽 10。按实际抽数+阵名。
            name=(req.question or
                  ((_spread_name + " · " + str(len(cards)) + " 张")
                   if _spread_name else f"{len(cards)} 张牌阵")))
    # R3154：塔罗接 AI 解读块——牌面坐标+综合口径行进 facts
    # R3157：record=False 是分享重放——爬虫可达，独立小桶
    ai_task_id = llm_polish.spawn_ai_task(
        llm_polish.facts_tarot(out, out.get("warm"), req.question),
        req.question,
        rate_key=("ai" if getattr(req, "record", True) else "ai_replay"),
        rate_limit=(60 if getattr(req, "record", True) else 15))
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    # R3124b：判词升格信道用结果 ref
    out["result_ref"] = _stash_result("tarot", out)
    return out


def tarot_draw(req) -> dict:
    """单张抽牌 + 确定性关键词转述（首页快速入口用）。

    契约（R178b，D-228b）：顶层键保持与重构前一致的 `card` + `interpretation`
    两个。原第三个键 `model`（LLM 模型名）随 LLM 层移除而消失——引擎标识
    改由 `interpretation.engine` 携带，不再单独占一个顶层键。
    **不新增 `draws` 键**：多张牌阵是 `/api/tarot` 的职责，本端点只给单张，
    否则同一份牌面在两个键里各存一份，前端不知该信哪个。
    """
    req.validate_ranges()   # R2364：与其他入口同纪律——question 剥控制字
    draws = tarot_mod.draw(seed=req.seed, n=req.n)
    if not draws:
        raise ComputeError("抽牌失败")
    cards = _draw_dicts(draws)
    card = cards[0]
    interpretation = interpreter.interpret_tarot(cards, req.question)
    out = {
        "card": {"name": card["name"], "upright": card["upright"],
                 "upright_kw": card["upright_kw"],
                 "reversed_kw": card["reversed_kw"],
                 "meaning": card["meaning"]},
        "interpretation": interpretation,
        "warm": voice.warm_tarot(cards, interpretation, req.question),
    }
    # R3150c：首页快速单抽也挂快照——抽一张来聊同样要判词口径一致。
    out["result_ref"] = _stash_result("tarot", out)
    return out


def dream(req) -> dict:
    """解梦（R3178）：写死象征词库三件套（老话/回声/微行动）——
    不判吉凶不预言。命中给解读，未命中老实说没收录并邀她讲画面。

    契约与其他占卜面同形：warm.reply 逐行渲染 + result_ref 快照 +
    ai_task_id 轮询解读块。梦境文本按 question 同纪律进台账摘要
    （截断在 paipan_history 侧兜底）。"""
    req.validate_ranges()
    # R3214：表单路径此前不做繁体归一（聊天路径 chat_dream_facts 有
    # _t2s）——「夢見掉頭髮」漏键。拉齐。
    r = dream_mod.interpret_dream(_t2s(req.text))
    out = {
        "symbols": r["symbols"],
        "matched": r["matched"],
        "warm": {"reply": r["reply"]},
        "disclaimer": r["disclaimer"],
        # R3214：微行动提为独立字段——卡面单挂「小动作」锚点，
        # 不再埋在 reply 平文行里。
        "action": r.get("action") or "",
        # R3214：卡面回显她的梦（截 120 字，长描述提交后她能对上号）
        "echo": req.text[:120],
        # 各面同契约：同步段恒 None，解读走 ai_task_id 轮询
        "ai_polish": None,
    }
    # req_dict 走 question 键（非 text）——敏感词剥名/列清逻辑在
    # paipan_history 侧只认这个键，换键等于绕过危机足迹保护。
    # R3214：列表名不再回显梦原文（私密文本不该出现在列表行）——
    # 命中用象征名，未命中用「一个梦」。
    # R3265（R3247-P2）：symbol.name 是内部键式命名（掉头发/秃了、
    # 自己出事/死了），台账标题取斜杠前段展示名，列表不读术语。
    _dname = ("解梦 · " + r["symbols"][0]["name"].split("/")[0]
              if r["symbols"] else "解梦 · 一个梦")
    paipan_history.save_async(
        {"question": req.text[:200]},
        out, rtype="dream",
        name=_dname)
    ai_task_id = llm_polish.spawn_ai_task(
        dream_mod.facts_dream(out), req.text,
        rate_key="ai", rate_limit=60)
    if ai_task_id:
        out["ai_task_id"] = ai_task_id
    out["result_ref"] = _stash_result("dream", out)
    return out


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

# R3091（specs/010-P3）：日签宜忌词白话表——daily.do/dont 改挂当日
# 黄历 yi/ji 真词（盘点 agent Top-2：池子级 do/dont 与当日事实脱钩）。
# 表外古词原样透出（书上的词，翻译缺位不编造）。
_HL_TERM_SPOKEN: dict[str, str] = {
    "出行": "出远门", "移徙": "搬家挪窝", "入宅": "搬新家",
    "嫁娶": "办喜事", "纳采": "提亲相亲", "订盟": "定亲签约",
    "问名": "相亲问名", "开市": "开业开张", "开业": "开业开张",
    "动土": "动土开工", "修造": "装修修缮", "上梁": "上梁封顶",
    "竖柱上梁": "上梁封顶", "安床": "安床挪床", "合帐": "挂帐安床",
    "求医": "看医生", "治病": "治病调理", "求医疗病": "看医生",
    "祭祀": "祭祖祈福", "祈福": "许愿祈福", "求嗣": "备孕添丁",
    "会友": "约朋友聚", "赴任": "入职赴任", "上任": "入职赴任",
    "谒贵": "见重要的人", "纳财": "进账收款", "出货财": "出货变现",
    "交易": "谈生意", "立券": "签合同", "开仓": "动用存款",
    "沐浴": "好好洗个澡", "扫舍": "大扫除", "理发": "理发",
    "整手足甲": "剪指甲", "栽种": "种花种草", "牧养": "养宠物",
    "破土": "破土动工", "安葬": "安葬", "解除": "断舍离消灾",
    "经络": "按摩调理", "酝酿": "启动筹备", "畋猎": "户外活动",
    "取渔": "钓鱼玩水", "乘船": "坐船", "渡水": "过河水边",
    "登高": "爬山登高", "归宁": "回娘家", "入学": "开学上课",
    "习艺": "学手艺", "平治道涂": "修路整地", "修饰垣墙": "刷墙翻新",
    "伐木": "砍树伐木", "捕捉": "除虫除害", "裁衣": "做衣服",
    "冠笄": "成年礼", "进人口": "添丁进口", "补垣": "补墙堵漏",
    "塞穴": "堵洞防患", "造屋": "盖房", "架马": "搭架开工",
    "开渠": "挖渠引水", "穿井": "打井", "结网": "织网筹备",
    "分居": "分开住", "词讼": "打官司", "诉讼": "打官司",
    "远行": "出远门", "苫盖": "遮盖防雨",
    # R3314（R3311-中6）：建除/星宿表里的古词漏收——「狩猎」裸贴
    # 给今天的用户太穿越。补口语译名（丧葬类保留原词庄重感）。
    "狩猎": "户外活动", "田猎": "户外活动", "登山": "爬山登高",
    "破屋坏垣": "拆旧翻新", "筑堤": "加固防护", "行丧": "丧仪",
    "出官": "赴任履职", "求名": "求名赶考", "平整": "平整土地",
}


def _hl_spoken(terms: list[str], n: int = 3) -> str:
    """黄历宜忌词列 → 白话串（前 n 个）。

    同译名去重（出行/远行→出远门 同日并存时只留一个，selftest
    daily.advice.dedup 闸对「、」分片唯一性有钉）。"""
    out: list[str] = []
    for t in terms:
        s = _HL_TERM_SPOKEN.get(t, t)
        if s not in out:
            out.append(s)
        if len(out) >= n:
            break
    return "、".join(out)


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


# R3314（R3311-中5）：判词首句同质化——整月由日干五行驱动，
# 「火气比较足」连开 21 天。每行各备两句、按日子轮换（10 个变体，
# ≥8），强元素句挪到关系事实段之后——日子不同先说的先变。
_STRONG_LEAD: dict[str, tuple[str, str]] = {
    "木": ("木气比较足：生长舒展的劲儿今天更明显",
         "木气今天偏旺：想往外舒展的那股劲更足"),
    "火": ("火气比较足：这股热乎劲儿今天更明显",
         "火气今天偏旺：冲劲儿足，也更容易上头"),
    "土": ("土气比较足：厚稳托底的劲儿今天更明显",
         "土气今天偏旺：稳当和固执一起被放大"),
    "金": ("金气比较足：干脆利落劲儿今天更明显",
         "金气今天偏旺：利落决断的劲更足"),
    "水": ("水气比较足：绕得开找得到的劲儿今天更明显",
         "水气今天偏旺：灵活和流动感更足"),
}


def fortune_summary(calc_out: dict, day: "datetime | None" = None) -> str:
    """从运算事实转述运势一句话（纯坐标转述，不新增结论）。

    R2349g（R68-P2）：copy_bank 的 levels 四档恒在时 daily() 不会走这里
    ——仅当 copy_bank 缺失/损坏时的兜底路径，保留勿删。
    """
    if not calc_out:
        return "今天的运势卡没算出来，稍后再看看～"
    # R216b 续3（UX 队列 U-010）：原版「五行中火土偏旺；有1处地支自刑，
    # 宜稳不宜争；今日日运：庚午」术语裸抛——每条跟一句人话短注。
    parts = []
    rels = calc_out.get("relations") or []
    bad = [r for r in rels if r.get("type") in _BAD_RELS]
    good = [r for r in rels if r.get("type") in _GOOD_RELS]
    # R3314：关系事实段先行——逐日变化度高于五行行。
    if bad:
        # R3316（审-P2）：术语括号（相害/自刑）是内部盘语——summary
        # 是上海报 headline 的最大传播面，受众读不懂。人话段保留，
        # 术语明细留在 relmap 专业层。
        parts.append(f"有{len(bad)}处小别扭，容易自己跟自己较劲，稳一点就好")
    if good:
        parts.append(f"有{len(good)}处顺劲，有人搭把手，事情好推")
    strong = (calc_out.get("five_elements") or {}).get("strong") or []
    if strong:
        _pick = ((day.toordinal() if day else 0)
                 % len(_STRONG_LEAD["木"]))
        parts.append("；".join(
            _STRONG_LEAD.get(e, (f"{e}气比较足：这方面的特质今天更明显",) * 2)[_pick]
            for e in strong))
    # R231a（R36 口播残留）：「今天的干支是丁酉」是纯坐标转述，
    # 对普通用户无意义且日期词不随查询日漂移——整行删除，不补假锚点。
    if not parts:
        return "今天五行平和，无大冲大合，平平稳稳就是福 ✨"
    return "；".join(parts) + "。"


def daily(date_str: str | None = None,
          # R2349l（R73-P1-3）：bday=YYYY-MM-DD 用户生日——
          # 返回 personal 字段（日主×当日十神），不进缓存。
          bday: str | None = None) -> dict:
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
        # R2502：解析后规整回规范形——Py3.11+ fromisoformat 会收下
        # 20260101/2026-W01-1 这类变体，原样下传会让 bazi_calc 的
        # split('-') 炸进降级卡，还以非规范串当 daily_cache 键落脏行。
        date_str = _parse_iso_date(date_str).isoformat()
    date_str = date_str or _today_cn().isoformat()
    # R2349l（R73-P1-3）：bday=用户生日 → 「我的日主 × 今天日干」十神行。
    # personal 含用户生辰，绝不进 daily_cache（按日缓存会串用户）。
    _personal = None
    if bday:
        # R2502：bday 非法值此前被裸 except 静默吞成「无 personal」——
        # 与 ?date=garbage→400 的契约不对称。边界即拒。
        _bd = _parse_iso_date(bday)
        try:
            _ub = bazi_compute(_bd.year, _bd.month, _bd.day, 12, "女")
            _ug = (_ub.day or "")[0]                    # 日主天干
            _dg, _dzz = huangli_mod.day_ganzhi(
                datetime(*map(int, date_str.split("-")), 12))
            _god = ten_god(_ug, _dg) if _ug else ""
            _lb = voice.TEN_GOD_WARM.get(_god, ("", ""))[0]
            # R2519（深度收尾）：personal 行从纯描述加「适合」行动尾——
            # 首页大卡此前只告诉用户「今天是什么日」不说「能干什么」，
            # 复用 TEN_GOD_ACTION 二联（取适合项，留意项留给结果页）。
            _act = voice.TEN_GOD_ACTION.get(_god)
            _personal = {
                "god": _god, "label": _lb,
                "line": (f"你的日主 {_ug} × 今天 {_dg} ， "
                         f"今天是你的「{_lb or _god}」日"
                         + (f"，适合{_act[0]}" if _act else "")),
            }
            # R2349l（R73-P1-14）：流年十神——日主 × 流年天干（立春口径）。
            _yg, _yy = _liunian(date.fromisoformat(date_str))
            _ygod = ten_god(_ug, _yg[0]) if _ug else ""
            _ylb = voice.TEN_GOD_WARM.get(_ygod, ("", ""))[0]
            _personal["year_gz"] = _yg
            _personal["year_god"] = _ygod
            _personal["year_line"] = (
                f"{_yy} 是你的"
                f"「{_ylb or _ygod}」年（流年 {_yg}）"
                if _ug else "")
            # R3245（用户实测「填什么生日都是小吉」）：个人冲合修正层。
            # 通判 level/summary 算的是「今天这一天」的盘（全日通胜口径），
            # 跟你生日无关——对你个人的顺逆另判：今日支 × 你的日支（权重
            # 最高，日支是自身/配偶宫）→ 落空再看年支（外围层）。
            _u_db = (_ub.day or "")[1:2]         # 你的日支
            _u_yb = (_ub.year or "")[1:2]        # 你的年支
            _mrel = None
            for _zb, _kk in ((_u_db, "日支"), (_u_yb, "年支")):
                if _zb and _dzz:
                    _rp = _rel_pair(_dzz, _zb)
                    if _rp:
                        _mrel = (_rp[0], _kk, _zb)
                        break
                    if _san_he([_dzz, _zb]):
                        _mrel = ("半合", _kk, _zb)
                        break
                    if _zb == _dzz:
                        # 同支值日＝伏吟（辰午酉亥亦称自刑）——旧事重提、
                        # 原地打转的象，权重低于对冲但强于无关系。
                        _mrel = ("伏吟", _kk, _zb)
                        break
            if _mrel:
                _mty, _mk, _mz = _mrel
                _mverdict = {
                    "六冲": "小凶" if _mk == "日支" else "轻冲",
                    "相刑": "小挫" if _mk == "日支" else "小绊",
                    "相害": "小绊" if _mk == "日支" else "小绊",
                    "六合": "合缘" if _mk == "日支" else "岁合",
                    "半合": "半合",
                    "伏吟": "伏吟" if _mk == "日支" else "岁吟",
                }.get(_mty, "")
                if _mty == "六冲":
                    _ml = (f"今天{_dzz}冲你的{_mk}{_mz}——对你来说气性偏大，"
                           "重要决定缓一缓更稳" if _mk == "日支" else
                           f"今天{_dzz}冲你的{_mk}{_mz}——外围有点小波动，"
                           "出门多留神就好")
                elif _mty == "相刑":
                    _ml = (f"今天{_dzz}和你的{_mk}{_mz}相刑——容易跟自己较劲，"
                           "别苛责自己" if _mk == "日支" else
                           f"今天{_dzz}和你的{_mk}{_mz}相刑——小拧巴，不碍大事")
                elif _mty == "相害":
                    _ml = (f"今天{_dzz}和你的{_mk}{_mz}相害——小磕绊多一点，"
                           "慢一点就没事" if _mk == "日支" else
                           f"今天{_dzz}和你的{_mk}{_mz}相害——外围小磕绊，"
                           "不必放心上")
                elif _mty == "六合":
                    _ml = (f"今天{_dzz}合你的{_mk}{_mz}——人缘顺、有人搭手，"
                           "开口求人正合适" if _mk == "日支" else
                           f"今天{_dzz}合你的{_mk}{_mz}——大环境跟你合拍")
                elif _mty == "伏吟":
                    _ml = (f"今天{_dzz}和你的{_mk}{_mz}伏吟——旧事容易重提，"
                           "适合收尾不适合开新局" if _mk == "日支" else
                           f"今天{_dzz}和你的{_mk}{_mz}伏吟——老主题回来绕一圈，"
                           "平常心接住就好")
                else:  # 半合
                    _ml = (f"今天{_dzz}和你的{_mk}{_mz}半合——暗中有顺劲，"
                           "顺势推一把")
                _personal["mine"] = {
                    "verdict": _mverdict, "line": _ml,
                    "tone": "down" if _mty in ("六冲", "相刑", "相害")
                            else ("up" if _mty in ("六合", "半合") else "flat")}
            elif _dzz:
                _personal["mine"] = {
                    "verdict": "无冲无合",
                    "line": f"今天{_dzz}日跟你的盘不冲不合，通判照样走",
                    "tone": "flat"}
            # R3314（R3311-高2）：流年最小确定性卡——
            # ① 年度签：流年干支 + 五行基调（干支元素直读）；
            # ② 犯太岁：流年支 × 用户年支 值/冲/刑/害/破（传统五档）；
            # ③ 太岁位/岁破位：流年支方位与对冲支方位。
            _lnz = _yg[1] if _yg else ""
            _lnwx = (GAN_ELEM.get(_yg[0], "") +
                     voice.ZHI_ELEMENT.get(_lnz, "")) if _yg else ""
            _ts_kind = ""
            if _u_yb and _lnz:
                if _u_yb == _lnz:
                    _ts_kind = "值太岁"
                elif CHONG.get(_lnz) == _u_yb:
                    _ts_kind = "冲太岁"
                elif (_lnz, _u_yb) in XING or (_u_yb, _lnz) in XING:
                    _ts_kind = "刑太岁"
                elif XIANG_HAI.get(_lnz) == _u_yb:
                    _ts_kind = "害太岁"
                elif XIANG_PO.get(_lnz) == _u_yb:
                    _ts_kind = "破太岁"
            _personal["year_detail"] = {
                "wx": _lnwx,
                "taisui": _ts_kind,
                "ts_dir": _ZHI_DIR.get(_lnz, ""),
                "sp_dir": _ZHI_DIR.get(CHONG.get(_lnz, ""), "")}
        except ComputeError:
            _personal = None
        except Exception:
            _personal = None
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
            # R2349t（R87-P0-1）：cv=5——cv≤4 的行可能含 personal
            # 脏字段（请求方生辰派生），抬代次让存量脏行一律重算覆盖。
            # R3091：cv=6——summary 事实句/do/dont 黄历真词口径。
            # R3304：cv=7——cv=6 行 do/dont 含「宜：/忌：」内嵌前缀。
            if _c.get("cv") == 7 and (not _want or _c.get("noble") == _want):
                # R2349k（R72-A2）：festival 是派生字段不入缓存语义——
                # 现算随包回（旧缓存行也能拿到节日行）。
                _r = {"date": date_str, **_c, "cached": True,
                      "festival": _festival_for(
                          _d0, _term_name_for(_d0)),
                      "moon": _moon_for(_d0),
                      "term": _term_banner(_d0),
                      # R2349l：lucky/mercury 是 per-date 派生键——cv4
                      # 之前落库的旧缓存行没有它们，现算随包回。
                      "lucky": _c.get("lucky") or _lucky_for(_d0),
                      "mercury": (_c.get("mercury")
                                  or _mercury_state(_d0)),
                      "venus": (_c.get("venus")
                                or _venus_state(_d0)),
                      "mars": (_c.get("mars")
                               or _mars_state(_d0)),
                      # R3261：财神方位同为 per-date 派生键——旧缓存行
                      # 现算随包回，不抬 cv 代次。
                      "money_dir": (_c.get("money_dir")
                                    or huangli_mod.caishen_fang(
                                        datetime(_d0.year, _d0.month,
                                                 _d0.day, 12))),
                      # R3317-G：旧缓存行无 daily_card——同口径现算随包回
                      "daily_card": (_c.get("daily_card")
                                     or _daily_card_for(_d0)),
                      # R3326（审-P0）：cv=7 存量行（R3304→R3325 间写入）
                      # 无 outfit——命中即永无穿搭包。同口径现算回填。
                      "outfit": (_c.get("outfit")
                                 or _outfit_for(_d0)),
                      # R3601：week_sky 同口径 per-date 现算——旧缓存行随包补。
                      "week_sky": (_c.get("week_sky")
                                   or _week_sky(_d0)),
                      # R3318：cv<6 时代存的行没有 lunar 锚——同口径现算
                      "lunar": (_c.get("lunar")
                                or _daily_lunar_str(_d0))}
                if _personal:
                    _r["personal"] = _personal
                else:
                    # R2349t（R87-P0-1）：防御存量脏行——不带 bday 的
                    # 请求绝不能拿到上一个用户的 personal 行。
                    _r.pop("personal", None)
                # R3150b：缓存命中路径同样挂快照 ref——走缓存≠没卡。
                # personal 行在 stash 前剔除：快照不落库但仍是共享
                # 内存件，不该进别的请求方的生辰派生字段。
                _stash = {k: v for k, v in _r.items() if k != "personal"}
                _r["result_ref"] = _stash_result("daily", _stash)
                return _r
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
            # R2350c（R97-P2-4）：相邻日还会撞首项（16 池双抽，实测
            # 9-21/9-22 同签）——再把「昨天抽过的」从今日池剔除，
            # 明天预告不再有复读感。池子剔空时兜底原池。
            _yd = (d - timedelta(days=1)).isoformat()
            _py1 = _pick(_db["yi"], _yd, "y")
            _py2 = _pick([x for x in _db["yi"] if x != _py1] or _db["yi"],
                         _yd, "y2")
            _yp = [x for x in _db["yi"] if x not in (_py1, _py2)] or _db["yi"]
            _y1 = _pick(_yp, date_str, "y")
            _y2 = _pick([x for x in _yp if x != _y1] or _yp,
                        date_str, "y2")
            do_str = _y1 + "、" + _y2
            _pj1 = _pick(_db["ji"], _yd, "j")
            _pj2 = _pick([x for x in _db["ji"] if x != _pj1] or _db["ji"],
                         _yd, "j2")
            _jp = [x for x in _db["ji"] if x not in (_pj1, _pj2)] or _db["ji"]
            _j1 = _pick(_jp, date_str, "j")
            _j2 = _pick([x for x in _jp if x != _j1] or _jp,
                        date_str, "j2")
            dont_str = _j1 + "、" + _j2
        # R3091（specs/010-P3）：do/dont 改挂当日黄历真宜忌——池子句
        # 与当日事实脱钩（盘点 agent Top-2）。日无真词时回退池子。
        _dq_dt = datetime(d.year, d.month, d.day, 12)
        try:
            _dq = huangli_mod.day_query(_dq_dt)
            _dyi, _dji = _dq.get("yi") or [], _dq.get("ji") or []
            if _dyi:
                # R3304（审-P1）：标签归展示层、值归数据层——API 不再
                # 预制「宜：/忌：」前缀（海报行签「宜试试」+「宜：宜：」
                # 双前缀事故根因）。各消费方自己挂签。
                do_str = _hl_spoken(_dyi)
            if _dji:
                dont_str = _hl_spoken(_dji)
        except Exception:
            pass
        # R3091：summary 事实句优先——有盘面关系/失衡就说事实，
        # 情绪池降级为语气后缀；事实为空才整句走池。
        _mood = summary if (_db and level in (_db.get("levels") or {})) \
            else ""
        _fact_sum = fortune_summary(calc_out, _dq_dt)
        if _fact_sum and not _fact_sum.startswith("今天的运势卡") \
                and not _fact_sum.startswith("今天五行平和"):
            summary = (_fact_sum.rstrip("。")
                       + ("；" + _mood if _mood else "。"))
        else:
            summary = _mood or _fact_sum
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
        # R3314（R3311-中2）：日卡补农历日期+日干支锚——月相按
        # 初一十五跑、七夕/中元全是农历节，卡面却只有公历，「今天
        # 新月」得靠用户自己悟=初一。派生字段确定性可查。
        _lunar_str = _daily_lunar_str(d)
        result = {
            "date": date_str,
            "cv": 7,                     # R3304：do/dont 不再预制宜忌前缀
            "level": level,
            "lunar": _lunar_str,
            "summary": summary,
            "noble": noble_str,
            "noble_liuhe": noble_lh,
            "do": do_str,
            "dont": dont_str,
            "cached": False,
            # R2349k（R72-A2）：节日行与黄历卡同源
            "festival": _festival_for(d, _term_name_for(d)),
            # R2349l（R73-P1-4/P2-9）：开运三件套+水逆态——全是当日
            # 干支/历表的确定性派生，随缓存同口径存取。
            "lucky": _lucky_for(d),
            # R3325：五行穿搭五档——玄学×穿搭交叉垂类（调研证实）
            "outfit": _outfit_for(d),
            # R3261（R12）：财神方位——日干查表确定性坐标，给「搞钱」
            # 人群一个每日可看的落点（调研：财运诉求 74.9%）。
            "money_dir": huangli_mod.caishen_fang(
                datetime(d.year, d.month, d.day, 12)),
            "mercury": _mercury_state(d),
            # R3502：金逆/火逆同构状态（表外年份静默）
            "venus": _venus_state(d),
            "mars": _mars_state(d),
            "moon": _moon_for(d),
            # R3601：未来 7 天天象预告（确定性历表）
            "week_sky": _week_sky(d),
            # R3317-G：今日牌——同日全站同一张大阿卡纳
            "daily_card": _daily_card_for(d),
            "term": _term_banner(d),
            **({"personal": _personal} if _personal else {}),
        }
        # R2502（R143 延伸）：BOOKS_WRITE_DISABLE 公开展示态下 GET 也照写
        # daily_cache——共享库写面应全拒。写禁时跳过落库，照算照回。
        if deps.public_writes_open():
            # R2509（审-P2-3）：缓存写失败（库只读/长锁）曾把整个算好的
            # result 掉进「没算出来」降级——缓存写是辅助面，失败不该
            # 伪报计算失败。独立 try，写挂照样回真卡。
            try:
                with deps.knowledge() as kb:
                    # R2349t（R87-P0-1）：personal 是请求方生辰派生——整包落
                    # daily_cache 会让无 bday 的请求拿到上一用户的日主行，
                    # wipe 也够不着（缓存只按日期窗口清）。落库剔除；
                    # 每请求现算成本=一次干支查表。
                    kb.set_daily_cache(
                        date_str,
                        bazi={k: v for k, v in result.items()
                              if k != "personal"})
            except Exception:  # noqa: BLE001
                pass
        # R3150b：日签接入 result_ref 快照——照卡聊「今天怎么样」
        # 小满手里是卡面原文（summary/宜忌/贵人），不是泛日运腔。
        # 快照只留内存（2h TTL/LRU）不落库；personal 是请求方生辰
        # 派生字段，stash 前剔除（与落库剔除同口径）。
        result["result_ref"] = _stash_result(
            "daily", {k: v for k, v in result.items() if k != "personal"})
        return result
    except Exception:                                 # 计算失败降级为"平"，不 500
        # R228b：不把 str(exc) 透传给用户——那是 Python 异常原文
        # （"year 10000 is out of range"），给固定中性文案。
        return {"date": date_str, "level": "平", "summary": "今天的运势卡暂时没算出来，稍后再看看～",
                "noble": "—", "do": "—", "dont": "—", "cached": False,
                # R2349l：降级路径同构常驻键（契约探针）
                "lunar": "",
                "festival": [], "lucky": {}, "mercury": {}, "moon": {},
                "venus": {}, "mars": {}, "week_sky": [],
                "outfit": {},
                "daily_card": {},
                "term": {}}


def lunar_convert(y: int, m: int, d: int, leap: bool = False) -> dict:
    """农历 → 公历换算（首页礼物生日输入等轻量入口用）。

    R3232：前端 me 档案/判词链全是公历坐标系——农历生日先在这里
    换成公历再落档，档案不做农历记忆。越界/不存在的农历日抛
    ValidationError → 400 中文人话（lunar_to_solar 的 ValueError
    原文已是中文且自带纠正信息，如「该年闰月是X月」）。
    """
    try:
        s = lunar.lunar_to_solar(y, m, d, bool(leap))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return {"solar": s.isoformat(), "year": s.year,
            "month": s.month, "day": s.day}


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
    today = _today_cn().isoformat()
    # R3307（审-低9）：bazi 分支按数字 id 直读 derived 表——/1..500
    # 挨个试即拖走全部研究笔记原文（可枚举个人数据面），前端从未
    # 调用它。删面比加签名更省：bazi 一律 404。
    if share_type == "bazi":
        raise NotFoundError("这条没找到，可能被清掉了，刷新看看")
    if share_type in ("tarot", "book"):
        # R228r：这两个分享面无后端存档，share_id 原样回显——限长+拒控制字符
        # 守住上限，任意长串/HTML 片段不该被当分享标题直接回显。
        if not share_id or len(share_id) > 80 or not share_id.isprintable():
            raise NotFoundError("这条没找到，可能被清掉了，刷新看看")
        title, content = (("塔罗占卜结果", "塔罗牌阵解读") if share_type == "tarot"
                          else ("读书笔记", "古籍研究笔记"))
        return {"title": title, "subtitle": share_id, "content": content,
                "image_color": SHARE_COLORS[share_type], "created_at": today}
    raise NotFoundError("这个分享类型不认识")


def user_prefs() -> dict:
    with deps.knowledge() as kb:
        return {"theme": kb.get_pref("theme", "cream"),
                "recent": _recent_list(kb),
                "favorites": [dict(r) for r in kb.list_favorites()]}


def clear_user_prefs() -> dict:
    """R3339（审-低）：「忘掉」面此前够不到 user_prefs 表——死写端点
    攒下的键、recent 列表永存。theme 刻意保留（wipe 口径：偏好保留）。"""
    with deps.knowledge() as kb:
        return {"deleted": kb.clear_prefs_except(("theme",))}


def set_user_prefs(payload: dict) -> dict:
    # R228j：自由键值≠无界——键数/键长/值长不设限就是 sqlite 无限写入面。
    payload = payload or {}
    if len(payload) > 64:
        raise ValidationError("存的偏好太多了，先清一批再存")
    items = []
    for k, v in payload.items():
        # R2508（审-P0）：dict 值不属 pydantic str 校验面——孤代理
        # \ud800 能漏到 sqlite 绑定炸 UnicodeEncodeError。键值都剥。
        if isinstance(k, str):
            k = re.sub(r"[\ud800-\udfff]", "", k)
        if not isinstance(k, str) or not k or len(k) > 64:
            raise ValidationError("偏好名太长或为空，换短一点的")
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        v = re.sub(r"[\ud800-\udfff]", "", str(v))
        if len(v) > 4000:
            raise ValidationError("这条偏好存不下（太长了）")
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
        # R2516（审-P2-1）：不存在如实 404，不再假成功。
        if not kb.remove_favorite(fid):
            raise NotFoundError("这条收藏没找到，可能已经删掉了。")
    return {"ok": True}


def clear_favorites() -> dict:
    """R2349（R65-P1-2）：清空收藏表，「忘掉我的数据」收口面。"""
    with deps.knowledge() as kb:
        kb.clear_favorites()
    return {"ok": True}


def couple_checkin(req) -> dict:
    """合拍打卡（R3343）：双方各自把打卡日集合推上来，服务端只回交集。

    输入校验全在 CoupleCheckinRequest（pair_id 64hex、member 0|1、
    days≤400 且逐项真实日期）——到这里的都是干净值。"""
    with deps.knowledge() as kb:
        return kb.couple_sync(req.pair_id, req.member, req.days)


def muyu_state() -> dict:
    """敲敲木鱼（R3424）：今天的「全铺子一起敲」共敲数。

    匿名计数器——只按日累计数字，不记任何身份/指纹。"""
    _t = _today_cn().isoformat()
    with deps.knowledge() as kb:
        return {"date": _t, "today": kb.counter_get("muyu:" + _t)}


def muyu_knock(n: int) -> dict:
    """敲一下：把 n 记进今天的共敲数并返回新值。n 在 schema 已收 1..500。"""
    _t = _today_cn().isoformat()
    with deps.knowledge() as kb:
        return {"date": _t, "today": kb.counter_add("muyu:" + _t, n)}


def external_news() -> dict:
    """外部资讯通道：抓预置 RSS/Atom 源。不落库、不写 history。"最新消息"
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
    """外部资讯的运势风格包装（预留面，daily 未接入，前端零调用，R85-P2-8 登记）。"""
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
    """按日期键缓存的值宫卡：当日结果恒定，跨午夜自动换键失效。"""
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
    return dict(_today_horoscope_cached(iso_day or _today_cn().isoformat()))


def _cross_ref_bazi(b, gender: str, month: int = 0, day: int = 0,
                    today_iso: str | None = None,
                    year: int | None = None,
                    hour: int | None = None) -> dict:
    """八字结果页 → 你的太阳星座 + 今天的运势侧重。

    month/day 是**出生**月日（太阳星座的唯一依据）。缺省 0 时降级为只给
    今日值宫，不再瞎猜本命星座。R3308：year/hour 透传节气精判。
    """
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day, year=year, hour=hour) \
            if month and day else {}
        today = _today_horoscope(today_iso)
        sign = prof.get("sign", "")
        today_sign = today.get("today_sign", "")
        note = today.get("today_note", "")
        # 一句话只说一件事：本命座的长处 + 今天当值宫的节奏。两者撞车时
        # （旧文案"你是双子座…今天的整体节奏：节奏放慢一点"读起来自相矛盾）
        # 明确标出"今天是 X 宫的日子"，让用户知道这是两个不同维度。
        if sign and today_sign and note:
            if sign == today_sign:
                msg = f"你是{sign}座，今天正好轮到你当班：{note}"
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
    """合婚结果页 → 双方太阳星座配对。

    a_md/b_md = (出生月, 出生日) 或 R3308 后的 (年, 月, 日[, 时辰])。"""
    from guji.xingzuo import sun_sign
    try:
        # R3308：3/4 元组带年（+时辰）走节气精判；2 元组旧调用保持粗判。
        def _sg(md: tuple) -> str:
            if len(md) >= 3:
                h = md[3] if len(md) > 3 else None
                return sun_sign(md[1], md[2], year=md[0], hour=h)
            if len(md) == 2:
                return sun_sign(*md)
            return ""
        sa = _sg(a_md)
        sb = _sg(b_md)
        if not (sa and sb):
            return {}
        # R2349s（R84-P1-11）：全宇宙 66 对异座组合只有 2 个模板——按
        # 四象给差异化口径，同象/异象不同说法。
        _ELEM = {"白羊": "火", "狮子": "火", "射手": "火",
                 "金牛": "土", "处女": "土", "摩羯": "土",
                 "双子": "风", "天秤": "风", "水瓶": "风",
                 "巨蟹": "水", "天蝎": "水", "双鱼": "水"}
        if sa == sb:
            _pool = [f"都是{sa}座，同款脾气：合得来的时候特别合，别较劲就行。",
                     f"两个{sa}座照镜子：优点是翻倍的，毛病也是翻倍的。",
                     "同座同频，很多话不用解释，偶尔也要给对方留点新鲜感。"]
            tip = _pool[hash((a_md, b_md)) % len(_pool)]
        elif _ELEM.get(sa) == _ELEM.get(sb):
            tip = (f"{sa}座配{sb}座，同象（{_ELEM.get(sa)}象）同频。"
                   "底层节奏天然合拍，剩下就看谁更有趣了。")
        elif {_ELEM.get(sa), _ELEM.get(sb)} in ({"火", "风"}, {"土", "水"}):
            tip = (f"{sa}座配{sb}座，风火相煽/土水相养的路数。"
                   "能量是互相喂的，搭好了很旺。")
        elif frozenset({_ELEM.get(sa), _ELEM.get(sb)}) in _SIGN_HARD:
            # R3106（specs/010）：相冲象组与 xzmatch 同口径——报具体
            # 吵点+处方，不再吃「快慢互补」通用池（66 对 3 模板实测）。
            _hh = {frozenset({"火", "水"}):
                       "一个急着冲、一个先要情绪被接住，最容易吵在"
                       "「你不懂我」；急的先回应感受，慢的直接说要什么。",
                   frozenset({"风", "土"}):
                       "一个要变化、一个要落地，吵的点在「靠不靠谱」；"
                       "大事听土象定盘，小事随风象兴头。"}
            tip = (f"{sa}座配{sb}座，"
                   + _hh[frozenset({_ELEM.get(sa), _ELEM.get(sb)})])
        else:
            _pool = [f"{sa}座配{sb}座，节奏不一样反而互补，谁先开口谁占便宜。",
                     f"{sa}座配{sb}座，一个快一个慢：慢的那个决定走多远。",
                     f"{sa}座配{sb}座，频道不同但可以互译：愿意翻译就是爱。"]
            tip = _pool[hash((a_md, b_md)) % len(_pool)]
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
    # R2355（R111-P2-7）：先查年份界再查日内有效性——「2101-02-30」
    # 此前报「这一天不存在」，其实问题是年份越界。
    _ym = re.match(r"^(\d{4})-\d{1,2}-\d{1,2}$", date_str or "")
    if _ym and not (YEAR_LO <= int(_ym.group(1)) <= YEAR_HI):
        raise ValidationError(
            f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {_ym.group(1)}")
    try:
        parsed = date.fromisoformat(date_str)
    except ValueError:
        # R230t（R33-P3-11）：2026-02-31 这种「格式对但日子不存在」
        # 此前被报成「格式不对」——文案误导。分开说。
        _msg = (f"这一天不存在，收到 {date_str}"
                if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", date_str or "")
                else "日期格式没看懂，照着 2026-01-01 这样填试试")
        raise ValidationError(_msg) from None
    # R2506（审-F3）：Py3.11+ fromisoformat 放宽收 20260101、
    # 2026-W01-1 等非规范形——与 schemas._iso_canonical 同口径，
    # isoformat 往返只放 YYYY-MM-DD（GET 与 POST 契约对齐）。
    if parsed.isoformat() != date_str:
        raise ValidationError(
            "日期格式没看懂，照着 2026-01-01 这样填试试")
    if not (YEAR_LO <= parsed.year <= YEAR_HI):
        raise ValidationError(
            f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {parsed.year}")
    return parsed


def _cross_ref_huangli(date_str: str, today_str: str | None = None) -> dict:
    """黄历结果页 → 今天的星座值宫（这一处本来就该用"今日"，逻辑成立）。"""
    from guji.xingzuo import daily_horoscope
    try:
        from datetime import date as _date
        d = _date.fromisoformat(date_str) if date_str else _today_cn()
        b = bazi_compute(d.year, d.month, d.day, 12, "男")
        h = daily_horoscope(b.day)
        sign = h.get("today_sign", "")
        note = h.get("today_note", "")
        if not (sign and note):
            return {}
        # R228p：用户翻的是查询日，不一定是今天——文案跟着说"那天"。
        # R2349k（R72-B3）：「今天」的锚用客户端日（today 参数）——
        # UTC 服务器日 0-8 点比中国用户慢半天，那时候翻今天会被说「那天」。
        try:
            _today = (_date.fromisoformat(today_str)
                      if today_str else _today_cn())
        except (ValueError, TypeError):
            _today = _today_cn()
        _when = "今天" if d == _today else "那天"
        # R2350a（R94-P1-6）：note 文案内含硬编码「今日宜…」——非今天卡
        # 变成「那天轮到X座当班：今日宜…」时态打架。剥掉前缀时间词。
        if _when == "那天" and note.startswith("今日"):
            note = note[2:]
        return {
            "zodiac_sign": sign,
            "zodiac_note": note,
            # R233g（R44-P2-9）：与前端「X座当班」口径统一——「值宫」
            # 是生造术语，读屏/年轻用户都读不顺。
            "message": f"{_when}轮到{sign}座当班：{note}",
        }
    except Exception:
        return {}


def _cross_ref_taohua(month: int, day: int, strength: str = "",
                      year: int | None = None,
                      hour: int | None = None) -> dict:
    """桃花结果页 → 星座桃花信号，与八字强度叠加判断。
    R3308：year/hour 透传节气精判。"""
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day, year=year, hour=hour)
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
        # R2500（R144-P2-1）：note 末尾无句号时与「牌面这边」直接粘连
        # 成跑连句（实屏「…脑子才转牌面这边偏逆位…」）——分隔符归一化。
        _note = note.rstrip("。！？…；") + "；" if note else ""
        return {
            "today_sign": sign,
            "today_note": note,
            "today_direction": sign_direction(sign),
            "card_direction": card_dir,
            "upright_count": _up,
            "total": _total,
            "message": f"今天{sign}宫：{_note}牌面这边{card_side}，{relation}。",
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
            "message": f"今天{sign}宫：{note}卦里{gua_side}，{relation}。",
        }
    except Exception:
        return {}


def _cross_ref_qiming(month: int, day: int,
                      year: int | None = None,
                      hour: int | None = None) -> dict:
    """起名结果页 → 太阳星座气质，给挑名字的参考角度。
    R3340（审-P1）：year/hour 透传节气精判（与 bazi/taohua 同口径）。"""
    from guji.xingzuo import sun_sign_profile
    try:
        prof = sun_sign_profile(month, day, year=year, hour=hour)
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
