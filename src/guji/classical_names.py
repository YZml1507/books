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
        min_elem = min(counts.items(), key=lambda x: x[1] if x[1] > 0 else float("inf"))[0]
        missing = [min_elem]

    full_names = []

    # 为每个缺行生成名字
    for elem in missing:
        classical_entries = _CLASSICAL_DB.get(elem, [])
        if not classical_entries:
            continue

        # D-004-fix：seed 传入时随机打乱，否则按性别排序
        if seed is not None:
            import random as _random
            _rng = _random.Random(seed)
            selected = classical_entries[:]
            _rng.shuffle(selected)
            selected = selected[:top_n * 2]
        else:
            def _score_entry(entry):
                char = entry.get("字", "")
                if gender == "女" and char in FEMININE_CHARS:
                    return 3
                if gender == "男" and char in MASCULINE_CHARS:
                    return 3
                return 1
            selected = sorted(classical_entries, key=_score_entry, reverse=True)[:top_n * 2]

        for entry in selected[:top_n]:
            char = entry.get("字", "")
            if not char or char in surname:
                continue

            given = char
            name = surname + given
            # 检查名字内是否重复用字
            if len(set(given)) != len(given):
                continue

            full_names.append({
                "full_name": name,
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

    return {
        "surname": surname,
        "five_elements": {"counts": counts, "missing": missing},
        "full_names": unique[:top_n],
        "candidates": [],
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
