"""web/app.py — 八字排盘网页端后端（FastAPI）。

编排层，复用 src/guji 的既有模块，不复制业务逻辑：
  POST /api/bazi   {year, month, day, hour, gender, use_llm, question,
                    calendar_type, lunar_year?, lunar_month?, lunar_day?,
                    lunar_leap?, scope, range_start?, range_end?,
                    ask_date, ask_hour, location}
                  -> {paipan, calc, evidence[], llm}
  GET  /          单页前端（web/static/index.html）

scope：
  * day   单日（默认，用 ask_date/ask_hour）
  * range 日期范围（range_start~range_end 逐日流日关系，≤31 天）
  * life  生平（大运表：起运岁数 + 每运 10 年干支 + 与日主十神）
calendar_type：solar（公历，默认）| lunar（农历，lunar_year/month/day/leap）

红线遵守（与 CLI 一致）：
  * LLM KEY 只在服务端（llm_config.json，已 gitignore），API 响应不回传 key。
  * LLM 解读不落库、不缓存——每次请求即时调用，仅进程内返回。
  * 引用与生成分离：evidence（古籍引文）与 llm（生成文本）分字段返回，
    calc（运算事实）为结构化坐标，前端分段展示。
  * 输入校验在系统边界（Pydantic + 显式范围检查），非法输入 400 中文报错。
  * 首请求可能较慢（bge 语义路径首次加载模型/向量缓存），后续复用缓存。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# PyInstaller 单文件模式：__file__ 在 _MEIPASS 临时解压目录，exe 在 dist/。
# data/ 在项目根（dist/ 的父目录），不是 exe 同目录——开发期 ROOT 是项目根，
# frozen 期 ROOT 指向 exe 所在 dist/，需向上一级找含 data/ 的项目根。
if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    # exe 在 <项目根>/dist/books_app.exe，data/ 在 <项目根>/data/
    parent = os.path.dirname(exe_dir)
    if os.path.isdir(os.path.join(parent, "data", "index")):
        ROOT = parent
    else:
        # exe 被拷到别处（无项目根），退回 exe 同目录——用户需自带 data/
        ROOT = exe_dir
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from guji import liuyao as liuyao_mod  # noqa: E402
from guji import huangli as huangli_mod  # noqa: E402
from guji import qiming as qiming_mod  # noqa: E402
from guji import taohua as taohua_mod  # noqa: E402
from guji import tarot as tarot_mod  # noqa: E402
from guji import hehun as hehun_mod  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from guji import external as external_feed  # noqa: E402
from guji import history as history_db  # noqa: E402
from guji import llm_reader  # noqa: E402
from guji import lunar  # noqa: E402
from guji.bazi import compute  # noqa: E402
from guji.bazi_calc import calc as bazi_calc  # noqa: E402
from guji.bazi_calc import calc_life, calc_range  # noqa: E402
from guji.bazi_lookup import retrieve_fast, retrieve_semantic  # noqa: E402
from guji.compare import compare_address  # noqa: E402
from guji.knowledge import KnowledgeBase  # noqa: E402
from guji.research import concept_census, compare_works, research  # noqa: E402
from guji.search import Corpus  # noqa: E402
from guji.bookstudy import book_summary  # noqa: E402
from guji.bookstudy import chapter as book_chapter  # noqa: E402
from guji.bookstudy import structure as book_structure  # noqa: E402

app = FastAPI(title="古籍智慧助手（读书 + 八字）", version="0.5.0")

# 静态前端路径：frozen 时 spec 把 web/static 内嵌进 _MEIPASS 临时解压目录，
# 必须优先用它——按"exe + data/ 单独分发"模型，exe 旁没有 web/ 目录，
# 若从 ROOT 找首页会 404/500（bundled 副本不可达）。开发期 _MEIPASS 不存在，
# 走项目根（审查轨 R18a 44d-1 移交，修复属优化轨 web/ 领土）。
# 注意 _MEIPASS 缺省不能给 ""：join("", ...) 得到相对路径，恰好被 cwd 命中。
_MEIPASS = getattr(sys, "_MEIPASS", None)
_STATIC_CANDIDATES = (
    [os.path.join(_MEIPASS, "web", "static", "index.html")] if _MEIPASS else []
) + [os.path.join(ROOT, "web", "static", "index.html")]
INDEX = next((p for p in _STATIC_CANDIDATES if os.path.exists(p)),
             _STATIC_CANDIDATES[-1])
CORPUS_DB = os.path.join(ROOT, "data", "index", "corpus.db")
KNOWLEDGE_DB = os.path.join(ROOT, "data", "index", "knowledge.db")

YEAR_LO, YEAR_HI = 1900, 2100
SCOPES = ("day", "range", "life")
CALENDARS = ("solar", "lunar")


class BaziRequest(BaseModel):
    year: int = Field(..., description="公历年份（calendar_type=solar 时直接使用）")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    use_llm: bool = False
    question: str | None = None
    calendar_type: str = "solar"          # solar | lunar
    lunar_year: int | None = None
    lunar_month: int | None = None
    lunar_day: int | None = None
    lunar_leap: bool = False              # 是否闰月
    scope: str = "day"                    # day | range | life
    range_start: str | None = Field(None, description="范围起点 YYYY-MM-DD")
    range_end: str | None = Field(None, description="范围终点 YYYY-MM-DD")
    ask_date: str | None = Field(None, description="问事日期 YYYY-MM-DD，默认今天")
    ask_hour: int | None = Field(None, description="问事时辰 0-23，默认不比对流时")
    location: str | None = Field(None, description="问事地点（可选，仅提示用）")

    def validate_ranges(self) -> None:
        if self.calendar_type not in CALENDARS:
            raise HTTPException(400, "calendar_type 只能是 solar 或 lunar")
        if self.scope not in SCOPES:
            raise HTTPException(400, f"scope 只能是 {'/'.join(SCOPES)}")
        if self.calendar_type == "lunar":
            if not (self.lunar_year and self.lunar_month and self.lunar_day):
                raise HTTPException(400, "农历输入需提供 lunar_year/month/day")
            if not (1 <= self.lunar_month <= 12):
                raise HTTPException(400, "lunar_month 需在 1-12")
            if not (1 <= self.lunar_day <= 30):
                raise HTTPException(400, "lunar_day 需在 1-30")
        else:
            if not (YEAR_LO <= self.year <= YEAR_HI):
                raise HTTPException(400,
                                    f"year 需在 {YEAR_LO}-{YEAR_HI} 之间（节气表适用范围）")
            if not (1 <= self.month <= 12):
                raise HTTPException(400, "month 需在 1-12")
            if not (1 <= self.day <= 31):
                raise HTTPException(400, "day 需在 1-31")
        if not (0 <= self.hour <= 23):
            raise HTTPException(400, "hour 需在 0-23")
        if self.gender not in ("男", "女"):
            raise HTTPException(400, "gender 只能是 男 或 女")
        if self.ask_hour is not None and not (0 <= self.ask_hour <= 23):
            raise HTTPException(400, "ask_hour 需在 0-23")
        if self.ask_date is not None:
            try:
                d = datetime.strptime(self.ask_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "ask_date 需为 YYYY-MM-DD 格式")
            if not (YEAR_LO <= d.year <= YEAR_HI):
                raise HTTPException(400,
                                    f"ask_date 年份需在 {YEAR_LO}-{YEAR_HI} 之间")
        if self.scope == "range":
            if not (self.range_start and self.range_end):
                raise HTTPException(400, "scope=range 需提供 range_start 和 range_end")
            try:
                datetime.strptime(self.range_start, "%Y-%m-%d")
                datetime.strptime(self.range_end, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(400, "range_start/range_end 需为 YYYY-MM-DD 格式")


def _resolve_birth(req: BaziRequest) -> tuple[int, int, int]:
    """把请求里的生日解析成公历 (year, month, day)。农历输入在此转换。"""
    if req.calendar_type == "lunar":
        try:
            d = lunar.lunar_to_solar(req.lunar_year, req.lunar_month,
                                     req.lunar_day, req.lunar_leap)
        except ValueError as exc:
            raise HTTPException(400, f"农历换算失败：{exc}") from exc
        if not (YEAR_LO <= d.year <= YEAR_HI):
            raise HTTPException(400,
                                f"换算后公历年份需在 {YEAR_LO}-{YEAR_HI} 之间")
        return d.year, d.month, d.day
    return req.year, req.month, req.day


@app.get("/")
def index():
    if not os.path.exists(INDEX):
        raise HTTPException(500, "前端文件缺失：web/static/index.html")
    return FileResponse(INDEX)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": llm_reader.available()}


@app.get("/api/external/news")
def external_news():
    """外部资讯通道（P5）：抓取预置 RSS/Atom 源，走 7897 代理或直连。

    只返回进程内抓取结果，不落库、不写 history——"最新消息"是即时信息，
    与古籍语料 Source 层严格隔离（红线：引用与生成分离、原文与解读分离）。
    单源失败自动降级，不影响其余源。
    """
    try:
        return external_feed.fetch_sources(max_sources=6)
    except Exception as exc:  # 整个通道异常（如代理未开）→ 结构化报错
        return {"fetched_at": None, "proxy": external_feed.PROXY,
                "sources": [], "error": f"{type(exc).__name__}: {exc}"}


@app.post("/api/bazi")
def bazi_api(req: BaziRequest):
    req.validate_ranges()
    by, bm, bd = _resolve_birth(req)   # 农历在此换算成公历
    try:
        b = compute(by, bm, bd, req.hour, req.gender)
    except Exception as exc:  # 排盘异常（如节气表范围外）→ 4xx，不崩
        raise HTTPException(422, f"排盘失败：{exc}") from exc

    # 运算层：按 scope 分支（单日 / 日期范围 / 生平大运），全部纯坐标可核验
    ask_date = req.ask_date or date.today().isoformat()
    if req.scope == "range":
        try:
            calc_out = calc_range(b, req.range_start, req.range_end, req.ask_hour)
        except ValueError as exc:  # 倒序 / 超 31 天 → 400 中文报错
            raise HTTPException(400, str(exc)) from exc
        calc_out["scope"] = "range"
    elif req.scope == "life":
        calc_out = calc_life(b, by)
        calc_out["scope"] = "life"
    else:
        calc_out = bazi_calc(b, ask_date=ask_date, ask_hour=req.ask_hour)
        calc_out["scope"] = "day"
    if req.location:
        calc_out["location"] = req.location

    evidence = retrieve_fast(b, per_query=2, per_work=1)
    # 去重（同一单元 FTS 多词命中），保留前 12 条
    seen, dedup = set(), []
    for e in evidence:
        k = (e["work_id"], e["page_anchor"], e["text"][:40])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
        if len(dedup) >= 12:
            break
    evidence = dedup

    llm_out = {"ok": False, "text": None, "model": None}
    if req.use_llm:
        if not llm_reader.available():
            llm_out["text"] = ("未配置 LLM：请复制 llm_config.example.json 为 "
                               "llm_config.json 并填写 base_url/api_key。")
        else:
            try:
                text = llm_reader.interpret(b.render(), evidence, req.question,
                                            calc_out)
                llm_out = {"ok": True, "text": text,
                           "model": os.environ.get("LLM_MODEL", "llm_config.json")}
            except Exception as exc:  # 网络/API 错误：引用证据不受影响
                llm_out["text"] = f"LLM 调用失败：{exc}"

    paipan_out = {
        "render": b.render(),
        "nayin": b.nayin,
        "warn": b.warn,
    }
    # 历史库：完整往返入库（用户授权 D-039：独立 history.db，与语料隔离）
    input_snapshot = {
        "year": req.year, "month": req.month, "day": req.day, "hour": req.hour,
        "gender": req.gender, "use_llm": req.use_llm, "question": req.question,
        "calendar_type": req.calendar_type,
        "lunar_year": req.lunar_year, "lunar_month": req.lunar_month,
        "lunar_day": req.lunar_day, "lunar_leap": req.lunar_leap,
        "scope": req.scope, "range_start": req.range_start,
        "range_end": req.range_end,
        "ask_date": ask_date, "ask_hour": req.ask_hour, "location": req.location,
        "birth_resolved": f"{by}-{bm:02d}-{bd:02d}",
    }
    try:
        history_db.save_record(input_snapshot, paipan_out, calc_out,
                               evidence, llm_out)
    except Exception:  # 历史写入失败不阻断主流程
        pass

    return {
        "paipan": paipan_out,
        "calc": calc_out,
        "evidence": evidence,
        "llm": llm_out,
    }


@app.get("/api/history")
def history_list(limit: int = 50):
    """历史列表（轻量字段，供前端列表展示）。"""
    limit = min(max(limit, 1), 200)
    return {"records": history_db.list_records(limit)}


@app.get("/api/history/{rid}")
def history_detail(rid: int):
    """单条完整记录（含排盘/运算/引文/LLM 全文）。"""
    rec = history_db.get_record(rid)
    if rec is None:
        raise HTTPException(404, f"历史记录 {rid} 不存在")
    return rec


@app.delete("/api/history/{rid}")
def history_delete(rid: int):
    """删除一条历史记录。"""
    if not history_db.delete_record(rid):
        raise HTTPException(404, f"历史记录 {rid} 不存在")
    return {"ok": True, "deleted": rid}


# ---------------------------------------------------------------------------
# P1 读书网页化：复用 src/guji 既有模块，只编排不复制逻辑。
# 与 CLI（scripts/ask.py）调同一批函数（Corpus.search / at_address /
# at_scheme / compare_address / coverage / stats），保证两端输出一致。
# ---------------------------------------------------------------------------

# 五种地址体系的 label（scheme -> 地址形式说明），供前端 addr 视图提示
SCHEME_LABELS = {
    "zhouyi": "卦·爻（周易系，addr1=卦號 1-64，addr2=爻位）",
    "bcv": "卷:章:節（圣经系，addr_name=卷名）",
    "yilin": "卦·林（焦氏易林，addr1=本卦，addr2=之卦）",
    "booksec": "BOOK:節（Herodotus/Plato/Iliad，addr1=卷）",
    "play": "剧目:幕場（Shakespeare，addr1=剧目序号 1-44，addr2='ACT <roman> SCENE <roman>'）",
    "euclid": "BOOK:proposition（几何原本，addr1=卷，addr2=命题）",
    "None": "无正典地址（页锚点）",
}


def _hit_dict(h) -> dict:
    """Hit -> JSON-safe dict（citation/disclosure 为既有展示串，不做二次加工）。"""
    return {
        "work_id": h.work_id,
        "title": h.title,
        "attribution": h.attribution,
        "edition": h.edition,
        "page_anchor": h.page_anchor,
        "scheme": h.scheme,
        "addr_name": h.addr_name,
        "gua": h.gua,          # = addr1
        "yao": h.yao,          # = addr2
        "layer": h.layer,
        "text": h.text,
        "file": h.file,
        "score": h.score,
        "skipped_chars": h.skipped_chars,
        "suspect": h.suspect,
        "citation": h.citation(),
        "disclosure": h.disclosure(),
    }


@app.get("/api/search")
def api_search(q: str = "", layer: str | None = None, work: str | None = None,
               genre: str | None = None, scheme: str | None = None,
               limit: int = 10):
    """全文检索（与 CLI `ask.py search` 同内核 Corpus.search）。

    q 为空时返回 400——检索必须有查询词；地址定位请用 /api/addr。
    """
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "q 不能为空——检索需要查询词；找某个地址请用 /api/addr")
    limit = min(max(limit, 1), 50)
    c = Corpus(CORPUS_DB)
    try:
        hits = c.search(q, limit=limit, layer=layer, work_id=work,
                        genre=genre, scheme=scheme)
        return {"query": q, "count": len(hits), "hits": [_hit_dict(h) for h in hits]}
    finally:
        c.close()


@app.get("/api/addr")
def api_addr(scheme: str = "zhouyi", gua: int | None = None,
             yao: str | None = None, layer: str | None = None,
             addr_name: str | None = None, addr1: int | None = None,
             addr2: str | None = None, limit: int = 20):
    """地址定位（与 CLI `ask.py addr` 同内核）。

    zhouyi 用 gua/yao（=addr1/addr2 便利别名，D-016）；其余 scheme 用
    addr_name/addr1/addr2 走通用 at_scheme。scheme 显式声明，杜绝
    Psalms-99 == 卦99 类跨体系碰撞（D-005）。
    """
    if scheme not in SCHEME_LABELS:
        raise HTTPException(400, f"scheme 只能是 {'/'.join(SCHEME_LABELS)}")
    limit = min(max(limit, 1), 100)
    c = Corpus(CORPUS_DB)
    try:
        if scheme == "zhouyi":
            if gua is None:
                raise HTTPException(400, "zhouyi 定位需提供 gua（1-64）")
            hits = c.at_address(gua, yao, layer=layer, limit=limit)
        else:
            hits = c.at_scheme(scheme, addr_name=addr_name, addr1=addr1,
                               addr2=addr2, layer=layer, limit=limit)
        return {"scheme": scheme, "count": len(hits),
                "hits": [_hit_dict(h) for h in hits]}
    finally:
        c.close()


@app.get("/api/compare")
def api_compare(gua: int, yao: str = "九三", layer: str = "經"):
    """跨版本同址比对 + 差异摘要（复用 compare.compare_address，CLI `ask.py compare` 同内核）。"""
    if not (1 <= gua <= 64):
        raise HTTPException(400, "gua 需在 1-64")
    if layer not in ("經", "注", "十翼", "圖", "正文", "傳"):
        # 允许任意 layer 字符串（不校验枚举，保持与 CLI 一致宽容度）
        pass
    c = Corpus(CORPUS_DB)
    try:
        cmp = compare_address(c, gua, yao, layer=layer)
        findings = []
        for f in cmp.findings:
            findings.append({
                "kind": f.kind, "at": f.at, "base": f.base,
                "others": f.others, "note": f.note, "base_id": f.base_id,
                "line": f.line(),
            })
        return {
            "addr": cmp.addr,
            "reference": cmp.reference,
            "agree": cmp.agree,
            "counts": cmp.counts(),
            "witnesses": cmp.witnesses,
            "citations": cmp.citations,
            "commentary": cmp.commentary,
            "findings": findings,
        }
    finally:
        c.close()


class AskRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=200, description="研究问题/检索词")
    use_llm: bool = False
    allow_damaged: bool = False
    max_addresses: int = Field(3, ge=1, le=6)


class ThreadEvidence(BaseModel):
    work_id: str = ""
    file: str = ""
    quote: str = ""
    raw_start: int | None = None
    raw_end: int | None = None
    page_anchor: str | None = None
    scheme: str | None = None
    addr1: int | None = None
    addr2: str | None = None
    role: str = "supports"


class ThreadRecordRequest(BaseModel):
    """研究线程写入（R34b）：一条 derived claim + 可选证据（G8 纪律）。"""
    kind: str = Field(..., description="summary | diff | link | answer | refusal")
    claim: str = Field(..., min_length=1, max_length=2000)
    method: str = Field(..., min_length=1, max_length=100)
    evidence: list[ThreadEvidence] = Field(default_factory=list)
    confidence: str | None = None
    thread_id: int | None = None


@app.get("/api/research")
def api_research(q: str = "", max_addresses: int = 3, allow_damaged: bool = False):
    """深度研究（R18b）：检索→读地址→扩展的多轮循环，返回证据集 + 步骤链 + 差异摘要。

    确定性算法无 LLM——每步 (action/query/found/kept) 都返回，「链路可展示」（G4）。
    命中全部位于质量闸门标记区时拒绝（G7），allow_damaged=true 可查看。
    """
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "q 不能为空")
    if len(q) > 200:
        raise HTTPException(400, "q 过长（≤200 字符）")
    if not (1 <= max_addresses <= 6):
        raise HTTPException(400, "max_addresses 需在 1-6")
    c = Corpus(CORPUS_DB)
    try:
        r = research(c, q, max_addresses=max_addresses, allow_damaged=allow_damaged)
        return {
            "question": r.question, "refused": r.refused, "reason": r.reason,
            "steps": r.step_dict(),
            "evidence": [_hit_dict(h) for h in r.evidence],
            "flagged": [_hit_dict(h) for h in r.flagged],
            "comparisons": r.comparisons,
        }
    finally:
        c.close()


@app.get("/api/concept")
def api_concept(q: str = "", per_work: int = 3):
    """跨书概念研究（R18b）：一个概念词在全部语料的作品级普查 + 同址多见证地图。"""
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "q 不能为空")
    if len(q) > 200:
        raise HTTPException(400, "q 过长（≤200 字符）")
    per_work = min(max(per_work, 1), 10)
    c = Corpus(CORPUS_DB)
    try:
        return concept_census(c, q, per_work=per_work)
    finally:
        c.close()


@app.get("/api/compare_works")
def api_compare_works(work_a: str = "", work_b: str = "", q: str = "",
                      per_work: int = 3):
    """两书对照研究（R24b，愿景 §7 Comparative Study）：指定两本书 + 一个概念，
    返回两书各自的 top 证据（citation+层+原文）并排、层分布对照、以及两书
    同址命中的 zhouyi 地址——共享地址正是版本/注家分歧开始之处。"""
    work_a = (work_a or "").strip()
    work_b = (work_b or "").strip()
    q = (q or "").strip()
    if not work_a or not work_b:
        raise HTTPException(400, "work_a / work_b 不能为空")
    if not q:
        raise HTTPException(400, "q 不能为空")
    if len(q) > 200:
        raise HTTPException(400, "q 过长（≤200 字符）")
    per_work = min(max(per_work, 1), 10)
    c = Corpus(CORPUS_DB)
    try:
        return compare_works(c, work_a, work_b, q, per_work=per_work)
    finally:
        c.close()


@app.post("/api/ask")
def api_ask(req: AskRequest):
    """研究问答（R18b）：/api/research 的证据集 + 可选 LLM 白话综合。

    纪律与 /api/bazi 的 llm 层一致：检索拒绝时不调 LLM（G7 不让模型替语料编造）；
    引文由服务器从证据对象渲染，LLM 输出独立成字段，不落库不缓存。
    """
    q = req.q.strip()
    if not q:
        raise HTTPException(400, "q 不能为空")
    c = Corpus(CORPUS_DB)
    try:
        r = research(c, q, max_addresses=req.max_addresses,
                     allow_damaged=req.allow_damaged)
        ev = [_hit_dict(h) for h in r.evidence[:12]]
        resp = {
            "question": r.question, "refused": r.refused, "reason": r.reason,
            "steps": r.step_dict(),
            "evidence": ev,
            "evidence_citations": [h.citation() for h in r.evidence[:12]],
            "comparisons": r.comparisons,
            "llm": None, "llm_error": None,
        }
        if r.refused or not ev:
            return resp
        if req.use_llm:
            if not llm_reader.available():
                resp["llm_error"] = "LLM 未配置（llm_config.json / LLM_API_KEY）"
            else:
                try:
                    text = llm_reader.interpret_research(q, ev, r.comparisons)
                    # R115b（D-161b）：与 /api/bazi 的 llm_out 对齐——生成文本
                    # 必须标注模型来源（GOAL.md 纪律）。llm 为 None 或 dict，
                    # 前端按 dict.text + dict.model 渲染。
                    resp["llm"] = {"ok": True, "text": text,
                                   "model": llm_reader.configured_model()}
                except RuntimeError as exc:
                    resp["llm_error"] = str(exc)
        return resp
    finally:
        c.close()


@app.get("/api/works")
def api_works():
    """语料书目（与 CLI `ask.py works` 同内核 Corpus.coverage）。"""
    c = Corpus(CORPUS_DB)
    try:
        rows = [dict(r) for r in c.coverage()]
        # R48b: merge the manifest source marker so local-imported works
        # (add_local_work, R31b) are distinguishable from built-in corpus.
        src = {}
        try:
            man = json.load(open(os.path.join(ROOT, "data", "catalog",
                                              "corpus_manifest.json"),
                                 encoding="utf-8"))
            src = {w.get("id"): w.get("source") for w in man.get("works", [])
                   if w.get("id")}
        except (OSError, ValueError):
            src = {}
        for r in rows:
            r["source"] = src.get(r["id"]) or "kanripo/内置"
        return {"works": rows, "total": len(rows)}
    finally:
        c.close()


@app.get("/api/stats")
def api_stats():
    """索引统计（与 CLI `ask.py stats` 同内核）。"""
    c = Corpus(CORPUS_DB)
    try:
        stats = c.stats()
        layers = [dict(r) for r in c.db.execute(
            "SELECT layer, count(*) n FROM unit GROUP BY layer ORDER BY n DESC")]
        meta = [dict(r) for r in c.db.execute(
            "SELECT key, value FROM build_meta")]
        return {"stats": stats, "layers": layers, "meta": meta,
                "schemes": SCHEME_LABELS}
    finally:
        c.close()


@app.get("/api/threads")
def api_threads():
    """研究线程列表（G9：可恢复的研究线索，复用 KnowledgeBase.resume）。"""
    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        rows = [dict(r) for r in kb.resume()]
        return {"threads": rows, "stats": kb.stats()}
    finally:
        kb.close()


@app.get("/api/threads/{tid}")
def api_thread_detail(tid: int):
    """单条研究线程完整内容：transcript + derived claims + 证据回查。"""
    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        turns = [dict(r) for r in kb.thread_transcript(tid)]
        if not turns:
            raise HTTPException(404, f"线程 {tid} 不存在或暂无对话")
        claims = []
        for row in kb.db.execute("SELECT id FROM derived WHERE thread_id=? ORDER BY id",
                                 (tid,)):
            d = kb.get(row["id"])
            if d is None:
                continue
            claims.append({
                "id": d.id, "kind": d.kind, "claim": d.claim, "method": d.method,
                "confidence": d.confidence, "created_at": d.created_at,
                "evidence": [{
                    "role": e.role, "work_id": e.work_id, "file": e.file,
                    "page_anchor": e.page_anchor, "scheme": e.scheme,
                    "addr1": e.addr1, "addr2": e.addr2, "quote": e.quote,
                } for e in d.evidence],
            })
        v = kb.verify(os.path.join(ROOT, "data", "raw"))
        return {"turns": turns, "claims": claims, "verify": v}
    finally:
        kb.close()


@app.post("/api/threads")
def api_thread_record(req: ThreadRecordRequest):
    """研究线程写入（R34b）：把一条研究结论记入 G9 线程，跨会话可恢复。

    G8 纪律原样继承自 knowledge.record：kind ∈ {summary, diff, link, answer}
    是断言型，必须带至少一条证据，否则 400；kind='refusal' 允许无证据（G7：
    「证据不足」本身是合法研究输出）。证据只收真实引文字段，服务器端落库。
    """
    from guji.knowledge import Evidence  # noqa: E402

    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        ev = [Evidence(work_id=e.work_id, file=e.file,
                       raw_start=e.raw_start if e.raw_start is not None else -1,
                       raw_end=e.raw_end if e.raw_end is not None else -1,
                       quote=e.quote, page_anchor=e.page_anchor,
                       scheme=e.scheme, addr1=e.addr1, addr2=e.addr2,
                       role=e.role)
              for e in req.evidence]
        try:
            did = kb.record(req.kind, req.claim, req.method, ev,
                            confidence=req.confidence, thread_id=req.thread_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        row = kb.db.execute(
            "SELECT thread_id FROM derived WHERE id = ?", (did,)).fetchone()
        return {"derived_id": did, "thread_id": row["thread_id"] if row else None,
                "kind": req.kind, "claim": req.claim[:120],
                "n_evidence": len(ev)}
    finally:
        kb.close()


# ---------------------------------------------------------------------------
# Book Study (R23b): structured reading map + chapter view
# ---------------------------------------------------------------------------

@app.get("/api/bookstudy/structure")
def api_book_structure(work_id: str, sample_chars: int = 60):
    """Works structural map: sections in source order, sizes, layers, samples."""
    work_id = (work_id or "").strip()
    if not work_id:
        raise HTTPException(400, "work_id 不能为空")
    sample_chars = min(max(sample_chars, 20), 200)
    c = Corpus(CORPUS_DB)
    try:
        return book_structure(c, work_id, sample_chars=sample_chars)
    finally:
        c.close()


@app.get("/api/bookstudy/summary")
def api_book_summary(work_id: str):
    """Book Summary (R27b): 整本书结构化知识卡——节数/单元/总字数/层分布/
    损坏披露/未编址/体量极端节。纯只读聚合。"""
    work_id = (work_id or "").strip()
    if not work_id:
        raise HTTPException(400, "work_id 不能为空")
    c = Corpus(CORPUS_DB)
    try:
        return book_summary(c, work_id)
    finally:
        c.close()


@app.get("/api/bookstudy/chapter")
def api_book_chapter(work_id: str, scheme: str,
                     addr_name: str | None = None,
                     addr1: int | None = None,
                     file: str | None = None,
                     limit: int = 60):
    """One section's reading view: every unit in source order with citations."""
    work_id = (work_id or "").strip()
    scheme = (scheme or "").strip()
    if not work_id:
        raise HTTPException(400, "work_id 不能为空")
    if not scheme:
        raise HTTPException(400, "scheme 不能为空")
    limit = min(max(limit, 1), 200)
    c = Corpus(CORPUS_DB)
    try:
        return book_chapter(c, work_id, scheme,
                            addr_name=addr_name, addr1=addr1,
                            file=file, limit=limit)
    finally:
        c.close()


