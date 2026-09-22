"""huangli — 黄历择日纯计算模块。

本地实现，规则写死可核验，不产生"新文本"。

包含三层：
  1. 建除十二值（十二值星）：建/除/满/平/定/执/破/危/成/收/开/闭
     - 按月支起"建"，日支依次顺排十二地支
     - 月支 = 当月"节"对应地支（立春=寅..小寒=丑）
  2. 二十八宿：角/亢/氐/房/心/尾/箕/斗/牛/女/虚/危/室/壁/
     奎/婁/胃/昴/畢/觜/參/井/鬼/柳/星/張/翼/軫
     - 按日轮转，起算日取一个已知锚点（如 1900-01-31 角宿）
  3. 彭祖百忌：按日柱天干/地支查表（"甲不开仓..."等）

宜忌规则：
  - 建除十二值各对应宜忌事项（通行规则，写死）
  - 输入事项（婚嫁/开业/出行/动土/搬家/安葬）→ 给出某日宜/忌

节气时刻复用 bazi.term_time（Meeus 太阳黄经二分求解，±15min 精度）。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from .bazi import term_time, jdn, ZHI

# --------------------------------------------------------------------------------------
# 建除十二值（十二值星）
# --------------------------------------------------------------------------------------
JIAN_CHU = ["建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭"]

# 建除十二值对应的宜忌（通行规则，写死可核验）
ZHIRI_YIJI: dict[str, dict[str, list[str]]] = {
    "建": {"yi": ["谒贵", "上任", "出行"], "ji": ["开仓", "动土"]},
    # R2349n（R77-P1-1）：「沐浴」是传统黄历真词（除日去秽气），补进
    # 除日宜词——此前词表没有它，沐浴问法只能走中性卡。
    "除": {"yi": ["治病", "祭祀", "解除", "沐浴"], "ji": ["嫁娶", "求名"]},
    # R229z续22（R9-P2-2）：词表统一通行字形「移徙」——原「移徒」是异体
    # 写法，与场景词表/神煞层的「移徙」永不相等（搬家/挪窝的忌项映射
    # 因此永不命中）。
    "满": {"yi": ["祭祀", "祈福", "进人口"], "ji": ["安葬", "移徙"]},
    "平": {"yi": ["修造", "动土", "平整"], "ji": ["祭祀", "祈福"]},
    "定": {"yi": ["祭祀", "祈福", "冠笄"], "ji": ["诉讼", "出官"]},
    "执": {"yi": ["捕捉", "狩猎", "祭祀"], "ji": ["开市", "立券"]},
    "破": {"yi": ["求医疗病", "破屋坏垣"], "ji": ["嫁娶", "开市", "安葬"]},
    "危": {"yi": ["祭祀", "祈福", "安床"], "ji": ["登山", "乘船"]},
    "成": {"yi": ["入学", "上任", "开市", "立券", "嫁娶"], "ji": ["诉讼"]},
    "收": {"yi": ["纳财", "捕捉", "畋猎"], "ji": ["出行", "安葬"]},
    "开": {"yi": ["祭祀", "祈福", "求嗣", "上任"], "ji": ["安葬", "破土"]},
    "闭": {"yi": ["筑堤", "塞穴", "安葬"], "ji": ["开市", "求医", "出行"]},
}


def _month_zhi_index(dt: datetime) -> int:
    """dt 所在月的地支索引（0=子..11=亥）。

    月支以"节"为界：立春=寅(2) 惊蛰=卯(3) .. 小寒=丑(1)。
    R229z续21b（R9-P1-1）：黄历层统一到「日」粒度——交节日整日记新月建，
    与传统万年历一致（交节叠值落交节日）。此前按交节时刻精确切，
    ?date=D（hour=0）与同日 now() 会给出不同建除/月支。
    注意：八字 bazi.compute 的月令仍按真实交节时刻——那是排盘口径，
    与本函数的日粒度黄历口径各管各的，互不影响。
    """
    year = dt.year
    day = dt.date()
    # 十二节 + 对应地支索引
    jies = [("立春", 2), ("惊蛰", 3), ("清明", 4), ("立夏", 5), ("芒种", 6),
            ("小暑", 7), ("立秋", 8), ("白露", 9), ("寒露", 10), ("立冬", 11),
            ("大雪", 0), ("小寒", 1)]
    cands = []
    for y in (year - 1, year, year + 1):
        for name, zhi in jies:
            cands.append((term_time(y, name) + timedelta(hours=8), zhi))
    cands.sort()
    prev_zhi = 2  # 默认寅
    for t, zhi in cands:
        if t.date() <= day:
            prev_zhi = zhi
        else:
            break
    return prev_zhi


def jianchu_value(dt: datetime) -> str:
    """dt 这天的建除十二值。

    月支起"建"，日支与月支的差（mod 12）决定值星位置。
    例：寅月（建在寅），寅日=建，卯日=除，辰日=满..丑日=闭。
    """
    month_zhi = _month_zhi_index(dt)
    # 日柱地支
    jd = jdn(dt.year, dt.month, dt.day)
    day_gan_zhi = (jd + 49) % 60     # 日柱六十甲子序
    day_zhi_idx = day_gan_zhi % 12   # 地支索引 0=子..11=亥

    offset = (day_zhi_idx - month_zhi) % 12
    return JIAN_CHU[offset]


# --------------------------------------------------------------------------------------
# 二十八宿
# --------------------------------------------------------------------------------------
XIUXIU = [
    "角", "亢", "氐", "房", "心", "尾", "箕",        # 东方青龙
    "斗", "牛", "女", "虚", "危", "室", "壁",        # 北方玄武
    "奎", "婁", "胃", "昴", "畢", "觜", "參",        # 西方白虎
    "井", "鬼", "柳", "星", "張", "翼", "軫",        # 南方朱雀
]

# 二十八宿宜忌（通行规则，写死可核验）
XIUXIU_YIJI: dict[str, dict[str, list[str]]] = {
    "角": {"yi": ["嫁娶", "祭祀"], "ji": ["行丧", "安葬"]},
    "亢": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "栽种"]},
    "氐": {"yi": ["栽种", "纳财"], "ji": ["嫁娶", "出行"]},
    "房": {"yi": ["嫁娶", "祭祀", "上任"], "ji": ["田猎"]},
    "心": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "动土"]},
    "尾": {"yi": ["嫁娶", "祭祀", "求嗣"], "ji": ["安葬"]},
    "箕": {"yi": ["纳财", "捕捉"], "ji": ["嫁娶", "开市"]},
    "斗": {"yi": ["开市", "立券", "纳财"], "ji": ["安葬"]},
    "牛": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "动土"]},
    "女": {"yi": ["祭祀", "祈福", "求嗣"], "ji": ["嫁娶", "开市"]},
    "虚": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "开市", "求医"]},
    "危": {"yi": ["祭祀", "祈福", "安床"], "ji": ["登山", "乘船"]},
    "室": {"yi": ["修造", "动土", "入宅"], "ji": ["嫁娶"]},
    "壁": {"yi": ["祭祀", "祈福", "修造"], "ji": ["嫁娶", "出行"]},
    "奎": {"yi": ["祭祀", "祈福", "修造"], "ji": ["嫁娶", "动土"]},
    "婁": {"yi": ["祭祀", "嫁娶", "纳财"], "ji": ["出行", "安葬"]},
    "胃": {"yi": ["祭祀", "祈福", "纳财"], "ji": ["嫁娶", "动土"]},
    "昴": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "动土", "安葬"]},
    "畢": {"yi": ["嫁娶", "祭祀", "入宅"], "ji": ["安葬", "开市"]},
    "觜": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "出行"]},
    "參": {"yi": ["祭祀", "祈福", "求嗣"], "ji": ["嫁娶", "开市"]},
    "井": {"yi": ["祭祀", "祈福", "纳财"], "ji": ["嫁娶", "动土"]},
    "鬼": {"yi": ["祭祀", "祈福"], "ji": ["嫁娶", "出行", "安葬"]},
    "柳": {"yi": ["祭祀", "祈福", "求嗣"], "ji": ["嫁娶", "开市"]},
    "星": {"yi": ["祭祀", "祈福", "上任"], "ji": ["嫁娶", "动土"]},
    "張": {"yi": ["嫁娶", "祭祀", "上任"], "ji": ["安葬"]},
    "翼": {"yi": ["祭祀", "祈福", "上任"], "ji": ["嫁娶", "动土"]},
    "軫": {"yi": ["祭祀", "祈福", "出行"], "ji": ["嫁娶", "开市"]},
}

# 二十八宿起算锚点：1900-01-31（农历庚子年正月初一）= 箕宿
# R229z续20（R9-P0）：R5 修复时从 wnl.cc 取的「星宿：室宿」实为本命星宿字段
# （同页并排还有「值日星宿」）。三方独立证据收敛 offset=6：
#   1. 曜日规则：1900-01-31=星期三（水曜），水宿组={箕,壁,參,軫}，offset=6 给箕✓
#      （offset=12 给室=火宿，违例——曜日宿组是全定义域硬不变量）
#   2. 外部锚点：2000-01-01 万年历=胃宿（offset=6✓，12✗）
#   3. 外部锚点：2024-02-10 万年历=氐宿（offset=6✓，12✗）
# JDN(1900,1,31)=2415051；XIUXIU[6]=箕。
_XIU_ANCHOR_JDN = 2415051
_XIU_ANCHOR_OFFSET = 6  # 箕=6

# 曜日→宿组（七曜配宿不变量：每个曜日恒落同五行宿组）——probe 回归用
_WEEKDAY_XIU_GROUP = {
    6: {"房", "虚", "昴", "星"},      # 周日=日宿
    0: {"心", "危", "畢", "張"},      # 周一=月宿
    1: {"尾", "室", "觜", "翼"},      # 周二=火宿
    2: {"箕", "壁", "參", "軫"},      # 周三=水宿
    3: {"斗", "奎", "井", "角"},      # 周四=木宿
    4: {"牛", "婁", "鬼", "亢"},      # 周五=金宿
    5: {"氐", "女", "胃", "柳"},      # 周六=土宿
}


def xiu_value(dt: datetime) -> str:
    """dt 这天的二十八宿值。"""
    jd = jdn(dt.year, dt.month, dt.day)
    offset = (jd - _XIU_ANCHOR_JDN + _XIU_ANCHOR_OFFSET) % 28
    return XIUXIU[offset]


# --------------------------------------------------------------------------------------
# 彭祖百忌
# --------------------------------------------------------------------------------------
# 十天干彭祖百忌
PENGZU_GAN: dict[str, str] = {
    "甲": "甲不开仓，财物耗散",
    "乙": "乙不栽植，千株不长",
    "丙": "丙不修灶，必见灾殃",
    "丁": "丁不剃头，头必生疮",
    "戊": "戊不受田，田主不祥",
    "己": "己不破券，二比并亡",
    "庚": "庚不经络，织机虚张",
    "辛": "辛不合酱，主人不尝",
    "壬": "壬不汲水，更难提防",
    "癸": "癸不词讼，理弱敌强",
}
# 十二地支彭祖百忌
PENGZU_ZHI: dict[str, str] = {
    "子": "子不问卜，自惹祸殃",
    "丑": "丑不冠带，主不还乡",
    "寅": "寅不祭祀，神鬼不尝",
    "卯": "卯不穿井，水泉不香",
    "辰": "辰不哭泣，必主重丧",
    "巳": "巳不远行，财物伏藏",
    "午": "午不苫盖，屋主更张",
    "未": "未不服药，毒气入肠",
    "申": "申不安床，鬼祟入房",
    "酉": "酉不会客，醉坐颠狂",
    "戌": "戌不吃犬，作怪上床",
    "亥": "亥不嫁娶，不利新郎",
}


def pengzu_baiji(dt: datetime) -> dict[str, str]:
    """dt 这天的彭祖百忌（天干 + 地支）。"""
    gan, zhi = day_ganzhi(dt)
    return {"gan": gan, "zhi": zhi,
            "gan_text": PENGZU_GAN[gan], "zhi_text": PENGZU_ZHI[zhi]}


# --------------------------------------------------------------------------------------
# 神煞层
# --------------------------------------------------------------------------------------
# 天德起例（正月起丁，含二月申/八月寅/十一月巳三个地支位）
TIAND = ["丁", "申", "壬", "辛", "亥", "甲", "癸", "寅", "丙", "乙", "巳", "庚"]
# 月厌起例（正月起戌，逆行十二地支）
YUEYAN = ["戌", "酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥"]

# 三合局共享映射（申子辰/亥卯未/寅午戌/巳酉丑），劫煞/灾煞/月煞/驿马均引用
SANHE_JIESHA = {           # 劫煞起例（三合局→劫煞地支）
    "申子辰": "巳", "亥卯未": "申", "寅午戌": "亥", "巳酉丑": "寅",
}
SANHE_ZAISHA = {           # 灾煞起例（劫煞下一支）
    "申子辰": "午", "亥卯未": "酉", "寅午戌": "子", "巳酉丑": "卯",
}
SANHE_YUESHA = {           # 月煞起例
    "申子辰": "未", "亥卯未": "戌", "寅午戌": "丑", "巳酉丑": "辰",
}
SANHE_YIMA = {             # 驿马起例（与劫煞同支）
    "申子辰": "寅", "亥卯未": "巳", "寅午戌": "申", "巳酉丑": "亥",
}
SANHE_YUEDE = {            # 月德起例（三合局→天干）
    "寅午戌": "丙", "申子辰": "壬", "亥卯未": "甲", "巳酉丑": "庚",
}

# 月支索引 → 三合局名（0=子..11=亥）
_ZHI_TO_SANHE: dict[int, str] = {}
for _name in ("申子辰", "亥卯未", "寅午戌", "巳酉丑"):
    for _c in _name:
        _ZHI_TO_SANHE[ZHI.index(_c)] = _name

# 天赦日（按季节）：春戊寅、夏甲午、秋戊申、冬甲子
# 季节按月支：寅卯辰=春，巳午未=夏，申酉戌=秋，亥子丑=冬
_TIANSHA_MAP: dict[int, str] = {
    2: "戊寅", 3: "戊寅", 4: "戊寅",    # 春
    5: "甲午", 6: "甲午", 7: "甲午",    # 夏
    8: "戊申", 9: "戊申", 10: "戊申",   # 秋
    11: "甲子", 0: "甲子", 1: "甲子",    # 冬
}

# 天乙贵人起例（日干→贵人地支列表）
GUIREN: dict[str, list[str]] = {
    "甲": ["丑", "未"], "戊": ["丑", "未"], "庚": ["丑", "未"],
    "乙": ["子", "申"], "己": ["子", "申"],
    "丙": ["酉", "亥"], "丁": ["酉", "亥"],
    "壬": ["卯", "巳"], "癸": ["卯", "巳"],
    "辛": ["寅", "午"],
}

# R233v（R52-P1-3）：杨公忌十三日（农历月日，通行表写死可核验）。
_YANGGONG: frozenset = frozenset({
    (1, 13), (2, 11), (3, 9), (4, 7), (5, 5), (6, 3), (7, 1),
    (7, 29), (8, 27), (9, 25), (10, 23), (11, 21), (12, 19),
})

# 神煞对宜忌的影响（写死可核验）
_TIAND_YIJI: tuple[list[str], list[str]] = (
    ["祭祀", "祈福", "嫁娶"], ["诉讼"])
_YUEDE_YIJI: tuple[list[str], list[str]] = (
    ["祭祀", "祈福", "嫁娶"], ["诉讼"])
_TIANSHA_YIJI: tuple[list[str], list[str]] = (
    ["祭祀", "祈福", "求嗣", "出行"], ["诉讼"])
_GUIREN_YIJI: tuple[list[str], list[str]] = (
    ["谒贵", "上任", "嫁娶"], [])
_YIMA_YIJI: tuple[list[str], list[str]] = (
    ["出行", "移徙", "上任"], [])
_JIESHA_YIJI: tuple[list[str], list[str]] = (
    [], ["嫁娶", "移徙", "安葬", "出行"])
_ZAISHA_YIJI: tuple[list[str], list[str]] = (
    [], ["嫁娶", "移徙", "安葬", "出行"])
_YUESHA_YIJI: tuple[list[str], list[str]] = (
    [], ["嫁娶", "移徙", "安葬"])
_YUEYAN_YIJI: tuple[list[str], list[str]] = (
    [], ["嫁娶", "远行", "移徙", "归家"])


def day_ganzhi(dt: datetime) -> tuple[str, str]:
    """dt 这天的日柱天干地支。

    R228p：算法单源化——直接委托 bazi.day_ganzhi（JDN 锚点 (jd+49)%60
    两边一致），本函数只剩签名适配（gan,zhi）。"""
    from .bazi import day_ganzhi as _dgz
    gz, _idx = _dgz(dt)
    return gz[0], gz[1]


def tiande(dt: datetime) -> str:
    """天德（正月起丁）。返回天干或地支。"""
    # 月支索引 → 农历月序（寅月=正月=0）
    mzi = _month_zhi_index(dt)
    # 寅(2)→0, 卯(3)→1 ... 丑(1)→11
    lunar_month = (mzi - 2) % 12
    return TIAND[lunar_month]


def yuede(dt: datetime) -> str:
    """月德（三合局→天干）。"""
    mzi = _month_zhi_index(dt)
    sanhe = _ZHI_TO_SANHE[mzi]
    return SANHE_YUEDE[sanhe]


def tianshe(dt: datetime) -> bool:
    """天赦日判定：季节对应天赦干支 == 该日干支。"""
    mzi = _month_zhi_index(dt)
    target = _TIANSHA_MAP[mzi]
    gan, zhi = day_ganzhi(dt)
    return (gan + zhi) == target


def jiesha(dt: datetime) -> str:
    """劫煞（三合局→地支）。"""
    mzi = _month_zhi_index(dt)
    return SANHE_JIESHA[_ZHI_TO_SANHE[mzi]]


def zaisha(dt: datetime) -> str:
    """灾煞（劫煞下一支）。"""
    mzi = _month_zhi_index(dt)
    return SANHE_ZAISHA[_ZHI_TO_SANHE[mzi]]


def yuesha(dt: datetime) -> str:
    """月煞（三合局→地支）。"""
    mzi = _month_zhi_index(dt)
    return SANHE_YUESHA[_ZHI_TO_SANHE[mzi]]


def yueyan(dt: datetime) -> str:
    """月厌（正月起戌，逆行）。"""
    mzi = _month_zhi_index(dt)
    lunar_month = (mzi - 2) % 12
    return YUEYAN[lunar_month]


def yima(dt: datetime) -> str:
    """驿马（三合局→地支，与劫煞同支）。"""
    mzi = _month_zhi_index(dt)
    return SANHE_YIMA[_ZHI_TO_SANHE[mzi]]


def guiren(dt: datetime) -> list[str]:
    """天乙贵人（日干→贵人地支列表，2 个）。"""
    gan, _ = day_ganzhi(dt)
    return list(GUIREN[gan])


def shensha(dt: datetime) -> dict:
    """dt 这天所有神煞的 dict（纯坐标计算）。"""
    gan, zhi = day_ganzhi(dt)
    mzi = _month_zhi_index(dt)
    return {
        "tiande": tiande(dt),
        "yuede": yuede(dt),
        "tianshe": tianshe(dt),
        "jiesha": jiesha(dt),
        "zaisha": zaisha(dt),
        "yuesha": yuesha(dt),
        "yueyan": yueyan(dt),
        "yima": yima(dt),
        "guiren": guiren(dt),
        "day_gan": gan,
        "day_zhi": zhi,
        "month_zhi": ZHI[mzi],
        # R233w（R52-P1-2）：「临日」判定收成单点真相——前端此前自己复现
        # 了一份（日支==神煞值 的逐项比较），两份逻辑迟早漂。这里直接
        # 回吐命中的神煞名，前端只做 名字→文案 的展示映射。
        "linri": _linri(gan, zhi, dt),
    }


def _linri(gan: str, zhi: str, dt: datetime) -> dict:
    """临日命中名单：吉神/凶煞各一列，名字是神煞键。"""
    good, bad = [], []
    if zhi in guiren(dt):
        good.append("贵人")
    if yima(dt) == zhi:
        good.append("驿马")
    if tianshe(dt):
        good.append("天赦")
    _td = tiande(dt)
    if _td and (_td == gan or _td == zhi):
        good.append("天德")
    _yd = yuede(dt)
    if _yd and _yd == gan:
        good.append("月德")
    for fn, name in ((jiesha, "劫煞"), (zaisha, "灾煞"),
                     (yuesha, "月煞"), (yueyan, "月厌")):
        if fn(dt) == zhi:
            bad.append(name)
    return {"good": good, "bad": bad}


def shensha_yiji(dt: datetime) -> tuple[list[str], list[str]]:
    """神煞对宜忌的影响（基于"临日"判定：日支是否等于神煞值）。

    返回 (宜列表, 忌列表)，去重。
    """
    gan, zhi = day_ganzhi(dt)
    yi: list[str] = []
    ji: list[str] = []

    # 天赦日
    if tianshe(dt):
        yi += _TIANSHA_YIJI[0]; ji += _TIANSHA_YIJI[1]
    # 天德临日：天德值混排干/支，日干==天德干 或 日支==天德支
    td = tiande(dt)
    if gan == td or zhi == td:
        yi += _TIAND_YIJI[0]; ji += _TIAND_YIJI[1]
    # 月德临日：月德是纯天干神煞，日干==月德干
    if gan == yuede(dt):
        yi += _YUEDE_YIJI[0]; ji += _YUEDE_YIJI[1]
    # 劫煞临日
    if jiesha(dt) == zhi:
        ji += _JIESHA_YIJI[1]
    # 灾煞临日
    if zaisha(dt) == zhi:
        ji += _ZAISHA_YIJI[1]
    # 月煞临日
    if yuesha(dt) == zhi:
        ji += _YUESHA_YIJI[1]
    # 月厌临日
    if yueyan(dt) == zhi:
        ji += _YUEYAN_YIJI[1]
    # 驿马临日
    if yima(dt) == zhi:
        yi += _YIMA_YIJI[0]
    # 贵人临日（日支 in guiren）
    if zhi in guiren(dt):
        yi += _GUIREN_YIJI[0]

    return sorted(set(yi)), sorted(set(ji))


# --------------------------------------------------------------------------------------
# 综合查询
# --------------------------------------------------------------------------------------
# R77（R2349n）：同义族冲突——宜忌两侧换字同义照样是打架。
# 「宜修造/塞穴/筑堤 忌动土」在卡面上读作「宜装修、忌开工」，同词交集
# 的 conflict 键盖不到（28/60 天有同词，跨字同义另有一批）。
# 判定：某词的族同时命中宜、忌两侧 → 该族两侧词全部标记。
_TERM_FAMILIES: list[frozenset[str]] = [
    frozenset({"修造", "动土", "破土", "塞穴", "筑堤", "破屋坏垣",
               "竖柱", "上梁"}),                          # 开工营造
    frozenset({"出行", "远行", "归家", "移徙", "入宅", "乘船", "登山"}),
    frozenset({"开市", "立券", "纳财", "开仓", "交易", "置产"}),
    frozenset({"嫁娶", "求嗣", "进人口", "纳采", "订盟"}),  # 婚育
    frozenset({"上任", "求名", "入学"}),                   # 功名
    frozenset({"祭祀", "祈福"}),                           # 敬拜
    frozenset({"求医", "治病", "求医疗病"}),               # 医疗
    frozenset({"捕捉", "畋猎", "狩猎", "田猎"}),           # 猎取
]
_WORD_FAMILY: dict[str, frozenset[str]] = {}
for _fam in _TERM_FAMILIES:
    for _w in _fam:
        _WORD_FAMILY[_w] = _WORD_FAMILY.get(_w, frozenset()) | _fam


def term_family(term: str) -> frozenset[str]:
    """词的同义族（无族时返回只含自身的单元素集）。"""
    return _WORD_FAMILY.get(term, frozenset({term}))


def family_conflicts(yi: list[str], ji: list[str]) -> list[str]:
    """返回所有卷入「同义族宜忌对冲」的词（两侧并集）。"""
    yi_s, ji_s = set(yi), set(ji)
    out: set[str] = set()
    for w in yi_s | ji_s:
        fam = _WORD_FAMILY.get(w)
        if fam and (fam & yi_s) and (fam & ji_s):
            out |= (fam & (yi_s | ji_s))
    return sorted(out)


def day_query(dt: datetime) -> dict:
    """查 dt 这天的黄历坐标（纯计算，无解读）。

    返回：
      date: "YYYY-MM-DD"
      jianchu: 建除十二值
      xiu: 二十八宿值
      pengzu: 彭祖百忌 {gan, zhi, gan_text, zhi_text}
      yi: 宜（合并建除+二十八宿）
      ji: 忌（合并建除+二十八宿）
    """
    jc = jianchu_value(dt)
    xx = xiu_value(dt)
    pz = pengzu_baiji(dt)

    yi = list(set(ZHIRI_YIJI[jc]["yi"] + XIUXIU_YIJI[xx]["yi"]))
    ji = list(set(ZHIRI_YIJI[jc]["ji"] + XIUXIU_YIJI[xx]["ji"]))

    # R233v（R52-P1-2）：神煞宜忌层接线——天赦/天德/月德/驿马/贵人临日
    # 的宜项与劫煞/灾煞/月煞/月厌的忌项此前算完就丢（死代码），词表里
    # 远行/移徙/上任/诉讼 这类词因此恒不命中（「问搬家年年中性」）。
    _sy, _sj = shensha_yiji(dt)
    yi = list(set(yi) | set(_sy))
    ji = list(set(ji) | set(_sj))

    # R216b 续6（V-001）：补农历日期与冲煞——传统黄历核心字段，
    # 纯坐标计算 additive（既有键零改动）。
    _lunar = {}
    try:
        from .lunar import solar_to_lunar
        _lunar = solar_to_lunar(dt.year, dt.month, dt.day)
    except Exception:
        _lunar = {}
    _gz_gan, _gz_zhi = day_ganzhi(dt)
    _zhi_idx = ZHI.index(_gz_zhi) if _gz_zhi in ZHI else 0

    # R233v（R52-P1-3）：传统硬凶日标记——月破/四离/四绝/杨公忌。
    # 此前任何日子宜忌条目都差不多多，「诸事不宜」级日子与普通日
    # 无差别。只打标不改词表。
    _flags: list[str] = []
    if _zhi_idx == (_month_zhi_index(dt) + 6) % 12:
        _flags.append("月破")
    try:
        from .bazi import term_time as _tt
        _tom = dt + timedelta(days=1)
        for _y in (dt.year - 1, dt.year, dt.year + 1):
            for _tn in ("春分", "夏至", "秋分", "冬至"):
                if (_tt(_y, _tn) + timedelta(hours=8)).date() == _tom.date() \
                        and "四离" not in _flags:
                    _flags.append("四离")
            for _tn in ("立春", "立夏", "立秋", "立冬"):
                if (_tt(_y, _tn) + timedelta(hours=8)).date() == _tom.date() \
                        and "四绝" not in _flags:
                    _flags.append("四绝")
    except Exception:
        pass
    if _lunar and (_lunar.get("month"), _lunar.get("day")) in _YANGGONG:
        _flags.append("杨公忌")
    # R233w（R52-P3-9）：交节时刻 ±15min 精度对日粒度的残余风险——
    # 与其藏着，把「今日交节 + CST 时刻」透明化回吐；用户看到
    # 「交在 23:5X」自然明白日粒度边界，这也是黄历卡本该有的信息。
    _term_today = None
    try:
        from .bazi import TERM_LONGITUDE
        for _tn in TERM_LONGITUDE:
            _t = term_time(dt.year, _tn) + timedelta(hours=8)
            if _t.date() == dt.date():
                _term_today = {"name": _tn, "time": _t.strftime("%H:%M")}
                break
    except Exception:
        pass
    _chong = ZHI[(_zhi_idx + 6) % 12]          # 六冲：对冲支
    _cs_animal = {"子":"鼠","丑":"牛","寅":"虎","卯":"兔","辰":"龙","巳":"蛇",
                  "午":"马","未":"羊","申":"猴","酉":"鸡","戌":"狗","亥":"猪"}
    return {
        "date": f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}",
        "jianchu": jc,
        "xiu": xx,
        "pengzu": pz,
        "yi": sorted(yi),
        "ji": sorted(ji),
        # R229z续21（R9-P1-2）：约 22% 日子宜∩忌同见（建除说宜、星宿说忌）。
        # 原样透出两列是黄历本真写法，但阅读者需要知道哪些词在打架——
        # 交集单独开键透出，卡面标※、聊天事实行改走「宜忌都有」口径。
        "conflict": sorted(set(yi) & set(ji)),
        # R77（R2349n）：换字同义的对冲词也透出——卡面同样标※
        "conflict_family": family_conflicts(yi, ji),
        "shensha": shensha(dt),
        # R2351（R108-§四.3-1）：1900-01-01~30 在宣称域内但农历表
        # 起点是 1900-01-31（该日=庚子年正月初一）——此前 lunar
        # 三键静默空串，现在透一句「表外」说明而不是假装无农历。
        "lunar": {"month_cn": _lunar.get("month_cn", ""),
                  "day_cn": _lunar.get("day_cn", ""),
                  "ganzhi_year_cn": _lunar.get("ganzhi_year_cn", ""),
                  **({"note": "农历对照自 1900-01-31 起"}
                     if not _lunar.get("month_cn") else {})},
        "chongsha": {"chong": _chong,
                     "chong_animal": _cs_animal.get(_chong, ""),
                     "sha_fang": _SHA_FANG.get(_zhi_idx, "")},
        "day_flags": _flags,
        # R2350a（R94-P1-4）：日值神 + 时辰吉凶——「黄道/黑道日」与
        # 十二时辰宜忌是传统黄历卡标配字段。
        "zhishen": zhishen_day(dt),
        "zhishen_ji": zhishen_day(dt) in ZHISHEN_JI,
        "hours": hour_zhishen(dt),
        # R2350a（R94-P2-10）：日干支此前算而不透出（shensha 里
        # 有 day_gan/day_zhi 散件）——直接给合成串。
        "ganzhi_day_cn": _gz_gan + _gz_zhi + "日",
        **({"term_today": _term_today} if _term_today else {}),
    }


# R2350a（R94-P1-4）：十二值神（大黄道）+ 时辰吉凶——传统黄历标配，
# 此前整体缺席。日值神按日支轮值（子日青龙、丑日明堂……）；
# 时辰值神按日支起青龙法：
#   子午青龙起在申，卯酉之日寅上行，寅申须从子上起，
#   巳亥在午不须论，辰戌之位定在辰，丑未戌时亲。
# 黄道六神（青龙/明堂/金匮/天德/玉堂/司命）临为吉时，黑道六神
# （天刑/朱雀/白虎/天牢/玄武/勾陈）临为凶时。
ZHISHEN = ["青龙", "明堂", "天刑", "朱雀", "金匮", "天德",
           "白虎", "玉堂", "天牢", "玄武", "司命", "勾陈"]
ZHISHEN_JI = frozenset({"天刑", "朱雀", "白虎", "天牢", "玄武", "勾陈"})
# 日支 → 青龙所在时辰（地支名）
_ZHISHEN_START = {
    "子": "申", "午": "申", "卯": "寅", "酉": "寅",
    "寅": "子", "申": "子", "巳": "午", "亥": "午",
    "辰": "辰", "戌": "辰", "丑": "戌", "未": "戌",
}


def zhishen_day(dt: datetime) -> str:
    """日值神（大黄道）：按「月支」起青龙（子午临申、卯酉居寅、
    寅申从子、巳亥在午、辰戌归辰、丑未从戌），落在日支上的神即
    当日值神。注意与小黄道（时辰值神，按日支起）区分——同一套
    口诀、不同的锚。"""
    month_zhi = _month_zhi_index(dt)
    _, zhi = day_ganzhi(dt)
    start = ZHI.index(_ZHISHEN_START.get(ZHI[month_zhi], "申"))
    return ZHISHEN[(ZHI.index(zhi) - start) % 12]


def hour_zhishen(dt: datetime) -> list[dict]:
    """十二时辰值神+吉凶：[{branch, shen, ji}]，按日支起青龙法轮转。"""
    _, day_zhi = day_ganzhi(dt)
    start = ZHI.index(_ZHISHEN_START.get(day_zhi, "申"))
    out = []
    for i, br in enumerate(ZHI):
        shen = ZHISHEN[(i - start) % 12]
        out.append({"branch": br, "shen": shen,
                    "ji": shen not in ZHISHEN_JI})
    return out


# 冲煞方位写死表（日支索引 → 煞方，通行规则：申子辰日煞南，寅午戌日煞北…）
_SHA_FANG: dict[int, str] = {
    0: "南", 4: "南", 8: "南",          # 子/辰/申
    1: "东", 5: "东", 9: "东",          # 丑/巳/酉
    2: "北", 6: "北", 10: "北",         # 寅/午/戌
    3: "西", 7: "西", 11: "西",         # 卯/未/亥
}


# 事项别名归一（R118b，D-164b）：find_good_days 用精确匹配 affair in
# yi，而宜列表词与前端选项/用户口语可能不一致（实测：前端"婚嫁" vs
# 宜列表"嫁娶"——择日对"婚嫁"永远 0 命中）。别名映射到宜列表的规范词。
AFFAIR_ALIASES: dict[str, str] = {
    "婚嫁": "嫁娶",
    "开市": "开市",
}


def find_good_days(start: datetime, end: datetime,
                   affair: str | list[str]) -> list[dict]:
    """在 [start, end] 区间内找出适宜某事项的日子。

    affair: 婚嫁/开业/出行/动土/搬家/安葬/祭祀/祈福/求嗣/上任/入学/纳财，
    或一串规范词列表（任一命中即收——R229z续8：多词逐日循环一次，
    不再词×天双重扫描）。
    返回 list[day_query result]，只含 affair 在 yi 里的日子。
    """
    terms = ([AFFAIR_ALIASES.get(t, t) for t in affair]
             if isinstance(affair, list)
             else [AFFAIR_ALIASES.get(affair, affair)])   # 别名归一后再匹配
    # R2351（R108-§四.3-2）：宣称域 1900-2100——end 跨界会把 2101 日
    # 推上吉日榜，而该日拿去单日查询又被 400 拒。钳到域内末日。
    end = min(end, datetime(2100, 12, 31))
    good: list[dict] = []
    cur = start
    while cur <= end:
        q = day_query(cur)
        # R228m：宜∩忌双标日剔除——「宜嫁娶也忌嫁娶」的日子不能当吉日推
        # （92 天窗口实测 19 天同项冲忌并存）。
        # R233v（R52-P2-6）：命中口径与聊天事实行统一为双向子串——
        # term「求医」⊂词「求医疗病」这种包含关系两侧不再打架。
        def _hit(tt, words):
            return any(tt in w or w in tt for w in words)
        # R77（R2349n-P2-7）：上榜日忌栏含同义族词也要剔除——
        # 「宜修造忌动土」的日子不算干净的搬家吉日。
        _fam_terms: set[str] = set()
        for _t in terms:
            _fam_terms |= set(_WORD_FAMILY.get(_t, (_t,)))
        if (any(_hit(t, q["yi"]) and not _hit(t, q["ji"]) for t in terms)
                and not any(_hit(t, q["ji"]) for t in _fam_terms)):
            good.append(q)
        cur += timedelta(days=1)
    return good
