"""六爻运算层验证探针。

验证 liuyao.py 新增的运算层：
  - najia: 纳甲（天干地支配六爻）
  - liuqin: 六亲（按宫五行与爻五行生克定六亲）
  - shiying: 世应（按宫内位置定世爻/应爻）
  - liushen: 六神（按日干起六神）
  - paipan: 综合排盘

所有规则已核实（天机爻Wiki、卜筮正宗、纳甲歌、Dao Oracle、OldBird，多源交叉验证）。
验证数据来源：传统六爻标准规则，见上方各函数文档。

验证通过 print('PASS') 并 sys.exit(0)；失败 sys.exit(1)。
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from guji.liuyao import (
    Hexagram,
    Yao,
    GUA_TO_GONG,
    GONG_WUXING,
    GUA_GONG_POSITION,
    najia,
    liuqin,
    shiying,
    liushen,
    paipan,
)


def _make_qian() -> Hexagram:
    """构造乾卦（文王序1，六爻全阳，无动爻）。"""
    lines = [Yao(yang=True, moving=False, position=p) for p in range(1, 7)]
    return Hexagram(lines=lines, gua_number=1, gua_name="乾", moving_lines=[])


def _make_kun() -> Hexagram:
    """构造坤卦（文王序2，六爻全阴，无动爻）。"""
    lines = [Yao(yang=False, moving=False, position=p) for p in range(1, 7)]
    return Hexagram(lines=lines, gua_number=2, gua_name="坤", moving_lines=[])


def test_qian_najia():
    """1. 乾卦纳甲：初甲子,二甲寅,三甲辰,四壬午,五壬申,上壬戌。"""
    qian = _make_qian()
    result = najia(qian)
    expected = [
        (1, "甲", "子"),
        (2, "甲", "寅"),
        (3, "甲", "辰"),
        (4, "壬", "午"),
        (5, "壬", "申"),
        (6, "壬", "戌"),
    ]
    actual = [(r["position"], r["heavenly_stem"], r["earthly_branch"]) for r in result]
    assert actual == expected, f"乾卦纳甲不符: {actual} != {expected}"


def test_kun_najia():
    """2. 坤卦纳甲：初乙未,二乙巳,三乙卯,四癸丑,五癸亥,上癸酉。"""
    kun = _make_kun()
    result = najia(kun)
    expected = [
        (1, "乙", "未"),
        (2, "乙", "巳"),
        (3, "乙", "卯"),
        (4, "癸", "丑"),
        (5, "癸", "亥"),
        (6, "癸", "酉"),
    ]
    actual = [(r["position"], r["heavenly_stem"], r["earthly_branch"]) for r in result]
    assert actual == expected, f"坤卦纳甲不符: {actual} != {expected}"


def test_qian_liuqin():
    """3. 乾卦六亲：乾宫=金，六亲依次为子孙/妻财/父母/官鬼/兄弟/父母。"""
    qian = _make_qian()
    result = liuqin(qian)
    # 乾宫=金
    # 初爻子(水)：金生水=子孙
    # 二爻寅(木)：金克木=妻财
    # 三爻辰(土)：土生金=父母
    # 四爻午(火)：火克金=官鬼
    # 五爻申(金)：同我=兄弟
    # 上爻戌(土)：土生金=父母
    expected = [
        (1, "子孙", "水"),
        (2, "妻财", "木"),
        (3, "父母", "土"),
        (4, "官鬼", "火"),
        (5, "兄弟", "金"),
        (6, "父母", "土"),
    ]
    actual = [(r["position"], r["liuqin"], r["wuxing"]) for r in result]
    assert actual == expected, f"乾卦六亲不符: {actual} != {expected}"


def test_qian_shiying():
    """4. 乾卦世应：乾=本宫卦，世=6（上爻），应=3（三爻）。"""
    qian = _make_qian()
    result = shiying(qian)
    assert result["shi"] == 6, f"乾卦世爻应为6，实际{result['shi']}"
    assert result["ying"] == 3, f"乾卦应爻应为3，实际{result['ying']}"
    assert result["gong"] == "乾", f"乾卦宫名应为乾，实际{result['gong']}"
    assert result["gong_position"] == "本宫", f"乾卦宫位应为本宫，实际{result['gong_position']}"
    assert result["gong_wuxing"] == "金", f"乾宫五行应为金，实际{result['gong_wuxing']}"


def test_liushen():
    """5. 六神排布：甲日初爻青龙，自下而上排6个：青龙朱雀勾陈螣蛇白虎玄武。"""
    result = liushen("甲")
    expected = [
        (1, "青龙"), (2, "朱雀"), (3, "勾陈"),
        (4, "螣蛇"), (5, "白虎"), (6, "玄武"),
    ]
    actual = [(r["position"], r["shen"]) for r in result]
    assert actual == expected, f"甲日六神不符: {actual} != {expected}"


def test_gua_to_gong():
    """6. 八宫归属抽查：八纯卦 + 游魂卦 + 归魂卦。"""
    # 八纯卦
    assert GUA_TO_GONG[1] == "乾", f"1乾应属乾宫，实际{GUA_TO_GONG[1]}"
    assert GUA_TO_GONG[2] == "坤", f"2坤应属坤宫，实际{GUA_TO_GONG[2]}"
    assert GUA_TO_GONG[29] == "坎", f"29坎应属坎宫，实际{GUA_TO_GONG[29]}"
    assert GUA_TO_GONG[30] == "离", f"30离应属离宫，实际{GUA_TO_GONG[30]}"
    assert GUA_TO_GONG[51] == "震", f"51震应属震宫，实际{GUA_TO_GONG[51]}"
    assert GUA_TO_GONG[52] == "艮", f"52艮应属艮宫，实际{GUA_TO_GONG[52]}"
    assert GUA_TO_GONG[57] == "巽", f"57巽应属巽宫，实际{GUA_TO_GONG[57]}"
    assert GUA_TO_GONG[58] == "兑", f"58兑应属兑宫，实际{GUA_TO_GONG[58]}"

    # 游魂卦抽查
    assert GUA_TO_GONG[35] == "乾", f"35晋应属乾宫，实际{GUA_TO_GONG[35]}"
    assert GUA_GONG_POSITION[35] == "游魂", f"35晋宫位应为游魂，实际{GUA_GONG_POSITION[35]}"
    assert GUA_TO_GONG[36] == "坎", f"36明夷应属坎宫，实际{GUA_TO_GONG[36]}"
    assert GUA_GONG_POSITION[36] == "游魂", f"36明夷宫位应为游魂，实际{GUA_GONG_POSITION[36]}"

    # 归魂卦抽查
    assert GUA_TO_GONG[14] == "乾", f"14大有应属乾宫，实际{GUA_TO_GONG[14]}"
    assert GUA_GONG_POSITION[14] == "归魂", f"14大有宫位应为归魂，实际{GUA_GONG_POSITION[14]}"
    assert GUA_TO_GONG[7] == "坎", f"7师应属坎宫，实际{GUA_TO_GONG[7]}"
    assert GUA_GONG_POSITION[7] == "归魂", f"7师宫位应为归魂，实际{GUA_GONG_POSITION[7]}"

    # 宫五行抽查
    assert GONG_WUXING["乾"] == "金"
    assert GONG_WUXING["兑"] == "金"
    assert GONG_WUXING["离"] == "火"
    assert GONG_WUXING["震"] == "木"
    assert GONG_WUXING["巽"] == "木"
    assert GONG_WUXING["坎"] == "水"
    assert GONG_WUXING["艮"] == "土"
    assert GONG_WUXING["坤"] == "土"

    # 全表完整性：64卦每卦都有宫名 + 宫位
    assert len(GUA_TO_GONG) == 64, f"GUA_TO_GONG应有64条，实际{len(GUA_TO_GONG)}"
    assert len(GUA_GONG_POSITION) == 64, f"GUA_GONG_POSITION应有64条，实际{len(GUA_GONG_POSITION)}"
    for num in range(1, 65):
        assert num in GUA_TO_GONG, f"文王序{num}缺失宫名"
        assert num in GUA_GONG_POSITION, f"文王序{num}缺失宫位"


def test_paipan():
    """7. 综合排盘：起一卦（固定种子），调paipan，验证返回dict结构完整。"""
    rng = random.Random(42)
    h = None
    # 起卦直到有动爻（固定种子下可复现）
    for _ in range(10):
        from guji.liuyao import cast_coins
        h = cast_coins(rng)
        if h.moving_lines:
            break

    assert h is not None, "起卦失败"
    assert h.moving_lines, f"应有动爻，实际moving_lines={h.moving_lines}"

    pp = paipan(h, "甲")

    # 顶层结构
    assert "ben_gua" in pp, "paipan缺ben_gua"
    assert "bian_gua" in pp, "paipan缺bian_gua"
    assert "moving_lines" in pp, "paipan缺moving_lines"
    assert pp["moving_lines"] == h.moving_lines

    # 本卦结构
    bg = pp["ben_gua"]
    for key in ["gua_number", "gua_name", "gong", "gong_wuxing",
                "gong_position", "shi", "ying", "lines"]:
        assert key in bg, f"ben_gua缺{key}"
    assert bg["gua_number"] == h.gua_number
    assert bg["gua_name"] == h.gua_name
    assert len(bg["lines"]) == 6, f"ben_gua应有6爻，实际{len(bg['lines'])}"

    # 本卦每爻结构（含世应/六神/纳甲/六亲）
    for line in bg["lines"]:
        for key in ["position", "yang", "moving", "stem", "branch",
                    "wuxing", "liuqin", "is_shi", "is_ying", "shen"]:
            assert key in line, f"ben_gua爻缺{key}: {line}"
        # 世应标记：恰好一爻is_shi=True，一爻is_ying=True
    shi_lines = [l for l in bg["lines"] if l["is_shi"]]
    ying_lines = [l for l in bg["lines"] if l["is_ying"]]
    assert len(shi_lines) == 1, f"世爻应恰好1个，实际{len(shi_lines)}"
    assert len(ying_lines) == 1, f"应爻应恰好1个，实际{len(ying_lines)}"
    assert shi_lines[0]["position"] == bg["shi"], "世爻位不一致"
    assert ying_lines[0]["position"] == bg["ying"], "应爻位不一致"

    # 变卦结构（无世应/六神，但算纳甲/六亲）
    bi = pp["bian_gua"]
    for key in ["gua_number", "gua_name", "gong", "gong_wuxing",
                "gong_position", "lines"]:
        assert key in bi, f"bian_gua缺{key}"
    assert len(bi["lines"]) == 6, f"bian_gua应有6爻，实际{len(bi['lines'])}"
    for line in bi["lines"]:
        for key in ["position", "yang", "moving", "stem", "branch",
                    "wuxing", "liuqin"]:
            assert key in line, f"bian_gua爻缺{key}: {line}"
        # 变卦不排六神
        assert "shen" not in line, "变卦不应有六神"

    # 变卦卦号 != 本卦卦号（有动爻时）
    if h.moving_lines:
        assert bi["gua_number"] != bg["gua_number"], "有动爻时变卦应不同于本卦"


def main():
    tests = [
        test_qian_najia,
        test_kun_najia,
        test_qian_liuqin,
        test_qian_shiying,
        test_liushen,
        test_gua_to_gong,
        test_paipan,
    ]
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            sys.exit(1)
    print("PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
