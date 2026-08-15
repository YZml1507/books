"""bazi — 纯计算排盘模块（公历 → 四柱 / 日主 / 纳音 / 大运方向）。

输入：出生公历年、月、日、时（24 小时制整数小时）、性别（"男"/"女"）。
输出：Bazi dataclass，含
  - year/month/day/hour 四柱干支（干 + 支）
  - day_master 日主（日干）
  - nayin 各柱纳音（年/月/日/时）
  - dayun_dir 大运顺逆（年干阴阳 × 性别：阳男阴女顺、阴男阳女逆）
  - warn 边界警示（出生时刻距节气 ≤ 30 分钟时提示需人工核对）

实现约束（照项目纪律）：
  * 纯标准库（datetime/math），零新依赖——排盘是坐标换算，不产生任何"新文本"。
  * 月柱以十二"节"（立春/惊蛰/清明/立夏/芒种/小暑/立秋/白露/寒露/立冬/大雪/小寒）
    为界，年柱以立春为界——这是子平法的通行口径，不是按公历月。
  * 节气时刻用低精度太阳黄经（Meeus《Astronomical Algorithms》简化式）二分求解，
    精度约 ±15 分钟；出生时刻落在节前后 30 分钟内时置 warn（边界出生需人工核对，
    不假装精确）。日柱用儒略日数 mod 60。
  * 时柱按"五鼠遁"（日干推子时干）；月干按"五虎遁"（年干推寅月干）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"

# 六十甲子纳音表（甲子=0 起，每两个干支一组）
NAYIN60 = [
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金",   # 甲子..癸酉
    "山头火", "涧下水", "城头土", "白蜡金", "杨柳木",   # 甲戌..癸未
    "泉中水", "屋上土", "霹雳火", "松柏木", "长流水",   # 甲申..癸巳
    "沙中金", "山下火", "平地木", "壁上土", "金箔金",   # 甲午..癸卯
    "覆灯火", "天河水", "大驿土", "钗钏金", "桑柘木",   # 甲辰..癸丑
    "大溪水", "沙中土", "天上火", "石榴木", "大海水",   # 甲寅..癸亥
]

# 二十四节气黄经（度）。月柱取"节"（单数位）：立春315 / 惊蛰345 / 清明15 /
# 立夏45 / 芒种75 / 小暑105 / 立秋135 / 白露165 / 寒露195 / 立冬225 / 大雪255 / 小寒285。
TERM_LONGITUDE = {  # 名称 -> 太阳黄经（度，0 = 春分）
    "小寒": 285, "大寒": 300, "立春": 315, "雨水": 330,
    "惊蛰": 345, "春分": 0,   "清明": 15,  "谷雨": 30,
    "立夏": 45,  "小满": 60,  "芒种": 75,  "夏至": 90,
    "小暑": 105, "大暑": 120, "立秋": 135, "处暑": 150,
    "白露": 165, "秋分": 180, "寒露": 195, "霜降": 210,
    "立冬": 225, "小雪": 240, "大雪": 255, "冬至": 270,
}
# 月柱地支随"节"：立春后寅月 .. 小寒后丑月
JIE_TO_ZHI = {"立春": 2, "惊蛰": 3, "清明": 4, "立夏": 5, "芒种": 6,
              "小暑": 7, "立秋": 8, "白露": 9, "寒露": 10, "立冬": 11,
              "大雪": 0, "小寒": 1}   # 地支索引：0=子 .. 11=亥

# 五虎遁：年干 -> 寅月天干（月干 = (base + 月支-寅) % 10）
WUHU = {"甲": 2, "己": 2, "乙": 4, "庚": 4, "丙": 6, "辛": 6,
        "丁": 8, "壬": 8, "戊": 0, "癸": 0}   # 值 = 天干索引（丙=2 戊=4 庚=6 壬=8 甲=0）
# 五鼠遁：日干 -> 子时天干
WUSHU = {"甲": 0, "己": 0, "乙": 2, "庚": 2, "丙": 4, "辛": 4,
         "丁": 6, "壬": 6, "戊": 8, "癸": 8}


@dataclass
class Bazi:
    year: str      # 年柱 干支，如 "甲子"
    month: str     # 月柱
    day: str       # 日柱
    hour: str      # 时柱
    day_master: str   # 日主（日干）
    nayin: list          # [年, 月, 日, 时] 纳音
    dayun_dir: str       # "顺" / "逆"
    warn: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def render(self) -> str:
        line = (f"{self.year}年 {self.month}月 {self.day}日 {self.hour}时"
                f"　日主：{self.day_master}　大运：{self.dayun_dir}")
        if self.warn:
            line += "\n⚠ " + "；".join(self.warn)
        return line


# --------------------------------------------------------------------------------------
# 儒略日数（公历 -> JDN，整数，午正起算）与反向
# --------------------------------------------------------------------------------------
def jdn(y: int, m: int, d: int) -> int:
    """公历 y-m-d -> 儒略日数（整数）。Fliegel–Van Flandern 式。"""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def gregorian(jd: int) -> tuple[int, int, int]:
    """儒略日数 -> 公历 (y, m, d)。"""
    j = jd + 32044
    g = j // 146097
    dg = j % 146097
    c = (dg // 36524 + 1) * 3 // 4
    dc = dg - c * 36524
    b = dc // 1461
    db = dc % 1461
    a = (db // 365 + 1) * 3 // 4
    da = db - a * 365
    y = g * 400 + c * 100 + b * 4 + a
    m = (da * 5 + 308) // 153 - 2
    d = da - (m + 4) * 153 // 5 + 122
    return y, m - 12 * (m > 12), d + 1


# --------------------------------------------------------------------------------------
# 太阳黄经（低精度，Meeus 简化式）与节气时刻求解
# --------------------------------------------------------------------------------------
def _sun_longitude(jde: float) -> float:
    """给定儒略世纪时刻的太阳视黄经（度，[0,360)）。误差约 0.01° ≈ 15 分钟。"""
    t = (jde - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = math.radians(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m)
         + 0.000289 * math.sin(3 * m))
    omega = math.radians(125.04 - 1934.136 * t)
    return (l0 + c - 0.00569 - 0.00478 * math.sin(omega)) % 360.0


def jde_from_dt(dt: datetime) -> float:
    """datetime -> 儒略世纪时刻 JDE（天）。"""
    jd = jdn(dt.year, dt.month, dt.day) - 0.5
    return jd + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24.0


def term_time(year: int, name: str) -> datetime:
    """该公历年内某节气的 UTC 时刻（二分求解黄经交点）。

    太阳黄经一年单调经过每个目标角度一次，所以单峰二分即可；为稳妥在
    [year-01-01, year+1-01-01) 内求解，返回命中年份的那次。
    """
    target = TERM_LONGITUDE[name]
    lo = datetime(year, 1, 1, 0, 0, 0)
    hi = datetime(year + 1, 1, 1, 0, 0, 0)

    def lon_deg(dt: datetime) -> float:
        return _sun_longitude(jde_from_dt(dt))

    # 找目标角度在区间内的一次穿越（处理 0° 附近绕行）
    def gap(dt: datetime) -> float:
        v = lon_deg(dt) - target
        return v if v > -180 else v + 360

    lo_g, hi_g = gap(lo), gap(hi)
    if lo_g * hi_g > 0:
        # 未跨越：可能目标在区间外（不可能，太阳黄经 365 天转一圈），兜底全区间扫描
        step = timedelta(days=8)
        prev, prev_g = lo, lo_g
        cur = lo + step
        while cur < hi:
            cg = gap(cur)
            if prev_g * cg < 0:
                lo, hi, lo_g = prev, cur, prev_g
                break
            prev, prev_g = cur, cg
            cur += step
        else:
            return lo
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        mg = gap(mid)
        if lo_g * mg <= 0:
            hi, hi_g = mid, mg
        else:
            lo, lo_g = mid, mg
    return lo + (hi - lo) / 2


def _is_before(dt: datetime, year: int, name: str) -> bool:
    """dt 是否早于该年该节气时刻（时区按东八区近似处理，见 module 说明）。"""
    t = term_time(year, name) + timedelta(hours=8)   # UTC -> CST
    return dt < t


# --------------------------------------------------------------------------------------
# 四柱推算
# --------------------------------------------------------------------------------------
def _stem_index(gan: str) -> int:
    return GAN.index(gan)


def day_ganzhi(dt: datetime) -> tuple[str, int]:
    """日柱干支 + 六十甲子索引。基准：JDN 与 60 周期的已知对齐点。"""
    idx = (jdn(dt.year, dt.month, dt.day) + 49) % 60
    return GAN[idx % 10] + ZHI[idx % 12], idx


def hour_ganzhi(day_gan: str, hour: int) -> str:
    """时柱：五鼠遁。时支 = (hour+1)//2 % 12（23-1 点子时）。"""
    zhi = (hour + 1) // 2 % 12
    gan = (WUSHU[day_gan] + zhi) % 10
    return GAN[gan] + ZHI[zhi]


