"""2a 方案 A/B — sentence-transformers + BAAI/bge-small-zh-v1.5（PyTorch CPU）实测。

D-031 否决了方案 C（TF-IDF+SVD，hit 67.3% < 80%）；D-032 把方案 A/B 记为 BLOCKED
（红线第 3 类：新外部依赖 + 联网抓取）。用户已于 2026-08-15 显式授权
（"授权引入 sentence-transformers+PyTorch CPU、授权下载 BAAI/bge 模型"），
provenance 见 data/catalog/model_provenance.json（sha256/source_url/fetched_at/licence=MIT）。

流程与方案 C 完全一致（probe_embed_tfidf.py），只换 encoder：
  - 5088 个 zhouyi 經层带卦/爻地址单元为文档集
  - 55 条 D-029 手写转述（probe_t7r_concept.PARAPHRASES，不手写新题）为查询
  - bge-small-zh-v1.5 编码，余弦 top-10 判 hit

闸门（先定后测，照 GOAL §3）：
  hit rate      ≥ 80%   55 条转述 top-10 含 gold 地址
  建向量耗时    ≤ 10 分钟  wall clock
  单次查询延迟  ≤ 2 秒     55 条各查一次取中位数
  内存峰值      ≤ 4 GB     模型 + 5088 向量 + 矩阵临时
  13 道闸门     全过

bge 检索惯例（模型卡）：查询侧加指令前缀 "为这个句子生成表示以用于检索相关文章："，
文档侧不加。本探针照此执行。
"""
import json
import sqlite3
import time
from pathlib import Path

import numpy as np

DB = "data/index/corpus.db"
REPORT = "probes/embed_bge_report.json"
MODEL_DIR = "data/external/bge-small-zh-v1.5"
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
# Persisted doc vectors so scripts/eval_g1.py can score retrieval_concept without
# re-encoding 5088 units on every gate run. Freshness: the id list is compared against the
# current corpus; any change (rebuild, new work) forces a re-encode.
DOCVECS = "data/catalog/bge_docvecs.npy"
DOCMETA = "data/catalog/bge_docmeta.json"

from probe_t7r_concept import PARAPHRASES  # noqa: E402


