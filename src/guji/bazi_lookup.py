"""bazi_lookup — 八字坐标 → 命理书检索（FTS + bge 双路径）。

把 `bazi.Bazi` 的纯计算坐标（四柱/日主/纳音）接到现有语料检索：
  * FTS 路径：坐标词（日柱干支、纳音、日主等）在各命理书中精确检索，
    返回带引用（文件+页锚点）的原文——与 answer.py 同一语义：给证据，不生成。
  * bge 路径：对命理书单元做语义编码（向量缓存复用，照 eval_g1 的
    bge_docvecs 先例），用坐标词查询 top-k，覆盖"转述式问法"。

命理书目（八字/星命/占卜类，实测均在库且有内容）：
  三命通會 KR3g0042 · 星學大成 KR3g0041 · 李虛中命書 KR3g0033 ·
  玉管照神局 KR3g0044 · 太清神鑑 KR3g0045 · 星命溯源 KR3g0035 ·
  御定星歷考原 KR3g0050 · 太乙金鏡式經 KR3g0047 · 遁甲演義 KR3g0048 ·
  京氏易傳 KR3g0030 · 六壬大全 KR3g0031

只读。数字来自脚本输出（GOAL §2）。查询词来自坐标换算，非新文本。
"""
from __future__ import annotations

import json
import os
import sqlite3

import numpy as np

from .bazi import Bazi
from .search import render_citation

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(ROOT, "data", "index", "corpus.db")

# 八字命理相关书目（有内容、与排盘坐标直接相关的优先在前）
MINGLI_WORKS = [
    "KR3g0042",  # 三命通會
    "KR3g0041",  # 星學大成
    "KR3g0033",  # 李虛中命書
    "KR3g0044",  # 玉管照神局
    "KR3g0045",  # 太清神鑑
    "KR3g0035",  # 星命溯源
    "KR3g0050",  # 御定星歷考原
    "KR3g0047",  # 太乙金鏡式經
    "KR3g0048",  # 遁甲演義
    # P2 子平经典语料扩充（2026-08-15 落盘，过三道判定第一步：古籍原文）
    "ziping-zhenquan",  # 子平真诠
    "sanming-tonghui",  # 三命通会
    "wuxing-dayi",      # 五行大义
    "wuxing-jingji",    # 五行精纪
    "mingli-tanyuan",   # 命理探原
    "mingli-yueyan",    # 命理约言
    "lantai-miaoxuan",  # 兰台妙选
    # P2 缺口1 补登（2026-08-16，过三道判定，见 DECISIONS.md D-044）
    "ditiansui",          # 滴天髓（任铁樵阐微）
    "qiongtongbaojian",   # 穷通宝鉴
]

MODEL_DIR = os.path.join(ROOT, "data", "external", "bge-small-zh-v1.5")
SEM_DOCVECS = os.path.join(ROOT, "data", "catalog", "bge_mingli_docvecs.npy")
SEM_DOCMETA = os.path.join(ROOT, "data", "catalog", "bge_mingli_docmeta.json")


# --------------------------------------------------------------------------------------
# 坐标 → 查询词
# --------------------------------------------------------------------------------------
def queries_from(b: Bazi) -> list[tuple[str, str]]:
    """(词, 说明) 列表。优先长词（日柱干支/纳音/日主），单字只作补充。

    干支两字词在 FTS 分段后是相邻 token 短语，可精确命中；单字"甲"噪音大，
    仅作 bge 语义补充用，不参与 FTS 主检索。
    """
    out = [
        (b.day, "日柱"),                       # 如 甲辰
        (b.month, "月柱"),                     # 如 丙寅
        (b.year, "年柱"),                      # 如 甲辰
        (b.nayin[2], "日柱纳音"),              # 如 覆灯火
        (b.nayin[1], "月柱纳音"),
        (b.nayin[0], "年柱纳音"),
        (b.day_master, "日主"),                # 如 甲
    ]
    return out


def _fts_phrase(q: str) -> str:
    from .variants import fold, segment_cjk
    seg = segment_cjk(fold(q)).replace('"', "")
    return f'"{seg}"'


