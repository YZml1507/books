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
        char = entry.get("字", "")
        if gender == "女" and char in FEMININE_CHARS:
            return 3
        if gender == "男" and char in MASCULINE_CHARS:
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

    _step = max(int(top_n), 1)
    if seed is not None and pool:
        import random as _random
        _segs = max(len(pool) // _step, 1)
        _round = (max(int(seed), 1) - 1) // _segs
        _seg = (max(int(seed), 1) - 1) % _segs
        _random.Random(_round).shuffle(pool)          # 每轮一个新顺序
        _start = _seg * _step
        selected_pairs = pool[_start:_start + _step] or pool[:_step]
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