def main():
    t_start = time.time()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 与方案 C 完全相同的文档集：经层带卦/爻地址单元
    cur.execute("""
        SELECT unit.id, unit.text, unit.addr1, unit.addr2,
               work.id AS work_id
        FROM unit
        JOIN work ON work.id = unit.work_id
        WHERE unit.layer = '經'
          AND unit.addr1 IS NOT NULL
          AND unit.addr2 IS NOT NULL
        ORDER BY unit.id
    """)
    rows = cur.fetchall()
    n_units = len(rows)
    print(f"loaded {n_units} 經 units with 卦/爻 addresses")
    units = [r[1] for r in rows]
    addr_lookup = {r[0]: (r[2], r[3]) for r in rows}
    ids = [r[0] for r in rows]

    # ---- load model (local copy, no network) ----
    from sentence_transformers import SentenceTransformer
    t_model = time.time()
    model = SentenceTransformer(MODEL_DIR)
    print(f"model loaded in {time.time() - t_model:.1f}s")

    # ---- encode documents (build) ----
    t_enc = time.time()
    doc_vecs = np.asarray(model.encode(units, batch_size=64, show_progress_bar=False,
                                       normalize_embeddings=True), dtype=np.float32)
    build_time = time.time() - t_start
    # persist for eval_g1 reuse
    np.save(DOCVECS, doc_vecs)
    json.dump({"ids": ids, "addrs": [[r[2], r[3]] for r in rows]},
              open(DOCMETA, "w", encoding="utf-8"))
    print(f"cached doc vectors -> {DOCVECS} ({doc_vecs.nbytes / 1e6:.1f}MB) + {DOCMETA}")
    print(f"encoded {n_units} docs: {doc_vecs.shape} dtype={doc_vecs.dtype} "
          f"nbytes={doc_vecs.nbytes / 1e6:.1f}MB in {time.time() - t_enc:.1f}s")
    print(f"\n=== build timing ===")
    print(f"total build time: {build_time:.1f}s "
          f"({'OK' if build_time <= 600 else 'OVER 10min'})")

    # ---- query: 55 paraphrases, top-10 ----
    top_k = 10
    hits = 0
    latencies = []
    miss_details = []

    print(f"\n=== paraphrase retrieval (bge-small-zh-v1.5 + cosine) ===")
    for query, exp_gua, exp_yao, why in PARAPHRASES:
        t_q = time.time()
        q = model.encode([QUERY_PREFIX + query], normalize_embeddings=True)
        q = np.asarray(q, dtype=np.float32).reshape(1, -1)
        sims = doc_vecs @ q.T
        sims = sims.ravel()
        order = np.argsort(-sims)
        top = order[:top_k]

        found_rank = None
        for rank, idx in enumerate(top, 1):
            a1, a2 = addr_lookup[ids[idx]]
            if a1 == exp_gua and a2 == exp_yao:
                found_rank = rank
                break

        latency = time.time() - t_q
        latencies.append(latency)

        if found_rank:
            hits += 1
            status = "OK "
        else:
            status = "MISS"
            top_addrs = []
            for idx in top[:3]:
                a1, a2 = addr_lookup[ids[idx]]
                top_addrs.append(f"卦{a1}{a2}")
            miss_details.append({
                "query": query,
                "exp": f"卦{exp_gua}{exp_yao}",
                "top3": top_addrs,
                "top_score": float(sims[top[0]]),
            })

        print(f"  [{status}] expect 卦{exp_gua} {exp_yao}  "
              f"rank={found_rank}  latency={latency*1000:.0f}ms")

    total = len(PARAPHRASES)
    hit_rate = hits / total
    median_lat = float(np.median(latencies)) if latencies else 0.0
    max_lat = float(np.max(latencies)) if latencies else 0.0

    print(f"\n=== verdict (方案 A/B: bge-small-zh-v1.5) ===")
    print(f"hit rate (correct addr in top-{top_k}): {hits}/{total} = "
          f"{100*hit_rate:.1f}%")
    print(f"query latency: median={median_lat*1000:.0f}ms  max={max_lat*1000:.0f}ms  "
          f"({'OK' if median_lat <= 2.0 else 'OVER 2s'})")
    print(f"build time: {build_time:.1f}s  "
          f"({'OK' if build_time <= 600 else 'OVER 10min'})")
    print(f"doc vectors in memory: {doc_vecs.nbytes / 1e6:.1f} MB "
          f"({'OK' if doc_vecs.nbytes < 4e9 else 'OVER 4GB'})")
    print(f"gate: {'PASS (hit>=80%)' if hit_rate >= 0.80 else 'FAIL (hit<80%)'}")

    if miss_details:
        print(f"\n=== {len(miss_details)} MISS details (top-3 false matches) ===")
        for m in miss_details:
            print(f"  exp={m['exp']}  got top3={m['top3']}  score={m['top_score']:.3f}")
            print(f"    query: {m['query']}")

    report = {
        "scheme": "A/B",
        "method": "sentence-transformers + BAAI/bge-small-zh-v1.5 (CPU) + cosine",
        "model_dir": MODEL_DIR,
        "provenance": "data/catalog/model_provenance.json",
        "query_prefix": QUERY_PREFIX,
        "n_units": n_units,
        "n_paraphrases": total,
        "hit_rate_top10": float(hit_rate),
        "hit_rate_top10_count": f"{hits}/{total}",
        "build_time_s": float(build_time),
        "query_latency_median_ms": median_lat * 1000,
        "query_latency_max_ms": max_lat * 1000,
        "doc_vectors_mb": float(doc_vecs.nbytes / 1e6),
        "gate_pass": bool(hit_rate >= 0.80),
        "miss_details": miss_details,
    }
    Path(REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\nreport -> {REPORT}")

    conn.close()
    import sys
    sys.exit(0 if hit_rate >= 0.80 else 1)


if __name__ == "__main__":
    main()
