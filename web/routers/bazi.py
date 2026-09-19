"""web/routers/bazi.py — 八字域 HTTP 绑定（排盘 / 桃花 / 合婚 / 起名 / 历史）。

只做 HTTP 绑定：解析请求 → 调 services → 返回 dict。校验异常由
`web.errors` 统一转 400/422/404。
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import Response

from guji import llm_polish, paipan_history

from .. import services
from ..errors import NotFoundError
from ..schemas import (BaziRequest, ChatRequest, HehunRequest,
                       NameReviewRequest, QimingRequest)

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
    facts += services.chat_huangli_facts(req.message)
    tid = llm_polish.spawn_chat_task(
        req.session_id, req.message, facts=facts)
    if tid:
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


# ---- 排盘历史台账（2026-08-28 新增，命名带 paipan_ 前缀与旧 /api/history* 隔离）----

@router.get("/api/paipan/history")
def paipan_history_list(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """排盘历史分页列表（id 倒序=最新在前）。空库 → {total:0, items:[]}。"""
    if paipan_history.disabled():
        return {"total": 0, "items": []}
    return paipan_history.list_records(limit=limit, offset=offset)


@router.get("/api/paipan/history/export")
def paipan_history_export() -> Response:
    """CSV 导出（UTF-8 with BOM，Excel 直接打开不乱码）。"""
    # R229n（R6-#5）：disabled 语义是「不写不查」——此前只查 list，
    # get/delete/export 在禁用下仍吐完整记录与 CSV。
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "ts", "name", "question", "paipan_render"])
    for row in paipan_history.export_rows():
        writer.writerow(row)
    content = "\ufeff" + buf.getvalue()
    filename = datetime.now().strftime("paipan_history_%Y%m%d.csv")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/paipan/history/{rid}")
def paipan_history_get(rid: int) -> dict:
    """单条完整记录（result 为完整排盘响应，前端可复用渲染函数）。"""
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    rec = paipan_history.get_record(rid)
    if rec is None:
        raise NotFoundError(f"排盘记录不存在：#{rid}")
    return rec


@router.delete("/api/paipan/history/{rid}")
def paipan_history_delete(rid: int) -> dict:
    if paipan_history.disabled():
        raise NotFoundError("排盘历史未启用")
    if not paipan_history.delete_record(rid):
        raise NotFoundError(f"排盘记录不存在：#{rid}")
    return {"ok": True}


# R219b（P0-4 用户裁决）：/api/history、/api/history/{rid}（GET/DELETE）三个
# 端点随「我的解读」历史记录功能整体删除——不再记录用户解读（用户原话：
# 不记录，浪费内存，后续会建用户隔离数据库）。services.history_* 与
# /api/bazi 内的 history_db.save_record() 同批移除。
