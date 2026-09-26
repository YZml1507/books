"""interpreter — 确定性解读层（取代 llm_reader，零成本、零网络、可核验）。

替换背景（2026-08-19，用户决策）：LLM 接入成本高且引入网络依赖与不可复现
输出，本模块以**规则模板 + 语料引文**替代它。与 llm_reader 的根本差别：

  * llm_reader：把坐标事实喂给远端模型，输出**生成文本**——不可复现、
    有成本、可能编造引文（G2 存在的原因）。
  * interpreter：只做两件事——(1) 把 bazi_calc/liuyao 已算好的结构化事实
    按写死的模板转述为白话；(2) 把检索到的古籍原文按出处并列。
    **不新增任何事实**，每句话都能回指到一个 calc 字段或一条引文。

红线遵守：
  * 输出是**转述**不是生成：模板文字写死在本模块，事实全部来自入参。
    宪法 III「绝对不可入库的一类内容：生成文本」不受影响——本模块输出
    与 llm 输出一样只在响应里返回，落 history.db（D-039 已授权），
    不进 corpus.db / knowledge.db，不参与检索。
  * 不作吉凶断言式的现实决策建议（不给医疗/投资/法律建议）。
    「宜/忌」只转述黄历坐标与五行强弱，措辞固定。
  * 纯函数、无 IO、无网络、无随机：同输入必同输出（可复验）。

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe -m guji.interpreter        # 本模块自测
    .\\.venv\\Scripts\\python.exe web\\selftest.py           # web 层端到端
"""
from __future__ import annotations

from datetime import datetime


# R233g（R44-P0-1）：生死/重病类敏感问法——不能走话题兜底（会被当
# 格式错吐黑话），也不能交给判词背书。确定性转介，语气放稳。
# R233r（R49-Top5-3）：词表与聊天层同源（llm_polish._is_sensitive）——
# 此前两表漂移：这边多「寿命/要死了/病死」，那边多「存活率/晚期」，
# 同一个问法过不同闸门宽严不一。软词排除表（多肉会不会死）也一并共享。
_SENSITIVE_LINE = ("这个话题盘面真答不了，也不该靠它拿主意——"
                   "身体或心里难受的话，找医生、找信得过的人聊聊才是正路，"
                   "小满陪你说点别的也行。")

# 本模块唯一的"事实来源"是入参；下面这些表是**术语解释表**，
# 只是翻译表——把命理术语转成白话，不改变任何计算结果。（R219b P1-4：去套话）

# 十神白话（《三命通会》《渊海子平》通行释义的中性转述，不含吉凶断言）
TEN_GOD_PLAIN = {
    "比肩": "同类相助，行事有同伴同行，也易与人比较",
    "劫财": "同类相争，人际往来密集，财物易共享或分摊",
    "食神": "温和的表达与享受，偏向平稳输出",
    "伤官": "锋利的表达与创造，偏向突破既有框架",
    "偏财": "流动的财，来源多元而不固定",
    "正财": "稳定的财，来源固定可积累",
    "七杀": "外来的压力与约束，推动力强而紧迫",
    "正官": "秩序与责任，偏向规范内行事",
    "偏印": "偏门的学习与直觉，思路独特",
    "正印": "正统的学习与庇护，偏向稳步积累",
}

# 五行白话（性质转述，不含吉凶）
ELEMENT_PLAIN = {
    "木": "生长、舒展、条理",
    "火": "明亮、外显、热度",
    "土": "承载、稳定、厚重",
    "金": "收敛、决断、规整",
    "水": "流动、智巧、渗透",
}

# 五行相生相克（用于"补缺"的方向说明）
ELEMENT_GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 地支关系白话（中性描述关系强度，不断吉凶）
RELATION_PLAIN = {
    "六冲": "两支正对，主变动、位移，节奏易被打断",
    "相害": "两支暗损，多为细碎摩擦而非大事",
    "相刑": "两支相扰，事情容易反复、需要返工",
    "自刑": "同支自扰，内部消耗多于外部阻力",
    "六合": "两支相合，事情容易牵连成事、有人配合",
    "三合": "三支成局，力量集中于一个五行方向",
    "半合": "两支半成局，方向已现但力量未满",
    "相生": "一方助另一方，能量顺向传递",
}

