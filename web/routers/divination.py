"""web/routers/divination.py — 占卜域 HTTP 绑定（六爻 / 黄历 / 塔罗）。

三者都是本地纯计算：起卦坐标与择日坐标由本地代码算出（可核验），
卦辞/爻辞从已入库的周易语料取出（引用可核验），解读走确定性规则层。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import services
from ..schemas import LiuyaoRequest, TarotDrawRequest, TarotRequest

router = APIRouter(tags=["divination"])


@router.post("/api/liuyao")
def liuyao(req: LiuyaoRequest) -> dict:
    """六爻起卦（coins 铜钱 / time 时间）+ 本卦变卦經文引用 + 确定性解读。"""
    return services.liuyao(req)


@router.get("/api/huangli")
def huangli(date: str | None = None, affair: str | None = None,
            # R228b：days 无界时逐日 day_query 线性 DoS（实测 365 天≈21s）
            days: int = Query(1, ge=1, le=92)) -> dict:
    """黄历择日：单日宜忌坐标，或在日期区间内找宜某事项的日子。"""
    return services.huangli(date, affair, days)


@router.get("/api/huangli/resolve_date")
def huangli_resolve_date(q: str = Query("", max_length=80)) -> dict:
    """R229z：节日/农历/复杂日期表达 → 公历日期（前端问一嘴的兜底——
    _hlDayOffset 本地解不动时调它；解不出 date=null，前端回退显示日）。"""
    return services.resolve_huangli_date(q)


@router.post("/api/tarot")
def tarot(req: TarotRequest) -> dict:
    """塔罗牌阵：78 张静态牌表 + seed 确定性抽牌 + 关键词转述。"""
    return services.tarot(req)


@router.post("/api/tarot/draw")
def tarot_draw(req: TarotDrawRequest) -> dict:
    """快速抽牌（首页入口）：单张牌 + 关键词转述。"""
    return services.tarot_draw(req)
