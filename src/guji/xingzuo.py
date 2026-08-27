"""xingzuo — 十二宫日运（004 M2 T2.1，specs/004-warm-voice US4）。

规则（全部写死可核验，D-148a：十二宫内容就是古籍内容，不隔离）：

  * 今名 ↔ 古籍名映射（传统名 ↔ 今名）：
      白羊=戌=白羊宫、金牛=酉=金牛宫、双子=申=隂陽宫、巨蟹=未=巨蟹宫、
      狮子=午=獅子宫、处女=巳=雙女宫、天秤=辰=天秤宫、天蝎=卯=天蝎宫、
      射手=寅=人馬宫、摩羯=丑=磨蝎宫、水瓶=子=寶瓶宫、双鱼=亥=雙魚宫
  * 日运规则（写死）：以**当日日支**查上表得「今日值宫」，
    每宫配一段写死的温柔文案 + 一条真实语料引文锚点。
    引文锚点已逐条在 corpus.db 逐字命中（T2.2，见 web/baselines/xingzuo_fixture.json）。

  * 锚点出处（《星學大成》KR3g0041 十二宫神表，卷二十一/十七）：
      人馬宫天威星 / 天蝎宫武庫星 / 天秤宫地暗星 / 雙女宫地隔星 /
      獅子宫龍首星 / 巨蟹宫暗金星 / 隂陽宫天廢星 / 金牛宫祼形星 /
      白羊宫都官星 / 雙魚宫天煞星 —— KR3g0041_WYG_021-26b
      磨蝎宫沉晦星 —— KR3g0041_WYG_017-29a
      寶瓶宫（火星变段名寶瓶宫天暴星同页序列）—— KR3g0041_WYG_015-29b

红线遵守：
  * 纯函数：无 IO、无网络、无随机、不读时钟；"今天"由调用方传入。
  * 文案写死在本模块，事实（宫名/星名/引文）来自语料锚点——不生成新命理断言。
  * 输出只随响应返回、只落 history.db（D-039），不进 corpus/knowledge。

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe -m guji.xingzuo     # 本模块自测
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 今名 → (古籍宫名, 宫星名, 引文锚点, 温柔文案)
# 锚点 = (work_id, page_anchor, needle)：needle 必须能在该页文本中逐字命中
# （web/check_xingzuo.py 判据 10 的可追溯性依据）。
# ---------------------------------------------------------------------------
SIGNS: dict[str, dict] = {
    "白羊": {
        "palace": "白羊宫", "star": "都官星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "白羊宫都官星"),
        "note": "今天适合把心里的话说出口——你的直率自带说服力。",
        "love": "直接表达心意，今天说出口成功率翻倍。",
        "career": "行动力在线，适合推进卡住的项目。",
        "wealth": "财运平稳，适合做理财规划。",
    },
    "金牛": {
        "palace": "金牛宫", "star": "祼形星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "金牛宫祼形星"),
        "note": "节奏放慢一点也没关系，稳稳的你最有魅力。",
        "love": "稳定的吸引力，今天适合深度交流。",
        "career": "踏实做事，你的认真会被看见。",
        "wealth": "财运不错，适合谈加薪或投资。",
    },
    "双子": {
        "palace": "隂陽宫", "star": "天廢星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "隂陽宫天廢星"),
        "note": "脑子转得快的日子，把灵感记下来会有惊喜。",
        "love": "聊天运旺，和喜欢的人话题不断。",
        "career": "灵感多，适合头脑风暴和创意工作。",
        "wealth": "小财运，可能有意外收入。",
    },
    "巨蟹": {
        "palace": "巨蟹宫", "star": "暗金星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "巨蟹宫暗金星"),
        "note": "照顾别人之前，先给自己倒杯水。",
        "love": "温柔体贴，今天适合关心喜欢的人。",
        "career": "团队合作顺利，你的细心帮了大忙。",
        "wealth": "适合存钱，今天有省钱机会。",
    },
    "狮子": {
        "palace": "獅子宫", "star": "龍首星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "獅子宫龍首星"),
        "note": "发光的日子，站在人群里也藏不住。",
        "love": "魅力四射，今天适合约会或表白。",
        "career": "领导力凸显，适合做决策。",
        "wealth": "大方但别冲动消费。",
    },
    "处女": {
        "palace": "雙女宫", "star": "地隔星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "雙女宫地隔星"),
        "note": "细节控的胜利——今天你的仔细会被人看见。",
        "love": "细心观察，发现对方的小变化。",
        "career": "完美主义加分，工作质量高。",
        "wealth": "精打细算，适合做预算。",
    },
    "天秤": {
        "palace": "天秤宫", "star": "地暗星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "天秤宫地暗星"),
        "note": "纠结的时候抛硬币，不是要它替你决定，是抛到一半你就知道答案了。",
        "love": "平衡感好，适合处理感情问题。",
        "career": "协调能力强，适合谈判。",
        "wealth": "收支平衡，避免冲动购物。",
    },
    "天蝎": {
        "palace": "天蝎宫", "star": "武庫星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "天蝎宫武庫星"),
        "note": "直觉很准的一天，相信第一感觉。",
        "love": "神秘感吸引对方，今天适合深度交流。",
        "career": "洞察力强，能看穿问题本质。",
        "wealth": "偏财运好，可能有意外收获。",
    },
    "射手": {
        "palace": "人馬宫", "star": "天威星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "人馬宫天威星"),
        "note": "想出发就出发，今天的你走哪条路都对。",
        "love": "乐观开朗，吸引志同道合的人。",
        "career": "冒险精神适合开拓新领域。",
        "wealth": "远见带来财运，适合长期投资。",
    },
    "摩羯": {
        "palace": "磨蝎宫", "star": "沉晦星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_017-29a", "磨蝎宫沉晦星"),
        "note": "默默努力的人，运气也在悄悄靠近。",
        "love": "稳重可靠，给对方安全感。",
        "career": "踏实努力，升职加薪有希望。",
        "wealth": "积少成多，坚持理财计划。",
    },
    "水瓶": {
        "palace": "寶瓶宫", "star": "天暴星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_015-29b", "寶瓶宫天暴星"),
        "note": "特立独行不是错，是你的签名。",
        "love": "独特魅力吸引欣赏你的人。",
        "career": "创新思维带来突破。",
        "wealth": "另类投资可能有惊喜。",
    },
    "双鱼": {
        "palace": "雙魚宫", "star": "天煞星",
        "anchor": ("KR3g0041", "KR3g0041_WYG_021-26b", "雙魚宫天煞星"),
        "note": "爱做梦的人运气不会太差——梦是愿望的预告。",
        "love": "浪漫多情，今天适合约会。",
        "career": "想象力丰富，适合创作。",
        "wealth": "直觉敏锐，投资有灵感。",
    },
}

_SIGN_ORDER = ("白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
               "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼")

# 日支 → 今名（日支即"今日值宫"的查表键）
_ZHI_SIGN: dict[str, str] = {
    "戌": "白羊", "酉": "金牛", "申": "双子", "未": "巨蟹",
    "午": "狮子", "巳": "处女", "辰": "天秤", "卯": "天蝎",
    "寅": "射手", "丑": "摩羯", "子": "水瓶", "亥": "双鱼",
}


def day_sign(day_zhi: str) -> str:
    """当日日支 → 今日值宫今名。未知地支返回空串。"""
    return _ZHI_SIGN.get(day_zhi or "", "")


def daily_horoscope(day_ganzhi: str) -> dict:
    """当日日干支 → 十二宫聚合卡（今日值宫 + 全 12 宫一句话）。

    day_ganzhi 形如 "丁卯"（首字天干忽略，次字地支查表）。
    纯函数：固定输入必得固定输出。
    """
    zhi = (day_ganzhi or "")[-1:]
    today = day_sign(zhi)
    return {
        "day_ganzhi": day_ganzhi,
        "today_sign": today,
        "today_note": SIGNS[today]["note"] if today else "",
        "signs": [
            {
                "sign": name,
                "palace": SIGNS[name]["palace"],
                "star": SIGNS[name]["star"],
                "note": SIGNS[name]["note"],
                "love": SIGNS[name].get("love", ""),
                "career": SIGNS[name].get("career", ""),
                "wealth": SIGNS[name].get("wealth", ""),
                "is_today": name == today,
            }
            for name in _SIGN_ORDER
        ],
    }


def citation_for(sign: str) -> dict:
    """某宫的引文锚点（判据 10 可追溯性）。sign 用今名。"""
    a = SIGNS.get(sign, {}).get("anchor")
    if not a:
        return {}
    return {"work_id": a[0], "page_anchor": a[1], "needle": a[2]}


# ---------------------------------------------------------------------------
# 自测：固定输入 → 固定输出（宪法第一条）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    h = daily_horoscope("丁卯")
    assert h["today_sign"] == "天蝎", h["today_sign"]
    assert h["signs"][7]["is_today"] is True       # 天蝎在第 8 位
    assert len(h["signs"]) == 12
    assert all(s["note"] for s in h["signs"])
    # C-002：星座详情页分维度字段
    assert all(s.get("love") and s.get("career") and s.get("wealth") for s in h["signs"])
    # 确定性
    assert daily_horoscope("丁卯") == h
    # 12 支全覆盖
    for zhi in _ZHI_SIGN:
        assert day_sign(zhi), zhi
    # 锚点表完整
    for name in _SIGN_ORDER:
        a = citation_for(name)
        assert a.get("needle") and a.get("work_id"), name

    print("今日值宫（丁卯日）：", h["today_sign"], "-", h["today_note"])
    print("xingzuo self-test PASS (12宫/确定性/锚点完整)")
