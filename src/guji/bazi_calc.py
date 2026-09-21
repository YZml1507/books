"""bazi_calc — 八字运算层（纯标准库，纯坐标计算，不产生新文本）。

在排盘（bazi.compute 的四柱坐标）之上做结构化"运算"：
  * 十神关系：日主 vs 四柱天干 / 地支藏干主气
  * 五行统计：四柱天干 + 藏干主气的五行分布、缺行、偏旺
  * 地支关系：命局内 六冲/六合/三合(半合)/相刑/相害
  * 流日/流时：问事日期时间的当日干支、流时干支，与命局天干十神、
    地支冲合刑害比对（day_ganzhi / hour_ganzhi 复用 bazi.py，已验证）

红线（WEB_PLAN_v2 §3/§8）：
  * 全部是写死的通行命理规则表 + 坐标计算；summary 是模板拼接，逐字段
    与运算结果一致，可核验；不产生"新文本"。
  * 零第三方依赖（只用标准库 + bazi.py 的干支函数）。
  * 所有输出都是坐标/事实，不带倾向性断言。

规则表（通行命理常识，写死可核对）：
  * 天干五行：甲乙木 丙丁火 戊己土 庚辛金 壬癸水
  * 地支五行与藏干（本气/中气/余气）：
      子(癸) 丑(己癸辛) 寅(甲丙戊) 卯(乙) 辰(戊乙癸) 巳(丙庚戊)
      午(丁己) 未(己丁乙) 申(庚壬戊) 酉(辛) 戌(戊辛丁) 亥(壬甲)
  * 十神以日干为我：同我=比肩/劫财，生我=正印/偏印，我生=食神/伤官，
    克我=正官/七杀，我克=正财/偏财（阴阳分偏正）。
  * 六冲：子午 丑未 寅申 卯酉 辰戌 巳亥
  * 六合：子丑 寅亥 卯戌 辰酉 巳申 午未
  * 三合：申子辰(水) 亥卯未(木) 寅午戌(火) 巳酉丑(金)；三支齐为三合，
    任两支为半合
  * 相刑：子卯 寅巳申 丑戌未 辰午酉亥自刑
  * 相害：子未 丑午 寅巳 卯辰 申亥 酉戌
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .bazi import Bazi, day_ganzhi, hour_ganzhi

# --------------------------------------------------------------------------------------
# 基础规则表（写死、可核对）
# --------------------------------------------------------------------------------------
GAN_ELEM = {"甲": "木", "乙": "木", "丙": "火", "丁": "火",
            "戊": "土", "己": "土", "庚": "金", "辛": "金",
            "壬": "水", "癸": "水"}
GAN_YINYANG = {"甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
               "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴"}

# 地支藏干：(天干, 权重) — 本气>中气>余气
ZHI_HIDDEN = {
    "子": [("癸", 1.0)],
    "丑": [("己", 0.6), ("癸", 0.3), ("辛", 0.1)],
    "寅": [("甲", 0.6), ("丙", 0.3), ("戊", 0.1)],
    "卯": [("乙", 1.0)],
    "辰": [("戊", 0.6), ("乙", 0.3), ("癸", 0.1)],
    "巳": [("丙", 0.6), ("庚", 0.3), ("戊", 0.1)],
    "午": [("丁", 0.7), ("己", 0.3)],
    "未": [("己", 0.6), ("丁", 0.3), ("乙", 0.1)],
    "申": [("庚", 0.6), ("壬", 0.3), ("戊", 0.1)],
    "酉": [("辛", 1.0)],
    "戌": [("戊", 0.6), ("辛", 0.3), ("丁", 0.1)],
    "亥": [("壬", 0.7), ("甲", 0.3)],
}

SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # 我生
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}       # 我克

# 六冲（双向）：子午 丑未 寅申 卯酉 辰戌 巳亥
CHONG = {"子": "午", "午": "子", "丑": "未", "未": "丑",
         "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
         "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
# 六合（双向）：子丑 寅亥 卯戌 辰酉 巳申 午未
LIU_HE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
          "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}
# 三合局（组 -> 五行）
SAN_HE = [("申子辰", "水"), ("亥卯未", "木"), ("寅午戌", "火"), ("巳酉丑", "金")]
# 相刑（无序对）+ 自刑地支
XING = [("子", "卯"), ("寅", "巳"), ("巳", "申"), ("寅", "申"),
        ("丑", "戌"), ("戌", "未"), ("丑", "未")]
ZI_XING = {"辰", "午", "酉", "亥"}
# 相害（双向）：子未 丑午 寅巳 卯辰 申亥 酉戌
XIANG_HAI = {"子": "未", "丑": "午", "寅": "巳", "卯": "辰",
             "巳": "寅", "午": "丑", "未": "子", "辰": "卯",
             "申": "亥", "酉": "戌", "亥": "申", "戌": "酉"}

POS_NAMES = {0: "年", 1: "月", 2: "日", 3: "时"}


# --------------------------------------------------------------------------------------
# 十神
# --------------------------------------------------------------------------------------
def ten_god(day_master: str, gan: str) -> str:
    """日主 day_master 见干 gan 的十神。

    阴阳分偏正（同我者：同阴阳=比肩，异=劫财；我克者：同=偏财，异=正财；
    克我者：同=七杀，异=正官；生我者：同=偏印，异=正印；我生者：同=食神，异=伤官）。
    """
    me, other = GAN_ELEM[day_master], GAN_ELEM[gan]
    same = GAN_YINYANG[day_master] == GAN_YINYANG[gan]
    if me == other:                      # 同我
        return "比肩" if same else "劫财"
    if SHENG[other] == me:               # 生我（印）
        return "偏印" if same else "正印"
    if SHENG[me] == other:               # 我生（食伤）
        return "食神" if same else "伤官"
    if KE[other] == me:                  # 克我（官杀）
        return "七杀" if same else "正官"
    return "偏财" if same else "正财"    # 我克（财）


def _god_basis(day_master: str, gan: str) -> str:
    """十神依据一句话（坐标可核验）。"""
    me, other = GAN_ELEM[day_master], GAN_ELEM[gan]
    same = "同阴阳" if GAN_YINYANG[day_master] == GAN_YINYANG[gan] else "异阴阳"
    if me == other:
        return f"{day_master}{gan}同为{me}，{same}"
    if SHENG[other] == me:
        return f"{gan}生{day_master}（{other}生{me}），{same}"
    if SHENG[me] == other:
        return f"{day_master}生{gan}（{me}生{other}），{same}"
    if KE[other] == me:
        return f"{gan}克{day_master}（{other}克{me}），{same}"
    return f"{day_master}克{gan}（{me}克{other}），{same}"


# --------------------------------------------------------------------------------------
# 五行统计
# --------------------------------------------------------------------------------------
def five_element_counts(b: Bazi) -> dict[str, float]:
    """四柱五行权重：天干各 1.0 + 地支藏干按权重（本气 .6/.7 中气 .3 余气 .1）。"""
    counts = {e: 0.0 for e in ("木", "火", "土", "金", "水")}
    for pillar in (b.year, b.month, b.day, b.hour):
        counts[GAN_ELEM[pillar[0]]] += 1.0          # 天干
        for gan, w in ZHI_HIDDEN[pillar[1]]:
            counts[GAN_ELEM[gan]] += w              # 藏干
    return {e: round(v, 2) for e, v in counts.items()}


# --------------------------------------------------------------------------------------
# 地支关系
# --------------------------------------------------------------------------------------
def _rel_pair(z1: str, z2: str) -> tuple[str, str] | None:
    """两支关系：(type, note)。无关系返回 None。"""
    if CHONG.get(z1) == z2:
        return "六冲", f"{z1}{z2}冲"
    if LIU_HE.get(z1) == z2:
        return "六合", f"{z1}{z2}合"
    if (z1, z2) in XING or (z2, z1) in XING:
        return "相刑", f"{z1}{z2}刑"
    if XIANG_HAI.get(z1) == z2:
        return "相害", f"{z1}{z2}害"
    return None


def _san_he(zhis: list[str]) -> list[dict]:
    """三合/半合检测：三支齐=三合；任两支=半合（子辰 等）。"""
    out = []
    for group, elem in SAN_HE:
        have = [z for z in group if z in zhis]
        if len(have) == 3:
            out.append({"type": "三合", "note": f"{group}三合{elem}局"})
        elif len(have) == 2:
            out.append({"type": "半合", "note": f"{''.join(have)}半合{elem}局"})
    return out


def _zi_xing(zhis: list[str]) -> list[dict]:
    """自刑：辰/午/酉/亥 在命局中出现 ≥2 次。"""
    out = []
    seen = {}
    for z in zhis:
        if z in ZI_XING:
            seen[z] = seen.get(z, 0) + 1
    for z, n in seen.items():
        if n >= 2:
            out.append({"type": "自刑", "note": f"{z}{z}自刑"})
    return out


# --------------------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------------------
def calc(b: Bazi, ask_date: str | None = None,
         ask_hour: int | None = None) -> dict:
    """排盘坐标 -> 结构化运算事实。

    ask_date: "YYYY-MM-DD"，缺省为今天（本地日期）；流日/流时与命局比对。
    ask_hour: 0-23，缺省不比对流时。

    返回（WEB_PLAN_v2 §3.2 契约）：
      ten_gods / five_elements / relations / day_luck / summary
    """
    pillars = [b.year, b.month, b.day, b.hour]
    day_master = b.day_master

    # --- 十神：四柱天干 + 四支藏干主气 ---
    ten_gods = []
    for i, p in enumerate(pillars):
        pos = POS_NAMES[i]
        ten_gods.append({
            "pos": f"{pos}干", "gan": p[0],
            "god": ten_god(day_master, p[0]),
            "basis": _god_basis(day_master, p[0]),
        })
    for i, p in enumerate(pillars):
        pos = POS_NAMES[i]
        hidden = ZHI_HIDDEN[p[1]]
        main_gan = hidden[0][0]
        ten_gods.append({
            "pos": f"{pos}支藏干", "gan": main_gan,
            "god": ten_god(day_master, main_gan),
            "basis": f"{p[1]}藏{''.join(g for g, _ in hidden)}，主气{main_gan}："
                     + _god_basis(day_master, main_gan),
        })

    # --- 五行统计 ---
    counts = five_element_counts(b)
    missing = [e for e, v in counts.items() if v <= 0.001]
    mx = max(counts.values())
    # R230a-7（R13-P1-1）：并列最高 = 均势不是独旺——此前木火金水同分时
    # 四行全标「偏旺」（抽样约 4.7% 的盘踩到）。并列放 strong_tied，
    # strong 只保留唯一最高者。
    _tops = sorted(e for e, v in counts.items() if abs(v - mx) < 0.001)
    strong = _tops if len(_tops) == 1 else []
    strong_tied = _tops if len(_tops) > 1 else []

    # --- 地支关系：命局内两两 + 三合/自刑 ---
    zhis = [p[1] for p in pillars]
    relations = []
    for i in range(4):
        for j in range(i + 1, 4):
            r = _rel_pair(zhis[i], zhis[j])
            if r:
                relations.append({
                    "type": r[0],
                    "a": f"{POS_NAMES[i]}支{zhis[i]}",
                    "b": f"{POS_NAMES[j]}支{zhis[j]}",
                    "note": r[1],
                })
    for r in _san_he(zhis):
        relations.append({"type": r["type"], "a": "四柱", "b": "地支", "note": r["note"]})
    for r in _zi_xing(zhis):
        relations.append({"type": r["type"], "a": "四柱", "b": "地支", "note": r["note"]})

    # --- 流日 / 流时 ---
    if ask_date:
        y, m, d = (int(x) for x in ask_date.split("-"))
        dt = datetime(y, m, d, 12, 0, 0)
        dgz, _ = day_ganzhi(dt)
    else:
        today = date.today()
        dgz, _ = day_ganzhi(datetime(today.year, today.month, today.day, 12, 0, 0))
    day_rel = ten_god(day_master, dgz[0])
    day_branch = []
    for i, z in enumerate(zhis):
        r = _rel_pair(dgz[1], z)
        if r:
            day_branch.append({"pos": f"{POS_NAMES[i]}支{z}", "type": r[0], "note": r[1]})
    day_luck = {
        "day_ganzhi": dgz,
        "day_master_rel": f"{dgz[0]}为日主{day_master}之{day_rel}",
        "day_branch_rels": day_branch,
        "hour_ganzhi": None, "hour_master_rel": None, "hour_branch_rels": [],
    }
    if ask_hour is not None:
        hgz = hour_ganzhi(dgz[0], ask_hour)
        hrel = ten_god(day_master, hgz[0])
        hbranch = []
        for i, z in enumerate(zhis):
            r = _rel_pair(hgz[1], z)
            if r:
                hbranch.append({"pos": f"{POS_NAMES[i]}支{z}", "type": r[0], "note": r[1]})
        day_luck.update({
            "hour_ganzhi": hgz,
            "hour_master_rel": f"{hgz[0]}为日主{day_master}之{hrel}",
            "hour_branch_rels": hbranch,
        })

    # --- summary：模板拼接（可核验，非 LLM 文本）---
    parts = [f"日主{day_master}（{GAN_ELEM[day_master]}），四柱：{b.year} {b.month} {b.day} {b.hour}"]
    dist = "、".join(f"{e}{v:g}" for e, v in counts.items())
    parts.append(f"五行分布：{dist}")
    if missing:
        parts.append(f"缺{''.join(missing)}")
    if strong:
        parts.append(f"{'、'.join(strong)}偏旺")
    elif strong_tied:
        parts.append(f"{'、'.join(strong_tied)}均势（无一行独大）")
    if relations:
        parts.append("地支关系：" + "；".join(f"{r['note']}" for r in relations))
    if day_branch or day_luck["day_master_rel"]:
        dl = f"今日{dgz}：{day_luck['day_master_rel']}"
        if day_branch:
            dl += "；" + "；".join(f"{r['pos']}{r['note'].replace('合', '合')}"
                                   for r in day_branch)
        parts.append(dl)
    if day_luck.get("hour_ganzhi"):
        hl = f"流时{day_luck['hour_ganzhi']}：{day_luck['hour_master_rel']}"
        if day_luck["hour_branch_rels"]:
            hl += "；" + "；".join(f"{r['pos']}{r['note']}"
                                   for r in day_luck["hour_branch_rels"])
        parts.append(hl)

    return {
        "ten_gods": ten_gods,
        "five_elements": {"counts": counts, "missing": missing,
                           "strong": strong, "strong_tied": strong_tied},
        "relations": relations,
        "day_luck": day_luck,
        "summary": "。".join(parts) + "。",
    }


def calc_range(b: Bazi, start_date: str, end_date: str,
               ask_hour: int | None = None) -> dict:
    """日期范围：逐日流日/流时与命局的冲合刑害关系（纯坐标，可核验）。

    start_date / end_date: "YYYY-MM-DD"，闭区间，跨度 ≤ 31 天（防爆）。
    输出 {start, end, days:[{date, day_ganzhi, day_master_rel,
    day_branch_rels, hour_ganzhi?, hour_master_rel?, hour_branch_rels?}],
    summary}。
    """
    d0 = datetime.strptime(start_date, "%Y-%m-%d")
    d1 = datetime.strptime(end_date, "%Y-%m-%d")
    if d1 < d0:
        raise ValueError("结束的日子要排在开始之后哦")
    span = (d1 - d0).days
    if span > 31:
        raise ValueError("一次最多看 31 天，分几段查更清楚")
    pillars = [b.year, b.month, b.day, b.hour]
    zhis = [p[1] for p in pillars]
    day_master = b.day_master
    days = []
    cur = d0
    while cur <= d1:
        dgz, _ = day_ganzhi(cur)
        rel = ten_god(day_master, dgz[0])
        branch = []
        for i, z in enumerate(zhis):
            r = _rel_pair(dgz[1], z)
            if r:
                branch.append({"pos": f"{POS_NAMES[i]}支{z}", "type": r[0],
                               "note": r[1]})
        item = {
            "date": cur.strftime("%Y-%m-%d"),
            "day_ganzhi": dgz,
            "day_master_rel": f"{dgz[0]}为日主{day_master}之{rel}",
            "day_branch_rels": branch,
        }
        if ask_hour is not None:
            hgz = hour_ganzhi(dgz[0], ask_hour)
            hrel = ten_god(day_master, hgz[0])
            hbranch = []
            for i, z in enumerate(zhis):
                r = _rel_pair(hgz[1], z)
                if r:
                    hbranch.append({"pos": f"{POS_NAMES[i]}支{z}", "type": r[0],
                                    "note": r[1]})
            item.update({
                "hour_ganzhi": hgz,
                "hour_master_rel": f"{hgz[0]}为日主{day_master}之{hrel}",
                "hour_branch_rels": hbranch,
            })
        days.append(item)
        cur += timedelta(days=1)
    summary = (f"日主{day_master}，范围 {start_date}~{end_date} 共 {len(days)} 天"
               f"（{start_date} 为 {days[0]['day_ganzhi']}，"
               f"{end_date} 为 {days[-1]['day_ganzhi']}），逐日流日关系见上。")
    return {"start": start_date, "end": end_date, "days": days, "summary": summary}


def calc_life(b: Bazi, birth_year: int) -> dict:
    """生平模式：大运表（起运岁数 + 每运 10 年干支 + 与日主十神）+ 流年概览。

    birth_year: 出生公历年份（用于把大运段换算成约略公历年份段）。
    输出 {qi_yun_age, dayun:[{index, start_age, end_age, pillar, gan_rel,
    year_start}], summary}。纯坐标计算（大运干支已在 bazi.meta 算好）。
    """
    day_master = b.day_master
    qi = b.meta.get("qi_yun_age")
    pillars = b.meta.get("dayun_pillars") or []
    dayun = []
    for k, p in enumerate(pillars):
        start_age = (qi or 0) + 10 * k
        end_age = start_age + 10
        dayun.append({
            "index": k + 1,
            "start_age": round(start_age, 1),
            "end_age": round(end_age, 1),
            "pillar": p,
            "gan_rel": ten_god(day_master, p[0]),
            # R230h（R20-F10）：int() 截断与 start_age 的 round(1) 展示错位
            # ——「4.9岁起运→1994」读着像 1995；按四舍五入进位贴展示口径。
            "year_start": birth_year + int(round(start_age)),  # 约略公历年份段起点
        })
    parts = [f"日主{day_master}，大运{'顺' if b.dayun_dir == '顺' else '逆'}排，"
             f"约 {round(qi, 1) if qi is not None else '?'} 岁起运"]
    parts.append("；".join(f"{d['pillar']}({d['start_age']}~{d['end_age']}岁)"
                           for d in dayun))
    return {
        "qi_yun_age": round(qi, 1) if qi is not None else None,
        "dayun": dayun,
        "summary": "。".join(parts) + "。",
    }


if __name__ == "__main__":
    # 自检：文档 §7.1 已知八字手工核对
    # 找一个庚辰日出生的人：日主庚，年干甲 → 偏财；子午冲案例另造。
    b = Bazi(year="甲子", month="丙寅", day="庚辰", hour="丙子",
             day_master="庚", nayin=["海中金", "炉中火", "白蜡金", "涧下水"],
             dayun_dir="顺")
    c = calc(b, ask_date="2024-05-01", ask_hour=10)
    import json
    print(json.dumps(c, ensure_ascii=False, indent=1))
    # 断言：庚 见 甲 = 偏财
    assert ten_god("庚", "甲") == "偏财", ten_god("庚", "甲")
    # 庚 见 丙 = 七杀（丙火克庚金，同阳）
    assert ten_god("庚", "丙") == "七杀", ten_god("庚", "丙")
    # 庚 见 壬 = 食神（庚生壬，同阳）
    assert ten_god("庚", "壬") == "食神", ten_god("庚", "壬")
    print("十神断言 OK")
