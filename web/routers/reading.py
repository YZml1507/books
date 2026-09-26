"""web/routers/reading.py — 读书域 HTTP 绑定。

检索 / 定位 / 比对 / 深度研究 / 研究问答 / 概念普查 / 两书对照 / 书目 /
索引统计 / 研究线程 / 读书视图。与 CLI（scripts/ask.py）调同一批 service
函数，保证两端输出一致。

契约登记（R2517，审-P2-3）：研究域端点的「对象不存在」走 200 +
`{"error": "中文原因"}` 语义（bookstudy/compare_works/research/ask），
是 selftest 钉扎的既有约定（`bookstudy.summary.missing` 等）——前端
按 `j.error` 分支渲染，不翻 404；与 search/addr 的 400-ValidationError
约定并存是有意的两套语义，非缺陷。
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import deps, services
from ..schemas import AskRequest, ThreadRecordRequest

router = APIRouter(tags=["reading"])


@router.get("/api/search")
def search(q: str = "", layer: str | None = None, work: str | None = None,
           genre: str | None = None, scheme: str | None = None,
           limit: int = 10) -> dict:
    """全文检索（与 CLI `ask.py search` 同内核 Corpus.search）。"""
    return services.search(q, layer=layer, work=work, genre=genre,
                           scheme=scheme, limit=limit)


@router.get("/api/addr")
def addr(scheme: str = "zhouyi", gua: int | None = None,
         yao: str | None = None, layer: str | None = None,
         addr_name: str | None = None, addr1: int | None = None,
         addr2: str | None = None, limit: int = 20) -> dict:
    """地址定位。zhouyi 用 gua/yao；其余 scheme 用 addr_name/addr1/addr2。"""
    return services.addr(scheme, gua=gua, yao=yao, layer=layer,
                         addr_name=addr_name, addr1=addr1, addr2=addr2,
                         limit=limit)


@router.get("/api/compare")
def compare(gua: int, yao: str = "九三", layer: str = "經",
            allow_damaged: bool = False) -> dict:
    """跨版本同址比对 + 差异摘要。"""
    return services.compare(gua, yao, layer, allow_damaged=allow_damaged)


@router.get("/api/research")
def research(q: str = "", max_addresses: int = 3,
             allow_damaged: bool = False) -> dict:
    """深度研究：检索→读地址→扩展，返回证据集 + 步骤链 + 差异摘要。"""
    return services.deep_research(q, max_addresses=max_addresses,
                                  allow_damaged=allow_damaged)


# R228l 登记：/api/ask 与 /api/stats 前端零调用——有意保留给
# CLI 等价物与第三方集成（selftest 断言仍钉着其契约），不是僵尸。
@router.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """研究问答：证据集 + 确定性综合（拒绝时不综合，G7）。"""
    return services.ask(req)


@router.get("/api/concept")
def concept(q: str = "", per_work: int = 3) -> dict:
    """跨书概念研究：作品级普查 + 同址多见证地图。"""
    return services.concept(q, per_work)


@router.get("/api/compare_works")
def compare_works(work_a: str = "", work_b: str = "", q: str = "",
                  per_work: int = 3) -> dict:
    """两书对照：两书 top 证据并排 + 层分布对照 + 同址命中地址。"""
    return services.compare_works(work_a, work_b, q, per_work)


@router.get("/api/works")
def works() -> dict:
    """语料书目（与 CLI `ask.py works` 同内核 Corpus.coverage）。"""
    return services.works()


@router.get("/api/stats")
def stats() -> dict:
    """索引统计（与 CLI `ask.py stats` 同内核）。

    前端零调用——有意保留（见本文件 /api/ask 上方 R228l 登记）。"""
    return services.stats()


@router.get("/api/threads")
def threads(status: str = "open", limit: int = 50) -> dict:
    """研究线程列表（G9：可恢复的研究线索）。limit≤500 供备份/wipe
    够到全部线程（R2500/R143-P1-3）。"""
    return services.threads(status, limit)


@router.delete("/api/threads")
def threads_clear() -> dict:
    """全量清研究线程+手记（R2500/R143-P1-3：「忘掉我的数据」用——
    逐条删只够到前 50 条且 claims 原文留库）。"""
    deps.write_guard()   # R2357
    return services.threads_clear_all()


@router.get("/api/threads/{tid}")
def thread_detail(tid: int) -> dict:
    """单条线程完整内容：transcript + derived claims + 证据回查。"""
    return services.thread_detail(tid)


@router.delete("/api/threads/{tid}")
def thread_remove(tid: int) -> dict:
    """删除一条研究线程（R230q：turns 随删，derived claims 解绑保留）。"""
    deps.write_guard()   # R2357
    return services.thread_delete(tid)


@router.patch("/api/threads/{tid}")
def thread_patch(tid: int, status: str) -> dict:
    """改线程状态（R230r / R30-#8：open/parked/closed——收起的线程不再
    占 resume 列表位）。"""
    deps.write_guard()   # R2357
    return services.thread_set_status(tid, status)


@router.post("/api/threads")
def thread_record(req: ThreadRecordRequest) -> dict:
    """写入一条研究结论（G8：断言型 kind 必须带证据，refusal 可无）。"""
    deps.write_guard()   # R2357
    return services.thread_record(req)


@router.get("/api/bookstudy/structure")
def book_structure(work_id: str, sample_chars: int = 60) -> dict:
    """整书结构图：按源序列出各节、体量、层分布、样例。"""
    return services.book_structure(work_id, sample_chars)


@router.get("/api/bookstudy/summary")
def book_summary(work_id: str) -> dict:
    """整书知识卡：节数/单元/字数/层分布/损坏披露/体量极端节。"""
    return services.book_summary(work_id)


@router.get("/api/bookstudy/chapter")
def book_chapter(work_id: str, scheme: str, addr_name: str | None = None,
                 addr1: int | None = None, file: str | None = None,
                 limit: int = 60) -> dict:
    """单节阅读视图：按源序列出每个单元 + 引用。"""
    return services.book_chapter(work_id, scheme, addr_name=addr_name,
                                 addr1=addr1, file=file, limit=limit)
