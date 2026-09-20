"""Retrieval over the 古籍 index, addressable by 卦/爻 and filterable by layer.

The reason this is not a thin wrapper over FTS5: char-segmenting a CJK query turns it
into multiple tokens, and bare multi-token FTS5 MATCH is an implicit AND anywhere in the
document. Searching 見群龍无首 would then match any unit containing those five characters
in any order or position. Quoting the segmented string forces a phrase match, which is
what a 古籍 lookup means. A hit-count test cannot catch this — it must be checked against
the returned text.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from .variants import fold, segment_cjk


# R230a-30（R14-P1-1）+ R230c（R17-P1-3 下沉共享）：简体查询词的保守简→繁
# 重试表。只收单义字（一对一映射，古籍语境不会错）；云/后/余/只/干/几/征/
# 系/台/面/松/咸/曲/谷/卜/丑/于/舍/历/困/蒙/涂/辟/向/须/御/折/钟/朱/致/
# 脏/伙/签 等一对多或简繁同字易错者一律不收——宁可不命中也不给错方向。
# 只对查询词生效，语料侧 fold 不变。web services 与 mcp_server 共用此表。
S2T_RETRY = {p[0]: p[1] for p in (  # noqa: E501 — 数据表，逐对显式
    "潜潛 龙龍 马馬 门門 问問 闻聞 见見 无無 为為 与與 车車 长長 风風 飞飛 鸟鳥 "
    "鱼魚 龟龜 万萬 书書 乐樂 礼禮 学學 师師 处處 变變 数數 断斷 时時 东東 "
    "国國 离離 兑兌 阴陰 阳陽 传傳 说說 记記 经經 义義 圣聖 贞貞 来來 跃躍 "
    "渊淵 饮飲 军軍 众眾 妇婦 户戶 庙廟 泽澤 电電 岁歲 昼晝 进進 动動 穷窮 "
    "达達 败敗 兴興 乱亂 顺順 应應 当當 据據 敌敵 刚剛 险險 丽麗 战戰 劳勞 "
    "润潤 热熱 视視 听聽 觉覺 声聲 语語 辞辭 艺藝 医醫 亿億 忆憶 营營 蝇蠅 "
    "踊踴 忧憂 优優 邮郵 誉譽 园園 员員 圆圓 远遠 愿願 运運 酝醞 杂雜 赃贓 "
    "凿鑿 枣棗 灶竈 斋齋 毡氈 赵趙 证證 郑鄭 织織 职職 纸紙 挚摯 掷擲 滞滯 "
    "种種 烛燭 筑築 庄莊 桩樁 妆妝 壮壯 状狀 准準 浊濁 资資 总總 纵縱 丰豐 "
    "涣渙 节節 济濟 谦謙 随隨 蛊蠱 临臨 观觀 贲賁 剥剝 颐頤 习習 恒恆 晋晉 "
    "损損 渐漸 归歸 术術 药藥 权權 杀殺 满滿 岗崗 体體 肤膚 灵靈 厉厲 厌厭 "
    "县縣 备備 伞傘 举舉 乌烏 买買 卖賣 亲親 亵褻 仅僅 从從 仑侖 仓倉 仪儀 "
    "们們 价價 会會 伟偉 伤傷 伦倫 伪偽 伫佇 剑劍 剂劑 剧劇 劝勸 办辦 务務 "
    "励勵 劲勁 势勢 勋勳 区區 协協 却卻 参參 双雙 发發 叙敘 号號 叹嘆 吃喫 "
    "启啟 吴吳 唤喚 嘱囑 团團 围圍 图圖 场場 坏壞 块塊 坚堅 坛壇 坝壩 坟墳 "
    "坠墜 垒壘 垦墾 垫墊 堑塹 堕墮 墙牆 壳殼 壶壺 头頭 夹夾 夺奪 奋奮 奖獎 "
    "奥奧 妈媽 妩嫵 妪嫗 姗姍 娄婁 娅婭 娆嬈 娇嬌 娈孌 娱娛 娲媧 娴嫻 婴嬰 "
    "婵嬋 婶嬸 媪媼 嫒嬡 嫔嬪 嫘嫘 嫠嫠 嫣嫣 嫦嫦 嫩嫩 嬉嬉 嬷嬤 孀孀 孪孿 "
    "宁寧 宝寶 实實 宠寵 审審 宪憲 宫宮 宽寬 宾賓 寝寢 对對 导導 将將 尔爾 "
    "尘塵 尝嘗 尧堯 尴尷 层層 屉屜 届屆 属屬 屡屢 屿嶼 岂豈 岖嶇 岘峴 岚嵐 "
    "岛島 岭嶺 岳嶽 峡峽 峣嶢 峤嶠 峥崢 峦巒 崭嶄 嵘嶸 嶔嶔 巅巔 巋巋 巍巍").split()
    if len(p) == 2 and p[0] != p[1]}  # len 守卫：手滑拼出三字词即静默丢弃


def s2t_retry(q: str) -> str:
    """按保守映射把简体查询词翻成繁体候选——无变化时返回原串（调用方据此
    决定是否重试与是否披露 hint）。"""
    return "".join(S2T_RETRY.get(ch, ch) for ch in q)


def fts_phrase(q: str) -> str:
    """Segmented, folded, and quoted so FTS5 treats it as an adjacent phrase."""
    seg = segment_cjk(fold(q)).replace('"', '')
    # R228z续：C0 控制字符剥掉——\x00 会让 FTS5 报 "unterminated string"
    # （内部按 C 串截断），别的控制符也不构成任何检索意义。
    seg = "".join(ch for ch in seg if ord(ch) >= 0x20)
    return f'"{seg}"'


def render_citation(*, work_id: str, title: str | None = None,
                    attribution: str | None = None, edition: str | None = None,
                    page_anchor: str | None = None, file: str = "",
                    scheme: str | None = None, addr_name: str | None = None,
                    gua: int | None = None, yao: str | None = None,
                    skipped_chars: int = 0, suspect: str | None = None) -> str:
    """出处渲染的**唯一实现**（`Hit.citation()` 与 bazi_lookup 共用）。

    为什么抽成模块级函数（R179b，D-231b）：`/api/bazi` 的 evidence 走
    `bazi_lookup.retrieve_fast()`，它返回裸 dict 而非 `Hit`，于是响应里
    根本没有 `citation` 键，前端 `esc(ev.citation||'')` 把出处静默渲染成
    空串——原文有了、出处没了（审查轨 R118a-03 实测）。

    修法上**绝不能在 bazi_lookup 里再拼一遍同样的格式**：同一条渲染规则
    存在两份拷贝、对同样的字节给出不同结论，正是 LESSONS.md L-01 记录的
    真实事故（变体折叠表两份拷贝给出相反结论）。故把格式收成本函数，
    两个调用点都指向它。

    每个组成部分都能在源文件里核验，不做任何推断。披露标记（! 表示引文
    非连续、? 表示地址被质量闸门标记）是出处的一部分，不是可选附加——
    隐藏自己省略了什么的出处，是本项目视为最严重的失败模式。
    """
    who = f"{title or work_id}"
    if attribution:
        who += f"（{attribution}）"
    addr = ""
    if gua is not None or addr_name:
        if scheme == "zhouyi":
            nm = f"（{addr_name}）" if addr_name else ""
            addr = f" 卦{gua}{nm}"
            if yao:
                addr += f"·{yao}"
        else:
            # Generic rendering for any other scheme, e.g. "Genesis 1:1".
            parts = [p for p in (addr_name, str(gua) if gua else None) if p]
            addr = " " + " ".join(parts) + (f":{yao}" if yao else "")
    ed = f" [{edition}]" if edition else ""
    marks = ("!" if skipped_chars else "") + ("?" if suspect else "")
    tail = f" {marks}" if marks else ""
    return f"{who}{ed}{addr} @{page_anchor or '?'} ({file}){tail}"


@dataclass
class Hit:
    work_id: str
    title: str | None
    attribution: str | None
    edition: str | None
    page_anchor: str | None
    gua: int | None            # = addr1
    yao: str | None            # = addr2
    layer: str
    text: str
    file: str
    score: float
    scheme: str | None = None
    addr_name: str | None = None
    skipped_chars: int = 0
    suspect: str | None = None

    @property
    def contiguous(self) -> bool:
        """Is `text` a contiguous run of the source, or an envelope with material removed?"""
        return self.skipped_chars == 0

    def disclosure(self) -> str:
        """What the citation does not otherwise say. Empty when there is nothing to disclose.

        Two things a reader cannot see from the text alone, and both were measured rather
        than assumed (probes/probe_disclosure.py, data/catalog/quality_report.json):

          * 54.1% of units skip material inside their own cited range (median 62 chars,
            max 7,388) because same-address runs were merged across an interleaved layer.
            Quoting 經 while silently dropping the 注 between its halves is conventional
            practice, but leaving it undisclosed is not honest citation.
          * 20 units sit at an address the quality gate flagged as damaged. Returning
            KR1a0006 卦61 上九翰青登于天 with no warning presents OCR corruption as text.
        """
        bits = []
        if self.skipped_chars:
            bits.append(f"⚠ 非连续引文：区间内另有 {self.skipped_chars:,} 字未包含"
                        f"（{self.layer}层过滤）")
        if self.suspect:
            bits.append(f"⚠ 该地址已被质量闸门标记：{self.suspect}")
        return "  ".join(bits)

    def citation(self) -> str:
        """Every component is verifiable in the source file; nothing is inferred."""
        return render_citation(
            work_id=self.work_id, title=self.title, attribution=self.attribution,
            edition=self.edition, page_anchor=self.page_anchor, file=self.file,
            scheme=self.scheme, addr_name=self.addr_name, gua=self.gua,
            yao=self.yao, skipped_chars=self.skipped_chars, suspect=self.suspect)


_SELECT = """
SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
       u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
       u.layer, u.text, u.file, u.skipped_chars, u.suspect
