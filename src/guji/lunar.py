"""lunar — 农历 ↔ 公历转换（1900-2100，纯标准库，数据可核验）。

用户需求（2026-08-15）：日期输入既支持阳历（公历）也支持农历（阴历）。
排盘本身以公历 + 太阳黄经节气为基准（bazi.py），农历只是**输入层换算**：
农历日期 → 公历日期后走既有 compute()，不改变排盘算法。

数据来源：经典农历信息表 LUNAR_INFO（1900-2100 共 201 项，通行公开数据，
lunar_python / cnlunar 等库同源）。每年编码为一个整数：
  * 低 4 位（&0xF）         ：闰月月份（0 = 无闰月）
  * bit16（&0x10000）        ：闰月为 30 天（否则 29）
  * bits 15..4（0x8000..0x10）：正月..十二月各月是否大月（1 = 30 天，
    基准 12*29=348 天，每大月 +1）
公历基准日：1900-01-31 = 农历 1900 正月初一（庚子年春节，公认）。

验证基准（公认公历春节，2026-08 时点公开常识）：
  2000-02-05 = 2000 正月初一（庚辰） 2023-01-22 = 2023 正月初一（癸卯）
  2024-02-10 = 2024 正月初一（甲辰） 2025-01-29 = 2025 正月初一（乙巳）
  2026-02-17 = 2026 正月初一（丙午）
闰月基准：2023 闰二月、2025 闰六月、2017 闰六月、2020 闰四月。
"""
from __future__ import annotations

from datetime import date, timedelta

LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,  # 1900-1909
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,  # 1910-1919
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,  # 1920-1929
    0x06566, 0x0d4a0, 0x0ea50, 0x16a95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,  # 1930-1939
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,  # 1940-1949
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,  # 1950-1959
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,  # 1960-1969
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,  # 1970-1979
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,  # 1980-1989
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,  # 1990-1999
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,  # 2000-2009
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,  # 2010-2019
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,  # 2020-2029
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,  # 2030-2039
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,  # 2040-2049
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,  # 2050-2059
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,  # 2060-2069
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,  # 2070-2079
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,  # 2080-2089
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,  # 2090-2099
    0x0d520,                                                                                     # 2100
]

BASE_SOLAR = date(1900, 1, 31)   # 农历 1900 正月初一（庚子年春节）
MONTH_CN = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "冬", "腊"]
DAY_CN = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八",
          "初九", "初十", "十一", "十二", "十三", "十四", "十五", "十六",
          "十七", "十八", "十九", "二十", "廿一", "廿二", "廿三", "廿四",
          "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"


def leap_month(y: int) -> int:
    """该农历年的闰月月份（0 = 无闰月）。"""
    return LUNAR_INFO[y - 1900] & 0xF


def leap_days(y: int) -> int:
    """闰月天数（30 或 29）。"""
    if not leap_month(y):
        return 0
    return 30 if (LUNAR_INFO[y - 1900] & 0x10000) else 29


def month_days(y: int, m: int) -> int:
    """农历 y 年第 m 月（非闰月）天数。bit15(0x8000)=正月 .. bit4(0x10)=十二月。"""
    return 30 if (LUNAR_INFO[y - 1900] & (0x10000 >> m)) else 29


def year_days(y: int) -> int:
    """农历 y 年总天数：基准 348（12*29），每大月 +1，另加闰月。"""
    total = 348
    info = LUNAR_INFO[y - 1900]
    bit = 0x8000
    while bit >= 0x10:          # 0x8000..0x10 共 12 个月
        if info & bit:
            total += 1
        bit >>= 1
    return total + leap_days(y)


def solar_to_lunar(y: int, m: int, d: int) -> dict:
    """公历 y-m-d -> 农历 {year, month, day, is_leap, month_cn, day_cn,
    ganzhi_year, ganzhi_year_cn}。范围外抛 ValueError。"""
    if not (1900 <= y <= 2100):
        raise ValueError(f"农历转换仅支持 1900-2100（收到 {y}）")
    target = date(y, m, d)
    if target < BASE_SOLAR:
        raise ValueError(f"{y}-{m:02d}-{d:02d} 早于农历表起点 1900-01-31")
    offset = (target - BASE_SOLAR).days
    ly = 1900
    while offset >= year_days(ly):
        offset -= year_days(ly)
        ly += 1
        if ly > 2100:
            raise ValueError("超出农历表范围")
    # offset 现在是农历年内第几天（0 起）。逐月推进（含闰月插入）。
    leap = leap_month(ly)
    lm, is_leap = 1, False
    while True:
        cur = leap_days(ly) if (is_leap and lm == leap) else month_days(ly, lm)
        if offset < cur:
            break
        offset -= cur
        if leap and lm == leap and not is_leap:
            is_leap = True        # 闰月接在同月份（非闰）之后
        else:
            lm += 1
            is_leap = False
    ld = offset + 1
    gz_year = (ly - 4) % 60
    month_cn = ("闰" if is_leap else "") + MONTH_CN[lm - 1] + "月"
    return {
        "year": ly, "month": lm, "day": ld, "is_leap": is_leap,
        "month_cn": month_cn, "day_cn": DAY_CN[ld - 1],
        "ganzhi_year": GAN[gz_year % 10] + ZHI[gz_year % 12],
        "ganzhi_year_cn": f"{GAN[gz_year % 10]}{ZHI[gz_year % 12]}年",
    }


