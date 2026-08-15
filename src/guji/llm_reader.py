"""llm_reader — LLM 辅助解读层（生成式，用户已授权；边界见下）。

把 bazi 坐标 + 检索到的命理书原文证据作为 context，调用大模型 chat API
生成一段白话解读。硬边界（用户授权时明确，GOAL §5 的生成文本红线由此豁免）：

  1. 不落库：返回的解读只是进程内字符串，绝不写入 corpus.db / knowledge.db，
     也不缓存到磁盘——每一次都是即时请求。
  2. 与引用分离：输出明确分两段——「原文证据」（古籍引文，可核验）与
     「LLM 解读」（生成文本，标注模型名）。解读必须基于给定的引文，不得
     编造引文里没有的内容（对齐 G7 语义）。
  3. KEY 从环境变量读，绝不进对话/命令行/日志。

配置（二选一，配置文件优先）：
  1. 项目根 llm_config.json（推荐）：复制 llm_config.example.json 为
     llm_config.json 后填写 base_url / api_key / model。该文件已被
     .gitignore，不会提交（KEY 只在你的本地文件里）。
  2. 环境变量：
       LLM_API_KEY    必填。OpenAI 兼容 API 的密钥。
       LLM_BASE_URL   可选，默认 https://api.openai.com/v1（DeepSeek/通义等
                      兼容服务填各自 base，如 https://api.deepseek.com/v1）。
       LLM_MODEL      可选，默认 gpt-4o-mini（按服务可用模型改）。
       LLM_TIMEOUT    可选，秒，默认 300。注意：实测该兼容服务推理较慢
                      （最小请求 50 tokens 约 29s），完整解读请给足超时。

依赖 httpx（已在 venv，sentence-transformers 的传递依赖），不新增。
"""
from __future__ import annotations

import json
import os

import httpx

DEFAULT_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "llm_config.json",
)

SYSTEM_PROMPT = (
    "你是古籍命理资料的研究助理。用户会给你：一个人的生辰八字坐标、"
    "由系统计算出的结构化运算事实（十神/五行/冲合刑害/流日流时），以及从"
    "命理古籍（三命通會、星學大成、李虛中命書等）检索到的原文引文。\n"
    "规则：\n"
    "1. 第一段必须是结论：用 1-3 句、口语化的大白话，直接回答用户问的运势"
    "问题（如'今天运势如何'），先给出明确判断（如'今天整体平顺/偏动荡/宜"
    "稳不宜争'），再分条给依据。\n"
    "2. 绝对禁止：以'所依据的原文引文'开头、以'无法计算/引文未涉及/资料不足"
    "以推断'作为主体回答，或把原文引文放在结论之前。引文只能作为'结论之后"
    "的依据'出现。\n"
    "3. 依据只能来自给定的'运算事实'和'古籍原文引文'，两者都没有的内容"
    "不得编造，不确定就明说'资料未涉及'（G7）；但'运算事实'是系统已按命理"
    "规则算好的坐标（十神/冲合/五行/流日流时），必须先把它转化为对用户问题"
    "的回答，而不是否定它。\n"
    "4. 运算事实是系统按命理规则算出的坐标，可以说'按十神/冲合推算'；"
    "引文要注明出处，**只写书名**（如《星學大成》），不要展示内部检索编号"
    "（KR3g 开头的代码）；页码锚点（WYG_xxx）可省略或用'第X页'表述。\n"
    "5. 输出用 markdown 结构：用 '## ' 分节、'**加粗**'标关键、'- '列要点，"
    "前端会渲染 markdown。\n"
    "6. 结尾单独一段标注：'以上为 LLM 生成解读，仅供参考，不构成现实决策"
    "依据。'\n"
    "7. 不给出医疗/投资/法律等现实决策建议；语气克制，不作确定性断言。"
)


