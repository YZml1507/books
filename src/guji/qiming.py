"""qiming — 五行起名纯计算模块。

输入：姓氏 + 出生（八字）→ 用 bazi_calc 的五行缺行 → 从部首五行表筛选补缺字
      → 给出字 + 五行 + 寓意坐标。

红线遵守（照项目纪律）：
  * 纯计算：选字基于部首五行规则表（写死可核验），不生成"新命理文本"。
  * 寓意坐标：只给字+五行+部首+简明寓意坐标（如"木-栋梁之材"），不作吉凶断言。
  * 不联网抓字库：候选字表写死在模块内，可核验、可审计。

五行规则表（通行命理常识，写死可核对）：
  * 天干五行：甲乙木 丙丁火 戊己土 庚辛金 壬癸水
  * 部首五行（简化版，按《康熙字典》部首归类）：
      木：木 竹 艹 禾 米 糸 衣
      火：火 日 灬 炎
      土：土 山 石 玉 田 邑
      金：金 钅 刀 刂 辛
      水：水 氵 冫 雨 鱼

候选字表（按五行分组，每字含部首+简明寓意坐标）：
  只收录常见、寓意正面、字形规整的汉字，避免生僻字。
"""
from __future__ import annotations

from .bazi import compute as bazi_compute
from .bazi_calc import five_element_counts

# --------------------------------------------------------------------------------------
# 部首五行表（写死可核验）
# --------------------------------------------------------------------------------------
RADICAL_ELEMENT: dict[str, str] = {
    # 木
    "木": "木", "竹": "木", "艹": "木", "禾": "木", "米": "木", "糸": "木", "衣": "木",
    "朩": "木",
    # 火
    "火": "火", "日": "火", "灬": "火", "炎": "火", "光": "火",
    # 土
    "土": "土", "山": "土", "石": "土", "玉": "土", "田": "土", "邑": "土",
    "阝": "土", "王": "土",
    # 金
    "金": "金", "钅": "金", "刀": "金", "刂": "金", "辛": "金", "戈": "金",
    "斤": "金", "皿": "金",
    # 水
    "水": "水", "氵": "水", "冫": "水", "雨": "水", "鱼": "水", "魚": "水",
    "川": "水", "巛": "水",
    # 人/走/言部首归入其五行本气（人=土、走=土、言=金）
    "亻": "土", "彳": "火", "口": "金",
    # R233u（R53-P2-3）：彡（文采修饰）入木——彬的字表标签是木，
    # 部首口径与字表标签对齐
    "彡": "木",
}