FROM unit u JOIN work w ON w.id = u.work_id
"""


class Corpus:
    def __init__(self, db_path: str):
        # R230c（R17-P2-3/P2-6/P2-9）：sqlite3.connect 对缺失路径会顺手建
        # 0B 残库，让后续所有 `os.path.exists` 入口失效——先挡存在性/非空/
        # schema 再开，缺索引的入口得到的是一句人话不是 traceback。
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            raise FileNotFoundError(
                f"索引缺失或为空：{db_path}（先跑 scripts/build_index.py）")
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        if not self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='work'").fetchone():
            self.db.close()
            raise FileNotFoundError(
                f"索引缺表（残库）：{db_path}（先跑 scripts/build_index.py）")

    def close(self):
        self.db.close()

    def stats(self) -> dict:
        q = ("SELECT (SELECT count(*) FROM work) w, (SELECT count(*) FROM unit) u, "
             "(SELECT count(*) FROM unit WHERE addr1 IS NOT NULL) g, "
             "(SELECT count(*) FROM unit WHERE addr2 IS NOT NULL) y")
        r = self.db.execute(q).fetchone()
        return {"works": r["w"], "units": r["u"], "with_gua": r["g"], "with_yao": r["y"]}

    def coverage(self) -> list[sqlite3.Row]:
        return self.db.execute("""
            SELECT w.id, w.title, w.genre, count(u.id) units,
                   sum(u.addr1 IS NOT NULL) addressed,
                   sum(u.addr2 IS NOT NULL) yao_addressed,
                   sum(u.page_anchor IS NOT NULL) anchored
            FROM work w LEFT JOIN unit u ON u.work_id = w.id
            GROUP BY w.id ORDER BY w.genre, w.id""").fetchall()

    def _search_where(self, query: str, gua, yao, layer, work_id, genre,
                      scheme, addr_name, addr1, addr2
                      ) -> tuple[str, list]:
        sql = """
            FROM unit_fts
            JOIN unit u ON u.id = unit_fts.rowid
            JOIN work w ON w.id = u.work_id
            WHERE unit_fts MATCH ?"""
        args: list = [fts_phrase(query)]
        # 'none' 哨兵 = scheme IS NULL（页锚点作品）；None = 不过滤。
        scheme_eq = "none" if scheme is not None and str(scheme).lower() == "none" \
            else scheme
        for col, val in (("u.addr1", gua if gua is not None else addr1),
                         ("u.addr2", yao if yao is not None else addr2),
                         ("u.scheme", scheme_eq), ("u.addr_name", addr_name),
                         ("u.layer", layer),
                         ("u.work_id", work_id), ("w.genre", genre)):
            if val is not None:
                sql += (f" AND {col} IS NULL" if val == "none"
                        else f" AND {col} = ?")
                if val != "none":
                    args.append(val)
        return sql, args

    def search(self, query: str, limit: int = 10, gua: int | None = None,
               yao: str | None = None, layer: str | None = None,
               work_id: str | None = None, genre: str | None = None,
               scheme: str | None = None, addr_name: str | None = None,
               addr1: int | None = None, addr2: str | None = None) -> list[Hit]:
        """`gua`/`yao` are convenience aliases for `addr1`/`addr2` (D-016). They are kept
        because 卦/爻 is what a 周易 caller means, but they carry no special status in
        storage — a Bible caller passes addr_name/addr1/addr2 through the same path."""
        where, args = self._search_where(query, gua, yao, layer, work_id,
                                         genre, scheme, addr_name, addr1, addr2)
        sql = ("""
            SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
                   u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
                   u.layer, u.text, u.file, u.skipped_chars, u.suspect,
                   bm25(unit_fts) AS score """ + where + " ORDER BY score LIMIT ?")
        args.append(limit)
        return [self._hit(r) for r in self.db.execute(sql, args)]

    def search_count(self, query: str, gua=None, yao=None, layer=None,
                     work_id=None, genre=None, scheme=None, addr_name=None,
                     addr1=None, addr2=None) -> int:
        """命中总数（R230a-30：count 原是截断后条数，UI 无法说「共 Y 条」）。"""
        where, args = self._search_where(query, gua, yao, layer, work_id,
                                         genre, scheme, addr_name, addr1, addr2)
        return self.db.execute("SELECT count(*) " + where, args).fetchone()[0]

    def at_address(self, gua: int, yao: str | None = None,
                   layer: str | None = None, limit: int = 50) -> list[Hit]:
        """Every edition's text at one canonical address — no query string involved.
        This is the operation that page anchors cannot do (D-005).

        Restricted to scheme='zhouyi': this method answers 「what does each
        witness read at 卦N·爻」, and 卦 addressing IS the zhouyi scheme. Without
        the filter, a Bible chapter number could collide with a 卦 number
        (Psalms 99 == 卦99), which would make the impossible-address gate
        (eval_g7 卦99) return Psalms text instead of refusing. The collision is
        real, not hypothetical: measured after Douay was ingested with
        scheme='bcv', addr1=chapter.
        """
        sql = _SELECT + " WHERE u.addr1 = ? AND u.scheme = 'zhouyi'"
        args: list = [gua]
        if yao:
            sql += " AND u.addr2 = ?"
            args.append(yao)
        if layer:
            sql += " AND u.layer = ?"
            args.append(layer)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def compare(self, gua: int, yao: str, per_work: int = 2) -> dict[str, list[Hit]]:
        """Group one address's text by work: the shape 'compare the commentators' needs."""
        out: dict[str, list[Hit]] = {}
        for h in self.at_address(gua, yao, limit=400):
            out.setdefault(h.work_id, [])
            if len(out[h.work_id]) < per_work:
                out[h.work_id].append(h)
        return out

    def at_scheme(self, scheme: str | None, addr_name: str | None = None,
                  addr1: int | None = None, addr2: str | None = None,
                  layer: str | None = None, limit: int = 50) -> list[Hit]:
        """Generic address lookup for ANY scheme — 卦/爻 for zhouyi, 卷:章 for bcv,
        幕:場 for play, BOOK:proposition for euclid, etc. `at_address` stays the
        zhouyi-only convenience (D-005: Psalms 99 == 卦99 collision); this is the
        scheme-scoped form used by the web addr view, where the caller declares the
        scheme explicitly so no cross-scheme collision can occur.

        scheme=None / 'none' 表示无编址（页锚点）作品——R230a-33 前 SCHEME_LABELS
        靠字面键 'None' 防呆，传字符串 'None' 会变成查 scheme='None' 恒零命中。
        """
        if scheme is None or str(scheme).lower() == "none":
            sql = _SELECT + " WHERE u.scheme IS NULL"
            args: list = []
        else:
            sql = _SELECT + " WHERE u.scheme = ?"
            args = [scheme]
        for col, val in (("u.addr_name", addr_name), ("u.addr1", addr1),
                         ("u.addr2", addr2), ("u.layer", layer)):
            if val is not None:
                sql += f" AND {col} = ?"
                args.append(val)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def units_by_id(self, unit_ids: list[int], limit: int = 50) -> list[Hit]:
        """Fetch units by primary key. The link table speaks unit ids (G4), and this is
        the read-back for a hop: `link.dst_unit` -> the unit it points at."""
        if not unit_ids:
            return []
        ids = [int(i) for i in unit_ids[:limit]]
        ph = ",".join("?" * len(ids))
        sql = _SELECT + f" WHERE u.id IN ({ph}) ORDER BY u.work_id, u.raw_start"
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, ids)]

    @staticmethod
    def _hit(r: sqlite3.Row, score: float | None = None) -> Hit:
        # Explicit field names: positional construction silently misassigns if the
        # SELECT column order is ever edited.
        return Hit(
            work_id=r["work_id"], title=r["title"], attribution=r["attribution"],
            edition=r["edition"], page_anchor=r["page_anchor"], gua=r["gua"],
            yao=r["yao"], layer=r["layer"], text=r["text"], file=r["file"],
            score=score if score is not None else r["score"],
            scheme=r["scheme"], addr_name=r["addr_name"],
            skipped_chars=r["skipped_chars"] or 0, suspect=r["suspect"],
        )
