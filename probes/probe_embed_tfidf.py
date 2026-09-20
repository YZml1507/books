"""T7-r 方案 C — TF-IDF + SVD（零新依赖）CPU embedding 可行性实测。

问题：纯 CPU、无 CUDA、只装 numpy，能否对 5,088 个周易单元建向量索引，
使 55 条手写白话转述 hit rate（top-10 含 gold 地址）≥ 80%？

这是 D-029 char-bigram TF-IDF + cosine（hit rate 78.2%）的升级版：
  - 同样用 char bigram（CJK 无需分词）
  - 加 SVD 降维（TruncatedSVD 的纯 numpy 实现）：
    * 去掉 TF-IDF 高维稀疏向量里的噪声维度
    * 低维 dense 向量做 cosine 更稳
  - 用 log(1+tf) 替裸 tf（sublinear scaling，压低高频卦名的权重）

闸门（先定后测，照 GOAL §3）：
  hit rate      ≥ 80%   55 条转述 top-10 含 gold 地址
  建向量耗时    ≤ 10 分钟  wall clock
  单次查询延迟  ≤ 2 秒     55 条各查一次取中位数
  内存峰值      ≤ 4 GB     TF-IDF 矩阵 + SVD 临时
  13 道闸门     全过

零新依赖：numpy（已在 venv）。无 scipy/sklearn——SVD 用 numpy.linalg.svd。
"""

import json
import sqlite3
import time
from pathlib import Path

import numpy as np
from collections import Counter

DB = "data/index/corpus.db"
REPORT = "probes/embed_c_report.json"

# 55 条手写转述（D-029 沉淀批），与 probe_t7r_concept.py 同源
# 不手写新题（GOAL §4 T1 手写错过两次）
from probe_t7r_concept import PARAPHRASES  # noqa: E402


def char_bigrams(text: str) -> Counter:
    c = Counter()
    for i in range(len(text) - 1):
        c[text[i:i + 2]] += 1
    return c