def _cfg() -> dict:
    """配置合并：llm_config.json 优先，环境变量兜底（未填字段）。"""
    file_cfg: dict = {}
    if os.path.exists(CONFIG_PATH):
        try:
            file_cfg = json.load(open(CONFIG_PATH, encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            file_cfg = {}
    key = (file_cfg.get("api_key") or os.environ.get("LLM_API_KEY", "")).strip()
    return {
        "key": key,
        "base": (file_cfg.get("base_url") or os.environ.get("LLM_BASE_URL")
                 or DEFAULT_BASE).strip() or DEFAULT_BASE,
        "model": (file_cfg.get("model") or os.environ.get("LLM_MODEL")
                  or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "timeout": float(file_cfg.get("timeout_seconds")
                         or os.environ.get("LLM_TIMEOUT", "300")),
    }


def available() -> bool:
    """是否已配置 API KEY（未配置时 CLI 走引用型路径，不解读）。"""
    return bool(_cfg()["key"])


def _fmt_calc(calc_data: dict | None) -> str:
    """运算事实 -> 文本块（坐标事实直接转述，不生成新文本）。

    兼容三种 scope：
      * day   （calc()）：十神/五行/地支关系/流日流时/summary
      * range （calc_range()）：逐日流日关系
      * life  （calc_life()）：大运表
    """
    if not calc_data:
        return ""
    scope = calc_data.get("scope", "day")
    lines = [f"summary：{calc_data.get('summary', '')}"]

    # --- range：逐日流日关系 ---
    days = calc_data.get("days")
    if days:
        day_lines = []
        for d in days:
            parts = [f"{d['date']}({d['day_ganzhi']})：{d['day_master_rel']}"]
            if d.get("day_branch_rels"):
                parts.append("；".join(r["note"] for r in d["day_branch_rels"]))
            if d.get("hour_ganzhi"):
                parts.append(f"流时{d['hour_ganzhi']}：{d['hour_master_rel']}")
                if d.get("hour_branch_rels"):
                    parts.append("；".join(r["note"] for r in d["hour_branch_rels"]))
            day_lines.append("；".join(parts))
        lines.append("逐日流日（" + calc_data.get("start", "") + "~"
                     + calc_data.get("end", "") + "）：\n" + "\n".join(day_lines))
        return "\n".join(lines)

    # --- life：大运表 ---
    dayun = calc_data.get("dayun")
    if dayun:
        dy_lines = []
        for d in dayun:
            dy_lines.append(
                f"{d['pillar']}（{d['start_age']}~{d['end_age']}岁，约"
                f"{d['year_start']}年起，见日主之{d['gan_rel']}）")
        lines.append("大运（" + (f"约{calc_data.get('qi_yun_age')}岁起运" if calc_data.get("qi_yun_age") else "起运岁未知")
                     + "）：\n" + "\n".join(dy_lines))
        return "\n".join(lines)

    # --- day：单日完整事实 ---
    tgs = calc_data.get("ten_gods") or []
    tg_lines = []
    for t in tgs:
        tg_lines.append(f"{t['pos']}{t['gan']} → {t['god']}（{t['basis']}）")
    if tg_lines:
        lines.append("十神：" + "；".join(tg_lines))
    fe = calc_data.get("five_elements") or {}
    if fe.get("counts"):
        dist = "、".join(f"{e}{v:g}" for e, v in fe["counts"].items())
        miss = "缺" + "".join(fe.get("missing") or []) if fe.get("missing") else "五行俱全"
        lines.append(f"五行：{dist}；{miss}")
    rels = calc_data.get("relations") or []
    if rels:
        lines.append("地支关系：" + "；".join(r["note"] for r in rels))
    dl = calc_data.get("day_luck") or {}
    if dl.get("day_ganzhi"):
        dl_line = f"今日{dl['day_ganzhi']}：{dl.get('day_master_rel', '')}"
        if dl.get("day_branch_rels"):
            dl_line += "；" + "；".join(
                f"{r['pos']}{r['note']}" for r in dl["day_branch_rels"])
        lines.append(dl_line)
    if dl.get("hour_ganzhi"):
        hl = f"流时{dl['hour_ganzhi']}：{dl.get('hour_master_rel', '')}"
        if dl.get("hour_branch_rels"):
            hl += "；" + "；".join(f"{r['pos']}{r['note']}"
                                  for r in dl["hour_branch_rels"])
        lines.append(hl)
    return "\n".join(lines)


def interpret(render_line: str, evidence: list[dict], question: str | None = None,
              calc_data: dict | None = None) -> str:
    """坐标 + 运算事实 + 原文证据 -> LLM 大白话解读（纯函数，无副作用，不落库）。

    render_line: bazi.render() 的排盘文本。
    calc_data:   bazi_calc.calc() 返回的结构化运算事实（可 None，此时只按引文回答）。
    evidence:    bazi_lookup 返回的 [{work_id, layer, page_anchor, file, text}, ...]
    """
    cfg = _cfg()
    if not cfg["key"]:
        raise RuntimeError("LLM_API_KEY 未配置：设置环境变量 LLM_API_KEY 后再用 --llm")

    ev_lines = []
    for i, e in enumerate(evidence, 1):
        wid = e.get("work_id", "")
        # 页锚/文件名剥掉 KR3g 编号前缀，只留可读页码（WYG_002-8b / 002.txt）
        page_raw = e.get("page_anchor") or ""
        page = "@" + page_raw.replace(f"{wid}_", "", 1) if page_raw else "@?"
        file_disp = (e.get("file") or "").replace(f"{wid}_", "", 1)
        book = e.get("title") or wid   # 优先书名；无则回退 work_id
        ev_lines.append(f"[{i}] {book}·{e.get('layer','')} {page} "
                        f"({file_disp}): {e['text'][:220]}")
    parts = [f"排盘：{render_line}"]
    calc_txt = _fmt_calc(calc_data)
    if calc_txt:
        parts.append("系统运算事实（按命理规则计算的坐标，可核验）：\n" + calc_txt)
    if ev_lines:
        parts.append("检索到的古籍原文引文：\n" + "\n".join(ev_lines))
    else:
        parts.append("古籍原文引文：无（检索未命中）")
    user = "\n\n".join(parts)
    q = question or "今天运势如何？"
    user += f"\n\n用户问题：{q}"

    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 1000,
    }
    resp = httpx.post(
        f"{cfg['base'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {cfg['key']}"},
        json=body,
        timeout=cfg["timeout"],
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常：{exc}") from exc


if __name__ == "__main__":
    print("usage: import from guji.llm_reader — via scripts/ask_bazi.py --llm")
    print("configure: setenv LLM_API_KEY (required); LLM_BASE_URL / LLM_MODEL optional")
