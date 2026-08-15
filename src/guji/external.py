"""src/guji/external.py — 外部资讯通道（P5）。

用户需求（2026-08-15）：借助 Agent-Reach 的平台通道获取"最新消息"、
browser-use 控制浏览器。本模块先落地**零 key 的 RSS/Atom 通道**：
  * 走代理 127.0.0.1:7897（用户已开梯子）；
  * 依赖 feedparser（已装入 .venv，见 TASK_LEDGER）；
  * 预置少量可靠源（新闻 / 古籍整理动态），并支持前端追加自定义源
    （自定义源仅存内存，不落库）。

红线遵守：
  * 只抓取**公开 RSS/Atom 源**，不做登录态/抓取付费内容；
  * 抓取结果只在进程内返回（不落语料库、不写 history.db）——
    "最新消息"是即时信息，不是古籍语料，与 Source 层严格隔离；
  * 超时与异常全部降级（单个源失败不影响其余源），不阻塞主流程。
"""
from __future__ import annotations

import os
import ssl
import time
import urllib.request
from dataclasses import dataclass, field

PROXY = os.environ.get("GUJI_PROXY", "http://127.0.0.1:7897")
FETCH_TIMEOUT = 12          # 单源抓取超时（秒）
MAX_ITEMS_PER_SOURCE = 8    # 每源最多返回条目数

# 预置零 key 源（title 用于前端展示）。
# mode: "proxy" 经 7897 代理抓取（海外源，实测 BBC 走代理正常）；
#       "direct" 直连（国内可达源，实测 Solidot 直连正常，走代理反而慢/不稳）。
# 实测记录（2026-08-15）：
#   * github.com/*.atom 本网络代理与直连均 SSL UNEXPECTED_EOF → 不预置；
#   * api.github.com 直连可用但共享 IP 易触发 403 rate limit → 不预置，留待用户自定义。
DEFAULT_SOURCES: list[dict[str, str]] = [
    {"id": "bbc_zh", "title": "BBC 中文新闻", "mode": "proxy",
     "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"},
    {"id": "solidot", "title": "Solidot 科技新闻", "mode": "direct",
     "url": "https://www.solidot.org/index.rss"},
]


@dataclass
class FeedItem:
    source_id: str = ""
    source_title: str = ""
    title: str = ""
    link: str = ""
    published: str = ""
    summary: str = ""
    _raw: dict = field(default_factory=dict, repr=False)


def _fetch_bytes(url: str, mode: str = "proxy") -> bytes:
    """抓取字节（超时 + 忽略证书问题，兼容部分源）。

    mode="proxy" 经 7897 代理（海外源）；mode="direct" 直连（国内可达源）。
    """
    handlers: list = []
    if mode == "direct":
        pass  # 直连：不加代理处理器
    else:
        handlers.append(urllib.request.ProxyHandler({
            "http": PROXY, "https": PROXY,
        }))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (guji-external/0.1; +https://localhost)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read()


def parse_feed_bytes(data: bytes) -> list[dict]:
    """用 feedparser 解析 RSS/Atom 字节，返回标准化条目列表。"""
    import feedparser
    parsed = feedparser.parse(data)
    out: list[dict] = []
    for e in parsed.entries[:MAX_ITEMS_PER_SOURCE]:
        out.append({
            "title": getattr(e, "title", "").strip(),
            "link": getattr(e, "link", "").strip(),
            "published": getattr(e, "published", "") or getattr(e, "updated", ""),
            "summary": (getattr(e, "summary", "") or getattr(e, "description", ""))[:280],
        })
    return out


def fetch_source(src: dict) -> dict:
    """抓取单个源，异常降级返回 {'ok': False, 'error': ...}。"""
    try:
        data = _fetch_bytes(src["url"], src.get("mode", "proxy"))
    except Exception as exc:  # 网络/超时/证书 → 单源降级
        return {"id": src["id"], "title": src["title"], "url": src["url"],
                "ok": False, "error": f"{type(exc).__name__}: {exc}", "items": []}
    try:
        items = parse_feed_bytes(data)
    except Exception as exc:
        return {"id": src["id"], "title": src["title"], "url": src["url"],
                "ok": False, "error": f"解析失败: {exc}", "items": []}
    return {"id": src["id"], "title": src["title"], "url": src["url"],
            "ok": True, "error": "", "items": items}


def fetch_sources(sources: list[dict] | None = None, max_sources: int = 6) -> dict:
    """并发抓取多个源（线程池），聚合返回。sources 为空时用预置源。"""
    import concurrent.futures
    srcs = sources if sources else DEFAULT_SOURCES
    srcs = srcs[:max_sources]
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(srcs) or 1) as ex:
        futs = {ex.submit(fetch_source, s): s for s in srcs}
        for fut in concurrent.futures.as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as exc:  # 防御：单源不应让整批失败
                s = futs[fut]
                results.append({"id": s["id"], "title": s["title"], "url": s["url"],
                                "ok": False, "error": str(exc), "items": []})
    # 按预置顺序稳定返回（as_completed 无序）
    order = {s["id"]: i for i, s in enumerate(srcs)}
    results.sort(key=lambda r: order.get(r["id"], 999))
    return {
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "proxy": PROXY,
        "sources": results,
    }


if __name__ == "__main__":
    # 冒烟：本地直跑验证（走 7897 代理）
    import json
    out = fetch_sources(max_sources=4)
    for s in out["sources"]:
        status = "OK" if s["ok"] else f"FAIL({s['error'][:60]})"
        print(f"[{status}] {s['title']}: {len(s['items'])} items")
        for it in s["items"][:2]:
            print(f"    - {it['title'][:60]} | {it['link'][:70]}")
    print(json.dumps({"fetched_at": out["fetched_at"]}))
