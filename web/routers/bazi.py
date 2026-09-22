"""web/routers/bazi.py — 八字域 HTTP 绑定（排盘 / 桃花 / 合婚 / 起名 / 历史）。

只做 HTTP 绑定：解析请求 → 调 services → 返回 dict。校验异常由
`web.errors` 统一转 400/422/404。
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

# R2350g（R106-F4）：缺参回落锚 UTC+8（同 services._now_cn）。
_CN_TZ = timezone(timedelta(hours=8))


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)

from fastapi import APIRouter, Query
from fastapi.responses import Response

from guji import llm_polish, paipan_history

from .. import deps, services
from ..errors import NotFoundError
from ..schemas import (BaziRequest, ChatRequest, HehunRequest,
                       NameReviewRequest, PaipanImportRequest,
                       QimingRequest, ValidationError)

router = APIRouter(tags=["bazi"])


@router.post("/api/bazi")
def bazi(req: BaziRequest) -> dict:
    """八字排盘：四柱 + 运算层（scope=day/range/life）+ 古籍引文 + 确定性解读。"""
    return services.bazi(req)


@router.post("/api/taohua")
def taohua(req: BaziRequest) -> dict:
    """八字桃花运：咸池/红鸾/天喜纯坐标（固定生日 → 固定输出）。"""
    return services.taohua(req)


@router.post("/api/hehun")
def hehun(req: HehunRequest) -> dict:
    """八字合婚：六冲/六合/日主五行/桃花支 + 大运冲合应期。"""
    return services.hehun(req)


@router.post("/api/qiming")
def qiming(req: QimingRequest) -> dict:
    """五行起名：八字五行缺行 → 部首五行候选字。"""
    return services.qiming(req)


@router.get("/api/ai/{tid}")
def ai_task(tid: str) -> dict:
    """AI 润色任务轮询端点（R191b，B-014/D-251b）。

    返回 {status: pending|done|failed, text}；未知/已过 TTL 的 id → 404
    （前端按失败处理：整块不渲染，D-244a 语义不变）。
    """
    st = llm_polish.ai_task_status(tid)
    if st is None:
        raise NotFoundError(f"AI 任务不存在或已过期：{tid[:8]}…")
    return st


@router.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """AI 陪伴层（R206b，specs/009 US1；D-259b）。

    additive 语义与四端点一致：DISABLE=1 / 配置关闭 → 响应无 chat_task_id 键
    （前端隐藏入口）。回复经既有 GET /api/ai/{tid} 轮询取回——零新轮询端点。
    会话历史只在内存，绝不入库。
    """
    out: dict = {}
    req.validate_ranges()
    # R227b：黄历类提问先在后端算成「黄历判定」事实再交给小满——
    # 事项没列进宜忌 ≠ 不支持（中性 + 近期吉日），杜绝照本宣科式回复。
    facts = list(req.facts or [])
    # R230a-6（R12-P2-2）：黄历判定走独立权威信道——客户端 facts 只是
    # 话题参考，按子串升格会让伪造判定混入权威位。
    # R230l（R24-P2-3）：客户端基准日透传——跨零点 ±TZ 窗口里服务器
    # 日与浏览器「今天」不同，黄历事实按用户日子算。
    _now = None
    if req.client_date:
        try:
            _now = datetime.combine(
                date.fromisoformat(req.client_date), _now_cn().time())
        except (ValueError, TypeError):
            pass   # validate_ranges 已挡；此处再兜底不炸
    tid = llm_polish.spawn_chat_task(
        req.session_id, req.message, facts=facts,
        verdict_facts=services.chat_huangli_facts(
            req.message, now=_now, session_id=req.session_id),
        # R230t（R32-P1-7）：判定锚定日透传——跨日存档判定作废。
        verdict_day=(_now or _now_cn()).date().isoformat())
    # R2355（R111-P2-6）：限流哨兵分流——rate_limited 给前端「歇口气」
    # 提示位；None 仍是关停/兜底静默降级（{}）。
    if tid == "__rate_limited__":
        out["rate_limited"] = True
    elif tid:
        out["chat_task_id"] = tid
    return out


@router.post("/api/qiming/review")
def qiming_review(req: NameReviewRequest) -> dict:
    """AI 起名点评（R207b；D-259b 同族）：引经据典推荐语，additive 键。

    DISABLE=1 / 配置关闭 → 响应无 review_task_id 键（前端隐藏入口）。"""
    out: dict = {}
    req.validate_ranges()
    tid = llm_polish.spawn_name_review_task(
        req.names, facts=req.facts or [])
    if tid:
        out["review_task_id"] = tid
    return out


@router.get("/api/xingzuo")
def xingzuo(date: str | None = None) -> dict:
    """十二宫日运（004 M2）：当日日支查宫 + 12 宫一句话 + 语料锚点。"""
    return services.xingzuo(date)


@router.get("/api/xzmatch")
def xzmatch(a: str = Query("", max_length=4),
            b: str = Query("", max_length=4),
            rel: str = Query("", max_length=2)) -> dict:
    """R2349l（R73-P1-7）：星座速配——sa/sb 为星座名（白羊…双鱼）；
    rel=闺蜜/同事 追加语境尾巴（R73-P2-11）。"""
    out = services.xzmatch(a, b, rel)
    if not out:
        raise ValidationError("没认出星座名——白羊、金牛、双子…双鱼里挑两个")
    return out


# ---- 排盘历史台账（2026-08-28 新增，命名带 paipan_ 前缀与旧 /api/history* 隔离）----

@router.get("/api/paipan/history")
def paipan_history_list(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """排盘历史分页列表（id 倒序=最新在前）。空库 → {total:0, items:[]}。"""
    if paipan_history.disabled():
        # R2349t（R87-P2-1）：带禁用标记——前端此前把禁用读成「还没用过」，
        # 「都会收在这里」与永不写的事实矛盾。
        return {"total": 0, "items": [], "disabled": True}
    return paipan_history.list_records(limit=limit, offset=offset)


@router.get("/api/paipan/tarot_collection")
def paipan_tarot_collection() -> dict:
    """R2349l（R73-P1-12）：塔罗图鉴——台账里抽过的牌 + 全 78 牌名。"""
    from guji.tarot import DECK
    # R2349t（R87-P2-1）：「不写不查」口径破洞——禁用下仍聚合存量
    # 库出牌，与历史列表的禁用语义不一致。
    if paipan_history.disabled():
        return {"collected": [], "deck": [d[0] for d in DECK],
                "total": len(DECK)}
    got = paipan_history.tarot_collection()
    return {"collected": got.get("collected", []),
            "deck": [d[0] for d in DECK], "total": len(DECK)}


@router.get("/api/paipan/history/export")
def paipan_history_export() -> Response:
    """CSV 导出（UTF-8 with BOM，Excel 直接打开不乱码）。"""
    # R229n（R6-#5）：disabled 语义是「不写不查」——此前只查 list，
    # get/delete/export 在禁用下仍吐完整记录与 CSV。
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "name", "question", "type", "paipan_render"])
    for row in paipan_history.export_rows():
        writer.writerow(row)
    content = "\ufeff" + buf.getvalue()
    filename = _now_cn().strftime("paipan_history_%Y%m%d.csv")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/paipan/history/export_json")
def paipan_history_export_json() -> dict:
    """R231a（R36-P3-3）：全量 JSON 导出（含 req/result，供备份+复看回放）。
    前端把它与 localStorage 键打包成「我的数据」文件。"""
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    return {"version": 1,
            "exported_at": _now_cn().isoformat(timespec="seconds"),
            "records": paipan_history.export_all()}


@router.post("/api/paipan/history/import")
def paipan_history_import(req: PaipanImportRequest) -> dict:
    """R231a（R36-P3-3）：备份文件回灌——追加式去重落库。"""
    deps.write_guard()   # R2357
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    _w, _sk, _new = paipan_history.import_rows(req.records)
    # R2400（R127-P2-5）：新行 id 回给前端——备份里的完整 req/result
    # 按新 id 回灌进本机镜像详情，云端清盘后点开依旧有完整排盘。
    return {"imported": _w, "skipped": _sk, "new_records": _new}


@router.get("/api/paipan/history/{rid}")
def paipan_history_get(rid: int) -> dict:
    """单条完整记录（result 为完整排盘响应，前端可复用渲染函数）。"""
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    rec = paipan_history.get_record(rid)
    if rec is None:
        raise NotFoundError(f"排盘记录不存在：#{rid}")
    return rec


@router.delete("/api/paipan/history")
def paipan_history_clear() -> dict:
    """R2345（R63-P1-3）：「忘掉我的数据」——台账整表清空。"""
    deps.write_guard()   # R2357：公开模式下任何人都能清别人的库
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    return {"ok": True, "deleted": paipan_history.clear_all()}


@router.delete("/api/paipan/history/{rid}")
def paipan_history_delete(rid: int) -> dict:
    deps.write_guard()   # R2357
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    if not paipan_history.delete_record(rid):
        raise NotFoundError(f"排盘记录不存在：#{rid}")
    return {"ok": True}


# R219b（P0-4 用户裁决）：/api/history、/api/history/{rid}（GET/DELETE）三个
# 端点随「我的解读」历史记录功能整体删除——不再记录用户解读（用户原话：
# 不记录，浪费内存，后续会建用户隔离数据库）。services.history_* 与
# /api/bazi 内的 history_db.save_record() 同批移除。