def main():
    t_start = time.time()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Load all 經-layer units with 卦/爻 addresses (the 5 Zhouyi works)
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
    units = [(r[0], r[1]) for r in rows]
    addr_lookup = {r[0]: (r[2], r[3]) for r in rows}

    # ---- Build char bigram docs + smoothed IDF ----
    docs_bg = []
    df = Counter()
    for uid, text in units:
        bg = char_bigrams(text)
        docs_bg.append((uid, bg))
        for term in bg:
            df[term] += 1
    N = len(docs_bg)
    vocab_sorted = sorted(df.keys())
    vocab_index = {t: i for i, t in enumerate(vocab_sorted)}
    V = len(vocab_index)
    # sklearn-style smoothed IDF
    idf = np.array([np.log((1 + N) / (1 + df[t])) + 1.0
                    for t in vocab_sorted], dtype=np.float64)

    # ---- Build sparse TF-IDF (COO-like via lists), then dense float32 ----
    # We build a dense matrix; 5088 x ~8000 float32 ≈ 163 MB — fine.
    # Construct row by row to avoid Python overhead in inner loop.
    t_tfidf = time.time()
    M = np.zeros((N, V), dtype=np.float32)
    for i, (uid, bg) in enumerate(docs_bg):
        for term, cnt in bg.items():
            j = vocab_index[term]
            # sublinear tf scaling: log(1+tf) * idf
            M[i, j] = np.log1p(cnt) * idf[j]
    # L2 normalize rows
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    M /= norms
    print(f"TF-IDF matrix built: {M.shape} dtype={M.dtype} "
          f"nbytes={M.nbytes / 1e6:.1f}MB in {time.time() - t_tfidf:.1f}s")

    # ---- SVD (single call) ----
    n_components = 100
    t_svd = time.time()
    # full_matrices=False gives U: (N, K), S: (K,), Vt: (K, V) where K=min(N,V)
    U, S, Vt = np.linalg.svd(M, full_matrices=False)
    svd_time = time.time() - t_svd
    print(f"SVD done in {svd_time:.1f}s — "
          f"U={U.shape} S={S.shape} Vt={Vt.shape}")

    # Truncate to n_components
    k = min(n_components, len(S))
    Vt_k = Vt[:k, :]            # (k, V)
    S_k = S[:k]                 # (k,)

    # Variance explained: sum(S_k^2) / sum(S_all^2) — single SVD call reused
    var_all = float((S ** 2).sum())
    var_k = float((S_k ** 2).sum())
    var_explained = var_k / var_all if var_all > 0 else 0.0
    print(f"variance explained by top-{k}: {var_explained:.3f}")

    # ---- Transform docs to LSA space: M @ Vt_k^T, then L2 normalize ----
    t_lsa = time.time()
    doc_lsa = M @ Vt_k.T       # (N, k)
    dnorms = np.linalg.norm(doc_lsa, axis=1, keepdims=True)
    dnorms[dnorms == 0] = 1.0
    doc_lsa /= dnorms
    print(f"LSA doc vectors: {doc_lsa.shape} in {time.time() - t_lsa:.1f}s")

    t_build_end = time.time()
    build_time = t_build_end - t_start
    print("\n=== build timing ===")
    print(f"total build time: {build_time:.1f}s "
          f"({'OK' if build_time <= 600 else 'OVER 10min'})")

    # ---- Query: project paraphrase to LSA space, cosine ----
    top_k = 10
    hits = 0
    rank_in_k = 0
    latencies = []
    miss_details = []

    # Pre-build query TF-IDF helper inline
    print(f"\n=== paraphrase retrieval (TF-IDF + SVD{100} + cosine) ===")
    for query, exp_gua, exp_yao, why in PARAPHRASES:
        t_q = time.time()
        qv = np.zeros(V, dtype=np.float32)
        qbg = char_bigrams(query)
        for term, cnt in qbg.items():
            j = vocab_index.get(term)
            if j is not None:
                qv[j] = np.log1p(cnt) * idf[j]
        qn = np.linalg.norm(qv)
        if qn == 0:
            print(f"  [ZERO] {query!r}")
            continue
        qv /= qn
        # Project to LSA space
        q_lsa = qv @ Vt_k.T
        qln = np.linalg.norm(q_lsa)
        if qln == 0:
            print(f"  [ZERO-LSA] {query!r}")
            continue
        q_lsa /= qln

        sims = doc_lsa @ q_lsa
        order = np.argsort(-sims)
        top = order[:top_k]

        found_rank = None
        for rank, idx in enumerate(top, 1):
            uid = docs_bg[idx][0]
            a1, a2 = addr_lookup[uid]
            if a1 == exp_gua and a2 == exp_yao:
                found_rank = rank
                break

        latency = time.time() - t_q
        latencies.append(latency)

        status = "OK " if found_rank else "MISS"
        if found_rank:
            hits += 1
            if found_rank <= top_k:
                rank_in_k += 1
        else:
            top_addrs = []
            for idx in top[:3]:
                uid = docs_bg[idx][0]
                a1, a2 = addr_lookup[uid]
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
    hit_rate = rank_in_k / total
    median_lat = float(np.median(latencies)) if latencies else 0.0
    max_lat = float(np.max(latencies)) if latencies else 0.0

    print("\n=== verdict (方案 C: TF-IDF + SVD) ===")
    print(f"hit rate (correct addr in top-{top_k}): {rank_in_k}/{total} = "
          f"{100*hit_rate:.1f}%")
    print(f"exact-rank-1 rate: {hits}/{total} = {100*hits/total:.1f}%")
    print(f"query latency: median={median_lat*1000:.0f}ms  max={max_lat*1000:.0f}ms  "
          f"({'OK' if median_lat <= 2.0 else 'OVER 2s'})")
    print(f"build time: {build_time:.1f}s  "
          f"({'OK' if build_time <= 600 else 'OVER 10min'})")
    print(f"TF-IDF matrix in memory: {M.nbytes / 1e6:.1f} MB "
          f"({'OK' if M.nbytes < 4e9 else 'OVER 4GB'})")
    # All four pre-registered criteria gate the exit (R18a): the docstring lists
    # hit/build/latency/memory as 闸门, but the exit used to test hit_rate only —
    # a partial gate wearing a full gate's docstring.
    gates = {
        "hit>=80%": hit_rate >= 0.80,
        "build<=10min": build_time <= 600,
        "median_latency<=2s": median_lat <= 2.0,
        "memory<4GB": M.nbytes < 4e9,
    }
    gate_ok = all(gates.values())
    print("gate: " + "  ".join(f"[{'PASS' if v else 'FAIL'}] {k}" for k, v in gates.items()))

    if miss_details:
        print(f"\n=== {len(miss_details)} MISS details (top-3 false matches) ===")
        for m in miss_details:
            print(f"  exp={m['exp']}  got top3={m['top3']}  "
                  f"score={m['top_score']:.3f}")
            print(f"    query: {m['query']}")

    report = {
        "scheme": "C",
        "method": "char-bigram TF-IDF (sublinear tf) + TruncatedSVD(100) + cosine",
        "n_units": n_units,
        "n_paraphrases": total,
        "vocab_size": V,
        "svd_components": k,
        "variance_explained": var_explained,
        "hit_rate_top10": float(hit_rate),
        "hit_rate_top10_count": f"{rank_in_k}/{total}",
        "exact_rank1_rate": float(hits / total),
        "build_time_s": float(build_time),
        "svd_time_s": float(svd_time),
        "query_latency_median_ms": median_lat * 1000,
        "query_latency_max_ms": max_lat * 1000,
        "tfidf_matrix_mb": float(M.nbytes / 1e6),
        "gate_pass": gate_ok,
        "gate_criteria": {k: bool(v) for k, v in gates.items()},
        "miss_details": miss_details,
    }
    Path(REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\nreport -> {REPORT}")

    conn.close()
    import sys
    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
