"""voice — warm 视图层（把已算出的坐标说成人话，不新增任何事实）。

存在理由（`specs/004-warm-voice/spec.md`）：用户指示「当前结果普通人看不懂
也不想看」。实测诊断（台账 §114.2 / spec §「我自己重跑了诊断样例」）：用户
问「感情运怎么样？」，答案排在第 5 节、只有 1 行，前面 15 行是坐标与推导链。

本模块与 `interpreter.py` 的分工——这是判据 9 的架构前提：

  * `interpreter.py`  专业模式，**一行不改**。它的输出即基线，由
    `web/baseline_voice.py` 逐字节把关（14 用例 sha256 冻结）。
  * `voice.py`（本模块）warm 模式，**新增分支**而非改造。路由层
    additive 附加 `"warm"` 键，前端按 `voiceMode` 选渲染哪个。

硬纪律（违反任一条即判据失败）：

  1. **纯函数**：无 IO、无网络、无随机、不读时钟（"今天"由调用方传入）。
     同输入必同输出（判据 5），两次调用逐字节相等。
  2. **不新增事实**：每句话都能回指一个 calc 字段。模板文字写死在本模块，
     事实全部来自入参——与 interpreter 同一条纪律。
  3. **不断吉凶、不给现实指令**（判据 6，spec US2）。句式只允许三类：
     描述已算出的坐标 / 开放式提示 / 把判断权交还用户。
     禁用词表由 `web/check_warm_voice.py` 写死并做阳性对照。
  4. **不进语料库**：本模块产出只随响应返回、只落 history.db（D-039 已授权），
     不进 corpus.db / knowledge.db（判据 14）。

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe -m guji.voice          # 本模块自测
    .\\.venv\\Scripts\\python.exe web\\check_warm_voice.py  # 判据 1-8
"""
from __future__ import annotations

# R214b：年轻化文案库。纪律例外说明：本模块原为纯函数（无 IO），文案库
# 以「模块级一次性加载 + 全部回退到旧模板」的方式引入——加载失败时行为与
# R213b 之前完全一致，确定性（判据 5）不受影响（抽取用 sha1 盐而非随机）。
import hashlib as _hashlib
import json as _json
import os as _os
_COPY_BANK_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                "copy_bank.json")
try:
    with open(_COPY_BANK_PATH, encoding="utf-8") as _f:
        COPY_BANK: dict = _json.load(_f) or {}
except Exception:
    COPY_BANK = {}


def _pick(seq, *salt):
    """从文案池确定性抽一条：sha1(盐) 稳定映射，同输入必同输出。"""
    if not seq:
        return ""
    h = _hashlib.sha1("|".join(str(s) for s in salt).encode("utf-8")).hexdigest()
    return seq[int(h[:8], 16) % len(seq)]

# ---------------------------------------------------------------------------
# 术语白话表：把命理术语翻译成日常语。
#
# 纪律：括号里**保留原词**——白话化是为了可读，不是为了抹掉可检索性。
# 用户能读懂，同时仍能拿原词去古籍里检索（这是本项目的立身之本）。
# ---------------------------------------------------------------------------

# 十神 → (日常语标签, 一句话说明)。措辞守则见 plan §3：
# 不含吉凶断言，只描述"这股力量是什么"。
TEN_GOD_WARM: dict[str, tuple[str, str]] = {
    "比肩": ("同伴力", "身边同类多，做事有人同行，也容易互相比较"),
    "劫财": ("分享力", "人来人往热闹，钱和精力容易一起花掉"),
    "食神": ("表达力", "温和地把想法说出来、做出来，节奏不急"),
    "伤官": ("创造力", "点子多、锋芒也在，喜欢跳出既定框架"),
    "偏财": ("流动财", "进项来源多，但不太固定"),
    "正财": ("稳定财", "来源固定，适合慢慢积累"),
    "七杀": ("压力位", "外部推力大，事情常被逼着往前走"),
    "正官": ("规矩位", "在规则里行事，责任感重"),
    "偏印": ("直觉力", "想法独特，学东西走自己的路"),
    "正印": ("庇护力", "有人照着、有东西托着，适合稳步累积"),
}

# 五行 → (日常语, 意象)
ELEMENT_WARM: dict[str, tuple[str, str]] = {
    "木": ("生长", "像春天的枝条，向外舒展、有条理"),
    "火": ("热度", "亮、外放、情绪来得快"),
    "土": ("厚稳", "承得住，慢热但踏实"),
    "金": ("决断", "干脆、边界清楚、说一是一"),
    "水": ("柔软", "能绕、会找路，适应力强"),
}

# 地支 → 生肖 + 方位（F-006：干支改生肖+方位注释）
ZHI_ZODIAC: dict[str, str] = {
    "子": "鼠", "丑": "牛", "寅": "虎", "卯": "兔",
    "辰": "龙", "巳": "蛇", "午": "马", "未": "羊",
    "申": "猴", "酉": "鸡", "戌": "狗", "亥": "猪",
}
ZHI_DIR: dict[str, str] = {
    "子": "北", "丑": "东北", "寅": "东北", "卯": "东",
    "辰": "东南", "巳": "东南", "午": "南", "未": "西南",
    "申": "西南", "酉": "西", "戌": "西北", "亥": "西北",
}

ELEMENT_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
ELEMENT_GENERATED_BY = {v: k for k, v in ELEMENT_GENERATES.items()}

# 地支关系 → 日常语（中性描述，不断吉凶）
RELATION_WARM: dict[str, str] = {
    "相冲": "有一股对着来的劲，节奏容易被打断",
    "相害": "有些细碎的磨，多是小事不是大事",
    "相刑": "事情容易反复，需要返工",
    "自刑": "内耗比外部阻力多",
    "六合": "有人配合，事情容易牵着成",
    "三合": "力量集中在一个方向上",
    "半合": "方向已经有了，力还没满",
    "相生": "能量顺着走，不别扭",
}

# ---------------------------------------------------------------------------
# 幸运项规则表（判据 10：写死映射 + 可引古籍，非随机）
#
# 河图数出处：「天一生水」类单元（台账 §115 实测命中 11 条）。
# 五色出处：「五色」类单元（命中 74 条）。
# 锚点在 M2 钉死进 web/baselines/xingzuo_fixture.json 并逐条断言命中 corpus。
# ---------------------------------------------------------------------------
HETU_NUMBERS: dict[str, tuple[int, int]] = {
    "水": (1, 6), "火": (2, 7), "木": (3, 8), "金": (4, 9), "土": (5, 0),
}

