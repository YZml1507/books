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
from dataclasses import dataclass

# 八卦（经卦）：伏羲先天序数字 ↔ 卦名 ↔ 二进制（阳=1 阴=0，自下而上读）
# 先天八卦数：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
# 伏羲先天八卦二进制（bit0=初爻=下爻，bit2=上爻）：
#   乾111 兑011(上爻阴) 离101(中爻阴) 震001(只有下爻阳) 巽110(只有下爻阴) 坎010 艮100(只有上爻阳) 坤000
# 注：阳在初=震，阳在中=坎，阳在上=艮；阴在初=巽，阴在中=离，阴在上=兑（伏羲先天序）
BAGUA_NAME = {7: "乾", 3: "兑", 5: "离", 1: "震", 6: "巽", 2: "坎", 4: "艮", 0: "坤"}
# 反查：卦名 -> 先天序（二进制）
NAME_TO_XIANTIAN = {v: k for k, v in BAGUA_NAME.items()}

# 先天八卦数 -> 二进制（3 bit，bit0=初爻 bit2=上爻）
# 乾111=7 兑011=3 离101=5 震001=1 巽110=6 坎010=2 艮100=4 坤000=0
# 上面的映射已直接用二进制值作 key，无需再转。

# 八卦单卦的二进制（自下而上：bit0=初爻，bit1=中爻，bit2=上爻）
# 伏羲先天八卦正确序（与 KR1a0001 本地语料「震下坎上《屯》」「巽下乾上《姤》」对照核实）
TRIGRAM_BITS = {
    "乾": 0b111, "兑": 0b011, "离": 0b101, "震": 0b001,
    "巽": 0b110, "坎": 0b010, "艮": 0b100, "坤": 0b000,
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
    21: ("离", "震"), 22: ("艮", "离"), 23: ("艮", "坤"), 24: ("坤", "震"),
    25: ("乾", "震"), 26: ("艮", "乾"), 27: ("艮", "震"), 28: ("兑", "巽"),
    29: ("坎", "坎"), 30: ("离", "离"), 31: ("兑", "艮"), 32: ("震", "巽"),
    33: ("乾", "艮"), 34: ("震", "乾"), 35: ("离", "坤"), 36: ("坤", "离"),
    37: ("巽", "离"), 38: ("离", "兑"), 39: ("坎", "艮"), 40: ("震", "坎"),
    41: ("艮", "兑"), 42: ("巽", "震"), 43: ("兑", "乾"), 44: ("乾", "巽"),
    45: ("兑", "坤"), 46: ("坤", "巽"), 47: ("兑", "坎"), 48: ("坎", "巽"),
    49: ("兑", "离"), 50: ("离", "巽"), 51: ("震", "震"), 52: ("艮", "艮"),
    53: ("巽", "艮"), 54: ("震", "兑"), 55: ("震", "离"), 56: ("离", "艮"),
    57: ("巽", "巽"), 58: ("兑", "兑"), 59: ("巽", "坎"), 60: ("坎", "兑"),
    61: ("巽", "兑"), 62: ("震", "艮"), 63: ("坎", "离"), 64: ("离", "坎"),
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


# ======================================================================================
# 六爻运算层：纳甲 / 六亲 / 世应 / 六神 / 综合排盘
# ======================================================================================
# 规则来源（多源交叉核实）：天机爻 Wiki、卜筮正宗、纳甲歌、Dao Oracle、OldBird。
# 本层只做坐标换算（干支/五行/六亲配位），不产生解卦文本。
#
# 文王序说明：本表用文王序（1=乾..64=未济），与 GUA_NAMES_64 对齐。
# GUA_NAMES_64[0]='乾'=文王序1。

# --------------------------------------------------------------------------------------
# 八宫归属表
# --------------------------------------------------------------------------------------
# 64卦分八宫，每宫8卦。宫序：乾震坎艮（阳宫，前4），坤巽离兑（阴宫，后4）。
# 每宫内顺序：本宫(八纯)/一世/二世/三世/四世/五世/游魂/归魂。
#
# 文王序 -> 宫名（已核实，见上方各宫列表）
# 注意：乾宫一世为姤（文王序44），非43；43夬属坤宫五世。此为核实校正点。
GUA_TO_GONG: dict[int, str] = {
    # 乾宫（金）
    1: "乾", 44: "乾", 33: "乾", 12: "乾",
    20: "乾", 23: "乾", 35: "乾", 14: "乾",
    # 震宫（木）
    51: "震", 16: "震", 40: "震", 32: "震",
    46: "震", 48: "震", 28: "震", 17: "震",
    # 坎宫（水）
    29: "坎", 60: "坎", 3: "坎", 63: "坎",
    49: "坎", 55: "坎", 36: "坎", 7: "坎",
    # 艮宫（土）
    52: "艮", 22: "艮", 26: "艮", 41: "艮",
    38: "艮", 10: "艮", 61: "艮", 53: "艮",
    # 坤宫（土）
    2: "坤", 24: "坤", 19: "坤", 11: "坤",
    34: "坤", 43: "坤", 5: "坤", 8: "坤",
    # 巽宫（木）
    57: "巽", 9: "巽", 37: "巽", 42: "巽",
    25: "巽", 21: "巽", 27: "巽", 18: "巽",
    # 离宫（火）
    30: "离", 56: "离", 50: "离", 64: "离",
    4: "离", 59: "离", 6: "离", 13: "离",
    # 兑宫（金）
    58: "兑", 47: "兑", 45: "兑", 31: "兑",
    39: "兑", 15: "兑", 62: "兑", 54: "兑",
}

# 宫名 -> 宫五行
GONG_WUXING: dict[str, str] = {
    "乾": "金", "兑": "金", "离": "火", "震": "木",
    "巽": "木", "坎": "水", "艮": "土", "坤": "土",
}

# 文王序 -> 宫内位置（'本宫'/'一世'/.../'归魂'）
# 每宫内顺序固定：本宫(0)/一世(1)/二世(2)/三世(3)/四世(4)/五世(5)/游魂(6)/归魂(7)
# 按核实表显式构建（每宫内顺序：本宫/一世/二世/三世/四世/五世/游魂/归魂）
GUA_GONG_POSITION: dict[int, str] = {}
_GUA_GONG_POS_BUILD: list[tuple[int, str]] = [
    # 乾宫
    (1, "本宫"), (44, "一世"), (33, "二世"), (12, "三世"),
    (20, "四世"), (23, "五世"), (35, "游魂"), (14, "归魂"),
    # 震宫
    (51, "本宫"), (16, "一世"), (40, "二世"), (32, "三世"),
    (46, "四世"), (48, "五世"), (28, "游魂"), (17, "归魂"),
    # 坎宫
    (29, "本宫"), (60, "一世"), (3, "二世"), (63, "三世"),
    (49, "四世"), (55, "五世"), (36, "游魂"), (7, "归魂"),
    # 艮宫
    (52, "本宫"), (22, "一世"), (26, "二世"), (41, "三世"),
    (38, "四世"), (10, "五世"), (61, "游魂"), (53, "归魂"),
    # 坤宫
    (2, "本宫"), (24, "一世"), (19, "二世"), (11, "三世"),
    (34, "四世"), (43, "五世"), (5, "游魂"), (8, "归魂"),
    # 巽宫
    (57, "本宫"), (9, "一世"), (37, "二世"), (42, "三世"),
    (25, "四世"), (21, "五世"), (27, "游魂"), (18, "归魂"),
    # 离宫
    (30, "本宫"), (56, "一世"), (50, "二世"), (64, "三世"),
    (4, "四世"), (59, "五世"), (6, "游魂"), (13, "归魂"),
    # 兑宫
    (58, "本宫"), (47, "一世"), (45, "二世"), (31, "三世"),
    (39, "四世"), (15, "五世"), (62, "游魂"), (54, "归魂"),
]
for _num, _pos in _GUA_GONG_POS_BUILD:
    GUA_GONG_POSITION[_num] = _pos
# 纳甲：天干地支配六爻
# --------------------------------------------------------------------------------------
# 纳干规则：按该爻所属经卦的内/外卦配天干
# 内卦=下卦=初爻/二爻/三爻；外卦=上卦=四爻/五爻/上爻
# 乾：内甲外壬；坤：内乙外癸；震庚；巽辛；坎戊；离己；艮丙；兑丁
_NAJIA_STEM: dict[str, tuple[str, str]] = {
    # (内卦干, 外卦干)
    "乾": ("甲", "壬"),
    "坤": ("乙", "癸"),
    "震": ("庚", "庚"),
    "巽": ("辛", "辛"),
    "坎": ("戊", "戊"),
    "离": ("己", "己"),
    "艮": ("丙", "丙"),
    "兑": ("丁", "丁"),
}

# 纳支规则：按该爻所属经卦的纳支顺序，自下而上（初爻→上爻）
# 乾：子寅辰午申戌（初爻子..上爻戌）
# 震：子寅辰午申戌
# 坎：寅辰午申戌子
# 艮：辰午申戌子寅
# 坤：未巳卯丑亥酉
# 巽：丑亥酉未巳卯
# 离：卯丑亥酉未巳
# 兑：巳卯丑亥酉未
_NAJIA_BRANCH: dict[str, list[str]] = {
    "乾": ["子", "寅", "辰", "午", "申", "戌"],
    "震": ["子", "寅", "辰", "午", "申", "戌"],
    "坎": ["寅", "辰", "午", "申", "戌", "子"],
    "艮": ["辰", "午", "申", "戌", "子", "寅"],
    "坤": ["未", "巳", "卯", "丑", "亥", "酉"],
    "巽": ["丑", "亥", "酉", "未", "巳", "卯"],
    "离": ["卯", "丑", "亥", "酉", "未", "巳"],
    "兑": ["巳", "卯", "丑", "亥", "酉", "未"],
}


def najia(h: Hexagram) -> list[dict]:
    """纳甲：为六爻配天干地支。

    规则（已核实）：
      - 初爻/二爻/三爻用下卦（内卦）的纳干纳支
      - 四爻/五爻/上爻用上卦（外卦）的纳干纳支
      - 纳支自下而上按经卦纳支顺序排

    返回 6 个 dict（自下而上，position 1..6），每个含：
      position, heavenly_stem, earthly_branch
    """
    upper_name, lower_name = _wengwang_upper_lower(h.gua_number)
    lower_stem = _NAJIA_STEM[lower_name][0]   # 内卦干
    upper_stem = _NAJIA_STEM[upper_name][1]   # 外卦干
    lower_branches = _NAJIA_BRANCH[lower_name]  # 下卦6支
    upper_branches = _NAJIA_BRANCH[upper_name]  # 上卦6支

    result: list[dict] = []
    for pos in range(1, 7):
        if pos <= 3:
            # 内卦：初爻取下卦纳支[0]，二爻[1]，三爻[2]
            stem = lower_stem
            branch = lower_branches[pos - 1]
        else:
            # 外卦：四爻取上卦纳支[3]，五爻[4]，上爻[5]
            stem = upper_stem
            branch = upper_branches[pos - 1]
        result.append({
            "position": pos,
            "heavenly_stem": stem,
            "earthly_branch": branch,
        })
    return result


# --------------------------------------------------------------------------------------
# 六亲：按宫五行与爻五行的生克关系定六亲
# --------------------------------------------------------------------------------------
# 地支五行表
# 亥子=水，寅卯=木，巳午=火，申酉=金，辰戌丑未=土
_ZHI_WUXING: dict[str, str] = {
    "亥": "水", "子": "水",
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "申": "金", "酉": "金",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

# 五行生克
# 生：水生木，木生火，火生土，土生金，金生水
# 克：水克火，火克金，金克木，木克土，土克水
_WUXING_SHENG: dict[str, str] = {
    "水": "木", "木": "火", "火": "土", "土": "金", "金": "水",
}
_WUXING_KE: dict[str, str] = {
    "水": "火", "火": "金", "金": "木", "木": "土", "土": "水",
}


def _liuqin_relation(gong_wx: str, yao_wx: str) -> str:
    """按宫五行与爻五行的生克关系定六亲。

    - 同我（五行相同）= 兄弟
    - 生我（爻五行生宫五行）= 父母
    - 我生（宫五行生爻五行）= 子孙
    - 我克（宫五行克爻五行）= 妻财
    - 克我（爻五行克宫五行）= 官鬼
    """
    if gong_wx == yao_wx:
        return "兄弟"
    if _WUXING_SHENG[yao_wx] == gong_wx:   # 爻生宫 = 生我 = 父母
        return "父母"
    if _WUXING_SHENG[gong_wx] == yao_wx:   # 宫生爻 = 我生 = 子孙
        return "子孙"
    if _WUXING_KE[gong_wx] == yao_wx:      # 宫克爻 = 我克 = 妻财
        return "妻财"
    if _WUXING_KE[yao_wx] == gong_wx:      # 爻克宫 = 克我 = 官鬼
        return "官鬼"
    raise ValueError(f"无法定六亲：宫五行={gong_wx} 爻五行={yao_wx}")


def liuqin(h: Hexagram) -> list[dict]:
    """六亲：为六爻配六亲。

    规则（已核实）：
      1. 取本卦 gua_number，查 GUA_TO_GONG 得宫名
      2. 查 GONG_WUXING 得宫五行
      3. 对每爻，取该爻纳支的地支，查地支五行
      4. 按宫五行与爻五行的生克关系定六亲

    返回 6 个 dict（自下而上，position 1..6），每个含：
      position, liuqin, wuxing
    """
    gong = GUA_TO_GONG[h.gua_number]
    gong_wx = GONG_WUXING[gong]
    najia_result = najia(h)

    result: list[dict] = []
    for item in najia_result:
        branch = item["earthly_branch"]
        yao_wx = _ZHI_WUXING[branch]
        relation = _liuqin_relation(gong_wx, yao_wx)
        result.append({
            "position": item["position"],
            "liuqin": relation,
            "wuxing": yao_wx,
        })
    return result


# --------------------------------------------------------------------------------------
# 世应：定世爻/应爻位置
# --------------------------------------------------------------------------------------
# 按宫内位置定世爻位（1=初爻..6=上爻）
_GONG_POSITION_TO_SHI: dict[str, int] = {
    "本宫": 6,
    "一世": 1,
    "二世": 2,
    "三世": 3,
    "四世": 4,
    "五世": 5,
    "游魂": 4,
    "归魂": 3,
}


def shiying(h: Hexagram) -> dict:
    """世应：定世爻/应爻位置。

    规则（已核实）：
      1. 取本卦 gua_number，查 GUA_GONG_POSITION 得宫内位置
      2. 按宫内位置定世爻位
      3. 应爻位 = (世爻位 + 2) % 6，若为0则取6（隔二位）

    返回 dict：{shi, ying, gong, gong_position, gong_wuxing}
    """
    gong = GUA_TO_GONG[h.gua_number]
    gong_pos = GUA_GONG_POSITION[h.gua_number]
    gong_wx = GONG_WUXING[gong]

    shi = _GONG_POSITION_TO_SHI[gong_pos]
    # 应爻隔世爻两位（中间隔两爻），即世+3 位取模6
    ying = (shi + 3) % 6
    if ying == 0:
        ying = 6

    return {
        "shi": shi,
        "ying": ying,
        "gong": gong,
        "gong_position": gong_pos,
        "gong_wuxing": gong_wx,
    }


# --------------------------------------------------------------------------------------
# 六神：按日干起六神
# --------------------------------------------------------------------------------------
# 日干 -> 初爻六神
_DAY_GAN_TO_INIT_SHEN: dict[str, str] = {
    "甲": "青龙", "乙": "青龙",
    "丙": "朱雀", "丁": "朱雀",
    "戊": "勾陈",
    "己": "螣蛇",
    "庚": "白虎", "辛": "白虎",
    "壬": "玄武", "癸": "玄武",
}

# 六神顺序（自初爻向上排6个）：青龙→朱雀→勾陈→螣蛇→白虎→玄武
_SHEN_ORDER = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]


def liushen(day_gan: str) -> list[dict]:
    """六神：按日干起六神，自初爻至上爻排。

    规则（已核实）：
      - 甲乙日初爻青龙，丙丁朱雀，戊勾陈，己螣蛇，庚辛白虎，壬癸玄武
      - 六神顺序自下而上：青龙→朱雀→勾陈→螣蛇→白虎→玄武

    输入 day_gan 是天干字符串（如 '甲'/'乙'/'丙'...）

    返回 6 个 dict（自下而上，position 1..6）：{position, shen}
    """
    init_shen = _DAY_GAN_TO_INIT_SHEN[day_gan]
    init_idx = _SHEN_ORDER.index(init_shen)

    result: list[dict] = []
    for pos in range(1, 7):
        shen = _SHEN_ORDER[(init_idx + pos - 1) % 6]
        result.append({"position": pos, "shen": shen})
    return result


# --------------------------------------------------------------------------------------
# 综合排盘：合并纳甲/六亲/世应/六神
# --------------------------------------------------------------------------------------
def _build_gua_lines(h: Hexagram, shi_ying: dict | None,
                     shen_list: list[dict] | None) -> list[dict]:
    """构建一卦的六爻明细（自上而下，position 6..1）。

    合并：卦爻阴阳/动爻 + 纳甲 + 六亲 + 世应标记 + 六神
    六神仅本卦排（变卦不排）。
    """
    najia_result = najia(h)
    liuqin_result = liuqin(h)
    najia_by_pos = {n["position"]: n for n in najia_result}
    liuqin_by_pos = {l["position"]: l for l in liuqin_result}
    shen_by_pos = {s["position"]: s for s in shen_list} if shen_list else {}

    shi = shi_ying["shi"] if shi_ying else None
    ying = shi_ying["ying"] if shi_ying else None

    lines: list[dict] = []
    for pos in range(6, 0, -1):  # 自上而下
        yao = h.lines[pos - 1]
        n = najia_by_pos[pos]
        l = liuqin_by_pos[pos]
        line = {
            "position": pos,
            "yang": yao.yang,
            "moving": yao.moving,
            "stem": n["heavenly_stem"],
            "branch": n["earthly_branch"],
            "wuxing": l["wuxing"],
            "liuqin": l["liuqin"],
        }
        if shi_ying is not None:
            line["is_shi"] = (pos == shi)
            line["is_ying"] = (pos == ying)
        if shen_list is not None:
            line["shen"] = shen_by_pos[pos]["shen"]
        lines.append(line)
    return lines


def paipan(h: Hexagram, day_gan: str) -> dict:
    """综合排盘：合并纳甲/六亲/世应/六神。

    返回结构：
      {
        'ben_gua': {  # 本卦
          'gua_number', 'gua_name', 'gong', 'gong_wuxing', 'gong_position',
          'shi', 'ying', 'lines': [6 爻明细，自上而下]
        },
        'bian_gua': {  # 变卦（无世应/六神，但算纳甲/六亲）
          'gua_number', 'gua_name', 'gong', 'gong_wuxing', 'gong_position',
          'lines': [6 爻明细，自上而下]
        },
        'moving_lines': [动爻位]
      }
    """
    # 本卦
    sy = shiying(h)
    shen_list = liushen(day_gan)
    ben_lines = _build_gua_lines(h, sy, shen_list)
    ben_gua = {
        "gua_number": h.gua_number,
        "gua_name": h.gua_name,
        "gong": sy["gong"],
        "gong_wuxing": sy["gong_wuxing"],
        "gong_position": sy["gong_position"],
        "shi": sy["shi"],
        "ying": sy["ying"],
        "lines": ben_lines,
    }

    # 变卦
    bian = changing_hexagram(h)
    sy_bian = shiying(bian)
    bian_lines = _build_gua_lines(bian, None, None)
    bian_gua = {
        "gua_number": bian.gua_number,
        "gua_name": bian.gua_name,
        "gong": sy_bian["gong"],
        "gong_wuxing": sy_bian["gong_wuxing"],
        "gong_position": sy_bian["gong_position"],
        "lines": bian_lines,
    }

    return {
        "ben_gua": ben_gua,
        "bian_gua": bian_gua,
        "moving_lines": h.moving_lines,
    }
