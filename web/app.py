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
import sqlite3
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
from fastapi.staticfiles import StaticFiles  # noqa: E402
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
# R155b（D-201b）：静态目录挂载——/static 指向 index.html 所在目录
# （开发期 ROOT/web/static；frozen 期 _MEIPASS/web/static，与 INDEX 同源），
# 供 index.html 引用本地 vendor/animotion CSS（动画样式离线可用）。
app.mount("/static", StaticFiles(directory=os.path.dirname(INDEX)), name="static")
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
                           "model": llm_reader.configured_model()}
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
        except (ValueError, sqlite3.IntegrityError) as exc:
            # R159b（D-205b）：非法 kind 触发 knowledge.py INSERT 的
            # sqlite3.IntegrityError（DB CHECK 约束），此前只捕获 ValueError
            # → 500 崩溃；扩展捕获转 400（与其余端点"非法参数→400"纪律一致）。
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
                           "model": llm_reader.configured_model()}
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
        # R138b（D-184b）：大运冲合应期（复用 calc_life 两人大运表逐运比较）
        dayun = hehun_mod.dayun_relation(ba, req.a_year, bb, req.b_year)
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
        "dayun_hits": dayun,
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
        # R128b（D-174b）：search 的 layer/work 过滤参数分支 standing 覆盖——
        # search check 只测裸 q，layer/work 过滤 SQL 零断言（若过滤拼接回归、
        # 返回未过滤全集则不可见，与 R118b/R119b/R124b/R126b 同族）。固定输入
        # 实测：layer=經 → hits=10；work=KR1a0001 → hits=2（过滤收窄生效）。
        check("search.layer", client.get("/api/search", params={"q": "潛龍勿用",
              "layer": "經"}),
              lambda j: (j.get("hits") and all(h.get("layer") == "經"
                                               for h in j["hits"])))
        check("search.work", client.get("/api/search", params={"q": "潛龍勿用",
              "work": "KR1a0001"}),
              lambda j: (j.get("hits") and all(h.get("work_id") == "KR1a0001"
                                               for h in j["hits"])))
        check("addr", client.get("/api/addr", params={"scheme": "zhouyi", "gua": 1}), lambda j: j.get("hits"))
        # R137b（D-183b）：addr zhouyi 的 yao 爻位过滤分支 standing 覆盖——
        # addr check 只测 gua=1 无 yao 参数，yao（addr2 爻位过滤）分支零断言
        # （若过滤被忽略、返回全爻则不可见，与 R110b addr 五类 scheme 同族——
        # R110b 补 scheme 维度、本轮补 yao 维度）。实测 gua=1&yao=初九 → 10
        # hits 全为初九；yao=用九 → 20 hits（过滤生效可复验）。
        check("addr.zhouyi.yao", client.get("/api/addr", params={"scheme": "zhouyi",
              "gua": 1, "yao": "初九"}),
              lambda j: (j.get("hits") and all(h.get("yao") == "初九"
                                               for h in j["hits"])))
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
        # R130b（D-176b）：bookstudy.chapter 的 NULL-scheme 文件节分支 standing
        # 覆盖——现有 check 只测 zhouyi（KR1a0001），无 scheme 文件节（老子）读取
        # 零断言（若 NULL-scheme 文件节回归则不可见，与 R118b/R119b/R124b/R126b/
        # R128b 同族）。实测 work_id=老子&scheme=booksec&addr1=1 → 200 + error
        # 键（NULL-scheme 文件节分支可用）。
        check("bookstudy.chapter.nullscheme", client.get("/api/bookstudy/chapter",
              params={"work_id": "老子", "scheme": "booksec", "addr1": 1}),
              lambda j: j.get("error") is not None)
        check("bookstudy.summary", client.get("/api/bookstudy/summary", params={"work_id": "KR1a0001"}),
              lambda j: j.get("n_units") and j.get("layers"))
        # R134b（D-180b）：bookstudy.summary 缺失作品拒绝分支 standing 覆盖——
        # summary check 只测命中路径（KR1a0001），缺失作品（NO_SUCH_WORK）拒绝
        # 分支零断言（若缺失校验回归为 500 则不可见，与 R130b bookstudy.chapter.
        # nullscheme 同族）。实测 work_id=NO_SUCH_WORK → 200 + error 键。
        check("bookstudy.summary.missing", client.get("/api/bookstudy/summary",
              params={"work_id": "NO_SUCH_WORK"}),
              lambda j: j.get("error") is not None)
        check("compare_works", client.get("/api/compare_works",
              params={"work_a": "KR5c0057", "work_b": "KR5c0126", "q": "無爲"}),
              lambda j: j.get("works") and len(j["works"]) == 2)
        # R130b（D-176b）：compare_works 无命中拒绝分支（G7）standing 覆盖——
        # 现有 check 只测有命中路径，G7 拒绝分支（error 键）零断言（若拒绝逻辑
        # 回归则不可见，与 R118b/R119b/R124b/R126b/R128b 同族）。实测无命中 q
        # → 200 + error="「電話飛機電腦」在两书均无命中"（分支可用）。
        check("compare_works.refuse", client.get("/api/compare_works",
              params={"work_a": "KR5c0057", "work_b": "KR5c0126", "q": "電話飛機電腦"}),
              lambda j: j.get("error") is not None)
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
        # R126b（D-172b）：bazi scope=range / scope=life 两分支 standing 覆盖——
        # bazi check 只测默认 scope=day，calc_range/calc_life 零断言（若大运
        # 干支/范围校验回归则不可见，与 R118b/R119b/R124b 同族）。固定输入：
        # range 2026-01-01~05 → days=5；life → dayun 长度 8（实测稳定）。
        check("bazi.range", client.post("/api/bazi", json={"year": 1990, "month": 5,
              "day": 15, "hour": 10, "gender": "男", "scope": "range",
              "range_start": "2026-01-01", "range_end": "2026-01-05"}),
              lambda j: (j.get("calc", {}).get("scope") == "range"
                         and len(j.get("calc", {}).get("days", [])) == 5))
        check("bazi.life", client.post("/api/bazi", json={"year": 1990, "month": 5,
              "day": 15, "hour": 10, "gender": "男", "scope": "life"}),
              lambda j: (j.get("calc", {}).get("scope") == "life"
                         and len(j.get("calc", {}).get("dayun", [])) == 8))
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
        # R138b（D-184b）：大运冲合应期 standing 覆盖——固定两人生日 → 8 运
        # 全"合"（实测 壬午×丁未 1997 … 己丑×庚子 2067），断言 dayun_hits
        # 非空且首运为合（抓 calc_life 复用/冲合比较静默失效）。
        check("hehun.dayun", client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
              "a_day": 15, "a_hour": 10, "a_gender": "男",
              "b_year": 1992, "b_month": 8, "b_day": 20, "b_hour": 14,
              "b_gender": "女"}),
              lambda j: (isinstance(j.get("dayun_hits"), list)
                         and len(j.get("dayun_hits", [])) == 8
                         and j.get("dayun_hits", [])[0]["relation"] == "合"
                         and j["dayun_hits"][0]["year_start"] == 1997))
        # R124b（D-170b）：错误处理路径 standing 覆盖——check() 闭包只断言合法
        # 输入的 200，非法输入（应 400）此前零断言：若某端点把参数校验改回未捕获
        # 异常（400→500），selftest 全绿看不见。以下独立断言 400（不走闭包），
        # 实测六用例当前均正确返回 400（tarot n=0 钳制为 200 属设计行为）。
        def _expect_400(name, resp):
            assert resp.status_code == 400, (name, resp.status_code, resp.text[:200])
            ok.append(name)

        # R163b（D-209b）：422 排盘失败分支断言辅助——400 参数校验断言不
        # 构成 422 计算失败路径的覆盖（compute 抛异常→422，如 1990-02-30
        # 不存在），独立断言状态码。
        def _expect_422(name, resp):
            assert resp.status_code == 422, (name, resp.status_code, resp.text[:200])
            ok.append(name)

        _expect_400("err.addr.scheme",
                    client.get("/api/addr", params={"scheme": "nonsense", "gua": 1}))
        _expect_400("err.liuyao.method",
                    client.post("/api/liuyao", json={"method": "dice", "seed": 42}))
        # R141b（D-187b）：liuyao time 起卦 year/month/missing 三条 400 校验
        # 分支 standing 覆盖——err.liuyao.method 只测非法 method，time 起卦
        # 的 year（line 772-773）、month（line 774-775）、missing（line 770-771）
        # 三条校验零断言（若校验回归为 500 或被移除则不可见，与 R139b
        # err.bazi.calendar/scope/gender 同族——同端点不同校验维度）。
        # 实测 year=1800→400、month=13→400、missing y/m/d→400——补断言零风险。
        _expect_400("err.liuyao.time.year",
                    client.post("/api/liuyao", json={"method": "time",
                                                     "year": 1800, "month": 5,
                                                     "day": 15, "hour": 10}))
        _expect_400("err.liuyao.time.month",
                    client.post("/api/liuyao", json={"method": "time",
                                                     "year": 1990, "month": 13,
                                                     "day": 15, "hour": 10}))
        _expect_400("err.liuyao.time.missing",
                    client.post("/api/liuyao", json={"method": "time", "hour": 10}))
        # R149b（D-195b）：liuyao time 起卦 day/hour 两条 400 校验分支 standing
        # 覆盖——err.liuyao.time.year/month/missing（R141b）已覆盖三条，但
        # day（line 776-777）、hour（line 778-779）两条零断言（若校验回归
        # 为 500 或被移除则不可见，与 R141b err.liuyao.time.year 同族——
        # 同端点不同校验维度）。实测 day=32→400、hour=24→400——补断言零风险。
        _expect_400("err.liuyao.time.day",
                    client.post("/api/liuyao", json={"method": "time",
                                                     "year": 1990, "month": 5,
                                                     "day": 32, "hour": 10}))
        _expect_400("err.liuyao.time.hour",
                    client.post("/api/liuyao", json={"method": "time",
                                                     "year": 1990, "month": 5,
                                                     "day": 15, "hour": 24}))
        # R157b（D-203b）：liuyao time 起卦公历转农历失败（solar_to_lunar
        # ValueError 捕获分支，line 789）400 校验 standing 覆盖——
        # err.liuyao.time.year/month/missing（R141b）与 day/hour（R149b）
        # 只覆盖输入形状校验，公历转农历运行时换算失败（如公历日期早于
        # 农历表起点 1900-01-31）由 lunar.py 抛出、经 line 789 捕获转
        # 400，这条路径零断言（若换算失败回归为 500、或被移除导致非法
        # 公历日期进入起卦计算则不可见，与 R141b err.liuyao.time.missing
        # 同族——同端点不同校验维度）。实测 year=1900-01-01 → 400 "公历
        # 转农历失败：1900-01-01 早于农历表起点 1900-01-31"——补断言
        # 零风险。
        _expect_400("err.liuyao.time.convert_fail",
                    client.post("/api/liuyao", json={"method": "time",
                                                     "year": 1900, "month": 1,
                                                     "day": 1, "hour": 10}))
        _expect_400("err.hehun.year",
                    client.post("/api/hehun", json={"a_year": 1800, "a_month": 5,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        # R150b（D-196b）：hehun 乙侧 b_year/b_month/b_day 三条 400 校验分支
        # standing 覆盖——err.hehun.year（R124b）只测甲侧 a_year，乙侧
        # b_year（line 963-965）、b_month、b_day 三条校验分支零断言（甲侧
        # 先抛 400 时乙侧代码路径从未执行，若乙侧校验回归为 500 或被移除
        # 则不可见，与 R124b err.hehun.year 同族——同端点不同校验维度）。
        # 实测 b_year=1800/b_month=13/b_day=0 均正确返回 400 + detail——
        # 补断言零风险。
        _expect_400("err.hehun.b_year",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1800, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        _expect_400("err.hehun.b_month",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 13,
                                                    "b_day": 20, "b_hour": 14}))
        _expect_400("err.hehun.b_day",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 0, "b_hour": 14}))
        # R154b（D-200b）：hehun 甲侧 a_month/a_day/a_hour + 乙侧 b_hour
        # 四条 400 校验分支 standing 覆盖——err.hehun.year（R124b）只测
        # 甲 a_year，err.hehun.b_year/b_month/b_day（R150b）只测乙侧
        # year/month/day，甲侧 a_month（line 983）、a_day（line 985）、
        # a_hour（line 987）与乙侧 b_hour（line 987）四条校验分支零断言
        # （year 断言不构成 month/day/hour 的覆盖，若这些校验回归为 500
        # 或被移除则不可见，与 R124b/R150b err.hehun.* 同族——同端点不同
        # 校验维度）。实测 a_month=13/a_day=0/a_hour=24/b_hour=24 均正确
        # 返回 400 + detail——补断言零风险。
        _expect_400("err.hehun.a_month",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 13,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        _expect_400("err.hehun.a_day",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 0, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        _expect_400("err.hehun.a_hour",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 15, "a_hour": 24,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        _expect_400("err.hehun.b_hour",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 5,
                                                    "a_day": 15, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 24}))
        # R164b（D-210b）：hehun 端点 422 排盘失败分支 standing 覆盖——
        # err.hehun.*（R124b/R150b/R154b）全为 400 参数校验断言，422 是
        # compute 抛异常路径（合法参数但组合非法，如 a 侧 1990-02-30 不
        # 存在，line 1004 "排盘失败：{exc}"）零断言（若排盘异常回归为
        # 500、或被移除导致非法组合静默排盘则不可见，与 R163b
        # err.bazi.paipan_fail 同族——不同端点同状态码维度）。实测
        # a 侧 year=1990/month=2/day=30 → 422 "排盘失败：day 30 must be
        # in range 1..28 for month 2 in year 1990"——补断言零风险。
        _expect_422("err.hehun.paipan_fail",
                    client.post("/api/hehun", json={"a_year": 1990, "a_month": 2,
                                                    "a_day": 30, "a_hour": 10,
                                                    "b_year": 1992, "b_month": 8,
                                                    "b_day": 20, "b_hour": 14}))
        # R142b（D-188b）：huangli 端点 date 格式/year 范围/非法日期三条 400
        # 校验分支 standing 覆盖——huangli check（行 1201）只测合法 date，
        # date 格式校验（line 843）、year 范围校验（line 851）、非法日期
        # 校验（line 859）三条 400 校验分支零断言（若校验回归为 500、或
        # 被移除导致非法日期进入黄历计算则不可见，与 R139b/R140b/R141b
        # 同族——同端点不同校验维度）。实测 date=garbage/1800-01-01/
        # 2026-02-30 均正确返回 400 + detail——补断言零风险。
        _expect_400("err.huangli.date",
                    client.get("/api/huangli", params={"date": "garbage"}))
        _expect_400("err.huangli.year",
                    client.get("/api/huangli", params={"date": "1800-01-01"}))
        _expect_400("err.huangli.illegal",
                    client.get("/api/huangli", params={"date": "2026-02-30"}))
        # R162b（D-208b）：huangli 端点 month/day 两条 400 校验分支 standing
        # 覆盖——err.huangli.date/year/illegal（R142b）已覆盖 date 格式、
        # year 范围、非法日期三条，但 month（line 853 "month 须在 1-12"）、
        # day（line 855 "day 须在 1-31"）两条零断言（date 格式/年份/非法
        # 日期断言不构成 month/day 的覆盖——如 date=2026-13-01 走 month
        # 校验、date=2026-01-32 走 day 校验，与 R142b 已覆盖的 date=
        # garbage/1800-01-01/2026-02-30 不同分支；若这些校验回归为 500
        # 或被移除则不可见，与 R142b err.huangli.date 同族——同端点不同
        # 校验维度）。实测 date=2026-13-01/2026-01-32 均正确返回 400 +
        # detail——补断言零风险。
        _expect_400("err.huangli.month",
                    client.get("/api/huangli", params={"date": "2026-13-01"}))
        _expect_400("err.huangli.day",
                    client.get("/api/huangli", params={"date": "2026-01-32"}))
        _expect_400("err.bazi.year",
                    client.post("/api/bazi", json={"year": 1800, "month": 5,
                                                   "day": 15, "hour": 10}))
        # R161b（D-207b）：bazi 端点 month/day/hour 三条 400 校验分支
        # standing 覆盖——err.bazi.year（R139b）只测年份范围，month
        # （line 139: "month 需在 1-12"）、day（line 141: "day 需在
        # 1-31"）、hour（line 143: "hour 需在 0-23"）三条校验零断言
        # （若校验回归为 500 或被移除则不可见，与 R139b err.bazi.year
        # 同族——同端点不同校验维度）。实测 month=13/day=32/hour=25
        # 均正确返回 400 + detail——补断言零风险。
        _expect_400("err.bazi.month",
                    client.post("/api/bazi", json={"year": 1990, "month": 13,
                                                   "day": 15, "hour": 10}))
        _expect_400("err.bazi.day",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 32, "hour": 10}))
        _expect_400("err.bazi.hour",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 25}))
        # R163b（D-209b）：bazi 端点 422 排盘失败分支 standing 覆盖——
        # err.bazi.*（R139b-R162b）全为 400 参数校验断言，422 是 compute
        # 抛异常路径（合法参数但组合非法，如 1990-02-30 不存在，line 215
        # "排盘失败：{exc}"）零断言（若排盘异常回归为 500、或被移除导致
        # 非法组合静默排盘则不可见，与 R124b err.* 同族但不同状态码维度）。
        # 实测 year=1990/month=2/day=30 → 422 "排盘失败：day 30 must be
        # in range 1..28 for month 2 in year 1990"——补断言零风险。
        _expect_422("err.bazi.paipan_fail",
                    client.post("/api/bazi", json={"year": 1990, "month": 2,
                                                   "day": 30, "hour": 10}))
        # R139b（D-185b）：bazi 端点 calendar_type/scope/gender 三条 400 校验
        # 分支 standing 覆盖——err.bazi.year 只测年份范围，calendar_type
        # （非 solar/lunar）、scope（非 day/range/life）、gender（非 男/女）
        # 三条校验零断言（若校验回归为 500 或被移除则不可见，与 R124b
        # err.bazi.year 同族——同端点不同校验维度）。实测三条均正确返回
        # 400 + detail（calendar_type=garbage/scope=garbage/gender=中）。
        _expect_400("err.bazi.calendar",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "garbage"}))
        _expect_400("err.bazi.scope",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "scope": "garbage"}))
        _expect_400("err.bazi.gender",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "gender": "中"}))
        # R150b（D-196b）：bazi 端点 lunar 三条 400 校验分支 standing 覆盖
        # ——err.bazi.calendar/scope/gender（R139b）已覆盖三条，但 lunar
        # 缺失（line 122-123）、lunar_month 超范围（line 124-125）、
        # lunar_day 超范围（line 126-127）三条零断言（若校验回归为 500
        # 或被移除则不可见，与 R139b err.bazi.calendar 同族——同端点不
        # 同校验维度）。实测 lunar 缺失/lunar_month=13/lunar_day=31 均正确
        # 返回 400 + detail——补断言零风险。
        _expect_400("err.bazi.lunar_missing",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "lunar"}))
        _expect_400("err.bazi.lunar_month",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "lunar",
                                                   "lunar_year": 1990,
                                                   "lunar_month": 13,
                                                   "lunar_day": 15}))
        _expect_400("err.bazi.lunar_day",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "lunar",
                                                   "lunar_year": 1990,
                                                   "lunar_month": 5,
                                                   "lunar_day": 31}))
        # R156b（D-202b）：bazi lunar_year 超范围（lunar_to_solar ValueError
        # 捕获分支，line 172）400 校验 standing 覆盖——err.bazi.lunar_
        # missing/month/day（R150b）只覆盖 lunar 输入形状，lunar_year 超
        # 范围由 lunar_to_solar 内部校验（lunar.py:131）抛出、经 line 172
        # 捕获转 400，这条路径零断言（若 lunar_year 校验回归为 500 或被
        # 移除导致非法农历年进入换算则不可见，与 R150b err.bazi.lunar_
        # month 同族——同端点不同校验维度）。实测 lunar_year=1800 → 400
        # "农历换算失败：农历年份需在 1900-2100（收到 1800）"——补断言
        # 零风险。
        _expect_400("err.bazi.lunar_year",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "lunar",
                                                   "lunar_year": 1800,
                                                   "lunar_month": 1,
                                                   "lunar_day": 1}))
        # R158b（D-204b）：bazi lunar 换算后公历年份范围（line 174 独立
        # 校验分支）400 校验 standing 覆盖——err.bazi.lunar_year（R156b）
        # 只覆盖 lunar_to_solar 抛异常路径（lunar_year=1800 经 line 172
        # 捕获转 400），line 174 是 lunar_to_solar **成功**但换算后公历
        # 年份越界（如农历 2100-12 月换算到公历 2101 年）的独立校验——
        # 两条路径不同，lunar_year 断言不构成 line 174 的覆盖（若该独立
        # 校验回归为 500 或被移除导致越界公历年份进入排盘则不可见，与
        # R156b err.bazi.lunar_year 同族——同端点不同校验维度）。实测
        # lunar_year=2100/12/15 → 400 "换算后公历年份需在 1900-2100 之间"
        # ——补断言零风险。
        _expect_400("err.bazi.lunar_solar_range",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "calendar_type": "lunar",
                                                   "lunar_year": 2100,
                                                   "lunar_month": 12,
                                                   "lunar_day": 15}))
        # R151b（D-197b）：bazi 端点 ask_hour/ask_date 格式/range 缺失/range
        # 格式四条 400 校验分支 standing 覆盖——err.bazi.calendar/scope/
        # gender/year/lunar（R139b/R150b）已覆盖六条，但 ask_hour（line
        # 141）、ask_date 格式（line 146）、scope=range 缺 range_start/end
        # （line 152）、range 格式（line 157）四条零断言（若校验回归为 500
        # 或被移除则不可见，与 R139b err.bazi.calendar 同族——同端点不
        # 同校验维度）。实测 ask_hour=24/ask_date=garbage/range 缺失/
        # range_start=garbage 均正确返回 400 + detail——补断言零风险。
        _expect_400("err.bazi.ask_hour",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "ask_hour": 24}))
        _expect_400("err.bazi.ask_date",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "ask_date": "garbage"}))
        _expect_400("err.bazi.range_missing",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "scope": "range"}))
        _expect_400("err.bazi.range_format",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "scope": "range",
                                                   "range_start": "garbage",
                                                   "range_end": "2026-01-01"}))
        # R152b（D-198b）：bazi range 运行时值域校验（calc_range 内
        # ValueError→400，line 217）两条 400 校验分支 standing 覆盖——
        # err.bazi.range_missing/range_format（R151b）只测输入形状，倒序
        # （end 早于 start）、超 31 天两条运行时值域校验零断言（missing/
        # format 断言不触发 calc_range 内部校验，若倒序/超长回归为 500
        # 或被移除则不可见，与 R151b err.bazi.range_format 同族——同端点
        # 不同校验维度）。实测倒序/超31天均正确返回 400 + detail——
        # 补断言零风险。
        _expect_400("err.bazi.range_order",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "scope": "range",
                                                   "range_start": "2026-02-01",
                                                   "range_end": "2026-01-01"}))
        _expect_400("err.bazi.range_span",
                    client.post("/api/bazi", json={"year": 1990, "month": 5,
                                                   "day": 15, "hour": 10,
                                                   "scope": "range",
                                                   "range_start": "2026-01-01",
                                                   "range_end": "2026-03-15"}))
        _expect_400("err.qiming.surname",
                    client.post("/api/qiming", json={"surname": "张伟", "year": 1990,
                                                     "month": 5, "day": 15,
                                                     "hour": 10}))
        # R140b（D-186b）：qiming 端点 gender/year 两条 400 校验分支 standing
        # 覆盖——err.qiming.surname 只测姓氏，gender（非 男/女，line 906）、
        # year（年份范围，line 896）零断言（若校验回归为 500 或被移除则不可见，
        # 与 R139b err.bazi.calendar/scope/gender 同族——同端点不同校验维度）。
        # 实测 gender=中 → 400 "gender 须为 男/女，收到 中"；year=1800 → 400
        # "年份须在 1900-2100，收到 1800"——补断言零风险。
        _expect_400("err.qiming.gender",
                    client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                     "month": 1, "day": 1,
                                                     "hour": 12, "gender": "中"}))
        _expect_400("err.qiming.year",
                    client.post("/api/qiming", json={"surname": "李", "year": 1800,
                                                     "month": 1, "day": 1,
                                                     "hour": 12, "gender": "男"}))
        # R149b（D-195b）：qiming 端点 month/day/hour 三条 400 校验分支
        # standing 覆盖——err.qiming.surname/gender/year（R140b）已覆盖
        # 三条，但 month（line 894-895）、day（line 896-897）、hour（line
        # 898-899）三条零断言（若校验回归为 500 或被移除则不可见，与 R140b
        # err.qiming.gender 同族——同端点不同校验维度）。实测 month=13→400、
        # day=0→400、hour=24→400——补断言零风险。
        _expect_400("err.qiming.month",
                    client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                     "month": 13, "day": 1,
                                                     "hour": 12, "gender": "男"}))
        _expect_400("err.qiming.day",
                    client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                     "month": 5, "day": 0,
                                                     "hour": 12, "gender": "男"}))
        _expect_400("err.qiming.hour",
                    client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                     "month": 5, "day": 15,
                                                     "hour": 24, "gender": "男"}))
        # R152b（D-198b）：qiming 计算失败分支（name_candidates 抛异常
        # →400，line 914）standing 覆盖——err.qiming.*（R140b/R149b）
        # 只测参数校验，计算失败路径零断言（若计算失败回归为 500 或被
        # 移除则不可见，与 R149b err.qiming.month 同族——同端点不同校验
        # 维度）。实测 month=2/day=30（不存在的日期）→ 400 "起名计算
        # 失败：day 30 must be in range 1..28 for month 2 in year 1990"
        # ——补断言零风险。
        _expect_400("err.qiming.calc_fail",
                    client.post("/api/qiming", json={"surname": "李", "year": 1990,
                                                     "month": 2, "day": 30,
                                                     "hour": 12, "gender": "男"}))
        # R143b（D-189b）：taohua 端点 year/gender/calendar 三条 400 校验
        # 分支 standing 覆盖——taohua（行 918）调用 req.validate_ranges()
        # 继承 BaziRequest 校验，但 err.* 只覆盖 bazi 端点，taohua 同名
        # 校验分支零断言（若 taohua 误移除 validate_ranges() 调用则不可见，
        # 与 R139b err.bazi.calendar/scope/gender 同族——独立端点需独立
        # 断言）。实测 year=1800/gender=中/calendar=garbage 均正确返回
        # 400 + detail——补断言零风险。
        _expect_400("err.taohua.year",
                    client.post("/api/taohua", json={"year": 1800, "month": 5,
                                                     "day": 15, "hour": 10,
                                                     "gender": "男"}))
        _expect_400("err.taohua.gender",
                    client.post("/api/taohua", json={"year": 1990, "month": 5,
                                                     "day": 15, "hour": 10,
                                                     "gender": "中"}))
        _expect_400("err.taohua.calendar",
                    client.post("/api/taohua", json={"year": 1990, "month": 5,
                                                     "day": 15, "hour": 10,
                                                     "gender": "男",
                                                     "calendar_type": "garbage"}))
        # R164b（D-210b）：taohua 端点 422 排盘失败分支 standing 覆盖——
        # err.taohua.*（R143b）全为 400 参数校验断言，422 是 compute 抛
        # 异常路径（合法参数但组合非法，如 1990-02-30 不存在，line 942
        # "排盘失败：{exc}"）零断言（若排盘异常回归为 500、或被移除导致
        # 非法组合静默排盘则不可见，与 R163b err.bazi.paipan_fail 同族
        # ——不同端点同状态码维度）。实测 year=1990/month=2/day=30 → 422
        # "排盘失败：day 30 must be in range 1..28 for month 2 in year
        # 1990"——补断言零风险。
        _expect_422("err.taohua.paipan_fail",
                    client.post("/api/taohua", json={"year": 1990, "month": 2,
                                                     "day": 30, "hour": 10,
                                                     "gender": "男"}))
        # R144b（D-190b）：compare_works/concept/research 三条 400 校验分支
        # standing 覆盖——compare_works check（行 1158）只测有命中路径，
        # work_a/work_b 缺失校验（line 517）零断言；concept check（行
        # 1156）只测 q=無為，q 为空校验（line 496）零断言；research
        # check（行 1368）只测 max_addresses=2，max_addresses=0 范围校验
        # （line 476）零断言。若这些校验回归为 500 或被移除则不可见
        # （L-22/L-23 同族；与 R139b/R142b 同族——同端点不同校验维度）。
        # 实测三条均正确返回 400 + detail——补断言零风险。
        _expect_400("err.compare_works.missing",
                    client.get("/api/compare_works", params={"work_b": "KR5c0126",
                                                              "q": "無爲"}))
        # R171b（D-219b）：/api/compare_works q 校验两条分支零 standing 断言——
        # err.compare_works.missing（R144b）只测 work_a/work_b 空，q 空
        # （line 527 "q 不能为空"）+ q 过长（line 529 "q 过长"）零断言
        # （若校验回归为 500、或被移除则不可见，与 err.concept.empty 同族
        # ——同内核不同端点 q 空校验）。实测 q="  " → 400 "q 不能为空"，
        # q="甲"*201 → 400 "q 过长"——补断言零风险。
        _expect_400("err.compare_works.q_empty",
                    client.get("/api/compare_works",
                               params={"work_a": "KR5c0057",
                                       "work_b": "KR5c0126", "q": "  "}))
        _expect_400("err.compare_works.q_too_long",
                    client.get("/api/compare_works",
                               params={"work_a": "KR5c0057",
                                       "work_b": "KR5c0126",
                                       "q": "甲" * 201}))
        _expect_400("err.concept.empty",
                    client.get("/api/concept", params={"q": ""}))
        _expect_400("err.research.max_addresses",
                    client.get("/api/research", params={"q": "潛龍勿用",
                                                         "max_addresses": 0}))
        # R145b（D-191b）：search 端点 q 为空校验 standing 覆盖——search
        # check（行 1051）只测 q=潛龍勿用，q 为空校验（line 361）零断言
        # （若校验回归为 500、或被移除导致空查询进入检索则不可见，与
        # R139b/R144b 同族——同端点不同校验维度）。实测 q=""→400 +
        # detail "q 不能为空——检索需要查询词；找某个地址请用 /api/addr"
        # ——补断言零风险。
        _expect_400("err.search.empty",
                    client.get("/api/search", params={"q": ""}))
        # R146b（D-192b）：concept/research 端点 q 过长校验 standing 覆盖
        # ——concept check（行 1156）只测 q=無為，q 过长校验（line 498:
        # "q 过长（≤200 字符）"）零断言；research check（行 1392）只测
        # q=潛龍勿用，q 过长校验（line 474）零断言。若校验回归为 500、
        # 或被移除导致超长查询进入检索则不可见（L-22/L-23 同族；与
        # R139b/R144b/R145b 同族——同端点不同校验维度）。实测 q=甲*201
        # /乙*201 均正确返回 400 + detail——补断言零风险。
        _expect_400("err.concept.too_long",
                    client.get("/api/concept", params={"q": "甲" * 201}))
        _expect_400("err.research.too_long",
                    client.get("/api/research", params={"q": "乙" * 201,
                                                         "max_addresses": 2}))
        # R153b（D-199b）：research/compare_works 端点 q 空校验 standing
        # 覆盖——err.research.max_addresses/too_long（R144b/R146b）只测
        # 参数范围/长度，research q 空校验（line 472）零断言；
        # err.compare_works.missing（R144b）只测 work_a/work_b 空，
        # compare_works q 空校验（line 519）零断言（若校验回归为 500、
        # 或被移除导致空查询进入检索/比对则不可见，与 R144b/R146b 同族
        # ——同端点不同校验维度）。实测 research q="" / compare_works q=""
        # 均正确返回 400 + detail "q 不能为空"——补断言零风险。
        _expect_400("err.research.empty",
                    client.get("/api/research", params={"q": "",
                                                         "max_addresses": 2}))
        _expect_400("err.compare_works.q_empty",
                    client.get("/api/compare_works", params={"work_a": "KR1a0001",
                                                              "work_b": "KR1a0032",
                                                              "q": ""}))
        # R147b（D-193b）：compare 端点 gua 范围校验 standing 覆盖——
        # compare check（行 1158）只测 gua=28/yao=九二，gua 超范围校验
        # （line 405: "gua 需在 1-64"）零断言（若校验回归为 500、或被
        # 移除导致超范围 gua 进入比对则不可见，与 R139b/R144b/R146b
        # 同族——同端点不同校验维度）。实测 gua=99 → 400 + detail
        # "gua 需在 1-64"——补断言零风险。
        _expect_400("err.compare.gua_range",
                    client.get("/api/compare", params={"gua": 99, "yao": "九二"}))
        # R148b（D-194b）：addr zhouyi 无 gua / bookstudy structure/chapter
        # work_id 为空三条 400 校验分支 standing 覆盖——addr check（行
        # 1073）只测 scheme=zhouyi+gua=1，zhouyi 无 gua 校验（line 390:
        # "zhouyi 定位需提供 gua（1-64）"）零断言；bookstudy.structure
        # check（行 1167）只测 KR1a0001，work_id 为空校验（line 695:
        # "work_id 不能为空"）零断言；bookstudy.chapter check（行 1080）
        # 只测 KR1a0001，work_id 为空校验（line 728）零断言。若这些校验
        # 回归为 500、或被移除导致非法输入进入计算则不可见（L-22/L-23
        # 同族；与 R139b/R144b/R147b 同族——同端点不同校验维度）。实测
        # 三条均正确返回 400 + detail——补断言零风险。
        _expect_400("err.addr.zhouyi.no_gua",
                    client.get("/api/addr", params={"scheme": "zhouyi"}))
        _expect_400("err.bookstudy.structure.empty",
                    client.get("/api/bookstudy/structure", params={"work_id": ""}))
        _expect_400("err.bookstudy.chapter.empty",
                    client.get("/api/bookstudy/chapter",
                               params={"work_id": "", "scheme": "zhouyi", "addr1": 1}))
        # R152b（D-198b）：bookstudy chapter 的 scheme 空校验（line 730
        # "scheme 不能为空"）standing 覆盖——err.bookstudy.chapter.empty
        # （R148b）只测 work_id 空，scheme 空分支零断言（若校验回归为
        # 500 或被移除则不可见，与 R148b err.bookstudy.chapter.empty 同族
        # ——同端点不同校验维度）。实测 work_id=KR1a0001&scheme= → 400
        # "scheme 不能为空"——补断言零风险。
        _expect_400("err.bookstudy.chapter.scheme",
                    client.get("/api/bookstudy/chapter",
                               params={"work_id": "KR1a0001", "scheme": "", "addr1": 1}))
        # R159b（D-205b）：/api/threads 非法 kind 400 校验 standing 覆盖——
        # threads check（行 1732）只测合法 kind=summary 路径，非法 kind
        # （kind=bogus）此前触发 knowledge.py INSERT 的 sqlite3.IntegrityError
        # （DB CHECK 约束）未被 except ValueError 捕获 → 500 崩溃（真实 bug，
        # R159b 摸底实测）。修复（except (ValueError, sqlite3.IntegrityError)
        # 转 400）后补断言：kind=bogus → 400 + detail 含 "CHECK constraint"
        # ——若回归为 500 则断言失败（抓 500→400 静默回归，与其余端点
        # "非法参数→400"纪律一致）。
        _expect_400("err.threads.kind",
                    client.post("/api/threads", json={"kind": "bogus",
                                                      "claim": "测试",
                                                      "method": "probe"}))

        # 核心研究/历史/线程/健康端点（R54b）：全部确定性、无写副作用
        # （ask 不落库不缓存、history/threads 只读）。external/news 依赖
        # 代理与网络，明确不进 standing 自测（D-100b）。
        check("research", client.get("/api/research", params={"q": "潛龍勿用", "max_addresses": 2}),
              lambda j: j.get("evidence") and j.get("steps"))
        # R132b（D-178b）：research 的 allow_damaged 放行分支 standing 覆盖——
        # research check 只测默认（allow_damaged 缺省 False），放行损坏区 suspect
        # 单元的分支零断言（若放行逻辑回归为永远拒绝/永远放行则不可见，与 R118b/
        # R119b/R124b/R126b/R128b/R130b 同族）。实测 allow_damaged=true → 200 +
        # refused=False + evidence 非空（放行分支可用）。
        check("research.allow_damaged", client.get("/api/research", params={"q": "潛龍勿用",
              "max_addresses": 2, "allow_damaged": True}),
              lambda j: j.get("refused") is False and bool(j.get("evidence")))
        # R170b（D-217b）：/api/ask 端点 q 校验两条分支零 standing 断言——
        # q="" → 422（Pydantic min_length），q="   " → 400 "q 不能为空"
        # （strip() 后空）。ask/ask.llm.shape check 只测正常路径，两条 q
        # 空/空白校验分支零断言（若 Pydantic min_length 被移除、或 strip
        # 校验回归为 422/500 则不可见，与 err.research.empty 同族——
        # 同内核不同端点 q 空校验）。实测 q="" → 422，q="   " → 400——
        # 补断言零风险。
        _ask_empty = client.post("/api/ask", json={"q": "   ", "max_addresses": 2})
        assert _ask_empty.status_code == 400, ("err.ask.q_empty",
                                               _ask_empty.status_code,
                                               _ask_empty.text[:200])
        assert _ask_empty.json().get("detail") == "q 不能为空", ("err.ask.q_empty",
                                                                _ask_empty.text[:200])
        ok.append("err.ask.q_empty")
        _ask_too_short = client.post("/api/ask", json={"q": "", "max_addresses": 2})
        assert _ask_too_short.status_code == 422, ("err.ask.q_too_short",
                                                   _ask_too_short.status_code,
                                                   _ask_too_short.text[:200])
        ok.append("err.ask.q_too_short")
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
        # R126b（D-172b）：history.detail 断言的 id 来源修正——原用
        # history_db.count()（行数）当 id 查，历史库经删除后 id 不连续
        # （实测 count=31 但 id 31 已删 → 404），改为取最新记录真实 id
        # （list_records(limit=1)[0]["id"]，实测 91）——count 非 id 的
        # 硬编码假设是 L-23 同族缺陷，按 FIX-DON'T-HIDE 修根因。
        _latest_rid = history_db.list_records(limit=1)
        check("history.detail", client.get(f"/api/history/{_latest_rid[0]['id'] if _latest_rid else 0}"),
              lambda j: j is None or "paipan" in j)  # 可能无该 id，但必须结构正确
        # R138b（D-184b）：history.detail 缺失记录拒绝分支 standing 覆盖——
        # 现有 check 只测命中路径（最新 id 91 → paipan），404 拒绝分支（get_record
        # 返回 None → HTTPException(404)）零断言（若 None 校验回归为误返回空
        # dict、或 HTTPException 误变 500，selftest 全绿看不见，与 R134b
        # bookstudy.summary.missing 同族）。实测 GET /api/history/99999 → 404
        # + detail 非空（拒绝分支可用）。404 不走 check() 闭包（它断言 200），
        # 单独断言状态码 + detail 形状。
        # 背景：R136b（8cd21e3）已加此断言，R137b（dd8ecff）误删——本轮恢复。
        _miss = client.get("/api/history/99999")
        assert _miss.status_code == 404, ("history.detail.missing", _miss.status_code, _miss.text[:200])
        assert _miss.json().get("detail"), ("history.detail.missing", _miss.text[:200])
        ok.append("history.detail.missing")
        check("threads.detail", client.get("/api/threads/1"),
              lambda j: "claims" in j and "turns" in j)
        # R169b（D-215b）：threads.detail 404 拒绝路径 standing 覆盖——
        # threads.detail check（上方）只测 tid=1 命中路径，tid 不存在
        # （line 637 "线程 {tid} 不存在或暂无对话"）零断言（若该 404
        # 校验回归为 500、或被移除导致非法 tid 静默返回空，
        # selftest 全绿看不见，与 history.detail.missing 同族——
        # 同状态码不同端点，L-22/L-23 同族）。实测 tid=99999 → 404 +
        # detail "线程 99999 不存在或暂无对话"——补断言零风险。
        _td_miss = client.get("/api/threads/99999")
        assert _td_miss.status_code == 404, ("threads.detail.missing",
                                             _td_miss.status_code,
                                             _td_miss.text[:200])
        assert _td_miss.json().get("detail"), ("threads.detail.missing",
                                               _td_miss.text[:200])
        ok.append("threads.detail.missing")
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