def month_ganzhi(year_gan: str, jie_zhi: int) -> str:
    """月柱：五虎遁。jie_zhi = 月支索引（寅=2 .. 丑=1）。

    月序从寅月（正月）起：寅=0, 卯=1, ..., 子=10, 丑=11——即 (jie_zhi - 2) mod 12。
    月干 = 寅月干 + 月序偏移。
    """
    order = (jie_zhi - 2) % 12
    gan = (WUHU[year_gan] + order) % 10
    return GAN[gan] + ZHI[jie_zhi]


def _jie_before(dt: datetime, year: int) -> tuple[str, int] | None:
    """dt 所在的"节"：返回 (节名, 月支索引)。按十二节遍历该年前后的节。"""
    jies = [("立春", 2), ("惊蛰", 3), ("清明", 4), ("立夏", 5), ("芒种", 6),
            ("小暑", 7), ("立秋", 8), ("白露", 9), ("寒露", 10), ("立冬", 11),
            ("大雪", 0), ("小寒", 1)]
    # 收集 [year-1, year+1] 内所有节时刻，取 dt 之前最近的一个
    cands = []
    for y in (year - 1, year, year + 1):
        for name, zhi in jies:
            cands.append((term_time(y, name) + timedelta(hours=8), name, zhi))
    cands.sort()
    for i in range(len(cands)):
        if cands[i][0] > dt:
            break
    if i == 0:
        return None
    t, name, zhi = cands[i - 1]
    return name, zhi


