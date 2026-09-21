"""web/routers/divination.py — 占卜域 HTTP 绑定（六爻 / 黄历 / 塔罗）。

三者都是本地纯计算：起卦坐标与择日坐标由本地代码算出（可核验），
卦辞/爻辞从已入库的周易语料取出（引用可核验），解读走确定性规则层。
"""
from __future__ import annotations

from datetime import date as _date, datetime as _datetime
from datetime import timedelta as _td, timezone as _tz

# R2350g（R106-F4）：缺参回落锚 UTC+8。
_CN_TZ = _tz(_td(hours=8))

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
            days: int = Query(1, ge=1, le=92),
            # R2349k（R72-B3）：客户端本地日——cross_ref「今天」锚用它。
            today: str = Query("", max_length=10)) -> dict:
    """黄历择日：单日宜忌坐标，或在日期区间内找宜某事项的日子。"""
    return services.huangli(date, affair, days, today or None)


@router.get("/api/huangli/resolve_date")
def huangli_resolve_date(q: str = Query("", max_length=80),
                         base: str = Query("", max_length=10)) -> dict:
    """R229z：节日/农历/复杂日期表达 → 公历日期（前端问一嘴的兜底——
    _hlDayOffset 本地解不动时调它；解不出 date=null，前端回退显示日）。
    R230l（R24-P3-4）：base=浏览器本地日——跨零点±TZ/年界窗口不漂移。"""
    _now = None
    if base:
        try:
            _now = _datetime.combine(
                _date.fromisoformat(base), _datetime.now(_CN_TZ).time())
        except (ValueError, TypeError):
            _now = None        # 非法 base 静默回落服务器日（同旧行为）
    return services.resolve_huangli_date(q, now=_now)


@router.post("/api/tarot")
def tarot(req: TarotRequest) -> dict:
    """塔罗牌阵：78 张静态牌表 + seed 确定性抽牌 + 关键词转述。"""
    return services.tarot(req)


@router.post("/api/tarot/draw")
def tarot_draw(req: TarotDrawRequest) -> dict:
    """快速抽牌（首页入口）：单张牌 + 关键词转述。"""
    return services.tarot_draw(req)