# --------------------------------------------------------------------------------------
# 候选字表（按五行分组）
# 格式：字: (部首, 寓意坐标)
# 寓意坐标格式："五行-简明寓意"，如 "木-栋梁之材"
# --------------------------------------------------------------------------------------
CANDIDATE_CHARS: dict[str, list[tuple[str, str, str]]] = {
    "木": [
        ("林", "木", "木-茂盛成林"),
        ("森", "木", "木-繁茂森然"),
        ("桐", "木", "木-梧桐栖凤"),
        ("柏", "木", "木-松柏长青"),
        ("栋", "木", "木-栋梁之材"),
        ("梁", "木", "木-栋梁之材"),
        ("彬", "彡", "木-文质彬彬"),
        ("杰", "木", "木-人杰地灵"),
        ("松", "木", "木-松柏长青"),
        ("枫", "木", "木-枫叶如丹"),
        ("楠", "木", "木-楠木坚贞"),
        ("楷", "木", "木-楷模示范"),
        ("榕", "木", "木-榕荫蔽日"),
        ("荣", "艹", "木-繁荣昌盛"),
        ("萱", "艹", "木-萱草忘忧"),
        ("芷", "艹", "木-芷兰芬芳"),
        ("薇", "艹", "木-薇草清雅"),
        ("兰", "艹", "木-兰心蕙质"),
        ("芳", "艹", "木-芳华永驻"),
        ("芬", "艹", "木-芬芳馥郁"),
    ],
    "火": [
        ("炎", "火", "火-日光赫赫"),
        ("煜", "火", "火-煜煜生辉"),
        ("炜", "火", "火-炜煌光明"),
        ("烨", "火", "火-烨烨华彩"),
        ("焕", "火", "火-焕然一新"),
        ("烽", "火", "火-烽火传捷"),
        ("耀", "光", "火-光耀门楣"),
        ("辉", "光", "火-光辉灿烂"),
        ("明", "日", "火-光明磊落"),
        ("旭", "日", "火-旭日东升"),
        ("晨", "日", "火-晨光熹微"),
        ("晗", "日", "火-晗光初现"),
        ("曦", "日", "火-晨曦初露"),
        ("晴", "日", "火-晴空万里"),
        ("暖", "日", "火-暖阳和煦"),
        ("昕", "日", "火-昕光破晓"),
        ("昱", "日", "火-昱昱光明"),
        ("煦", "灬", "火-春风和煦"),
        ("熙", "灬", "火-熙和安康"),
        ("然", "灬", "火-怡然自得"),
    ],
    "土": [
        ("坤", "土", "土-坤厚载物"),
        ("培", "土", "土-培植培育"),
        ("垣", "土", "土-城垣坚固"),
        ("坚", "土", "土-坚如磐石"),
        ("墨", "土", "土-墨香书韵"),
        ("壁", "土", "土-壁立千仞"),
        ("城", "土", "土-城池坚固"),
        ("基", "土", "土-基业长青"),
        ("堂", "土", "土-堂堂正正"),
        ("境", "土", "土-境界高远"),
        ("增", "土", "土-增益其所不能"),
        ("圣", "土", "土-圣贤之德"),
        ("佳", "亻", "土-佳人佳偶"),

        ("瑞", "王", "土-祥瑞之兆"),
        ("珍", "王", "土-珍奇宝贵"),
        ("珠", "王", "土-珠圆玉润"),
        ("琳", "王", "土-琳琅满目"),
        ("琪", "王", "土-琪花瑶草"),
        ("瑶", "王", "土-瑶池仙境"),
    ],
    "金": [
        ("鑫", "金", "金-金玉满堂"),
        ("锋", "钅", "金-锐不可当"),
        ("铭", "钅", "金-铭刻于心"),
        ("铮", "钅", "金-铁骨铮铮"),
        ("锦", "钅", "金-锦绣前程"),
        ("钟", "钅", "金-钟鸣鼎食"),
        ("钦", "钅", "金-钦敬尊崇"),
        ("镇", "钅", "金-镇定自若"),
        ("钰", "钅", "金-珍宝坚固"),
        ("银", "钅", "金-银光闪耀"),
        ("锐", "钅", "金-锐意进取"),
        ("钢", "钅", "金-百炼成钢"),
        ("鉴", "金", "金-鉴往知来"),
        ("钧", "钅", "金-雷霆万钧"),
        ("铂", "钅", "金-铂金珍贵"),
        ("铠", "钅", "金-铠甲坚固"),
        ("镜", "钅", "金-明镜高悬"),
        # R233u（R53-P2-3）：嘉部首是口（口→金），原标土与部首口径矛盾
        ("嘉", "口", "金-嘉言懿行"),
        ("铜", "钅", "金-铜墙铁壁"),
        ("铁", "钅", "金-铁骨铮铮"),
        ("锡", "钅", "金-锡泽恩惠"),
        # R191b（B-015）：金字池原本 20 字里女性向命中 0——女生缺金只能得到
        # 「林鑫铭」串。补两个钅部首的女性常用字（写死可核验，同表纪律）。
        ("铃", "钅", "金-铃音清越"),
        ("钗", "金", "金-金钗之贵"),
    ],
    "水": [
        ("泽", "氵", "水-泽被苍生"),
        ("浩", "氵", "水-浩浩荡荡"),
        ("淼", "水", "水-水润丰盈"),
        ("润", "氵", "水-润物无声"),
        ("涵", "氵", "水-涵养深厚"),
        ("渊", "氵", "水-渊博深邃"),
        ("清", "氵", "水-清正廉明"),
        ("澜", "氵", "水-波澜壮阔"),
        ("洁", "氵", "水-洁身自好"),
        ("洋", "氵", "水-汪洋恣肆"),
        ("淳", "氵", "水-淳朴厚道"),
        ("沁", "氵", "水-沁人心脾"),
        ("湘", "氵", "水-湘水悠悠"),
        ("波", "氵", "水-波光粼粼"),
        ("源", "氵", "水-源远流长"),
        ("深", "氵", "水-深谋远虑"),
        ("沛", "氵", "水-沛然莫御"),
        ("泓", "氵", "水-泓澄清澈"),
        ("渝", "氵", "水-矢志不渝"),
        ("潇", "氵", "水-潇洒自如"),
    ],
}


def get_element_by_radical(radical: str) -> str | None:
    """部首 -> 五行，查表返回。不在表中返回 None。"""
    return RADICAL_ELEMENT.get(radical)


# --------------------------------------------------------------------------------------
# 性别倾向表（R187b，specs/006 前置：全名组合的软偏好）
#
# 从 CANDIDATE_CHARS 字池人工归类；不在两表中的字视为中性。
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


