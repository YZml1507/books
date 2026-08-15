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

import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# PyInstaller 单文件模式：资源在 exe 同目录，__file__ 在 _MEIPASS 临时解压目录
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from guji import liuyao as liuyao_mod  # noqa: E402
from guji import huangli as huangli_mod  # noqa: E402
from guji import qiming as qiming_mod  # noqa: E402
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
from guji.search import Corpus  # noqa: E402

app = FastAPI(title="古籍智慧助手（读书 + 八字）", version="0.5.0")

INDEX = os.path.join(ROOT, "web", "static", "index.html")
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
    "play": "幕:場（Shakespeare，addr1=幕，addr2=場）",
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


@app.get("/api/works")
def api_works():
    """语料书目（与 CLI `ask.py works` 同内核 Corpus.coverage）。"""
    c = Corpus(CORPUS_DB)
    try:
        rows = [dict(r) for r in c.coverage()]
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
        # 公历 → 农历（lunar.py）
        try:
            ly, lm, ld, _ = lunar.solar_to_lunar(req.year, req.month, req.day)
        except Exception as exc:
            raise HTTPException(400, f"公历转农历失败：{exc}")
        hour_zhi = (req.hour + 1) // 2 % 12 + 1   # 0-23 → 子=1..亥=12
        ben = liuyao_mod.cast_time(req.year, lm, ld, hour_zhi)
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
            dt = datetime(y, m, d)
        except Exception:
            raise HTTPException(400, f"date 格式应为 YYYY-MM-DD，收到 {date}")
    else:
        dt = datetime.now()

    if YEAR_LO <= dt.year <= YEAR_HI is False:
        if not (YEAR_LO <= dt.year <= YEAR_HI):
            raise HTTPException(400, f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {dt.year}")

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
    try:
        result = qiming_mod.name_candidates(
            surname=req.surname, year=req.year, month=req.month,
            day=req.day, hour=req.hour, gender=req.gender,
            top_n=min(max(req.top_n, 1), 100))
    except Exception as exc:
        raise HTTPException(400, f"起名计算失败：{exc}")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