# R2530（调研-因果层）：柱位人生域——「年支巳 × 日支寅」点出了谁，
# 再补一句这些位置各自管什么，关系才落到生活面上。
_POS_DOMAIN = {
    "年": "早年",
    "月": "父母/青年环境",
    "日": "自己/婚姻",
    "时": "子女/将来",
}


def _pillar_domain(a: str, b: str) -> str:
    """「年支巳」「时支丑」→ 各柱人生域白话；聚合条目（四柱/地支）返回 ''。"""
    da = _POS_DOMAIN.get((a or "")[:1])
    db = _POS_DOMAIN.get((b or "")[:1])
    if not da or not db:
        return ""
    return f"牵动{da}与{db}"

_DISCLAIMER = ("以上为系统按写死规则对运算坐标的转述，非生成文本、"
               "非现实决策依据；古籍原文以引文出处为准。")


def _fmt_num(x: float) -> str:
    """0.3 -> '0.3'；2.0 -> '2'（避免展示 '2.0' 这种噪音）。"""
    return str(int(x)) if float(x) == int(x) else f"{float(x):g}"


# ---------------------------------------------------------------------------
# 八字解读
# ---------------------------------------------------------------------------
def interpret_bazi(paipan: dict, calc: dict,
                   evidence: list[dict] | None = None,
                   question: str | None = None) -> dict:
    """八字坐标 + 运算事实 -> 结构化白话解读（纯函数）。

    paipan: {"render", "nayin", "warn"}（web/app.py 的 paipan_out）
    calc:   bazi_calc.calc/calc_life/calc_range 的输出
    返回 {"ok", "kind", "sections":[{"title","lines":[...]}], "citations":[...],
          "text", "basis", "disclaimer"}
    text 为 markdown 全文（前端可直接渲染），sections 供结构化展示。
    """
    calc = calc or {}
    paipan = paipan or {}
    sections: list[dict] = []
    basis: list[str] = []          # 每条结论对应的 calc 字段（可核验）

    # ── 1. 四柱与日主 ──
    render = paipan.get("render") or ""
    head: list[str] = []
    if render:
        head.append(f"四柱：{render}")
    nayin = paipan.get("nayin") or []
    if nayin:
        head.append("纳音：" + " · ".join(str(n) for n in nayin))
    scope = calc.get("scope") or "day"
    if head:
        sections.append({"title": "排盘坐标", "lines": head})
        basis.append("paipan.render / paipan.nayin")

    # ── 2. 五行分布（强弱与缺行，全部来自 five_elements）──
    fe = calc.get("five_elements") or {}
    counts = fe.get("counts") or {}
    strong = fe.get("strong") or []
    missing = fe.get("missing") or []
    if counts:
        lines = ["分布：" + "、".join(f"{k}{_fmt_num(v)}" for k, v in counts.items())]
        if strong:
            for s in strong:
                lines.append(f"{s}偏旺——{ELEMENT_PLAIN.get(s, '')}的一面比较突出，"
                             f"用力过头时容易失衡")
        _tied = fe.get("strong_tied") or []
        if not strong and _tied:
            lines.append(f"{'、'.join(_tied)}并列最高——几股劲相当，没有一行独大")
        if missing:
            for m in missing:
                # R230a-7（R13-P0-1）：补缺走「生我」方向（缺木→补水，水生木），
                # 此前用 ELEMENT_GENERATES（我生，即泄耗方向）恰好说反。
                helper = {v: k for k, v in ELEMENT_GENERATES.items()}.get(m)
                tip = f"，可从{helper}的方向补" if helper else ""
                lines.append(f"缺{m}——{ELEMENT_PLAIN.get(m, '')}的一面偏弱{tip}")
        if not strong and not _tied and not missing:
            lines.append("五行齐全且无一行独旺，整体偏均衡")
        sections.append({"title": "五行强弱", "lines": lines})
        basis.append("calc.five_elements.counts/strong/missing")

    # ── 3. 十神（逐柱转述，basis 由 bazi_calc 提供）──
    tg = calc.get("ten_gods") or []
    if tg:
        lines = []
        for t in tg:
            god = t.get("god") or ""
            plain = TEN_GOD_PLAIN.get(god, "")
            pos = t.get("pos") or ""
            gan = t.get("gan") or ""
            # R230a-7（R13-P3-3）：日主不派十神（惯例）——「日干X → 比肩」
            # 换成「日主（自我）」标注，不显外行。
            if pos == "日干":
                seg = f"{pos}{gan} → 日主（自我）"
            else:
                seg = f"{pos}{gan} → {god}"
            if plain and pos != "日干":
                seg += f"：{plain}"
            if t.get("basis") and pos != "日干":
                seg += f"（依据：{t['basis']}）"
            lines.append(seg)
        sections.append({"title": "十神格局", "lines": lines})
        basis.append("calc.ten_gods[].god/basis")

    # ── 4. 四柱地支关系 ──
    rels = calc.get("relations") or []
    if rels:
        lines = []
        for r in rels:
            t = r.get("type") or ""
            note = r.get("note") or ""
            plain = RELATION_PLAIN.get(t, "")
            a, b = r.get("a") or "", r.get("b") or ""
            seg = f"{t}"
            if a and b:
                seg += f"（{a} × {b}）"
            if note:
                seg += f"：{note}"
            dom = _pillar_domain(a, b)
            if dom:
                seg += f"，{dom}"
            if plain:
                seg += f"——{plain}"
            lines.append(seg)
        sections.append({"title": "地支关系", "lines": lines})
        basis.append("calc.relations[].type/note")

    # ── 5. 按 scope 分支：单日流日 / 范围 / 生平大运 ──
    if scope == "day":
        dl = calc.get("day_luck") or {}
        lines = []
        if dl.get("day_ganzhi"):
            lines.append(f"今日 {dl['day_ganzhi']}：{dl.get('day_master_rel', '')}")
        for r in dl.get("day_branch_rels") or []:
            plain = RELATION_PLAIN.get(r.get("type") or "", "")
            seg = f"{r.get('pos', '')} {r.get('type', '')}（{r.get('note', '')}）"
            pos_dom = _POS_DOMAIN.get((r.get("pos") or "")[:1], "")
            if pos_dom:
                seg += f"——今天碰到的这一宫管{pos_dom}"
            if plain:
                seg += f"——{plain}"
            lines.append(seg)
        if dl.get("hour_ganzhi"):
            lines.append(f"流时 {dl['hour_ganzhi']}：{dl.get('hour_master_rel', '')}")
        for r in dl.get("hour_branch_rels") or []:
            plain = RELATION_PLAIN.get(r.get("type") or "", "")
            seg = f"时 {r.get('pos', '')} {r.get('type', '')}（{r.get('note', '')}）"
            if plain:
                seg += f"——{plain}"
            lines.append(seg)
        if not (dl.get("day_branch_rels") or dl.get("hour_branch_rels")):
            lines.append("与四柱地支无冲合刑害，这一天偏平稳")
        if lines:
            sections.append({"title": "流日流时", "lines": lines})
            basis.append("calc.day_luck.*")
    elif scope == "range":
        days = calc.get("days") or []
        lines = [f"范围 {calc.get('start', '')} ~ {calc.get('end', '')}，共 {len(days)} 天"]
        for d in days:
            # R2530（调研-因果层）：只报「六冲」不知道冲了谁——带上被碰
            # 的柱位与该宫管什么（与流日段的 _POS_DOMAIN 同口径）。
            marks = []
            for r in (d.get("day_branch_rels") or []):
                seg = f"{r.get('type', '')}·{r.get('pos', '')}"
                dom = _POS_DOMAIN.get((r.get("pos") or "")[:1], "")
                if dom:
                    seg += f"({dom})"
                marks.append(seg)
            tag = "、".join(marks) if marks else "无冲合"
            lines.append(f"{d.get('date', '')} {d.get('day_ganzhi', '')}："
                         f"{d.get('day_master_rel', '')}；{tag}")
        sections.append({"title": "逐日流日", "lines": lines})
        basis.append("calc.days[].day_ganzhi/day_branch_rels")
    elif scope == "life":
        dayun = calc.get("dayun") or []
        lines = []
        if calc.get("qi_yun_age") is not None:
            lines.append(f"约 {_fmt_num(calc['qi_yun_age'])} 岁起运")
        # R2529（调研-因果层）：大运=十年气候、流年是逐年天气——先给
        # 框架再给表，并标出「眼下」那一步（用户最常问的就是不知道
        # 自己在哪一步）。眼下步按当前公历年落在哪段判定，确定性。
        _now_y = datetime.now().year
        _cur_idx = next(
            (d.get("index") for d in dayun
             if isinstance(d.get("year_start"), int)
             and d["year_start"] <= _now_y < d["year_start"] + 10),
            None)
        if _cur_idx is not None:
            lines.append("大运是十年的气候——你眼下走的那一步在下面标了"
                         "「←眼下」，每年的流年在这个底色上做加减")
        for d in dayun:
            god = d.get("gan_rel") or ""
            plain = TEN_GOD_PLAIN.get(god, "")
            seg = (f"第 {d.get('index', '')} 运 {d.get('pillar', '')}"
                   f"（{_fmt_num(d.get('start_age', 0))}~{_fmt_num(d.get('end_age', 0))} 岁，"
                   f"约 {d.get('year_start', '')} 年起）：{god}")
            if plain:
                seg += f"——{plain}"
            if d.get("index") == _cur_idx:
                seg += "　←眼下"
            lines.append(seg)
        if lines:
            sections.append({"title": "大运走势", "lines": lines})
            basis.append("calc.dayun[].pillar/gan_rel")

    # ── 6. 提问回应（只把问题对齐到已有坐标，不新增结论）──
    q = (question or "").strip()
    if q:
        focus = _focus_lines(q, calc)
        sections.append({"title": f"针对「{q}」", "lines": focus})
        basis.append("question × calc（坐标对齐，未新增事实）")

    # ── 7. 古籍引文（原文并列，出处由服务端渲染）──
    citations = _citations(evidence or [])

    if calc.get("summary"):
        sections.append({"title": "运算摘要（原样）", "lines": [calc["summary"]]})
        basis.append("calc.summary")

    return {
        "ok": bool(sections),
        "kind": "rule-based",
        "engine": "guji.interpreter/1.0（确定性规则，无 LLM）",
        "sections": sections,
        "citations": citations,
        "text": _to_markdown(sections, citations),
        "basis": basis,
        "disclaimer": _DISCLAIMER,
    }