def _gender_score(char: str, gender: str) -> int:
    """性别契合分：契合 +1、相悖 -1、中性 0。确定性纯函数。"""
    if char in FEMININE_CHARS:
        return 1 if gender == "女" else -1
    if char in MASCULINE_CHARS:
        return 1 if gender == "男" else -1
    return 0


# --------------------------------------------------------------------------------------
# 全名组合（R187b，用户痛点：「取名的没给出完整名字」）
#
# 规则（全部写死可核验）：
#   * 形态一：姓+单字（缺行字）；形态二：姓+双字（至少一字属缺行）
#   * 硬过滤：名字内不重复用字、不用姓氏用字
#   * 排序：缺行命中数 > 性别契合分 > 候选表原顺序（稳定）
#   * 纯函数：无 random / 无时钟 / 无 IO；固定输入必得固定输出
# --------------------------------------------------------------------------------------
FULL_N_DEFAULT = 8
_MAX_MEANING_REPEAT = 2      # 同一寓意坐标的组合最多出现次数
_QIMING_HEAD_REPEAT = 2      # U-005：同一「名字首字」同批最多出现次数


# R233u（R53-P1-4）：姓氏×高危谐音 denylist——挨着姓的那个字一旦
# 凑成谐音词就是网名级翻车（实测产出：吴德=无德、吴陵=亡灵、杜梓=
# 肚子、范铜=饭桶、杨伟、秦寿、史珍香…）。只挡「紧邻姓的首字」
# 和「单字名」，第二字不受限（谐音必须挨着姓才成立）。
_SURNAME_TRAP: dict[str, frozenset[str]] = {
    "吴": {"德", "陵", "能", "心", "名", "用", "情", "义", "赖", "忧",
           "疾", "聊", "辜", "为", "寿", "畏", "法", "礼", "良", "福"},
    "杜": {"梓", "子", "楠", "康", "飞", "绝"},
    "范": {"铜", "桶", "统", "剑", "畴", "愁", "罪", "统", "例"},
    "史": {"珍", "香", "真", "达", "蒂", "努", "前", "尚"},
    "杨": {"伟", "柳", "絮", "花"},
    "朱": {"逸", "群", "仔", "投", "砂"},
    "贾": {"仁", "义", "善", "正", "经", "道", "庆"},
    "秦": {"寿", "兽", "晋"},
    "苟": {"且", "安", "延", "全"},
    "费": {"钱", "财", "劲", "心", "力"},
    "梅": {"运", "福", "财", "有", "钱", "门"},
    "毕": {"须", "竟", "胜", "业"},
    "殷": {"商", "实", "勤"},
    "宫": {"刑", "保", "廷"},
    "牛": {"马", "皮", "奶"},
    "马": {"虎", "桶", "后", "尚"},
    "侯": {"车", "爵", "赛"},
    "熊": {"掌", "胆", "腰"},
    "傅": {"债", "科", "彩"},
    "夏": {"流", "侯", "候"},
}


