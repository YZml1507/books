"""qiming — 起名共享常量模块（R2350a 瘦身）。

活路径：web/services.qiming → classical_names.generate_classical_names。
本模块现存内容：
  * FEMININE_CHARS / MASCULINE_CHARS——性别倾向字池（软偏好打分用，
    R187b；classical_names 引用）。
  * bazi_compute / five_element_counts——re-export（classical_names
    内部 from .qiming import 取这两个名）。

已删死簇（R2350a，selftest 注释 D-198b 记「待删/待标」转正）：
  RADICAL_ELEMENT、CANDIDATE_CHARS、get_element_by_radical、
  get_element_by_char、_gender_score、_full_name_combos、
  name_candidates、__main__ 演示——全部除自身外零调用，活引擎在
  classical_names.py。
"""
from __future__ import annotations

from .bazi import compute as bazi_compute
from .bazi_calc import five_element_counts

__all__ = ["bazi_compute", "five_element_counts",
           "FEMININE_CHARS", "MASCULINE_CHARS"]


# --------------------------------------------------------------------------------------
# 性别倾向表（R187b，specs/006 前置：全名组合的软偏好）
#
# 候选字池人工归类；不在两表中的字视为中性。
# 这是**软偏好**（打分），不是硬排除——女名可以带中性字，男名同理。
# --------------------------------------------------------------------------------------
FEMININE_CHARS: frozenset[str] = frozenset({
    # 木
    "萱", "芷", "薇", "兰", "芳", "芬",
    # 火
    "晴", "暖", "昕", "煦",
    # 土
    "珍", "珠", "琳", "琪", "瑶", "佳",
    # 水
    "沁", "洁", "湘", "潇",
    # 金（R191b，B-015：金字池此前零女性向字——铃/钗为池内新增，
    # 钰/锦是池内已有字的真实女名高频用法，此前漏归类）
    "铃", "钗", "钰", "锦",
})
MASCULINE_CHARS: frozenset[str] = frozenset({
    # 木
    "柏", "栋", "梁", "杰", "松", "楠", "楷", "榕", "荣",
    # 火
    "炎", "煜", "炜", "烨", "焕", "烽", "耀", "辉", "旭", "昱",
    # 土
    "坤", "培", "坚", "城", "基",
    # 金
    "锋", "锐", "钢", "钧", "铠", "铁", "镇",
    # 水
    "浩", "渊", "洋", "沛", "深", "波", "澜",
})