# 问题关键词 → 关注的坐标维度（写死映射，避免"猜用户意图"）
_TOPIC_MAP = (
    ("事业", ("正官", "七杀"), "官杀"),
    ("工作", ("正官", "七杀"), "官杀"),
    ("升职", ("正官", "七杀"), "官杀"),
    # R2533（受众口语）：15-25 的真实问法是「实习/面试/offer」
    # 不是「事业」——同一组官杀目标，口语词补齐。
    ("实习", ("正官", "七杀"), "官杀"),
    ("面试", ("正官", "七杀"), "官杀"),
    ("offer", ("正官", "七杀"), "官杀"),
    ("跳槽", ("正官", "七杀"), "官杀"),
    ("辞职", ("正官", "七杀"), "官杀"),
    ("离职", ("正官", "七杀"), "官杀"),
    ("入职", ("正官", "七杀"), "官杀"),
    ("加班", ("正官", "七杀"), "官杀"),
    ("财", ("正财", "偏财"), "财星"),
    ("钱", ("正财", "偏财"), "财星"),
    ("投资", ("正财", "偏财"), "财星"),
    ("工资", ("正财", "偏财"), "财星"),
    ("副业", ("正财", "偏财"), "财星"),
    ("兼职", ("正财", "偏财"), "财星"),
    ("存款", ("正财", "偏财"), "财星"),
    ("收入", ("正财", "偏财"), "财星"),
    # 感情类：多字词必须先于「朋友」——「男朋友」含子串「朋友」。
    ("感情", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("婚", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("桃花", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("恋爱", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("男朋友", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("女朋友", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("男友", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("女友", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("分手", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("暗恋", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("暧昧", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("脱单", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("crush", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("前任", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("复合", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("异地", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("网恋", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    ("恋", ("正财", "偏财", "正官", "七杀"), "夫妻星"),
    # 同辈/人际——比劫是同辈与竞争者（室友/闺蜜/同事纠纷走这里）。
    ("室友", ("比肩", "劫财"), "同辈星"),
    ("宿舍", ("比肩", "劫财"), "同辈星"),
    ("闺蜜", ("比肩", "劫财"), "同辈星"),
    ("朋友", ("比肩", "劫财"), "同辈星"),
    ("人缘", ("比肩", "劫财"), "同辈星"),
    ("社交", ("比肩", "劫财"), "同辈星"),
    ("同事", ("比肩", "劫财"), "同辈星"),
    # 长辈/家庭——印星主长辈庇护与学业（两用共一组目标）。
    ("父母", ("正印", "偏印"), "印星"),
    ("妈妈", ("正印", "偏印"), "印星"),
    ("爸爸", ("正印", "偏印"), "印星"),
    ("家人", ("正印", "偏印"), "印星"),
    ("家庭", ("正印", "偏印"), "印星"),
    ("学", ("正印", "偏印"), "印星"),
    ("考试", ("正印", "偏印"), "印星"),
    ("读书", ("正印", "偏印"), "印星"),
    ("考研", ("正印", "偏印"), "印星"),
    ("期末", ("正印", "偏印"), "印星"),
    ("论文", ("正印", "偏印"), "印星"),
    ("毕业", ("正印", "偏印"), "印星"),
    # R2533 续：「考」不能裸加——「考虑」是日常词会劫持问句到印星；
    # 只收具体考试名。上岸按语境两侧都沾，归印星（考试运）。
    ("考公", ("正印", "偏印"), "印星"),
    ("考编", ("正印", "偏印"), "印星"),
    ("上岸", ("正印", "偏印"), "印星"),
    ("健康", (), "五行均衡"),
    ("身体", (), "五行均衡"),
    ("失眠", (), "五行均衡"),
    ("睡眠", (), "五行均衡"),
    ("姨妈", (), "五行均衡"),
)


def _focus_lines(q: str, calc: dict) -> list[str]:
    """把用户问题对齐到已算出的坐标，只做筛选与转述，不新增判断。"""
    tg = calc.get("ten_gods") or []
    gods = [t.get("god") for t in tg]
    # R233g（R44-P0-1）：敏感问法优先拦截——此前落空吐「坐标维度」黑话。
    # R233r：与聊天层同一判定（lazy import 与 voice.py:1090 同款）。
    from guji import llm_polish as _lp
    if _lp._is_sensitive(q):
        return [_SENSITIVE_LINE]
    for kw, targets, label in _TOPIC_MAP:
        if kw not in q:
            continue
        if not targets:                      # 健康类：看五行均衡
            fe = calc.get("five_elements") or {}
            strong, missing = fe.get("strong") or [], fe.get("missing") or []
            if strong or missing:
                return [f"{label}相关：" +
                        "；".join(filter(None, [
                            ("偏旺 " + "、".join(strong)) if strong else "",
                            ("偏弱/缺 " + "、".join(missing)) if missing else "",
                        ])) + "——失衡处就是要留意的地方"]   # R219b（P1-4）：去套话
            return [f"{label}相关：五行分布无明显偏旺或缺行"]
        hit = [t for t in tg if t.get("god") in targets]
        if hit:
            def _hit_seg(t):
                # R2530（调研-因果层）：不止报「在哪」，还说「这个位置
                # 管什么」——pos 首字即四柱位（年/月/日/时）。
                dom = _POS_DOMAIN.get((t.get("pos") or "")[:1], "")
                g = f"{t.get('pos', '')}{t.get('gan', '')}({t.get('god', '')}"
                return g + (f"，这宫管{dom}" if dom else "") + ")"
            return [f"{label}出现在：" + "、".join(_hit_seg(t) for t in hit)
                    + f"——{label}现于盘中，相关事项在四柱里有着落点"]
        # R2529：括号列的是「想看谁」targets 不是「盘里有谁」gods——
        # life scope 无 ten_gods 时 gods 全空渲染成裸「（）」。
        _tg = "、".join(str(g) for g in targets if g)
        return [f"{label}未现于四柱天干" + (f"（想看的是{_tg}）" if _tg else "")
                + "——本盘这一维线索偏少，不作推测"]
    return ["这个问题盘面没有对应的维度——感情、工作、学习、财运、"
            "身体节奏这些能聊，要不换个问法试试？"]


def _citations(evidence: list[dict]) -> list[dict]:
    """把证据对象渲染成引文（出处由服务端从字段拼装，绝不由模型产生）。"""
    out = []
    for e in evidence[:12]:
        wid = e.get("work_id") or ""
        book = e.get("title") or wid
        cite = e.get("citation")
        if not cite:
            page_raw = e.get("page_anchor") or ""
            page = page_raw.replace(f"{wid}_", "", 1) if page_raw else ""
            cite = f"《{book}》{e.get('layer') or ''}" + (f" @{page}" if page else "")
        out.append({
            "citation": cite,
            "text": (e.get("text") or "")[:220],
            "work_id": wid,
            "layer": e.get("layer") or "",
            "why": e.get("why") or "",
        })
    return out


def _to_markdown(sections: list[dict], citations: list[dict]) -> str:
    parts = []
    for s in sections:
        parts.append(f"## {s['title']}")
        parts.extend(f"- {ln}" for ln in s["lines"] if ln)
    if citations:
        parts.append("## 古籍原文依据")
        for c in citations:
            parts.append(f"- **{c['citation']}**：{c['text']}")
    parts.append("")
    parts.append(_DISCLAIMER)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 六爻解读
# ---------------------------------------------------------------------------
def interpret_liuyao(ben: dict, bian: dict, moving_lines: list,
                     jing: list[dict] | None = None,
                     question: str | None = None) -> dict:
    """六爻卦象 -> 白话转述 + 卦爻辞引文（纯函数，不新增卦义）。

    ben/bian: liuyao.render_hexagram 的输出（label/gua_number/gua_name/lines/...）
    jing:     本卦/变卦的經文引文（_hit_dict 列表）
    """
    ben, bian = ben or {}, bian or {}
    sections: list[dict] = []
    basis: list[str] = []

    core = [f"本卦：{ben.get('gua_name', '')}（第 {ben.get('gua_number', '')} 卦）"]
    if bian.get("gua_name"):
        core.append(f"变卦：{bian.get('gua_name', '')}（第 {bian.get('gua_number', '')} 卦）")
    sections.append({"title": "卦象坐标", "lines": core})
    basis.append("liuyao.render_hexagram(ben/bian).gua_name/gua_number")

    ml = list(moving_lines or [])
    if ml:
        pos_names = ["初", "二", "三", "四", "五", "上"]
        named = [pos_names[i - 1] if isinstance(i, int) and 1 <= i <= 6 else str(i)
                 for i in ml]
        lines = [f"动爻：{('、'.join(named))}爻（共 {len(ml)} 个）",
                 "动爻是变化发生的位置——本卦为当下，变卦为动爻变化后的去向"]
        if len(ml) >= 3:
            lines.append("动爻较多，所问之事变数偏大，宜看整体趋向而非单爻")
    else:
        lines = ["无动爻（静卦）：所问之事当下格局稳定，变化动力不明显"]
    sections.append({"title": "动爻", "lines": lines})
    basis.append("liuyao ben.moving_lines")

    if ben.get("gua_name") and bian.get("gua_name"):
        if ben["gua_name"] == bian["gua_name"]:
            sections.append({"title": "走向", "lines": ["本卦与变卦相同，方向不改"]})
        else:
            sections.append({"title": "走向", "lines": [
                f"由 {ben['gua_name']} 转向 {bian['gua_name']}——"
                f"这是卦象给出的变化方向，卦义请以下方經文原文为准"]})
        basis.append("ben.gua_name vs bian.gua_name")

    q = (question or "").strip()
    if q:
        sections.append({"title": f"针对「{q}」", "lines": [
            "系统只给卦象坐标与經文原文，不代为断事——"
            "请据下方卦爻辞原文对照所问（G7：无证据不推测）"]})

    citations = _citations(jing or [])
    return {
        "ok": True,
        "kind": "rule-based",
        "engine": "guji.interpreter/1.0（确定性规则，无 LLM）",
        "sections": sections,
        "citations": citations,
        "text": _to_markdown(sections, citations),
        "basis": basis,
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# 塔罗解读
# ---------------------------------------------------------------------------
def interpret_tarot(cards: list[dict], question: str | None = None) -> dict:
    """塔罗抽牌 -> 关键词转述（纯函数）。

    cards: [{name, upright(bool), upright_kw, reversed_kw, meaning, position}]
    只转述 tarot.py 写死的象征关键词，不作吉凶断言、不作现实建议。
    """
    cards = cards or []
    sections: list[dict] = []
    for c in cards:
        up = bool(c.get("upright"))
        kw = c.get("upright_kw") if up else c.get("reversed_kw")
        lines = [f"{'正位' if up else '逆位'}：{kw or ''}"]
        if c.get("meaning"):
            lines.append(f"象征：{c['meaning']}")
        title = c.get("name") or "牌"
        if c.get("position"):
            title = f"{c['position']} · {title}"
        sections.append({"title": title, "lines": lines})

    if len(cards) > 1:
        ups = sum(1 for c in cards if c.get("upright"))
        sections.append({"title": "牌面统计", "lines": [
            f"共 {len(cards)} 张，正位 {ups} 张、逆位 {len(cards) - ups} 张",
            "正逆位比例只是牌面事实，不构成结论"]})

    q = (question or "").strip()
    if q:
        sections.append({"title": f"针对「{q}」", "lines": [
            "以上为牌面象征关键词的转述；如何对应所问由你自己判断，"
            "系统不代为断事"]})

    return {
        "ok": bool(sections),
        "kind": "rule-based",
        "engine": "guji.interpreter/1.0（确定性规则，无 LLM）",
        "sections": sections,
        "citations": [],
        "text": _to_markdown(sections, []),
        "basis": ["tarot.draw[].name/upright/upright_kw/reversed_kw/meaning"],
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# 研究综合（取代 llm_reader.interpret_research）
# ---------------------------------------------------------------------------
def interpret_research(question: str, evidence: list[dict],
                       comparisons: list[dict] | None = None) -> dict:
    """研究问题 + 语料证据 -> 结构化综合（纯函数，不新增论断）。

    与 llm_reader.interpret_research 的差别：不做"白话综合"（那需要生成），
    而是做**可核验的聚合**——按书/层统计命中、并列原文、列出同址分歧。
    这正是 G2/G7 要的：结论只能是"语料里有什么"，不是"模型认为什么"。
    """
    evidence = evidence or []
    sections: list[dict] = []
    basis: list[str] = []

    if not evidence:
        return {
            "ok": False,
            "kind": "rule-based",
            "engine": "guji.interpreter/1.0（确定性规则，无 LLM）",
            "sections": [{"title": "证据不足", "lines": [
                f"「{question}」在当前语料没检索到能对上的原文——"
                "不作推测"]}],
            "citations": [],
            "text": f"## 证据不足\n- 「{question}」在当前语料没检索到能对上的原文，"
                    f"不作推测。\n\n{_DISCLAIMER}",
            "basis": ["evidence 为空"],
            "disclaimer": _DISCLAIMER,
        }

    by_work: dict[str, list[dict]] = {}
    by_layer: dict[str, int] = {}
    for e in evidence:
        key = e.get("title") or e.get("work_id") or "?"
        by_work.setdefault(key, []).append(e)
        # R2349j（R71-P2）：缺键兜底 misc 是技术词——界面会显示「misc N」。
        lay = e.get("layer") or "其他"
        by_layer[lay] = by_layer.get(lay, 0) + 1

    sections.append({"title": "命中概览", "lines": [
        f"「{question}」在 {len(by_work)} 部书中命中 {len(evidence)} 条原文",
        "按层分布：" + "、".join(f"{k} {v}" for k, v in
                             sorted(by_layer.items(), key=lambda kv: -kv[1])),
        "书目：" + "、".join(f"《{w}》{len(v)}条" for w, v in by_work.items()),
    ]})
    basis.append("evidence[].work_id/title/layer 聚合计数")

    if comparisons:
        lines = []
        for cmp in comparisons[:6]:
            addr = cmp.get("addr") or ""
            fs = cmp.get("findings") or []
            if not fs:
                continue
            lines.append(f"{addr}：{len(fs)} 处版本差异")
            for f in fs[:3]:
                lines.append(f"　· {f.get('line') or f.get('note') or ''}")
        if lines:
            lines.append("同址多见证处的差异即注家/版本分歧所在，系统并列不裁决")
            sections.append({"title": "同址版本分歧", "lines": lines})
            basis.append("comparisons[].findings[].line")

    citations = _citations(evidence)
    return {
        "ok": True,
        "kind": "rule-based",
        "engine": "guji.interpreter/1.0（确定性规则，无 LLM）",
        "sections": sections,
        "citations": citations,
        "text": _to_markdown(sections, citations),
        "basis": basis,
        "disclaimer": _DISCLAIMER,
    }


def available() -> bool:
    """兼容旧调用点：确定性解读器永远可用（无需 key、无需网络）。"""
    return True


def configured_model() -> str:
    """兼容旧调用点：返回引擎标识而非模型名（无外部模型）。"""
    return "guji.interpreter/1.0（本地规则，无 LLM）"


if __name__ == "__main__":  # 自测：固定输入 → 固定输出（可复验）
    import os
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from guji.bazi import compute
    from guji.bazi_calc import calc, calc_life, calc_range

    b = compute(1990, 5, 15, 10, "男")
    paipan = {"render": b.render(), "nayin": b.nayin, "warn": b.warn}

    c = calc(b, ask_date="2026-08-19", ask_hour=10)
    c["scope"] = "day"
    out = interpret_bazi(paipan, c, [], "事业运如何？")
    assert out["ok"] and out["sections"], out
    titles = [s["title"] for s in out["sections"]]
    assert "五行强弱" in titles and "十神格局" in titles, titles
    assert "针对「事业运如何？」" in titles, titles
    assert out["text"].startswith("## 排盘坐标"), out["text"][:60]
    # 确定性：同输入必同输出
    assert interpret_bazi(paipan, c, [], "事业运如何？")["text"] == out["text"]

    cl = calc_life(b, 1990)
    cl["scope"] = "life"
    lo = interpret_bazi(paipan, cl, [])
    assert any(s["title"] == "大运走势" for s in lo["sections"]), lo

    cr = calc_range(b, "2026-08-19", "2026-08-21", 10)
    cr["scope"] = "range"
    ro = interpret_bazi(paipan, cr, [])
    assert any(s["title"] == "逐日流日" for s in ro["sections"]), ro

    lyo = interpret_liuyao({"gua_name": "师", "gua_number": 7},
                           {"gua_name": "坤", "gua_number": 2}, [2], [])
    assert lyo["ok"] and any("动爻" == s["title"] for s in lyo["sections"]), lyo

    to = interpret_tarot([{"name": "节制", "upright": True, "upright_kw": "调和",
                           "meaning": "象征调和", "position": "现在"}], "今天如何")
    assert to["ok"] and to["sections"][0]["title"] == "现在 · 节制", to

    ro2 = interpret_research("無為", [{"work_id": "KR5c0057", "title": "老子",
                                      "layer": "經", "text": "無為而無不為",
                                      "citation": "《老子》經"}])
    assert ro2["ok"] and ro2["citations"], ro2
    ro3 = interpret_research("無為", [])
    assert ro3["ok"] is False and "证据不足" in ro3["text"], ro3

    print("interpreter self-test PASS (bazi day/life/range, liuyao, tarot, research)")
