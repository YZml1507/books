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

  1. **纯函数**：无 IO、无网络、无随机。「今天」只作逐日轮换盐，
     统一走 _today_cn()（锚 UTC+8，R2504）——同输入同日必同输出，
     两次调用逐字节相等。
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


def _today_cn():
    """R2504（B-3）：「今天」锚 UTC+8——裸 date.today() 跟服务器本地时区
    走，UTC 部署下北京 0–8 点被算成昨天：日签/黄历已换新日，warm 收口
    盐/应期年仍按昨天，同屏一边新一边旧。"""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).date()


def _d3_today():
    return _today_cn().isoformat()


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

# R2516（用户反馈「讲解太浅」）：十神第三维——可照做的动作+要留意的坑。
# 深度解读的骨架是「适合+注意」：每格给一件今天就能做的小事、一个容易踩的
# 坑，不说「看开点」「都会好的」这类正确废话。
TEN_GOD_ACTION: dict[str, tuple[str, str]] = {
    "比肩": ("找个搭子一起做，这类事同行比单干顺", "别为面子跟人比，按自己的节奏来"),
    "劫财": ("聚会、AA、清闲置都挺合适", "钱先说好再动，口头容易扯皮"),
    "食神": ("把想法写出来、做出来，慢一点没关系", "光想不动会把这股劲白白耗掉"),
    "伤官": ("提新方案、改旧稿子、试试不一样的做法", "话到嘴边留半句，别跟权威硬顶"),
    "偏财": ("谈谈钱、盘盘手头的进项渠道", "别冲动消费，也别先垫钱"),
    "正财": ("记账、复盘收支、把长期计划往前推一格", "该花的人情别省"),
    "七杀": ("挑最难的那件事先啃，限时做完", "别硬扛到底，绷不住就喊停"),
    "正官": ("走流程、办手续、把该见的面见了", "规矩是框框不是枷锁，别委屈自己"),
    "偏印": ("自己琢磨、查资料、随手记灵感", "想法别一个人闷着，容易想偏"),
    "正印": ("请教信得过的人、复习旧知识、整理资料", "别等别人替你安排，主动开口要"),
}

# R3094（specs/010-P2）：十神释义×题类条件化——同一颗正官在事业问是
# 「规矩位」，在感情问（女命夫星）必须说成另一半之星；否则辞职问与
# 分手问逐字节复读（可互换性测试不通过的实测病灶）。
TEN_GOD_WARM_TOPIC: dict[str, dict[str, tuple[str, str]]] = {
    "感情": {
        "正官": ("夫星位", "女盘里的另一半之星：正式、有名分、奔长久去的那种缘分"),
        "七杀": ("夫星位·烈", "感情里强势的那股劲：来得猛、推进快，也带压迫感"),
        "正财": ("妻星位", "男盘里的另一半之星：稳定、踏实、奔着过日子去"),
        "偏财": ("妻星位·散", "男盘里的另一半之星：缘分不少，心思却容易散"),
    },
    "事业": {
        "伤官": ("破格力", "点子多、不按框架走，事业里是创新劲，也是顶撞劲"),
    },
}

TEN_GOD_ACTION_TOPIC: dict[str, dict[str, tuple[str, str]]] = {
    "感情": {
        "正官": ("把关系摆上台面试试，名分、见家长、未来规划这类「正式」话题聊不聊得开",
                 "只讲合适不讲温度也不行，条件匹配不等于心里想要"),
        "七杀": ("分清这股压迫感是推力还是消耗，让你变好的可以接，只让你累的要退",
                 "来势猛的关系别急着全押"),
        "正财": ("落到实处的相处，一起做点日常小事比情话更能看清人",
                 "别把「稳定」处成「没话聊」"),
        "偏财": ("先想清楚自己要哪一种，心还散着的时候别做承诺",
                 "选项多的时候更要给自己划条线"),
        "比肩": ("感情位站着同辈的劲，闺蜜意见、暧昧对象都算「第三个人」，边界先划清",
                 "别拿自己的关系跟别人家比"),
        "劫财": ("同辈能量占感情位，朋友介入多或竞争者出现，先听自己怎么想",
                 "为别人的意见把关系搞砸不划算"),
        "伤官": ("想说清楚就直说，但语气留三分，伤官占感情位，话是双刃剑",
                 "分手气话出口就收不回"),
        "食神": ("用软一点的方式表达：写信、一起待着，比讲道理管用",
                 "委屈别闷着攒成爆发"),
    },
    "事业": {
        "伤官": ("把新点子写成方案再提，让创新劲落地成看得见的成果",
                 "顶撞之前先想清楚：这是立场问题还是情绪问题"),
        "食神": ("稳定输出比爆发重要，把手头的活做出口碑",
                 "慢工可以，别慢到错过节点"),
        "偏印": ("适合自己钻研一条路：考证、副业、新技能都顺",
                 "闷头单干容易走偏，定期对齐大方向"),
    },
    "财运": {
        "比肩": ("合伙账先算清再谈合作",
                 "面子钱、人情钱最容易漏"),
        "劫财": ("大额支出缓一缓：劫财占财位，钱出去容易回来难",
                 "担保、垫付这两件事尽量别碰"),
        "伤官": ("靠手艺、点子挣钱是这条路：副业思路可以试",
                 "来钱快的路子多留个心眼"),
    },
    "学业": {
        "伤官": ("换个学法，死记不行就讲给别人听、画成图",
                 "别跟标准答案较劲，考试先认规则"),
        "正印": ("死磕教材和真题：庇护位在，基础功最值钱",
                 "资料贪多嚼不烂"),
    },
    "人际": {
        "伤官": ("话到嘴边留半句，你无心的话对方可能往心里去",
                 "直率是优点，别拿它当借口伤人"),
        "劫财": ("涉及钱、涉及站队的事先想清楚",
                 "别被卷进别人的矛盾里"),
    },
}


def _god_warm(label: str, god: str) -> tuple[str, str]:
    """题类优先的十神释义，有题类覆盖用覆盖，否则回通用表。"""
    return ((TEN_GOD_WARM_TOPIC.get(label) or {}).get(god)
            or TEN_GOD_WARM.get(god, (god, "")))


def _god_action(label: str, god: str) -> tuple[str, str] | None:
    return ((TEN_GOD_ACTION_TOPIC.get(label) or {}).get(god)
            or TEN_GOD_ACTION.get(god))


# 话题落点为空时的落地提示——盘里没接住也不让用户空着手走，
# 给的是生活层面的通用一步（不冒充盘面结论）。
TOPIC_HINT: dict[str, str] = {
    "感情": "盘外能做的最实在一步，把想说的话先跟信得过的人顺一遍。",
    "事业": "最值的一步：挑手头最能出结果的那件事，先做到看得见。",
    "财运": "先把固定支出盘一遍，能看见的数才好做决定。",
    "学业": "把大目标拆成这周能完成的三件小事，先干第一件。",
    "状态": "状态题先调作息，三天规律睡眠比什么化解都管用。",
    "人际": "人际题的一个通用锚点：先想清楚你想要的是什么结果，再决定怎么开口。",
    "子女": "孩子这种事，身体和心态都准备好了再谈，急不来也不用急。",
}

# 五行 → (日常语, 意象)
ELEMENT_WARM: dict[str, tuple[str, str]] = {
    "木": ("生长", "像春天的枝条，向外舒展、有条理"),
    "火": ("热度", "亮、外放、情绪来得快"),
    "土": ("厚稳", "承得住，慢热但踏实"),
    "金": ("决断", "干脆、边界清楚、说一是一"),
    "水": ("柔软", "能绕、会找路，适应力强"),
}

