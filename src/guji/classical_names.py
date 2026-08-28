"""classical_names.py — 古籍典故取名模块（R217a 新增）。

从《诗经》《楚辞》《论语》《周易》《道德经》等经典中，
按五行缺行检索合适的字，组合成名字 + 附带典故出处。

纪律：
  * 纯计算：选字基于五行规则 + 古籍典故库（写死可核验），不生成新文本。
  * 每个名字附带原句 + 出处 + 意象说明，用户一眼知道"这名字来自哪里"。
  * 确定性：同输入必同输出（sha1 盐抽取，不违反判据 5）。
"""
from __future__ import annotations

import hashlib as _hashlib
import json as _json
import os as _os

from .qiming import CANDIDATE_CHARS, FEMININE_CHARS, MASCULINE_CHARS, _gender_score

# 加载古籍典故库
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_DB_PATH = _os.path.join(_HERE, "classical_names.json")

try:
    with open(_DB_PATH, encoding="utf-8") as _f:
        _CLASSICAL_DB: dict = _json.load(_f) or {}
except Exception:
    _CLASSICAL_DB = {}


def _pick(seq, *salt):
    """从列表中确定性抽取一条。"""
    if not seq:
        return None
    h = _hashlib.sha1("|".join(str(s) for s in salt).encode("utf-8")).hexdigest()
    return seq[int(h[:8], 16) % len(seq)]


def _pick_n(seq, n, *salt):
    """从列表中确定性抽取 n 条不重复项。"""
    if not seq:
        return []
    h = _hashlib.sha1("|".join(str(s) for s in salt).encode("utf-8")).hexdigest()
    result = []
    used = set()
    for i in range(min(n, len(seq))):
        idx = (int(h[:8], 16) + i * 7919) % len(seq)
        while idx in used:
            idx = (idx + 1) % len(seq)
        used.add(idx)
        result.append(seq[idx])
    return result


# ---------------------------------------------------------------------------
# R225b（审查轨 R222a 抓到 `典故库 ∩ FEMININE_CHARS = 0`）：典故库自带的性别
# 倾向表。`qiming.py` 的 FEMININE_CHARS/MASCULINE_CHARS 服务于它自己那套候选池，
# 与本模块 R217a 另建的 75 字典故库是两套独立词汇，交集为 0 → 女性加分从未
# 触发。这里按目标用户（15-25 岁年轻女性）标尺对典故库 75 字逐字归类。
#
# 判定标尺：好念、好写、寓意正向、有质感但不做作。
# ---------------------------------------------------------------------------
# 女性向：清亮、柔和、有画面感，小红书语感里站得住
_FEM_LEAN: frozenset[str] = frozenset({
    # 水
    # R226b-fix：澜 也已删除（九歌·河伯句中无"澜"字，无法坐实）
    "萍", "露", "柔", "涟", "伊", "缨", "润",
    # R226b-fix：泓/汐 因出处不可坐实已从典故库删除，此处同步移除
    "湄", "清", "淑",                          # R225b 新增
    "洄", "泛", "渌",                          # R225b 二批
    # 木
    "华", "采", "棠", "蓁", "苏", "葭", "猗", "衿", "竹", "乔",
    "苓", "苹", "菁", "舜", "楚",              # R225b 新增（"谷"归中性）
    "萧", "蔓", "莞", "茁", "沃", "荷",        # R225b 二批
    # 火
    "彤", "皎", "丹", "仪", "照", "流",
    "昭", "晞", "灿", "阳", "熠",              # R225b 新增
    "灼", "月", "煌",                          # R225b 二批
    # 土
    "悠", "谦", "靖",
    "瑾", "璧", "琇", "璆", "臧",              # R225b 新增
    # R226b-fix：岫 出处含糊已删除
    "宁", "景", "秩", "章",                    # R225b 二批（"阜"归中性）
    # 金
    "琼", "球", "光", "恒",
    "锡", "瑟", "珪", "瑰", "瑶",              # R225b 新增
    "扬", "铃",                                # R225b 二批（"圯"归中性）
})
# 男性向：厚重、刚健、器物与秩序意象
_MASC_LEAN: frozenset[str] = frozenset({
    "梧", "振", "厚", "敦", "德", "陵", "度", "圭", "衡", "充",
    "赫", "曜", "临", "鸣", "离", "明", "利", "诚", "鹤", "顺",
    # R226b-fix：井 因「句」为空已从典故库删除，此处同步移除
    "觉", "善", "琢", "溯", "潜", "粮",
    # R226b：原男性向严重不足（木元素只有 1 个字），男生的契合层凑不满
    # 一批 top_n=8 就会掉到"契合层+中性层"混合，性别倾向被冲淡。
    # 补足到每元素 ≥8，出处同为诗经/尚书。
    "柏", "桢", "析", "梓", "台", "桐", "柯",        # 木
    "旅", "融", "烈", "闻",                          # 火
    "岳", "笃", "本",                                # 土
    "攻", "钦", "干",                                # 金
    "江", "纪", "湛",                                # 水
    # R226b 二批：上一批补完男性向仍只有 19 字（木+土），19//8 = 2 段 →
    # 男生第 3 批回绕（实测 1∩3=5）。按容量公式 3 段需 ≥24，故补到每元素 ≥13。
    "聊", "条", "棣", "樊", "茂",                    # 木
    "冈", "绩", "原",                                # 土
    "常", "炽", "严",                                # 火
    "坚", "钟", "介",                                # 金
    "沔", "楫", "汤",                                # 水
})
# 女性池排除：语义不佳或过于生僻，对年轻女性用户是负分
#   鹜=野鸭 / 茕=孤独 / 玷=玉的瑕疵 / 暴、牢、烂、炉=意象不佳
#   埙=古乐器（生僻）/ 苞=未开花苞（易误读）/ 染=有污染联想
_AVOID_FEM: frozenset[str] = frozenset({
    "鹜", "茕", "玷", "暴", "牢", "烂", "炉", "埙", "苞", "染",
    "萋",   # 「萋萋」在诗里多连着荒芜寂寥用，不适合做名字
})