# ---------------------------------------------------------------------------
# P3 六爻占卜 + 黄历择日（本地纯计算，复用 zhouyi 语料查卦辞/爻辞）
# ---------------------------------------------------------------------------

class LiuyaoRequest(BaseModel):
    method: str = "coins"        # coins | time
    # coins 法：可选 seed（复验用），不传则真随机
    seed: int | None = None
    # time 法：公历年/月/日/时 → 用 lunar.py 转农历后起卦
    year: int | None = None
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    use_llm: bool = False
    question: str | None = None


@app.post("/api/liuyao")
def api_liuyao(req: LiuyaoRequest):
    """六爻起卦（本地计算）+ 卦辞/爻辞引用（复用 zhouyi 语料）。

    红线：起卦坐标由本地代码算出（可核验），卦辞/爻辞从已入库的
    周易语料取出（G2 引用可核验），LLM 解读另字段返回（标注生成）。
    """
    import random as _rng
    if req.method == "coins":
        rng = _rng.Random(req.seed) if req.seed is not None else _rng.Random()
        ben = liuyao_mod.cast_coins(rng)
    elif req.method == "time":
        if not all(v is not None for v in (req.year, req.month, req.day, req.hour)):
            raise HTTPException(400, "时间起卦需 year/month/day/hour")
        if not (YEAR_LO <= req.year <= YEAR_HI):
            raise HTTPException(400, f"year 须在 {YEAR_LO}-{YEAR_HI}，收到 {req.year}")
        if not (1 <= req.month <= 12):
            raise HTTPException(400, f"month 须在 1-12，收到 {req.month}")
        if not (1 <= req.day <= 31):
            raise HTTPException(400, f"day 须在 1-31，收到 {req.day}")
        if not (0 <= req.hour <= 23):
            raise HTTPException(400, f"hour 须在 0-23，收到 {req.hour}")
        # 公历 → 农历（lunar.py）
        try:
            lm_info = lunar.solar_to_lunar(req.year, req.month, req.day)
        except ValueError as exc:
            raise HTTPException(400, f"公历转农历失败：{exc}")
        ly, lm, ld = lm_info["year"], lm_info["month"], lm_info["day"]
        hour_zhi = (req.hour + 1) // 2 % 12 + 1   # 0-23 → 子=1..亥=12
        ben = liuyao_mod.cast_time(ly, lm, ld, hour_zhi)
    else:
        raise HTTPException(400, f"method 须为 coins|time，收到 {req.method}")

    bian = liuyao_mod.changing_hexagram(ben)
    # 卦辞/爻辞引用：从 zhouyi 语料取本卦+变卦的经文
    c = Corpus(CORPUS_DB)
    try:
        ben_jing = [_hit_dict(h) for h in c.at_address(ben.gua_number, layer="經", limit=10)]
        bian_jing = [_hit_dict(h) for h in c.at_address(bian.gua_number, layer="經", limit=10)]
    finally:
        c.close()

    llm_out = {"ok": False, "text": None, "model": None}
    if req.use_llm:
        if not llm_reader.available():
            llm_out["text"] = ("未配置 LLM：请复制 llm_config.example.json 为 "
                               "llm_config.json 并填写 base_url/api_key。")
        else:
            try:
                # 运算事实 = 卦象坐标；引文 = 卦辞/爻辞
                calc_dict = {
                    "scope": "liuyao",
                    "ben": liuyao_mod.render_hexagram(ben, "本卦"),
                    "bian": liuyao_mod.render_hexagram(bian, "变卦"),
                    "moving_lines": ben.moving_lines,
                }
                ev = ben_jing + bian_jing
                # evidence 字段精简（仅 work_id/title/text/citation）
                ev_slim = [{"work_id": e["work_id"], "title": e["title"],
                            "text": e["text"], "citation": e["citation"]}
                           for e in ev[:6]]
                text = llm_reader.interpret(
                    f"本卦{ben.gua_name}(卦{ben.gua_number}) 变卦{bian.gua_name}(卦{bian.gua_number})",
                    ev_slim, req.question, calc_dict)
                llm_out = {"ok": True, "text": text,
                           "model": os.environ.get("LLM_MODEL", "llm_config.json")}
            except Exception as exc:
                llm_out["text"] = f"LLM 调用失败：{exc}"

    return {
        "ben": liuyao_mod.render_hexagram(ben, "本卦"),
        "bian": liuyao_mod.render_hexagram(bian, "变卦"),
        "ben_jing": ben_jing,
        "bian_jing": bian_jing,
        "llm": llm_out,
    }


