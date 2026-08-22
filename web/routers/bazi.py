"""web/routers/bazi.py — 八字域 HTTP 绑定（排盘 / 桃花 / 合婚 / 起名 / 历史）。

只做 HTTP 绑定：解析请求 → 调 services → 返回 dict。校验异常由
`web.errors` 统一转 400/422/404。
"""
from __future__ import annotations

from fastapi import APIRouter

from guji import llm_polish

from .. import services
from ..errors import NotFoundError
from ..schemas import BaziRequest, HehunRequest, QimingRequest

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


@router.get("/api/xingzuo")
def xingzuo(date: str | None = None) -> dict:
    """十二宫日运（004 M2）：当日日支查宫 + 12 宫一句话 + 语料锚点。"""
    return services.xingzuo(date)


@router.get("/api/history")
def history_list(limit: int = 50) -> dict:
    """历史列表（轻量字段，供前端列表展示）。"""
    return services.history_list(limit)


@router.get("/api/history/{rid}")
def history_detail(rid: int) -> dict:
    """单条完整记录（含排盘/运算/引文/解读全文）。"""
    return services.history_detail(rid)


@router.delete("/api/history/{rid}")
def history_delete(rid: int) -> dict:
    """删除一条历史记录。"""
    return services.history_delete(rid)
