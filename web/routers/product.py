"""web/routers/product.py — 产品域 HTTP 绑定。

每日运势 / 首页功能卡片 / 分享卡片 / 用户偏好 / 收藏 / 外部资讯 / 健康检查。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import deps, services
from ..schemas import (CoupleCheckinRequest, DailyRequest,
                       FavoriteAddRequest, LunarConvertRequest,
                       PrefsRequest)

router = APIRouter(tags=["product"])


# R3316（审-P2）：HEAD 一并放行——平台/监控的 HEAD 探活此前吃
# 405，GET 正常 → 误报不健康。
@router.api_route("/api/health", methods=["GET", "HEAD"])
def health() -> dict:
    """健康检查：解读引擎标识 + 索引是否就位。"""
    return services.health()


@router.get("/api/daily")
def daily(date: str | None = Query(None, max_length=10),
          # R2349l（R73-P1-3）：bday=用户生日 → 出 personal 个性行
          bday: str = Query("", max_length=10)) -> dict:
    """每日运势卡片：等级 + 一句话 + 贵人属相 + 宜忌（命中 daily_cache）。"""
    return services.daily(date, bday or None)


# R3307（审-中6）：POST 变体——bday 是生日坐标属半隐私，此前 GET query
# 会留在边缘/CDN 日志与抓包里；带 bday 的调用一律走 body。GET 保留
# 给无 bday 的低敏预取与旧客户端。
@router.post("/api/daily")
def daily_post(req: DailyRequest) -> dict:
    """POST 版日签——body {date, bday}，敏感生日不进 URL。"""
    return services.daily(req.date, req.bday or None)


@router.get("/api/lunar/convert")
def lunar_convert(y: int = Query(..., ge=1900, le=2100),
                  m: int = Query(..., ge=1, le=12),
                  d: int = Query(..., ge=1, le=30),
                  leap: int = Query(0, ge=0, le=1)) -> dict:
    """农历 → 公历换算（R3232：首页礼物生日输入框等轻量入口）。

    农历日上限 30（表界把守），非法农历日由 services 抛 400 中文人话。
    """
    return services.lunar_convert(y, m, d, bool(leap))


@router.post("/api/lunar/convert")
def lunar_convert_post(req: LunarConvertRequest) -> dict:
    """R3307（审-中6）：POST 版农历换算——生日坐标走 body 不进 URL。"""
    return services.lunar_convert(req.y, req.m, req.d, bool(req.leap))


# R228l 登记：/api/widget、/api/share/*、/api/external/fortune 前端零调用
# ——widget 是嵌入部件预留面、share 是分享卡数据面（JS 侧走本地海报渲染）、
# fortune 是外部资讯预留。selftest 断言钉着契约，不是僵尸端点。
# R2349s（R85-P1-5）：R208b 删 news 面板后 /api/external/news 同样
# 前端零调用，一并登记（仅 probe_contract 作网络用例覆盖）。
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
    deps.write_guard()   # R2357：公网演示模式禁写共享库
    return services.set_user_prefs(req.to_dict())


@router.delete("/api/user/prefs")
def clear_user_prefs() -> dict:
    """R3339（审-低）：「忘掉」清偏好表（theme 保留）。"""
    deps.write_guard()
    return services.clear_user_prefs()


@router.post("/api/favorites")
def add_favorite(req: FavoriteAddRequest) -> dict:
    """收藏一条结果。"""
    deps.write_guard()   # R2357
    return services.add_favorite(req)


@router.delete("/api/favorites/{fid}")
def remove_favorite(fid: int) -> dict:
    """取消收藏。"""
    deps.write_guard()   # R2357
    return services.remove_favorite(fid)


@router.delete("/api/favorites")
def clear_favorites() -> dict:
    """R2349（R65-P1-2）：清空全部收藏——「忘掉我的数据」调用面。"""
    deps.write_guard()   # R2357
    return services.clear_favorites()


@router.post("/api/couple/checkin")
def couple_checkin(req: CoupleCheckinRequest) -> dict:
    """合拍打卡（R3343）：本方打卡日集合并入，回两人交集。"""
    deps.write_guard()   # R2357：公网演示模式禁写共享库
    return services.couple_checkin(req)


@router.get("/api/external/news")
def external_news() -> dict:
    """外部资讯通道：抓预置 RSS/Atom 源。不落库，与语料 Source 层隔离。"""
    return services.external_news()


@router.get("/api/external/fortune")
def external_fortune() -> dict:
    """外部资讯的运势风格包装（预留面——daily 未接入，前端零调用，R85-P2-8 登记）。"""
    return services.external_fortune()