def generate_classical_names(surname: str, year: int, month: int, day: int,
                              hour: int, gender: str = "女",
                              top_n: int = 8, seed: int | None = None) -> dict:
    """古籍典故取名主函数。

    流程：
      1. 计算八字五行，确定缺行
      2. 从古籍典故库中按缺行检索合适的字
      3. 组合成「姓+字」或「姓+双字」完整名字
      4. 每个名字附带原句 + 出处 + 意象说明

    seed: 随机种子，None=默认确定性输出；传入不同值可得到不同名字组合

    Returns:
        dict: {full_names: [{full_name, given, elements, origin, story, form}, ...]}
    """
    from .qiming import bazi_compute, five_element_counts

    b = bazi_compute(year, month, day, hour, gender)
    counts = five_element_counts(b)
    missing = [e for e, v in counts.items() if v <= 0.001]
    if not missing:
        # R220b（P0-3 第二次返工的真因）：五行都不缺时原来只取**最弱的一个**
        # 元素兜底 → 候选池只有该元素的 15 个字。top_n=8 时 8×2 > 15，
        # 数学上就装不下「连续三批互不相同」，无论洗牌算法怎么改都做不到
        # （前两轮都在算法上打转，其实是池子太小）。
        # 改为取**最弱的两个**元素：池子翻倍到 ~30，segs = 30//8 = 3，
        # 三批互斥才成立。语义上也更合理——五行都不缺的盘本无严格缺行，
        # 补两个最弱的比只补一个更贴近「补不足」的本意。
        _ranked = sorted(counts.items(),
                         key=lambda x: x[1] if x[1] > 0 else float("inf"))
        missing = [e for e, _v in _ranked[:2]]

    full_names = []

    def _score_entry(entry: dict) -> int:
        """性别契合打分。

        R225b 修（审查轨 R222a 抓到）：原实现只查 `qiming.FEMININE_CHARS` /
        `MASCULINE_CHARS`，但那两个字表服务于 qiming.py 自己那套候选池
        （萱/芷/薇/铃/钗…），与本模块 R217a 另建的 75 字典故库**从未对齐**。
        实测 `典故库 ∩ FEMININE_CHARS = 0` —— 女性加分**从来没触发过一次**，
        给女生起名时排序完全无性别倾向；而 `∩ MASCULINE_CHARS = 4`
        （松/沛/渊/澜）反而让男名有加分。目标用户恰恰是年轻女性。
        这也是候选池里「鹜/茕/苞/埙」一直冒头的原因：没有任何机制把
        女性向的字排上来。
        修法：给典故库自带一层性别倾向表（下面 _FEM_LEAN / _MASC_LEAN /
        _AVOID_FEM），与原字表并用（原字表保留，命中仍算分）。
        """
        char = entry.get("字", "")
        # 明确不适合给女生的字：语义不佳或生僻（鹜=野鸭、茕=孤独、玷=玉瑕）
        if gender == "女" and char in _AVOID_FEM:
            return -2
        if gender == "女" and (char in _FEM_LEAN or char in FEMININE_CHARS):
            return 3
        if gender == "男" and (char in _MASC_LEAN or char in MASCULINE_CHARS):
            return 3
        return 1

    # ------------------------------------------------------------------
    # 单字名候选：**先把所有缺行的候选字合并成一个统一池**，再做批次切分。
    #
    # 演进史（两次返工，都因为判据太松）：
    #  · D-004-fix：`random.Random(seed).shuffle(全池)` 再截前 top_n
    #    → 同一个池反复重抽，相邻两批重叠 4/8。
    #  · R219b：改「固定种子洗池 + offset=(seed-1)*top_n 环形取段」
    #    → 只是把同一序列整体平移，绕一圈撞回原窗口。审查轨实测
    #    seed1∩seed3 = 7/8、2∩4 = 7/8、3∩5 = 7/8（**每隔一次几乎全重复**）。
    #    R219b 只报了相邻对（1∩2、2∩3 = 1），正好是唯一看起来正常的位置。
    #  · R220b 第一次返工：改「轮次重洗 + 轮内分段」，但分段做在**每个缺行
    #    元素内部**，而 full_names 是多元素合并结果 → 段内互斥在合并后被破坏，
    #    最坏交集仍有 6/8。
    #
    # 现在：统一池 + 轮次重洗 + 轮内不相交分段。
    #   segs  = 池长 // top_n        每轮能切出的完整批数
    #   round = (seed-1) // segs     第几轮（每轮换一个洗牌种子）
    #   seg   = (seed-1) %  segs     本轮第几段（**段间零交集**）
    # 同一轮内任意两批零重叠；跨轮重洗，顺序与内容都变。
    # ------------------------------------------------------------------
    pool: list[tuple[str, dict]] = []
    for elem in missing:
        for entry in _CLASSICAL_DB.get(elem, []):
            char = entry.get("字", "")
            if not char or char in surname:
                continue
            if len(set(char)) != len(char):       # 名字内不得重复用字
                continue
            # R225b：语义不佳/生僻字**直接不进女性池**。原先只靠 _score_entry
            # 排序压后，但 seed 分支走的是洗牌+分段、完全不看分数 → 这些字
            # 照样上屏（「李鹜」「李茕」就是这么来的）。这里做硬过滤。
            if gender == "女" and char in _AVOID_FEM:
                continue
            pool.append((elem, entry))

    # 同字去重（不同缺行可能命中同一个字，合并后会重复上屏）
    _seen_chars: set[str] = set()
    _uniq: list[tuple[str, dict]] = []
    for elem, entry in pool:
        char = entry.get("字", "")
        if char in _seen_chars:
            continue
        _seen_chars.add(char)
        _uniq.append((elem, entry))
    pool = _uniq

    # R225b：seed 分支原来纯洗牌、**完全不看性别分**，所以女性结果里混进
    # 「陵/粮/顺/敦/厚/振」这类明显男性向的字。改为**先按性别把池分成
    # 契合层 + 中性层，契合层优先**，层内再洗牌分段——既保留"换一批不重复"
    # 的轮次语义，又让性别倾向真正生效。
    if pool:
        _fit = [p for p in pool if _score_entry(p[1]) >= 3]
        _neutral = [p for p in pool if _score_entry(p[1]) < 3]
    else:
        _fit, _neutral = [], []

    _step = max(int(top_n), 1)
    if seed is not None and pool:
        import random as _random
        # 契合层够一批就只在契合层内轮转；不够则契合层打头、中性层补齐
        _base = _fit if len(_fit) >= _step else (_fit + _neutral)
        _segs = max(len(_base) // _step, 1)
        _round = (max(int(seed), 1) - 1) // _segs
        _seg = (max(int(seed), 1) - 1) % _segs
        _shuffled = _base[:]
        _random.Random(_round).shuffle(_shuffled)     # 每轮一个新顺序
        _start = _seg * _step
        selected_pairs = _shuffled[_start:_start + _step] or _shuffled[:_step]
    else:
        selected_pairs = sorted(
            pool, key=lambda p: _score_entry(p[1]), reverse=True)[:_step]

    for elem, entry in selected_pairs:
        given = entry.get("字", "")
        full_names.append({
            "full_name": surname + given,
            "given": given,
            "elements": [elem],
            "origin": entry.get("出处", ""),
            "story": f"「{entry.get('句', '')}」 —— {entry.get('出处', '')}。{entry.get('意象', '')}",
            "form": "single",
        })

    # 如果单字名不够，尝试双字名
    if len(full_names) < top_n:
        for elem in missing:
            classical_entries = _CLASSICAL_DB.get(elem, [])
            if len(classical_entries) < 2:
                continue
            for gender_comp in ["木", "火", "土", "金", "水"]:
                if gender_comp == elem:
                    continue
                comp_entries = _CLASSICAL_DB.get(gender_comp, [])
                if not comp_entries:
                    continue
                for _ in range(3):
                    e1 = _pick(classical_entries, surname, year, month, elem)
                    e2 = _pick(comp_entries, surname, year, month, gender_comp)
                    if not e1 or not e2:
                        continue
                    c1 = e1.get("字", "")
                    c2 = e2.get("字", "")
                    if not c1 or not c2 or c1 == c2:
                        continue
                    if c1 in surname or c2 in surname:
                        continue
                    given = c1 + c2
                    name = surname + given
                    if len(set(given)) != len(given):
                        continue
                    full_names.append({
                        "full_name": name,
                        "given": given,
                        "elements": [elem, gender_comp],
                        "origin": e1.get("出处", "") + " + " + e2.get("出处", ""),
                        "story": f"「{e1.get('句', '')}」「{e2.get('句', '')}」—— 前者取{c1}，后者取{c2}，意象相生。",
                        "form": "double",
                    })
                    if len(full_names) >= top_n:
                        break
            if len(full_names) >= top_n:
                break

    # 去重
    seen = set()
    unique = []
    for n in full_names:
        if n["full_name"] not in seen:
            seen.add(n["full_name"])
            unique.append(n)

    # R221b-fix（审查轨 R221a 目视发现）：`candidates` 自 R217a 建模块起就
    # 写死空列表，前端却一直渲染「单字候选池（0 字）」折叠区 → 一个永远空的
    # 空壳，闸门（只断言 full_names）抓不到，靠 vision 目视才发现。
    # 现在填真数据：候选池就是上面那个统一 pool（已按性别打分排序），
    # 每项给字 + 五行 + 出处，供用户展开挑字。
    # 键名必须是 {char, element, radical, meaning}——前端 app.js:3076-3083
    # 读的就是这四个（radical 位显示"部首"，meaning 位显示释义）。
    # 这里 radical 用出处（典故来源比部首对用户更有用），meaning 用意象。
    _cand = [
        {
            "char": _e.get("字", ""),
            "element": _el,
            "radical": _e.get("出处", ""),
            "meaning": _e.get("意象", ""),
        }
        for _el, _e in sorted(pool, key=lambda p: _score_entry(p[1]),
                              reverse=True)
    ]
    return {
        "surname": surname,
        "five_elements": {"counts": counts, "missing": missing},
        "full_names": unique[:top_n],
        "candidates": _cand,
        "bazi": {"render": b.render()},
        "summary": f"姓氏：{surname}；八字：{b.year} {b.month} {b.day} {b.hour}（日主{b.day_master}）；五行分布：{'、'.join(f'{e}{v:g}' for e, v in counts.items())}；{'缺' + ''.join(missing) if missing else '五行俱全'}",
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    r = generate_classical_names("李", 1990, 5, 15, 12, gender="女")
    for n in r["full_names"]:
        print(f"{n['full_name']} | {n['origin']} | {n['story'][:60]}...")
    print(f"共 {len(r['full_names'])} 个名字")
