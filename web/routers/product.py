"""web/routers/product.py — 产品域 HTTP 绑定。

每日运势 / 首页功能卡片 / 分享卡片 / 用户偏好 / 收藏 / 外部资讯 / 健康检查。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import services
from ..schemas import FavoriteAddRequest, PrefsRequest

router = APIRouter(tags=["product"])


@router.get("/api/health")
def health() -> dict:
    """健康检查：解读引擎标识 + 索引是否就位。"""
    return services.health()


@router.get("/api/daily")
def daily(date: str | None = None,
          # R2349l（R73-P1-3）：bday=用户生日 → 出 personal 个性行
          bday: str = Query("", max_length=10)) -> dict:
    """每日运势卡片：等级 + 一句话 + 贵人属相 + 宜忌（命中 daily_cache）。"""
    return services.daily(date, bday or None)


# R228l 登记：/api/widget、/api/share/*、/api/external/fortune 前端零调用
# ——widget 是嵌入部件预留面、share 是分享卡数据面（JS 侧走本地海报渲染）、
# fortune 是外部资讯预留。selftest 断言钉着契约，不是僵尸端点。
@router.get("/api/widget")
def widget() -> dict:
    """首页功能卡片数据：各模块图标/标题/描述 + 最近使用标记。"""
    return services.widget()


@router.get("/api/share/{share_type}/{share_id}")
def share(share_type: str, share_id: str) -> dict:
    """分享卡片数据：可截图分享的结果摘要。"""
    return services.share(share_type, share_id)


@router.get("/api/user/prefs")
def user_prefs() -> dict:
    """用户偏好：主题、最近使用、收藏。"""
    return services.user_prefs()


@router.post("/api/user/prefs")
def set_user_prefs(req: PrefsRequest) -> dict:
    """设置用户偏好（任意键值；list/dict 值自动 JSON 序列化）。"""
    return services.set_user_prefs(req.to_dict())


@router.post("/api/favorites")
def add_favorite(req: FavoriteAddRequest) -> dict:
    """收藏一条结果。"""
    return services.add_favorite(req)


@router.delete("/api/favorites/{fid}")
def remove_favorite(fid: int) -> dict:
    """取消收藏。"""
    return services.remove_favorite(fid)


@router.delete("/api/favorites")
def clear_favorites() -> dict:
    """R2349（R65-P1-2）：清空全部收藏——「忘掉我的数据」调用面。"""
    return services.clear_favorites()


@router.get("/api/external/news")
def external_news() -> dict:
    """外部资讯通道：抓预置 RSS/Atom 源。不落库，与语料 Source 层隔离。"""
    return services.external_news()


@router.get("/api/external/fortune")
def external_fortune() -> dict:
    """外部资讯的运势风格包装（每日运势卡片的外部资讯部分）。"""
    return services.external_fortune()
