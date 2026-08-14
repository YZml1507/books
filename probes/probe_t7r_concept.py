"""T7-r CPU embedding feasibility — zero-dependency lower bound.

Question: can concept-level (paraphrase) retrieval work on this corpus
WITHOUT a neural embedding model, using only numpy?

Method (zero new deps):
  - char-bigram TF-IDF vectors over the 經 layer of 5 Zhouyi works
  - cosine similarity between a hand-written paraphrase query and every unit
  - check: does the correct 卦/爻 rank in the top-k?

This is a LOWER BOUND test. If even this naive bag-of-bigrams has
discrimination, CPU embedding is certainly feasible. If it fails,
we need a real model (and that decision goes to the user — it's a
new dependency, GOAL §1 line 3).

The paraphrases are hand-written for FEASIBILITY ASSESSMENT ONLY,
not for the eval bank. The eval bank must be auto-derived (GOAL §4 T1).
"""

import sqlite3
import numpy as np
from collections import Counter

DB = "data/index/corpus.db"

# Hand-written paraphrase queries for feasibility probing.
# Each: (query, expected 卦, expected 爻, why)
# These are NOT for the eval bank — they're a minimal signal probe.
PARAPHRASES = [
    # 乾九二: 見龍在田利見大人
    ("龍出現在田野中 利於出現偉大的人物",
     1, "九二", "轉述乾卦九二爻辭"),
    # 乾上九: 亢龍有悔
    ("飛得太高的龍會有悔恨",
     1, "上九", "轉述乾卦上九爻辭"),
    # 坤六四: 括囊无咎无譽
    ("像紮緊口袋一樣 沒有過錯也沒有讚譽",
     2, "六四", "轉述坤卦六四爻辭"),
    # 屯初九: 磐桓利居貞利建侯
    ("徘徊不前 利於堅守正道 利於建立諸侯",
     3, "初九", "轉述屯卦初九爻辭"),
    # 蒙初六: 發蒙利用刑人用說桎梏
    ("啟發蒙昧 利於用刑罰之人 解除枷鎖",
     4, "初六", "轉述蒙卦初六爻辭"),
    # 師九二: 在師中吉无咎王三錫命
    ("在軍隊中居中吉利沒有過錯 君王三次賜予命令",
     7, "九二", "轉述師卦九二爻辭"),
    # 比九五: 顯比王用三驅失前禽
    ("光明親比 君王用三面驅趕 失去前面的禽鳥",
     8, "九五", "轉述比卦九五爻辭"),
    # 泰六五: 帝乙歸妹以祉元吉
    ("帝乙嫁妹妹 因此得福 大吉",
     11, "六五", "轉述泰卦六五爻辭"),
    # 否九五: 休否大人吉其亡其亡繫于苞桑
    ("停止否塞 大人吉利 危險啊危險 繫在苞桑之上",
     12, "九五", "轉述否卦九五爻辭"),
    # 謙九三: 勞謙君子有終吉
    ("勤勞而謙虛的君子 有好結果 吉利",
     15, "九三", "轉述謙卦九三爻辭"),
]


def char_bigrams(text: str) -> Counter:
    """Bag of character bigrams — handles CJK without word segmentation."""
    c = Counter()
    for i in range(len(text) - 1):
        c[text[i:i+2]] += 1
    return c


def build_tfidf(units):
    """Build TF-IDF over char bigrams for a list of (id, text)."""
    docs = []
    df = Counter()
    for uid, text in units:
        bg = char_bigrams(text)
        docs.append((uid, bg))
        for term in bg:
            df[term] += 1
    N = len(docs)
    idf = {t: np.log((N + 1) / (d + 1)) + 1.0 for t, d in df.items()}
    return docs, idf


def vectorize(bg: Counter, idf: dict, vocab_index: dict) -> np.ndarray:
    v = np.zeros(len(vocab_index))
    for term, cnt in bg.items():
        if term in vocab_index:
            v[vocab_index[term]] = cnt * idf.get(term, 1.0)
    return v


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Get all 經-layer units from the 5 Zhouyi works that have 卦/爻 addresses.
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
    print(f"loaded {len(rows)} 經 units with 卦/爻 addresses")

    units = [(r[0], r[1]) for r in rows]
    docs, idf = build_tfidf(units)

    # vocab index
    vocab = set(idf.keys())
    vocab_index = {t: i for i, t in enumerate(sorted(vocab))}
    print(f"vocab size (char bigrams): {len(vocab_index)}")

    # Precompute all doc vectors (sparse-ish; use float32 to save memory)
    doc_vectors = np.zeros((len(docs), len(vocab_index)), dtype=np.float32)
    for i, (uid, bg) in enumerate(docs):
        doc_vectors[i] = vectorize(bg, idf, vocab_index)
    # L2 normalize rows
    norms = np.linalg.norm(doc_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    doc_vectors /= norms

    # unit id -> row index
    uid_to_idx = {uid: i for i, (uid, _) in enumerate(docs)}

    # addr1/addr2 lookup by unit id
    addr_lookup = {r[0]: (r[2], r[3]) for r in rows}

    # For each paraphrase, compute cosine to all docs, check rank of correct.
    print("\n=== paraphrase retrieval (char-bigram TF-IDF + cosine) ===")
    top_k = 10
    hits = 0
    rank_in_k = 0
    for query, exp_gua, exp_yao, why in PARAPHRASES:
        qbg = char_bigrams(query)
        qv = vectorize(qbg, idf, vocab_index)
        qn = np.linalg.norm(qv)
        if qn == 0:
            print(f"  [ZERO] {query!r} — no bigram overlap with vocab")
            continue
        qv /= qn
        sims = doc_vectors @ qv
        order = np.argsort(-sims)
        top = order[:top_k]
        # Does any top-k unit have the expected (addr1, addr2)?
        found_rank = None
        for rank, idx in enumerate(top, 1):
            uid = docs[idx][0]
            a1, a2 = addr_lookup[uid]
            if a1 == exp_gua and a2 == exp_yao:
                found_rank = rank
                break
        status = "OK " if found_rank else "MISS"
        if found_rank:
            hits += 1
            if found_rank <= top_k:
                rank_in_k += 1
        top_text = docs[top[0]][0]
        top_score = sims[top[0]]
        print(f"  [{status}] expect 卦{exp_gua} {exp_yao}  "
              f"rank={found_rank}  top_score={top_score:.3f}")
        print(f"       query: {query}")
        print(f"       why:   {why}")

    total = len(PARAPHRASES)
    print(f"\n=== verdict ===")
    print(f"hit rate (correct addr in top-{top_k}): {rank_in_k}/{total} = "
          f"{100*rank_in_k/total:.1f}%")
    print(f"exact-rank-1 rate: {hits}/{total} = {100*hits/total:.1f}%")

    conn.close()


if __name__ == "__main__":
    main()
