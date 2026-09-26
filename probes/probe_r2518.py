#!/usr/bin/env python3
"""R2518 — 深度第二轮：六爻场景行动锚 + 塔罗无提问路径指引。

- `_LIUYAO_CAT_STEP` 七类场景各一件卦外能做的小事；收口与经文指针
  合并不挤 lines[:6]。
- 塔罗无提问路径：kw 后挂 `_TAROT_KW_GUIDANCE` 行动句（不再只露
  原始 kw 串）；`_tarot_kw_guidance` no-q 回落先查表再给 meta 句。
"""
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "src")   # guji 包内互导
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


from src.guji import voice  # noqa: E402

# --- 1. 场景表覆盖全部七类 ---
cats = {cat for _p, _y, _n, cat in voice._LIUYAO_SCENE}
ck("step.all_cats", cats <= set(voice._LIUYAO_CAT_STEP))
ck("step.nonempty",
   all(len(v) >= 10 for v in voice._LIUYAO_CAT_STEP.values()))

# --- 2. 六爻：有场景提问 → 收口带行动句 ---
_pp = {"ben_gua": {"shi": 3, "ying": 6, "lines": [
    {"position": i, "liuqin": lq} for i, lq in enumerate(
        ["父母", "兄弟", "官鬼", "子孙", "妻财", "官鬼"], 1)]}}
_hit = voice.reply_liuyao({"gua_number": 11, "gua_name": "泰"},
                          {"gua_number": 34, "gua_name": "大壮"},
                          [3], "跳槽要不要跳", paipan=_pp)
ck("ly.step_present",
   any("能做的最实一步" in l for l in _hit))
ck("ly.scripture_kept",
   any("卦辞爻辞的原文在下面" in l for l in _hit))
ck("ly.cap6", len(_hit) <= 6)

# --- 3. 无场景提问 → 原收口兜底 ---
_noq = voice.reply_liuyao({"gua_number": 11, "gua_name": "泰"},
                          {"gua_number": 0, "gua_name": ""},
                          [], "", paipan={})
ck("ly.noq_fallback",
   any("慢慢体会" in l for l in _noq))

# --- 4. 塔罗无提问路径：指引句上屏 ---
_cards = [{"name": "星币9", "upright": False, "upright_kw": "累积",
           "reversed_kw": "收尾难·差口气·撑住", "meaning": "x"}]
_r = voice.warm_tarot(_cards, {"sections": []}, None)
ck("tr.noq_guidance",
   any("别耗在最后一公里" in l for l in _r["reply"]))
# 有提问路径不受影响（原有指引仍在）
_r2 = voice.warm_tarot(_cards, {"sections": []}, "工作的事")
ck("tr.q_guidance",
   any("别耗在最后一公里" in l for l in _r2["reply"]))

# --- 5. kw_guidance no-q 回落：表里有 → 行动句；表外 → meta 句 ---
ck("kw.noq_table",
   voice._tarot_kw_guidance("收尾难", "") == "就差临门一脚，别耗在最后一公里")
ck("kw.noq_fallback",
   "提示你关注" in voice._tarot_kw_guidance("不存在的词", ""))

# --- 6. 危机/敏感提问三入口同闸（R2518 补 _is_crisis）---
ck("ly.sensitive",
   "卦面真答不了" in "".join(
       voice.reply_liuyao({}, {}, [], "我活不下去了", paipan={})))
ck("ly.crisis_hard",
   "卦面真答不了" in "".join(
       voice.reply_liuyao({}, {}, [], "癌症晚期还能活多久", paipan={})))
ck("tr.crisis",
   "牌面真接不了" in "".join(
       voice.warm_tarot([], {}, "我不想活了")["reply"]))
ck("bz.crisis",
   "盘里真接不了" in "".join(
       voice.reply_bazi("庚", {"ten_gods": [], "five_elements": {},
                               "relations": [], "day_luck": {}},
                        "我活不下去了", gender="女")))
# 撒娇豁免不破——「想死你了」不该转介
ck("bz.not_crisis",
   "盘里真接不了" not in "".join(
       voice.reply_bazi("庚", {"ten_gods": [], "five_elements": {},
                               "relations": [], "day_luck": {}},
                        "想死你了我们什么时候见面", gender="女")))

print(f"\n{len(PASS)} checks, {len(FAIL)} failed: {FAIL}")
sys.exit(1 if FAIL else 0)
