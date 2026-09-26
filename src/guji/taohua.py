"""taohua — 八字桃花运（咸池/红鸾/天喜），纯坐标计算（R111b，D-157b）。

照 huangli.py 神煞层先例：全部规则为传统命理定式，写死可核验；输出是
坐标事实 + 写死说明文字，**不做** LLM 生成解读、不作吉凶断言。固定八字
→ 固定输出，可命令复验。

规则（传统定式）：
- 咸池（桃花）：以年支查三合局 → 桃花支。申子辰→酉、寅午戌→卯、
  巳酉丑→午、亥卯未→子。
- 红鸾：以年支查，红鸾支 = (3 - 年支idx) mod 12（子见卯、丑见寅、
  寅见丑、卯见子、辰见亥、巳见戌、午见酉、未见申、申见未、酉见午、
  戌见巳、亥见辰）。
- 天喜：红鸾的对冲支（红鸾支 +6 mod 12）。
桃花落宫：四柱中哪柱的地支 == 桃花支，即命中该柱。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bazi import Bazi, ZHI

# 咸池（桃花）：年支 → 桃花支（三合局定式，写死可核验）
XIANCHI: dict[str, str] = {
    "申": "酉", "子": "酉", "辰": "酉",
    "寅": "卯", "午": "卯", "戌": "卯",
    "巳": "午", "酉": "午", "丑": "午",
    "亥": "子", "卯": "子", "未": "子",
}

# 四柱名（顺序 = 年/月/日/时）
_PILLARS = ("year", "month", "day", "hour")
_PILLAR_CN = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}

# 桃花落宫的写死说明（非生成文本，照 huangli YIJI 静态表先例）
_PILLAR_MEANING: dict[str, str] = {
    "year": "年柱桃花主早年（少年期的人缘与情窦初开）",
    "month": "月柱桃花主青年（社交圈、同辈中的异性缘）",
    "day": "日柱桃花主配偶宫（婚恋缘分，夫妻关系的信息位）",
    "hour": "时柱桃花主中年后（晚缘、墙外桃花）",
}

_STRENGTH_CN = {"strong": "旺", "mid": "中", "weak": "弱"}


@dataclass
class Taohua:
    year_zhi: str                  # 年支
    peach_zhi: str                 # 桃花支（咸池）
    hit_pillars: list[str]         # 命中桃花支的四柱名（年/月/日/时）
    hongluan: str                  # 红鸾支（年支查）
    hongluan_pillar: list[str]     # 红鸾临四柱中的哪些柱
    tianxi: str                    # 天喜支
    tianxi_pillar: list[str]       # 天喜临四柱中的哪些柱
    strength: str                  # strong / mid / weak
    notes: list[str] = field(default_factory=list)   # 写死说明

    def render(self) -> str:
        parts = [f"年支 {self.year_zhi}，桃花星（咸池）在 {self.peach_zhi}"]
        if self.hit_pillars:
            parts.append("命中" + "、".join(_PILLAR_CN[p] for p in self.hit_pillars))
        else:
            parts.append("四柱地支均未临桃花")
        parts.append(f"红鸾 {self.hongluan}（临 " +
                     ("、".join(_PILLAR_CN[p] for p in self.hongluan_pillar) if self.hongluan_pillar else "无") +
                     f"）· 天喜 {self.tianxi}（临 " +
                     ("、".join(_PILLAR_CN[p] for p in self.tianxi_pillar) if self.tianxi_pillar else "无") + "）")
        parts.append("桃花强度：" + _STRENGTH_CN[self.strength])
        if self.notes:
            parts.append("；".join(self.notes))
        return "　".join(parts)


def _hongluan_zhi(year_zhi: str) -> str:
    """红鸾支 = (3 - 年支idx) mod 12（传统定式，写死可核验）。"""
    return ZHI[(3 - ZHI.index(year_zhi)) % 12]


def compute(b: Bazi) -> Taohua:
    """主入口：八字四柱 → 桃花运分析（纯坐标计算）。"""
    pillars = {k: b.__getattribute__(k)[1] for k in _PILLARS}  # 取各柱地支
    year_zhi = pillars["year"]
    day_zhi = pillars["day"]
    peach = XIANCHI[year_zhi]
    # R2349s（R83-P1）：咸池传统上也可由日支起——只认年支参考时，年柱
    # 自己永远不可能命中 →「strong」构造性稀缺（实测 50 盘 0 强）。
    # 年/日支两个参考位都认，命中任一并集计。
    peach_d = XIANCHI[day_zhi]
    hit = [k for k in _PILLARS if pillars[k] == peach or pillars[k] == peach_d]

    hl = _hongluan_zhi(year_zhi)
    hl_hit = [k for k in _PILLARS if pillars[k] == hl]
    tx = ZHI[(ZHI.index(hl) + 6) % 12]
    tx_hit = [k for k in _PILLARS if pillars[k] == tx]

    if len(hit) >= 2:
        strength = "strong"
    elif len(hit) == 1:
        strength = "mid"
    else:
        strength = "weak"

    notes: list[str] = []
    for k in _PILLARS:
        if k in hit:
            notes.append(_PILLAR_MEANING[k])
    if hl_hit:
        notes.append("红鸾临柱，传统上主婚恋缘分信息")
    if tx_hit:
        notes.append("天喜临柱，传统上主喜庆缘分信息")
    if not notes:
        # R219b（P1-4）：去掉「仅坐标事实，不作断言」免责套话
        notes.append("四柱没有桃花/红鸾/天喜临支——这段缘分信号偏安静，适合先把自己过好")

    return Taohua(
        year_zhi=year_zhi, peach_zhi=peach,
        hit_pillars=hit, hongluan=hl, hongluan_pillar=hl_hit,
        tianxi=tx, tianxi_pillar=tx_hit, strength=strength, notes=notes,
    )


def dayun_hits(b: Bazi, birth_year: int) -> list[dict]:
    """大运桃花应期（R113b，D-159b）：大运干支地支 == 桃花支 → 应期列表。

    复用 `bazi_calc.calc_life` 的大运表（每运 10 年干支 + year_start 约略
    公历年份段起点）。纯坐标计算，固定八字 → 固定应期，可命令复验。
    实测（命令实跑）：1990-05-15 10:00 女命（阳年逆排）大运第 2 运 己卯
    （2003 起）地支卯 == 桃花支卯 → 命中；男命同生日无命中。
    """
    from .bazi_calc import calc_life

    # R2504（B-4）：应期层与 hit_pillars 同口径——年/日支两个参考位
    # 都认（R2349s 只修了命中层，应期漏改；日支桃花用户的全部应期
    # 信号被系统性丢弃，应期本来就低频 ~1/12 每运）。
    peaches = {XIANCHI[b.year[1]], XIANCHI[b.day[1]]}
    life = calc_life(b, birth_year)
    out: list[dict] = []
    for d in life["dayun"]:
        if d["pillar"][1] in peaches:
            out.append({
                "index": d["index"],
                "pillar": d["pillar"],
                "start_age": d["start_age"],
                "end_age": d["end_age"],
                "year_start": d["year_start"],
            })
    return out
