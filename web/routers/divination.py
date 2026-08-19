"""web/routers/divination.py — 占卜域 HTTP 绑定（六爻 / 黄历 / 塔罗）。

三者都是本地纯计算：起卦坐标与择日坐标由本地代码算出（可核验），
卦辞/爻辞从已入库的周易语料取出（引用可核验），解读走确定性规则层。
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import services
from ..schemas import LiuyaoRequest, TarotDrawRequest, TarotRequest

router = APIRouter(tags=["divination"])


@router.post("/api/liuyao")
def liuyao(req: LiuyaoRequest) -> dict:
    """六爻起卦（coins 铜钱 / time 时间）+ 本卦变卦經文引用 + 确定性解读。"""
    return services.liuyao(req)


@router.get("/api/huangli")
def huangli(date: str | None = None, affair: str | None = None,
            days: int = 1) -> dict:
    """黄历择日：单日宜忌坐标，或在日期区间内找宜某事项的日子。"""
    return services.huangli(date, affair, days)


@router.post("/api/tarot")
def tarot(req: TarotRequest) -> dict:
    """塔罗牌阵：78 张静态牌表 + seed 确定性抽牌 + 关键词转述。"""
    return services.tarot(req)


@router.post("/api/tarot/draw")
def tarot_draw(req: TarotDrawRequest) -> dict:
    """快速抽牌（首页入口）：单张牌 + 关键词转述。"""
    return services.tarot_draw(req)
