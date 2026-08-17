"""hehun — 八字合婚（R121b，D-167b）：两人八字的六冲/六合/日主五行/桃花支比较。

纯坐标计算，规则写死可核验，不生成解读文本、不作吉凶断言（照 R111b
桃花运 / R112b 塔罗先例：功能静态数据非语料，不触碰"生成文本入库"红线）。
固定两人生日 → 固定输出，可命令复验。

比较维度（传统定式，写死表）：
- 年支六冲：子午、丑未、寅申、卯酉、辰戌、巳亥
- 年支六合：子丑、寅亥、卯戌、辰酉、巳申、午未
- 日主五行：男/女日干五行（木火土金水）
- 桃花支重叠：复用 taohua 咸池（年支三合局查桃花支）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bazi import Bazi, GAN
from .bazi_calc import ten_god
from .taohua import compute as taohua_compute

# 年支六冲（传统定式，写死可核验）
SIX_CLASH: dict[str, str] = {
    "子": "午", "午": "子", "丑": "未", "未": "丑",
    "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
    "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳",
}
# 年支六合
SIX_COMBINE: dict[str, str] = {
    "子": "丑", "丑": "子", "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳", "午": "未", "未": "午",
}
# 天干五行
GAN_ELEMENT: dict[str, str] = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
# 五行相生（传统定式）：木→火→土→金→水→木
_SHENG: dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 写死说明文字（非生成，照 huangli YIJI 先例）
_NOTE_CLASH = "年支六冲：传统上主两人生肖冲克，需磨合（仅坐标事实，不作断言）"
_NOTE_COMBINE = "年支六合：传统上主生肖相合，较有缘分（仅坐标事实，不作断言）"
_NOTE_DAY_WX = "日主五行相生：传统上主五行流通较好（仅坐标事实，不作断言）"
_NOTE_DAY_WX_CLASH = "日主五行相克：传统上主五行碰撞，需看具体组合（仅坐标事实，不作断言）"
_NOTE_PEACH = "桃花支重叠：两人桃花支相同，传统上主缘分信息同频（仅坐标事实，不作断言）"


@dataclass
class Hehun:
    year_zhi_a: str                  # 男年支
    year_zhi_b: str                  # 女年支
    clash: bool                      # 年支六冲
    combine: bool                    # 年支六合
    day_gz_a: str                    # 男日柱
    day_gz_b: str                    # 女日柱
    day_wx_a: str                    # 男日主五行
    day_wx_b: str                    # 女日主五行
    day_wx_sheng: bool               # 日主五行相生（a 生 b 或 b 生 a）
    peach_a: str                     # 男桃花支
    peach_b: str                     # 女桃花支
    peach_same: bool                 # 桃花支重叠
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [f"男 {self.day_gz_a}（日主{self.day_wx_a}）· 女 {self.day_gz_b}（日主{self.day_wx_b}）"]
        parts.append(f"年支 {self.year_zhi_a}/{self.year_zhi_b}：" +
                     ("六冲" if self.clash else ("六合" if self.combine else "无冲合")))
        parts.append(f"日主五行：" + ("相生" if self.day_wx_sheng else "相克"))
        parts.append(f"桃花支 {self.peach_a}/{self.peach_b}：" + ("重叠" if self.peach_same else "不同"))
        if self.notes:
            parts.append("；".join(self.notes))
        return "　".join(parts)


def compute(b_a: Bazi, b_b: Bazi) -> Hehun:
    """主入口：两人八字 → 合婚坐标比较（纯计算）。"""
    za, zb = b_a.year[1], b_b.year[1]
    clash = SIX_CLASH.get(za) == zb
    combine = SIX_COMBINE.get(za) == zb
    wxa, wxb = GAN_ELEMENT[b_a.day[0]], GAN_ELEMENT[b_b.day[0]]
    sheng = _SHENG.get(wxa) == wxb or _SHENG.get(wxb) == wxa
    ta, tb = taohua_compute(b_a), taohua_compute(b_b)
    pa, pb = ta.peach_zhi, tb.peach_zhi
    peach_same = pa == pb

    notes: list[str] = []
    if clash:
        notes.append(_NOTE_CLASH)
    if combine:
        notes.append(_NOTE_COMBINE)
    notes.append(_NOTE_DAY_WX if sheng else _NOTE_DAY_WX_CLASH)
    if peach_same:
        notes.append(_NOTE_PEACH)
    if not notes:
        notes.append("无六冲/六合/桃花重叠，仅坐标事实（不作断言）")

    return Hehun(
        year_zhi_a=za, year_zhi_b=zb, clash=clash, combine=combine,
        day_gz_a=b_a.day, day_gz_b=b_b.day,
        day_wx_a=wxa, day_wx_b=wxb, day_wx_sheng=sheng,
        peach_a=pa, peach_b=pb, peach_same=peach_same, notes=notes,
    )
