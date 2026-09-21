"""神煞层验证探针 — src/guji/huangli.py 的 9 个神煞 + 综合 + 宜忌影响。

规则来源（多源交叉核实）：千里命稿 / 卜筮全书 / 御定星历考原 / 六壬大全。

import 路径用 guji.huangli（sys.path 含 src），不用 src.guji.huangli。
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from datetime import datetime
from guji.huangli import (
    tiande, yuede, tianshe, jiesha, zaisha, yuesha, yueyan, yima, guiren,
    shensha, shensha_yiji, day_query,
    TIAND, YUEYAN,
)


def run():
    # ---- 1. 天德：正月（寅月）= 丁 ----
    dt = datetime(2026, 2, 15)          # 寅月 = 正月
    assert tiande(dt) == "丁", f"tiande 期望 丁，实得 {tiande(dt)!r}"
    # 二月（卯月）= 申
    dt2 = datetime(2026, 3, 15)         # 卯月 = 二月
    assert tiande(dt2) == "申", f"tiande 二月 期望 申，实得 {tiande(dt2)!r}"
    # 数据表完整性
    assert len(TIAND) == 12 and TIAND[0] == "丁" and TIAND[2] == "壬"

    # ---- 2. 月德：寅月（寅午戌→丙）----
    assert yuede(dt) == "丙", f"yuede 寅月 期望 丙，实得 {yuede(dt)!r}"
    # 卯月属亥卯未 → 甲
    assert yuede(dt2) == "甲", f"yuede 卯月 期望 甲，实得 {yuede(dt2)!r}"

    # ---- 3. 天赦：春季戊寅日 ----
    # 2026-03-05 = 戊寅日，寅月属春季 → tianshe=True
    dt_ts = datetime(2026, 3, 5)
    assert tianshe(dt_ts) is True, "tianshe 2026-03-05 戊寅春 期望 True"
    # 非天赦日：2026-02-15 = 庚申
    assert tianshe(dt) is False, "tianshe 2026-02-15 庚申 期望 False"
    # 冬季天赦：甲子日且月支=子/丑/亥
    # 2025-12-21 = 甲子，月支应为子（冬季）—— 单独验甲子日干支
    dt_winter = datetime(2025, 12, 21)
    from guji.huangli import day_ganzhi
    assert day_ganzhi(dt_winter) == ("甲", "子"), f"甲子日核实失败: {day_ganzhi(dt_winter)}"

    # ---- 4. 劫煞：寅月（寅午戌→亥）----
    assert jiesha(dt) == "亥", f"jiesha 寅月 期望 亥，实得 {jiesha(dt)!r}"
    # 卯月（亥卯未→申）
    assert jiesha(dt2) == "申", f"jiesha 卯月 期望 申，实得 {jiesha(dt2)!r}"

    # ---- 5. 灾煞：寅月（寅午戌→子）----
    assert zaisha(dt) == "子", f"zaisha 寅月 期望 子，实得 {zaisha(dt)!r}"
    assert zaisha(dt2) == "酉", f"zaisha 卯月 期望 酉，实得 {zaisha(dt2)!r}"

    # ---- 6. 月煞：寅月（寅午戌→丑）----
    assert yuesha(dt) == "丑", f"yuesha 寅月 期望 丑，实得 {yuesha(dt)!r}"
    assert yuesha(dt2) == "戌", f"yuesha 卯月 期望 戌，实得 {yuesha(dt2)!r}"

    # ---- 7. 月厌：正月（寅月）= 戌 ----
    assert yueyan(dt) == "戌", f"yueyan 正月 期望 戌，实得 {yueyan(dt)!r}"
    assert yueyan(dt2) == "酉", f"yueyan 二月 期望 酉，实得 {yueyan(dt2)!r}"
    assert len(YUEYAN) == 12 and YUEYAN[0] == "戌" and YUEYAN[11] == "亥"

    # ---- 8. 驿马：寅月（寅午戌→申）----
    assert yima(dt) == "申", f"yima 寅月 期望 申，实得 {yima(dt)!r}"
    assert yima(dt2) == "巳", f"yima 卯月 期望 巳，实得 {yima(dt2)!r}"

    # ---- 9. 天乙贵人：甲日→丑未 ----
    # 2026-01-10 = 甲申日
    dt_jia = datetime(2026, 1, 10)
    g, z = day_ganzhi(dt_jia)
    assert g == "甲", f"甲日核实失败: gan={g}"
    assert guiren(dt_jia) == ["丑", "未"], f"guiren 甲日 期望 ['丑','未']，实得 {guiren(dt_jia)!r}"
    # 庚日（2026-02-15）→ 丑未
    assert guiren(dt) == ["丑", "未"], f"guiren 庚日 期望 ['丑','未']，实得 {guiren(dt)!r}"
    # 辛日→寅午；找一个辛日
    dt_xin = datetime(2026, 8, 15)       # 辛酉日
    g2, _ = day_ganzhi(dt_xin)
    assert g2 == "辛" and guiren(dt_xin) == ["寅", "午"], \
        f"guiren 辛日核实失败: {g2}, {guiren(dt_xin)}"

    # ---- 10. shensha 综合 ----
    s = shensha(dt)
    expected_keys = {"tiande", "yuede", "tianshe", "jiesha", "zaisha",
                     "yuesha", "yueyan", "yima", "guiren",
                     "day_gan", "day_zhi", "month_zhi",
                     # R233w：临日判定单点真相（good/bad 名单由后端回吐）
                     "linri"}
    assert set(s.keys()) == expected_keys, f"shensha keys 不符: {set(s.keys())}"
    assert s["day_gan"] == "庚" and s["day_zhi"] == "申" and s["month_zhi"] == "寅"
    assert s["tianshe"] is False
    assert isinstance(s["guiren"], list) and len(s["guiren"]) == 2

    # ---- 11. shensha_yiji 结构 ----
    yi, ji = shensha_yiji(dt)
    assert isinstance(yi, list) and isinstance(ji, list), "shensha_yiji 应返回 (list, list)"
    # 2026-02-15 = 庚申日，month_zhi=寅：驿马=申（与日支同）→ 宜出行/移徙/上任
    assert "出行" in yi and "移徙" in yi and "上任" in yi, \
        f"驿马临日宜项缺失: yi={yi}"
    # 贵人=丑未，日支=申 不临贵人；天德=丁不临日支申；月德=丙不临；劫煞=亥不临
    # 故只应有驿马宜项
    assert "嫁娶" not in yi

    # 天赦日宜项验证（2026-03-05 戊寅春）
    yi_ts, ji_ts = shensha_yiji(dt_ts)
    assert "祭祀" in yi_ts and "祈福" in yi_ts and "求嗣" in yi_ts and "出行" in yi_ts, \
        f"天赦日宜项缺失: yi={yi_ts}"
    assert "诉讼" in ji_ts, f"天赦日忌诉讼缺失: ji={ji_ts}"

    # ---- 12. day_query 集成 ----
    q = day_query(dt)
    assert "shensha" in q, "day_query 应含 'shensha' 字段"
    assert q["shensha"]["day_gan"] == "庚", "day_query.shensha.day_gan 核实失败"
    # 既有字段未破坏
    for k in ("date", "jianchu", "xiu", "pengzu", "yi", "ji"):
        assert k in q, f"day_query 缺既有字段: {k}"

    print("PASS")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
