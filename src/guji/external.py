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
import urllib.parse
from dataclasses import dataclass, field

PROXY = os.environ.get("GUJI_PROXY", "http://127.0.0.1:7897")
FETCH_TIMEOUT = 12          # 单源抓取超时（秒）
MAX_ITEMS_PER_SOURCE = 8    # 每源最多返回条目数
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # 响应大小上限 4 MB（DoS 防护）

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

    安全（R12 审查）：URL scheme 白名单 + 响应大小上限（防 SSRF/DoS）。
    """
    # SSRF 防护：拒绝 file://、非 http(s) scheme、内网/元数据地址
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"非法 scheme: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "") or host.startswith("127.") or host.startswith("10.") \
       or host.startswith("192.168.") or host == "169.254.169.254" or host == "0.0.0.0":
        raise ValueError(f"拒绝内网/元数据地址: {host}")
    # 172.16/12 私网段检查
    if host.startswith("172."):
        try:
            if 16 <= int(host.split(".")[1]) <= 31:
                raise ValueError(f"拒绝私网地址: {host}")
        except (IndexError, ValueError):
            pass

    handlers: list = []
    if mode == "direct":
        pass  # 直连：不加代理处理器
    else:
        handlers.append(urllib.request.ProxyHandler({
            "http": PROXY, "https": PROXY,
        }))
    # R230a-42（R15-P2-2）：此前关主机名校验+CERT_NONE，出站抓取可被路径
    # 上中间人换内容。恢复默认校验；证书失败走 fetch_source 单源降级。
    ctx = ssl.create_default_context()
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (guji-external/0.1; +https://localhost)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
        # DoS 防护：响应大小上限 4 MB（feed 正常 <100 KB，恶意超大源不致耗尽内存）
        return resp.read(MAX_RESPONSE_BYTES)


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
    """抓取单个源，异常降级返回 {'ok': False, 'error': ...}。

    R230g（R19-P3-1）：error 字段此前塞原始英文异常（URLError/DNS
    原文）——前端零调用时无感，一旦 UI 复用就触「英文原文上屏」红线。
    error 只留中文人话；英文细节进 debug 字段供排查。"""
    try:
        data = _fetch_bytes(src["url"], src.get("mode", "proxy"))
    except Exception as exc:  # 网络/超时/证书 → 单源降级
        return {"id": src["id"], "title": src["title"], "url": src["url"],
                "ok": False, "error": "这个源暂时拉不到",
                "debug": f"{type(exc).__name__}: {exc}", "items": []}
    try:
        items = parse_feed_bytes(data)
    except Exception as exc:
        return {"id": src["id"], "title": src["title"], "url": src["url"],
                "ok": False, "error": "这个源的内容暂时读不懂",
                "debug": f"解析失败: {exc}", "items": []}
    return {"id": src["id"], "title": src["title"], "url": src["url"],
            "ok": True, "error": "", "items": items}


def fetch_sources(sources: list[dict] | None = None, max_sources: int = 6) -> dict:
    """并发抓取多个源（线程池），聚合返回。sources 为空时用预置源。

    缓存/限流（R12 审查）：进程内 5 分钟 TTL 缓存，避免每次刷新重抓6源
    打上游 rate limit；10 秒内最多 1 次抓取（限流）。
    """
    import concurrent.futures
    global _FETCH_CACHE, _FETCH_LAST_AT

    now = time.time()
    # 限流：10 秒内最多 1 次抓取（命中缓存不算）
    if now - _FETCH_LAST_AT < 10:
        if _FETCH_CACHE:
            return _FETCH_CACHE
    # 缓存命中：5 分钟内返回上次结果
    if _FETCH_CACHE and (now - _FETCH_LAST_AT) < 300:
        return _FETCH_CACHE

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
    out = {
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "proxy": PROXY,
        "sources": results,
    }
    _FETCH_CACHE = out
    _FETCH_LAST_AT = now
    return out


# 缓存状态（R12 审查：避免重复抓取打上游 rate limit）
_FETCH_CACHE: dict | None = None
_FETCH_LAST_AT: float = 0.0


def fortune_wrap(raw: dict, date_str: str | None = None) -> dict:
    """把原始 news feed 包装为"每日运势"风格的内容。

    不是返回新闻列表，而是包装成命理博主口吻的"今天需要注意什么"。
    用于 /api/daily 端点的外部资讯部分。
    """
    # R2350g（R106-F4）：缺 date 回落锚 UTC+8——UTC 部署早 8 点前
    # 裸 today() 会取到昨天。
    from datetime import datetime as _dt, timedelta as _td, \
        timezone as _tz
    ds = date_str or _dt.now(_tz(_td(hours=8))).date().isoformat()

    items: list[dict] = []
    for src in raw.get("sources", []):
        if not src.get("ok"):
            continue
        for it in src.get("items", [])[:3]:
            items.append(it)

    if not items:
        return {"date": ds, "ok": False, "items": [],
                "summary": "今天外部资讯暂时拉不到，晚点再看看 🔮"}

    # 取前 3 条作为"今日要点"
    top = items[:3]
    summaries = []
    for i, it in enumerate(top):
        summaries.append(f"{i+1}. {it['title'][:60]}")

    summary = (
        f"🌟 今天外部世界有 {len(top)} 件事值得关注：\n" + "\n".join(summaries)
    )

    return {
        "date": ds,
        "ok": True,
        "items": [{"title": it["title"], "link": it["link"],
                    "published": it.get("published", ""),
                    "summary": it.get("summary", "")[:120]}
                   for it in top],
        "summary": summary,
        "source_count": len(raw.get("sources", [])),
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
    # 测试 fortune_wrap
    fw = fortune_wrap(out)
    print(f"\nfortune_wrap: ok={fw['ok']}, items={len(fw['items'])}")
    print(json.dumps({"fetched_at": out["fetched_at"], "fortune": fw["summary"][:200]},
                     ensure_ascii=False))
