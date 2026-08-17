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
    peach = XIANCHI[year_zhi]
    hit = [k for k in _PILLARS if pillars[k] == peach]

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
        notes.append("四柱无桃花/红鸾/天喜临支，缘分信息平淡（仅坐标事实，不作断言）")

    return Taohua(
        year_zhi=year_zhi, peach_zhi=peach,
        hit_pillars=hit, hongluan=hl, hongluan_pillar=hl_hit,
        tianxi=tx, tianxi_pillar=tx_hit, strength=strength, notes=notes,
    )
