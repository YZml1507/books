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
    # 豫六五: 貞疾恆不死
    ("堅守正道雖有疾病 長久不死",
     16, "六五", "轉述豫卦六五爻辭"),
    # 隨六二: 係小子失丈夫
    ("繫念小人 失去丈夫",
     17, "六二", "轉述隨卦六二爻辭"),
    # 蠱初六: 幹父之蠱有子考无咎
    ("整治父親的積弊 有這樣的兒子 父親無過錯",
     18, "初六", "轉述蠱卦初六爻辭"),
    # 臨六三: 甘臨无攸利既憂之无咎
    ("甘心居高臨下 沒有好處 既已憂懼 則無過錯",
     19, "六三", "轉述臨卦六三爻辭"),
    # 觀六四: 觀國之光利用賓于王
    ("觀看國家的風光 利於做君王的賓客",
     20, "六四", "轉述觀卦六四爻辭"),
    # 賁六五: 賁于丘園束帛戔戔吝終吉
    ("裝飾山丘園圃 一束束絲帛微薄 雖有吝嗇 終獲吉利",
     22, "六五", "轉述賁卦六五爻辭"),
    # 復六四: 中行獨復
    ("走在行列中間 獨自返回正道",
     24, "六四", "轉述復卦六四爻辭"),
    # 无妄六三: 无妄之災或繫之牛行人之得邑人之災
    ("不妄為卻遭災禍 有人拴著牛 過路人得了 邑人卻遭殃",
     25, "六三", "轉述无妄卦六三爻辭"),
    # 大畜六五: 豶豕之牙吉
    ("閹割公豬的牙齒 吉利",
     26, "六五", "轉述大畜卦六五爻辭"),
    # 頤六四: 顛頤吉虎視眈眈其欲逐逐无咎
    ("顛倒頤養 吉利 虎視眈眈 欲望追逐 卻無過錯",
     27, "六四", "轉述頤卦六四爻辭"),
    # 大過九二: 枯楊生稊老夫得其女妻无不利
    ("枯楊長出新嫩芽 老夫娶得年輕妻子 無不利",
     28, "九二", "轉述大過卦九二爻辭"),
    # 坎九五: 坎不盈祗既平无咎
    ("坎陷未盈滿 恭敬則平 無過錯",
     29, "九五", "轉述坎卦九五爻辭"),
    # 離九四: 突如其來如焚如死如棄如
    ("突如其來 焚燒般 死亡般 棄絕般",
     30, "九四", "轉述離卦九四爻辭"),
    # 恆九三: 不恆其德或承之羞貞吝
    ("不能恆守其德 或許承受羞辱 堅守正道亦有吝難",
     32, "九三", "轉述恆卦九三爻辭"),
    # 遯六二: 執之用黃牛之革莫之勝說
    ("用黃牛皮繩牢牢執繫 沒有人能解開",
     33, "六二", "轉述遯卦六二爻辭"),
    # 大壯九三: 羝羊觸藩羸其角
    ("公羊觸撞籬笆 角被纏住",
     34, "九三", "轉述大壯卦九三爻辭"),
    # 晉六二: 晉如愁如貞吉受茲介福于其王母
    ("前進卻滿懷愁苦 堅守正道吉利 從王母那裡接受大福",
     35, "六二", "轉述晉卦六二爻辭"),
    # 明夷六五: 箕子之明夷利貞
    ("箕子的明夷之傷 利於堅守正道",
     36, "六五", "轉述明夷卦六五爻辭"),
    # 家人九三: 家人嗃嗃悔厲吉婦子嘻嘻終吝
    ("家人嚴厲管教 有悔有危卻終吉利 婦孺嘻嘻笑 終有吝難",
     37, "九三", "轉述家人卦九三爻辭"),
    # 蹇六二: 王臣蹇蹇匪躬之故
    ("君王的臣子蹇蹇難行 不是為自身緣故",
     39, "六二", "轉述蹇卦六二爻辭"),
    # 解九二: 田獲三狐得黃矢貞吉
    ("田獵捕獲三隻狐 得到黃銅箭矢 堅守正道吉利",
     40, "九二", "轉述解卦九二爻辭"),
    # 損六五: 或益之十朋之龜弗克違元吉
    ("有人贈予價值十朋的靈龜 不能推辭 大吉",
     41, "六五", "轉述損卦六五爻辭"),
    # 益九五: 有孚惠心勿問元吉有孚惠我德
    ("有誠信施惠之心 不必占問 大吉 別人以誠信惠我之德回報",
     42, "九五", "轉述益卦九五爻辭"),
    # 夬九四: 臀无膚其行次且牽羊悔亡聞言不信
    ("臀部無膚 行路躊躇 牽羊則悔亡 聽信人言卻不信從",
     43, "九四", "轉述夬卦九四爻辭"),
    # 姤初六: 繫于金柅貞吉有攸往見凶羸豕孚蹢躅
    ("繫在金屬車閘上 堅守吉利 有所前往見凶 瘦豬確實踟躕不安",
     44, "初六", "轉述姤卦初六爻辭"),
    # 萃六三: 萃如嗟如无攸利往无咎小吝
    ("聚集卻又嘆息 沒有好處 前往無過錯 略有吝難",
     45, "六三", "轉述萃卦六三爻辭"),
    # 升九三: 升虛邑
    ("升進到空虛的城邑",
     46, "九三", "轉述升卦九三爻辭"),
    # 困九五: 劓刖困于赤紱乃徐有說利用祭祀
    ("受劓刑刖刑 困於赤紱 乃漸漸有脫困之機 利於祭祀",
     47, "九五", "轉述困卦九五爻辭"),
    # 井九五: 井洌寒泉食
    ("井水清冽 寒泉可食",
     48, "九五", "轉述井卦九五爻辭"),
    # 革六二: 己日乃革之征吉无咎
    ("到了己日才變革 征行吉利 無過錯",
     49, "六二", "轉述革卦六二爻辭"),
    # 鼎九四: 鼎折足覆公餗其形渥凶
    ("鼎足折斷 傾覆公侯的美食 其狀濕濡 凶",
     50, "九四", "轉述鼎卦九四爻辭"),
    # 震六三: 震蘇蘇震行无眚
    ("震動蘇蘇恐懼 震懼前行則無災眚",
     51, "六三", "轉述震卦六三爻辭"),
    # 艮六五: 艮其輔言有序悔亡
    ("止於其輔頰 說話有條理 悔恨消失",
     52, "六五", "轉述艮卦六五爻辭"),
    # 漸九三: 鴻漸于陸夫征不復婦孕不育凶利禦寇
    ("鴻雁漸進到高地 丈夫出征不歸 婦人懷孕不育 凶 利於抵禦盜寇",
     53, "九三", "轉述漸卦九三爻辭"),
    # 歸妹九四: 歸妹愆期遲歸有時
    ("嫁妹延誤婚期 遲嫁自有其時",
     54, "九四", "轉述歸妹卦九四爻辭"),
    # 豐九三: 豐其沛日中見沫折其右肱无咎
    ("豐大被幡幕遮蔽 日中看見小星 折斷右臂 無過錯",
     55, "九三", "轉述豐卦九三爻辭"),
    # 旅九四: 旅于處得其資斧我心不快
    ("旅途停宿之處 得到資財斧斤 我心卻不快樂",
     56, "九四", "轉述旅卦九四爻辭"),
    # 巽九五: 貞吉悔亡无不利无初有終先庚三日後庚三日吉
    ("堅守吉利悔恨消失 無不利 無初卻有終 先庚三日後庚三日 吉",
     57, "九五", "轉述巽卦九五爻辭"),
    # 兌九二: 孚兌吉悔亡
    ("以誠信使人喜悅 吉利 悔亡",
     58, "九二", "轉述兌卦九二爻辭"),
    # 渙九五: 渙汗其大號渙王居无咎
    ("渙散如汗其大號令 渙散王之居所 無過錯",
     59, "九五", "轉述渙卦九五爻辭"),
    # 節六三: 不節若則嗟若无咎
    ("不能節制 則嘆息嗟怨 無過錯",
     60, "六三", "轉述節卦六三爻辭"),
    # 中孚六四: 月幾望馬匹亡无咎
    ("月亮將近圓滿 馬匹走失 無過錯",
     61, "六四", "轉述中孚卦六四爻辭"),
    # 小過六五: 密雲不雨自我西郊公弋取彼在穴
    ("密雲不雨 從我西郊而起 公侯射取穴中之物",
     62, "六五", "轉述小過卦六五爻辭"),
    # 既濟九三: 高宗伐鬼方三年克之小人勿用
    ("殷高宗征伐鬼方 三年才征服 小人不可用",
     63, "九三", "轉述既濟卦九三爻辭"),
    # 未濟九四: 貞吉悔亡震用伐鬼方三年有賞于大國
    ("堅守吉利悔亡 震動用以征伐鬼方 三年有賞於大國",
     64, "九四", "轉述未濟卦九四爻辭"),
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
