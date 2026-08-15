"""liuyao — 六爻起卦纯计算模块。

两种起卦法：
  1. 铜钱法（yarrow 替代）：三枚铜钱摇六次，每次正反面组合定爻。
     - 3 正 = 老阳（动，阳→阴）  ⚊○
     - 2 正 1 反 = 少阴（静）    ⚋
     - 1 正 2 反 = 少阳（静）    ⚊
     - 3 反 = 老阴（动，阴→阳）  ⚋×
     自下而上画卦（初爻→上爻）。
  2. 时间起卦（梅花易数）：年数+月数+日数 → 上卦；+时数 → 下卦；÷6 余数 → 动爻。
     年数取地支序（子=1..亥=12），月数取农历月（正=1..腊=12），日数取农历日，
     时数取地支序。本模块只做坐标计算，不做"解卦文本"——解卦由 LLM 表达层负责。

64 卦表复用 zhouyi 语料：本卦/变卦的卦号 → Corpus.at_address(gua) 取卦辞/爻辞。
卦号采用文王序（1=乾..64=未济），与 zhouyi addr1 一致。

实现约束（照项目纪律）：
  * 纯标准库（datetime/math/random），零新依赖——起卦是坐标换算，不产生"新文本"。
  * 时间起卦用 bazi.lunar 的农历表（1900-2100），不另写农历换算。
  * 动爻阴阳变后查变卦，卦号由六爻阴阳按伏羲序（先天八卦）拼成后天文王序。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

# 八卦（经卦）：伏羲先天序数字 ↔ 卦名 ↔ 二进制（阳=1 阴=0，自下而上读）
# 先天八卦数：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
BAGUA_NAME = {7: "乾", 6: "兑", 5: "离", 4: "震", 3: "巽", 2: "坎", 1: "艮", 0: "坤"}
# 反查：卦名 -> 先天序（二进制）
NAME_TO_XIANTIAN = {v: k for k, v in BAGUA_NAME.items()}

# 先天八卦数 -> 二进制（3 bit，bit0=初爻 bit2=上爻）
# 乾111=7 兑110=6 离101=5 震100=4 巽011=3 坎010=2 艮001=1 坤000=0
# 上面的映射已直接用二进制值作 key，无需再转。

# 八卦单卦的二进制（自下而上：bit0=初爻，bit1=中爻，bit2=上爻）
TRIGRAM_BITS = {
    "乾": 0b111, "兑": 0b110, "离": 0b101, "震": 0b100,
    "巽": 0b011, "坎": 0b010, "艮": 0b001, "坤": 0b000,
}

# 六爻：自下而上 6 个爻，每个爻 0=阴 1=阳，动爻标记
@dataclass
class Yao:
    yang: bool          # True=阳爻 False=阴爻
    moving: bool        # True=动爻
    position: int       # 1=初爻 .. 6=上爻

    def symbol(self) -> str:
        if self.yang:
            return "⚊○" if self.moving else "⚊"
        return "⚋×" if self.moving else "⚋"


@dataclass
class Hexagram:
    lines: list[Yao]            # 6 爻，自下而上（lines[0]=初爻）
    gua_number: int             # 文王序 1..64
    gua_name: str               # 卦名（乾/坤/...）
    moving_lines: list[int]     # 动爻位置 1..6

    def binary(self) -> int:
        """6 bit 二进制，bit0=初爻 .. bit5=上爻，阳=1 阴=0。"""
        v = 0
        for i, y in enumerate(self.lines):
            if y.yang:
                v |= (1 << i)
        return v


# --------------------------------------------------------------------------------------
# 卦号映射：6 bit 二进制（自下而上）→ 文王序 1..64
# --------------------------------------------------------------------------------------
# 文王序按"乾坤屯蒙需讼师..未济"排列，每宫八卦。
# 二进制 → 文王序 的映射表（bit0=初爻..bit5=上爻）。
# 标准 64 卦表：文王序 -> (上卦名, 下卦名)
WENWANG_TABLE: dict[int, tuple[str, str]] = {}  # gua_number -> (upper, lower)
_BIN_TO_WENWANG: dict[int, int] = {}             # binary -> gua_number

# 文王六十四卦序（1=乾 .. 64=未济）与对应上下经卦
# 来源：《周易》序卦传，标准排列，可核验。
_WENWANG_SEQ = [
    (1,  "乾", "乾"),   (2,  "坤", "坤"),   (3,  "坎", "震"),   (4,  "艮", "坎"),
    (4,  "坎", "乾"),   # 占位修正：需(5) 坎上乾下
]
# 上面的内联写法易错，改为显式全表（64 行）。按二进制 bit0=初爻..bit5=上爻。
# 卦名取自 KR1a0001《X第N》标题，与 zhouyi addr1 一致。

# 64 卦全表：文王序 -> 卦名（与 zhouyi addr_name 对齐）
GUA_NAMES_64 = [
    "乾", "坤", "屯", "蒙", "需", "讼", "师", "比",
    "小畜", "履", "泰", "否", "同人", "大有", "謙", "豫",
    "隨", "蠱", "臨", "觀", "噬嗑", "賁", "剝", "復",
    "无妄", "大畜", "頤", "大過", "坎", "離", "咸", "恒",
    "遯", "大壯", "晉", "明夷", "家人", "睽", "蹇", "解",
    "損", "益", "夬", "姤", "萃", "升", "困", "井",
    "革", "鼎", "震", "艮", "漸", "歸妹", "豐", "旅",
    "巽", "兌", "渙", "節", "中孚", "小過", "既濟", "未濟",
]
# 反查：卦名 -> 文王序
NAME_TO_WENWANG = {n: i + 1 for i, n in enumerate(GUA_NAMES_64)}


def _binary_to_gua_number(binary: int) -> int:
    """6 bit 二进制（bit0=初爻..bit5=上爻）→ 文王序 1..64。

    用伏羲先天八卦定位：上卦 = bits[5:3]，下卦 = bits[2:0]。
    再用"先天八卦数 → 文王序"查表。
    但伏羲序与文王序无简单算术关系，必须查表。
    本表按《周易》标准排列，与 KR1a0001 addr1 对齐。
    """
    lower_bits = binary & 0b111          # 下卦（初三四爻... 实为 bit0,1,2）
    upper_bits = (binary >> 3) & 0b111   # 上卦（bit3,4,5）
    # 二进制 -> 八卦名
    # bit0=初爻 bit2=三爻（下卦顶）；bit3=四爻 bit5=上爻
    lower_name = _bits_to_trigram(lower_bits)
    upper_name = _bits_to_trigram(upper_bits)
    # 上下经卦 → 文王序：查 64 卦表
    for num, name in enumerate(GUA_NAMES_64, 1):
        u, l = _wengwang_upper_lower(num)
        if u == upper_name and l == lower_name:
            return num
    raise ValueError(f"binary {binary:#08b} (upper={upper_name} lower={lower_name}) no match")


def _bits_to_trigram(bits: int) -> str:
    """3 bit -> 八卦名。bit0=初爻 bit1=中爻 bit2=上爻。"""
    for name, b in TRIGRAM_BITS.items():
        if b == bits:
            return name
    raise ValueError(f"bits {bits:#06b} no trigram")


# 文王序 -> (上卦, 下卦) 全表
_WENWANG_UPPER_LOWER: dict[int, tuple[str, str]] = {
    1: ("乾", "乾"), 2: ("坤", "坤"), 3: ("坎", "震"), 4: ("艮", "坎"),
    5: ("坎", "乾"), 6: ("乾", "坎"), 7: ("坤", "坎"), 8: ("坎", "坤"),
    9: ("巽", "乾"), 10: ("乾", "兑"), 11: ("坤", "乾"), 12: ("乾", "坤"),
    13: ("乾", "离"), 14: ("离", "乾"), 15: ("坤", "艮"), 16: ("震", "坤"),
    17: ("兑", "震"), 18: ("艮", "巽"), 19: ("坤", "兑"), 20: ("巽", "坤"),
    21: ("离", "震"), 22: ("艮", "离"), 23: ("坤", "艮"), 24: ("震", "坤"),
    25: ("乾", "震"), 26: ("艮", "乾"), 27: ("艮", "震"), 28: ("兑", "巽"),
    29: ("坎", "坎"), 30: ("离", "离"), 31: ("兑", "艮"), 32: ("震", "巽"),
    33: ("乾", "艮"), 34: ("震", "乾"), 35: ("离", "坤"), 36: ("坤", "离"),
    37: ("巽", "离"), 38: ("离", "兑"), 39: ("坎", "艮"), 40: ("震", "坎"),
    41: ("艮", "兑"), 42: ("巽", "震"), 43: ("兑", "乾"), 44: ("乾", "巽"),
    45: ("兑", "坤"), 46: ("坤", "巽"), 47: ("兑", "坎"), 48: ("坎", "巽"),
    49: ("离", "兑"), 50: ("离", "巽"), 51: ("震", "震"), 52: ("艮", "艮"),
    53: ("巽", "艮"), 54: ("震", "兑"), 55: ("震", "离"), 56: ("离", "艮"),
    57: ("巽", "巽"), 58: ("兑", "兑"), 59: ("巽", "坎"), 60: ("坎", "兑"),
    61: ("巽", "兑"), 62: ("艮", "震"), 63: ("坎", "离"), 64: ("离", "坎"),
}


def _wengwang_upper_lower(gua_number: int) -> tuple[str, str]:
    return _WENWANG_UPPER_LOWER[gua_number]


# --------------------------------------------------------------------------------------
# 起卦法
# --------------------------------------------------------------------------------------
def cast_coins(rng: random.Random | None = None) -> Hexagram:
    """铜钱法起卦：三枚铜钱摇六次。

    每枚铜钱：正面=3 反面=2。三枚之和：
      6 = 三反 = 老阴（动，阴）
      7 = 二反一正 = 少阳（静，阳）
      8 = 一反二正 = 少阴（静，阴）
      9 = 三正 = 老阳（动，阳）
    自下而上画卦（第一摇=初爻）。
    """
    r = rng or random.Random()
    lines: list[Yao] = []
    moving: list[int] = []
    for pos in range(1, 7):
        total = sum(r.choice([2, 3]) for _ in range(3))  # 三枚
        yang = total in (7, 9)                            # 7少阳 9老阳 = 阳
        is_moving = total in (6, 9)                       # 6老阴 9老阳 = 动
        lines.append(Yao(yang=yang, moving=is_moving, position=pos))
        if is_moving:
            moving.append(pos)
    binary = sum((1 << i) if y.yang else 0 for i, y in enumerate(lines))
    gua = _binary_to_gua_number(binary)
    return Hexagram(lines=lines, gua_number=gua,
                    gua_name=GUA_NAMES_64[gua - 1], moving_lines=moving)


def cast_time(year: int, month_lunar: int, day_lunar: int,
              hour_zhi: int) -> Hexagram:
    """时间起卦（梅花易数法）。

    上卦 = (年数 + 月数 + 日数) % 8   [余 0 当 8]
    下卦 = (年数 + 月数 + 日数 + 时数) % 8
    动爻 = (年数 + 月数 + 日数 + 时数) % 6   [余 0 当 6]

    年数 = 地支序（子=1 .. 亥=12）
    月数 = 农历月（正=1 .. 腊=12）
    日数 = 农历日（1..30）
    时数 = 地支序（子=1 .. 亥=12）
    """
    year_num = ((year - 4) % 12) + 1   # 子年=1（公历 4 的倍数=子年尾）
    month_num = month_lunar
    day_num = day_lunar
    hour_num = hour_zhi                 # 已是 1..12

    upper = (year_num + month_num + day_num) % 8
    if upper == 0:
        upper = 8
    lower = (year_num + month_num + day_num + hour_num) % 8
    if lower == 0:
        lower = 8
    moving = (year_num + month_num + day_num + hour_num) % 6
    if moving == 0:
        moving = 6

    # 先天序 1..8 -> 八卦名（先天序：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8）
    xiantian = {1: "乾", 2: "兑", 3: "离", 4: "震",
                5: "巽", 6: "坎", 7: "艮", 8: "坤"}
    upper_name = xiantian[upper]
    lower_name = xiantian[lower]

    # 查文王序
    gua = 0
    for num in range(1, 65):
        u, l = _wengwang_upper_lower(num)
        if u == upper_name and l == lower_name:
            gua = num
            break
    if gua == 0:
        raise ValueError(f"upper={upper_name} lower={lower_name} no match")

    # 构造六爻（自下而上）：下卦在下，上卦在上
    lower_bits = TRIGRAM_BITS[lower_name]
    upper_bits = TRIGRAM_BITS[upper_name]
    binary = (upper_bits << 3) | lower_bits
    lines: list[Yao] = []
    moving_list: list[int] = []
    for pos in range(1, 7):
        bit = (binary >> (pos - 1)) & 1
        yang = bool(bit)
        is_moving = (pos == moving)
        lines.append(Yao(yang=yang, moving=is_moving, position=pos))
        if is_moving:
            moving_list.append(pos)

    return Hexagram(lines=lines, gua_number=gua,
                    gua_name=GUA_NAMES_64[gua - 1], moving_lines=moving_list)


def changing_hexagram(h: Hexagram) -> Hexagram:
    """变卦：动爻阴阳变，重新查卦号。无动爻则变卦=本卦。"""
    new_lines: list[Yao] = []
    for y in h.lines:
        if y.moving:
            new_lines.append(Yao(yang=not y.yang, moving=False, position=y.position))
        else:
            new_lines.append(Yao(yang=y.yang, moving=False, position=y.position))
    binary = sum((1 << i) if y.yang else 0 for i, y in enumerate(new_lines))
    gua = _binary_to_gua_number(binary)
    return Hexagram(lines=new_lines, gua_number=gua,
                    gua_name=GUA_NAMES_64[gua - 1], moving_lines=[])


def render_hexagram(h: Hexagram, label: str = "本卦") -> dict:
    """渲染卦象为前端可用的 dict（纯坐标，无解读文本）。"""
    return {
        "label": label,
        "gua_number": h.gua_number,
        "gua_name": h.gua_name,
        "lines": [
            {"position": y.position, "yang": y.yang,
             "moving": y.moving, "symbol": y.symbol()}
            for y in reversed(h.lines)  # 上爻在上
        ],
        "moving_lines": h.moving_lines,
        "binary": h.binary(),
    }