@app.get("/api/huangli")
def api_huangli(date: str | None = None, affair: str | None = None,
                days: int = 1):
    """黄历择日（本地纯计算）。

    - date=YYYY-MM-DD：查单日宜忌坐标（建除/二十八宿/彭祖百忌）
    - affair=婚嫁&days=30：在 [date, date+days) 内找宜该事项的日子
    """
    dt: datetime
    if date:
        try:
            y, m, d = (int(x) for x in date.split("-"))
        except Exception:
            raise HTTPException(400, f"date 格式应为 YYYY-MM-DD，收到 {date}")
        if not (YEAR_LO <= y <= YEAR_HI):
            raise HTTPException(400, f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {y}")
        if not (1 <= m <= 12):
            raise HTTPException(400, f"month 须在 1-12，收到 {m}")
        if not (1 <= d <= 31):
            raise HTTPException(400, f"day 须在 1-31，收到 {d}")
        try:
            dt = datetime(y, m, d)
        except ValueError:
            raise HTTPException(400, f"非法日期 y={y} m={m} d={d}")
    else:
        dt = datetime.now()

    if affair:
        end = dt + timedelta(days=max(days, 1) - 1)
        good = huangli_mod.find_good_days(dt, end, affair)
        return {"affair": affair, "start": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
                "days": days, "good_days": good,
                "count": len(good)}

    q = huangli_mod.day_query(dt)
    return {"date": q["date"], "jianchu": q["jianchu"], "xiu": q["xiu"],
            "pengzu": q["pengzu"], "yi": q["yi"], "ji": q["ji"]}


# ---------------------------------------------------------------------------
# P4 五行起名（本地纯计算，复用 bazi_calc 五行缺行）
# ---------------------------------------------------------------------------

class QimingRequest(BaseModel):
    surname: str = Field(..., description="姓氏（单字）")
    year: int = Field(..., description="公历年")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    top_n: int = 20


@app.post("/api/qiming")
def api_qiming(req: QimingRequest):
    """五行起名：八字 → 五行缺行 → 候选字库筛选补缺字。

    纯计算：选字基于部首五行规则表（写死可核验），寓意坐标只给
    "五行-简明寓意"，不作吉凶断言，不生成"新命理文本"。
    """
    if not (YEAR_LO <= req.year <= YEAR_HI):
        raise HTTPException(400, f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {req.year}")
    if not req.surname or len(req.surname) != 1:
        raise HTTPException(400, "surname 须为单字姓氏")
    if not (1 <= req.month <= 12):
        raise HTTPException(400, f"month 须在 1-12，收到 {req.month}")
    if not (1 <= req.day <= 31):
        raise HTTPException(400, f"day 须在 1-31，收到 {req.day}")
    if not (0 <= req.hour <= 23):
        raise HTTPException(400, f"hour 须在 0-23，收到 {req.hour}")
    if req.gender not in ("男", "女"):
        raise HTTPException(400, f"gender 须为 男/女，收到 {req.gender}")
    try:
        result = qiming_mod.name_candidates(
            surname=req.surname, year=req.year, month=req.month,
            day=req.day, hour=req.hour, gender=req.gender,
            top_n=min(max(req.top_n, 1), 100))
    except Exception as exc:
        raise HTTPException(400, f"起名计算失败：{exc}")
    return result


@app.post("/api/taohua")
def api_taohua(req: BaziRequest):
    """八字桃花运（R111b，D-157b）：咸池/红鸾/天喜 纯坐标计算。

    复用 BaziRequest（含农历换算），排盘后按四柱查桃花星落宫。输出为
    坐标事实 + 写死说明文字（照 huangli 神煞层先例），不生成解读文本、
    不作吉凶断言；固定生日 → 固定输出，可命令复验。
    """
    req.validate_ranges()
    by, bm, bd = _resolve_birth(req)   # 农历在此换算成公历
    try:
        b = compute(by, bm, bd, req.hour, req.gender)
        t = taohua_mod.compute(b)
        dayun = taohua_mod.dayun_hits(b, by)
    except Exception as exc:
        raise HTTPException(422, f"排盘失败：{exc}") from exc
    return {
        "bazi": {"year": b.year, "month": b.month, "day": b.day,
                 "hour": b.hour, "day_master": b.day_master},
        "year_zhi": t.year_zhi,
        "peach_zhi": t.peach_zhi,
        "hit_pillars": t.hit_pillars,
        "hongluan": t.hongluan,
        "hongluan_pillar": t.hongluan_pillar,
        "tianxi": t.tianxi,
        "tianxi_pillar": t.tianxi_pillar,
        "strength": t.strength,
        "dayun_hits": dayun,
        "notes": t.notes,
        "render": t.render(),
    }


class TarotRequest(BaseModel):
    seed: int = Field(42, description="随机种子（固定 seed → 固定牌面，可复验）")
    n: int = Field(3, description="抽牌张数 1-10，默认 3（过去/现在/未来）")


class HehunRequest(BaseModel):
    """八字合婚（R121b，D-167b）：两人公历生日（同 BaziRequest 的 solar 约定）。"""
    a_year: int = Field(..., description="甲 公历年")
    a_month: int = Field(..., description="甲 月 1-12")
    a_day: int = Field(..., description="甲 日 1-31")
    a_hour: int = Field(..., description="甲 时 0-23")
    a_gender: str = "男"
    b_year: int = Field(..., description="乙 公历年")
    b_month: int = Field(..., description="乙 月 1-12")
    b_day: int = Field(..., description="乙 日 1-31")
    b_hour: int = Field(..., description="乙 时 0-23")
    b_gender: str = "女"


@app.post("/api/hehun")
def api_hehun(req: HehunRequest):
    """八字合婚（R121b，D-167b）：六冲/六合/日主五行/桃花支纯坐标比较。

    合规：比较规则为传统定式写死表（照 R111b/R112b 先例），输出为坐标
    事实 + 写死说明文字，不生成解读文本、不作吉凶断言；固定两人生日 →
    固定输出，可命令复验。
    """
    for tag, y, mo, d, h in (("甲", req.a_year, req.a_month, req.a_day, req.a_hour),
                             ("乙", req.b_year, req.b_month, req.b_day, req.b_hour)):
        if not (YEAR_LO <= y <= YEAR_HI):
            raise HTTPException(400, f"{tag} 年份须在 {YEAR_LO}-{YEAR_HI}，收到 {y}")
        if not (1 <= mo <= 12):
            raise HTTPException(400, f"{tag} month 须在 1-12，收到 {mo}")
        if not (1 <= d <= 31):
            raise HTTPException(400, f"{tag} day 须在 1-31，收到 {d}")
        if not (0 <= h <= 23):
            raise HTTPException(400, f"{tag} hour 须在 0-23，收到 {h}")
    try:
        ba = compute(req.a_year, req.a_month, req.a_day, req.a_hour, req.a_gender)
        bb = compute(req.b_year, req.b_month, req.b_day, req.b_hour, req.b_gender)
        h = hehun_mod.compute(ba, bb)
    except Exception as exc:
        raise HTTPException(422, f"排盘失败：{exc}") from exc
    return {
        "a_bazi": {"year": ba.year, "day": ba.day, "day_master": ba.day_master},
        "b_bazi": {"year": bb.year, "day": bb.day, "day_master": bb.day_master},
        "year_zhi_a": h.year_zhi_a, "year_zhi_b": h.year_zhi_b,
        "clash": h.clash, "combine": h.combine,
        "day_wx_a": h.day_wx_a, "day_wx_b": h.day_wx_b,
        "day_wx_sheng": h.day_wx_sheng,
        "peach_a": h.peach_a, "peach_b": h.peach_b, "peach_same": h.peach_same,
        "notes": h.notes,
        "render": h.render(),
    }


@app.post("/api/tarot")
def api_tarot(req: TarotRequest):
    """塔罗牌占卜（R112b，D-158b）：78 张牌静态表 + seed 确定性抽牌。

    合规：牌意关键词为功能内静态数据（公版象征坐标），不入语料库、不声称
    古籍出处、不生成解读文本、不作吉凶断言。固定 seed → 固定牌面，可复验。
    """
    draws = tarot_mod.draw(seed=req.seed, n=req.n)
    return {
        "seed": req.seed,
        "n": len(draws),
        "draws": [
            {"index": d.index, "name": d.name, "upright": d.upright,
             "upright_kw": d.upright_kw, "reversed_kw": d.reversed_kw,
             "meaning": d.meaning, "position": d.position,
             "render": d.render()}
            for d in draws
        ],
    }


if __name__ == "__main__":
    import sys as _sys

    if "--selftest" in _sys.argv:
        # Web-layer standing self-test (R49b): TestClient against the live
        # endpoints, asserting response shapes so a silent endpoint break
        # (e.g. R48b's missing `import json`) is caught by a reproducible
        # command, not by an ad-hoc smoke. Run:
        #   cd web && PYTHONPATH=src:. python -m app --selftest
        from fastapi.testclient import TestClient

        client = TestClient(app)
        ok = []

        def check(name, resp, pred):
            assert resp.status_code == 200, (name, resp.status_code, resp.text[:200])
            body = resp.json()
            assert pred(body), (name, body)
            ok.append(name)

        check("search", client.get("/api/search", params={"q": "潛龍勿用"}), lambda j: j.get("hits"))
        check("addr", client.get("/api/addr", params={"scheme": "zhouyi", "gua": 1}), lambda j: j.get("hits"))
        # R110b（D-156b）：zhouyi 之外五类 scheme 走 at_scheme 通用路径，此前无
        # standing 断言——若该路径静默失效，13 闸门与五层自测都看不见。固定参数
        # 实测可稳定复现（bcv Proverbs 12:12 / yilin 中孚 61 / booksec addr1=10 /
        # play THE SONNETS 1 / euclid Book 1），断言 200 + hits 非空 + scheme 回显。
        for _sch, _params in (
            ("addr.bcv", {"scheme": "bcv", "addr_name": "Proverbs", "addr1": 12, "addr2": "12"}),
            ("addr.yilin", {"scheme": "yilin", "addr1": 61}),
            ("addr.booksec", {"scheme": "booksec", "addr1": 10}),
            ("addr.play", {"scheme": "play", "addr_name": "THE SONNETS", "addr1": 1}),
            ("addr.euclid", {"scheme": "euclid", "addr_name": "Book 1", "addr1": 1}),
        ):
            check(_sch, client.get("/api/addr", params=_params),
                  lambda j, s=_params["scheme"]: j.get("hits") and j.get("scheme") == s)
        check("compare", client.get("/api/compare", params={"gua": 28, "yao": "九二"}), lambda j: "findings" in j)
        check("works", client.get("/api/works"), lambda j: j.get("works") and all("source" in w for w in j["works"]))
        check("stats", client.get("/api/stats"), lambda j: j.get("stats") and j.get("layers"))
        check("bookstudy.structure", client.get("/api/bookstudy/structure", params={"work_id": "KR1a0001"}),
              lambda j: j.get("sections") and j.get("scheme") == "zhouyi")
        check("bookstudy.chapter", client.get("/api/bookstudy/chapter",
              params={"work_id": "KR1a0001", "scheme": "zhouyi", "addr1": 1}),
              lambda j: j.get("units") and all(u.get("citation") for u in j["units"]))
        check("bookstudy.summary", client.get("/api/bookstudy/summary", params={"work_id": "KR1a0001"}),
              lambda j: j.get("n_units") and j.get("layers"))
        check("compare_works", client.get("/api/compare_works",
              params={"work_a": "KR5c0057", "work_b": "KR5c0126", "q": "無爲"}),
              lambda j: j.get("works") and len(j["works"]) == 2)
        check("concept", client.get("/api/concept", params={"q": "無爲"}), lambda j: j.get("census"))
        check("threads.list", client.get("/api/threads"), lambda j: "threads" in j)

        # 数术主 tab 端点（R53b）：bazi/liuyao/huangli/qiming 确定性 standing 覆盖。
        # 实测 seed=42 起卦结果固定（本卦 22 賁），固定输入可复验；全部纯本地计算。
        # bazi 端点会把查询写入真实 history.db（D-039 用户授权）——自测须清理
        # 本次新增记录（L-22 教训：写端点自测不得污染真实库，threads 同款）。
        from guji import history as history_db
        rows_before = history_db.list_records(limit=1)
        max_id_before = rows_before[0]["id"] if rows_before else 0
        # R68b：P2 子平书集合（bazi_lookup.MINGLI_WORKS 中的 9 部本地入库书）
        _ZI_PING_WORKS = {"ditiansui", "lantai-miaoxuan", "mingli-tanyuan",
                          "mingli-yueyan", "qiongtongbaojian", "sanming-tonghui",
                          "wuxing-dayi", "wuxing-jingji", "ziping-zhenquan"}
        check("bazi", client.post("/api/bazi", json={"year": 1990, "month": 1, "day": 1,
              "hour": 12, "gender": "男"}),
              lambda j: (j.get("paipan") and j.get("calc")
                         # R68b 归因修正（R69b，D-115b）：web /api/bazi 的
                         # evidence 来自 retrieve_fast（FTS 路径，app.py:225），
                         # 此处断言 FTS 命中非空 + 含 P2 子平书——抓 FTS 检索
                         # 静默失效，与语义路径无关（语义路径见下方 semantic check）
                         and j.get("evidence")
                         and any(e.get("work_id") in _ZI_PING_WORKS
                                 for e in j.get("evidence", []))))
        # R119b（D-165b）：bazi lunar 农历换算路径 standing 覆盖——bazi check
        # 只测 solar，calendar_type=lunar 走 _resolve_birth→lunar_to_solar
        # 零断言（若换算/闰月/范围校验静默失效则不可见）。固定农历生日
        # 1990-05-15 男 → 200 + 四柱非空 + 日主癸（lunar_to_solar=1990-06-07，
        # 与 solar 同日期八字一致可交叉验证）；lunar_leap 亦断言非 4xx。
        check("bazi.lunar", client.post("/api/bazi", json={"calendar_type": "lunar",
              "lunar_year": 1990, "lunar_month": 5, "lunar_day": 15,
              "lunar_leap": False, "hour": 10, "gender": "男",
              "year": 1990, "month": 5, "day": 15}),
              lambda j: (j.get("paipan") and j["paipan"].get("render")
                         and j["paipan"]["render"].startswith("庚午年 壬午月 癸卯日")))
        check("bazi.lunar_leap", client.post("/api/bazi", json={"calendar_type": "lunar",
              "lunar_year": 1990, "lunar_month": 5, "lunar_day": 15,
              "lunar_leap": True, "hour": 10, "gender": "女",
              "year": 1990, "month": 5, "day": 15}),
              lambda j: j.get("paipan") and j["paipan"].get("render"))
        for rec in history_db.list_records(limit=5):
            if rec["id"] > max_id_before:
                history_db.delete_record(rec["id"])
        # R69b（D-115b）：retrieve_semantic（bge 语义路径）standing 覆盖——
        # 该路径只在 CLI（scripts/ask_bazi.py）调用，web /api/bazi 不经过它，
        # 13 闸门与五层自测此前均不覆盖（R67b 重建 bge_mingli 缓存后受益者
        # 仍无自测）。固定 Bazi 输入（与 bazi check 同款）→ 语义命中非空 +
        # 含 P2 子平书（实测命中 ziping-zhenquan 等），抓语义路径静默失效。
        from guji.bazi import compute as _bazi_compute
        from guji.bazi_lookup import retrieve_semantic as _retrieve_semantic
        sem = _retrieve_semantic(_bazi_compute(1990, 1, 1, 12, "男"), top_k=8)
        assert sem and any(e["work_id"] in _ZI_PING_WORKS for e in sem), "semantic retrieval must hit P2 books"
        ok.append("bazi.semantic")
        check("liuyao", client.post("/api/liuyao", json={"method": "coins", "seed": 42}),
              lambda j: j.get("ben") and j["ben"].get("gua_number") == 22)
        # R118b（D-164b）：liuyao time（梅花易数时间起卦）与 huangli affair
        # （择日查找 find_good_days）两条已接线能力路径此前零 standing 断言——
        # 实测发现 affair 分支因 timedelta 未导入而 NameError 静默损坏（已修，
        # app.py:30）。固定参数确定性可复验：time 起卦 2026-08-16 10:00 → 萃45；
        # affair=婚嫁 2026-08-17 起 30 天 → good_days 非空。
        check("liuyao.time", client.post("/api/liuyao", json={"method": "time",
              "year": 2026, "month": 8, "day": 16, "hour": 10}),
              lambda j: j.get("ben") and j["ben"].get("gua_number") == 45)
        check("huangli.affair", client.get("/api/huangli", params={"affair": "婚嫁",
              "date": "2026-08-17", "days": 30}),
              lambda j: j.get("count", 0) > 0 and bool(j.get("good_days")))
        check("huangli", client.get("/api/huangli", params={"date": "2026-08-17", "days": 1}),
              lambda j: j.get("date") and j.get("jianchu"))
        check("qiming", client.post("/api/qiming", json={"surname": "李", "year": 1990,
              "month": 1, "day": 1, "hour": 12, "gender": "男", "top_n": 5}),
              lambda j: j.get("candidates"))
        # R111b（D-157b）：桃花运纯坐标计算 standing 覆盖——固定生日→固定输出，
        # 断言咸池/红鸾/天喜字段齐全且 render 含坐标事实（抓端点静默失效）。
        check("taohua", client.post("/api/taohua", json={"year": 1990, "month": 5,
              "day": 15, "hour": 10, "gender": "男"}),
              lambda j: (j.get("peach_zhi") and j.get("hongluan")
                         and j.get("tianxi") and j.get("strength")
                         and j.get("render") and j["bazi"]["year"] == "庚午"
                         and "dayun_hits" in j))
        # R113b（D-159b）：大运桃花应期 standing 覆盖——女命阳年逆排，大运第 2 运
        # 己卯（2003 起）地支卯 == 桃花支卯 → dayun_hits 非空且含己卯（实测稳定）。
        check("taohua.dayun", client.post("/api/taohua", json={"year": 1990, "month": 5,
              "day": 15, "hour": 10, "gender": "女"}),
              lambda j: (isinstance(j.get("dayun_hits"), list)
                         and any(d.get("pillar") == "己卯" and d.get("year_start") == 2003
                                 for d in j.get("dayun_hits", []))))
        # R112b（D-158b）：塔罗牌 seed 确定性 standing 覆盖——固定 seed → 固定
        # 牌面（实测 seed=42 抽 3 张含 节制/皇后/权杖国王），断言 n=3 + 每张牌
        # 有名称/正逆位/关键词（抓端点静默失效）。
        check("tarot", client.post("/api/tarot", json={"seed": 42, "n": 3}),
              lambda j: (j.get("n") == 3 and len(j.get("draws")) == 3
                         and all(d.get("name") and d.get("upright") is not None
                                 and d.get("render") for d in j["draws"])
                         and j["draws"][0]["name"] == "节制"))
        # R114b（D-160b）：牌阵位置含义 standing 覆盖——seed=42 n=3 位置名恰为
        # 过去/现在/未来（实测稳定），n=5 为五张牌阵（抓位置表静默失效）。
        check("tarot.spread", client.post("/api/tarot", json={"seed": 42, "n": 3}),
              lambda j: [d.get("position") for d in j.get("draws", [])]
                        == ["过去", "现在", "未来"])
        check("tarot.spread5", client.post("/api/tarot", json={"seed": 42, "n": 5}),
              lambda j: [d.get("position") for d in j.get("draws", [])]
                        == ["现状", "助力", "阻碍", "过去", "结果"])
        # R121b（D-167b）：八字合婚纯坐标 standing 覆盖——固定两人生日 → 固定
        # 输出（实测 1990-05-15 男 vs 1992-08-20 女 → 无冲合/日主相生/桃花不同），
        # 断言字段齐全 + 确定性（抓端点静默失效）。
        check("hehun", client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
              "a_day": 15, "a_hour": 10, "a_gender": "男",
              "b_year": 1992, "b_month": 8, "b_day": 20, "b_hour": 14,
              "b_gender": "女"}),
              lambda j: (j.get("clash") is False and j.get("combine") is False
                         and j.get("day_wx_sheng") is True
                         and j.get("peach_same") is False
                         and j.get("render") and j.get("notes")))

        # 核心研究/历史/线程/健康端点（R54b）：全部确定性、无写副作用
        # （ask 不落库不缓存、history/threads 只读）。external/news 依赖
        # 代理与网络，明确不进 standing 自测（D-100b）。
        check("research", client.get("/api/research", params={"q": "潛龍勿用", "max_addresses": 2}),
              lambda j: j.get("evidence") and j.get("steps"))
        check("ask", client.post("/api/ask", json={"q": "潛龍勿用", "max_addresses": 2}),
              lambda j: j.get("evidence_citations"))
        # R115b（D-161b）：ask 的 llm 字段结构 standing 覆盖——llm 为 None
        # （未配置 LLM）或 dict 且含 text+model 键（配置时须标注模型来源）。
        # 不依赖 LLM 是否配置，断言两种合法形态（抓字段形状静默漂移）。
        check("ask.llm.shape", client.post("/api/ask", json={"q": "潛龍勿用",
              "max_addresses": 2, "use_llm": True}),
              lambda j: j.get("llm") is None
                        or (isinstance(j.get("llm"), dict)
                            and isinstance(j["llm"].get("text"), str)
                            and isinstance(j["llm"].get("model"), str)))
        check("history", client.get("/api/history", params={"limit": 3}),
              lambda j: "records" in j and isinstance(j["records"], list))
        check("history.detail", client.get(f"/api/history/{history_db.count()}"),
              lambda j: j is None or "paipan" in j)  # 可能无该 id，但必须结构正确
        check("threads.detail", client.get("/api/threads/1"),
              lambda j: "claims" in j and "turns" in j)
        check("health", client.get("/api/health"), lambda j: j.get("ok") is True)
        # 首页 `/`（R61b）：单页前端入口，返回 HTML 非 JSON——不走 check()
        # 闭包（它断言 resp.json()），单独断言状态码 + content-type + 关键标记。
        home = client.get("/")
        assert home.status_code == 200, ("home", home.status_code, home.text[:200])
        assert "text/html" in (home.headers.get("content-type") or ""), "home must be HTML"
        assert "<html" in home.text.lower(), "home must contain <html>"
        ok.append("home")

        # threads POST: write a bound claim with a REAL quote -> readback ->
        # cleanup (R34b lesson: never leave test rows in the live store)
        from guji.knowledge import KnowledgeBase
        from guji.variants import fold, segment_cjk

        post = client.post("/api/threads", json={
            "kind": "summary",
            "claim": "web selftest: 無爲在老子中的可核验引文",
            "method": "app-selftest", "thread_id": 1,
            "evidence": [{"work_id": "KR5c0057", "file": "KR5c0057_043.txt",
                          "quote": "第四十三章 天下之至柔",
                          "page_anchor": "KR5c0057_tls_043-1a"}]})
        assert post.status_code == 200, post.text
        did = post.json()["derived_id"]
        assert post.json()["thread_id"] == 1
        # readback
        detail = client.get("/api/threads/1").json()
        assert any(c["id"] == did and "無爲在老子中的可核验引文" in c["claim"]
                   for c in detail["claims"]), "thread readback must contain the bound claim"
        # cleanup
        kb = KnowledgeBase(KNOWLEDGE_DB)
        try:
            row = kb.db.execute("SELECT claim FROM derived WHERE id=?", (did,)).fetchone()
            if row is not None:
                seg = segment_cjk(fold(row["claim"]))
                kb.db.execute("INSERT INTO derived_fts(derived_fts,rowid,seg) "
                              "VALUES('delete',?,?)", (did, seg))
                kb.db.execute("DELETE FROM evidence WHERE derived_id=?", (did,))
                kb.db.execute("DELETE FROM derived WHERE id=?", (did,))
                kb.db.commit()
        finally:
            kb.close()
        ok.append("threads.post+readback+cleanup")
        print(f"web self-test PASS ({len(ok)} checks): {', '.join(ok)}")
    else:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8000)