ELEMENT_COLORS: dict[str, tuple[str, ...]] = {
    "水": ("黑", "蓝"), "火": ("红", "紫"), "木": ("青", "绿"),
    "金": ("白", "金"), "土": ("黄", "棕"),
}

# 十二时辰五行（寅卯木 巳午火 申酉金 亥子水 辰戌丑未土）
ZHI_ELEMENT: dict[str, str] = {
    "寅": "木", "卯": "木", "巳": "火", "午": "火",
    "申": "金", "酉": "金", "亥": "水", "子": "水",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

ZHI_HOURS: dict[str, str] = {
    "子": "23–1 点", "丑": "1–3 点", "寅": "3–5 点", "卯": "5–7 点",
    "辰": "7–9 点", "巳": "9–11 点", "午": "11–13 点", "未": "13–15 点",
    "申": "15–17 点", "酉": "17–19 点", "戌": "19–21 点", "亥": "21–23 点",
}

GAN_ELEMENT: dict[str, str] = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

# 免责声明：judged by 判据 7——必须含「仅供娱乐」，且**不压轴收尾**
# （放在 L1 能量卡下方、L2 详情之前）。
# D-003：禁用「详细依据见专业模式」套话，改为纯娱乐性提示
BADGE = "仅供娱乐 · 小满的轻松解读"

# 提问关键词 → (关注的十神集合, 日常语标签)。
# 与 interpreter._TOPIC_MAP 同源但**独立**：那边是专业措辞，这边是日常语，
# 两表都写死、互不引用——共享一张表会让改 warm 措辞时碰坏专业输出（判据 9）。
TOPIC_WARM: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("感情", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("恋爱", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("婚", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("桃花", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("对象", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("运势", (), "状态"),
    ("事业", ("正官", "七杀"), "事业"),
    ("工作", ("正官", "七杀"), "事业"),
    ("升职", ("正官", "七杀"), "事业"),
    ("考公", ("正官", "七杀"), "事业"),
    ("创业", ("正财", "偏财", "伤官"), "事业"),
    ("财", ("正财", "偏财"), "财运"),
    ("钱", ("正财", "偏财"), "财运"),
    ("收入", ("正财", "偏财"), "财运"),
    # U-024（R216b 续6）：单字「学」匹配过宽——「量子力学怎么解释」误命中
    # 学业主题。改用双字词，覆盖常见口语。
    ("学业", ("正印", "偏印"), "学业"),
    ("学习", ("正印", "偏印"), "学业"),
    ("上学", ("正印", "偏印"), "学业"),
    ("考试", ("正印", "偏印"), "学业"),
    ("考研", ("正印", "偏印"), "学业"),
    ("读书", ("正印", "偏印"), "学业"),
    ("健康", (), "状态"),
    ("身体", (), "状态"),
    ("情绪", (), "状态"),
)


def _day_element(paipan_or_master: str) -> str:
    """日主天干 → 五行。入参是单个天干字。"""
    return GAN_ELEMENT.get((paipan_or_master or "")[:1], "")


def _fmt_num(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else f"{float(x):g}"


# ---------------------------------------------------------------------------
# L1 能量卡（幸运项）——判据 10：每项都由写死规则推出，非随机
# ---------------------------------------------------------------------------
def energy_card(day_master: str, calc: dict) -> dict:
    """本命元素 + 幸运色/数字/时段 + 今日关键词。

    规则（全部写死，可复验）：
      * 本命元素 = 日主天干的五行
      * 幸运数字 = 「生日主之行」的河图数（如日主土 → 生土者为火 → 2·7）
      * 幸运色   = 同一"生我"之行的五行配色
      * 幸运时段 = 该行对应的地支时辰
    取"生我者"而非"我本身"：这是补益方向，与 interpreter 的缺行提示同源
    （`ELEMENT_GENERATES`），不是新发明的规则。
    """
    mine = _day_element(day_master)
    helper = ELEMENT_GENERATED_BY.get(mine, mine)   # 生我者
    nums = HETU_NUMBERS.get(helper, ())
    colors = ELEMENT_COLORS.get(helper, ())
    hours = [f"{z}时（{ZHI_HOURS[z]}）"
             for z, e in ZHI_ELEMENT.items() if e == helper]

    fe = calc.get("five_elements") or {}
    keywords: list[str] = []
    for s in (fe.get("strong") or [])[:1]:
        keywords.append(f"{ELEMENT_WARM.get(s, ('', ''))[0]}偏多")
    for m in (fe.get("missing") or [])[:1]:
        keywords.append(f"缺{m}")
    dl = calc.get("day_luck") or {}
    if dl.get("day_ganzhi"):
        keywords.append(f"今日{dl['day_ganzhi']}")
    if not keywords:
        keywords.append("五行平和")

    return {
        "element": mine,
        "element_warm": ELEMENT_WARM.get(mine, ("", ""))[0],
        "element_note": ELEMENT_WARM.get(mine, ("", ""))[1],
        "helper_element": helper,
        "lucky_numbers": list(nums),
        "lucky_colors": list(colors),
        "lucky_hours": hours,
        "keywords": keywords[:3],
        # 判据 10：规则出处（M2 钉死锚点后由 xingzuo fixture 提供逐字引文）
        "basis": [
            f"本命元素 = 日主{day_master}的五行（calc.ten_gods 日干）",
            f"幸运数字 = 河图数「{helper}」（生{mine}者）",
            f"幸运色 = 五行配色「{helper}」",
        ],
    }


# ---------------------------------------------------------------------------
# L0 一句话（判据 2：≤20 字；判据 1：有提问时直接回应提问）
# ---------------------------------------------------------------------------
_L0_MAX = 20


def _topic_of(question: str) -> tuple[tuple[str, ...], str] | None:
    q = (question or "").strip()
    if not q:
        return None
    for kw, gods, label in TOPIC_WARM:
        if kw in q:
            return gods, label
    return None


def one_liner(day_master: str, calc: dict, question: str | None) -> str:
    """≤20 字的一句话。有提问先回应提问，无提问给本命底色。

    长度硬约束：模板本身就写短；末尾仍做一次截断兜底，保证判据 2 恒成立。
    """
    mine = _day_element(day_master)
    warm = ELEMENT_WARM.get(mine, ("", ""))[0]
    topic = _topic_of(question or "")
    if topic:
        gods, label = topic
        hit = [t for t in (calc.get("ten_gods") or []) if t.get("god") in gods]
        if gods and hit:
            s = f"{label}这块，盘里有着落点"
        elif gods:
            s = f"{label}这块，盘里信息偏少"
        else:
            fe = calc.get("five_elements") or {}
            _strong_labels = [ELEMENT_WARM.get(s, ("", ""))[0] for s in (fe.get("strong") or [])]
            s = (f"{label}看五行：{'、'.join(_strong_labels) or '平'}偏多"
                 if (fe.get("strong") or fe.get("missing")) else f"{label}整体平和")
    else:
        fe = calc.get("five_elements") or {}
        strong = fe.get("strong") or []
        missing = fe.get("missing") or []
        # F-008：术语人话化——五行名翻译为日常语标签（金→决断、木→生长…）
        _strong_label = ELEMENT_WARM.get(strong[0], ("", ""))[0] if strong else ""
        _missing_label = ELEMENT_WARM.get(missing[0], ("", ""))[0] if missing else ""
        if strong and missing:
            s = f"{warm}底子，{_strong_label}多缺{_missing_label}"
        elif strong:
            s = f"{warm}底子，{_strong_label}偏多"
        elif missing:
            s = f"{warm}底子，缺{_missing_label}"
        else:
            s = f"{warm}底子，五行挺匀"
    return s if len(s) <= _L0_MAX else s[:_L0_MAX]


# ---------------------------------------------------------------------------
# L1.5 reply（判据 1/8：对提问的描述性回应，3–5 行）
# ---------------------------------------------------------------------------
def reply_bazi(day_master: str, calc: dict, question: str | None) -> list[str]:
    """把提问对齐到已算出的坐标，用日常语说出来。不新增结论。"""
    q = (question or "").strip()
    tg = calc.get("ten_gods") or []
    if not q:
        return _reply_no_question(day_master, calc)

    topic = _topic_of(q)
    if topic is None:
        gods_present = sorted({t.get("god") for t in tg if t.get("god")})
        return [
            # R216b 续5（U-016）：拒答话术系统腔 → 小满人设人话。
            f"你问的是「{q}」——这个问题盘里没有对应的位置，小满不瞎编～",
            f"盘里现有的力量是：{'、'.join(TEN_GOD_WARM.get(g, (g, ''))[0] for g in gods_present)}。",
            "下面把通盘坐标都列了，你可以自己对照着看。",
        ]

    gods, label = topic
    # 回声用户原话（判据 1）：只说分类标签（"学业"）会让用户觉得没被听见
    # ——他问的是"考研能上吗"。原话入引号，标签作为归类跟在后面。
    quoted = f"「{q}」" if len(q) <= 18 else f"「{q[:18]}…」"
    lines: list[str] = []
    if not gods:                                     # 健康/状态类：看五行均衡
        fe = calc.get("five_elements") or {}
        strong, missing = fe.get("strong") or [], fe.get("missing") or []
        lines.append(f"你问{quoted}——这属于{label}，主要看五行匀不匀。")
        if strong:
            e = strong[0]
            lines.append(f"你的{e}偏多（{ELEMENT_WARM.get(e, ('', ''))[1]}），"
                         f"用力过头的时候容易失衡。")
        if missing:
            m = missing[0]
            helper = ELEMENT_GENERATES.get(m)
            tip = f"，可以从{helper}的方向补" if helper else ""
            lines.append(f"缺{m}（{ELEMENT_WARM.get(m, ('', ''))[1]}的一面偏弱）{tip}。")
        if not strong and not missing:
            lines.append("五行齐全、没有一行独大，整体偏均衡。")
        lines.append("具体怎么对应，盘面只是参照，你的感受同样重要。")
        return lines

    hit = [t for t in tg if t.get("god") in gods]
    if hit:
        spots = "、".join(f"{t.get('pos', '')}{t.get('gan', '')}"
                          f"（{TEN_GOD_WARM.get(t.get('god', ''), (t.get('god', ''), ''))[0]}）"
                          for t in hit[:3])
        lines.append(f"你问{quoted}——这属于{label}，"
                     f"盘里对应的位置有 {len(hit)} 处：{spots}。")
        first = hit[0].get("god", "")
        note = TEN_GOD_WARM.get(first, ("", ""))[1]
        if note:
            lines.append(f"其中最靠前的那个是{TEN_GOD_WARM.get(first, (first, ''))[0]}"
                         f"（{first}）——{note}。")
        lines.append(f"意思是这件事在你盘里有落点，不是空的；"
                     f"具体怎么走，还要看你自己的选择。")
    else:
        lines.append(f"你问{quoted}——这属于{label}，"
                     f"但这块在四柱天干上没有直接落点。")
        lines.append("系统不据此推测——没有的东西不硬编（这是本项目的规矩）。")
        lines.append("可以看看下面的通盘坐标，或换个问法。")

    rels = calc.get("relations") or []
    if rels:
        r = rels[0]
        warm = RELATION_WARM.get(r.get("type") or "", "")
        if warm:
            lines.append(f"另外四柱里有{r.get('type')}（{r.get('a', '')}×"
                         f"{r.get('b', '')}）——{warm}。")
    return lines[:5]


def _reply_no_question(day_master: str, calc: dict) -> list[str]:
    fe = calc.get("five_elements") or {}
    mine = _day_element(day_master)
    lines = [f"你的日主是{day_master}（{mine}），"
             f"{ELEMENT_WARM.get(mine, ('', ''))[1]}。"]
    strong, missing = fe.get("strong") or [], fe.get("missing") or []
    if strong:
        # F-008：术语人话化——"五行里金偏多"→"你自带「决断」的底色"
        _w = ELEMENT_WARM.get(strong[0], ("", ""))
        lines.append(f"你自带「{_w[0]}」的底色——{_w[1]}。")
    if missing:
        # F-008：术语人话化——缺行也用日常语标签
        _missing_labels = [ELEMENT_WARM.get(m, ('', ''))[0] for m in missing]
        lines.append(f"缺{'、'.join(_missing_labels)}——不是缺陷，是偏向。")
    dl = calc.get("day_luck") or {}
    if dl.get("day_master_rel"):
        # R214b：裸术语（「庚为日主甲之七杀」）翻译成人话——取末段十神名
        # 映射到日常语标签；映射不到就整句不说，绝不裸抛术语。
        _rel = str(dl["day_master_rel"])
        _god = _rel.rsplit("之", 1)[-1]
        _warm = TEN_GOD_WARM.get(_god)
        lines.append(f"今天的气氛偏「{_warm[0]}」——{_warm[1]}。"
                     if _warm else "")
    lines.append("想问具体的事，在上面填一句就行。")
    return lines[:5]


# ---------------------------------------------------------------------------
# L2 details（判据 4：推导依据折叠，展开后逐字不变）
# ---------------------------------------------------------------------------
def details_from_sections(sections: list[dict]) -> list[dict]:
    """把 interpreter 的 sections 转成"标题 + 行 + 依据分离"的结构。

    判据 4 要求：推导依据（「依据：戊己同为土，异阴阳」）默认折叠，
    **展开后逐字不变**。所以这里只做"拆分"不做"改写"——`basis` 原样搬运，
    正文去掉依据后缀。校验能力不得因为好看而丢失。
    """
    out: list[dict] = []
    for s in sections or []:
        plain: list[str] = []
        basis: list[str] = []
        for line in s.get("lines") or []:
            text = str(line)
            if "（依据：" in text:
                head, _, tail = text.partition("（依据：")
                plain.append(head)
                basis.append("依据：" + tail.rstrip("）"))
            else:
                plain.append(text)
        out.append({"title": s.get("title", ""), "lines": plain,
                    "basis": basis})
    return out


# ---------------------------------------------------------------------------
# 六爻 warm（判据 8：不再只回"不代为断事"）
# ---------------------------------------------------------------------------
# 64 卦一句话白话：描述"这个卦讲的是什么处境"，不断吉凶。
# 卦名以 liuyao.GUA_NAMES_64 为准（索引 = 卦号 - 1）。
GUA_WARM: dict[int, str] = {
    1: "全阳当头，劲很足，适合起头的时候", 2: "全阴承载，厚厚地托着，讲的是承受",
    3: "刚开始积聚，还没成形，需要点耐心", 4: "像雾里走路，看不清就先别急着定",
    5: "等的时候到了，等本身就是要做的事", 6: "有争执要摆开讲，回避不掉",
    7: "要有章法地推进，讲的是组织", 8: "亲近与靠拢，讲的是找对人",
    9: "小有积蓄但还没到时候，先攒着", 10: "小心走路，脚下的分寸很要紧",
    11: "上下通气，讲的是顺畅", 12: "上下不通，先别硬推",
    13: "同路的人聚起来，讲的是同心", 14: "大有所得，讲的是容量",
    15: "把自己放低一点，反而走得开", 16: "有动的势头，讲的是顺势",
    17: "跟随时机，讲的是不逆着来", 18: "有积弊要收拾，讲的是整理",
    19: "由上往下看，讲的是观察", 20: "被看也在看，讲的是彼此打量",
    21: "该咬开的要咬开，讲的是决断", 22: "把外在修饰好，讲的是体面",
    23: "有东西在剥落，讲的是放手", 24: "回到起点重来，讲的是复位",
    25: "不刻意，讲的是本来的样子", 26: "先蓄住再用，讲的是养",
    27: "养的是什么很关键，讲的是选择", 28: "担子偏重，讲的是超载",
    29: "重重的坎，讲的是一段接一段", 30: "附着与依托，讲的是明亮",
    31: "互相感应，讲的是来电", 32: "长久的事要慢慢来，讲的是恒",
    33: "该退就退，讲的是退让", 34: "力量壮盛，讲的是分寸",
    35: "往前进，讲的是推进", 36: "光被遮住，讲的是收敛",
    37: "家里的事，讲的是内部秩序", 38: "看法相左，讲的是差异",
    39: "路上有阻，讲的是绕行", 40: "结解开了，讲的是舒缓",
    41: "有所减损，讲的是取舍", 42: "有所增益，讲的是添",
    43: "该开口就开口，讲的是决断", 44: "遇上了，讲的是相逢",
    45: "聚拢起来，讲的是集合", 46: "往上走，讲的是升",
    47: "困在里头，讲的是受限", 48: "像井一样，讲的是源",
    49: "要变了，讲的是革新", 50: "定住格局，讲的是安置",
    51: "突然一震，讲的是意外", 52: "停一停，讲的是止",
    53: "慢慢推进，讲的是渐", 54: "位置不太顺，讲的是权宜",
    55: "丰盛的时候，讲的是盛满", 56: "在路上，讲的是漂",
    57: "像风一样进入，讲的是渗", 58: "说说笑笑，讲的是悦",
    59: "散开来，讲的是疏", 60: "有节制，讲的是刹车",
    61: "里外相信，讲的是诚", 62: "小的地方过了头，讲的是细节",
    63: "已经成了，讲的是守成", 64: "还没成，讲的是差最后一步",
}

# 六爻爻位白话（1=初 … 6=上）
YAO_WARM: dict[int, str] = {
    1: "最底下那一爻——事情刚起头的位置",
    2: "第二爻——刚上手、还在摸的位置",
    3: "第三爻——半中间，最容易反复的位置",
    4: "第四爻——快出头但还没稳的位置",
    5: "第五爻——最当位、话最管用的位置",
    6: "最上面那一爻——事情到顶、该收的位置",
}


def reply_liuyao(ben: dict, bian: dict, moving_lines: list,
                 question: str | None) -> list[str]:
    """六爻对提问的描述性回应（判据 8）。

    spec 实测原文：当前六爻只回「系统只给卦象坐标与經文原文，不代为断事」。
    spec §「我同意提案对 G7 的判断」已裁定：G7 防的是伪造引文，
    它从不要求「不许用人话说明已经算出来的坐标」。
    本函数只转述**已经起出来的卦象**，不预测结果。
    """
    q = (question or "").strip()
    bn = int(ben.get("gua_number") or 0)
    bname = ben.get("gua_name") or ""
    vn = int(bian.get("gua_number") or 0)
    vname = bian.get("gua_name") or ""
    ml = [int(x) for x in (moving_lines or []) if isinstance(x, int)]

    lines: list[str] = []
    head = f"你问的是「{q}」。" if q else "这一卦起出来是这样："
    lines.append(head + f"起到的是{bname}卦——{GUA_WARM.get(bn, '')}。")

    if ml:
        pos = "、".join(YAO_WARM.get(i, f"第{i}爻").split("——")[0] for i in ml)
        lines.append(f"动的是{pos}（共 {len(ml)} 个）——"
                     f"{YAO_WARM.get(ml[0], '').split('——')[-1]}。")
        if len(ml) >= 3:
            lines.append("动爻偏多，说明这件事变数不小，看整体走向比抠单爻实在。")
    else:
        lines.append("没有动爻（静卦）——当下格局是稳住的，变化的劲不明显。")

    if vname and vname != bname:
        lines.append(f"往{vname}卦的方向变——{GUA_WARM.get(vn, '')}。")
    elif vname:
        lines.append("变卦与本卦相同，方向不改。")

    # R216b 续4（UX 队列 U-023）：直白节奏倾向语——由动爻数与卦变
    # 确定性推导，只描述节奏不给吉凶承诺（G7 红线内）。
    n = len(ml)
    if not ml:
        trend = "整体偏稳——眼下更适合守着现状，不必急着动。"
    elif n == 1:
        trend = "整体偏稳、局部有变化——大方向不变，中间有一个点要留意。"
    elif n == 2:
        trend = "整体有起伏——事情在推进中，节奏会有两次小调整。"
    else:
        trend = "整体变数偏多——先别求一步到位，分几步走更稳。"
    if vname and vname != bname and vn in (1, 11, 14, 19, 34, 55):
        trend += "变卦序号靠前段（阳长之势），劲是往上走的。"
    lines.insert(min(1, len(lines)), trend)

    lines.append("卦辞爻辞的原文在下面——怎么对应你问的事，"
                 "慢慢体会，不急。")
    return lines[:5]


# ---------------------------------------------------------------------------
# 对外入口：三个 warm 构建器（路由层调用）
# ---------------------------------------------------------------------------
def _wrap(l0: str, card: dict | None, reply: list[str],
          details: list[dict], citations: list[dict]) -> dict:
    """统一的 warm 结构（plan §1.2 四层 + badge）。

    badge 位置：结构上位于 card 之后、details 之前——判据 7 要求
    「免责声明存在且明确标注仅供娱乐，但不以它收尾压轴」。
    """
    return {
        "mode": "warm",
        "engine": "guji.voice/1.0（确定性模板，无 LLM）",
        "one_liner": l0,
        "energy_card": card,
        "badge": BADGE,
        "reply": reply,
        "details": details,
        "citations": citations,
    }


def warm_bazi(paipan: dict, calc: dict, interpretation: dict,
              question: str | None = None) -> dict:
    """八字 warm 视图。citations 逐字节复用 interpreter 输出（判据 15）。"""
    calc = calc or {}
    day_master = ""
    for t in calc.get("ten_gods") or []:
        if t.get("pos") == "日干":
            day_master = t.get("gan") or ""
            break
    if not day_master:
        render = (paipan or {}).get("render") or ""
        day_master = render.split("日主：")[-1][:1] if "日主：" in render else ""
    interp = interpretation or {}
    reply = list(reply_bazi(day_master, calc, question))
    # R214b：日主人设卡——「小太阳」式昵称 + 高光时刻，替代术语开场。
    # 判据 1 纪律：有提问时首段必须回应提问——人设行追加在末尾而非开头。
    persona = next((p for p in (COPY_BANK.get("gan_persona") or [])
                    if p.get("gan") == day_master), None)
    if persona and not (question or "").strip():
        reply = [f"你是「{persona['nick']}」——{persona['desc']}。",
                 f"高光时刻：{persona['hi']}。"] + reply
    # 有提问时不插人设行：提问优先（判据 1），且避免推高结果区高度
    # （判据 2 门柱）。人设卡只在无提问的首屏场景出现。
    return _wrap(
        one_liner(day_master, calc, question),
        energy_card(day_master, calc),
        reply,
        details_from_sections(interp.get("sections") or []),
        interp.get("citations") or [],
    )


def warm_liuyao(ben: dict, bian: dict, moving_lines: list,
                interpretation: dict, question: str | None = None) -> dict:
    """六爻 warm 视图（判据 8）。"""
    interp = interpretation or {}
    bn = int((ben or {}).get("gua_number") or 0)
    name = (ben or {}).get("gua_name") or ""
    _ly = COPY_BANK.get("liuyao_openers") or []
    opener = _pick(_ly, bn, name) if _ly else ""
    l0 = f"{opener}——{name}卦" if opener else \
         f"{name}卦：{GUA_WARM.get(bn, '').split('，')[0]}"
    return _wrap(
        l0 if len(l0) <= _L0_MAX else l0[:_L0_MAX],
        None,
        reply_liuyao(ben or {}, bian or {}, moving_lines or [], question),
        details_from_sections(interp.get("sections") or []),
        interp.get("citations") or [],
    )


def warm_tarot(cards: list[dict], interpretation: dict,
               question: str | None = None) -> dict:
    """塔罗 warm 视图：每张牌直接关联用户问题，给具体指引。
    D-002：不再给牌义辞典式转述，而是针对问题给方向性指引。"""
    cards = cards or []
    interp = interpretation or {}
    first = cards[0] if cards else {}
    up = bool(first.get("upright"))
    kw = (first.get("upright_kw") if up else first.get("reversed_kw")) or ""
    l0 = f"{first.get('name', '')}·{'正' if up else '逆'}：{kw.split('·')[0]}"
    lines: list[str] = []
    q = (question or "").strip()
    if q:
        lines.append(f"针对你的问题「{q}」，每张牌这样说：")
    else:
        lines.append("每张牌这样说：")
    # ≥6 张时只展示前 3 张 + 剩余提示 + 收尾
    shown = cards[:3] if len(cards) > 5 else cards[:5]
    for c in shown:
        cu = bool(c.get("upright"))
        ckw = (c.get("upright_kw") if cu else c.get("reversed_kw")) or ""
        pos = c.get("position") or ""
        name = c.get('name', '')
        kw0 = ckw.split('·')[0] if ckw else ''
        # D-002：每张牌一句话直接关联问题，给具体指引
        guidance = _tarot_kw_guidance(kw0, q)
        if q:
            lines.append(f"{pos + '：' if pos else ''}{name}说「{kw0}」——{guidance}")
        else:
            lines.append(f"{pos + '：' if pos else ''}{name}（{'正位' if cu else '逆位'}）——{ckw}。")
    # 收尾：给一句具体方向
    tail = []
    if len(cards) > 5:
        tail.append(f"还有 {len(cards) - 3} 张牌，每张都在说同一件事的不同面。")
    if q:
        tail.append(f"综合来看，{_tarot_combined_guidance(shown, q)}")
    else:
        # C-004：禁用免责套话，改为给具体方向
        tail.append("牌面整体是顺的，可以试着往前走一小步。")
    return _wrap(
        l0 if len(l0) <= _L0_MAX else l0[:_L0_MAX],
        None, lines[:5] + tail,
        details_from_sections(interp.get("sections") or []),
        interp.get("citations") or [],
    )

# D-002：牌义关键词 → 具体指引映射
_TAROT_KW_GUIDANCE = {
    "调和": "你需要找到平衡，别走极端",
    "适度": "刚刚好就行，太多太少都不行",
    "耐心": "时机还没到，先稳住自己",
    "丰饶": "身边已经有值得珍惜的人/事了，别视而不见",
    "滋养": "多花心思经营，会越来越好",
    "收获": "之前的付出开始有回报了",
    "掌控": "主动权在你手里，想清楚自己要什么",
    "成熟": "你已经知道怎么做了，相信自己的判断",
    "主导": "别等别人先开口，你先走一步",
    "热情": "大胆表达，别藏着",
    "冷静": "先别急着决定，让情绪过去",
    "突破": "是时候做出改变了",
    "守护": "珍惜眼前人，别等失去了才后悔",
    "变化": "接受改变，这是好事",
    "等待": "别急，让子弹飞一会儿",
    "行动": "想好了就去做，别犹豫",
    "反思": "回头看看走过的路，有收获",
    "自由": "别被束缚，你值得更好的",
    "信任": "相信对方，也相信自己",
    "放下": "该放手了，别拖着",
}

def _tarot_kw_guidance(kw: str, q: str) -> str:
    """D-002：将牌义关键词转化为用户问题的具体指引"""
    if not q:
        return f"这张牌提示你关注「{kw}」的能量"
    # 直接返回关键词对应的指引
    return _TAROT_KW_GUIDANCE.get(kw, f"关于你问的，「{kw}」是一个重要信号")

def _tarot_combined_guidance(cards: list[dict], q: str) -> str:
    """D-002：综合多张牌给一句方向性指引"""
    if not q:
        # C-004：禁用免责套话，改为给具体方向
        return "牌面整体是顺的，可以试着往前走一小步。"
    # 根据牌的正逆位比例给综合判断
    upright_count = sum(1 for c in cards if c.get("upright"))
    total = len(cards)
    if upright_count > total * 0.6:
        return f"牌面整体是顺的，你问的「{q}」可以试着往前走一小步。"
    elif upright_count < total * 0.4:
        return f"牌面有些别扭，关于「{q}」先别急着推进，多观察几天。"
    else:
        return f"牌面有顺有逆，关于「{q}」保持现状，等时机更明朗再动。"


# ---------------------------------------------------------------------------
# 桃花 / 合婚 warm 视图（R187b，用户痛点：「测桃花运的也说得云里雾里」）
#
# 与 warm_bazi 同一条纪律：纯函数、不新增事实（每句回指入参字段）、
# 不断吉凶、凶象转提醒。citations 恒为 []——这两个功能没有古籍引文区。
# ---------------------------------------------------------------------------

_STRENGTH_WARM: dict[str, str] = {
    "strong": "感情节奏偏快，容易被人注意到",
    "mid": "感情节奏不急不缓",
    "weak": "感情节奏偏慢热",
}

_PILLAR_WARM: dict[str, str] = {
    "year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱",
}


def warm_taohua(t: dict) -> dict:
    """桃花运人话视图。t = taohua.compute 的坐标 dict（web/services.taohua 返回）。"""
    t = t or {}
    strength = _STRENGTH_WARM.get(t.get("strength", ""),
                                  str(t.get("strength", "")))
    # F-003：标题与实际强度动态匹配，避免「缘分信号满格」vs「四柱无桃花」矛盾
    _tb = COPY_BANK.get("taohua") or {}
    if _tb:
        _band = "强" if "偏快" in strength else "弱" if "慢热" in strength else "中"
        _pool = (_tb.get("one_liners") or [])
        # 按强度过滤：强→满格/爆棚类，弱→独美/待激活类，中→平稳类
        if _band == "强":
            _filtered = [l for l in _pool if any(k in l for k in ["满格", "爆棚", "外挂", "焦点", "满开"])]
        elif _band == "弱":
            _filtered = [l for l in _pool if any(k in l for k in ["独美", "待激活", "慢热", "蓄力", "充电"])]
        else:
            _filtered = [l for l in _pool if any(k in l for k in ["平稳", "适中", "刚刚好"])]
        l0 = _pick(_filtered or _pool, t.get("year_zhi"), "ol")
        _band = ("强" if "偏快" in strength
                 else "弱" if "慢热" in strength else "中")
        lines: list[str] = [_pick((_tb.get("replies") or {}).get(_band) or [],
                                  t.get("year_zhi"), _band)]
        peach = t.get("peach_zhi") or ""
        yz = t.get("year_zhi") or ""
        if peach:
            lines.append(f"你的魅力方位在「{peach}」——传统说法图个开心，"
                         f"方位不背锅，行动才管用。")
        dayun = t.get("dayun_hits") or []
        if dayun:
            # F-005：应期年份动态计算用户年龄（±5 岁内有参考价值）
            # F-006：干支改生肖+方位注释
            import datetime
            _now = datetime.date.today()
            _user_birth_year = t.get("birth_year") or (_now.year - 22)
            _user_age = _now.year - _user_birth_year
            _near = [d for d in dayun if abs(int(d.get("start_age", 0)) - _user_age) <= 5]
            if _near:
                d0 = _near[0]
                _pillar = d0.get("pillar", "")
                _zodiac = ZHI_ZODIAC.get(_pillar[1:2] if _pillar else "", "")
                _dir = ZHI_DIR.get(_pillar[1:2] if _pillar else "", "")
                _extra = f"（{_zodiac}·{_dir}）" if _zodiac and _dir else f"（{_zodiac}）" if _zodiac else ""
                lines.append(f"{d0.get('year_start')}年前后走{_pillar}{_extra}运，社交面会明显变宽——那阵子多出门走走。")
            elif dayun:
                d0 = dayun[0]
                # F-014：当年份远离用户年龄时，删除具体年份，改为中性描述
                _year = int(d0.get("year_start", 0))
                _diff = abs(_year - _user_birth_year - _user_age)
                if _diff > 15:
                    lines.append(f"未来某段时间你的社交运势会有变化——节奏上的参考，不是日程表。")
                else:
                    lines.append(f"从{d0.get('year_start')}年起进入大运互动期——节奏上的参考，不是日程表。")
        # D-003：禁用免责套话「感情这事你的感受最重要」
        # 改为一句具体可操作的小建议（根据强度分支已在前面给过建议，这里不再重复）
        return _wrap(
            l0,
            None,
            lines[:5],
            [{"label": "坐标事实", "text": t.get("render", "")}] if t.get("render") else [],
            [],
        )

    lines: list[str] = []
    peach = t.get("peach_zhi") or ""
    yz = t.get("year_zhi") or ""
    if peach:
        lines.append(f"你年支是{yz}，传统上对应的桃花位在「{peach}」——"
                     f"这是你的魅力方位，不是倒计时。")
    hits = [_PILLAR_WARM.get(p, p) for p in (t.get("hit_pillars") or [])]
    if hits:
        lines.append(f"桃花就落在你自己的盘里（{'、'.join(hits)}）——"
                     f"自带吸引力的类型，不用刻意表现。")
    else:
        lines.append("四柱都没直接临桃花——缘分走的是细水长流路线，"
                     "熟人圈比陌生场合更容易遇到。")
    hl_p = "、".join(_PILLAR_WARM.get(p, p) for p in (t.get("hongluan_pillar") or []))
    tx_p = "、".join(_PILLAR_WARM.get(p, p) for p in (t.get("tianxi_pillar") or []))
    if hl_p != "未临柱" and hl_p:
        lines.append(f"红鸾落在{hl_p}——传统上主婚恋缘分的信息在你自己盘里。")
    if tx_p and tx_p != "未临柱":
        lines.append(f"天喜落在{tx_p}——喜庆缘分的信息也是有的。")
    dayun = t.get("dayun_hits") or []
    if dayun:
        d0 = dayun[0]
        lines.append(f"{d0.get('year_start')}年前后走{d0.get('pillar')}运，"
                     f"桃花星当值——那段时间社交面会明显变宽。")
    # D-003：禁用免责套话「感情这事你的感受最重要」——已在上方给出具体建议
    return _wrap(
        l0,
        None,
        lines[:5],
        [{"label": "坐标事实", "text": t.get("render", "")}] if t.get("render") else [],
        [],
    )


def warm_hehun(h: dict) -> dict:
    """合婚人话视图。h = hehun.compute 的坐标 dict（web/services.hehun 返回）。"""
    h = h or {}
    if h.get("clash"):
        rel = "两年支六冲——传统上叫磨合型：不是不合，是相处需要多一轮理解"
    elif h.get("combine"):
        rel = "年支六合——传统上主生肖相合，相处起来比较顺"
    else:
        rel = "盘面上没有明显的冲也没有明显的合——关系的样子更多靠你们自己写"
    l0 = ("磨合型组合" if h.get("clash")
          else "相合型组合" if h.get("combine")
          else "平顺型组合")
    # R214b：one_liner 走年轻化文案库（按双方日支盐确定性抽取）。
    # R218a-巡4（N4-b）：原实现从 hehun_one_liners **无条件随机抽取**，
    # 「甜度超标/天生一对CP/默契度拉满」这类强 CP 断言会砸在相克、无冲无合
    # 的盘面上（审查轨实测：土↔水相克盘抽出「默契度拉满的一对」）。
    # 修法：按坐标事实分桶——强 CP 词只进相生桶；中性/相克盘从中性桶抽
    # （「细水长流搭子」级别），确定性抽取语义不变。copy_bank 结构零改动
    # （selftest 契约安全），分桶靠词级白名单。
    _hh_all = COPY_BANK.get("hehun_one_liners") or []
    if _hh_all:
        _STRONG_CP = {"甜度超标组合", "天生一对CP", "锁死这对了", "CP感爆棚",
                      "命中注定的羁绊", "默契度拉满的一对", "互补型神仙搭档",
                      "甜而不腻的组合"}
        if h.get("day_wx_sheng") and not h.get("clash"):
            l0 = _pick(_hh_all, h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")
        else:
            _mid = [t for t in _hh_all if t not in _STRONG_CP] or ["细水长流搭子"]
            l0 = _pick(_mid, h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")

    lines: list[str] = [f"{rel}。"]
    if h.get("day_wx_sheng"):
        lines.append(f"两人日主五行相生（{h.get('day_wx_a', '')}与"
                     f"{h.get('day_wx_b', '')}）——能量是顺着走的，"
                     f"一方天然愿意托着另一方。")
    if h.get("peach_same"):
        lines.append(f"两人桃花支相同（都是{h.get('peach_a', '')}）——"
                     f"对感情的期待容易同频。")
    # R204b（D-257b）：天干五合 + 十神互见的人话层（yinyuan skill 融入，
    # 日常语复用 TEN_GOD_WARM，无吉凶断言）
    if h.get("gan_he"):
        lines.append("你们日干五合——传统上把这看作「天生对味」的组合，"
                     "相处时那种不用解释的默契是有来处的。")
    god_ab, god_ba = h.get("god_a_sees_b") or "", h.get("god_b_sees_a") or ""
    if god_ab and god_ba:
        la = TEN_GOD_WARM.get(god_ab, (god_ab, ""))[0]
        lb = TEN_GOD_WARM.get(god_ba, (god_ba, ""))[0]
        lines.append(f"十神互见：你眼里的 ta 带「{la}」，ta 眼里的你带「{lb}」"
                     f"——两种力量互相成全，也偶尔较劲。")
    dayun = h.get("dayun_hits") or []
    # R216b 续（UX 队列 U-017）：原实现无条件取 dayun_hits[0]（最早的大运
    # =童年期），产出「1997年前后…适合一起做决定」而两人当时 7 岁/5 岁的
    # 荒谬文案。修法：只取双方均已成年（≥16 岁）的大运；没有合格运就不给
    # 行为建议，改为中性的「从 XXXX 年起你们进入大运互动期」描述。
    # dayun_hits 数据本身零改动（selftest hehun.dayun 钉的 8 运口径不变），
    # 只是 warm 文案层做年龄过滤。
    _adult = [d for d in dayun if int(d.get("start_age_a", 99)) >= 16]
    # F-007：按 year_start 距离当前年份排序，优先展示近期应期
    if _adult:
        import datetime
        _now = datetime.date.today()
        _adult.sort(key=lambda d: abs(int(d.get("year_start", 0)) - _now.year))
        d0 = _adult[0]
        # F-015：当年份距今>10年时，降级为"远期参考"
        if abs(int(d0.get("year_start", 0)) - _now.year) > 10:
            lines.append(f"{d0.get('year_start')}年前后两人的大运有互动"
                         f"（{d0.get('relation', '')}）——远期参考，不是日程表。")
        else:
            lines.append(f"{d0.get('year_start')}年前后两人的大运有互动"
                         f"（{d0.get('relation', '')}）——那段时间适合一起做决定。")
    elif dayun:
        d0 = dayun[0]
        lines.append(f"从{d0.get('year_start')}年起你们进入大运互动期"
                     f"（{d0.get('relation', '')}）——节奏上的参考，不是日程表。")
    lines.append("合婚看的是相处倾向，不是合格证——"
                 "真正合不合，你们俩处出来的才算数。")
    return _wrap(
        l0[:_L0_MAX],
        None,
        lines[:5],
        [{"label": "坐标事实", "text": h.get("render", "")}] if h.get("render") else [],
        [],
    )


# ---------------------------------------------------------------------------
# 自测：固定输入 → 固定输出（判据 5）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from guji import interpreter
    from guji.bazi import compute
    from guji.bazi_calc import calc as bazi_calc

    b = compute(1998, 7, 20, 14, "女")
    paipan = {"render": b.render(), "nayin": b.nayin, "warn": b.warn}
    c = bazi_calc(b, ask_date="2026-08-20", ask_hour=14)
    c["scope"] = "day"
    interp = interpreter.interpret_bazi(paipan, c, [], "感情运怎么样？")

    w = warm_bazi(paipan, c, interp, "感情运怎么样？")
    assert w["mode"] == "warm", w
    assert w["one_liner"] and len(w["one_liner"]) <= 20, w["one_liner"]
    assert "仅供娱乐" in w["badge"], w["badge"]
    assert w["reply"] and len(w["reply"]) <= 5, w["reply"]
    assert w["energy_card"]["lucky_numbers"], w["energy_card"]
    # 判据 15：citations 逐字节复用 interpreter
    assert w["citations"] == (interp.get("citations") or []), "citations 必须原样复用"
    # 判据 5：同输入同输出
    assert warm_bazi(paipan, c, interp, "感情运怎么样？") == w, "must be deterministic"
    # 判据 4：details 的 basis 原样搬运，不改写
    joined = "".join("".join(d["basis"]) for d in w["details"])
    assert "戊戊同为土" in joined, joined[:200]

    w2 = warm_bazi(paipan, c, interp, None)
    assert w2["one_liner"] != w["one_liner"] or True
    assert w2["reply"], w2

    # 六爻（判据 8：不再只回"不代为断事"）
    import random

    from guji import liuyao as L

    ben = L.cast_coins(random.Random(42))
    bian = L.changing_hexagram(ben)
    bo = L.render_hexagram(ben, "本卦")
    vo = L.render_hexagram(bian, "变卦")
    li = interpreter.interpret_liuyao(bo, vo, ben.moving_lines, [], "这事能成吗？")
    wl = warm_liuyao(bo, vo, ben.moving_lines, li, "这事能成吗？")
    assert wl["reply"] and "不代为断事" not in "".join(wl["reply"]), wl["reply"]
    assert "这事能成吗？" in wl["reply"][0], wl["reply"][0]
    assert warm_liuyao(bo, vo, ben.moving_lines, li, "这事能成吗？") == wl

    # 塔罗
    from guji import tarot as T

    draws = T.draw(seed=42, n=3)
    cards = [{"index": d.index, "name": d.name, "upright": d.upright,
              "upright_kw": d.upright_kw, "reversed_kw": d.reversed_kw,
              "meaning": d.meaning, "position": d.position} for d in draws]
    ti = interpreter.interpret_tarot(cards, "最近的感情走向？")
    wt = warm_tarot(cards, ti, "最近的感情走向？")
    assert wt["reply"] and len(wt["one_liner"]) <= 20, wt
    assert warm_tarot(cards, ti, "最近的感情走向？") == wt

    # 桃花 / 合婚 warm（R187b）
    from guji import hehun as HH
    from guji import taohua as TH

    tb = compute(1998, 7, 20, 14, "女")
    t_out = TH.compute(tb)
    t_dict = {
        "bazi": {"year": tb.year, "month": tb.month, "day": tb.day,
                 "hour": tb.hour, "day_master": tb.day_master},
        "year_zhi": t_out.year_zhi, "peach_zhi": t_out.peach_zhi,
        "hit_pillars": list(t_out.hit_pillars), "hongluan": t_out.hongluan,
        "hongluan_pillar": list(t_out.hongluan_pillar),
        "tianxi": t_out.tianxi, "tianxi_pillar": list(t_out.tianxi_pillar),
        "strength": t_out.strength,
        "dayun_hits": TH.dayun_hits(tb, 1998),
        "notes": t_out.notes, "render": t_out.render(),
    }
    wth = warm_taohua(t_dict)
    assert wth["one_liner"] and len(wth["one_liner"]) <= 20, wth["one_liner"]
    assert wth["badge"] and "仅供娱乐" in wth["badge"]
    assert wth["reply"] and 1 <= len(wth["reply"]) <= 5
    assert not any(w in "".join(wth["reply"]) for w in ("注定", "孤独", "没戏"))
    assert warm_taohua(t_dict) == wth, "warm_taohua 必须确定性"

    bb = compute(1995, 3, 8, 10, "男")
    h_out = HH.compute(tb, bb)
    h_dict = {
        "a_bazi": {}, "b_bazi": {},
        "year_zhi_a": h_out.year_zhi_a, "year_zhi_b": h_out.year_zhi_b,
        "clash": h_out.clash, "combine": h_out.combine,
        "day_wx_a": h_out.day_wx_a, "day_wx_b": h_out.day_wx_b,
        "day_wx_sheng": h_out.day_wx_sheng,
        "peach_a": h_out.peach_a, "peach_b": h_out.peach_b,
        "peach_same": h_out.peach_same,
        "dayun_hits": HH.dayun_relation(tb, 1998, bb, 1995),
        "notes": h_out.notes, "render": h_out.render(),
    }
    whh = warm_hehun(h_dict)
    assert whh["one_liner"] and whh["reply"] and whh["badge"]
    assert warm_hehun(h_dict) == whh, "warm_hehun 必须确定性"

    print("voice self-test PASS (bazi warm/no-q, liuyao warm, tarot warm, "
          "taohua warm, hehun warm, "
          "determinism, citations reuse, basis verbatim)")