def _full_name_combos(surname: str, missing: list[str], gender: str,
                      candidates: list[dict],
                      full_n: int = FULL_N_DEFAULT,
                      strong_elem: str = "") -> list[dict]:
    """候选字 → 完整姓名列表（姓+单字 / 姓+双字），确定性排序。"""
    pool = [c for c in candidates if c["char"] not in surname]
    miss_set = set(missing)
    _trap = _SURNAME_TRAP.get(surname, frozenset())

    def _entry(given: str, chars: list[dict]) -> dict:
        return {
            "full_name": surname + given,
            "given": given,
            "elements": [c["element"] for c in chars],
            # U-018：两字寓意坐标相同时去重为一处（原「松柏长青 · 松柏长青」）
            "meanings": " · ".join(dict.fromkeys(
                c["meaning"].split("-", 1)[-1] for c in chars)),
            "form": "single" if len(chars) == 1 else "double",
        }

    scored: list[tuple[int, int, int, dict]] = []   # (缺行命中数, 性别分, 表序, entry)
    order = 0

    # 形态一：单字名（R233u：trap 字挨着姓成词，剔除）
    for c in pool:
        if c["char"] in _trap:
            continue
        hit = 1 if c["element"] in miss_set else 0
        g = _gender_score(c["char"], gender)
        scored.append((hit, g, order := order + 1, _entry(c["char"], [c])))

    # 形态二：双字名（i<j 组合，去重用字）
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b2 = pool[i], pool[j]
            if a["char"] == b2["char"] or a["char"] in _trap:
                continue
            # R233u（R53-P1-5）：最强五行字不进双字——缺木+火最旺时
            # 「李桐闻」把最强的火再塞一字，与「补缺不加强」矛盾。
            if strong_elem and strong_elem not in miss_set and \
               (a["element"] == strong_elem or b2["element"] == strong_elem):
                continue
            hit = (1 if a["element"] in miss_set else 0) + \
                  (1 if b2["element"] in miss_set else 0)
            if hit == 0:
                continue                      # 双字组合必须至少一字补缺行
            g = _gender_score(a["char"], gender) + _gender_score(b2["char"], gender)
            scored.append((hit, g, order := order + 1,
                           _entry(a["char"] + b2["char"], [a, b2])))

    # 稳定排序：性别分降序 → 缺行命中降序 → 表序升序
    # R191b（B-015）：原键把缺行命中放在性别分之前——双字全命中缺行的
    # 组合恒排最前，性别分形同虚设；叠加金字池零女性向字，女生缺金只会得到
    # 林鑫铭/林鑫铮/…（D-252b：性别契合优先于补缺教条，缺行信息仍在
    # candidates 与 summary 完整展示，专业信息不丢失）。
    scored.sort(key=lambda t: (-t[1], -t[0], t[2]))

    out: list[dict] = []
    meaning_count: dict[str, int] = {}
    # R216b 续（UX 队列 U-005）：同批名字中间字去重——原实现只限寓意重复，
    # 排序后同首字组合扎堆（实测「李萱芷/李萱薇/李萱兰/…」8 名全带「萱」，
    # 审查轨巡1 的「李柏X」同源）。规则：每个「名字首字」在同批最多出现
    # 2 次；池子不够时回填被跳过的次优组合，保证足额 full_n 个。
    head_count: dict[str, int] = {}
    skipped: list[dict] = []
    for _, _, _, entry in scored:
        if len(out) >= full_n:
            break
        mkey = entry["meanings"]
        hkey = entry["given"][:1]
        if meaning_count.get(mkey, 0) >= _MAX_MEANING_REPEAT or \
           head_count.get(hkey, 0) >= _QIMING_HEAD_REPEAT:
            skipped.append(entry)
            continue
        meaning_count[mkey] = meaning_count.get(mkey, 0) + 1
        head_count[hkey] = head_count.get(hkey, 0) + 1
        out.append(entry)
    for entry in skipped:               # 回填：多样性约束放宽但寓意上限不放宽
        if len(out) >= full_n:
            break
        if meaning_count.get(entry["meanings"], 0) >= _MAX_MEANING_REPEAT:
            continue
        meaning_count[entry["meanings"]] = meaning_count.get(entry["meanings"], 0) + 1
        out.append(entry)
    # R233u（R53-P1-5）：排序键让双字恒压单字——单字名实际不可达。
    # top_n 内保底 ~1/4 单字席位：用次优单字顶替尾部双字。
    _seat = max(1, full_n // 4)
    if sum(1 for e in out if e["form"] == "single") < _seat:
        _spare = [e for e in scored if e[3]["form"] == "single"
                  and e[3] not in out]
        for _se in _spare:
            if sum(1 for e in out if e["form"] == "single") >= _seat:
                break
            for _k in range(len(out) - 1, -1, -1):
                if out[_k]["form"] == "double":
                    out[_k] = _se[3]
                    break
    return out


def get_element_by_char(char: str) -> str | None:
    """字 -> 五行（查候选字表）。不在候选表中返回 None。"""
    for elem, chars in CANDIDATE_CHARS.items():
        for c, _, _ in chars:
            if c == char:
                return elem
    return None


# --------------------------------------------------------------------------------------
# 起名算法
# --------------------------------------------------------------------------------------
def name_candidates(surname: str, year: int, month: int, day: int,
                    hour: int, gender: str = "男",
                    top_n: int = 20) -> dict:
    """八字 → 五行缺行 → 从候选字库筛选补缺字。

    返回 dict：
      surname: 姓氏
      bazi: Bazi 对象
      five_elements: {counts, missing, strong}
      candidates: [{char, element, radical, meaning}, ...]  按五行缺行优先排序
      summary: 模板拼接的坐标摘要（可核验，非 LLM 文本）
    """
    b = bazi_compute(year, month, day, hour, gender)
    counts = five_element_counts(b)
    missing = [e for e, v in counts.items() if v <= 0.001]

    # 如果不缺任何五行，则选最弱的五行来补
    if not missing:
        # 找最弱的五行（权重最小且 > 0）
        min_elem = min(counts.items(), key=lambda x: x[1] if x[1] > 0 else float('inf'))[0]
        missing = [min_elem]

    # 从候选字库筛选补缺字
    candidates: list[dict] = []
    for elem in missing:  # 优先补缺行
        if elem in CANDIDATE_CHARS:
            for char, radical, meaning in CANDIDATE_CHARS[elem]:
                candidates.append({
                    "char": char,
                    "element": elem,
                    "radical": radical,
                    "meaning": meaning,
                })

    # 如果缺行字不够，补充其他五行字
    if len(candidates) < top_n:
        for elem, chars in CANDIDATE_CHARS.items():
            if elem in missing:
                continue  # 已经加过
            for char, radical, meaning in chars:
                if len(candidates) >= top_n:
                    break
                candidates.append({
                    "char": char,
                    "element": elem,
                    "radical": radical,
                    "meaning": meaning,
                })
            if len(candidates) >= top_n:
                break

    candidates = candidates[:top_n]

    _strong_elem = max(counts.items(), key=lambda x: x[1])[0] if counts else ""
    full_names = _full_name_combos(surname, missing, gender, candidates,
                                   strong_elem=_strong_elem)

    # summary：模板拼接（可核验，非 LLM 文本）
    dist = "、".join(f"{e}{v:g}" for e, v in counts.items())
    miss_str = f"缺{''.join(missing)}" if missing else "五行俱全"
    summary_parts = [
        f"姓氏：{surname}",
        f"八字：{b.year} {b.month} {b.day} {b.hour}（日主{b.day_master}）",
        f"五行分布：{dist}",
        miss_str,
    ]
    if missing:
        comp_chars = "、".join(c["char"] for c in candidates[:5] if c["element"] in missing)
        summary_parts.append(f"补{''.join(missing)}候选字（前5）：{comp_chars}")
    if full_names:
        top3 = "、".join(n["full_name"] for n in full_names[:3])
        summary_parts.append(f"完整名推荐（前3）：{top3}")

    return {
        "surname": surname,
        "bazi": {
            "year": b.year, "month": b.month, "day": b.day, "hour": b.hour,
            "day_master": b.day_master,
            "render": b.render(),
        },
        "five_elements": {
            "counts": {e: round(v, 2) for e, v in counts.items()},
            "missing": missing,
        },
        "candidates": candidates,
        "full_names": full_names,
        "summary": "；".join(summary_parts),
    }


# --------------------------------------------------------------------------------------
# 自测：固定输入 → 固定输出（宪法第一条）
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    r1 = name_candidates("林", 1998, 7, 20, 14, gender="女")
    assert r1["full_names"], "full_names 不应为空"
    for n in r1["full_names"]:
        fn = n["full_name"]
        assert fn.startswith(r1["surname"]), fn
        given = fn[len(r1["surname"]):]
        assert len(set(given)) == len(given), f"名字内重复用字：{fn}"
        assert n["form"] in ("single", "double")
    # 女名前3不应是男性专属高分字开头
    top3 = "".join(n["given"] for n in r1["full_names"][:3])
    for m in ("锋", "钢", "铁", "铠"):
        assert m not in top3[:2], f"女名前2出现男性字 {m}: {top3}"
    # R191b（B-015 判据，specs/006 同款）：gender=女 时前 8 个 full_names 中
    # 含 FEMININE_CHARS 的 ≥5 个；gender=男 时含 MASCULINE_CHARS 的 ≥5 个。
    def _fem_count(res):
        return sum(1 for n in res["full_names"]
                   if any(ch in FEMININE_CHARS for ch in n["given"]))

    def _masc_count(res):
        return sum(1 for n in res["full_names"]
                   if any(ch in MASCULINE_CHARS for ch in n["given"]))

    assert _fem_count(r1) >= 5, f"女前8女性向不足5：{[n['full_name'] for n in r1['full_names']]}"
    r2 = name_candidates("王", 1990, 5, 15, 23, gender="男")
    assert _masc_count(r2) >= 5, f"男前8男性向不足5：{[n['full_name'] for n in r2['full_names']]}"
    # 确定性：两次调用逐字节相等
    r1b = name_candidates("林", 1998, 7, 20, 14, gender="女")
    assert r1 == r1b, "两次调用输出不一致（违反确定性）"

    assert r2["full_names"]
    print("女（林·缺金）前3全名：",
          "、".join(n["full_name"] for n in r1["full_names"][:3]))
    print("女（林·缺金）前8女性向命中：", _fem_count(r1), "/8")
    print("男（王）前3全名：",
          "、".join(n["full_name"] for n in r2["full_names"][:3]))
    print("男（王）前8男性向命中：", _masc_count(r2), "/8")
    print("qiming self-test PASS (full_names/硬过滤/性别软偏好B-015判据/确定性)")
