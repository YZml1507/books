"""web/routers — 按域拆分的 HTTP 绑定层。

每个模块只做三件事：声明路径与查询参数、调 `web.services` 的同名函数、
把纯 dict 交回 FastAPI。**不写业务逻辑，不 catch 业务异常**——校验失败
由 `web.errors` 注册的统一处理器转成 400/422/404。

域划分（按 URL 前缀而非按实现文件，前端 tab 与之一一对应）：
    bazi        /api/bazi /api/taohua /api/hehun /api/qiming
                /api/qiming/review /api/chat /api/ai/{tid}
                /api/xingzuo /api/xzmatch /api/paipan/*（R219b：
                /api/history* 三端点随历史记录功能删除）
    reading     /api/search /api/addr /api/compare /api/research /api/ask
                /api/concept /api/compare_works /api/works /api/stats
                /api/threads /api/bookstudy/*
    divination  /api/liuyao /api/huangli /api/tarot
    product     /api/daily /api/widget /api/share /api/user/prefs
                /api/favorites /api/external/* /api/health
    account     /api/account/*（R3358 轻账号：注册/登录/备份推拉）
"""
from __future__ import annotations

from . import account, bazi, divination, product, reading

ROUTERS = (bazi.router, reading.router, divination.router,
           product.router, account.router)

__all__ = ["ROUTERS", "account", "bazi", "divination", "product",
           "reading"]