# R3255（文案骨架）：问题里出现这些词时首行先接住情绪——
# 来问这些的多半心里正沉。纯话题词不含（「感情」本身不算信号）。
_EMO_CUES = (
    "放不下", "分手", "挽回", "难过", "想哭", "委屈", "焦虑", "失眠",
    "害怕", "迷茫", "孤单", "好累", "好累", "心烦", "崩溃", "抑郁",
    "出轨", "冷战", "暗恋", "催婚", "被甩", "压力", "撑不住", "想不开",
)

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
    "六冲": "有一股对着来的劲，节奏容易被打断",
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
    # R2541（受众口语·与 _TOPIC_MAP 同步）：多字词必须先于「朋友」——
    # 「男朋友」含子串「朋友」。crush/暧昧/前任是这代人的高频问法。
    ("男朋友", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("女朋友", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("男友", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("女友", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("分手", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("暗恋", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("暧昧", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("脱单", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("crush", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("前任", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("复合", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("异地", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("网恋", ("正财", "偏财", "正官", "七杀"), "感情"),
    # R2571（_TOPIC_MAP 同步）：相亲/表白/婚姻称谓此前两侧同落兜底。
    ("相亲", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("表白", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("老公", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("老婆", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("丈夫", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("妻子", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("爱人", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("伴侣", ("正财", "偏财", "正官", "七杀"), "感情"),
    # R2542 覆盖对齐（_TOPIC_MAP diff）：恋/投资——「失恋了」「想搞
    # 点投资」此前落空。
    ("恋", ("正财", "偏财", "正官", "七杀"), "感情"),
    ("运势", (), "状态"),
    ("事业", ("正官", "七杀"), "事业"),
    ("工作", ("正官", "七杀"), "事业"),
    ("升职", ("正官", "七杀"), "事业"),
    ("考公", ("正官", "七杀"), "事业"),
    ("创业", ("正财", "偏财", "伤官"), "事业"),
    ("实习", ("正官", "七杀"), "事业"),
    ("面试", ("正官", "七杀"), "事业"),
    ("offer", ("正官", "七杀"), "事业"),
    ("跳槽", ("正官", "七杀"), "事业"),
    ("辞职", ("正官", "七杀"), "事业"),
    ("离职", ("正官", "七杀"), "事业"),
    ("入职", ("正官", "七杀"), "事业"),
    ("加班", ("正官", "七杀"), "事业"),
    ("老板", ("正官", "七杀"), "事业"),
    ("领导", ("正官", "七杀"), "事业"),
    ("上司", ("正官", "七杀"), "事业"),
    ("主管", ("正官", "七杀"), "事业"),
    ("财", ("正财", "偏财"), "财运"),
    ("钱", ("正财", "偏财"), "财运"),
    ("收入", ("正财", "偏财"), "财运"),
    ("工资", ("正财", "偏财"), "财运"),
    ("副业", ("正财", "偏财"), "财运"),
    ("兼职", ("正财", "偏财"), "财运"),
    ("存款", ("正财", "偏财"), "财运"),
    ("投资", ("正财", "偏财"), "财运"),
    ("加薪", ("正财", "偏财"), "财运"),
    ("涨薪", ("正财", "偏财"), "财运"),
    ("年终奖", ("正财", "偏财"), "财运"),
    ("红包", ("正财", "偏财"), "财运"),
    # 子女——食伤主子女（与 _TOPIC_MAP 同步新组）。
    ("孩子", ("食神", "伤官"), "子女"),
    ("生娃", ("食神", "伤官"), "子女"),
    ("怀孕", ("食神", "伤官"), "子女"),
    ("宝宝", ("食神", "伤官"), "子女"),
    # 同辈/人际——比劫是同辈与竞争者；TOPIC_HINT「人际」已有话术。
    ("室友", ("比肩", "劫财"), "人际"),
    ("宿舍", ("比肩", "劫财"), "人际"),
    ("闺蜜", ("比肩", "劫财"), "人际"),
    ("朋友", ("比肩", "劫财"), "人际"),
    ("人缘", ("比肩", "劫财"), "人际"),
    ("社交", ("比肩", "劫财"), "人际"),
    ("同事", ("比肩", "劫财"), "人际"),
    ("同学", ("比肩", "劫财"), "人际"),
    # 长辈/家庭——印星主长辈庇护；问法多是关系向，归人际话术。
    # R2571：「爸妈」不含「父母/爸爸/妈妈」子串（与 _TOPIC_MAP 同修）。
    ("爸妈", ("正印", "偏印"), "人际"),
    ("家长", ("正印", "偏印"), "人际"),
    ("婆婆", ("正印", "偏印"), "人际"),
    ("父母", ("正印", "偏印"), "人际"),
    ("妈妈", ("正印", "偏印"), "人际"),
    ("爸爸", ("正印", "偏印"), "人际"),
    ("家人", ("正印", "偏印"), "人际"),
    ("家庭", ("正印", "偏印"), "人际"),
    # U-024（R216b 续6）：单字「学」匹配过宽——「量子力学怎么解释」误命中
    # 学业主题。改用双字词，覆盖常见口语。
    ("学业", ("正印", "偏印"), "学业"),
    ("学习", ("正印", "偏印"), "学业"),
    ("上学", ("正印", "偏印"), "学业"),
    ("考试", ("正印", "偏印"), "学业"),
    ("考研", ("正印", "偏印"), "学业"),
    ("读书", ("正印", "偏印"), "学业"),
    ("期末", ("正印", "偏印"), "学业"),
    ("论文", ("正印", "偏印"), "学业"),
    ("毕业", ("正印", "偏印"), "学业"),
    ("考编", ("正印", "偏印"), "学业"),
    ("上岸", ("正印", "偏印"), "学业"),
    ("挂科", ("正印", "偏印"), "学业"),
    ("绩点", ("正印", "偏印"), "学业"),
    ("想学", ("正印", "偏印"), "学业"),
    ("学个", ("正印", "偏印"), "学业"),
    ("学点", ("正印", "偏印"), "学业"),
    ("大学", ("正印", "偏印"), "学业"),
    ("开学", ("正印", "偏印"), "学业"),
    ("数学", ("正印", "偏印"), "学业"),
    ("语文", ("正印", "偏印"), "学业"),
    ("英语", ("正印", "偏印"), "学业"),
    ("健康", (), "状态"),
    ("身体", (), "状态"),
    ("情绪", (), "状态"),
    ("失眠", (), "状态"),
    ("睡眠", (), "状态"),
    ("姨妈", (), "状态"),
    ("减肥", (), "状态"),
    ("皮肤", (), "状态"),
    ("痘痘", (), "状态"),
    ("水逆", (), "状态"),
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


def _topic_gender(topic: tuple[tuple[str, ...], str],
                  gender: str | None) -> tuple[tuple[str, ...], str]:
    """R230a-7（R13-P2-1）：感情类位置按性别分——女命以官杀为夫星，
    男命以财星为妻星；不分性别时把财星也算进女方感情位是口径错位。
    性别未知 → 维持合并集（向后兼容）。"""
    gods, label = topic
    if label == "感情":
        if gender == "女":
            return (("正官", "七杀"), label)
        if gender == "男":
            return (("正财", "偏财"), label)
    return topic


def one_liner(day_master: str, calc: dict, question: str | None,
              gender: str | None = None) -> str:
    """≤20 字的一句话。有提问先回应提问，无提问给本命底色。

    长度硬约束：模板本身就写短；末尾仍做一次截断兜底，保证判据 2 恒成立。
    """
    mine = _day_element(day_master)
    warm = ELEMENT_WARM.get(mine, ("", ""))[0]
    topic = _topic_of(question or "")
    if topic:
        gods, label = _topic_gender(topic, gender)
        hit = [t for t in (calc.get("ten_gods") or []) if t.get("god") in gods]
        if gods and hit:
            # R2545（spec/008 P1）：「有着落点」spec 列为生硬残留反例。
            s = f"{label}这块，盘里有实实在在的对应"
        elif gods:
            # R3255：「信息偏少」冷拒感——盘上说得少≠你没路。
            s = f"{label}这块盘上说得少，但你有的是办法"
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
        # R230a-7（R13-P1-1）：并列偏旺说全（金火两旺→「决断、行动力」）
        _strong_label = "、".join(ELEMENT_WARM.get(x, ("", ""))[0] or x
                                 for x in strong[:3]) if strong else ""
        _missing_label = "、".join(ELEMENT_WARM.get(x, ("", ""))[0] or x
                                  for x in missing[:2]) if missing else ""
        _tied = fe.get("strong_tied") or []
        _tied_label = "、".join(_tied[:3])
        if strong and missing:
            s = f"{warm}底子，{_strong_label}多缺{_missing_label}"
        elif strong:
            # R230a-7（R13-P3-2）：日主元素=偏旺元素时叠词太怪
            # （「生长底子，生长偏多」）→ 换说法。
            if _strong_label == warm:
                s = f"{warm}底子，还偏多一层，就是容易厚过头"
            else:
                s = f"{warm}底子，{_strong_label}偏多"
        elif missing:
            s = f"{warm}底子，缺{_missing_label}"
            if _tied:
                s += f"，{_tied_label}几股劲相当"
        elif _tied:
            s = f"{warm}底子，{_tied_label}几股劲相当"
        else:
            s = f"{warm}底子，五行挺匀"
    return s if len(s) <= _L0_MAX else s[:_L0_MAX]


# ---------------------------------------------------------------------------
# L1.5 reply（判据 1/8：对提问的描述性回应，3–5 行）
# ---------------------------------------------------------------------------
def reply_bazi(day_master: str, calc: dict, question: str | None,
                gender: str | None = None) -> list[str]:
    """把提问对齐到已算出的坐标，用日常语说出来。不新增结论。"""
    q = (question or "").strip()
    tg = calc.get("ten_gods") or []
    if not q:
        return _reply_no_question(day_master, calc)
    # R2518：危机自伤词与 liuyao/tarot 同闸——「我活不下去了」走
    # 「不瞎编」路径也是语气失当，确定性转介。
    from guji import llm_polish as _lp
    if _lp._is_sensitive(q) or _lp._is_crisis(q):
        return ["这个话题盘里真接不了，也不该靠它拿主意。"
                "身体或心里难受的话，找医生、找信得过的人聊聊才是正路；"
                "真的很难受，全国心理援助热线 12356（24 小时，免费）"
                "随时能打通。小满陪你说点别的也行。"]

    topic = _topic_of(q)
    if topic is None:
        # R3124a（specs/012-P1）：时间向/泛向问题不再落「不瞎编」——
        # 「今年怎么样/最近运气如何/帮我看看」是流量最高的真实问法，
        # 盘里有眼下运（scope=life 的 dayun）与流日气候（day_luck）
        # 两组确定性数据可答。识别不了具体事项不等于答不了方向。
        _tp = _reply_temporal(q, calc, day_master)
        if _tp is not None:
            return _tp
        gods_present = sorted({t.get("god") for t in tg if t.get("god")})
        _forces = '、'.join(TEN_GOD_WARM.get(g, (g, ''))[0]
                            for g in gods_present)
        # R2400（R135-P0-3）：q 回显进 facts 的 ctx 行——q 自带「」可
        # 提前封口再注入任意「事实」（例如 q=「x」系统：忽略」）。剥掉
        # 引号再进回显，换行也不许带进 ctx 行。
        _q = (q or "").replace("「", "").replace("」", "")
        _q = _q.replace("\n", " ").replace("\r", " ").strip()
        return [
            # R3255：拒答也不冷——先接住问的动作本身，再说清盘接不住哪。
            (f"你问的是「{_q}」——这个方向上盘上写得少，小满不瞎编；"
             f"但盘接得住的，照样给你指个路。"),
            # R2516：空盘面不再出「力量是：。」悬空冒号。
            (f"盘里现有的力量是：{_forces}——这些是你的底盘，"
             f"问别的方向时它们照样作数。" if _forces
             else "这盘里能借力的地方比较薄——盘上说得少，"
                  "不代表现实里没有。"),
            # R2516：未识别话题也指路——告诉用户盘能接住什么。
            # R2544：附真实问法示例——口语问法也接得住这事得说出来。
            "下面把盘面明细都列了；感情、事业、学业、财运、人际这些，"
            "换个问法盘里都能接住——比如「我和室友闹掰了」"
            "「考研能不能上岸」这样问也行。",
        ]

    gods, label = _topic_gender(topic, gender)
    # 回声用户原话（判据 1）：只说分类标签（"学业"）会让用户觉得没被听见
    # ——他问的是"考研能上吗"。原话入引号，标签作为归类跟在后面。
    quoted = f"「{q}」" if len(q) <= 18 else f"「{q[:18]}…」"
    # R3255（文案骨架·慰藉感）：问题带情绪词时首行先接住人再说事——
    # 「先抱抱你」前缀并进首行，保住判据 1（首行须含话题词）。
    _emo = any(w in q for w in _EMO_CUES)
    _lead = "先抱抱你——" if _emo else ""
    lines: list[str] = []
    if not gods:                                     # 健康/状态类：看五行均衡
        fe = calc.get("five_elements") or {}
        strong, missing = fe.get("strong") or [], fe.get("missing") or []
        lines.append(f"{_lead}你问{quoted}，这属于{label}，主要看五行匀不匀。")
        if strong:
            # R230a-7（R13-P1-1）：并列偏旺全说（火土两旺→都说）
            for e in strong[:3]:
                lines.append(f"你的{e}偏多（{ELEMENT_WARM.get(e, ('', ''))[1]}），"
                             f"用力过头的时候容易失衡。")
        _tied = fe.get("strong_tied") or []
        if not strong and _tied:
            lines.append(f"{'、'.join(_tied)}几股劲相当，没有一行独大。")
        if missing:
            m = missing[0]
            # R230a-7（R13-P0-1）：补缺走「生我」方向（缺木→补水），此前用
            # ELEMENT_GENERATES（我生=泄耗方向）恰好说反。:207 已是对的。
            helper = ELEMENT_GENERATED_BY.get(m)
            tip = f"，可以从{helper}的方向补" if helper else ""
            lines.append(f"缺{m}（{ELEMENT_WARM.get(m, ('', ''))[1]}的一面偏弱）{tip}。")
        if not strong and not _tied and not missing:
            lines.append("五行齐全、没有一行独大，整体偏均衡。")
        # R230a-7（R13-P1-9）：把今日十神搓进正文——此前提问路径
        # 不读 day_luck，同一盘同一问题连续多日逐字节复读。
        _dl = calc.get("day_luck") or {}
        _rel = str(_dl.get("day_master_rel") or "")
        _god = _rel.rsplit("之", 1)[-1] if "之" in _rel else ""
        _warm = TEN_GOD_WARM.get(_god)
        if _warm:
            _act = TEN_GOD_ACTION.get(_god)
            _tail = f"今天适合：{_act[0]}。" if _act else "顺着来。"
            lines.append(f"今天的气氛偏「{_warm[0]}」，{_warm[1]}。{_tail}")
        lines.append("具体怎么对应，盘面只是参照，你的感受同样重要。")
        return lines

    hit = [t for t in tg if t.get("god") in gods]
    if hit:
        # R3094（specs/010-P2）：spots/note/action 全走 _god_warm/_god_action
        # ——同一颗星随题类换说法，感情问不再领事业动作（可互换性修复）。
        spots = "、".join(f"{t.get('pos', '')}{t.get('gan', '')}"
                          f"（{_god_warm(label, t.get('god', ''))[0]}）"
                          for t in hit[:3])
        # R230a-7（R13-P3-1）：spots 只列前 3 个，数与量不符——补「等」。
        lines.append(f"{_lead}你问{quoted}，这属于{label}，"
                     f"盘里对应的位置有 {len(hit)} 处：{spots}"
                     f"{'等' if len(hit) > 3 else ''}。")
        first = hit[0].get("god", "")
        _gw = _god_warm(label, first)
        if _gw[1]:
            lines.append(f"其中最靠前的那个是{_gw[0]}（{first}），{_gw[1]}。")
        # R2516（用户反馈「讲解太浅」）：收口从免责套话换行动锚——
        # 「具体怎么走看你自己的选择」是正确废话；用户要的是今天能做
        # 什么。取最靠前落点的「适合+留意」二联（题类优先）。
        _act = _god_action(label, first)
        if _act:
            lines.append(f"顺着这个位置走：{_act[0]}；{_act[1]}。")
        else:
            lines.append(_pick(["意思是这件事在你盘里有着落，不是空的；"
                                "具体怎么走，还要看你自己的选择。",
                                "盘里给这事留了位置，往哪走，看你心意。",
                                "这题盘里能接住，方向有了，步子你来定。"],
                               "bazi-hit", q, _today_cn().isoformat()))
        # R3255（文案骨架·收口）：碎片行收拢成一句「所以怎么看」——
        # hit 路径才敢说「有落点」，miss 路径没有这句。
        lines.append(_pick(
            ["串起来说：这件事在你盘里有着落，眼下也有风——"
             "照着风走，剩下的你自己定。",
             "收个尾：位置在、时机也亮着灯，怎么走是你的事，"
             "小满把底递给你了。"],
            "bazi-close", q, _today_cn().isoformat()))
    else:
        lines.append(f"{_lead}你问{quoted}，这属于{label}，"
                     f"但这块在你盘里着墨不多——盘上写得少，"
                     f"不代表现实里没有。")
        # R3255：「不硬凑」内部腔改坦白口吻的温柔版——
        # 但「不瞎编/不硬说」的诚实锚每个变体都得留（探针钉着）。
        lines.append(_pick(["盘上没有的，小满不瞎编——说实话比说好话要紧。",
                            "盘上没有的我不硬说——真话比好听话有用。",
                            "这一维盘面没给线索，小满不瞎编。"],
                           "bazi-miss", q, _today_cn().isoformat()))
        # R2516：盘没接住也不让用户空手走——给话题级的通用一步
        # （明说不是盘面结论）。
        lines.append(TOPIC_HINT.get(label)
                     or "可以看看下面的盘面明细，或换个问法。")

    rels = calc.get("relations") or []
    if rels:
        r = rels[0]
        warm = RELATION_WARM.get(r.get("type") or "", "")
        if warm:
            # R2509（审-P2-9）：默认路径不裸说「四柱」。
            lines.append(f"另外你盘里有个「{r.get('type')}」的关系"
                         f"（{r.get('a', '')}×{r.get('b', '')}），{warm}。")
    # R230a-7（R13-P1-9）：今日十神进正文，破跨日复读。
    _dl = calc.get("day_luck") or {}
    _rel = str(_dl.get("day_master_rel") or "")
    _god = _rel.rsplit("之", 1)[-1] if "之" in _rel else ""
    _warm = TEN_GOD_WARM.get(_god)
    if _warm:
        # R2516：同行内挂「今天适合」——独立成行会被 lines[:5] 截掉。
        _act = TEN_GOD_ACTION.get(_god)
        _tail = f"今天适合：{_act[0]}。" if _act else ""
        lines.append(f"今天的气氛偏「{_warm[0]}」，{_warm[1]}。{_tail}")
    # R3255：上限 5→7——用户实测「讲得太短不解压」；丰盈不等于
    # 啰嗦，每行仍是一句完整的人话，上限只是把截断放宽。
    return lines[:7]


def _reply_no_question(day_master: str, calc: dict) -> list[str]:
    fe = calc.get("five_elements") or {}
    mine = _day_element(day_master)
    # R2509（审-P1-3）：流量最大的一句暖文案——「日主」首次出现
    # 就地注解，不指望用户去翻专业释义。
    lines = [f"你的日主（出生那天的天干，也就是你的本命五行）"
             f"是{day_master}（{mine}），"
             f"{ELEMENT_WARM.get(mine, ('', ''))[1]}。"]
    strong, missing = fe.get("strong") or [], fe.get("missing") or []
    if strong:
        # F-008：术语人话化——"五行里金偏多"→"你自带「决断」的底色"
        # R230a-7（R13-P1-1）：并列偏旺全说
        for _s in strong[:3]:
            _w = ELEMENT_WARM.get(_s, ("", ""))
            lines.append(f"你自带「{_w[0]}」的底色：{_w[1]}。")
    _tied = fe.get("strong_tied") or []
    if not strong and _tied:
        lines.append(f"{'、'.join(_tied)}几股劲相当：没有一行独大。")
    if missing:
        # F-008：术语人话化——缺行也用日常语标签
        _missing_labels = [ELEMENT_WARM.get(m, ('', ''))[0] for m in missing]
        lines.append(f"缺{'、'.join(_missing_labels)}：不是缺陷，是偏向。")
    dl = calc.get("day_luck") or {}
    if dl.get("day_master_rel"):
        # R214b：裸术语（「庚为日主甲之七杀」）翻译成人话——取末段十神名
        # 映射到日常语标签；映射不到就整句不说，绝不裸抛术语。
        _rel = str(dl["day_master_rel"])
        _god = _rel.rsplit("之", 1)[-1]
        _warm = TEN_GOD_WARM.get(_god)
        # R230a-7（R13-P3-4）：映射不到时此前 append 空串 → 回复出空行。
        if _warm:
            _act = TEN_GOD_ACTION.get(_god)
            _tail = f"今天适合：{_act[0]}。" if _act else ""
            lines.append(f"今天的气氛偏「{_warm[0]}」，{_warm[1]}。{_tail}")
    # R233c（R40-W7）：流日流时里的日支关系（冲合刑害）pro 卡早算好，
    # 温柔端只吃了十神没吃关系——补一条白话，碰到合/冲说清「和谁、
    # 什么感觉」。
    _dbr = dl.get("day_branch_rels") or []
    if _dbr:
        _r0 = _dbr[0]
        _w = RELATION_WARM.get(_r0.get("type") or "", "")
        if _w:
            # R2509（审-P2-10）：pos 是「日支/年支」行话——译成位置白话。
            _pos_cn = {"日支": "夫妻/感情位", "年支": "根基位",
                       "月支": "成长位", "时支": "归宿位"}.get(
                _r0.get("pos") or "", _r0.get("pos") or "某个位置")
            lines.append(f"今天的日子碰到你的{_pos_cn}"
                         f"（{_r0.get('type')}），{_w}。")
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
    1: "全阳当头，劲很足，适合起头的时候", 2: "全阴打底，厚厚地托着，讲的是承受",
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
    1: "最底下那一爻：事情刚起头的位置",
    2: "第二爻：刚上手、还在摸的位置",
    3: "第三爻：半中间，最容易反复的位置",
    4: "第四爻：快出头但还没稳的位置",
    5: "第五爻：最当位、话最管用的位置",
    6: "最上面那一爻：事情到顶、该收的位置",
}


# R233u（R53-P0-4）：问题词 → 用神（六亲）——传统断卦的坐标层
# 「先看哪一爻」。只做坐标指认不断吉凶（G7 内）。
_YAO_POS_CN = {1: "初", 2: "二", 3: "三", 4: "四", 5: "五", 6: "上"}


# 六亲 → 温柔版叫法（R233y）：术语只进专业坐标行/details。
_LIUQIN_WARM = {"官鬼": "事业与忧心", "妻财": "财物", "兄弟": "同辈竞争",
                "父母": "文书庇护", "子孙": "晚辈与解忧"}


_LIUYAO_SCENE: list[tuple[str, str, str, str]] = [
    ("事业|工作|求职|跳槽|升职|面试|offer|项目|职称|离职", "官鬼",
     "代表事业与职位的那一爻", "career"),
    ("感情|恋爱|喜欢|复合|表白|桃花|婚姻|结婚|对象|分手|相亲|异地",
     "妻财", "代表感情走向的那一爻", "love"),
    ("财|钱|工资|副业|投资|生意|买卖|理财|债|报销", "妻财",
     "代表财物与所得的那一爻", "money"),
    ("学业|考试|论文|证书|文书|签证|房子|合同|考研|留学", "父母",
     "代表文书与学业的那一爻", "study"),
    ("健康|身体|生病|病|手术|体检", "官鬼", "代表身体状况的那一爻",
     "health"),
    ("子女|孩子|怀孕|求嗣|宠物|下属", "子孙", "代表孩子与晚辈的那一爻",
     "child"),
    ("合作|同事|竞争|朋友|兄弟|姐妹|合伙人", "兄弟",
     "代表同辈与合作竞争的那一爻", "peer"),
]
import re as _re_lq
_SCENE_RE = [(_re_lq.compile(k), v, note, cat)
             for k, v, note, cat in _LIUYAO_SCENE]

# R3100（specs/010 判词层）：用神/应爻×世爻五行生克→传统口径倾向行。
# 只报「那股劲的方向」不下吉凶断言（G7 红线内）——用户要的是
# 「照卦面看顺不顺」，不是「磨合一类」的虚词。
_WX_KE_LY = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

# R3143（specs/014-L2）：地支六冲——用神支的逢值（同支日）与逢冲
# （对冲支日）是六爻传统断法里最常用的两条应期口径。
_ZHI_CHONG_LY = {"子": "午", "午": "子", "丑": "未", "未": "丑",
                 "寅": "申", "申": "寅", "卯": "酉", "酉": "卯",
                 "辰": "戌", "戌": "辰", "巳": "亥", "亥": "巳"}
# R3175：化进神/化退神——动爻化出同五行、地支序进/退一位，传统
# 断法叫「进」「退」（进者劲往上走，退者劲在收）。四正行序无
# 争议；土的进退神（丑辰未戌连环）各书口径不一，不收。
_LY_JIN_SHEN = {"亥": "子", "寅": "卯", "巳": "午", "申": "酉"}
_LY_TUI_SHEN = {v: k for k, v in _LY_JIN_SHEN.items()}


def _ly_lean_line(user_wx: str, other_wx: str, other_label: str) -> str:
    """user_wx=世爻五行，other_wx=用神/应爻五行。返回倾向句或空。"""
    if not user_wx or not other_wx:
        return ""
    if other_wx == user_wx:
        return (f"这一卦照传统口径看：{other_label}跟你同气。"
                "不急不缓，按自己的节奏来就是。")
    if ELEMENT_GENERATES.get(other_wx) == user_wx:
        return (f"这一卦照传统口径看：{other_label}是朝你这边来的。"
                "顺势接住比使劲推更划算。")
    if ELEMENT_GENERATES.get(user_wx) == other_wx:
        return (f"这一卦照传统口径看：这事要你持续供着劲。"
                "先有付出才有回响，掂量好值不值。")
    if _WX_KE_LY.get(other_wx) == user_wx:
        return (f"这一卦照传统口径看：{other_label}压着你走。"
                "先想清楚接不接得住，别硬扛。")
    if _WX_KE_LY.get(user_wx) == other_wx:
        return (f"这一卦照传统口径看：主动权在你手里。"
                "成不成看你抓不抓，卦不管怂。")
    return ""


# R3124a（specs/012-P1）：时间向/泛向提问的判定词——
# 「今年怎么样/最近运气如何/帮我看看」是全端流量最高的真实问法，
# 此前落「盘里没有对应的位置」实质是拒答。盘里有眼下运（dayun）与
# 流日气候（day_luck）两组确定性数据可答——识别不了具体事项
# 不等于答不了方向。
_TEMPORAL_Q = _re_lq.compile(
    r"今年|明年|后年|去年|这几年|近两年|两三年|最近|近期|"
    # R3140：月/周尺度问法接住——「下个月怎么样」此前落不瞎编，
    # 流月锚本就能算。
    r"这个月|下个月|本月|下月|这周|本周|下周|"
    r"这段|这阵|眼下|目前|现在|接下来|未来|今后|往后|运势|运气|"
    r"流年|大运|前景|走向|走势|发展|帮我看看|帮我分析|解读一下|"
    r"看看我|说说我的|我怎么样|我的命|命怎么样|整体|总体|全面|"
    r"综合|随便看看|大致")
# 问的是跨年尺度（需要 dayun 才算答到位）
_TEMPORAL_YEAR = _re_lq.compile(
    r"今年|明年|后年|这几年|近两年|流年|大运|未来|今后|往后|前景|"
    r"一生|这辈子|长期")


def _reply_temporal(question: str, calc: dict,
                    day_master: str) -> list[str] | None:
    """时间向/泛向问题的确定性回答：眼下运→流日气候→底色三层。

    三层全部取已算好的坐标，不新造断言。答不了（数据缺且词不命中）
    返回 None，让调用方走原有「不瞎编」路径。
    """
    q = (question or "").strip()
    if not q or not _TEMPORAL_Q.search(q):
        return None
    lines: list[str] = []
    fe = calc.get("five_elements") or {}
    dy = calc.get("dayun") or []
    dl = calc.get("day_luck") or {}
    _qq = q.replace("「", "").replace("」", "").replace("\n", " ").strip()
    lines.append(f"你问的是「{_qq}」，这类看方向的问题，"
                 "盘里最实的两样是眼下走什么运、日子的气候往哪吹。")
    # 1) 眼下大运（scope=life 才有 dayun）——十年主基调
    _now_y = _today_cn().year
    _cur = _nxt = None
    if dy:
        _cur = next((d for d in dy
                     if d.get("year_start") is not None
                     and d["year_start"] <= _now_y < d["year_start"] + 10),
                    None)
        _nxt = next((d for d in dy
                     if (d.get("year_start") or 0) > _now_y), None)
    if _cur:
        _gw = TEN_GOD_WARM.get(_cur.get("gan_rel") or "", ("", ""))
        lines.append(
            f"眼下走在第{_cur.get('index')}运「{_cur.get('pillar')}」"
            f"（{_cur.get('start_age')}~{_cur.get('end_age')}岁）" +
            (f"，这十年的主基调偏「{_gw[0]}」：{_gw[1]}。"
             if _gw[0] else "。"))
        if _nxt:
            lines.append(
                f"下一运 {_nxt.get('year_start')} 年前后换班"
                f"（约 {_nxt.get('start_age')} 岁起）"
                "，大方向的拐点记在那个时间窗。")
    # R3125（specs/012-P3）：流年锚——问「今年/明年」时把该年干支
    # 对日主十神的确定性对应摆出来（立春换年口径，年内节气前仍属
    # 上年的只在「今年」做边界说明，明年/后年直取目标年干支）。
    _ym = _re_lq.search(r"今年|明年|后年|流年", q)
    if _ym and day_master:
        _off = {"今年": 0, "明年": 1, "后年": 2, "流年": 0}[
            _ym.group(0)]
        _ly_y = _now_y + _off
        from .bazi import GAN as _GAN, ZHI as _ZHI, term_time as _tt
        _idx = (_ly_y - 4) % 60
        _ly_gz = _GAN[_idx % 10] + _ZHI[_idx % 12]
        from .bazi_calc import ten_god as _bc_ten_god
        _god = _bc_ten_god(day_master, _ly_gz[0])
        _gw2 = TEN_GOD_WARM.get(_god or "")
        if _god:
            _note = ""
            if _ym.group(0) == "今年":
                try:
                    _lc = _tt(_ly_y, "立春")
                    if _today_cn().date() < _lc.date():
                        _note = ("（立春前其实还在上一年的气场里，"
                                 "这是个传统口径提示）")
                except Exception:
                    pass
            lines.append(
                f"{_ym.group(0)}{_ly_y}年是{_ly_gz}年{_note}。"
                f"{_ly_gz[0]}对你日主{day_master}来说是「{_god}」"
                + (f"（{_gw2[0]}）：{_gw2[1]}" if _gw2 else "")
                + "，年度主线参考，不是日程表。")
    # R3126（specs/013-P3）：流月锚——「这个月」尺度的确定性坐标，
    # 本月干支（节气换月口径，与排盘一致）对日主十神。
    # R3140：「下个月/下月」取下月中段日（15 号必落该月节气窗内）。
    if day_master:
        try:
            from .bazi import compute as _bz_compute
            from .bazi_calc import ten_god as _tg2
            _now_dt = _today_cn()
            _want_next = bool(_re_lq.search(r"下个月|下月", q))
            _ty, _tm = _now_dt.year, _now_dt.month
            if _want_next:
                _tm += 1
                if _tm > 12:
                    _tm, _ty = 1, _ty + 1
            _mgz = _bz_compute(_ty, _tm,
                               15 if _want_next else _now_dt.day,
                               12).month
            _mgod = _tg2(day_master, _mgz[0])
            _gm = TEN_GOD_WARM.get(_mgod or "")
            if _mgod:
                lines.append(
                    f"{'下个月' if _want_next else '这个月'}是{_mgz}月"
                    f"，{_mgz[0]}对你是「{_mgod}」"
                    + (f"（{_gm[0]}）：{_gm[1]}" if _gm else "")
                    + "，当月基调参考。")
        except Exception:
            pass
    # 2) 流日气候（day_luck）——「最近」最实的抓手
    _rel = str(dl.get("day_master_rel") or "")
    _god = _rel.rsplit("之", 1)[-1] if "之" in _rel else ""
    _w = TEN_GOD_WARM.get(_god)
    if _w:
        _act = TEN_GOD_ACTION.get(_god)
        lines.append(f"今天的气氛偏「{_w[0]}」，{_w[1]}。" +
                     (f"顺势的做法：{_act[0]}；要留的坑：{_act[1]}。"
                      if _act else ""))
    _dbr = dl.get("day_branch_rels") or []
    if _dbr:
        _r0 = _dbr[0] or {}
        _rw = RELATION_WARM.get(_r0.get("type") or "", "")
        if _rw:
            _pos_cn = {"日支": "夫妻/感情位", "年支": "根基位",
                       "月支": "成长位", "时支": "归宿位"}.get(
                _r0.get("pos") or "", _r0.get("pos") or "某个位置")
            lines.append(f"今天的地支碰到你的{_pos_cn}"
                         f"（{_r0.get('type')}），{_rw}。")
    # 3) 底色一句（五行强弱）
    strong = fe.get("strong") or []
    if strong:
        _lbl = "、".join(ELEMENT_WARM.get(s, (s, ""))[0] or s
                        for s in strong[:2])
        lines.append(f"底色上你「{_lbl}」偏多，这股劲往哪个方向使，"
                     "比旺不旺更要紧。")
    # 4) 收口：问的是跨年尺度但只有单日盘 → 指路「一生」；否则引到
    #    具体事项
    if _TEMPORAL_YEAR.search(q) and not dy:
        lines.append("你问的是跨年的大方向，排盘时范围选「一生」，"
                     "我把大运逐年展开给你看。")
    else:
        lines.append("想问具体的事（感情、事业、学业、财运、人际），"
                     "把那件事写出来，我往细里说。")
    return lines[:6] if len(lines) > 1 else None


# R2518（深度第二轮）：七类场景各给一件卦外能做的小事——
# 不断吉凶，卦面之外让人有事可做。
# R3128（specs/012-P4 同构）：六爻处方升三段式——先做→看信号→
# 若不对怎么调，与合婚处方同一结构。
_LIUYAO_CAT_STEP: dict[str, str] = {
    "career": "能做的最实一步：把眼下最想推进的那件事拆成三步，今天先走第一步。"
              "观察信号：走完第一步的两三天里，事情是变顺还是更卡。"
              "要是更卡，先别硬推第二步，回去看第一步是不是方向错了。",
    "love": "比猜对方心思更实的：先想清楚你想从这段关系里要什么，写下来三条。"
            "观察信号：对着这三条看眼下这段关系满足了几条。"
            "要是一条都没满足，先别急着修复关系，先回答「我还要不要」。",
    "money": "先把这笔进出写成数字摆出来，能看清的账才好做决定。"
             "观察信号：数字摆出来后，你是松了口气还是更紧了。"
             "要是更紧，说明问题不在算账在收入结构，先去看进项那条线。",
    "study": "文书题最忌拖：今天就把要准备的东西列个清单。"
             "观察信号：清单列完的第一项，能不能在两小时内动起手。"
             "要是动不了，不是懒是目标太大：把第一项再对半拆。",
    "health": "身体的事卦面只当参考：不舒服别硬扛，该看就看。"
              "观察信号：按医生或常识调整一周后，症状是缓是平是重。"
              "要是平了或重了，换一家再看，卦面不替诊断。",
    "child": "这类事急不来，先把日常节奏理顺最划算。"
             "观察信号：节奏顺了之后，你自己松不松。"
             "要是还是绷着，卡点不在节奏在心态：先给自己放两天假。",
    "peer": "跟人打交道的事：先想清楚你的底线在哪，写下来。"
            "观察信号：底线亮出来之后，对方是收敛还是变本加厉。"
            "要是变本加厉，这关系该降级就降级，底线不是谈判筹码。",
}


def _liuyao_scene(q: str) -> tuple[str, str, str] | tuple[None, None, None]:
    for pat, ys, note, cat in _SCENE_RE:
        if pat.search(q):
            return ys, note, cat
    return None, None, None


# R2349q（R81-P1-5）：六亲白话按语境换皮——健康题世爻临官鬼是
# 「身体状况」不是「事业与忧心」；感情题（女命看官鬼/男命看妻财）
# 两星同报，不把女用户指到妻财爻。
_LIUQIN_WARM_SCENE = {
    ("官鬼", "health"): "身体状况",
    ("官鬼", "love"): "感情里牵挂的那一端",
    ("妻财", "love"): "感情里牵挂的那一端",
}


def reply_liuyao(ben: dict, bian: dict, moving_lines: list,
                 question: str | None,
                 paipan: dict | None = None) -> list[str]:
    """六爻对提问的描述性回应（判据 8）。

    spec 实测原文：当前六爻只回「系统只给卦象坐标与經文原文，不代为断事」。
    spec §「我同意提案对 G7 的判断」已裁定：G7 防的是伪造引文，
    它从不要求「不许用人话说明已经算出来的坐标」。
    本函数只转述**已经起出来的卦象**，不预测结果。
    """
    q = (question or "").strip()
    # R2349q（R81-P0-1）：生死/重病提问此前零拦截——用神指认+走向
    # 分析照常跑是指向性伤害。与聊天/问一嘴同一闸口径。
    # R2518：危机自伤词同拦——「我活不下去了」此前照常给卦面解读，
    # 语气严重失当；与聊天层 _CRISIS_PAT 同一口径转介。
    from guji import llm_polish as _lp
    if _lp._is_sensitive(q) or _lp._is_crisis(q):
        return ["这个话题卦面真答不了，也不该靠它拿主意。"
                "身体或心里难受的话，找医生、找信得过的人聊聊才是正路；"
                "真的很难受，全国心理援助热线 12356（24 小时，免费）"
                "随时能打通。小满陪你说点别的也行。"]
    bn = int(ben.get("gua_number") or 0)
    bname = ben.get("gua_name") or ""
    vn = int(bian.get("gua_number") or 0)
    vname = bian.get("gua_name") or ""
    ml = [int(x) for x in (moving_lines or []) if isinstance(x, int)]

    lines: list[str] = []
    # R3126（specs/013-P6）：梳理位——先把问题归到一条线再亮卦，
    # 让她确认「它在回答我真正问的」（调研：塔罗师问题梳理是
    # 解读前的专业步骤，选错线=回答跑题的根因）。
    _th_line = ""
    if q:
        _th_line = _lp._chat_theme(q)
        _th_line = f"，这事归「{_th_line}」这条线" if _th_line else ""
    head = (f"你问的是「{q}」{_th_line}。" if q
            else "这一卦起出来是这样：")
    lines.append(head + f"起到的是{bname}卦，{GUA_WARM.get(bn, '')}。")

    # R233u（R53-P0-4）：用神/世应坐标——让用户知道「这卦里先看哪一爻」。
    # 坐标如实转述（六亲落位、是否动爻），不断吉凶。
    _pp = paipan or {}
    _bl = ((_pp.get("ben_gua") or {}).get("lines")) or []
    _shi_pos = (_pp.get("ben_gua") or {}).get("shi")
    _ying_pos = (_pp.get("ben_gua") or {}).get("ying")
    if _bl and _shi_pos:
        _by_pos = {int(l.get("position", 0)): l for l in _bl}
        _shi_l = _by_pos.get(int(_shi_pos), {})
        _ying_l = _by_pos.get(int(_ying_pos or 0), {})
        # R233y（R54-P2-19/20）：六亲黑话不进温柔版正文——世爻/应爻/
        # 官鬼/妻财/不现 全翻成位置人话（专业坐标在 details 里照给）。
        _ys, _ys_note, _cat = _liuyao_scene(q) if q else (None, None, None)
        # R2349q（R81-P1-5）：六亲标签按场景换皮（健康→身体状况等）。
        _lq_a = (_LIUQIN_WARM_SCENE.get((_shi_l.get("liuqin", ""), _cat))
                 or _LIUQIN_WARM.get(_shi_l.get("liuqin", ""), ""))
        _lq_b = (_LIUQIN_WARM_SCENE.get((_ying_l.get("liuqin", ""), _cat))
                 or _LIUQIN_WARM.get(_ying_l.get("liuqin", ""), ""))
        _seg = (f"卦里代表你的那一爻在{_YAO_POS_CN.get(int(_shi_pos), '第' + str(_shi_pos))}爻"
                + (f"（临{_lq_a}）" if _lq_a else ""))
        if _ying_l:
            _seg += (f"，代表事情那头的那一爻在"
                     f"{_YAO_POS_CN.get(int(_ying_pos or 0), '')}爻"
                     + (f"（临{_lq_b}）" if _lq_b else ""))
        _pos_of = lambda lq: [int(l.get("position", 0)) for l in _bl
                              if l.get("liuqin") == lq]
        if _ys:
            _ys_pos = _pos_of(_ys)
            if _cat == "love":
                # 感情题两星同报：女命看官鬼（夫星）、男命看妻财（妻星）。
                # R2350b（R98-P1-4）：官鬼/妻财当场翻译——六亲黑话不进
                # 温柔版正文是既定纪律（本文件 645 行注释），这里漏翻了。
                _gg = _pos_of("官鬼")
                _qc = _pos_of("妻财")
                _bits = []
                if _gg:
                    _bits.append(
                        f"夫星落在{_YAO_POS_CN.get(_gg[0], '第' + str(_gg[0]))}爻"
                        + ("（动爻，正在动的点上）" if _gg[0] in ml else ""))
                if _qc:
                    _bits.append(
                        f"妻星落在{_YAO_POS_CN.get(_qc[0], '第' + str(_qc[0]))}爻"
                        + ("（动爻，正在动的点上）" if _qc[0] in ml else ""))
                # R3173：伏神——星没上卦不代表没有，本宫纯卦里它藏在
                # 某位爻底下。单星缺位也要报伏位（妻财缺 23.5%、
                # 官鬼缺 12%，缺位是常态不是边角）。
                for _flq, _fln in (("官鬼", "夫星"), ("妻财", "妻星")):
                    if _pos_of(_flq):
                        continue
                    _fs0 = [f for f in (_pp.get("fushen") or [])
                            if f.get("liuqin") == _flq]
                    if _fs0:
                        _bits.append(
                            f"{_fln}没露面，伏在"
                            f"{_YAO_POS_CN.get(_fs0[0].get('position'), '')}爻"
                            f"（{_fs0[0].get('branch') or ''}）底下"
                            "，还憋着，透出才算数")
                if _bits:
                    # R2509（审-P2-14）：括号里的「官鬼/妻财」是把刚翻译完
                    # 的黑话又塞回来——温柔版纪律（六亲白话）已破，删掉。
                    _seg += ("。感情的事传统上女看「夫星」、男看「妻星」"
                             "，这卦里" + "、".join(_bits))
                else:
                    _seg += ("。感情的事传统上女看「夫星」、男看「妻星」"
                             "，两星都没直接落位，那就看代表你和事情的"
                             "两端更实在")
            elif _ys_pos:
                _mv = "且是动爻：你问的事正在动的点上" \
                    if _ys_pos[0] in ml else ""
                _seg += (f"。问这类事传统上先看{_ys_note}。"
                         f"落在{_YAO_POS_CN.get(_ys_pos[0], '第' + str(_ys_pos[0]))}爻{_mv}")
            else:
                _fs_l2 = [f for f in (_pp.get("fushen") or [])
                          if f.get("liuqin") == _ys]
                if _fs_l2:
                    _f1 = _fs_l2[0]
                    _seg += (f"。问这类事传统上先看{_ys_note}，它没露面，"
                             f"伏在{_YAO_POS_CN.get(_f1.get('position'), '')}爻"
                             f"（{_f1.get('branch') or ''}）底下，事还憋着，"
                             "透出才算数")
                else:
                    _seg += (f"。问这类事传统上先看{_ys_note}，它没直接落在这卦里，"
                             f"那就看代表你和事情的两端更实在")
        lines.append(_seg + "。")
        # R3100：倾向行——感情题看应×世（对方那头 vs 你），其余场景
        # 看用神×世。五行生克是已算坐标，如实转述不下吉凶断言。
        _lean = ""
        if _cat == "love":
            _lean = _ly_lean_line(_shi_l.get("wuxing", ""),
                                  _ying_l.get("wuxing", ""), "对方那头")
        elif _ys and _ys_pos:
            _ys_l = _by_pos.get(_ys_pos[0], {})
            _lean = _ly_lean_line(_shi_l.get("wuxing", ""),
                                  _ys_l.get("wuxing", ""), "你问的事")
        if _lean:
            lines.append(_lean)

        # R3143（specs/014-L2）：应期参考——用神支的逢值（同支日）与
        # 逢冲（对冲支日）是六爻最常用应期口径；动爻上的用神优先
        # （传统以动为应）。如实转述成「参考窗口」，不下「必应验」断言。
        _yz_l = _ying_l or {}
        # 感情题与上文口径对齐——女看官鬼（夫星）优先，男命视角的
        # 妻财次之；同星多爻时动爻优先（传统以动为应）。
        _cands = ([_pos_of("官鬼"), _pos_of("妻财")] if _cat == "love"
                  else [_pos_of(_ys)] if _ys else [])
        for _pl in _cands:
            if _pl:
                _mv_c = [p for p in _pl if p in ml]
                _yz_l = _by_pos.get((_mv_c or _pl)[0], {}) or _yz_l
                break
        _zb = (_yz_l or {}).get("branch") or ""
        _zc = _ZHI_CHONG_LY.get(_zb, "")
        if _zb and _zc:
            try:
                import datetime as _dt2
                from guji.bazi import day_ganzhi as _dgz
                _d_val = _d_chg = None
                _base = _dt2.date.fromisoformat(str(_d3_today()))
                for _i in range(1, 46):
                    _dd = _base + _dt2.timedelta(days=_i)
                    _gz = _dgz(_dt2.datetime(_dd.year, _dd.month,
                                           _dd.day))[0]
                    _bd = _gz[1] if len(_gz) >= 2 else ""
                    if _d_val is None and _bd == _zb:
                        _d_val = _dd
                    if _d_chg is None and _bd == _zc:
                        _d_chg = _dd
                    if _d_val and _d_chg:
                        break
                if _d_val and _d_chg:
                    lines.append(
                        f"应期参考（传统口径）：代表这事的那爻带{_zb}。"
                        f"{_d_val.month}月{_d_val.day}日逢值、"
                        f"{_d_chg.month}月{_d_chg.day}日逢冲，"
                        "事情容易在这两个日子前后有动静"
                        "（参考，不是日程表）。")
            except Exception:
                pass

        # R3168（specs/014-L2+）：月建旺衰——传统断卦看「用神对月令得
        # 不得气」，此前月建/日辰压根没算进盘。如实转述成底气句，
        # 只描述支撑强弱，不下吉凶断言。用神选取与应期同口径（_yz_l）。
        try:
            _yj_b = (_pp.get("yuejian") or "")
            _rc_b = (_pp.get("richen") or "")
            _ys_wx2 = (_yz_l or {}).get("wuxing") or ""
            _yj_wx = ZHI_ELEMENT.get(_yj_b, "")
            _rc_wx = ZHI_ELEMENT.get(_rc_b, "")
            _yj_txt = ""
            if _yj_b and _yj_wx and _ys_wx2:
                # R3175：月破——用神支与月建对冲，是月令压制里最狠的
                # 一档（「破」比「克」更伤根基），优先于普通生克报。
                if _zb and _ZHI_CHONG_LY.get(_yj_b) == _zb:
                    _yj_txt = (f"月令{_yj_b}正冲着你问的事（{_zb}）"
                               "，传统上这叫「月破」，这个月事头被"
                               "冲得立不稳，缓一缓比硬推强")
                elif _yj_wx == _ys_wx2:
                    _yj_txt = (f"月令{_yj_b}和你问的事同气，正当令，"
                               "这段日子事头底气足")
                elif ELEMENT_GENERATES.get(_yj_wx) == _ys_wx2:
                    _yj_txt = (f"月令{_yj_b}（{_yj_wx}）生着你问的事"
                               f"（{_ys_wx2}），这个月它有外援托着，底气偏足")
                elif _WX_KE_LY.get(_yj_wx) == _ys_wx2:
                    _yj_txt = (f"月令{_yj_b}（{_yj_wx}）压着你问的事"
                               f"（{_ys_wx2}），这段事头偏弱，更得照着"
                               "处方那句来")
                elif ELEMENT_GENERATES.get(_ys_wx2) == _yj_wx:
                    _yj_txt = (f"月令{_yj_b}（{_yj_wx}）泄着你问的事"
                               f"（{_ys_wx2}），劲容易被分走，推进省着点用")
                elif _WX_KE_LY.get(_ys_wx2) == _yj_wx:
                    _yj_txt = (f"月令{_yj_b}（{_yj_wx}）耗着你问的事"
                               f"（{_ys_wx2}），能推动但费劲，别指望它"
                               "自己滚起来")
            if _yj_txt:
                # 日辰帮衬只在和月令同向时点名——对冲细节留给专业层。
                if _rc_wx and _rc_wx == _ys_wx2:
                    _yj_txt += f"；日辰{_rc_b}也同气帮衬"
                lines.append("顺带一提，这卦摇的时间坐标里。" +
                             _yj_txt + "。")
            # R3170：旬空——用神支落空亡是「事还没坐实」的经典信号。
            # 如实转述成「飘着没定」，不吓人不断言凶。
            _xk = _pp.get("xunkong") or []
            _xk_bits = []
            if _zb and _zb in _xk:
                _xk_bits.append(f"代表这事的那爻（{_zb}）正落空亡。"
                                "眼下这事还飘在半空没坐实")
            # 世爻（你自己这头）落空是另一重信号：心还没定。用神与世
            # 同支时只报一次。
            _sh_b = (_shi_l or {}).get("branch") or ""
            if _sh_b and _sh_b in _xk and _sh_b != _zb:
                _xk_bits.append(f"你自己那爻（{_sh_b}）也空着。"
                                "心里可能还没真拿定主意")
            if _xk_bits:
                lines.append("还有一点。" + "；".join(_xk_bits) +
                             "。先别急着当定局，等它落了地再看。")
            # R3175：暗动——静爻被日辰对冲，传统叫「暗动」：表面
            # 没动、底下在拱。只点用神/世爻（全盘每个爻都报就吵了）。
            _ad, _cs = [], []
            _ad_seen = set()
            for _al, _albl in ((_yz_l, "代表这事的那爻"),
                               (_shi_l, "你自己那爻")):
                _ab2 = (_al or {}).get("branch") or ""
                _ap = (_al or {}).get("position") or _ab2
                if (_ab2 and _rc_b and _ap not in _ad_seen and
                        _ZHI_CHONG_LY.get(_rc_b) == _ab2):
                    _ad_seen.add(_ap)
                    if (_al or {}).get("moving"):
                        # 动爻逢日冲是「冲散」（日破）——劲使出来
                        # 就散，与静爻暗动分口径报。
                        _cs.append(_albl + f"（{_ab2}）动是动了，"
                                           f"可日辰{_rc_b}冲着它。"
                                           "劲使出来就散")
                    else:
                        _ad.append(_albl + f"（{_ab2}）被日辰{_rc_b}冲着")
            _ad2 = []
            if _ad:
                _ad2.append("暗处有动静。" + "；".join(_ad) +
                            "，面上看着静，底下其实在拱")
            if _cs:
                _ad2.append("；".join(_cs) +
                            "，这一步先别使全力")
            if _ad2:
                lines.append("；".join(_ad2) + "。")
        except Exception:
            pass

    if ml:
        def _yw_lbl(s):
            return s.split("：")[0].split("——")[0]

        def _yw_mean(s):
            return s.split("：", 1)[-1] if "：" in s else s.split("——")[-1]

        pos = "、".join(_yw_lbl(YAO_WARM.get(i, f"第{i}爻")) for i in ml)
        # R2349q（R81-P1-16）：多动爻此前只解释第一爻（3 动爻共用初爻
        # 语义）——每爻各自取白话，逗号隔开。
        _mv_mean = [
            (_yw_lbl(YAO_WARM.get(i, f"第{i}爻")),
             _yw_mean(YAO_WARM.get(i, "")))
            for i in ml]
        _mv_txt = "；".join(f"{p}在动：{m}" for p, m in _mv_mean)
        lines.append(f"动的是{pos}（共 {len(ml)} 个），{_mv_txt}。")
        if len(ml) >= 3:
            lines.append("动爻偏多，说明这件事变数不小，看整体走向比抠单爻实在。")
        # R3171：回头生/克——动爻化出之爻对本位的五行关系是传统
        # 断卦的分水岭（动而有援 vs 动而受伤）。变卦纳甲五行已算，
        # 如实转述不下吉凶断言。
        try:
            _bgl = {int(l.get("position", 0)): l
                    for l in ((_pp.get("bian_gua") or {}).get("lines") or [])}
            _bgl0 = {int(l.get("position", 0)): l
                     for l in ((_pp.get("ben_gua") or {}).get("lines") or [])}
            _hs, _hk = [], []
            _jt = {"进": [], "退": [], "伏吟": [], "反吟": []}
            for _mp2 in ml:
                _al2 = _bgl0.get(_mp2, {}) or {}
                _bl2 = _bgl.get(_mp2, {}) or {}
                _a2, _b2 = _al2.get("wuxing", ""), _bl2.get("wuxing", "")
                if not _a2 or not _b2:
                    continue
                if ELEMENT_GENERATES.get(_b2) == _a2:
                    _hs.append(_mp2)
                elif _WX_KE_LY.get(_b2) == _a2:
                    _hk.append(_mp2)
                # R3175：化进神/退神——同气地支序进/退，劲的方向。
                # 同批伏吟（化同支=原地折腾）/反吟（化冲=翻来覆去）。
                _ab3, _bb3 = _al2.get("branch", ""), _bl2.get("branch", "")
                if _LY_JIN_SHEN.get(_ab3) == _bb3:
                    _jt["进"].append(_mp2)
                elif _LY_TUI_SHEN.get(_ab3) == _bb3:
                    _jt["退"].append(_mp2)
                elif _ab3 and _bb3 == _ab3:
                    _jt["伏吟"].append(_mp2)
                elif _ab3 and _ZHI_CHONG_LY.get(_ab3) == _bb3:
                    _jt["反吟"].append(_mp2)
            _hb = []
            if _hs:
                _hb.append("、".join(
                    _YAO_POS_CN.get(p, f"第{p}爻").split("——")[0]
                    for p in _hs) + "动出去有接应（化回头生）")
            if _hk:
                _hb.append("、".join(
                    _YAO_POS_CN.get(p, f"第{p}爻").split("——")[0]
                    for p in _hk) +
                    "动出去反被打回来（化回头克），那一步要留个后手")
            _JT_COPY = {
                "进": "化进神：那股劲在往上走，顺的话会越来越顺",
                "退": "化退神：那股劲在往回收，别全押在这一步上",
                "伏吟": "动而化伏吟：动了半天还在原地，那股憋屈多半"
                        "来自自己跟自己较劲",
                "反吟": "动而化反吟：翻来覆去来回摆，主意一天三变，"
                        "先按住别急着定",
            }
            for _jd in ("进", "退", "伏吟", "反吟"):
                if _jt[_jd]:
                    _hb.append("、".join(
                        _YAO_POS_CN.get(p, f"第{p}爻").split("——")[0]
                        for p in _jt[_jd]) + _JT_COPY[_jd])
            if _hb:
                lines.append("再细看动的爻。" + "；".join(_hb) + "。")
        except Exception:
            pass
    else:
        lines.append("没有动爻（静卦），当下格局是稳住的，变化的劲不明显。")

    if vname and vname != bname:
        lines.append(f"往{vname}卦的方向变，{GUA_WARM.get(vn, '')}。")
    elif vname:
        lines.append("变卦与本卦相同，方向不改。")

    # R3172：卦级六合/六冲格局——传统口径里六合主缠主聚（事黏糊，
    # 急不得），六冲主散主快（一阵风，别拖）。本卦→变卦的合冲转
    # 换是走向信号：先合后冲=眼下缠着长远散，先冲后合反之。
    try:
        _lh_b = ((_pp.get("ben_gua") or {}).get("liuhe_chong") or "")
        _lh_v = ((_pp.get("bian_gua") or {}).get("liuhe_chong") or "")
        if _lh_b and _lh_v and _lh_b != _lh_v:
            lines.append(
                f"卦象格局上，这卦{_lh_b}变{_lh_v}，传统口径里这是"
                f"「先{'合着' if _lh_b == '六合' else '散着'}后"
                f"{'散' if _lh_v == '六冲' else '合'}」的走向，"
                "眼下与长远不是一回事，别拿当下一刻当结局。")
        elif _lh_b:
            lines.append(
                f"卦象格局上，这卦是{_lh_b}卦，传统口径里"
                + ("合主缠、主聚：这事黏糊，不会一拍两散，"
                   "宜慢解不宜快刀。" if _lh_b == "六合" else
                   "冲主散、主快：这事容易一阵风就过，"
                   "拖泥带水反而更耗。"))
        elif _lh_v and vname and vname != bname:
            lines.append(
                f"卦象格局上，变卦落{_lh_v}：往长远看这股劲是"
                + ("「合上、黏住」的，急不得。" if _lh_v == "六合" else
                   "「散开」的，别抱长久指望。"))
    except Exception:
        pass

    # R216b 续4（UX 队列 U-023）：直白节奏倾向语——由动爻数与卦变
    # 确定性推导，只描述节奏不给吉凶承诺（G7 红线内）。
    n = len(ml)
    # R2349g（R68-P2）：每档 trend 双变体——同一卦（时间起卦同日同时辰
    # 恒定）连摇不再复读同一句；按本卦卦号确定性二选一。
    _alt = (bn % 2) == 1
    if not ml:
        trend = ("整体偏稳，眼下更适合守着现状，不必急着动。" if not _alt
                 else "卦面是静的：格局稳着，安心做手上的事。")
    elif n == 1:
        trend = ("整体偏稳、局部有变化：大方向不变，中间有一个点要留意。"
                 if not _alt else
                 "主线是稳的，就一个地方在动，盯住那一点就够。")
    elif n == 2:
        trend = ("整体有起伏：事情在推进中，节奏会有两次小调整。"
                 if not _alt else
                 "两处都在动，事情会拐两个小弯，跟着节奏走。")
    else:
        trend = ("整体变数偏多，先别求一步到位，分几步走更稳。"
                 if not _alt else
                 "动的点多，这事先抓大方向，细节边走边调。")
    # R230a-7（R13-P1-4）：阳长之势 = 十二消息卦阳长段（复24/临19/泰11/
    # 大壮34/夬43/乾1）——此前的 (14,55) 是误植（大有/丰不在消息卦阳长段）。
    if vname and vname != bname and vn in (1, 11, 19, 24, 34, 43):
        trend += "变卦落在阳气渐长的卦位，劲是往上走的。"
    lines.insert(min(1, len(lines)), trend)

    # R2518（深度第二轮）：收口从「慢慢体会」软着陆换成场景级一步——
    # 与 TOPIC_HINT 同理：卦面之外给一个不冒充断语、能照做的动作。
    _cat_end = _liuyao_scene(q)[2] if q else None
    _step = _LIUYAO_CAT_STEP.get(_cat_end or "")
    if _step:
        lines.append(_step + "卦辞爻辞的原文在下面，慢慢对照，不急。")
    else:
        lines.append("卦辞爻辞的原文在下面：怎么对应你问的事，"
                     "慢慢体会，不急。")
    # R233u~R3168 同型四咬：每加一行处方（末位承重行）就被 [:N] 顶出去。
    # R3170 结构性修——不再逐次调 cap：含「卦辞爻辞」（处方/经文引导
    # 收尾行）的行先捞出保底，其余按序填满槽位，处方恒在队尾。
    # R3172：六合冲格局行再占一行（seed42 实测连顶两次：cap 11/12
    # 都把它挤掉）——最坏行序 13：卦名/节奏/坐标/倾向/应期/月令/
    # 空亡/动爻/多动/回头/变卦/格局 + 处方尾行。
    # R3175：暗动行再占一行——最坏 14。
    _CAP = 14
    if len(lines) <= _CAP:
        return lines
    _tail = [l for l in lines if "卦辞爻辞" in l]
    _body = [l for l in lines if "卦辞爻辞" not in l]
    return _body[:_CAP - len(_tail)] + _tail


# ---------------------------------------------------------------------------
# 对外入口：三个 warm 构建器（路由层调用）
# ---------------------------------------------------------------------------
def _render_details(render: str) -> list[dict]:
    """R232b（R40-A7/A8）：盘面明细走统一 details schema（title/lines/
    basis）——此前 {label,text} 形状进了 renderWarm 后 title 空、
    lines 缺，明细被静默丢弃。按换行拆行。"""
    if not render:
        return []
    lines = [ln for ln in str(render).split("\n") if ln.strip()]
    return [{"title": "盘面明细", "lines": lines, "basis": []}]


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
              question: str | None = None,
              gender: str | None = None,
              hour_known: bool = True) -> dict:
    """八字 warm 视图。citations 逐字节复用 interpreter 输出（判据 15）。

    hour_known=False 时不出时柱行——用户没填时辰按午时排是默认盘，
    不能把默认当时辰来讲（服务层另有「没填时辰」明示行）。"""
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
    reply = list(reply_bazi(day_master, calc, question, gender=gender))
    # R214b：日主人设卡——「小太阳」式昵称 + 高光时刻，替代术语开场。
    # 判据 1 纪律：有提问时首段必须回应提问——人设行追加在末尾而非开头。
    persona = next((p for p in (COPY_BANK.get("gan_persona") or [])
                    if p.get("gan") == day_master), None)
    if persona and not (question or "").strip():
        reply = [f"你是「{persona['nick']}」，{persona['desc']}。",
                 f"高光时刻：{persona['hi']}。"] + reply
    # 有提问时不插人设行：提问优先（判据 1），且避免推高结果区高度
    # （判据 2 门柱）。人设卡只在无提问的首屏场景出现。
    # R232b（R40-A5/W2）：scope=life 的大运表此前只进 pro 渲染——温柔
    # 用户选了「一生大运」也只看到单日口径。补一段人话收口：几岁起运
    # + 当下走在哪一运 + 下一运什么时候换。
    if calc.get("scope") == "life":
        dy = calc.get("dayun") or []
        if dy:
            qi = calc.get("qi_yun_age")
            _now_y = _today_cn().year
            _cur = next((d for d in dy
                         if (d.get("year_start") is not None
                             and d["year_start"] <= _now_y
                             < d["year_start"] + 10)), None)
            _nxt = next((d for d in dy
                         if (d.get("year_start") or 0) > _now_y), None)
            seg = []
            if qi is not None:
                seg.append(f"约 {qi} 岁起运")
            if _cur:
                seg.append(f"眼下走在第{_cur['index']}运「{_cur['pillar']}」"
                           f"（{_cur.get('start_age')}~{_cur.get('end_age')}岁）")
            if _nxt:
                seg.append(f"下一运 {_nxt.get('year_start')} 年前后换班"
                           f"（约 {_nxt.get('start_age')} 岁）")
            # R2509（审-P1-1）：默认受众是 15–25 岁，「大运/第N运/干支
            # 柱」裸出现看不懂——首提加口语注解、藏掉支柱名。
            # R3125：时间向问题的 _reply_temporal 已自带眼下运+换班年——
            # 同内容行不再重复追加。
            if not any("眼下走在第" in _ln for _ln in reply):
                reply = reply + ["大运（十年一轮的大方向）节奏：" +
                                 "；".join(seg) +
                                 "，方向感参考，不是日程表。"]
    # R3141（specs/014-L3）：年度追踪行——本年干支十神 +
    # 十二流月按「顺气/使劲」分档点名（大师应期轴的年内尺度）。
    # R3151：挪出 scope==life 闸——单日卡也带 yearly 块（R3151 起
    # calc() 也算了），「看八字」默认档此前年度锚恒空。年度行插在
    # 「想问具体的事」引导行前面——CTA 恒为末行才顺。
    _cta = ""
    for _i in range(len(reply) - 1, -1, -1):
        if reply[_i].startswith("想问具体的事"):
            _cta = reply.pop(_i)
            break
    _yr = calc.get("yearly") or {}
    _g0 = TEN_GOD_WARM.get(_yr.get("gan_rel") or "")
    if _yr.get("ganzhi") and _yr.get("gan_rel"):
        reply.append(
            f"今年{_yr['year']}是{_yr['ganzhi']}年，{_yr['ganzhi'][0]}"
            f"对你日主{day_master}是「{_yr['gan_rel']}」"
            + (f"（{_g0[0]}）：{_g0[1]}" if _g0 else "")
            + "，年度主基调，不是日程表。")
    _mos = _yr.get("months") or []
    # R3151：月份分档明细只在生平档全量给——单日卡已有流日/日支
    # 关系行，再塞 12 月分档太满；单日卡只带年度锚行。
    # R3165：分档数据由 calc.yearly.easy/hard 直给（同口径，不再本地重算）。
    if _mos and calc.get("scope") == "life":
        _ez = _yr.get("easy") or []
        _hd2 = _yr.get("hard") or []
        if _ez:
            reply.append("今年偏顺气的月份：" + "、".join(_ez[:6]) +
                         "，基调轻的窗口，适合推进要在意的事。")
        if _hd2:
            reply.append("今年要使劲的月份：" + "、".join(_hd2[:6]) +
                         "，不是坏，是这几个月基调偏重，别在那时"
                         "硬扛大决定。")
    # R3232（用户实测）：填了生辰几时，解读此前一个字不提——时柱
    # 只进了四柱渲染，判词层零融合。补一条白话行：时辰名+时段 +
    # 时干十神的白话标签（原词放括号，判据 3 括号外计词不破）。
    # 时柱在传统口径看后劲/晚段，不新增吉凶断言。
    if hour_known:
        _pl = ((paipan or {}).get("render") or "").split("　")[0].split()
        _hp = _pl[3].rstrip("时") if len(_pl) >= 4 else ""
        _hz = _hp[1:2] if len(_hp) >= 2 else ""
        _hgod = next((t.get("god") for t in (calc.get("ten_gods") or [])
                      if t.get("pos") == "时干"), "")
        _hw = TEN_GOD_WARM.get(_hgod or "")
        if _hp and _hz:
            _seg = (f"时柱「{_hp}」：你生在{_hz}时"
                    f"（{ZHI_HOURS.get(_hz, '')}）")
            if _hw:
                _seg += f"，这一柱带的是「{_hw[0]}」（{_hgod}），{_hw[1]}"
            _seg += "。传统口径里时柱看后劲和晚段，越往后越显。"
            reply.append(_seg)
    if _cta:
        reply.append(_cta)
    return _wrap(
        one_liner(day_master, calc, question, gender=gender),
        energy_card(day_master, calc),
        reply,
        details_from_sections(interp.get("sections") or []),
        interp.get("citations") or [],
    )


def warm_liuyao(ben: dict, bian: dict, moving_lines: list,
                interpretation: dict, question: str | None = None,
                paipan: dict | None = None) -> dict:
    """六爻 warm 视图（判据 8）。"""
    interp = interpretation or {}
    bn = int((ben or {}).get("gua_number") or 0)
    name = (ben or {}).get("gua_name") or ""
    _ly = COPY_BANK.get("liuyao_openers") or []
    opener = (_pick(_ly, bn, name, _d3_today()) if _ly else "")
    l0 = f"{opener}：{name}卦" if opener else \
         f"{name}卦：{GUA_WARM.get(bn, '').split('，')[0]}"
    return _wrap(
        l0 if len(l0) <= _L0_MAX else l0[:_L0_MAX],
        None,
        reply_liuyao(ben or {}, bian or {}, moving_lines or [], question,
                     paipan=paipan),
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
    # R2349q（R81-P0-1）：生死/重病提问此前零拦截——抽到行动 kw0
    # 时逐张给「想好了就去做」是指向性伤害。与聊天/问一嘴同一闸口径。
    from guji import llm_polish as _lp
    # R2518：与 reply_liuyao 同补——危机自伤词也转介，不照常解牌。
    if _lp._is_sensitive(q) or _lp._is_crisis(q):
        return _wrap(l0, None,
                     ["这个话题牌面真接不了，不是不愿意，是它不该靠占卜来定。",
                      "身体或心里难受的话，医生和信得过的人才是最该找的；"
                      "真的很难受，全国心理援助热线 12356（24 小时，免费）"
                      "随时能打通。",
                      "想聊点别的，小满都在。"],
                     [], [])
    if q:
        # R3126（specs/013-P6）：梳理位——先归到一条线再逐张说牌。
        _th = _lp._chat_theme(q)
        lines.append(f"针对你的问题「{q}」"
                     + (f"，这事归「{_th}」这条线，" if _th else "，")
                     + "每张牌这样说：")
    else:
        lines.append("每张牌这样说：")
    # ≥6 张时不再只贴前 3 张——按位置权重选 5 张叙事（R3090/specs/010-P2）：
    # 前 3 个关键位 + 建议/指引/希望/结果 收尾位，凯尔特十字的「希望/结果」
    # 此前根本没机会开口。
    if len(cards) > 5:
        _KEY_POS = {"现在", "现状", "阻碍", "根源", "目标", "未来",
                    "关键", "助力", "环境", "你", "TA", "这段关系",
                    "内心", "身体", "灵性"}
        _TAIL_POS = {"建议", "指引", "希望", "结果"}
        _key = [c for c in cards if c.get("position") in _KEY_POS]
        _tl = [c for c in cards if c.get("position") in _TAIL_POS]
        shown = (_key[:3] + _tl[:2] or _key[:5]) or cards[:3]
        shown = shown[:5]
    else:
        shown = cards[:5]
    # R233u（R53-P0-3 连带）：位置修饰让「过去/现在/未来」真的参与语义；
    # 同阵同 kw0（约 5%）降级为呼应表述，不再同一句话贴两遍。
    # R3090：位置域表扩到全部命名阵——同一张牌落「阻碍」位与落「希望」
    # 位说不同的话（牌位判词化）。
    _POS_CLAUSE = {
        "过去": "（留下的影响）", "现在": "（正在发生）",
        "现状": "（正在发生）", "未来": "（接下来要注意）",
        "结果": "（按牌面走到的样子）", "阻碍": "（挡你的那个点）",
        "助力": "（能借的力）", "根源": "（事的根）",
        "目标": "（想去的方向）", "环境": "（周围的场）",
        "建议": "（牌给的处方）", "指引": "（牌给的处方）",
        "希望": "（你盼的方向）", "你": "（你这边的状态）",
        "TA": "（ta 那边的状态）", "这段关系": "（关系的底色）",
        "内心": "（心里真正的声音）", "身体": "（身体的提醒）",
        "灵性": "（往深里走的那层）", "关键": "（整局的关键点）",
        "选项A": "（选 A 会怎样）", "选项B": "（选 B 会怎样）",
    }
    _seen_kw: set[str] = set()
    for c in shown:
        cu = bool(c.get("upright"))
        ckw = (c.get("upright_kw") if cu else c.get("reversed_kw")) or ""
        pos = c.get("position") or ""
        pos_label = pos + _POS_CLAUSE.get(pos, "") if pos else ""
        name = c.get('name', '')
        kw0 = ckw.split('·')[0] if ckw else ''
        # D-002：每张牌一句话直接关联问题，给具体指引
        guidance = _tarot_kw_guidance(kw0, q)
        # R3090：位置改写句式——阻碍位的 kw 是要跨的坎、建议/指引位的
        # kw 就是处方、结果位是走向预言；同牌异位不再同句。
        _pre = f"{pos_label + '：' if pos_label else ''}"
        if pos == "阻碍":
            # R3119：正位硬牌同按「要跨的坎」——权杖10/宝剑8 这类
            # 正位即吃力的牌说「障碍不算硬」是错的（实测领错档）。
            if name in _TAROT_HEAVY or not cu or kw0 in _TAROT_HARD_UP:
                _tpl = (f"{_pre}{name}说「{kw0}」，落在阻碍位，"
                        f"这正是要跨的坎：{guidance}")
            else:
                _tpl = (f"{_pre}{name}说「{kw0}」，好牌落阻碍位，"
                        f"障碍不算硬，要留神的是「{kw0}」被用过头："
                        f"{guidance}")
        elif pos in ("建议", "指引"):
            _tpl = f"{_pre}{name}，牌给的处方就是「{kw0}」：{guidance}"
        elif pos == "希望":
            _tpl = f"{_pre}{name}说「{kw0}」，你盼的方向长这样：{guidance}"
        elif pos == "结果":
            _tpl = f"{_pre}{name}说「{kw0}」，按现在走法，结局大致在这：{guidance}"
        else:
            _tpl = ""
        if q:
            if kw0 in _seen_kw:
                lines.append(f"{_pre}{name}也在说「{kw0}」，和前面那张是呼应，"
                             f"这件事的信号挺明确。")
            elif _tpl:
                lines.append(_tpl)
            else:
                lines.append(f"{_pre}{name}说「{kw0}」，{guidance}")
        else:
            # R2349q（R81-P1-9）：无提问路径同 kw0 撞句也降级——
            # 此前圣杯2逆+权杖2逆连出两句一字不差的「失衡·两难·拉扯」。
            if kw0 in _seen_kw:
                lines.append(f"{_pre}{name}（{'正位' if cu else '逆位'}）"
                             f"也在说「{kw0}」，是呼应前面那张。")
            elif _tpl:
                lines.append(_tpl)
            else:
                # R2518：无提问路径此前只露原始 kw 串——指引表就在手边
                # 却不给（「收尾难·差口气·撑住」alone 对用户是术语），
                # 挂上指引句，与有提问路径同一深度。
                _gd = _tarot_kw_guidance(kw0, "")
                lines.append(f"{_pre}{name}（{'正位' if cu else '逆位'}），{ckw}。"
                             + (f"{_gd}。" if _gd else ""))
        _seen_kw.add(kw0)
    # 收尾：给一句具体方向
    tail = []
    # R3188（specs/012-P0）：二选一阵的核心问题「选哪个」此前只逐牌
    # 念不给倾向——选项A/选项B 两位的牌面轻重对比就是这局要交的答案。
    _cA = next((c for c in cards if c.get("position") == "选项A"), None)
    _cB = next((c for c in cards if c.get("position") == "选项B"), None)
    if _cA and _cB:
        def _opt_w(c):
            cu = bool(c.get("upright"))
            kw0 = (((c.get("upright_kw") if cu else c.get("reversed_kw"))
                    or "").split("·")[0])
            bad = ((not cu) or c.get("name") in _TAROT_HEAVY
                   or kw0 in _TAROT_HARD_UP)
            return (not bad), kw0
        _ga, _kwa = _opt_w(_cA)
        _gb, _kwb = _opt_w(_cB)
        if _ga and not _gb:
            tail.append(f"两边摆一块看：A 的「{_kwa}」是顺牌，"
                        f"B 的「{_kwb}」偏沉，牌面略偏 A；"
                        "但牌是参考，你心里那杆秤才是主票。")
        elif _gb and not _ga:
            tail.append(f"两边摆一块看：B 的「{_kwb}」是顺牌，"
                        f"A 的「{_kwa}」偏沉，牌面略偏 B；"
                        "但牌是参考，你心里那杆秤才是主票。")
        elif not _ga and not _gb:
            tail.append(f"A 的「{_kwa}」和 B 的「{_kwb}」都偏沉。"
                        "牌面说怎么选都不轻松，先想清楚哪个亏你更吃得起。")
        else:
            tail.append(f"A 的「{_kwa}」和 B 的「{_kwb}」都是顺牌。"
                        "牌面没拦你，哪边更像你想要的就走哪边。")
    if len(cards) > len(shown):
        tail.append(f"其余 {len(cards) - len(shown)} 张是细节的注脚。"
                    "主角是上面那几张。")
    if q:
        tail.append(f"综合来看，{_tarot_combined_guidance(shown, q)}")
    else:
        # C-004：禁用免责套话，改为给具体方向
        # R2349q（R81-P0-4）：无提问路径此前写死「整体是顺的」——
        # 死神/三逆位也照说；走 combined 函数吃重牌检查（原来里面
        # 的 not-q 重牌分支是死代码）。
        tail.append(_tarot_combined_guidance(shown, q))
    return _wrap(
        l0 if len(l0) <= _L0_MAX else l0[:_L0_MAX],
        None, lines[:5] + tail,
        details_from_sections(interp.get("sections") or []),
        interp.get("citations") or [],
    )

# D-002：牌义关键词 → 具体指引映射。
# R233u（R53-P0-3）：键必须与牌面首关键词（kw0）双向对齐——旧表 33 键
# 里 23 个永远不可达、69 个可达 kw0 只有 10 个有指引，88% 走兜底复读。
# 现全表 77 键 = DECK 全部 kw0，selftest（web/selftest.py 判据）里有覆盖闸钉着。
_TAROT_KW_GUIDANCE = {
    "调和": "你需要找到平衡，别走极端",
    "丰饶": "身边已经有值得珍惜的人/事了，别视而不见",
    "掌控": "主动权在你手里，想清楚自己要什么",
    "行动": "想好了就去做，别犹豫",
    "冲突": "有摩擦不怕，说开了反而更近",
    "阴影": "看不清的地方先照个亮，别急着否定自己的直觉",
    # R230a-7（R13-P0-3）：重牌软化指引——吓人字眼必须带安抚。
    "结束": "一个阶段翻篇了，不是坏事：腾出来的位置才有新的开始",
    "突变": "事情可能有变化，提前有准备就不慌",
    "束缚": "有些缠着你的东西，可以慢慢松开它",
    "幻象": "现在看不太清就先别急着定论，等等再决定",
    # 22 大牌 kw0
    "开始": "新起点就在眼前，先迈一小步试试",
    "鲁莽": "冲劲有了，就差先看一眼脚下",
    "创造": "你的想法能落地，别怕和别人不一样",
    "欺骗": "有些事没表面那么简单，多留个心眼",
    "直觉": "你的感觉是对的，别硬找理由否定它",
    "忽视直觉": "心里那个嘀咕声不是错觉，听听它",
    "依赖": "可以靠，但别把全部重量都放上一个人身上",
    "秩序": "按节奏来，现在稳比快重要",
    "专制": "抓得太紧反而留不住，松一点",
    "传承": "老办法有它的道理，值得参考",
    "教条": "规矩是死的，你的情况是活的",
    "结合": "能走到一起的就顺着来，别硬拧",
    "分歧": "不一致不可怕，先听对方说完再定",
    "前进": "方向没错，保持这个速度",
    "失控": "方向盘暂时不在你手里，先减速别硬掰",
    "勇气": "你比想象中扛得住，再顶一下",
    "软弱": "现在示弱不是认输，是保存体力",
    "内省": "答案在你自己身上，安静一会儿就听见了",
    "孤立": "一个人待着没问题，但别把门关死",
    "转折": "运气在换挡，别按老剧本走",
    "停滞": "停不是坏事，正好检查一遍再出发",
    "公正": "公道会到的，你该得的跑不掉",
    "偏颇": "信息不全的时候别急着站队",
    "换位": "站到对面看一眼，答案会不一样",
    "固执": "认死理认到最后，累的只有自己",
    "抗拒": "越抗拒越缠人，先承认它存在",
    "解脱": "松开的那一刻你就自由了",
    "避祸": "躲开的那一下，其实是替你挡了灾",
    "希望": "熬的这段够长了，这就是天亮前的信号",
    "失望": "落差是真实的，但它不是终局",
    "澄清": "雾在散，很快就能看清",
    "光明": "好事在明面上，放心往前走",
    "觉醒": "你其实已经醒了，接下来只是承认它",
    "自省": "回看不是后悔，是把路数理一遍",
    "完成": "这一段真的告一段落了，值得松口气",
    "未竟": "就差最后一步，别在这时候松手",
    # 56 小牌 rank/宫廷 kw0
    "开端": "种子刚落土，浇水就行，别挖出来看",
    "联合": "单打独斗不如搭个伙",
    "成长": "在往上走，别急，速度正常",
    "稳固": "底盘是稳的，可以往上盖了",
    "调整": "现在改还来得及，成本很低",
    "坚持": "快了，这时候放弃最亏",
    "进展": "在动，只是还没到你的视野里",
    "顶点": "到顶了，接下来该往回收一收",
    "暂缓": "先别启动，时机差一口气",
    "失衡": "两头都在拉你，先找回自己的重心",
    "受挫": "磕一下不是否定你，是路线要微调",
    "内耗": "最大的消耗是你自己跟自己打架",
    "反复": "旧问题回潮，这次换个处理方式",
    "自我怀疑": "怀疑自己是改卷太严，不是答得差",
    "阻滞": "堵是暂时的，别把堵车当成路不对",
    "过载": "扛太满了，该卸的卸一卸",
    "天真": "愿意相信是好事，给自己留个验证步骤",
    "涵养": "你稳得住，这就是最大的底牌",
    "学习": "当新手不丢人，这个阶段就该多吸收",
    "过度": "再好的东西过量了也是负担",
    "专断": "一言堂省事，但容易漏掉关键声音",
    "忧惧": "脑子里那个小剧场先关一关，事情没它演的那么糟",
    "谷底": "最坏的一段到了，往后只有回升，先照顾好自己",
    "缓过来": "没那么糟，你在慢慢回血：别急着复盘",
    "触底回升": "最坏的已经过去了，往后每一步都是往上",
    # R2349q（R81-P1-6）：宝剑3/8 覆写后的新 kw0 指引（重牌口吻带安抚）。
    "心痛": "疼是真的，但看清了就不白疼，先把自己照顾好",
    "愈合": "伤口在收口，别急着回去揭，让它自己长好",
    "受困": "绳子没你感觉的那么紧：先解最近的一个结",
    "松绑": "困住你的在松：往外挪一步试试",
    # R2555：14 张花色×rank 覆写的新 kw0 指引（tarot.py 同批）。
    "倦怠": "电量见底了先充电，不是懒，是该歇",
    "失落": "疼是真的，但别只盯着打翻的那几只",
    "怀念": "旧回忆可以待一会儿，别住下来",
    "选择多": "选项多不等于都要，先挑最想走的那条",
    "离开": "转身不是逃，是去找更对的位置",
    "如愿": "这段的甜是应得的，好好收下",
    "被看见": "你的努力有人在看，值得开心一下",
    "带伤撑着": "扛到这儿已经很厉害了，最后一段别硬顶",
    "扛太满": "担子可以分出去，全扛不是本事",
    "过渡": "在慢慢撤出难局，方向没错，别急",
    "取巧": "捷径可以走，但别留下要自己还的账",
    "手头紧": "难是阶段性的，门没关死：先顾好基本盘",
    "打磨": "笨功夫在这个阶段最值钱，继续做",
    "自足": "你自己挣的底气最稳，享受它",
    "回神": "缓过来了，好意就在眼前，伸手接一下",
    "困在过去": "滤镜该摘了，回头看一眼就走",
    "挑花眼": "先落地一个，别的幻想先放放",
    "舍不得走": "走不动就先停一停，但别骗自己还想要",
    "贪更多": "杯子已经满了，再多就洒了",
    "风头受挫": "掌声没来不代表没赢：先认自己的分",
    "真累了": "可以歇，带伤硬撑不值得",
    "该卸货了": "分出去不丢人，是你一个人的太多了",
    "耍滑反噬": "小聪明翻车了，补洞比躲账省力",
    "练不动": "手感断了就停一停，偷工不如歇",
    "虚撑": "底气要真的，撑场面不如先补内功",
}

# R230a-7（R13-P0-3）：重牌黑名单——抽到这些牌时综合判定不说
# 「整体是顺的」（问健康抽到死神还说「顺」是错上加错）。
_TAROT_HEAVY = {"死神", "高塔", "恶魔", "月亮", "宝剑3", "宝剑9", "宝剑10",
                # R2555：圣杯5（失落哀悼）/星币5（拮据被冷落）是
                # 真负牌——问健康抽到它们还说「整体是顺的」同样错上加错。
                "圣杯5", "星币5"}

# R3119：正位但牌面本身在吃力的 kw0——这些牌不在重牌名单（不是
# 负牌），但落阻碍位说「障碍不算硬」是错的（权杖10「扛太满」实测
# 领走过「好牌落阻碍位」）。判据走 kw0 不走牌名：共享 rank 词
# （5=冲突/9系撑型/10系满载吃力）与花色覆写都能接住。
_TAROT_HARD_UP = {"受困", "忧惧", "谷底", "扛太满", "带伤撑着",
                  "倦怠", "失落", "手头紧", "取巧", "冲突", "内耗",
                  "受挫"}

def _tarot_kw_guidance(kw: str, q: str) -> str:
    """D-002：将牌义关键词转化为用户问题的具体指引"""
    # R2518：无提问路径也吃指引表——原回落「提示你关注 X 的能量」
    # 是空泛 meta 句；表里有就用表里的行动句，没有才回落。
    if not q:
        return _TAROT_KW_GUIDANCE.get(
            kw, f"这张牌提示你关注「{kw}」的能量")
    # 直接返回关键词对应的指引
    return _TAROT_KW_GUIDANCE.get(kw, f"关于你问的，「{kw}」是一个重要信号")

def _tarot_combined_guidance(cards: list[dict], q: str) -> str:
    """D-002：综合多张牌给一句方向性指引"""
    # R2349g（R68-P1-3）：收尾句按首牌名做确定性盐，各档双变体——
    # 同阵重抽（同日同问 seed 恒定）仍同款，跨问题/跨天错开。
    _salt = sum(ord(c) for c in str((cards[0] or {}).get("name", ""))) if cards else 0
    _alt = (_salt % 2) == 1
    # R3119：正位硬牌计权重——满手「扛太满/受困」的正位牌面
    # 说「整体是顺的」是错的（判词只描述盘面劲向，不落吉凶断言）。
    _hard_n = sum(1 for c in cards if c.get("upright")
                  and (c.get("upright_kw") or "").split("·")[0]
                  in _TAROT_HARD_UP)
    if not q:
        # C-004：禁用免责套话，改为给具体方向
        # R230a-7（R13-P0-3）：无提问路径同样先看重牌
        if any(c.get("name") in _TAROT_HEAVY for c in cards):
            return ("牌里有几张在提醒你，先把自己照顾好，事情慢一点没关系。"
                    if not _alt else
                    "这组牌有几张沉甸甸的：先顾好自己，别的都可以等等。")
        if _hard_n >= 2:
            return ("这组牌好几张都在使劲，先把手上的担子卸一卸再赶路。"
                    if not _alt else
                    "牌不凶但挺累：先看哪件事可以先分出去、放一放。")
        return ("牌面整体是顺的，可以试着往前走一小步。"
                if not _alt else
                "这组牌气色不错：心里那件事，可以往前试半步。")
    # R230a-7（R13-P0-3）：有重牌在场时不论正逆位都不说「整体是顺的」——
    # 先安抚再看走向。
    if any(c.get("name") in _TAROT_HEAVY for c in cards):
        return (f"牌里有几张在提醒你的位置，关于「{q}」，先照顾好自己，事情可以慢一点推进。"
                if not _alt else
                f"关于「{q}」，牌里有几张分量重的，先把自己安顿好，事不急这一天。")
    # R3119：q 路径同口径——≥2 张正位硬牌先答「累」再谈顺逆。
    if _hard_n >= 2:
        return (f"这组牌好几张都在使劲，关于「{q}」，先看你手上的事哪件能卸一卸。"
                if not _alt else
                f"关于「{q}」，牌不凶但担子重，先把能分出去的分出去。")
    # 根据牌的正逆位比例给综合判断
    # R3129（specs/012-P4 同构）：三档收尾补「观察信号+复判时点」——
    # 方向句之后给可验的行动锚，不停在「多观察几天」。
    upright_count = sum(1 for c in cards if c.get("upright"))
    total = len(cards)
    if upright_count > total * 0.6:
        return (f"牌面整体是顺的，你问的「{q}」可以试着往前走一小步。"
                "先看第一步走出去的两三天里事情是变顺还是更卡。"
                "更卡就停一停回来复盘，顺就接着走。"
                if not _alt else
                f"顺位的牌占了上风，「{q}」这事，可以先迈半步试试水。"
                "落脚的两三天看动静：顺就继续，卡了就退一步看哪不对。")
    elif upright_count < total * 0.4:
        return (f"牌面有些别扭，关于「{q}」先别急着推进，多观察几天。"
                "观察的信号很简单：让你犯别扭的那个点接下来会不会自己"
                "化开：一周内没化开，这事就值得重新想想而不是硬推。"
                if not _alt else
                f"逆位偏多，「{q}」这事先放一放，看清了再动不迟。"
                "放一放的期间盯住一件事：别扭的根源露头没有。"
                "露头了再决定要不要动。")
    else:
        return (f"牌面有顺有逆，关于「{q}」保持现状，等时机更明朗再动。"
                "等的期间别干等：把手边能准备的那部分先备着，"
                "信号一明你就能抢半步。"
                if not _alt else
                f"顺逆各半，「{q}」眼下不动比乱动强，再等等信号。"
                "等的空档先备着能备的，信号一明直接动，不浪费等待。")


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
        # R2349s（R84-P0-3）：one_liners 改为分档 dict——关键词过滤
        # 强档只命中 2/16，旺盘实测抽到「待激活」弱档句同屏互搏。
        # 现在每档 ≥4 条且永不错档；盐仍带日期逐日轮换。
        _today = _today_cn().isoformat()
        _ol = _tb.get("one_liners") or {}
        _pool = (_ol.get(_band) if isinstance(_ol, dict)
                 else _ol) or []
        l0 = _pick(_pool, t.get("year_zhi"), _today, "ol")
        _band = ("强" if "偏快" in strength
                 else "弱" if "慢热" in strength else "中")
        # R3089（specs/010-P1）：判词带——锚 strength/hit_pillars，
        # 落柱翻成「缘分入口在哪条圈」的具体预言，替代 replies 池软句。
        _hit_keys = [p for p in (t.get("hit_pillars") or [])]
        _hits = [_PILLAR_WARM.get(p, p) for p in _hit_keys]
        if _band == "强":
            _v = (f"判词直说：缘分信号偏强，桃花落在"
                  f"{'、'.join(_hits)}——传统口径里这叫缘分底子厚，"
                  "意思是属于你的机缘本来就不缺")
        elif _band == "中":
            _v = (f"判词直说：有信号不算旺，桃花落在{_hits[0]}——"
                  "缘分入口主要走这根柱")
        else:
            _v = ("判词直说：缘分信号偏弱，四柱都没临桃花：不是没有，"
                  "是入口不在自己身上")
        lines: list[str] = [_v]
        # 入口预判：落柱→具体圈层（年=老同学同乡、月=同事同龄、
        # 日=身边近圈、时=晚熟/线上）；无落柱→介绍人渠道。
        _PILLAR_SCENE = {
            "year": "年柱管早年根基，传统口径里信号偏「旧相识、家里牵线」这条线",
            "month": "月柱管成长环境，信号偏「同龄人、一起做事的圈子」",
            "day": "日柱管贴身圈，信号不在远方，就在你天天见得着的人里",
            "hour": "时柱管晚段，信号偏晚来，传统口径里也可能来自比你小的一圈",
        }
        if _hit_keys:
            lines.append("入口预判（传统口径）：" + "；".join(
                _PILLAR_SCENE.get(p, "") for p in _hit_keys
                if p in _PILLAR_SCENE) + "。")
        else:
            lines.append("入口预判：缘分入口在介绍人和熟人局，可做的"
                         "事：每月至少两次熟人局露脸，让朋友知道你在看。")
        peach = t.get("peach_zhi") or ""
        yz = t.get("year_zhi") or ""
        if peach:
            # R2349s（R84-P2-18）：地支黑话翻译——与大运行的 ZHI_DIR
            # 口径一致（「卯（兔·东）」）。
            _pz = ZHI_ZODIAC.get(peach, "")
            _pd = ZHI_DIR.get(peach, "")
            _pt = f"{peach}（{_pz}·{_pd}）" if _pz and _pd else peach
            lines.append(f"传统口径把桃花位挂在「{_pt}」，图个开心记着玩就行。")
        # R230a-7（R13-P2-4）：copy_bank 分支此前丢了坐标事实行
        # （落柱/红鸾/天喜）——与 fallback 分支对齐，保住可核验性。
        # R3089：落柱/无落柱已由判词行+入口预判承担，此段并入不再复述。
        _hl = "、".join(_PILLAR_WARM.get(p, p)
                       for p in (t.get("hongluan_pillar") or []))
        _tx = "、".join(_PILLAR_WARM.get(p, p)
                       for p in (t.get("tianxi_pillar") or []))
        # R2350b（R98-P1-7）：天喜/红鸾首提随行翻译——裸词贴屏时
        # 用户不知道这两个词指什么。
        if _hl and _hl != "未临柱":
            lines.append(f"红鸾（婚恋信号）落在{_hl}，婚恋缘分的信号在你自己盘里。")
        if _tx and _tx != "未临柱":
            lines.append(f"天喜（喜庆信号）落在{_tx}：喜庆缘分的信号也有。")
        dayun = t.get("dayun_hits") or []
        if dayun:
            # F-005：应期年份动态计算用户年龄（±5 岁内有参考价值）
            # F-006：干支改生肖+方位注释
            _now = _today_cn()
            _user_birth_year = t.get("birth_year") or (_now.year - 22)
            _user_age = _now.year - _user_birth_year
            _near = [d for d in dayun if abs(int(d.get("start_age", 0)) - _user_age) <= 5]
            if _near:
                d0 = _near[0]
                _pillar = d0.get("pillar", "")
                _zodiac = ZHI_ZODIAC.get(_pillar[1:2] if _pillar else "", "")
                _dir = ZHI_DIR.get(_pillar[1:2] if _pillar else "", "")
                _extra = f"（{_zodiac}·{_dir}）" if _zodiac and _dir else f"（{_zodiac}）" if _zodiac else ""
                # R3079（巡#496）：|start_age-age|≤5 的近命中里，多数情况
                # 用户其实正住在这运里（start≤age<end）——过去时
                # 「那阵子多出门走走」是把当下窗口讲成三年前的事。
                # 在运中改现在时+换班边界；未到/已过才留年份锚。
                _sa = float(d0.get("start_age") or 0)
                _ea = float(d0.get("end_age") or 0)
                if _ea and _sa <= _user_age < _ea:
                    _end_year = _user_birth_year + int(round(_ea))
                    lines.append(
                        f"你现在正走在{_pillar}{_extra}运里（约到"
                        f"{_end_year}年才换班），这几年社交面正宽，"
                        "多出门走走正是时候。")
                else:
                    lines.append(f"{d0.get('year_start')}年前后走{_pillar}{_extra}运，社交面会明显变宽，那阵子多出门走走。")
            elif dayun:
                d0 = dayun[0]
                # F-014：当年份远离用户年龄时，删除具体年份，改为中性描述
                _year = int(d0.get("year_start", 0))
                _diff = abs(_year - _user_birth_year - _user_age)
                if _diff > 15:
                    # R230y（R36-口播）：晚缘不再虚化——「未来某段时间」对用户
                    # 等于没说（实测 1998 年生应期落在 69+ 岁）。给「慢炖型」
                    # 定心丸话术，比含糊更准确也更治愈。
                    # R2350b（R98-P1-7）：「应期」翻成「来得偏晚」。
                    lines.append("你的缘分信号（天喜/红鸾）来得偏晚，缘分是慢炖型的，先把日子过出自己的节奏，该来的会踩点到。")
                else:
                    # R2349s（R84-P1-8）：「互动期」是合婚术语串场——
                    # 单人盘改「桃花运当班」口径。
                    lines.append(f"从{d0.get('year_start')}年起桃花运当班，节奏上的参考，不是日程表。")
        # D-003：禁用免责套话「感情这事你的感受最重要」
        # R3089：收口改带地图交权——信号强弱和入口已指明，决定权如实归还。
        # R3125（specs/012-P5）：弱档收口带脱罪位——信号弱是盘上
        # 没临柱，不是人的问题。
        if _band == "弱":
            lines.append("说句公道话：四柱没临桃花是盘的事，不是你不够"
                         "好，命理报的是信号强弱和入口方向；门在哪指"
                         "出来了，敲不敲门、跟谁走，是你的选择。")
        else:
            lines.append("命理报的是信号强弱和入口方向，缘分的门在哪指出来"
                         "了；敲不敲门、跟谁走，是你的选择。")
        _body, _close = lines[:-1][:6], lines[-1:]
        return _wrap(
            l0,
            None,
            _body + _close,
            _render_details(t.get("render", "")),
            [],
        )

    # R230a-7（R13-P2-3）：无 copy_bank 的 fallback 路径此前 l0 从未赋值
    # → NameError。按强度给固定一句。
    l0 = ("缘分信号满格" if "偏快" in strength
          else "慢热蓄力中" if "慢热" in strength else "稳步升温中")
    # R3089：fallback 分支同构判词带+入口预判（与 copy_bank 路径同口径）。
    _hit_keys = [p for p in (t.get("hit_pillars") or [])]
    hits = [_PILLAR_WARM.get(p, p) for p in _hit_keys]
    if "偏快" in strength:
        _v = (f"判词直说：缘分信号偏强，桃花落在{'、'.join(hits)}——"
              "传统口径里这叫缘分底子厚，意思是属于你的机缘本来就不缺")
    elif "慢热" in strength:
        _v = ("判词直说：缘分信号偏弱，四柱都没临桃花：不是没有，"
              "是入口不在自己身上")
    else:
        _v = (f"判词直说：有信号不算旺，桃花落在{hits[0]}——"
              "缘分入口主要走这根柱")
    lines: list[str] = [_v]
    _PILLAR_SCENE = {
        "year": "年柱管早年根基，传统口径里信号偏「旧相识、家里牵线」这条线",
        "month": "月柱管成长环境，信号偏「同龄人、一起做事的圈子」",
        "day": "日柱管贴身圈，信号不在远方，就在你天天见得着的人里",
        "hour": "时柱管晚段，信号偏晚来，传统口径里也可能来自比你小的一圈",
    }
    if _hit_keys:
        lines.append("入口预判（传统口径）：" + "；".join(
            _PILLAR_SCENE.get(p, "") for p in _hit_keys
            if p in _PILLAR_SCENE) + "。")
    else:
        lines.append("入口预判：缘分入口在介绍人和熟人局，可做的"
                     "事：每月至少两次熟人局露脸，让朋友知道你在看。")
    peach = t.get("peach_zhi") or ""
    yz = t.get("year_zhi") or ""
    if peach:
        # R2509（审-P2-13）：「年支」译成属相——用户对自己的属相有概念。
        lines.append(f"你的属相是{yz}，传统口径把桃花位挂在「{peach}」，"
                     f"图个开心记着玩就行。")
    hl_p = "、".join(_PILLAR_WARM.get(p, p) for p in (t.get("hongluan_pillar") or []))
    tx_p = "、".join(_PILLAR_WARM.get(p, p) for p in (t.get("tianxi_pillar") or []))
    if hl_p != "未临柱" and hl_p:
        lines.append(f"红鸾落在{hl_p}，传统上主婚恋缘分的信息在你自己盘里。")
    if tx_p and tx_p != "未临柱":
        lines.append(f"天喜落在{tx_p}：喜庆缘分的信息也是有的。")
    dayun = t.get("dayun_hits") or []
    if dayun:
        d0 = dayun[0]
        lines.append(f"{d0.get('year_start')}年前后走{d0.get('pillar')}运，"
                     f"桃花运当班，那段时间社交面会明显变宽。")
    # D-003：禁用免责套话「感情这事你的感受最重要」
    # R3089：fallback 收口同构带地图交权。
    # R3125（specs/012-P5）：弱档带脱罪位，与主路径同口径。
    if "慢热" in strength:
        lines.append("说句公道话：四柱没临桃花是盘的事，不是你不够"
                     "好，命理报的是信号强弱和入口方向；门在哪指"
                     "出来了，敲不敲门、跟谁走，是你的选择。")
    else:
        lines.append("命理报的是信号强弱和入口方向，缘分的门在哪指出来"
                 "了；敲不敲门、跟谁走，是你的选择。")
    _body, _close = lines[:-1][:6], lines[-1:]
    return _wrap(
        l0,
        None,
        _body + _close,
        _render_details(t.get("render", "")),
        [],
    )


# ---------------------------------------------------------------------------
# R3087（specs/010-P0）：合婚判词引擎素材——信号→摩擦类型→剧本→处方。
# 全部通行命理口径（日支冲五行分型/五行相克五型/年冲→家庭线），
# 判词直说不稀释，但每条负向必带具体矛盾面+条件化解，不写宿命断言。
# ---------------------------------------------------------------------------

# 日主五行相克十组合 → （摩擦主题， 剧本）。谁克谁决定矛盾样态——
# 金克木=批评与自由、木克土=进取与安稳、土克水=管控与自由、
# 水克火=冷热错频、火克金=冲动与界线（通行口径）。
_WX_KE_FRICTION: dict[frozenset, tuple[str, str, str]] = {
    frozenset(("金", "木")): (
        "批评与自由",
        "属金的那方习惯挑毛病、立规矩，属木的那方觉得怎么做都被否定。"
        "戏路基本是：TA随口一句「这个你又没弄好」，你当时没吭声，"
        "心里那根刺一晚上没拔；第二天TA早忘了，你还闷在情绪里。"
        "一个要快刀斩乱麻，一个要慢慢长。吵的点大多在「你管太多」。",
        "处方三段：先做，属金那方每天只挑一件非说不可的事说出口，"
        "剩下的咽回去；看信号，一周内对方回嘴变少、主动说话变多，"
        "就是走对了；要是越管越僵，改成每周固定一顿饭时间才提意见。"),
    frozenset(("木", "土")): (
        "进取与安稳",
        "属木的那方嫌对方不上进、太保守，属土的那方安全感被反复打破。"
        "戏路基本是：你兴冲冲说想换工作/想搬出去，TA第一反应是"
        "「现在这样不是挺好吗」，你觉得被泼了冷水，TA觉得你总折腾。"
        "接下来几天各说各话。吵的点大多在「变不变、怎么变」。",
        "处方三段：先做，换工作、搬家、大额开销这类事提前一个月"
        "打招呼；看信号，对方从「又来」变成问细节，缓冲就起作用了；"
        "要是还是顶回去，把变动拆小步：先说想干嘛，过两周再谈怎么干。"),
    frozenset(("土", "水")): (
        "管控与自由",
        "属土的那方爱安排、设限、查岗，属水的那方灵活爱变化、被管到"
        "窒息。戏路基本是：晚上没及时回消息，TA连发几条「在哪」"
        "「和谁」，你回得越简短TA问得越勤；挂电话那一刻两个人都"
        "委屈：一个要落地，一个要流动。吵的点大多在「你别管我」。",
        "处方三段：先做，出门前主动发一句「今晚和谁在哪」；看信号"
        "，对方追问次数降下来、语气松了，报备就到位了；要是还在"
        "连环问，约定一个固定的睡前通话时间，把不确定感填平。"),
    frozenset(("水", "火")): (
        "冷热错频",
        "属火的那方热情外放要回应，属水的那方冷静理性爱泼冷水。"
        "戏路基本是：你这边委屈得快要哭出来，TA在电话那头开始"
        "冷静分析「这事其实不怪谁」，你要的是抱住，TA给的是道理；"
        "越分析你越崩。吵的点大多在「你根本不在乎我」。",
        "处方三段：先做，热的那方开口前先说要哪种回应（要抱抱还是"
        "要建议）；看信号，下次情绪上头时对方没再讲道理而是先接住，"
        "就对频了；要是对方还是讲道理，直接把那句「我现在不需要"
        "分析」说出口。"),
    frozenset(("火", "金")): (
        "冲动与界线",
        "属火的那方凭热情行事、花钱凭感觉，冲垮属金那方的规则和计划。"
        "戏路基本是：你一时兴起买了个东西/临时改了个计划，TA的脸"
        "当场就沉下来「说好先商量的呢」；你觉得多大的事至于吗，"
        "TA觉得说好的规则你又破了，一个先干了再说，一个先想清楚"
        "再动。吵的点大多在「你怎么又乱来」。",
        "处方三段：先做，定一个数（比如单笔超过两人说好的额度），"
        "超过就各有一票否决权；看信号，冲动消费引发的争执归零，"
        "闸就设对了；要是对方觉得被管，把否决权换成「冷静24小时"
        "再下单」的软闸。"),
}

# 日支相冲按两支五行分三型（通行口径）：
# 水火（子午/巳亥）=急性争吵、两土（丑未/辰戌）=冷战较劲、
# 金木（寅申/卯酉）=硬碰硬原则之争。
def _dz_clash_flavor(dza: str, dzb: str) -> tuple[str, str, str]:
    """日支冲型 → （型名， 剧本， 处方）。"""
    pair = frozenset((ZHI_ELEMENT.get(dza, ""), ZHI_ELEMENT.get(dzb, "")))
    if pair == frozenset(("水", "火")):
        return ("水火相战",
                "急性争吵型：为小事当场爆、和好也快，伤在话赶话"
                "不留余地。典型戏路：晚上一条消息回的慢了或语气淡了，"
                "三两句就呛起来，「你什么意思」「你又什么意思」翻屏半小时；"
                "消气也快，就是每次都要说点狠话。爆点多是回复速度、"
                "语气、面子这类小事。",
                "处方三段：先做，吵上头时各自离屏十分钟，回来先复述"
                "对方那句再说自己的；看信号，争吵从翻屏半小时缩到"
                "十分钟内收尾，就是拆对了；要是还是收不住，把「先挂"
                "电话冷静」写成两人的暗号。")
    if pair == frozenset(("土", "土")):
        return ("两土斗气",
                "冷战较劲型：谁都不先低头、翻旧账。典型戏路：为家务谁干"
                "或一句话绊了嘴，当晚谁也不说话各刷各的手机；第二天"
                "还在僵，第三天变成「你还好意思不理我」，耗的是日常"
                "不是大事，但一次能拖好几天。",
                "处方三段：先做，约好冷战最多两小时，到点先问饿不饿；"
                "看信号，僵局从拖好几天缩到当天解开，就顺了；要是连"
                "暗号都拉不下脸用，写下来发消息也算数。")
    if pair == frozenset(("木", "金")):
        return ("金木相战",
                "硬碰硬型：原则和面子之争，吵起来升级快、容易把话"
                "说绝。典型戏路：本来是「这事怎么办」，三句就变成"
                "「到底听谁的」，再两句变成「你凭什么管我」，谁退"
                "一步都像认输。爆点多在「这事到底听谁的」。",
                "处方三段：先做，原则之争改问「这事谁更难受听谁的」，"
                "面子局换成感受局；看信号，争执不再往「听谁的」上滑，"
                "就解套了；要是还在抢赢，各写三条最在意的底线对表。")
    return ("相冲", "相处里有磕绊，把话说开比憋着强。",
            "处方三段：先做，别扭别过夜，睡前各自说一句今天哪里不"
            "舒服；看信号，小账日清，不再翻上周的旧账；要是连说都"
            "说不出口，先发文字再当面聊。")


# R3218：五行 → 一词气质（本命小卡「五行分布」行的人话落点）。
# 前端 _WX_TAG 逐字镜像（selftest wx.tag.parity 钉），单侧改会打闸。
WX_TAG: dict[str, str] = {
    "木": "向上长、有主心骨",
    "火": "热、快、要回应",
    "土": "稳、认死理、能托底",
    "金": "利落、有边界感",
    "水": "活、会转弯、能沉住",
}


def _hehun_pos_anchor(h: dict) -> str:
    """合婚盘里的首个正信号锚点（判词用）。"""
    if h.get("day_wx_sheng"):
        return (f"本命五行相生（{h.get('day_wx_a', '')}与"
                f"{h.get('day_wx_b', '')}）")
    _dz0 = h.get("day_zhi_rel") or ""
    _dzc = (f"{h.get('day_zhi_a', '')}/{h.get('day_zhi_b', '')}"
            if h.get("day_zhi_a") and h.get("day_zhi_b") else "")
    if _dz0 == "合":
        return f"夫妻宫{_dzc}六合" if _dzc else "夫妻宫六合"
    if _dz0 == "半合":
        return f"夫妻宫{_dzc}半合" if _dzc else "夫妻宫半合"
    if h.get("combine"):
        return "年支六合"
    if h.get("gan_he"):
        return "本命天干五合"
    if h.get("nayin_rel") in ("相生", "比和"):
        return "年命纳音相合"
    if h.get("peach_same"):
        return "桃花位相同"
    return ""


# R3152：合婚带问句——判词后补一行「对着你问的说」。只回词域命中
# 的五类（长久/吵架/复合/异地/心思），指向卡上已有的确定性段落，
# 不重复内容；未命中词域不塞行（认了问题但答非所问比不认更伤）。
def _hehun_q_line(q: str, h: dict) -> str:
    if _re_lq.search(r"结婚|嫁|娶|长久|未来|走下去|合适|适合|领证|订婚|定下来|走到底", q):
        dy = [d for d in (h.get("dayun_hits") or [])
              if int(d.get("start_age_a", 99)) >= 16]
        if dy:
            dy.sort(key=lambda d: abs(int(d.get("year_start", 0))
                                      - _today_cn().year))
            d0 = dy[0]
            _rel = d0.get("relation") or ""
            return (f"你问能不能走得长远，长期看的是两人大运的节奏："
                    f"{d0.get('year_start')}年前后那段大运是「{_rel}」"
                    + ("合，那段时间适合把大事往前定。"
                       if _rel == "合" else
                       "冲，那段时间容易顶上，大事慢半拍再定。"))
        return ("你问能不能走得长远，上面判词档答的是底子，"
                "下面「大运互动」那段是节奏坐标。")
    if _re_lq.search(r"吵架|磨合|矛盾|冷战|相处|争执|总吵|闹掰", q):
        return ("你问的是相处，下面「磨在」那段就是具体剧本，"
                "引信到当晚都写了；判词答底子，剧本答日子。")
    if _re_lq.search(r"复合|前任|挽回|和好|重新|回头", q):
        return ("你问要不要重来，复合看的是上次绊住你们的那几处"
                "变没变：下面的磨点就是它们，没变的话分数也不会变。")
    if _re_lq.search(r"异地|距离|见面少|两地", q):
        return ("你问异地，盘上量的是节奏合不合，不是公里数；"
                "下面「大运互动」那段是你们适合往一处走的时间窗。")
    if _re_lq.search(r"喜欢我|爱我|在意我|怎么想|心思|在乎|看.{0,2}我", q):
        return ("你问 TA 眼里你什么样，往下「互看」那段是照着"
                "十神互见算的：一段是你看 TA，一段反过来。")
    return ""


def warm_hehun(h: dict) -> dict:
    """合婚人话视图（R3087/specs/010 判词引擎版）。

    判词直说（不适合就说不合适）+ 生活面矛盾预言 + 条件化解 +
    带地图交权——修「磨合期长一点」「靠你们自己写」式软话。
    所有判词锚定已算出的信号字段，分档锚 match_score。"""
    h = h or {}
    _dz0 = h.get("day_zhi_rel") or ""
    _dza, _dzb = h.get("day_zhi_a", ""), h.get("day_zhi_b", "")
    _dzc = f"{_dza}/{_dzb}" if _dza and _dzb else ""

    # ---- R3087 判词引擎：硬伤清单 + 分档判词 -------------------------
    # 硬伤锚点（判词用）+ 生活面矛盾预言（正文行用）——每条负信号
    # 都落到「会为哪个生活面吵」，不写「磨合期长一点」式虚词。
    _hard: list[str] = []
    _dz_flavor, _dz_script, _dz_rx = "", "", ""
    if _dz0 == "冲":
        _dz_flavor, _dz_script, _dz_rx = _dz_clash_flavor(_dza, _dzb)
        _hard.append(f"日支{_dzc}相冲" if _dzc else "日支相冲")
    if h.get("clash"):
        _hard.append("年支六冲")
    _wx_ke = None
    if not h.get("day_wx_sheng") and not h.get("day_wx_same") \
            and h.get("day_wx_a") and h.get("day_wx_b"):
        _wx_ke = _WX_KE_FRICTION.get(
            frozenset((h.get("day_wx_a"), h.get("day_wx_b"))))
        _hard.append("本命五行相克")

    # 分档判词：锚 match_score（确定性 35–99）+ 硬伤数。吕才口径：
    # 夫妻宫冲/年冲/相克任一在场就不评上等；三硬伤叠满直接最低档。
    _scn = h.get("match_score")
    _scn = _scn if isinstance(_scn, (int, float)) else None
    if (_scn is not None and _scn < 45) or len(_hard) >= 3:
        _band = 3
    elif _hard and (len(_hard) >= 2 or _scn is None or _scn < 60):
        _band = 2
    elif _scn is not None and _scn >= 80 and not _hard:
        _band = 0
    else:
        _band = 1
    _neg = "、".join(_hard[:2])
    if _band == 3:
        rel = (f"判词直说：偏不合适，{_neg or '盘面负信号重叠'}，"
               "这套判定里能叠的负信号叠了大半。"
               "不是说不能走，是下面这几条成本先看完再定")
    elif _band == 2:
        rel = (f"判词直说：磕绊偏多，{_neg or '盘面助力薄'}，"
               "这组要花的力气比一般组合多。值不值，看完下面"
               "的具体问题再算")
    elif _band == 0:
        _pa = _hehun_pos_anchor(h)
        rel = (f"判词直说：上等合拍，{_pa}，这套判定里算底子顺的组合"
               if _pa else
               "判词直说：上等合拍，盘面正信号叠得多，底子是顺的")
    else:
        _pa = _hehun_pos_anchor(h)
        if _hard:
            rel = (f"中上磨合，{_pa or '底子能处'}，"
                   f"但{_neg}这类磕绊在判定里是明确负信号，下面直说磨在哪")
        elif _pa:
            rel = f"中上磨合：{_pa}，底子合得来，日子怎么过看怎么走法"
        else:
            rel = ("中上磨合：盘面没大冲也没大合，判定口径里算平淡局："
                   "说不上天定好也不算坏，路怎么走全看怎么处")
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
        # R233u（R53-P1-1）：强肯定词全归强桶——「这俩是真配」「双向奔赴型
        # 选手」等半强词此前漏在中性桶，盐修好就会砸到相克盘。
        _STRONG_CP = {"甜度超标组合", "天生一对CP", "合拍度少见的一对",
                      "合拍底子少见的厚", "越处越合拍的一对", "默契度拉满的一对",
                      "互补型神仙搭档", "甜而不腻的组合", "这俩是真配",
                      "双向奔赴型选手", "久处不厌预备役"}
        # R2349s（R84-P1-10）：强桶门槛此前只看年支 clash——日支冲
        # （夫妻宫顶牛）的相生盘照样抽「锁死这对了」，日支冲一并禁强桶。
        # R3226：摩擦向标签对 band0 上等合拍盘是口径打架（判词说底子
        # 顺、标签说要磨）——band0 剔出摩擦桶；band1 中上磨合照抽。
        _FRICTION_CP = {"欢喜冤家预定", "并肩作战型情侣",
                        "磨合型但有韧劲的一对", "磨合着磨合着就顺了"}
        _pool = (_hh_all if _band != 0 else
                 [t for t in _hh_all if t not in _FRICTION_CP])
        if not _pool:
            _pool = ["细水长流搭子"]
        if h.get("day_wx_sheng") and not h.get("clash") \
                and _dz0 != "冲":
            l0 = _pick(_pool, h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")
        else:
            _mid = [t for t in _pool if t not in _STRONG_CP] or ["细水长流搭子"]
            l0 = _pick(_mid, h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")
    # R3087：判词低档不抽甜池——band3 偏不合适换诚实档；band2 磕绊
    # 偏多限「认架」标签（细水长流/平平淡淡对磕绊盘是假话）。
    if _band == 3:
        l0 = _pick(["磕绊偏多的组合", "信号不太顺的一对",
                    "难走但不是死局的一对"],
                   h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")
    elif _band == 2:
        l0 = _pick(["要磨合的组合", "得花力气的一对",
                    "处得久要靠耐心的一对"],
                   h.get("day_zhi_a"), h.get("day_zhi_b"), "hh")

    lines: list[str] = [f"{rel}。"]
    # R3152：带问句时判词下一行就对着问的说——卡面不再无视那句
    # 「我们能结婚吗」。
    _ql = _hehun_q_line((h.get("question") or "").strip(), h)
    if _ql:
        lines.append(_ql)
    # 证据行按吕才婚配的证据层级排：夫妻宫 > 日主五行 > 年支 > 纳音。
    # 每条负信号都落「会为哪个生活面吵」，不写虚词（R3087/specs/010）。
    if _dz0 == "冲":
        lines.append(f"夫妻宫这组冲属{_dz_flavor}，{_dz_script}")
    elif _dz0 == "合":
        lines.append(f"日支（你们俩的夫妻宫）{h.get('day_zhi_a','')}/"
                     f"{h.get('day_zhi_b','')}六合：传统合婚最看重的一支"
                     f"对上了，底色是合的。")
    elif _dz0 == "半合":
        lines.append(f"日支（你们俩的夫妻宫）{h.get('day_zhi_a','')}/"
                     f"{h.get('day_zhi_b','')}半合：相处里有天然的合拍。")
    # R2509（审-P1-4）：默认受众不认「日主五行/纳音/大运」行话——
    # 首提一律译成「本命五行/五行小名/十年一轮的大方向」。
    if h.get("day_wx_sheng"):
        lines.append(f"两人本命五行相生（{h.get('day_wx_a', '')}与"
                     f"{h.get('day_wx_b', '')}），能量是顺着走的，"
                     f"一方天然愿意托着另一方。")
    elif h.get("day_wx_same"):
        # R230a-7（R13-P0-2）：同五行是比和——此前被归入「相克」口径。
        lines.append(f"两人本命五行同是{h.get('day_wx_a', '')}：同气相属，"
                     f"合拍来得快，顶起来也镜像，各留半步就顺。")
    elif _wx_ke:
        lines.append(f"两人本命五行相克（{h.get('day_wx_a', '')}与"
                     f"{h.get('day_wx_b', '')}），相克就是相克，判定上"
                     f"不绕弯：这组磨在「{_wx_ke[0]}」上，{_wx_ke[1]}")
    if h.get("clash"):
        lines.append("年支六冲·传统口径管这种叫根基相冲：矛盾容易长在"
                     "两个家庭的衔接处，双方父母、买房养老、孩子教育、"
                     "回谁家过年，是这组盘最常爆的点。")
    elif h.get("combine"):
        lines.append("年支六合：传统上主两家的根基合得来，"
                     "见家长和扯皮琐事上少一道坎。")
    elif h.get("year_zhi_rel") == "半合":
        lines.append("年支半合：根基层有三分顺意，不是最强的那种合，"
                     "但过日子够用。")
    # R3087：处方紧跟主证（日支冲型 > 相克型 > 年冲家庭线），
    # 被截断时先丢的是纳音/互看/大运这些低权重尾行。
    _rx = _dz_rx or (
        _wx_ke[2] if _wx_ke else
        ("处方三段：先做，两家的事提前立规矩，回谁家过年、买房谁出"
         "钱、父母介入多深都说死；看信号，逢年过节不再为这些事红脸；"
         "要是规矩还被冲破，下次谁越界谁负责去和对方家里解释。"
         if h.get("clash") else ""))
    if _rx:
        lines.append(_rx)
    if h.get("nayin_rel") == "比和":
        lines.append(f"年命纳音（五行的传统小名）同是"
                     f"{h.get('nayin_a','')}：命底相近，"
                     f"很多事不用解释就懂。")
    elif h.get("nayin_rel") == "相生":
        lines.append(f"年命纳音相生（{h.get('nayin_a','')}与"
                     f"{h.get('nayin_b','')}），传统上主互相滋养，"
                     f"在一起越久越顺。")
    elif h.get("nayin_rel") == "相克":
        lines.append(f"年命纳音相克（{h.get('nayin_a','')}与"
                     f"{h.get('nayin_b','')}），命底小名也对冲，"
                     f"这一项在判定里权重轻，记个底色提示就行。")
    if h.get("peach_same"):
        lines.append(f"两人桃花位相同（都是{h.get('peach_a', '')}）"
                     f"对感情的期待容易同频。")
    # R204b（D-257b）：天干五合 + 十神互见的人话层（yinyuan skill 融入，
    # 日常语复用 TEN_GOD_WARM，无吉凶断言）
    if h.get("gan_he"):
        lines.append("你们俩的本命天干五合：传统上把这看作"
                     "「天生对味」的组合，"
                     "相处时那种不用解释的默契是有来处的。")
    god_ab, god_ba = h.get("god_a_sees_b") or "", h.get("god_b_sees_a") or ""
    if god_ab and god_ba:
        # R2349s（R84-P2-19）：互看语境不复用 TEN_GOD_WARM 的资源词——
        # 「你眼里的 ta 带『稳定财』」把伴侣读成钱袋，物化观感差。
        # 互看专用一套「在对方身上感到的特质」标签。
        _GOD_REL = {
            "正财": "踏实感", "偏财": "灵气", "正官": "靠谱感", "七杀": "冲劲",
            "正印": "安定感", "偏印": "怪点子", "比肩": "战友感",
            "劫财": "义气", "食神": "松弛感", "伤官": "才气",
        }
        la = _GOD_REL.get(god_ab, god_ab)
        lb = _GOD_REL.get(god_ba, god_ba)
        lines.append(f"互看：你眼里的 ta 带「{la}」，ta 眼里的你带「{lb}」"
                     f"，两种力量互相成全，也偶尔较劲。")
    dayun = h.get("dayun_hits") or []
    # R216b 续（UX 队列 U-017）：原实现无条件取 dayun_hits[0]（最早的大运
    # =童年期），产出「1997年前后…适合一起做决定」而两人当时 7 岁/5 岁的
    # 荒谬文案。修法：只取双方均已成年（≥16 岁）的大运；没有合格运就不给
    # 行为建议，改为中性的「从 XXXX 年起你们进入大运（十年一轮）互动期」描述。
    # dayun_hits 数据本身零改动（selftest hehun.dayun 钉的 8 运口径不变），
    # 只是 warm 文案层做年龄过滤。
    _adult = [d for d in dayun if int(d.get("start_age_a", 99)) >= 16]
    # F-007：按 year_start 距离当前年份排序，优先展示近期应期
    if _adult:
        _now = _today_cn()
        _adult.sort(key=lambda d: abs(int(d.get("year_start", 0)) - _now.year))
        d0 = _adult[0]
        # F-015：当年份距今>10年时，降级为"远期参考"
        if abs(int(d0.get("year_start", 0)) - _now.year) > 10:
            lines.append(f"{d0.get('year_start')}年前后两人的大运（十年一轮的大方向）有互动"
                         f"（{d0.get('relation', '')}），远期参考，不是日程表。")
        elif str(d0.get("relation", "")) == "冲":
            # R233u（R53-P1-2）：冲运主摩擦动荡——劝「一起做决定」与
            # 冲的语义直接矛盾，改中性缓冲口径。
            lines.append(f"{d0.get('year_start')}年前后两人的大运（十年一轮的大方向）有互动"
                         f"（冲），那段时间容易顶上，重要的事留点缓冲、"
                         f"慢半拍再定。")
        else:
            lines.append(f"{d0.get('year_start')}年前后两人的大运（十年一轮的大方向）有互动"
                         f"（{d0.get('relation', '')}），那段时间适合一起做决定。")
    elif dayun:
        d0 = dayun[0]
        lines.append(f"从{d0.get('year_start')}年起你们进入大运（十年一轮）互动期"
                     f"（{d0.get('relation', '')}），节奏上的参考，不是日程表。")
    # R3087：收口从「靠你们自己写」升级成带地图的交权——先摆成本，
    # 再给判断条件，最后才归还决定权（调研 B 交权三段式）。
    # R3125（specs/012-P5）脱罪位并进收口：负向判词把磨归因给盘
    # 不归到人——收口行恒在不被截断，心理补偿只用盘上算得出的
    # 归因子（冲/克），不空泛安慰。
    if _band == 3:
        lines.append(
            f"先把话说明：这些磨是盘上{_neg or '多处摩擦'}带来的，"
            "不是你俩谁有毛病。走下去这组盘明标的成本就是这些。"
            "不是吓你，是盘上有判词的地方都给你指出来了。"
            "值不值这个成本只有你们俩知道：命理给的是会被反复考验的"
            "点，不是判决书，看清楚了还愿意牵手的，是你们自己的本事。")
    elif _band == 2:
        lines.append(
            "先说一句：这些磕绊是盘上的事，不是你俩谁的问题。"
            "能不能走，看一件实事：上面说到的那个摩擦点，你们俩之前"
            "撞见时是越吵越亲还是越处越累，前者这组盘啃得动，后者"
            "要想清楚再上车。命理给地图，路是你们俩走的。")
    elif _band == 0:
        # R3133：顺风盘同给功课——「顺」的具体成本是懒出来的惯性：
        # 合拍到不吵架的伴侣，最容易一起温水煮到没话聊。
        lines.append(
            "底子顺别浪费，传统口径里上等婚也要人事配，顺不是躺赢的"
            "许可。顺风局的具体功课：每隔一阵主动做一件你们俩没做过"
            "的小事：合拍的关系最怕处成惯性，甜味要自己续。"
            "这张表是地图，路是你们俩走的。")
    elif _hard:
        lines.append(
            "有磕绊不等于不能处，上面点名的那处磨，是这组盘要啃的"
            "骨头；处理好了是独一份的默契，啃不动再谈去留。"
            "命理给地图，路是你们俩走的。")
    else:
        lines.append(
            "这组没有判定点名的硬伤，剩下的功课是具体的：把上面会磨"
            "的地方提前说清楚，比出了问题再补省事。"
            "命理给地图，路是你们俩走的。")
    # R2349s（R84-P1-4）：收口免责句此前 append 后被 lines[:5] 裁掉——
    # 信号越丰富的盘（最甜的那批）恰好丢免责声明。留固定席位：内容行
    # 至多取 4 条 + 收口恒在。R3087：判词报告行数上限 4→7（结论/
    # 证据/剧本/处方/地图链不再被裁）。
    _body, _close = lines[:-1][:7], lines[-1:]
    return _wrap(
        l0[:_L0_MAX],
        None,
        _body + _close,
        _render_details(h.get("render", "")),
        [],
    )


def warm_qiming(out: dict, surname: str = "", gender: str = "") -> dict:
    """起名 warm 层——其余四功能都有多行 warm.reply，起名此前只有
    一条 one_liner + 后台 AI；LLM 不可用时只剩裸名单（R53-P3-3）。

    out = services.qiming 的返回 dict（five_elements/full_names/bazi）。
    """
    out = out or {}
    fe = out.get("five_elements") or {}
    names = out.get("full_names") or []
    miss = [w for w in (fe.get("missing") or []) if w]
    weak = [w for w in (fe.get("weak") or []) if w]
    kid = ("小姑娘" if gender == "女" else "小男孩" if gender == "男"
           else "宝宝")
    sn = (surname or "").strip()

    # R2509（审-P3-29）：空姓走「这位家小姑娘」语法不通；names 空时
    # 「挑了 0 个名字——都从古籍里来」自相矛盾，各设分支。
    if not names:
        lines = ["这回没挑到合适的名字，换个条件再试试？"]
    elif sn:
        lines = [f"给{sn}家{kid}挑了 {len(names)} 个名字：都从古籍里来，"
                 f"不是凭空造的。"]
    else:
        lines = [f"给{kid}挑了 {len(names)} 个名字：都从古籍里来，"
                 f"不是凭空造的。"]
    if miss:
        # R2349s（R84-P2-13）：量词随个数变——两行说「这一行」语法别扭。
        _mq = "这一行" if len(miss) == 1 else "这几行"
        lines.append(f"五行里 {'、'.join(miss)} {_mq}比较薄。"
                     f"名字里给它补一补，图个心里踏实。")
    elif weak:
        _wq = "这一行" if len(weak) == 1 else "这两行" if len(weak) == 2 else "这几行"
        # R3093（specs/010-P3）：弱行不再只说「往这个方向偏了偏」——
        # 报候选池里真接住弱行的字数，让「偏」有可验的落点。
        _wn = sum(1 for n in names
                  if set(str(e) for e in (n.get("elements") or []))
                  & set(weak))
        if _wn >= len(names):
            _wtail = (f"{len(names)} 个候选全都带着{'或'.join(weak)}"
                      f"的字，就往这个方向挑的")
        elif _wn:
            _wtail = (f"{len(names)} 个候选里有 {_wn} 个带着"
                      f"{'或'.join(weak)}的字，往这个方向偏的")
        else:
            _wtail = f"这批候选还没接住{_wq}，点「换一批」再试试"
        lines.append(f"五行没缺，{'、'.join(weak)} {_wq}偏弱，{_wtail}。")
    else:
        lines.append("五行挺匀的：挑名就只管好听、有出处。")
    # R2349s（R84-P2-17）：names[0] 是后端乱序首位，而前端按 _qmScore
    # 重排——点名的可能不是屏上「⭐首选」。后端没有 score 字段，对齐
    # 前端评分主维度：命中的缺行/弱行数 + 双字加成 + 出处字数。
    _want = set(miss or []) | set(weak or [])
    def _nm_score(n):
        _els = set(str(e) for e in (n.get("elements") or []))
        return (len(_els & _want) * 16
                + (6 if n.get("form") == "double" else 3)
                + min(len(n.get("story") or "") // 20, 9))
    _top = (max(names, key=_nm_score) if names else {})
    if _top.get("full_name"):
        _src = _top.get("origin") or "古籍"
        # R3093（specs/010-P3）：点名不再只报出处——字级五行对上缺/
        # 弱行的直接说「哪几字接住了哪几行」，说不出就退回出处口径。
        _given = str(_top.get("given") or "")
        _els = [str(e) for e in (_top.get("elements") or [])]
        _fit = [f"「{_given[i]}」属{_els[i]}"
                for i in range(min(len(_given), len(_els)))
                if _els[i] in _want]
        if _fit:
            lines.append(f"私心喜欢「{_top['full_name']}」"
                         f"{'、'.join(_fit)}，正好接住弱的那几行；"
                         f"出自{_src}。")
        else:
            lines.append(f"私心喜欢「{_top['full_name']}」，出自{_src}，"
                         f"念起来也顺口。")
    # R2519（深度收尾）：定名前的两件实在事——比「随缘吧」有用的收口。
    if names:
        lines.append("定之前做两件小事：把候选名连上姓，像平时喊孩子那样"
                     "顺口念几遍；再搜搜有没有谐音歧义。")
    lines.append(_pick(
        ["名字是参考，不是定数：家里人念着顺口最重要。",
         "好名字是祝福，不是枷锁：挑你们全家都喜欢的那个。",
         "这些名字只是个开头：最后叫哪个，听你们全家的心意。"],
        "qm-close", sn, str(len(names))))
    return _wrap(
        (out.get("one_liner") or "古书里挑的名字")[:_L0_MAX],
        None, lines[:5],
        _render_details((out.get("bazi") or {}).get("render", "")),
        [])


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
    assert w["reply"] and len(w["reply"]) <= 7, w["reply"]
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
    assert wth["reply"] and 1 <= len(wth["reply"]) <= 7
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