def lunar_to_solar(ly: int, lm: int, ld: int, is_leap: bool = False) -> date:
    """农历 ly 年 lm 月 ld 日（is_leap 是否闰月）-> 公历 date。

    R229z续24（R9-P2-3 定义域不对称声明）：输入农历年 ≤2100，但农历 2100
    年腊月初二~廿九映射到公历 2101-01/02——返回值可越出 solar_to_lunar
    的 1900-2100 接收域（反向再转会 ValueError）。下游干支/节气走天文
    算法不受表界限制；调用方需要「可回读」语义时应自行框界。"""
    if not (1900 <= ly <= 2100):
        raise ValueError(f"农历年份需在 1900-2100（收到 {ly}）")
    if not (1 <= lm <= 12):
        raise ValueError("农历月份需在 1-12")
    leap = leap_month(ly)
    if is_leap and leap != lm:
        raise ValueError(f"{ly} 年没有闰{lm}月（该年闰月是{leap}月）")
    if not (1 <= ld <= (leap_days(ly) if (is_leap and lm == leap)
                         else month_days(ly, lm))):
        raise ValueError(f"农历 {ly} 年{'闰' if is_leap else ''}{lm}月没有第 {ld} 天")
    # 累计该农历年之前所有年的天数
    offset = sum(year_days(y) for y in range(1900, ly))
    # 逐月推进到目标月（含闰月插入），再落到日
    cur_lm, cur_leap = 1, False
    while (cur_lm, cur_leap) != (lm, is_leap):
        offset += leap_days(ly) if (cur_leap and cur_lm == leap) \
            else month_days(ly, cur_lm)
        if leap and cur_lm == leap and not cur_leap:
            cur_leap = True       # 先非闰月后闰月
        else:
            cur_lm += 1
            cur_leap = False
    offset += ld - 1
    return BASE_SOLAR + timedelta(days=offset)


if __name__ == "__main__":
    # 基准：公认公历春节（2026-08 时点公开常识）
    cases = [
        ((2000, 2, 5), (2000, 1, 1, False, "庚辰")),
        ((2023, 1, 22), (2023, 1, 1, False, "癸卯")),
        ((2024, 2, 10), (2024, 1, 1, False, "甲辰")),
        ((2025, 1, 29), (2025, 1, 1, False, "乙巳")),
        ((2026, 2, 17), (2026, 1, 1, False, "丙午")),
    ]
    for (y, m, d), (ly, lm, ld, leap, gz) in cases:
        r = solar_to_lunar(y, m, d)
        assert r["year"] == ly and r["month"] == lm and r["day"] == ld \
            and r["is_leap"] == leap, (y, m, d, r)
        assert r["ganzhi_year"] == gz, (y, m, d, r["ganzhi_year"], gz)
        back = lunar_to_solar(ly, lm, ld, leap)
        assert back == date(y, m, d), (ly, lm, ld, back)
    # 闰月基准：2023 闰二月、2025 闰六月、2020 闰四月、2017 闰六月
    assert leap_month(2023) == 2 and leap_month(2025) == 6
    assert leap_month(2020) == 4 and leap_month(2017) == 6
    r = solar_to_lunar(2023, 3, 22)     # 2023 闰二月初一（公认）
    assert r["is_leap"] and r["month"] == 2, r
    r2 = solar_to_lunar(2025, 7, 25)    # 2025 闰六月初一（公认）
    assert r2["is_leap"] and r2["month"] == 6, r2
    # 往返一致：扫描 1900-2060 内 110 个抽样点
    for dd in range(0, 365 * 160, 527):
        d0 = BASE_SOLAR + timedelta(days=dd)
        lr = solar_to_lunar(d0.year, d0.month, d0.day)
        back = lunar_to_solar(lr["year"], lr["month"], lr["day"], lr["is_leap"])
        assert back == d0, (d0, lr, back)
    print("lunar.py 基准全部通过（5 春节 + 4 闰月 + 110 抽样往返）")
