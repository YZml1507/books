#!/usr/bin/env python3
"""R2516 — 内容深度升级钉扎（用户反馈「讲解太浅/小满泛泛」）。

深度 = 场景锚点 + 可照做的动作 + 留意点（调研结论）。本轮：
1. voice.py 十神补第三维 TEN_GOD_ACTION（适合+留意）；
   reply_bazi 命中位收口从免责池换行动句；
   未命中补 TOPIC_HINT 话题级通用一步；
   「今天的气氛偏…」三处同行内挂「今天适合：…」。
2. llm_polish._CHAT_SYSTEM 加具体性硬规则。
3. app.js CHAT_LAST_FACTS 注入盘面解读句（前端坐标侧）。
"""
import re
import sys

sys.path.insert(0, ".")
PASS, FAIL = [], []


def ck(name, cond, note=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {note}" if note else ""))


from src.guji import voice  # noqa: E402

# --- 1. TEN_GOD_ACTION 完备性：十神全覆盖、每项是（适合, 留意）二联 ---
gods = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]
ck("action.all_gods",
   all(g in voice.TEN_GOD_ACTION for g in gods) and len(voice.TEN_GOD_ACTION) == 10)
ck("action.shape",
   all(isinstance(voice.TEN_GOD_ACTION[g], tuple) and len(voice.TEN_GOD_ACTION[g]) == 2
       and all(isinstance(s, str) and len(s) >= 6 for s in voice.TEN_GOD_ACTION[g])
       for g in gods))
# 动作句不许是空泛词——抽查不含「看开点/都会好的/顺其自然」
ck("action.not_generic",
   not any(bad in "".join(voice.TEN_GOD_ACTION[g])
           for g in gods for bad in ("看开点", "都会好的", "顺其自然")))

# --- 2. TOPIC_HINT 覆盖全部话题 label ---
labels = {lbl for _kw, _g, lbl in voice.TOPIC_WARM}
ck("hint.covers_labels", labels <= set(voice.TOPIC_HINT))

# --- 3. reply_bazi 命中位：收口是行动句而非免责池 ---
_calc = {
    "ten_gods": [{"god": "正印", "pos": "年干", "gan": "甲"}],
    "five_elements": {}, "relations": [], "day_luck": {},
}
_hit = voice.reply_bazi("庚", _calc, "考研能上岸吗", gender="女")
ck("hit.action_line",
   any(l.startswith("顺着这个位置走：") for l in _hit))
ck("hit.no_disclaimer_pool",
   not any(("看你自己的选择" in l) or ("看你心意" in l) or ("步子你来定" in l)
           for l in _hit))
_act = voice.TEN_GOD_ACTION["正印"]
ck("hit.action_content",
   any(_act[0] in l and _act[1] in l for l in _hit))

# --- 4. reply_bazi 未命中：TOPIC_HINT 落地、诚信保留 ---
_miss = voice.reply_bazi("庚", {"ten_gods": [], "five_elements": {},
                                "relations": [], "day_luck": {}},
                         "我和他的感情呢", gender="女")
ck("miss.honesty_kept", any(("不瞎编" in l) or ("不硬说" in l) or ("不猜" in l)
                            for l in _miss))
ck("miss.topic_hint", any(voice.TOPIC_HINT["感情"] in l for l in _miss))

# --- 5. 「今天适合」同行挂在气氛句后（防 lines[:5] 截断）---
_dl_calc = {"ten_gods": [], "five_elements": {}, "relations": [],
            "day_luck": {"day_master_rel": "庚日主之食神"}}
_noq = voice._reply_no_question("庚", _dl_calc)
_atm = [l for l in _noq if "今天的气氛偏" in l]
ck("atm.inline_action",
   len(_atm) == 1 and "今天适合：" in _atm[0]
   and voice.TEN_GOD_ACTION["食神"][0] in _atm[0])

# --- 6. 未识别话题：指路保留 + 空力量不出悬空冒号 ---
_unk = voice.reply_bazi("庚", {"ten_gods": [], "five_elements": {},
                              "relations": [], "day_luck": {}},
                        "量子力学怎么解释", gender="女")
ck("unk.points_topics", any("换个问法盘里都能接住" in l for l in _unk))
ck("unk.no_dangling_colon", not any(l.rstrip().endswith("：。") for l in _unk))

# --- 7. _CHAT_SYSTEM 具体性硬规则 ---
from src.guji import llm_polish  # noqa: E402
ck("chat.specificity_rule",
   "不许只回正确的话" in llm_polish._CHAT_SYSTEM
   and "都会好的" in llm_polish._CHAT_SYSTEM)

# --- 8. app.js 坐标注入盘面解读 ---
_src = open("web/static/app.js", encoding="utf-8").read()
ck("js.reply_into_facts",
   "盘面解读：" in _src and re.search(r"CHAT_LAST_FACTS\.push\('盘面解读：'", _src))

# --- 9. 审-P2-1：删除不存在收藏如实 404（不假 ok）---
from src.guji.knowledge import KnowledgeBase  # noqa: E402
import tempfile, os  # noqa: E402

_fd, _tmp = tempfile.mkstemp(suffix=".db")
os.close(_fd)
try:
    _kb = KnowledgeBase(_tmp)
    ck("fav.delete_missing_false", _kb.remove_favorite(999999) is False)
    _id = _kb.add_favorite("bazi", "probe-r2516", "测")
    ck("fav.delete_real_true", _kb.remove_favorite(_id) is True)
    _kb.db.close()
finally:
    os.unlink(_tmp)
_svc = open("web/services.py", encoding="utf-8").read()
ck("fav.service_404",
   re.search(r"def remove_favorite[\s\S]{0,300}NotFoundError", _svc))

print(f"\n{len(PASS)} checks, {len(FAIL)} failed: {FAIL}")
sys.exit(1 if FAIL else 0)