def compute(year: int, month: int, day: int, hour: int,
            gender: str = "男") -> Bazi:
    """主入口：公历生日（hour 为 0..23 整数）-> Bazi。"""
    dt = datetime(year, month, day, hour, 0, 0)

    # 年柱：立春为界。立春前仍属上一干支年。
    # 干支纪年：公历 (y-4) % 10 / (y-4) % 12（甲子=0 对应公历 4 的倍数年）。
    lichun = term_time(year, "立春") + timedelta(hours=8)
    if dt < lichun:
        y_idx = ((year - 1 - 4) % 10, (year - 1 - 4) % 12)
    else:
        y_idx = ((year - 4) % 10, (year - 4) % 12)
    year_pillar = GAN[y_idx[0]] + ZHI[y_idx[1]]

    # 月柱：找 dt 之前最近的"节"
    jie = _jie_before(dt, year)
    if jie is None:
        month_pillar = "??"
        warn0 = "无法确定月柱（数据范围外）"
    else:
        month_pillar = month_ganzhi(year_pillar[0], jie[1])
        warn0 = None

    # 日柱 / 时柱
    day_pillar, day_idx = day_ganzhi(dt)
    hour_pillar = hour_ganzhi(day_pillar[0], hour)

    # 纳音
    def nayin_of(gz: str) -> str:
        g, z = GAN.index(gz[0]), ZHI.index(gz[1])
        # 六十甲子序：s ≡ g (mod 10) 且 s ≡ z (mod 12) 的 CRT 解；每两柱一组纳音。
        s = (6 * g - 5 * z) % 60
        return NAYIN60[s // 2 % 30]

    # 大运顺逆：阳年男/阴年女 顺；阴年男/阳年女 逆。阳干 = 甲丙戊庚壬（索引偶数）
    yang_year = y_idx[0] % 2 == 0
    dayun_dir = "顺" if (yang_year and gender == "男") or (not yang_year and gender == "女") \
        else "逆"

    warns = []
    if warn0:
        warns.append(warn0)
    # 边界警示：dt 距最近节 ≤ 30 分钟
    near = None
    for y in (year - 1, year, year + 1):
        for name in TERM_LONGITUDE:
            t = term_time(y, name) + timedelta(hours=8)
            if abs((dt - t).total_seconds()) <= 1800:
                near = f"{t:%Y-%m-%d %H:%M} {name}"
    if near:
        warns.append(f"出生时刻邻近节气（{near}），月柱/年柱边界需人工核对")

    return Bazi(
        year=year_pillar, month=month_pillar, day=day_pillar, hour=hour_pillar,
        day_master=day_pillar[0],
        nayin=[nayin_of(year_pillar), nayin_of(month_pillar),
               nayin_of(day_pillar), nayin_of(hour_pillar)],
        dayun_dir=dayun_dir,
        warn=warns,
        meta={"gindex_year": y_idx[0] * 12 + y_idx[1],
              "jie": jie[0] if jie else None,
              "jdn": jdn(year, month, day)},
    )


if __name__ == "__main__":
    import sys
    print("usage: python -m guji.bazi   (self-test)")
    # 自检：几个已知日柱基准点
    for (y, m, d, h, g) in [(2000, 1, 1, 12, "男"), (1984, 2, 2, 12, "男"),
                            (2024, 2, 10, 12, "女")]:
        b = compute(y, m, d, h, g)
        print(f"{y}-{m:02d}-{d:02d} {h}:00  ->  {b.render()}  纳音 {b.nayin}")