# --------------------------------------------------------------------------------------
# FTS 路径
# --------------------------------------------------------------------------------------
def retrieve_fast(b: Bazi, per_query: int = 2, per_work: int = 1,
                  top_queries: int = 3) -> list[dict]:
    """坐标词 FTS 检索命理书，返回带引用的原文证据。

    返回 [{query, why, work_id, title, citation, text, layer}...]，
    按 (query 权重, work 广度) 排序去重。
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    qs = queries_from(b)[:top_queries]
    seen: set[tuple] = set()
    out: list[dict] = []
    for q, why in qs:
        if len(q) < 2:
            continue  # 单字不参与 FTS（噪音）
        for wid in MINGLI_WORKS:
            hits = conn.execute(
                "SELECT u.work_id, w.title, u.layer, u.page_anchor, u.file, u.text, "
                "u.raw_start, bm25(unit_fts) AS score "
                "FROM unit_fts JOIN unit u ON u.id = unit_fts.rowid "
                "JOIN work w ON w.id = u.work_id "
                "WHERE u.work_id = ? AND unit_fts MATCH ? "
                "ORDER BY score LIMIT ?", (wid, _fts_phrase(q), per_query)).fetchall()
            for h in hits:
                key = (h["work_id"], h["raw_start"])
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "query": q, "why": why, "work_id": h["work_id"],
                    "title": h["title"], "layer": h["layer"],
                    "page_anchor": h["page_anchor"], "file": h["file"],
                    "text": h["text"], "score": float(h["score"]),
                    # R179b（D-231b，审查轨 R118a-03）：本函数返回裸 dict 而非
                    # Hit，此前**没有 citation 键**——前端 `esc(ev.citation||'')`
                    # 把出处静默渲染成空串，原文有了出处没了（宪法第三条
                    # 「引用与生成分离」要求原文必带可核验出处）。
                    # 复用 search.render_citation 而不是在此再拼一遍格式：
                    # 同一渲染规则两份拷贝正是 LESSONS.md L-01 的事故形态。
                    "citation": render_citation(
                        work_id=h["work_id"], title=h["title"],
                        page_anchor=h["page_anchor"], file=h["file"]),
                })
                if len([o for o in out if o["work_id"] == wid]) >= per_work:
                    break
    conn.close()
    out.sort(key=lambda o: (-o["score"], o["work_id"]))
    return out[: 20]


# --------------------------------------------------------------------------------------
# bge 语义路径（命理书向量缓存，照 eval_g1 的 bge_docvecs 先例）
# --------------------------------------------------------------------------------------
_sem_cache: tuple | None = None


def _sem_vecs(conn) -> tuple:
    """命理书单元向量 + 平行元数据。缓存按 work/单元 id 列表校验新鲜度。"""
    global _sem_cache
    if _sem_cache is not None:
        return _sem_cache
    rows = conn.execute(
        "SELECT id, work_id, layer, page_anchor, file, text FROM unit "
        "WHERE work_id IN (%s) ORDER BY id" % ",".join("?" * len(MINGLI_WORKS)),
        MINGLI_WORKS).fetchall()
    ids_now = [r["id"] for r in rows]
    meta = {"ids": ids_now,
            "meta": [{"id": r["id"], "work_id": r["work_id"], "layer": r["layer"],
                      "page_anchor": r["page_anchor"], "file": r["file"]}
                     for r in rows]}
    if os.path.exists(SEM_DOCVECS) and os.path.exists(SEM_DOCMETA):
        old = json.load(open(SEM_DOCMETA, encoding="utf-8"))
        old_meta = old.get("meta") or []
        # 结构校验：缓存必须含 id 字段（早期缓存缺它会导致回查 KeyError）
        if (old.get("ids") == ids_now and old_meta
                and all("id" in m for m in old_meta)):
            vecs = np.load(SEM_DOCVECS)
            _sem_cache = (vecs, old_meta)
            return _sem_cache
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_DIR)
    vecs = np.asarray(model.encode([r["text"] for r in rows], batch_size=64,
                                   show_progress_bar=False, normalize_embeddings=True),
                      dtype=np.float32)
    np.save(SEM_DOCVECS, vecs)
    json.dump(meta, open(SEM_DOCMETA, "w", encoding="utf-8"))
    _sem_cache = (vecs, meta["meta"])
    return _sem_cache


def retrieve_semantic(b: Bazi, top_k: int = 8) -> list[dict]:
    """bge 语义检索：以坐标词（含单字日主/纳音）为查询，命中命理书相关原文。

    元数据缓存不含 text（text 大、避免 json 膨胀），命中后按单元 id 回查。
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    vecs, meta = _sem_vecs(conn)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_DIR)
    queries = [q for q, _ in queries_from(b)]
    qv = np.asarray(model.encode(queries, normalize_embeddings=True), dtype=np.float32)
    # 取各查询最高分的并集（一个单元被任一坐标词命中即算）
    sims = vecs @ qv.T
    best = sims.max(axis=1)
    order = np.argsort(-best)[:top_k]
    out = []
    for idx in order:
        m = meta[idx]
        r = conn.execute("SELECT text FROM unit WHERE id=?", (m["id"],)).fetchone()
        w = conn.execute("SELECT title FROM work WHERE id=?", (m["work_id"],)).fetchone()
        out.append({
            "query": " / ".join(queries), "why": "语义检索",
            "work_id": m["work_id"],
            "title": w["title"] if w else None,   # 语义路径补书名（原硬编码 None）
            "layer": m["layer"],
            "page_anchor": m["page_anchor"], "file": m["file"],
            "text": r["text"] if r else "", "score": float(best[idx]),
            # 同 retrieve_fast：语义路径也必须带出处（R179b，D-231b）
            "citation": render_citation(
                work_id=m["work_id"], title=w["title"] if w else None,
                page_anchor=m["page_anchor"], file=m["file"]),
        })
    conn.close()
    return out


if __name__ == "__main__":
    print("usage: import from guji.bazi_lookup — no CLI here (see scripts/ask_bazi.py)")
