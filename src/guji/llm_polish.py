"""llm_polish — LLM 润色层（specs/006-llm-polish）。

把确定性算好的坐标事实交给 LLM，换回 2–3 句温柔的话。它是 **附加层**：
  * 输入只有已算出的事实（不引入新命理断言）
  * 失败（无配置/断网/超时/坏响应）一律静默降级返回 None
  * 输出不落任何库（corpus/knowledge/history 三库零命中，判据 3）
  * key 只从 web/llm_config.json（gitignore）或环境变量读，不进日志

纪律（D-242a/D-243a/D-244a）：
  * httpx 直连 OpenAI 兼容 chat/completions，零新增 pip 依赖
  * 超时默认 30s（R230t 校订：docstring 此前写 8s 与 _DEFAULTS 不符）；LLM 永远不是承重墙
  * 提示词禁止模型生成书名/页码/引文（判据：响应内零 citation 结构）

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe -m guji.llm_polish     # 本模块自测（离线部分）
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import sys
import threading
import time

# ---------------------------------------------------------------------------
# 配置加载：web/llm_config.json（gitignored）> 环境变量 > None（功能关闭）
# ---------------------------------------------------------------------------

_ENV_KEY = "BOOKS_LLM_API_KEY"
_ENV_BASE = "BOOKS_LLM_BASE_URL"
_ENV_MODEL = "BOOKS_LLM_MODEL"
# 总开关（D-245a）：设为 "0"/"off" 时无条件禁用 LLM 层。
# 用途：闸门/probe 环境需要确定性延迟（ui_smoke 的 25s 单用例预算装不下
# 13–30s 的 LLM 往返），以及用户想一键关闭。优先级高于配置文件。
_ENV_DISABLE = "BOOKS_LLM_DISABLE"

_DEFAULTS = {
    "enabled": True,
    "base_url": "https://apihub.agnes-ai.com/v1",
    "model": "agnes-2.5-flash",
    "timeout_s": 30,
    # agnes-2.5-flash 是推理模型：先烧 reasoning tokens 再出正文。
    # 实测 200 会全被思考吃光（finish=length、content 空），1000 才稳定出文。
    "max_tokens": 1000,
}


def load_config() -> dict | None:
    """读配置。返回 None = 功能关闭（调用方直接跳过，不得报错）。"""
    # 总开关（D-245a）：环境变量显式禁用优先于一切配置。
    # R2349w（R93-P2-2 勘正）：DISABLE=1/on/true/yes → 禁用；其余取值
    #（含 0/false）不覆盖文件配置、按配置文件走——此前 docstring 宣称
    # "=0 强制启用" 与实现不符。
    _dis = os.getenv(_ENV_DISABLE)
    if _dis is not None and _dis.strip().lower() in ("1", "on", "true", "yes"):
        return None
    cfg = dict(_DEFAULTS)
    # 本文件在 <root>/src/guji/llm_polish.py；here 取到 .../src/guji 目录，
    # 再上两级即仓库根（web/ 的父目录）
    here = os.path.dirname(os.path.abspath(__file__))     # .../src/guji
    root = os.path.dirname(os.path.dirname(here))         # .../books
    # R229x（R7 #13）：frozen/PyInstaller 形态下 __file__ 在 _MEIPASS（Temp
    # 解包目录），上两级找不到用户放在 exe 旁的 llm_config.json——补查
    # sys.executable 同目录（exe 旁才是用户实际放文件的位置）。
    _candidates = [os.path.join(root, "web", "llm_config.json")]
    if getattr(sys, "frozen", False):
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "llm_config.json"))
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "web",
                         "llm_config.json"))
    for path in _candidates:
        try:
            with open(path, encoding="utf-8") as f:
                cfg.update(json.load(f))
            break
        except Exception as _cfg_exc:
            # R230l（R24-P3-3）：文件存在但损坏/BOM/是目录此前静默吞掉——
            # 运维无法区分「没配」与「配坏了」。存在性失败静默（常态），
            # 解析性失败打一行 stderr 告警（不含内容）。
            if os.path.exists(path):
                print(f"[llm_polish] 配置文件 {path} 读取失败"
                      f"（{type(_cfg_exc).__name__}），按未配置降级",
                      file=sys.stderr)
    # 环境变量覆盖（部署形态用；key 不落盘的场景）
    if os.getenv(_ENV_KEY):
        cfg["api_key"] = os.environ[_ENV_KEY]
    if os.getenv(_ENV_BASE):
        cfg["base_url"] = os.environ[_ENV_BASE]
    if os.getenv(_ENV_MODEL):
        cfg["model"] = os.environ[_ENV_MODEL]
    # R2349w（R93-P2-3）：timeout_s/max_tokens 补 env 覆盖——不想落盘
    # json 的部署形态此前只能改文件。
    if os.getenv("BOOKS_LLM_TIMEOUT_S"):
        cfg["timeout_s"] = os.environ["BOOKS_LLM_TIMEOUT_S"]
    if os.getenv("BOOKS_LLM_MAX_TOKENS"):
        cfg["max_tokens"] = os.environ["BOOKS_LLM_MAX_TOKENS"]

    # R2349w（R93-P1-3）：enabled 手写 "false"（字符串）此前被判
    # truthy → 以为离线的环境照样连 LLM。字符串按语义解析。
    _en = cfg.get("enabled")
    if isinstance(_en, str):
        _en_l = _en.strip().lower()
        if _en_l in ("0", "false", "off", "no"):
            return None
        cfg["enabled"] = _en_l in ("1", "true", "on", "yes")
    if not cfg.get("enabled"):
        return None

    # R2349w（R93-P1-4）：timeout_s/max_tokens/base_url 类型错此前
    # load_config 放行、polish 时抛进 task failed 且服务端零日志——
    # 配置坏→AI 层静默消失。启动期 coerce，非法值回默认+stderr 告警。
    for _k, _t in (("timeout_s", int), ("max_tokens", int)):
        try:
            cfg[_k] = _t(cfg[_k])
            # R2524（审-LLM-P3）：0/负值此前放行——每请求 instant-fail，
            # 功能静默死亡；<=0 同坏类型回默认。
            if cfg[_k] <= 0:
                raise ValueError
        except (TypeError, ValueError):
            print(f"[llm_polish] 配置项 {_k}={cfg[_k]!r} 不是正整数，"
                  f"回退默认 {_DEFAULTS[_k]}", file=sys.stderr)
            cfg[_k] = _DEFAULTS[_k]
    if (not isinstance(cfg.get("base_url"), str)
            or not cfg["base_url"].startswith("http")):
        print(f"[llm_polish] 配置项 base_url={cfg.get('base_url')!r} "
              f"不是合法 URL，回退默认", file=sys.stderr)
        cfg["base_url"] = _DEFAULTS["base_url"]
    # R230l（R24-P2-1）：api_key 非字符串（用户手写配置文件填了
    # 数字/对象）此前 startswith 炸 AttributeError → 端点 500。
    # 按未配置处理——与 DISABLE 同路径静默降级。
    if (not isinstance(cfg.get("api_key"), str)
            or not cfg["api_key"]
            or cfg["api_key"].startswith("REPLACE")):
        return None
    return cfg


# ---------------------------------------------------------------------------
# 提示词：事实进、温柔话出。禁止新断言、禁止引用外观。
# ---------------------------------------------------------------------------

_SYSTEM = (
    "你是一个温柔的中文命理助手，为已经算好的命理结果"
    "（八字盘/卦象/牌面/合盘/起名）写解读润色。"
    "规则：1) 只使用【给定事实】里的信息，绝不发明新的命理断言、绝不出示新的术语；"
    "若事实里有性别/双方性别，称谓与措辞必须与之一致（女性绝不可称先生，反之亦然）；"
    "2) 绝不引用任何书名、页码、原文（引文由系统另行展示）；"
    "3) 语气像善解人意的朋友：温暖、鼓励、不说教、不恐吓、不用宿命式表述"
    "（禁止：注定/孤独/没戏/克夫克妻/必离，事实里算好的相克/相冲/相刑"
    "是盘面判词，可以直说，不许软成「看你们自己」）；"
    "4) 不给现实决策指令；"
    "5) 输出 2–3 句中文，总长不超过 90 字，不要分点、不要标题、不要 emoji。"
)

_TEMPLATE = (
    "【给定事实】\n{facts}\n\n{verdict_block}"
    "【用户提问】{question}\n\n"
    "请基于给定事实写一段温柔的解读。"
)


def _render(facts: list[str], question: str | None) -> str:
    # R230a-6（R12-P3-8）：占位句「请泛泛而谈」像在鼓励泛答——换中性标记。
    q = (question or "").strip() or "（无提问）"
    # R3132（specs/012-P0 同构）：判词行从 facts 堆里升格成权威块——
    # 此前判词只是第 N 条参考资料，模型可自由发挥成相反方向
    # （「偏不合适」的盘被润色成「挺合适的」实锤过）。单独成块+硬约束。
    # R3142（真修46）：桃花推进的是「判词直说：…」——startswith(判词)
    # 宽匹配接住 判词：/判词直说：/判词偏硬 各形态。
    _vf = [f for f in facts if str(f).startswith("判词")]
    _vf_block = (
        "【判词口径·必须一致】\n" + "\n".join(_vf) + "\n"
        "上面是已经算好的判词：你的解读可以展开、可以细化，"
        "但方向必须与判词一致，不许说反话（判词说磨合你不能说天作之合）。\n\n"
        if _vf else "")
    return _TEMPLATE.format(
        facts="\n".join("- " + _fact_line(f) for f in facts),
        verdict_block=_vf_block, question=q)


# ---------------------------------------------------------------------------
# 调用与解析
# ---------------------------------------------------------------------------

def polish(facts: list[str], question: str | None = None,
           config: dict | None = None, _transport=None,
           _attempts: int = 3) -> str | None:
    """事实列表 → 温柔段落文本；任何失败返回 None。

    _transport 仅测试注入用（callable(payload_dict, headers, url, timeout) -> dict），
    生产路径恒为 None（内部用 httpx）。
    内部重试 _attempts 次：agnes 端点实测有随机空正文 / SSL 断连（约半数），
    单次成功率不足，重试后整体可用性显著提升。重试不改变确定性语义——
    本函数本来就因 LLM 而不可复现，降级路径同样如此。
    """
    # R3018（真修#17）：question 是模板 user 位的裸用户文本——危机/敏感
    # 问句此前照样交 LLM 写解读，输出净化只剥宿命词不给转介，LLM 关闭
    # 时则静默缺席。确定性短路先于一切检查（罐头不依赖 LLM 在线、
    # 不烧 quota），与 chat/问一嘴同口径。
    if isinstance(question, str) and question.strip():
        if _is_crisis(question):
            return _CHAT_REFUSAL
        if _is_sensitive(question):
            return _SENSITIVE_REPLY
    cfg = config or load_config()
    if cfg is None:
        return None
    facts = [f for f in (facts or []) if f]
    if not facts:
        return None

    # R3242：polish 此前是链上唯一没接兜底的路径——chat/review 早按
    # R3223 逐节切换，排盘/起名/解梦等全部结果卡的 AI 块却主超时即死。
    # 与 chat 同构：按 fallbacks 顺序去重成链，共享同一 34s 轮询预算，
    # 节点超时即弃（_polish_node 内），让预算流到能活的链节。
    _dl = time.monotonic() + _POLL_BUDGET_S
    _seen_bases = {cfg.get("base_url")}
    _chain = [cfg]
    for _fcfg in load_fallback_configs():
        if _fcfg.get("base_url") in _seen_bases:
            continue
        _seen_bases.add(_fcfg.get("base_url"))
        _chain.append(_fcfg)
    for _ni, _node in enumerate(_chain):
        _ndl = _dl
        if _ni == 0:
            # R3242：主节点预算帽——推理模型「finish=length 加倍重试 +
            # 超时」二连可把 34s 吃干，兜底 0 余额。封顶 timeout_s+2s
            # （一次完整尝试+余量），剩余预算留给链上快节点。
            _ndl = min(_dl, time.monotonic() + float(
                _node.get("timeout_s") or _DEFAULTS["timeout_s"]) + 2)
        out = _polish_node(facts, question, _node, _transport=_transport,
                           _attempts=_attempts, deadline=_ndl)
        if out:
            return out
        if time.monotonic() >= _dl:
            break
    return None


def _polish_node(facts: list[str], question: str | None, cfg: dict,
                 _transport=None, _attempts: int = 3,
                 deadline: float | None = None) -> str | None:
    """单个 provider 节点上的 polish 尝试（payload 构建+重试循环）。

    R3242 从 polish() 抽出——兜底链按节点复用同一段尝试逻辑。"""
    payload = {
        "model": cfg.get("model") or _DEFAULTS["model"],
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _render(facts, question)},
        ],
        "max_tokens": int(cfg.get("max_tokens") or _DEFAULTS["max_tokens"]),
        # R230t（R32-P2-21）：polish 是「照事实说人话」的活——0.8 采样
        # 是「没查到」类漂移的温度贡献项，降到 0.5。
        "temperature": 0.5,
    }
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + cfg["api_key"],
               "Content-Type": "application/json"}
    timeout = float(cfg.get("timeout_s") or _DEFAULTS["timeout_s"])
    # R12-P2-4：预算由调用方传入——链上各节点共享同一终点。
    _deadline = (deadline if deadline is not None
                 else time.monotonic() + _POLL_BUDGET_S)

    for i in range(max(1, _attempts)):
        _to = min(timeout, max(0.5, _deadline - time.monotonic()))
        if _to <= 0.5 and time.monotonic() >= _deadline:
            break
        # R230t（R32-P2-21）：重试零退避——抖动期 3 连发瞬时打满。
        # 0.4s/0.8s 小睡，预算大头来去仍是真请求。
        if i:
            time.sleep(min(0.4 * i, 1.2))
        try:
            if _transport is not None:                # 测试注入
                data = _transport(payload, headers, url, _to)
            else:
                import httpx
                # B-020（R192b，审查轨 R132a-F2）：httpx 默认 trust_env=True，
                # 会拾取 Windows 注册表代理且无视 ProxyOverride——发往
                # 127.0.0.1/localhost 的请求被代理吞成 502 空响应（R192b 基线
                # 复现：mock 收到 0 个请求、polish 静默 None）。回环地址永远
                # 不该走系统代理，对 loopback 目标显式关掉 trust_env。
                # 远程目标（agnes 等）行为不变：仍走 trust_env=True 的默认客户端。
                if _is_loopback(url):
                    with httpx.Client(trust_env=False, timeout=_to) as cli:
                        resp = cli.post(url, json=payload, headers=headers)
                else:
                    resp = httpx.post(url, json=payload, headers=headers,
                                      timeout=_to)
                if resp.status_code != 200:
                    # R230t（R32-P0-1）：401/403/422 的「免重试」此前是死代码——
                    # continue 跳过标志位检查点，鉴权错照样打满 3 次。
                    # 4xx 全是确定性失败（鉴权/参数/找不到/实体过大），连同
                    # 429 配额耗尽一律一次即停，不再白烧往返。
                    if resp.status_code == 429 or 400 <= resp.status_code < 500:
                        break
                    continue                          # 可重试：网关类错误
                # R2524（审-LLM-P2-4）：.json() 前字节帽——异常上游
                # 实测吐过 36MB content，解析+回写放大内存×在途任务数。
                if len(resp.content) > 2_000_000:
                    continue
                data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            # R230t（R32-P0-2）：finish_reason=length = 推理模型把 max_tokens
            # 烧在思考里——空 content 或半截正文。同参重试只会再烧一遍预算：
            # 空判当次即弃，半截按失败降级（此前半截原文直接上屏）。
            if (data["choices"][0].get("finish_reason") or "") == "length":
                break
        except Exception as _pexc:
            # R3242：与 _chat_call 同口径——超时即弃节点让位下一链节，
            # 其余异常（断连/空回/解析错）保留原重试语义。
            if "Timeout" in type(_pexc).__name__:
                break
            continue                                  # D-244a 静默降级 + 重试
        out = _sanitize(text)
        # R3132（specs/012-P0 同构）：polish 出稿过判词方向闸——facts 里
        # 有判词行时，润色与判词唱反调按失败处理（重试带纠正提示）；
        # 三次仍犯返回 None 降级——卡面 warm.reply 本来就是判词原句，
        # 缺省渲染即一致，矛盾稿绝不落屏。
        if out:
            _vfacts = [f for f in facts if str(f).startswith("判词")]
            if _vfacts and _chat_verdict_contra(out, _vfacts):
                payload["messages"] = payload["messages"] + [{
                    "role": "user",
                    "content": "（系统提醒：上一次回复与判词方向相反。"
                               "判词是算好的结论只能顺着说，请按判词口径"
                               "重答，保持纯文本口语。）"}]
                out = None
            if out:
                return out
        # R230t（R32-P1-6）：输出被拦（禁语/引文/过短）时给重试一句改正线索，
        # 同参盲烧三轮是三倍 quota。
        payload["messages"] = payload["messages"] + [{
            "role": "user",
            "content": "（系统提醒：上一次回复因措辞不合规被拦"
                       "（禁语/引文/过短），请换一种说法重答，"
                       "保持纯文本口语。）"}]
    return None


_LEAK_PAT = re.compile(
    r"《[^》]{1,20}》|第\s*\d+\s*页|page\s*\d+|p\.\s*\d+", re.IGNORECASE)

# R230a-6（R12-P1-3）：review 的 prompt 明令引《诗经》《楚辞》篇名——
# 全表剥《》会把卖点销毁成断头句；这两路改用不含书名号段的变体。
_LEAK_PAT_KEEP_BOOK = re.compile(
    r"第\s*\d+\s*页|page\s*\d+|p\.\s*\d+", re.IGNORECASE)

# R230a-6（R12-P1-4）：输出侧禁语闸——与 _SYSTEM/_CHAT_SYSTEM 明令清单
# 对齐（注定/孤独/没戏/必离/克… + 指令式措辞）。此前只有 chat 有一条
# 偏窄的拦截表，polish/review 失守文本可原样落屏。命中 → 该次调用
# 按失败处理（重试/降级），不落历史不渲染。
_BANNED_OUT_PAT = re.compile(
    # R3087（specs/010）：相克|相刑 移出禁表——它们是盘面算出的技术词，
    # 用户明确要求「相克就是相克」直说。判死语义由「注定/必离/克夫克妻/
    # 赶紧分」等组合词继续拦截，技术词自身不表宿命。
    r"注定|孤独|没戏|必离|克夫|克妻|克你|克[他她它]|灾劫|大凶|劫数|"
    r"大难|别理他|直接分手|赶紧分|断联|(?<!不)你应该|你必须|你要记得|"
    # R2817（审）：紧邻「不」是否定 hedge（「我不建议你/你不应该」是模型在
    # 卸指令不是在指挥）——误杀会把贴题回复换成泛兜底；只豁免相邻不。
    r"(?<!不)建议你|"
    # R2345（R61-P1-3）：出侧闸此前只管命理恐吓/指令式措辞——补一层
    # 轻量高危词兜底（露骨成人/仇恨词模型吐出时降级不展示）。
    r"约炮|做爱|色情|裸体|裸照|口交|性交|强奸|"
    r"nigger|faggot|支那",
    re.IGNORECASE)

_LOOPBACK_PAT = re.compile(
    r"^https?://(127\.0\.0\.1|\[::1?\]|localhost)(:\d+)?(/|$)", re.IGNORECASE)

# R2400（R135-P0-4）：出侧内部外形串——后端键名/SQL/异常栈/服务器
# 路径直接上屏即露馅（「calc.ten_gods」「SELECT * FROM corpus」）。
# 命中按失败处理交上层降级，与禁语闸同口径。
_INTERNAL_OUT_PAT = re.compile(
    r"calc\.[a-z_]+|\bselect\b.+\bfrom\b|insert\s+into|drop\s+table|"
    r"traceback|corpus\.db|knowledge\.db|/home/|/users/|/app/|"
    r"[a-z]:[\\/]|\w+\.py\s*(?:line|:)", re.IGNORECASE)

# R2400（R135-P2-1）：prompt 模板的内部字段名——模型原样复述
# 「根据给定事实/参考口吻/排盘坐标」等于提示词结构外露。
_PROMPT_LEAK_PAT = re.compile(
    r"给定事实|候选名字|五行背景|参考口吻|排盘坐标|话题参考|请泛泛而谈|"
    r"ctx\s*[:：]|我的规则|只使用.{0,8}(信息|事实)", re.IGNORECASE)

# R2524（审-LLM-P2-3）：keep_citations 引文豁免段的窄禁表——只收
# 现代恐吓/判死词（真古籍引文几乎不含）；「相克/相刑/大凶/劫数」是
# 真古书高频词不进表，否则《五行相克》类合法引文被误杀。
_BANNED_QUOTE_PAT = re.compile(
    r"注定|必离|没戏|克夫|克妻|克你|克[他她它]|孤独终老|嫁不出去|"
    r"直接分手|赶紧分|断联|你应该|你必须", re.IGNORECASE)

# R230a-6（R12-P2-4）：前端轮询上限（app.js AI_POLL_CAP_S），后端最坏
# 链路必须在其内完成——慢成功白烧 quota，用户永远看不到。每次尝试
# 的 timeout 按「轮询预算剩余」递减，超预算直接收手让上层降级。
# R3243（用户实测）：三家提供方全是推理模型，拥挤期单次生成 15–30s
# 常见——34s 只装得下 1.5 个节点，兜底救不回。50s 让主节点帽
# (timeout_s+2≈26s) 后仍给快节点留 ~20s+ 真实窗口。
_POLL_BUDGET_S = 50.0
# R3245：起名点评链专用预算——三节点满载 68s，共用 50s 帽时末节
# 拿不到窗口；点评有确定性底卡托底，值得让链跑完。
_REVIEW_BUDGET_S = 78.0


def _is_loopback(url: str) -> bool:
    """URL 是否指向回环地址（B-020：loopback 不走系统代理）。"""
    return bool(_LOOPBACK_PAT.match(url or ""))


def _sanitize(text: str | None, keep_citations: bool = False) -> str | None:
    """输出净化：去书名号引用外观、裁掉空段、剥离推理模型 thinking 泄漏。判据 6 的代码侧兜底。

    keep_citations=True 保留《书名》段（起名点评的卖点就是出处）。
    R230a-6（R12-P1-4）：禁语命中按失败处理（返回 None 交给调用方重试/降级）。"""
    if not text:
        return None
    # agnes-2.5-flash 是推理模型：reasoning_content 偶发漏进 content，
    # 形态为 "...正文...\n</think> 正文..."——只保留最后一段 </think> 之后的正文。
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    # R230t（R32-P2-14）：只有开标签没有闭标签 = 整段英文思考原文会
    # 无遮挡上屏——按失败处理（交给调用方重试/降级）。
    if "<think>" in text:
        return None
    text = (_LEAK_PAT_KEEP_BOOK if keep_citations else _LEAK_PAT).sub("", text)
    # R230t（R32-P2-14）：\s{2,} 连换行一起压扁——模型的分段/双换行
    # 全糊成一行。只压水平空白，保留段落结构（3+ 连换行收到 2）。
    text = re.sub(r"[^\S\n]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = text.strip("\"“”'‘")
    # R230a-6（R12-P3-7）：<6 字下限会误杀合法短答（「挺好的。」4 字），放到 3。
    if len(text) < 3:
        return None
    # R230l（R24-P2-2）：上游回复无长度上限——实测 36MB content 会原样
    # 进任务行/响应/session history，下一条消息把 36MB 整体再发回上游。
    # 截到 8000 字（正常解读 200-800 字，10× 余量），截断标记进尾部。
    if len(text) > 8000:
        text = text[:8000].rstrip() + "……（内容太长，后面的截掉了）"
    # R2400（R135-P1-4）：伪 system 行/markdown 记号不许进小满口径——
    # 「system:」仿指令行剥掉；**/## 记号压回纯文本（卡片不渲 markdown，
    # 裸符号上屏很难看）。
    # R2822（审）：system 行剥除提到 CJK 检查之前——「system: be evil\n
    # 正常中文回复」的垃圾前缀曾把 CJK 占比拉到阈值下，本可洗净的回复
    # 被整条丢弃。剥完再算占比，漂移动作的量测才只算用户可见内容。
    text = re.sub(r"(?im)^\s*system\s*[:：].*\n?", "", text).strip()
    # R230t（R32-P2-18）：模型漂移成英文/拼音原文此前直通上屏——CJK
    # 占比过低（<1/3 且超 12 字）按失败降级。短答（「挺好的。」）不受影响。
    if len(text) >= 12:
        _cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        if _cjk * 3 < len(text):
            return None
    text = re.sub(r"\*{1,2}([^*\n]+)\*{1,2}", r"\1", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    # R2400（R140-followup）：markdown hr（---/*** /___ 独占行）压掉——
    # 起名点评实测漏「---」裸分隔线上屏。
    text = re.sub(r"(?m)^\s*[-*_]{3,}\s*$\n?", "", text)
    # R2524（审-LLM-P1-1）：零宽/不可见控制字剥掉——「注\u200b定」
    # 此前原样上屏渲染成「注定」，扫描形态也拼不回禁词。
    text = _OUT_ZW.sub("", text)
    if len(text) < 3:
        return None
    # R2524（审-LLM-P1-1）：禁语/内部串/提示词外露三闸改扫归一形态
    # ——此前在 markdown 还原之前扫原文，「注**定**」「你 应 该」
    # 「註定」全漏。_scan_form 剥记号/零宽/空白+繁折简，绕闸形态
    # 拼回真词再判（只用于判定，不改上屏文本）。
    _sf = _scan_form(text)
    # R3069（巡#486）：禁语/引号窄表改扫 _scan_flat——「注.定」「必-离」
    # 插符禁词不再直通上屏；内部串/泄露闸继续在带点 _sf 上跑
    # （calc\\. / ctx： 依赖点号句号不被破坏）。
    _sf2 = _scan_flat(text)
    if _BANNED_OUT_PAT.search(_sf2):
        # R230t（R32-P2-13）：keep_citations 路径引文内的古词（《》/「」里
        # 的「克明俊德」类）不该撞禁语闸——剥掉引号段再扫。
        if keep_citations:
            _unquoted = re.sub(r"《[^》]*》|「[^」]*」|『[^』]*』", "", _sf2)
            if _BANNED_OUT_PAT.search(_unquoted):
                return None
            # R2524（审-LLM-P2-3）：引号豁免被「《注定》」「「必离」」
            # 式投放绕开——现代恐吓词在真古籍引文里几乎不出现，
            # 引号内单独补一张窄表（「相克/大凶」等真古词不进表防误伤）。
            if _BANNED_QUOTE_PAT.search(_sf2):
                return None
        else:
            return None
    # R2400（R135-P0-4）：内部外形串上屏——模型复述提示词里见到的
    # 后端细节即降级（不渲染）。
    if _INTERNAL_OUT_PAT.search(_sf):
        return None
    # R2524（审-LLM-P2-1）：_PROMPT_LEAK_PAT 此前定义后从未接入——
    # 「根据给定事实…」式提示词结构外露直通上屏。
    if _PROMPT_LEAK_PAT.search(_sf):
        return None
    return text


# ---------------------------------------------------------------------------
# 后台任务层（R191b，specs/006 判据 9/10/11；B-014 的修法，D-251b）
#
# 形态：daemon 线程跑 polish()，结果存**进程内存** dict（重启即失）。
#   * AI 文本永不落任何库（宪法红线第 4 项：三库零命中判据继续成立）
#   * DISABLE=1 / 配置关闭时 spawn 根本不发生——响应里没有 ai_task_id 键，
#     与旧版逐字节一致（闸门环境零扰动，判据 11）
#   * 拿不到 = failed = 前端整块不渲染（D-244a 降级语义不变）
#
# 可测性：spawn_ai_task 接受与 polish 相同的 _transport 注入口，
# web/check_async_ai.py 用它打桩慢 LLM（零外网、确定性延迟）。
# ---------------------------------------------------------------------------

_TASK_TTL_S = 600.0          # 任务记录保留 10 分钟：足够前端轮询完，又不积内存
_MAX_PENDING = 12            # 在途 AI 任务上限——未鉴权端点每请求一线程+最坏
                             # 6 次 LLM 往返，无界时单人会话能拖垮连接池
# R2524（审-LLM-P1-2）：危机/敏感固定文案的罐头任务 id——覆盖写不
# 增行，免限流短路不再产生行洪泛。
_CANNED_TASK_IDS = {
    "crisis": "__canned_crisis__",
    "sensitive": "__canned_sensitive__",
}

_MAX_TASK_ROWS = 256         # R229t：任务行总数帽——_MAX_PENDING 只管在途，
                             # 完成行靠 600s TTL，洪泛可在此期间积成山；
                             # 超帽拒 spawn（功能降级但服务不死）。
_POLL_CAP_S = 40.0           # 前端轮询上限（秒）；到点未完成按失败处理（不渲染）

# R230t（R32-P0-4）：未鉴权 LLM 端点滑动窗口限速——_MAX_PENDING 只限
# 同时在途，串行重发不限速：每条 chat 最坏 6 次外呼，换 sid 即绕轮数帽。
_RATE: dict[str, list[float]] = {}
_RATE_WIN_S = 60.0
_RATE_CHAT_PER_SID = 8      # 每会话每分钟最多 8 个聊天任务
_RATE_GLOBAL = 120          # 全局任务帽/分钟（跨 sid 洪泛兜底）
_RATE_MAX_KEYS = 4096       # 键表洪泛帽

# R230t（R31-P2-6）：进程启动记号——前端对照此值能在「服务重启/会话失忆」
# 时给用户一个提示，而不是让小满对着还在屏上的旧气泡装记得。
_BOOT_ID = f"{int(time.time())}-{secrets.token_hex(3)}"

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _rate_ok(key: str, limit: int) -> bool:
    """滑动窗口限速：key 维度 + 全局维度同时查。False = 拒（上层按降级）。"""
    now = time.monotonic()
    kl = [t for t in _RATE.get(key, ()) if now - t < _RATE_WIN_S]
    gl = [t for t in _RATE.get("", ()) if now - t < _RATE_WIN_S]
    _RATE[key] = kl
    _RATE[""] = gl
    if len(_RATE) > _RATE_MAX_KEYS:        # 键表洪泛：清一半旧键
        for k in list(_RATE)[_RATE_MAX_KEYS // 2:]:
            if k:
                _RATE.pop(k, None)
    if len(kl) >= limit or len(gl) >= _RATE_GLOBAL:
        return False
    kl.append(now)
    gl.append(now)
    return True


def _gc_tasks() -> None:
    """清掉超 TTL 的已完成任务记录。调用方必须已持有 _tasks_lock。"""
    now = time.monotonic()
    # R230a-6（R12-P3-1）：pending 任务不在 TTL 回收范围——同 sid 串行
    # 排队时在途可 >TTL，回收会让线程跑完无处写、前端轮询 404「没接住」。
    # R3228（R3225 同型补防）：任务行缺 created/status 键此前 KeyError——
    # GC 在每次 spawn 首部跑，一条脏行=全 AI 层停摆。缺 created 按超龄
    # 逐出；缺 status 不当 pending 保（畸形行没有可交付的读者）。
    stale = [tid for tid, t in _tasks.items()
             if now - t.get("created", 0) > _TASK_TTL_S
             and t.get("status") != "pending"]
    # R2511（审-SV-P2）：pending 豁免泄漏源——Thread.start() 抛错/
    # BaseException/_session_lock 卡死都会留永久 pending 行，攒满
    # _MAX_PENDING=12 后所有 spawn 静默 None、AI 层停摆且零日志。
    # pending 的「不死」只保轮询预算内的正常排队；2×TTL 后照收
    # （线程真还在跑也只是写不回——比整层关停好）。
    stale += [tid for tid, t in _tasks.items()
              if t.get("status") == "pending"
              and now - t.get("created", 0) > _TASK_TTL_S * 2]
    for tid in stale:
        _tasks.pop(tid, None)


def spawn_ai_task(facts: list[str], question: str | None = None,
                  config: dict | None = None, _transport=None,
                  rate_key: str = "ai",
                  rate_limit: int = 60) -> str | None:
    """后台起一个 polish 任务，立刻返回 task_id；功能关闭返回 None。

    返回 None 时调用方不要往响应里放 ai_task_id 键——这样 DISABLE=1 的
    响应形状与旧版完全一致。
    （R191b 实测注：question 必须给默认值——taohua/hehun/qiming 无提问
    场景只传 facts 一个位置参数，缺默认值会在参数绑定期直接 TypeError，
    且与总开关无关。）
    """
    cfg = config or load_config()
    if cfg is None:
        return None
    facts = [f for f in (facts or []) if f]
    if not facts:
        return None
    # R230t（R32-P0-4）：AI 解读限速——同一盘重进页面重调的场景常见，
    # 每键一分钟 60 次足够正常使用，洪泛按降级处理。
    # R3157（审-拥塞）：分享重放/合盘 GET 这类爬虫可达路径用小桶——
    # 链接预览器刷爆单面时只挤爆自己的桶，不拖垮全局「ai」额度。
    if not _rate_ok(rate_key, rate_limit):
        return None
    tid = secrets.token_urlsafe(16)
    with _tasks_lock:
        _gc_tasks()
        if len(_tasks) >= _MAX_TASK_ROWS:
            return None
        pending = sum(1 for t in _tasks.values() if t["status"] == "pending")
        if pending >= _MAX_PENDING:
            return None
        _tasks[tid] = {"status": "pending", "text": None,
                       "created": time.monotonic()}

    def _run() -> None:
        with _tasks_lock:
            rec0 = _tasks.get(tid)
            if rec0 is not None:
                rec0["started"] = time.monotonic()
        try:
            text = polish(facts, question, cfg, _transport=_transport)
            status = "done" if text else "failed"
        # R2511（审-SV-P2）：BaseException——KeyboardInterrupt/
        # SystemExit 从 Exception 底下漏走会留永久 pending 行。
        except BaseException:                 # D-244a：任何异常都降级，不抛
            status, text = "failed", None
        with _tasks_lock:
            rec = _tasks.get(tid)
            if rec is not None:
                rec["status"] = status
                rec["text"] = text

    threading.Thread(target=_run, name="ai-polish-" + tid[:8],
                     daemon=True).start()
    return tid


def ai_task_status(tid: str) -> dict | None:
    """查任务状态。未知 id（含已过 TTL）返回 None（HTTP 层转 404）。

    读取**无副作用**：轮询请求若因网络抖动重发，第二次仍能拿到同样结果——
    不做「读走即焚」。回收完全靠 _gc_tasks 的 TTL。
    """
    with _tasks_lock:
        rec = _tasks.get(tid)
        if rec is None:
            return None
        return {"status": rec["status"], "text": rec["text"],
                "closed": bool(rec.get("closed")),
                # R233r（R49-P2-3）：本轮任务是不是该会话的第一条
                # （前面聊的已被 TTL 回收/进程换脑）。
                "fresh": bool(rec.get("fresh")),
                # R230v（R34-#5）：未起动=在 _session_lock 里排队
                "queued": "started" not in rec,
                # R230t（R31-P2-6）：进程启动记号透传——前端据此识别
                # 「重启失忆」并在气泡间插分隔提示。
                "boot": _BOOT_ID}


# ---------------------------------------------------------------------------
# AI 陪伴层（R206b，specs/009 US1；D-259b）
#
# 形态：chat() 同步函数复用 polish 的传输/重试/_sanitize 全套；
#   spawn_chat_task() 复用同一个 _tasks dict、锁、GC 与 /api/ai/{tid} 轮询
#   端点——零新轮询端点、零新 GC。会话历史**只在内存**（_CHAT_SESSIONS，
#   同 TTL GC），绝不入库；发给 LLM 的上下文不含生日等 PII。
#
# 安全红线（specs/009 US1 判据 b/c）：
#   * 输入侧 _CRISIS_PAT 命中自伤/危机关键词 → 不调 LLM，直接给固定转介话术
#     （LLM 绝不接手心理危机——输出侧兜底由 _CHAT_REFUSAL 双保险）；
#   * 输出侧 _CHAT_BANNED_PAT 命中指令式说教/现实决策命令 → 该次回复丢弃
#     降级为固定安全回复（D-244a 语义：拦截 ≠ 报错）；
#   * 会话轮数上限 _CHAT_MAX_TURNS=6，超限温和收尾（防依赖设计）；
#   * DISABLE=1 / 配置关闭 → spawn_chat_task 返回 None，前端隐藏入口。
# ---------------------------------------------------------------------------

_CHAT_MAX_TURNS = 6            # 单会话最大用户轮数；到顶温和收尾
_CHAT_SESSION_TTL_S = 1800.0   # 会话上下文保留 30 分钟
_CHAT_MAX_SESSIONS = 512       # R229t：sid 洪泛防护——TTL 只清旧不清多，
                               # 海量新 session_id 可在 30min 内撑爆内存；超帽
                               # 逐最旧的（LRU-ish），正常单用户永远碰不到。

_CHAT_SYSTEM = (
    "你是「小满」，一个懂玄学、更懂用户的互联网闺蜜（R214b 人设升级）。"
    # R2349r（R82-P2-3）：自称与 emoji 口径钉死——polish 的 _SYSTEM 有
    # 「不要 emoji」，chat 侧一直没写；自称「小满」同理补明。
    "说话像躺在沙发上和朋友聊天：称呼对方「宝」（别句句都喊，偶尔用"
    "更自然），自称「小满」，"
    "语气柔和带一点点俏皮，多用「我觉得」「说不定」这类软化词；"
    "可以用轻梗但绝不堆砌网络热梗，不用 emoji。"
    "用户可能刚测完盘，也可能什么都没测、直接来聊心情感情工作。"
    "有盘面信息就温和引用当话题，但绝不用命理术语吓人。"
    # R2349r（R82-P2-4）：「绝不下判断」收窄为「命运式断言」——与
    # 「宜就放心安利」的字面冲突消解（判定义务写清适用范围）。
    # R3087（specs/010）：「你们不合适」此前被例进禁句——用户明确要求
    # 盘里有判词时直说。收窄到纯宿命断言；系统算好的判定/判词照直说。
    "绝不下命运式断言（如「命中注定」「你会倒霉」「你们天生一对」）；"
    "但系统算好的判定照直说，黄历判定、合婚判词、盘面算出的相克"
    "相冲都不许软成「看你们自己」，判词说了不合适就照不合适聊。"
    # R233r（R49-Top5-5）：事实诚信——没测过的盘不许假装看过，
    # 用户没提的细节不许替 ta 编具体结论。
    "事实里没有的东西不许编：没给盘面就别假装看过盘，用户没说的细节"
    "不要替ta补具体结论。"
    # R3115（specs/011 P1-4）：档案事实用起来——给了她的生日/日主/
    # 性别就自然使用，别反过来再问「你生日是哪天」「你是男生女生」。
    "事实里给了她的档案（生日/日主/性别）就自然用起来。"
    "不许再问「你生日是哪天」「你是男生女生」这类档案里已经写了的问题。"
    # R233r（R49-Top5-5）：答完轻轻指路——一句带过，不是每条都指。
    "聊完可以轻轻指一条路（比如「明天记得来打卡」「去黄历翻翻挑日子」），"
    "一句带过就行，别每条都指、别变推销。"
    # R2516（用户反馈「小满回复太泛」）：具体性下限——安慰人人会说，
    # 小满的价值在「接下来能做什么」。三句里至少一句落到具体上。
    "不许只回正确的话·每轮至少给一样具体的：一个场景、一个能照做的小动作、"
    "或一个时间窗（像「睡前把明天最重要的那件事写下来」这种）；"
    "「都会好的」「看开点」「顺其自然」单独出现等于没答，"
    "事实里给了盘面解读就照着具体内容展开，不要复述标签。"
    # R233r（R49-P2-6）：健康/生死不下诊断。
    "健康、生死、重大疾病类问题不下诊断、不劝人不看医生，温和转给"
    "专业的人。"
    # R2349q（R82-P1-2）：财务话题同补边界——不下买卖判断，
    # 理财类决策温和转给专业的人。
    "理财、投资、股票、基金类问题不做买卖建议、不预测涨跌、"
    "不给仓位或金额分配方案（「先拿一万试水」这类也算建议）"
    "可以聊心情和压力，但具体怎么投、投多少，温和提醒找专业理财顾问。"
    "禁止指令式建议（「你应该…」「你要…」）、禁止替用户做现实决定、"
    "不说教不越界；对方不想深聊就自然换个开心的话题。"
    # R227b（用户反馈「不能照本宣科」）：黄历类提问照「黄历判定」说人话。
    "如果用户在问某天适不适合做某件事（出行/搬家/面试…），事实里可能带"
    "「黄历判定」，照着说：宜就放心安利，忌就轻轻提醒并把近期宜它的日子"
    "报出来；没列入宜忌是中性：不是不支持，只是黄历没为它背书，可照常"
    "安排；绝不要只回一句「黄历没提」就完事。"
    # R228w：实测模型会把「下周三」换算成错误日期/虚构宜日——钉死：
    # 日期一律以事实为准，事实没有的日子不许提。
    "所有日期、星期、宜忌日子严格以事实文本为准，事实里没有的日子一个都不许提。"
    # R227b（同批）：输出纯文本口语——渲染层支持白名单 markdown，但闲聊
    # 人设不需要加粗/列表/标题。
    # R3127：三句上限在有判词/盘面可聊时是深度天花板——闲聊仍两三句，
    # 聊到判词卡允许四五句（先复述她的问题→判词口径→具体场景→行动）。
    "全程输出纯文本口语：不用 markdown 标记（**、`、#、- 列表都不用），"
    "不分点不加标题。闲聊回复两三句话；聊到判词卡/盘面内容时可以到"
    "四五句：把判词口径、具体场景、能做的动作都说明白，但不许凑字数。"
    "结尾常带一个小反问或一个小行动（例：「要不要试试？」）。"
)

_CHAT_REFUSAL = ("这个话题有点重，我不太敢乱说。如果心里真的很难受，"
                 "全国心理援助热线 12356（24 小时，免费）随时能打通，"
                 "跟信任的朋友聊聊也会好一些，我一直都在，陪你聊聊"
                 "别的也行。")   # R233r（R49-Top5-1）：补 12356 热线

# R230a-5：轮数到顶后的确定性收尾轮换（不换语义，只免机械复读）。
_CHAT_CLOSERS = [
    "今天先聊到这里啦～盘一直在，随时回来看。记得好好吃饭。",
    "今天聊到这就够啦，盘面我替你收着，明儿想看随时来。先去喝口水歇会儿。",
    "咱们今天先到这里，不急。盘又不会跑，想我了随时回来。去忙你的吧～",
]

# R233r（R49-P2-5）：二级收口——主池转满一轮后换回访钩子。
_CHAT_CLOSERS_LATE = [
    "我已经陪你聊到电量见底啦，明天来打个卡/拆新签，好运我先替你留着。",
    "今天真聊够啦～明天拆新签再来找我，我给你留着位置。",
]

# R230a-6（R12-P2-5）：补高频口语与英文危机词——漏一个就是一条真实风险。
# R2400（R126-P1-5）：拆硬/软两层——硬词（想死/自杀/跳楼…）任何语境
# 接住；软词（死了算了/活腻/活着没意思）常见于物件口语（「电脑死了
# 算了」「这剧烂死了算了」），命中时按分句判：分句带物件词豁免。
_CRISIS_HARD_PAT = re.compile(
    # 厌世与抑郁同级——自杀意念词，「我厌世了」玩笑形也安全偏拦。
    r"不想活|想死|自杀|自残|伤害自己|想不开|轻生|跳楼|抑郁|厌世|"
    # R233r（R49-Top5-1）：直述自杀手段/绝望口语此前漏网。
    # 活著不收入 T2S（著→着 会误伤「著名/著作」）——字符组双形直收。
    r"活不下去|活[着著]好累|想消失|不想在了|烧炭|割腕|跳河|上吊|安眠药|"
    r"suicide|kill\s*myself|end\s*it", re.IGNORECASE)
_CRISIS_SOFT_PAT = re.compile(
    # R2400（R123-P1-2）：插字变体与口语决绝句——「活着真没意思」
    # 此前被子串「活着没意思」漏掉，实测直达 LLM。
    # R2400（R126-P2-1）：「没啥意思/没什么意思」补进来（软层物件
    # 豁免兜住「这游戏没啥意思」类口语）。
    r"活着.{0,3}没意思|死了算了|一了百了|活腻|没啥意思|没什么意思|"
    # R2991（巡#408）：「想跳下去/站在天台想跳」——跳楼/跳河在硬表
    # 但泛化的「跳下」裸形漏网。歧义形挪软层：跳下舞台/秋千/蹦极
    # 由物件表兜住；天台/桥/轨道等自伤向量绝不进排除表。
    r"跳下|"
    # R2992（巡#409）：自伤变体族——量词服药形（吞了三十片/整瓶）、
    # 不醒形（一觉不醒/不想醒来）、消失换序（从这世界消失）、
    # 持刀对体（拿刀对着手腕）。全歧义形入软层吃物件豁免。
    r"(吞|吃|咽|灌).{0,4}(整瓶|一把|一板|几十|三十|四十|五十|"
    r"好多|很多|全部|所有)|"
    # 「一觉不醒/不想醒来」撤回——「昨晚一觉不醒到天亮」是睡好觉
    # 良性形，且晨起物件入共享表会豁免「早上起来活着没意思」真信号。
    r"世界.{0,4}消失|消失.{0,4}世界|"
    r"拿刀.{0,4}(手|腕|脖|喉|脉)|"
    # 「割自己」有农务良性义（割自家麦子/韭菜），挪软层吃物件豁免。
    r"割自己|"
    # R2996（巡#413）：农药名（敌敌畏/百草枯——除草语境靠物件表）
    # 与诗意意念形（去天台算了/站楼顶边缘——天台刻意不进物件表）。
    r"敌敌畏|百草枯|喝.{0,3}毒药|"
    r"去.{0,3}(天台|楼顶|桥).{0,4}算了|"
    r"(楼顶|天台|桥).{0,3}边缘|"
    # R3066（巡#483）：谐音/黑话形——「想紫砂了」=想自杀、「想重
    # 开了」=重启人生黑话。必带语气后缀，「想买紫砂壶」「想重开
    # 一局游戏」不中（壶/局不占后缀位；游戏语境另吃物件豁免）。
    r"想紫砂[了啦吧]|想重开[了啦吧]", re.IGNORECASE)
_CRISIS_OBJ_PAT = re.compile(
    r"电脑|手机|剧|综艺|游戏|网|车|机器|电池|冰箱|代码|程序|软件|文件|"
    r"快递|外卖|爱豆|偶像|交通|航班|火车|课|班|题|作业|考试|"
    r"书|小说|电影|片子|番|漫|视频|"
    r"多肉|植物|宠物|猫|狗|鸟|鱼|花|虫|乌龟|仓鼠|基金|股票|痘|拖延|懒|"
    # R2400（R128-P1-10）：生活域物件——「这工作/日子/生活/婚姻/人生
    # 没啥意思」是吐槽不是求助，全被软词拦成危机干预。
    r"工作|日子|生活|婚姻|人生|学业|感情|事业|恋爱|爱情|"
    r"周|月|年|天气|饭|觉|歌|舞|妆|穿搭|发型|指甲|皮肤|身材|"
    # R2991：「跳下」的玩耍物件——舞台谢幕/蹦极/秋千/床沙发台阶
    # 均非自伤语境；天台/桥/轨道/楼/河等自伤向量刻意不收。
    r"舞台|蹦极|秋千|坡|台阶|床|桌|凳|沙发|飞机|公交|马|滑板|矮墙|"
    # R2992：吞量词的食物形（三十颗葡萄/整瓶可乐）、割自己的
    # 农务形（自家麦子/韭菜/庄稼）、拿刀的厨房形（萝卜/西瓜/纸）。
    # 拒收词：闹钟/早上/起床（会豁免晨重抑郁真信号）、草/苗/丸/
    # 瓜/糖（粗口与常见词误豁免）、一觉不醒族（睡好觉良性形）。
    r"葡萄|饺子|汤圆|果冻|可乐|苹果|"
    r"麦子|稻|韭菜|庄稼|"
    r"萝卜|西瓜|水果|纸|胶带|"
    # 「消失的世界纪录片」——影视语境豁免（片子/电影已收，补纪录片）。
    r"纪录片|纪录|"
    # R2996：百草枯/敌敌畏的农务语境——除草/菜地/果园/打药豁免。
    r"除草|菜地|农田|果园|打药|杀虫")
_CRISIS_SEG_PAT = re.compile(r"[，。！？；,.!?\n;~～…]+")
# 并集形态仍供 facts 过滤用（坐标事实里的危机词一律剥除，物件语境
# 也无须入上下文）。
_CRISIS_PAT = re.compile(
    _CRISIS_HARD_PAT.pattern + "|" + _CRISIS_SOFT_PAT.pattern,
    re.IGNORECASE)


def _is_crisis(msg: str) -> bool:
    """危机自伤判定——硬词全语境；软词分句判、物件语境豁免
    （「电脑死了算了」「这班累死了算了」不是求助）。"""
    # R2524：零宽字符剥掉再判——「想\u200b死」此前绕过硬词命中。
    # R2995：归一升级——剥零宽之外再繁折简（自殺/輕生/抑鬱接住）。
    # R3066：词内插符绕闸（自.杀/不想 活了）——硬词改判压平形态；
    # 软词仍按分句（物件豁免要「同句」作用域），但每个分句压平判、
    # 相邻两片并查兜住「死了.算了」被标点切开的插符形。
    msg = _norm_cs(msg)
    msg_flat = _norm_cs_flat(msg)
    for _h in _CRISIS_HARD_PAT.finditer(msg_flat):
        # R2400（R128-P1-10）：「想死你了/想死我了/想死她了」是高频
        # 撒娇语气——想死+人称代词不算求助；裸「想死了」不豁免（含
        # 真危机可能）。其余硬词照旧全语境接住。
        if _h.group(0) == "想死" and re.match(
                r"[你他她](?:了|啦)?|我了|我啦",
                msg_flat[_h.end():_h.end() + 2]):
            continue
        return True
    _segs = [_norm_cs_flat(_s) for _s in _CRISIS_SEG_PAT.split(msg)]

    def _soft_hit(t: str) -> bool:
        return bool(_CRISIS_SOFT_PAT.search(t)
                    and not _CRISIS_OBJ_PAT.search(t))

    for _i, _seg in enumerate(_segs):
        if _soft_hit(_seg):
            return True
        if _i + 1 < len(_segs) and _soft_hit(_seg + _segs[_i + 1]):
            return True
    return False

# R233g（R44-P0-3）：非自伤的生死/重病问法（绝症/活多久/亲人会不会走）
# 不属于危机自伤，但同样不该交给模型即兴——确定性转介，语气放稳。
# R233r（R49-Top5-3）：拆硬词/软词/排除词三层——软词（会不会死/
# 治得好吗/晚期）命中时若语境是宠物/植物/物件/拖延梗，不触发转介。
_SENSITIVE_HARD_PAT = re.compile(
    r"绝症|癌症|病危|临终|会不会去世|会去世|存活率|要死了|病死|"
    r"癌.{0,4}晚期|晚期.{0,4}癌|"
    # R2939（巡#356）：家暴/侵害求助此前两层都不中——危机表只收自伤，
    # 用户披露「被家暴/被霸凌/性骚扰」会拿到占卜腔回复而非转介。
    # 硬词只收无歧义词形；歧义词（打我/跟踪/霸凌）挪软层吃排除词。
    r"家暴|家庭暴力|殴打|虐待我|校园暴力|性骚扰|动手打我|猥亵我|"
    # R2992（巡#409）：受害形归纳——「被人X」插字此前全漏（被人强吻/
    # 被人侵犯/被人猥亵）。被+0~2字+受害词族一层收；X我形单列。
    r"被.{0,2}(虐待|强奸|性侵|猥亵|侵犯|强吻|迷奸|下药|胁迫|"
    r"勒索|恐吓|威胁)|强吻我|勒索我|恐吓我|威胁我|"
    # R2996（巡#413）：「被下了药」——被+了插字漏被下药；囚禁/
    # 裸照/艳照类名词零歧义入硬表。
    r"被.{0,2}下.{0,2}药|囚禁|非法拘禁|裸照|私密(照|视频|录像)|"
    r"艳照", re.IGNORECASE)
_SENSITIVE_SOFT_PAT = re.compile(
    # R2400（R123-P1-3）：「寿命」硬词误伤——「手机电池寿命」「冰箱寿命」
    # 实测收到医疗转介。挪软词层吃排除词表（人寿命仍可敏：排除词不含人）。
    r"还能活|活多久|会不会死|会死吗|晚期|治得好吗|寿命|"
    # R2991（巡#408）：「查出肿瘤/肿瘤指标」——硬表只到癌绝症，
    # 肿瘤披露（含良性）同样值得「先听医生的」转介而非占卜腔；
    # 宠物/新闻/剧情语境由排除表兜住。
    r"肿瘤|"
    # R2939（巡#356 续）：「男朋友打我/有人霸凌我/被人跟踪」——裸词在
    # 快递/电话/游戏/新闻语境由排除词兜住（打我电话≠求助）。
    r"打我|霸凌|跟踪|"
    # R2992（巡#409）：重病全族与侵害歧义形入软层——新闻/剧情/
    # 宠物语境由排除表兜（「刷到白血病新闻」不该拿转介腔）；
    # 「被灌醉」有酒局吐槽良性义、摸体/施害角色按复合形收。
    r"白血病|尿毒症|心梗|脑梗|中风|脑溢血|化疗|透析|洗肾|"
    # ICU 裸形会撞英文词内子串（particular 里藏 icu）——前后非字母
    # 才算独立缩写（进ICU 前字是汉字仍命中）。
    r"(?<![a-z])ICU(?![a-z])|"
    r"重症监护|急救室|病危通知书|器官移植|骨髓移植|截肢|"
    r"肝硬化|肾衰竭|心衰|被灌醉|"
    # 摸体只收受害向复合形——「摸鱼摸到腰疼」摸鱼梗不该拿转介腔。
    r"(被摸|摸我|摸我的|摸过).{0,3}(大腿|胸|腰|屁股|臀部|私处|下面|裆)|"
    r"摸过我|"
    r"(继父|干爹|老师|教练|上司|老板|客户|教官|师父|房东|司机|"
    r"前夫|网友|领导).{0,8}(摸我|摸过|侵犯|猥亵|强吻|睡我|"
    r"上我|脱我|压我)|"
    # R2996（巡#413）：强迫/动手动脚/性勒索/家暴方法词/P UA 五族。
    # 强迫+亲密行为复合形（被逼做PPT 不带亲密词不中）；动手动脚
    # 咸猪手成语；威胁+发片/被拍+隐私 sextortion；掐脖扇耳光
    # 方法词裸收。
    r"动手动脚|咸猪手|"
    r"(强迫|逼迫|被逼|被迫).{0,6}(发生关系|那种事|这种事|献身|"
    r"脱.{0,2}衣|陪睡|上床)|"
    r"逼我.{0,4}(脱|睡|上床|陪|献身|发生)|"
    r"威胁.{0,4}(照片|视频|录像|曝光|群发|发我|发出去|隐私|图)|"
    r"被.{0,3}(拍|录).{0,4}(照片|视频|录像|隐私|裸|私)|"
    r"掐.{0,2}脖|扇.{0,3}(耳光|巴掌)|被.{0,2}控制|PUA|"
    # 家暴演员形——「被父母打/被老公掐脖子」：裸打只许紧贴
    # 演员（.{0,1} 防「被同学拉着打游戏」误拦），重动作放宽。
    r"被.{0,3}(爸|妈|爹|父母|老公|丈夫|男友|男朋友|前夫|老婆|"
    r"妻子|对象|伴侣|室友|同学|同事|领导|老师|继母|公婆|婆婆|"
    r"岳母).{0,1}(打(?!call|电话|游戏|卡|球|牌|车|字|折|喷|呼|枪|"
    r"拳|麻|工|听|赌|扮|扫|算|瞌|蚊|鼓|针|饭|水)|揍|扇|掐|踹|"
    r"踢|抽|砸)|"
    r"被.{0,3}(爸|妈|爹|父母|老公|丈夫|男友|男朋友|前夫|老婆|"
    r"妻子|对象|伴侣|室友|同学|同事|领导|老师|继母|公婆|婆婆|"
    r"岳母).{0,4}(打我|打他|打她|关起来|锁.{0,2}我|扒.{0,2}我|"
    r"掐.{0,3}脖|扇.{0,3}(耳光|巴掌))|"
    # 「被按在床上打」——无演员词的方法形；按摩不带打不中。
    r"被按.{0,4}(打(?!call|电话|游戏|卡|球|牌|车|字|折|喷|呼|枪|"
    r"拳|麻|工|听|赌|扮|扫|算|瞌|蚊|鼓|针|饭|水)|揍|掐|扇|踹|"
    r"踢|抽|砸)|"
    # R3071（巡#488）：求医问药类——「该吃什么药/哪种药管用/
    # 布洛芬有用吗」此前放行拿占卜腔用药建议（医疗建议不该
    # 出自解忧铺，spec 医疗边界）。只收选择/效用问法——「我
    # 刚吃了退烧药」陈述形不中；真实药名须配问法尾才收。
    r"(什么|哪种|哪个|哪款|啥)药|药.{0,4}(推荐|管用|有用|好使|"
    r"副作用|哪种好|怎么选|怎么买)|"
    r"(布洛芬|对乙酰氨基酚|阿司匹林|抗生素|避孕药|止痛药|"
    r"退烧药|安眠药|降压药|降糖药|胰岛素|头孢|蒙脱石散|"
    r"奥美拉唑).{0,8}(有用吗|管用|好吗|行吗|可以|能不能|"
    r"要不要|副作用|伤.{0,2}身|怎么吃|怎么选|哪种)", re.IGNORECASE)
_SENSITIVE_EXCLUDE_PAT = re.compile(
    r"多肉|植物|宠物|猫|狗|鸟|鱼|花|虫|乌龟|仓鼠|手机|电池|电脑|游戏|"
    r"痘|拖延|懒|基金|股票|冰箱|车|"
    # R2939：打我/跟踪/霸凌 的口语与新闻语境豁免——打我电话/打我账号/
    # 快递跟踪/物流跟踪/校园霸凌新闻均非求助披露。
    r"电话|账号|物流|快递|外卖|新闻|剧情|"
    # R2992：重病词入软层后影视/文学语境也须豁免——「看化疗纪录片」
    # 「白血病电视剧」「霸凌小说」是作品讨论不是披露。
    # 只收完整词「纪录片」——裸「纪录」会豁免「病历纪录」医疗文书
    # 语境（可能伴随真披露）；危机物件侧无此风险可留裸形。
    r"纪录片|电影|电视剧|小说|歌词")

# R2345（R61-P1-1）：facts 信道黑名单原来只有 6 个词面子串——
# 「服从/规则/ignore/prompt/输出英文」全部直达 user 位。扩为指令词
# 族（中英）+ 危机/敏感词（P1-2：危机语义经 facts/昵称绕过确定性
# 转介——坐标事实不是自伤语境，剥行即可不触发转介）。
# R2400（R135-P0-1）：先归一再查——繁体「黃曆」、零宽/空格拆字
# （「黄\u200b历」「黄 历」）原样绕过词面子串。入闸文本统一
# 剥零宽/控制字+繁折简，词形之间容忍空白。
_FACT_ZW = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff\x00-\x1f\x7f-\x9f]")
# 繁折简小表——只须覆盖禁语/注入词面里的高频繁体字（防绕过用，
# 不做通用繁简转换；未收字原样通过）。
_FACT_T2S = dict(zip(
    "曆歷體從規詞獄視設輸譯語說聽確給讓該當檔稱講讀寫開關閉啟這個們為與屬統權數據歲樣點條順嚴厲師專級員責評價處務態實認詳後喚執調試頁碼憑記錄監斷決變論訴訊誤導遺攜帶類別應擬偽裝竊臺賬號密鑰証訪終腳進環目錄徑內刪擇縮復復歷塗館鷄鴨鵝鶴",
    "历历体从规词狱视设输译语说听确给让该当档称讲读写开关闭启这个们为与属统权数据岁样点条顺严厉师专级员责评价处务态实认详后唤执调试页码凭记录监断决变论诉讯误导遗携带类别应拟伪装窃台账号密钥证访终脚进环目录径内删择缩复复历涂馆鸡鸭鹅鹤"))
# R2995（巡#412）：危机/敏感判定归一化要吃的繁体用字——「自殺/
# 腫瘤/強吻/猥褻/性騷擾/會不會死/還能活」全族。只收词族实际
# 用字，不收著（著→着 会误伤「著名/著作」，活著走字符组处理）。
_FACT_T2S.update(zip(
    "殺輕樓鬱燒藥腫絕臨強姦褻騷擾蹤脅嚇毆動繼練東機網領脫壓襠發飛牆餃湯圓凍樂蘋麥莊蘿蔔紙膠紀聞劇電綜藝遊戲車軟遞愛課題業書頻寵貓鳥魚蟲烏龜倉學戀氣飯覺妝髮膚話醫傷殘會嗎妳還對脈診術療極時風腎過膩厭複",
    "杀轻楼郁烧药肿绝临强奸亵骚扰踪胁吓殴动继练东机网领脱压裆发飞墙饺汤圆冻乐苹麦庄萝卜纸胶纪闻剧电综艺游戏车软递爱课题业书频宠猫鸟鱼虫乌龟仓学恋气饭觉妆发肤话医伤残会吗你还对脉诊术疗极时风肾过腻厌复"))

# R3069（巡#486）：出侧禁语词族繁体——「註定/孤獨/沒戲/必離/相剋/
# 災劫/大難/趕緊分/斷聯/必須/建議/約炮」模型吐出时此前漏折。
_FACT_T2S.update(zip(
    "註獨沒離剋災難趕緊聯須議約罷單",
    "注独没离克灾难赶紧联须议约罢单"))


def _norm_cs(msg: str) -> str:
    """危机/敏感判定的归一形态：剥零宽 + 繁折简——词内插字与
    繁体输入不再绕闸（R2995）。判定专用，不改上屏文本。"""
    s = _OUT_ZW.sub("", msg or "")
    return "".join(_FACT_T2S.get(c, c) for c in s)

# R3066（巡#483）：词内插符绕闸——「自.杀」「不想 活了」「被猥.亵」
# 「zi sha」这类空白/标点/装饰拆词形此前全放行。判定用的第二形态：
# 结构化归一（保分句符供软词物件豁免）之外再给一个压平形态。
# 变调字母（sǐ/sì）先归 ascii 再走压平——拼音混写是同龄层真实写法。
_TONE_MAP = str.maketrans(
    "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü",
    "aaaaeeeeiiiioooouuuuuuuuu")
_FLAT_KEEP = re.compile(r"[^0-9a-zA-Z一-鿿]+")

# 拼音/混写→汉字折叠（压平后、判定前）：每条都是无歧义形，字母
# 边界防「想sign」类误折。折叠后走既有词表+豁免——「想si你了」
# 与「想死你了」同享人称豁免。
_PINYIN_FOLD = (
    (re.compile(r"(?<![a-z])zisha(?![a-z])", re.I), "自杀"),
    (re.compile(r"(?<![a-z])zi杀(?![a-z])"), "自杀"),
    (re.compile(r"(?<![a-z])gewan(?![a-z])", re.I), "割腕"),
    (re.compile(r"([想要])si(?![a-z])", re.I), r"\g<1>死"),
    (re.compile(r"不想huo(?![a-z])", re.I), "不想活"),
    (re.compile(r"huo[着著]?不下去", re.I), "活不下去"),
    (re.compile(r"huo[着著]好累", re.I), "活着好累"),
    (re.compile(r"跳lou(?![a-z])", re.I), "跳楼"),
    (re.compile(r"(?<![a-z])saorao(?![a-z])", re.I), "性骚扰"),
    (re.compile(r"(?<![a-z])wexie(?![a-z])", re.I), "猥亵"),
    (re.compile(r"(?<![a-z])qj(?![a-z])", re.I), "强奸"),
)


def _norm_cs_flat(msg: str) -> str:
    """判定专用的压平归一：_norm_cs 之上再变调归 ascii + 剥全部
    非字词符 + 拼音折叠。「自.杀/不想 活了/zi sha/想sǐ」同归正形。
    分句结构已灭——只供硬词/单串判定，软词分句走结构形态。"""
    s = _norm_cs(msg).lower().translate(_TONE_MAP)
    s = _FLAT_KEEP.sub("", s)
    for _rx, _rep in _PINYIN_FOLD:
        s = _rx.sub(_rep, s)
    return s

_FACT_BAN_PAT = re.compile(
    # 指令词族（中英）+ 危机/敏感词（另见 _CRISIS_PAT/_is_sensitive）。
    # 坐标事实只该是生辰/称呼/盘面字段——「回答/输出/语言」进事实行
    # 全是注入（R61-P1-1 实测：昵称「小鱼。用英文回答」原文送达）。
    r"黄\s*历|忽略|忘记|指令|服\s*从|规\s*则|提示\s*词|越\s*狱|扮演|假装|"
    r"不理会|无视|不管.{0,6}要求|不要理|人设|回答|输出|翻译|"
    r"英文|英语|日语|中文|语言|改成|换成|用.{0,4}说|"
    # R2400（R135-P0-1）：仿冒权威判定/系统身份的形状词——坐标里出现
    # 「判定/权威/系统/角色/要求/说法」概非合法坐标（坐标只该是
    # 生辰/称呼/盘面字段，这些词天然不进）。
    r"判\s*定|裁\s*[定断决]|权\s*威|系\s*统|官\s*[方网]|角\s*色|要\s*求|"
    r"说\s*法|办\s*法|身\s*份|遵\s*守|执\s*行|"
    r"instruction|ignore|forget|system|prompt|jailbreak|rules?|"
    r"disregard|override|pretend|english|japanese|"
    # R2400（R135-P0-1 续）：英文注入形状
    r"act\s*as|obey|from\s*now\s*on|don'?t\s*(listen|obey|follow)|"
    r"listen\s*to|assistant|developer\s*mode|new\s*instruction|"
    # R2938（巡#355）：DAN 系开场白——坐标事实只该是中文生辰/称呼/
    # 盘面字段，「you are now…」英文句式天然非合法坐标，无过杀面。
    r"you('re|\s+are)\s+now|"
    # R2400（R135-P0-4）：内部外形串——后端键名/SQL/异常栈/服务器路径
    # 进 prompt 会诱发模型复述「内部细节」或按注入语义接话。
    r"calc\.|select\s+.+\s+from|insert\s+into|drop\s+table|traceback|"
    r"corpus\.db|knowledge\.db|/home/|/users/|/app/|"
    r"[a-z]:[\\/]|\w+\.py\s*(?:line|:)|file\s+\"|"
    # R2524（审-LLM-P2-3）：恐吓/判死词进过滤——「林注定」「林必离」
    # 类候选名此前过闸喂模型，诱发模型输出正好撞出侧禁语表的词。
    r"注定|必离|没戏|克夫|克妻|孤独终老", re.IGNORECASE)


def _fact_norm(f: str) -> str:
    """校验用归一文本：剥零宽/控制字 + 繁折简（不改写原文，仅查用）。"""
    return "".join(_FACT_T2S.get(c, c) for c in _FACT_ZW.sub("", f))


# R2524（审-LLM-P1-1）：输出侧零宽/不可见字表——比 _FACT_ZW 少了
# \x00-\x1f（含 \n\r\t）与 \x7f-\x9f 里的换行族，剥它会把段落换行
# 一起吃掉；只收对显示文本百害无一利的隐形格式字。
_OUT_ZW = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]")


def _scan_form(s: str) -> str:
    """出侧闸门扫描用归一形态（只用于判定，不改上屏文本）：
    剥 markdown 记号/零宽/全部空白 + 繁折简——「注**定**」「注\u200b定」
    「你 应 该」「註定」式绕闸写法拼回真词再交给禁语/内部串闸。"""
    s = _OUT_ZW.sub("", s)
    s = re.sub(r"[*_`~]+", "", s)
    s = re.sub(r"\s+", "", s)
    return "".join(_FACT_T2S.get(c, c) for c in s)

# R3069（巡#486）：弱分隔符插字绕出侧闸——「注.定」「必-离」
# 「断/联」模型吐出直通上屏。只剥装饰类分隔（句读 。，；：
# 不剥——跨句拼接会误伤「注：定期」式合法文本）；点也剥，
# 内部串闸继续在带点的 _scan_form 上跑（calc\\. 不被破坏）。
_WEAK_SEP = re.compile(r"[.\-_/·'\"、．∙•・‒–—―]+")


def _scan_flat(s: str) -> str:
    """出侧禁语扫描的更强归一：_scan_form 之上再剥弱分隔符——
    禁语词（注定/必离/孤独）内插装饰符拼回真词。只用于
    _BANNED_OUT_PAT/_BANNED_QUOTE_PAT/_CHAT_BANNED_PAT 判定。"""
    return _WEAK_SEP.sub("", _scan_form(s))


def _fact_line(f) -> str:
    """渲染成 prompt 行前的兜底清洗：换行压成空格防伪造行边界。"""
    return re.sub(r"[\r\n]+", " ", str(f)).strip()


def _fact_is_safe(f: str) -> bool:
    """坐标事实放行闸：仿冒权威判定/指令注入/危机词一律剥除。

    R230a-41：客户端 facts 是 user 位上下文块（降权框），但仍做词表
    过滤收窄注入面；权威判定只走 verdict_facts 一条道。"""
    if not isinstance(f, str) or not f.strip():
        return False
    # R2400（R135-P0-3）：换行可伪造事实行边界——「x\n- 黄历判定：宜」
    # 一条注成两条权威行，含换行的事实行整体剥除。
    if "\n" in f or "\r" in f:
        return False
    _n = _fact_norm(f)
    # R3068（巡#485）：词内插符/拼音规避经 facts 混入——「她叫自.杀
    # 小队」「昵称zi sha」结构化词表查不到插符形，原文送进 LLM
    # 上下文块。补压平形态同查 BAN/CRISIS 两表（剥行语义不变，
    # 只是上下文更干净）。
    _nf = _norm_cs_flat(f)
    if _FACT_BAN_PAT.search(_n) or _FACT_BAN_PAT.search(_nf) \
            or _n.lstrip().lower().startswith("system"):
        return False
    # R61-P1-2：危机/生死词经 facts 混入会绕过 message 位的确定性
    # 转介——剥掉该行（它是「坐标事实」不是求助语境，不触发转介）。
    if _CRISIS_PAT.search(_n) or _CRISIS_PAT.search(_nf) \
            or _is_sensitive(_n):
        return False
    return True


# R3124c（specs/012-P0）：回复↔判词方向矛盾判定词表。
# 判词侧分负/正两族（同判词混出现时不判——混合盘天然两向都有）。
_VD_NEG = re.compile(
    r"不合适|相冲|相克|相刑|偏弱|偏淡|吃力|该退|宜守|不宜|"
    r"磨人|高开低走|压着你|先想清楚")
_VD_POS = re.compile(
    r"合拍|相生|比和|中上|上上|很旺|正旺|顺|宜|正缘|越处越|天作")
_OUT_CONTRA_POS = re.compile(
    r"很合适|特别合适|十分合适|非常合适|天作之合|绝配|天生一对|"
    r"命中注定的一对|放心在一起|大胆去爱|大胆在一起|一定会幸福|"
    r"肯定能成|一定能成")
_OUT_CONTRA_NEG = re.compile(
    r"不合适|不太合适|趁早分|肯定会散|注定没戏|没戏|走不到头|"
    r"放弃吧|不会幸福|成不了|趁早放手")


# R3126（specs/013-P1）：问题类型分类——调研塔罗师「问题梳理位」+
# 咨询释义技术：回复结构跟着问题类型走，而不是一律同构答。
# 倾诉先接情绪、求解先复述确认再给方向、验证先给口径再给理由。
_CHAT_INTENT_VENT = re.compile(
    r"好烦|烦死|难过|委屈|想哭|崩溃|撑不住|好累|失眠|分手|吵架|冷战|"
    r"被裁|失业|焦虑|迷茫|emo|不开心|难受|郁闷|压力大|想哭|崩溃|心碎")
_CHAT_INTENT_DECIDE = re.compile(
    r"该不该|要不要|能不能|怎么办|怎么选|如何做|值得吗|还来得及|"
    r"怎么破|怎么解决|选哪个|去不去|辞不辞|分不分|复合|表白")
_CHAT_INTENT_VERIFY = re.compile(
    r"是不是|会不会|真的吗|准吗|合适吗|配不配|有戏吗|喜欢我吗|爱我吗|"
    r"在想我吗|靠谱吗|信不信得过|对不对")


def _chat_intent(msg: str) -> str:
    """倾诉 > 求解 > 验证，情绪在场永远优先接住。"""
    m = _norm_cs_flat(msg or "")
    if not m:
        return ""
    if _CHAT_INTENT_VENT.search(m):
        return "vent"
    if _CHAT_INTENT_DECIDE.search(m):
        return "decide"
    if _CHAT_INTENT_VERIFY.search(m):
        return "verify"
    return ""


# R3126（specs/013-P5）：会话内复问识别——同一 session 里同一主题
# 出现第二次，让她知道小满记得这条线在聊什么（Moonly 飞轮的
# 最小实现：不建持久画像，先让模型看到重复主题）。
_CHAT_THEME: list[tuple[str, "re.Pattern"]] = [
    ("感情", re.compile(r"感情|恋爱|喜欢|桃花|对象|男朋友|女朋友|暗恋|"
                        r"复合|相亲|结婚|暧昧|crush|他对我|分手|失恋|"
                        r"前任|脱单|表白")),
    ("工作", re.compile(r"工作|职场|老板|同事|升职|跳槽|面试|裁员|加班|"
                        r"试用期|转正|实习|兼职|简历|入职|离职")),
    ("学业", re.compile(r"学业|考试|考研|考公|成绩|论文|学校|读书|专业")),
    ("财运", re.compile(r"钱|财|工资|收入|投资|副业|存款|花销")),
    ("人际", re.compile(r"朋友|闺蜜|室友|家人|父母|社交|关系")),
    # R3147：受众画像（15-25 女）高频的「情绪/自我」类此前无归类——
    # emo/内耗/迷茫 是这一代的核心语汇，漏收画像等于没画像。
    # 非危机级词（自伤类由危机闸另拦），可入画像。
    ("情绪", re.compile(r"焦虑|迷茫|内耗|emo|难过|孤独|自卑|压力|"
                        r"崩溃|失眠|容貌|减肥|自我|开心|不开心")),
    # R3184：睡眠/梦主题——聊梦此前无归类，画像少「睡不好」线。
    # 不用裸「梦」（「梦想」误伤）；失眠留在情绪（先命中）。
    ("睡眠", re.compile(r"梦见|梦到|做梦|噩梦|昨晚梦|睡不着|睡不好|"
                        r"睡眠|熬夜|睡醒")),
    ("运势", re.compile(r"运势|运气|今年|最近|大运|流年|水逆")),
]


def _chat_theme(msg: str) -> str:
    m = _norm_cs_flat(msg or "")
    for name, pat in _CHAT_THEME:
        if pat.search(m):
            return name
    return ""


_CHAT_INTENT_HINT = {
    "vent": "她这条更像在倾诉，开头先接住情绪（把她说的事用你的话"
            "复述一遍，「听起来真的挺…的」这种），别上来就讲道理或"
            "甩建议；情绪接住了再轻轻给一点能做的事。",
    "decide": "她这条是在要答案，开头先用一句把她的事复述成确认句"
              "（「你是在纠结要不要…对吧」这种），然后直接给方向："
              "盘/判词说了什么就说什么，再给能做的第一步，别绕。",
    "verify": "她这条是在要确认，先给明确口径（盘/判词怎么算就怎么"
              "说，是就是、不是就不是），再补一两句理由。",
}


def _chat_verdict_contra(text: str, rverdicts: list) -> str | None:
    """回复与卡面判词方向矛盾判定。

    返回 'pos_over_neg'（判词负、回复硬说正）/'neg_over_pos'
    （判词正、回复硬说负）/None。判词双向混存时不判——混合盘
    两向都真，无从判矛盾。
    """
    if not text or not rverdicts:
        return None
    _t = _scan_flat(text)
    _vs = [str(v) for v in rverdicts]
    _neg_v = any(_VD_NEG.search(v) for v in _vs)
    _pos_v = any(_VD_POS.search(v) for v in _vs)
    if _neg_v and not _pos_v and _OUT_CONTRA_POS.search(_t):
        return "pos_over_neg"
    if _pos_v and not _neg_v and _OUT_CONTRA_NEG.search(_t):
        return "neg_over_pos"
    return None


def _verdict_anchor_reply(rverdicts: list) -> str:
    """判词矛盾兜底回复：按判词原句确定性重组，方向必一致。"""
    _v = ""
    for f in rverdicts or []:
        s = str(f)
        if "判词" in s:
            _v = s.split("：", 1)[-1].strip()
            break
    if not _v and rverdicts:
        _v = str(rverdicts[0])[:80]
    return ("照你那张卡的判词直说。" + (_v or "盘上写得挺清楚") +
            "。这可能跟你想听的不一样，但盘就是这么落的；"
            "哪里硌、怎么处，咱可以接着聊。")


def _is_sensitive(msg: str) -> bool:
    """生死/重病敏感判定，聊天层与问一嘴（interpreter）共用一个口径。"""
    # R2524：同 _is_crisis——零宽写法绕过敏感词命中。
    # R2995：归一升级——繁折简（腫瘤/強吻/絕症接住）。
    # R3066：词内插符绕闸（被猥.亵/肿.瘤）——改判压平形态；
    # 排除词同判压平（物件豁免语义无分句作用域，行为不变）。
    msg_flat = _norm_cs_flat(msg)
    if _SENSITIVE_HARD_PAT.search(msg_flat):
        return True
    return bool(_SENSITIVE_SOFT_PAT.search(msg_flat)
                and not _SENSITIVE_EXCLUDE_PAT.search(msg_flat))
_SENSITIVE_REPLY = ("这个话题我真接不了，不是不愿意，是它不该靠占卜来定。"
                    "身体或心里难受的话，医生和信得过的人才是最该找的。"
                    "想聊点别的，小满都在。")

# R230a-6（R12-P1-4）：chat 替换闸与出站共用禁语表同宽（此前漏
# 「没戏/必离/注定孤独/他克你」）。
_CHAT_BANNED_PAT = _BANNED_OUT_PAT

_chat_sessions: dict[str, dict] = {}
_chat_lock = threading.Lock()
# 每会话一把调用锁：历史快照→LLM 往返→落历史整段串行化。
# 否则并发同 session 消息按「完成先后」而非「发出先后」落库，
# 慢请求先到会时序倒置（审查轨 chat-flow）。
_chat_call_locks: dict[str, threading.Lock] = {}


def _session_lock(session_id: str) -> threading.Lock:
    with _chat_lock:
        lk = _chat_call_locks.get(session_id)
        if lk is None:
            lk = _chat_call_locks[session_id] = threading.Lock()
        return lk


@contextlib.contextmanager
def _held_session_lock(session_id: str):
    """拿到「官方」会话锁再进临界区。

    R2524（审-LLM-P2-2）：GC 在「持锁者 release → 等待者 acquire」的
    缝隙里会把未锁定的锁行逐出表，新来者另建一把——等待者与后来者
    各握一把锁并行跑「快照→LLM→落历史」，时序倒置复发。拿到锁后
    回表里核对自己还是不是官方锁，不是就放掉重来。"""
    lk = _session_lock(session_id)
    lk.acquire()
    try:
        while True:
            with _chat_lock:
                if _chat_call_locks.get(session_id) is lk:
                    break
            lk.release()
            lk = _session_lock(session_id)
            lk.acquire()
        yield
    finally:
        lk.release()


def _gc_chat_sessions() -> None:
    now = time.monotonic()
    # R3225：session 缺 "updated" 此前 KeyError——GC 跑在每条 chat 首部，
    # 一条畸形会话=永久全站聊天停摆（进程重启才解）。缺键按超龄逐出。
    stale = [sid for sid, s in _chat_sessions.items()
             if now - s.get("updated", 0) > _CHAT_SESSION_TTL_S]
    for sid in stale:
        _chat_sessions.pop(sid, None)
        lk = _chat_call_locks.get(sid)
        if lk is not None and not lk.locked():
            _chat_call_locks.pop(sid, None)
    if len(_chat_sessions) > _CHAT_MAX_SESSIONS:
        _over = len(_chat_sessions) - _CHAT_MAX_SESSIONS
        # R230a-6（R12-P3-2）：逐出时跳过该 sid 锁仍握着的会话——那说明
        # 有在跑任务；把它逐了，回复交付但历史静默蒸发。多出的超额量
        # 下一次 GC 再收（locked 会话终究会解锁）。
        _victims = [sid for sid in sorted(
            _chat_sessions, key=lambda s: _chat_sessions[s].get("updated", 0))
            if not (_chat_call_locks.get(sid) and
                    _chat_call_locks[sid].locked())][:_over]
        for sid in _victims:
            _chat_sessions.pop(sid, None)
            lk = _chat_call_locks.get(sid)
            if lk is not None and not lk.locked():
                _chat_call_locks.pop(sid, None)
    # 锁表同帽：危机/非法消息也会先建锁，无会话可挂——超帽删未锁定的。
    # 任意 sid 都能占一格，与 sessions 分开计（防「只发被拒消息」型洪泛）。
    if len(_chat_call_locks) > _CHAT_MAX_SESSIONS * 2:
        _lk_over = len(_chat_call_locks) - _CHAT_MAX_SESSIONS * 2
        for sid in [s for s, lk in _chat_call_locks.items()
                    if not lk.locked()][:_lk_over]:
            _chat_call_locks.pop(sid, None)


def chat(session_id: str, user_msg: str,
         facts: list[str] | None = None,
         verdict_facts: list[str] | None = None,
         config: dict | None = None, _transport=None,
         verdict_day: str | None = None,
         result_verdicts: list[str] | None = None,
         _task_started=None) -> str | None:
    """多轮陪伴对话：session 内存上下文 + 用户消息 → 回复文本。

    facts：前端透传的坐标事实，只作「话题参考」。
    verdict_facts：后端算好的权威判定（黄历判定等）——独立信道，
        客户端永远摸不到（R12-P2-2：此前按「含『黄历判定』子串」升格，
        任客户端可伪造权威事实）。
    verdict_day：判定所锚定的日子（YYYY-MM-DD，浏览器本地日）——跨日后
        存檔判定自动作废，昨天算的「明天」不会今天继续注入。
    危机关键词命中 → 不调 LLM 直接返回固定转介文案（判据 b 硬兜底）。
    会话超轮数上限 → 返回温和收尾文案（不再消耗 LLM）。任何失败 None。
    """
    cfg = config or load_config()
    if cfg is None:
        return None
    msg = (user_msg or "").strip()
    if not msg or not session_id:
        return None

    # 串行化整段「快照→LLM→落历史」：同 session 并发按到达顺序完成，
    # 而非按 LLM 返回快慢（审查轨 chat-flow 实测时序倒置）。
    with _held_session_lock(session_id):
        with _chat_lock:
            # R2524（审-LLM-P3）：GC 先跑——fresh 采样在逐出之后，
            # 刚被 TTL 逐掉的会话如实报 fresh（前端补「记不全」分隔），
            # 此前标记在 GC 前打：陈旧行还在 → fresh=False → 上下文
            # 其实被清了却没任何提示。
            _gc_chat_sessions()
        # R2511（审-SV-P2）：started 标记挪到拿到会话锁之后——此前在
        # spawn 线程开头就打，排队等锁期间 queued=false 谎报，前端
        # 40s 轮询预算实际从入队起算（与注释语义相反）。
        if _task_started is not None:
            _task_started()
        with _chat_lock:
            sess = _chat_sessions.setdefault(
                session_id, {"messages": [], "updated": time.monotonic()})
            # R3227（R3225 同型）：脏会话有 updated 无 messages 时
            # sess["messages"] KeyError——该 sid 聊天永久 failed。
            sess.setdefault("messages", [])
            # R230a-6（R12-P1-2）：危机红线必须排在轮数收尾之前——此前满
            # 6 轮后发「我不想活了」会被收尾文案截胡，安全转介失效。
            if _is_crisis(msg):
                return _CHAT_REFUSAL
            # R233g：非自伤生死/重病问法——排危机之后（自伤优先走危机
            # 转介），调 LLM 之前确定性接住。
            if _is_sensitive(msg):
                return _SENSITIVE_REPLY

            if len(sess["messages"]) >= _CHAT_MAX_TURNS * 2:
                # R230a-5：到顶后每句追问同一句收尾略显机械——按追问序轮换
                # 三句确定性收尾（不换语义，仍是「今天到这里」的温和收口）。
                # messages 到顶后不再追加——用独立 closed_n 计数推进轮换
                _over = sess.get("closed_n", 0)
                sess["closed_n"] = _over + 1
                # R230d（R16-P2-7）：标记收口态——轮询端点带出 closed=True，
                # 前端据此给「开新话题」引导（此前用户只能对着复读的收尾文案
                # 干发消息，没有任何出路提示）。
                sess["closed"] = True
                # R233r（R49-P2-5）：二级收口——同一收尾池轮换满一轮后
                # 换「明天来打卡」方向钩子，不再机械转圈。
                if _over >= len(_CHAT_CLOSERS):
                    return _CHAT_CLOSERS_LATE[
                        (_over - len(_CHAT_CLOSERS))
                        % len(_CHAT_CLOSERS_LATE)]
                return _CHAT_CLOSERS[_over % len(_CHAT_CLOSERS)]

            # R230t（R32-P1-5）：历史总长截断——assistant 单条可到 8K，
            # 6 轮全量重发最坏 ~51K ≈ 5 万 token/轮。只带最近 ~4K 字符的
            # 轮次（约 2–3 轮），更远的细节模型记不住也不该烧。
            history = list(sess["messages"])
            _hb, _hkeep = 0, []
            for _m in reversed(history):
                _hb += len(_m.get("content") or "")
                if _hb > 4000:
                    break
                _hkeep.append(_m)
            history = _hkeep[::-1]
            # R2349r（R82-P2-7）：截断静默→模型不知道「更早的轮被省略
            # 了」，会对「我刚才说过…」类引用臆造。截断发生时写进人设
            # 尾巴一句实话。
            _truncated = len(_hkeep) < len(sess["messages"])
            # R230a-6（R12-P2-7）：判定事实落会话档——第 1 轮的判定在第 2
            # 轮 prompt 会消失（回复还在历史里、依据没了），模型只能自由
            # 发挥。新一轮判定覆盖旧的。
            # R230t（R32-P1-7）：本轮判定为空（没问到黄历事）→ 清档——
            # 此前话题漂移后旧「后天判定」还挂在 system 里继续注入；
            # 跨日档也作废（昨天算的「明天」今天已错位）。
            if verdict_facts is not None:
                if verdict_facts:
                    # R2400（R135-P1-3）：空白判定行（" "）也会落档注进
                    # prompt——先 strip 再收。
                    sess["verdicts"] = [f for f in verdict_facts
                                        if f and f.strip()]
                    sess["verdict_day"] = verdict_day
                else:
                    sess.pop("verdicts", None)
                    sess.pop("verdict_day", None)
            _verdicts = list(sess.get("verdicts") or [])
            if _verdicts and verdict_day and sess.get("verdict_day") \
                    and sess["verdict_day"] != verdict_day:
                # R2400（R135-P1-5b）：跨日档只置空不落删——档还挂着，
                # 后续 verdict_facts=None 的轮次也不会清。直接作废。
                _verdicts = []
                sess.pop("verdicts", None)
                sess.pop("verdict_day", None)
            # R3124b（specs/012-P0）：卡面判词层权威档——与黄历判定
            # 同信道级但语义不同：判词绑定的是「那张卡」，不锚日、
            # 整个会话期有效（聊到它就口径一致）；换新卡/明确清空
            # 才覆盖。
            if result_verdicts is not None:
                if result_verdicts:
                    sess["rverdicts"] = [f for f in result_verdicts
                                         if f and str(f).strip()]
                else:
                    sess.pop("rverdicts", None)
            _rverdicts = list(sess.get("rverdicts") or [])
            # R230t（R32-P1-8）：客户端每条消息都重发坐标 facts——存档为
            # 会话快照：相同则是重发（省一层抖动），不同（换了新盘）才更新。
            # 注入用的是快照，整个会话期内坐标都是话题锚。
            # R2400（R135-P1-5a）：入档即过闸——此前原样存档，靠渲染
            # 时每轮滤一次；恶意行会在会话期内一直被携带。只存干净行。
            _coords_new = [f for f in (facts or [])
                           if f and _fact_is_safe(f)]
            if _coords_new and _coords_new != sess.get("coords"):
                sess["coords"] = _coords_new
            _coords_snap = list(sess.get("coords") or [])

        # R228w：坐标事实与「黄历判定」分量不同——前者是话题参考
        # 「不要逐条念」，后者是已算好的权威结论必须照说。
        # R230t（R32-P2-10）：原顺序是 system(人设)→user(coords)→
        # system(verdicts)→history→user(msg)——中段 system 权重不稳，
        # coords 那条 user 没有对应 assistant 回复造成角色交错（实测
        # 「有宜面试事实仍说没查到」的结构性诱因）。改为：verdicts 并进
        # 首段 system，coords 紧贴最新消息并入同一条 user。
        _sys = _CHAT_SYSTEM
        # R233r（R49-Top5-5）：把用户本地「今天」写进人设——此前模型
        # 不知道今天是几号，聊到日期只能瞎猜。
        if verdict_day:
            _sys += ("\n今天是 " + verdict_day +
                     "（用户那边的日子），说到「今天/明天」都以这天为准。")
        if _verdicts:
            _sys += ("\n\n以下是系统已算好的黄历判定，是权威结论，"
                     "用户问到对应事项时必须照它回答、不许说没查到；"
                     "日期只能引用判定里出现的，不要自己编日子：\n- "
                     + "\n- ".join(_fact_line(f) for f in _verdicts))
        # R3124b（specs/012-P0）：卡面判词层进权威信道——此前判词只
        # 走「话题参考」facts，模型可自由发挥成与判词相反口径（用户
        # 实测「小满说的和卡面结果不一样」）。升格后：判词原句入
        # system、标明与卡面一致、禁止反驳与软化。
        if _rverdicts:
            _rv = [str(f).strip() for f in _rverdicts
                   if f and str(f).strip()][:9]
            _rv_txt = "\n- ".join(_fact_line(f) for f in _rv)
            if len(_rv_txt) > 1600:
                _rv_txt = _rv_txt[:1600].rstrip() + "……"
            _sys += ("\n\n这张卡的判词层结论是系统算好的，"
                     "和用户屏上看到的卡面逐字一致：\n- " + _rv_txt +
                     "\n聊到这张卡的事，口径必须和判词一致：判词说不合适"
                     "就照实说不合适，不许软成「看你们自己」「因人而异」；"
                     "判词说顺也别泼冷水。判词没覆盖的角度可以自由展开，"
                     "但绝不能和判词打架、不许假装没看过这张卡。")
        # R3126（specs/013-P1）：问题类型提示——回复结构跟问题走。
        _int_now = _chat_intent(msg)
        _int_hint = _CHAT_INTENT_HINT.get(_int_now)
        if _int_hint:
            _sys += "\n\n" + _int_hint
        # R3126（specs/013-P4）：情绪惯性——上轮还在倾诉，这轮她发了
        # 中性/开心的话也别秒变欢快；低落底色最多留一轮（久了就成
        # 揣测式共情）。sess 存上一轮的极性。
        if sess is not None:
            if sess.pop("last_emo_down", None) and _int_now != "vent":
                _sys += ("\n\n她刚才情绪偏低落，这轮语气保持温和、跟上"
                         "她的节奏，别突然亢奋闲聊。")
            sess["last_emo_down"] = (_int_now == "vent")
            # R3126（specs/013-P5）：复问识别——同主题第二轮起让她知道
            # 这条线聊过，顺着深聊而不是重新泛泛起头。
            _th = _chat_theme(msg)
            if _th:
                _tc = sess.setdefault("theme_hits", {})
                _tc[_th] = int(_tc.get(_th, 0)) + 1
                if _tc[_th] >= 2:
                    _sys += (f"\n\n她这轮已经第{_tc[_th]}次聊到「{_th}」"
                             "，说明这条线她没放下。顺着前面的内容往深走，"
                             "别像第一次那样泛泛起头；可以点名「你还是惦记"
                             "着这事」。")
        if _truncated:
            _sys += ("\n更早的聊天内容被省略了，用户提到「我之前说过…」"
                     "而你没看到时，老实说记不清了，不要编。")
        payload_msgs = [{"role": "system", "content": _sys}]
        _coords = _coords_snap
        _user_msg = msg
        if _coords:
            # R230a-41（R15-P1-3）：客户端 facts 直进 system 角色是可注入
            # 通道（"忽略所有先前的指令"/伪造「黄历判定：…」均以 system
            # 特权送达，mock 日志实锤）。降为 user 角色的上下文块，
            # 并剥掉仿冒权威判定口径的行——权威判定只走 _verdicts 一条道。
            _safe = [f for f in _coords if _fact_is_safe(f)]
            if _safe:
                # R2400（R135-P2-5）：prompt 总长无帽——facts 段按 3K
                # 截（单条坐标 ≤500、20 条上限本就该 ~10K 内，帽是给
                # 将来字段膨胀兜底）。
                _blk = "\n- ".join(_fact_line(f) for f in _safe)
                if len(_blk) > 3000:
                    _blk = _blk[:3000].rstrip() + "……"
                _user_msg = ("（我的排盘坐标事实，只作话题参考，"
                             "不要逐条念）：\n- " + _blk
                             + "\n\n" + msg)
        payload_msgs.extend(history)
        payload_msgs.append({"role": "user", "content": _user_msg})

        # R230a-6（R12-P2-4）：主模型与 dots 共享同一轮询预算——分段各 34s
        # 会超出前端 40s 上限，慢成功白烧。
        _dl = time.monotonic() + _POLL_BUDGET_S
        _banned_seen: list[bool] = []
        # R3242：主节点预算帽（同 polish）——超时/空泡重试二连会把全链
        # 预算烧干，封顶 timeout_s+2s 让兜底节有真实窗口。
        _dl0 = min(_dl, time.monotonic() + float(
            cfg.get("timeout_s") or _DEFAULTS["timeout_s"]) + 2)
        text = _chat_call(payload_msgs, cfg, _transport, deadline=_dl0,
                          banned_seen=_banned_seen)
        _used_cfg = cfg
        if not text:
            # R213b→R3223：备选大脑升级为兜底链——主模型失败按配置顺序
            # 逐节切换（同一 payload_msgs：system/facts/历史注入随链透传，
            # 换模型不丢上下文）；全链失败才真正降级 None。
            _seen_bases = {cfg.get("base_url")}
            for _fcfg in load_fallback_configs():
                if _fcfg.get("base_url") in _seen_bases:
                    continue
                _seen_bases.add(_fcfg.get("base_url"))
                _llm_log(f"chat 兜底切 {(_fcfg.get('base_url') or '')[:40]}"
                         f"/{_fcfg.get('model') or '?'}")
                text = _chat_call(payload_msgs, _fcfg, _transport,
                                  deadline=_dl, banned_seen=_banned_seen)
                if text:
                    _used_cfg = _fcfg
                    break
            if not text:
                # R230a-7：模型回了但全文被禁语拦下（_sanitize→None）与网络挂
                # 要区分——前者给安全固定句，后者才返回 None 走前端降级文案。
                if _banned_seen:
                    text = ("我可能说得不太对。盘是盘，日子是你自己的。"
                            "按你自己舒服的来就好。")
                else:
                    return None

        # 输出侧禁语命中 → 整条降级为固定安全回复（双保险）。判定在写历史
        # 之前——此前先把原文 append 进 messages 再查 banned，违规内容会留在
        # 会话上下文里污染后续轮次（审查轨 chat-flow）。
        # R2524：归一形态复扫——_sanitize 已按归一形态判过，这里兜底
        # 零宽/词内空白/繁体写法的漏网组合。
        if _CHAT_BANNED_PAT.search(_scan_flat(text)):
            text = ("我可能说得不太对。盘是盘，日子是你自己的。"
                    "按你自己舒服的来就好。")

        # R3124c（specs/012-P0）：成稿一致性闸——判词层进了权威信道
        # 模型仍可能方向性违背（判词说偏不合适、回复说很合适）。扫
        # 方向矛盾 → 纠偏重试一次；仍矛盾 → 按判词原句确定性兜底。
        if _rverdicts and text:
            if _chat_verdict_contra(text, _rverdicts):
                _fix_msgs = payload_msgs + [{
                    "role": "system",
                    "content": ("你上一版回复跟这张卡的判词层结论方向矛盾。"
                                "判词是权威结论：按它的口径重说一遍，"
                                "温柔但照实，不软化不加码。")}]
                # R3227：纠偏重试投给出稿的那条链节——兜底节出的稿
                # 回主链纠会撞上主链已挂的事实（白烧预算拿锚句）。
                _t2 = _chat_call(_fix_msgs, _used_cfg, _transport,
                                 deadline=_dl, banned_seen=_banned_seen)
                if _t2 and not _chat_verdict_contra(_t2, _rverdicts) \
                        and not _CHAT_BANNED_PAT.search(_scan_flat(_t2)):
                    text = _t2
                else:
                    text = _verdict_anchor_reply(_rverdicts)

        with _chat_lock:
            sess = _chat_sessions.get(session_id)
            if sess is not None:
                sess["messages"].append({"role": "user", "content": msg})
                # R230t（R32-P1-5）：存入历史的副本裁到 800 字——历史只供
                # 模型参考，超长原文前端已展示，整段回喂纯烧 token。
                # R230v（R34-#18）：截断处打标记——模型不会把半句话当全文
                # 引用（「回复到一半没了」的幻觉根因）。
                _hist = text[:800] + ("…（后略）" if len(text) > 800 else "")
                sess["messages"].append({"role": "assistant",
                                         "content": _hist})
                sess["updated"] = time.monotonic()
        return text


def _llm_log(msg: str) -> None:
    """LLM 失败归因一行日志——R3222：此前三次重试全静默，
    「走神了」无从区分超时/4xx/截断。只记状态码与异常类型，
    绝不记 key/payload/正文。"""
    try:
        print('[llm]', msg, file=sys.stderr)
    except Exception:
        pass


def _chat_call(payload_msgs: list[dict], cfg: dict,
               _transport=None, keep_citations: bool = False,
               deadline: float | None = None,
               banned_seen: list[bool] | None = None) -> str | None:
    """单次对话调用：复用 polish 的传输细节与重试语义。失败 None。

    keep_citations=True 时输出保留《书名》引文（起名点评专用）。
    deadline：调用方传入的总预算终点（monotonic），单次尝试按剩余窗口递减
    （R12-P2-4：主模型+dots 链共享同一预算，合计不超过前端轮询上限）。"""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + cfg["api_key"],
               "Content-Type": "application/json"}
    timeout = float(cfg.get("timeout_s") or _DEFAULTS["timeout_s"])
    if deadline is None:
        deadline = time.monotonic() + _POLL_BUDGET_S
    # R230t（R32-P1-6）：msgs 是可变副本——被拦后追加改正提示不影响调用方
    # 的原列表（主/dots 共享调用方 payload_msgs，不能把提示注进下一轮）。
    msgs = list(payload_msgs)
    _doubled = False   # R2359：finish=length 空回复时预算加倍救一次的标记

    for _i in range(3):
        _to = min(timeout, max(0.5, deadline - time.monotonic()))
        if _to <= 0.5 and time.monotonic() >= deadline:
            break
        # R230t（R32-P2-21）：与 polish 同款重试小退避。
        if _i:
            time.sleep(min(0.4 * _i, 1.2))
        payload = {
            "model": cfg.get("model") or _DEFAULTS["model"],
            "messages": msgs,
            "max_tokens": int(cfg.get("max_tokens") or _DEFAULTS["max_tokens"])
            * (2 if _doubled else 1),
            "temperature": 0.8,
        }
        try:
            if _transport is not None:
                data = _transport(payload, headers, url, _to)
            else:
                import httpx
                if _is_loopback(url):
                    with httpx.Client(trust_env=False, timeout=_to) as cli:
                        resp = cli.post(url, json=payload, headers=headers)
                else:
                    resp = httpx.post(url, json=payload, headers=headers,
                                      timeout=_to)
                if resp.status_code != 200:
                    # R230t（R32-P0-1）：4xx 全是确定性失败——鉴权/参数类重试
                    # 纯白烧；429 同理立刻停。
                    _llm_log(f"HTTP {resp.status_code} try={_i}")
                    if resp.status_code == 429 or 400 <= resp.status_code < 500:
                        break
                    continue
                # R2524（审-LLM-P2-4）：同 polish——解析前字节帽。
                if len(resp.content) > 2_000_000:
                    _llm_log(f"resp>2MB try={_i}")
                    continue
                data = resp.json()
            raw = (data["choices"][0]["message"]["content"] or "").strip()
            # R230t（R32-P0-2）：finish_reason=length = 思考烧光预算——
            # 空 content 或半截正文一律按失败处理，不重试不同参。
            # R2359：空 content 且未救过 → 预算加倍再试一轮（推理模型
            # 思考长度抖动，实测约两成问句烧穿 1000 上限出空泡；加倍后
            # 多数救回。半截正文仍直接判失败）。
            if (data["choices"][0].get("finish_reason") or "") == "length":
                if not raw and not _doubled:
                    _doubled = True
                    _llm_log(f"finish=length 空泡 try={_i}→预算加倍重试")
                    continue
                _llm_log(f"finish=length 截断 try={_i}（正文烧穿 max_tokens）")
                break
            if not raw:
                _llm_log(f"content 空 try={_i}")
        except Exception as _cexc:
            _llm_log(f"exc {type(_cexc).__name__} try={_i}")
            # R3242：超时=节点饱和——主/兜底链共享 34s 预算，同节点重试
            # 会把兜底链挤出局（主 2×20s 超时后全链 0 余额）。弃本节点
            # 让位下一链节；非超时异常（断连/解析错）仍按原语义重试。
            if "Timeout" in type(_cexc).__name__:
                break
            continue
        # R230a-7：记录「回了但被禁语拦」与「没回/挂了」的区别。
        # R2524：扫归一形态——「注**定**」式绕闸原文也要计入 banned_seen，
        # 否则漏进 _sanitize 才拦，降级文案口径偏成「没回/挂了」。
        if _BANNED_OUT_PAT.search(_scan_flat(raw)):
            if banned_seen is not None:
                banned_seen.append(True)
            # R230t（R32-P1-6）：共情复读用户原话里的禁词会连环撞闸——
            # 给下一次重试一句改正线索，不再同参盲烧（banned_seen=None 的
            # review 路径同样撞闸烧钱，提示也跟上）。
            # R2349r（R82-P2-1）：改正指令以 user 角色追加——尾部 system
            # 会让消息序变成 […,user,system,system]，部分 provider 对非
            # 交替角色低权重或拒绝；user 角色天然合规且语义不变。
            msgs = msgs + [{"role": "user", "content":
                            "（系统提醒：上一条回复因措辞过于直白被拦，请换"
                            "一种更柔和、不下判断的说法重答，保持纯文本口语。）"}]
        out = _sanitize(raw, keep_citations=keep_citations)
        if out:
            return out
    return None



# ── R213b：dots（小红书点点）模型接入 ──
# 活用途：chat 失败时的备选大脑 + review_names 起名点评备选
# （R2349s/R85-P1-3 复扫：xhs_copy 已于 R230t 删除、「调研顾问」无
# 调用方）。配置读 web/llm_config.json 的 "dots" 段；
# 缺失或 enabled=false → 全部 dots 功能静默关闭（与主 LLM 同一降级纪律）。

def load_dots_config() -> dict | None:
    """读 dots 配置。None = 关闭。BOOKS_LLM_DISABLE 总开关同样生效。"""
    _dis = os.getenv(_ENV_DISABLE)
    if _dis is not None and _dis.strip().lower() in ("1", "on", "true", "yes"):
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    # R230a-6（R12-P3-5）：frozen/PyInstaller 形态补 sys.executable 旁路径
    # （与 load_config 同款候选表）——否则 exe 形态下 dots 静默缺席。
    _candidates = [os.path.join(root, "web", "llm_config.json")]
    if getattr(sys, "frozen", False):
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "llm_config.json"))
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "web",
                         "llm_config.json"))
    d: dict = {}
    for path in _candidates:
        try:
            with open(path, encoding="utf-8") as f:
                d = (json.load(f) or {}).get("dots") or {}
            break
        except Exception:
            pass
    if not d:
        return None
    d.setdefault("base_url", "https://note3-prev-api.askdiandian.com/v1")
    d.setdefault("model", "dots3-note-prev")
    d.setdefault("timeout_s", 60)
    d.setdefault("max_tokens", 1200)
    # R2524（审-LLM-P2-5）：dots 配置补 load_config 同款校验——此前
    # "enabled":"false"（字符串）被 truthy 放行、timeout_s 坏类型在
    # _chat_call try 外抛 ValueError → 任务 failed。
    _en = d.get("enabled")
    if isinstance(_en, str):
        _en_l = _en.strip().lower()
        if _en_l in ("0", "false", "off", "no"):
            return None
        d["enabled"] = _en_l in ("1", "true", "on", "yes")
    if not d.get("enabled"):
        return None
    _dd = {"timeout_s": 60, "max_tokens": 1200}
    for _k in ("timeout_s", "max_tokens"):
        try:
            d[_k] = int(d[_k])
            if d[_k] <= 0:
                raise ValueError
        except (TypeError, ValueError):
            print(f"[llm_polish] dots 配置项 {_k}={d[_k]!r} 非法，"
                  f"回退默认 {_dd[_k]}", file=sys.stderr)
            d[_k] = _dd[_k]
    if (not isinstance(d.get("base_url"), str)
            or not d["base_url"].startswith("http")):
        print(f"[llm_polish] dots 配置项 base_url={d.get('base_url')!r} "
              f"不是合法 URL，回退默认", file=sys.stderr)
        d["base_url"] = "https://note3-prev-api.askdiandian.com/v1"
    if not isinstance(d.get("api_key"), str) or not d["api_key"]:
        return None
    return d


# R3223：兜底链——llm_config.json 的 "fallbacks" 数组（按数组顺序依次
# 切换，一个 key 出问题立即切下一个）+ 旧版 "dots" 段殿后（向后兼容，
# 已配置 dots 的部署形态不丢兜底）。主配置不变，仍在顶层段。

def load_fallback_configs() -> list[dict]:
    """读兜底链配置，返回按序排列的合法 provider 配置列表。

    None 不返回（用空表 []）——调用方 for 循环天然零兜底不做事。
    BOOKS_LLM_DISABLE 总开关同样生效。"""
    _dis = os.getenv(_ENV_DISABLE)
    if _dis is not None and _dis.strip().lower() in ("1", "on", "true", "yes"):
        return []
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    _candidates = [os.path.join(root, "web", "llm_config.json")]
    if getattr(sys, "frozen", False):
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "llm_config.json"))
        _candidates.append(
            os.path.join(os.path.dirname(sys.executable), "web",
                         "llm_config.json"))
    raw_list: list = []
    for path in _candidates:
        try:
            with open(path, encoding="utf-8") as f:
                raw_list = (json.load(f) or {}).get("fallbacks") or []
            break
        except Exception:
            pass
    if not isinstance(raw_list, list):
        raw_list = []
    out: list[dict] = []
    for _i, _d0 in enumerate(raw_list):
        if not isinstance(_d0, dict):
            continue
        d = dict(_d0)
        # 与 load_dots_config 同款校验纪律：字符串 enabled 按语义解析、
        # timeout_s/max_tokens coerce、坏条目跳过不误伤其余链节。
        _en = d.get("enabled", True)
        if isinstance(_en, str):
            _en_l = _en.strip().lower()
            if _en_l in ("0", "false", "off", "no"):
                continue
            d["enabled"] = _en_l in ("1", "true", "on", "yes")
        if not d.get("enabled", True):
            continue
        for _k, _dv in (("timeout_s", 30), ("max_tokens", 1000)):
            try:
                d[_k] = int(d.get(_k, _dv))
                if d[_k] <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                print(f"[llm_polish] fallbacks[{_i}] 配置项 {_k}="
                      f"{d.get(_k)!r} 非法，回退默认 {_dv}", file=sys.stderr)
                d[_k] = _dv
        if (not isinstance(d.get("base_url"), str)
                or not d["base_url"].startswith("http")):
            print(f"[llm_polish] fallbacks[{_i}] base_url="
                  f"{d.get('base_url')!r} 不是合法 URL，跳过此链节",
                  file=sys.stderr)
            continue
        if not isinstance(d.get("api_key"), str) or not d["api_key"]:
            continue
        out.append(d)
    dcfg = load_dots_config()
    if dcfg is not None:
        out.append(dcfg)
    return out


# R230t（R32-P2-21）：xhs_copy（小红书文案）连同 _XHS_COPY_SYSTEM 删除——
# 无路由无前端调用的死代码持有 dots 端点配置路径，需要时从 git 史拿回。

_NAME_REVIEW_SYSTEM = (
    "你是一位精通古典文学的起名顾问。用户会给你几个候选名字和五行背景。"
    "请为每个名字写一段 40-70 字的推荐语：优先从《诗经》《楚辞》《论语》"
    "《周易》《道德经》等经典中找与名字用字相关或同源的名句作为出处"
    "（引原句并注明篇名）；确实找不到出处的字，就从字形、字义、音韵讲它的好处。"
    "语气温暖有文化感，像一位有学问的长辈在郑重推荐。不要编造不存在的句子；"
    "不确定出处就直说「字义上」而不是硬引。"
    # R3104（specs/010）：给了五行背景就把点名落到补行上——
    # 与确定性 warm 层（R3093 字级五行接弱行）同一口径。
    "若给了五行背景里有所缺或偏弱行，推荐语要点明哪个名字的字接住了它；"
    "没有接住就如实说，别硬夸。最后用一句话总结哪个名字最亮眼。"
)


def review_names(names: list[str], facts: list[str] | None = None,
                 config: dict | None = None, _transport=None) -> str | None:
    """候选名列表 → 引经据典的推荐语文本。失败返回 None（D-244a）。"""
    cfg = config or load_config()
    if cfg is None:
        return None
    names = [n for n in (names or []) if n][:6]
    # R2400（R135-P0-2）：起名点评的 names/facts 同为客户端串，此前
    # 零过滤直进 prompt——「忽略规则；SELECT *…」原文送达。走同一道
    # 坐标闸（合法名字天然不含禁语词形）。
    names = [n for n in names if _fact_is_safe(n)]
    if not names:
        return None
    msgs = [{"role": "system", "content": _NAME_REVIEW_SYSTEM}]
    user = "候选名字：" + "、".join(names)
    if facts:
        _sf = [f for f in facts if f and _fact_is_safe(f)]
        if _sf:
            user += "\n五行背景：" + "；".join(_fact_line(f) for f in _sf)
    user += "\n\n请按上面规则为每个名字写推荐语。"
    msgs.append({"role": "user", "content": user})
    # R230a-6（R12-P1-3）：点评 prompt 明令引《诗经》篇名——净化需放行
    # 书名号段，否则输出被自家 _LEAK_PAT 剥成断头句。
    # R3245（用户实测反复「故事版没写出来」）：串行链理论满载
    # 26+20+22=68s>旧预算，拥挤期逐节 ReadTimeout 全挂——改三节点
    # 并发竞速：先出稿者获胜（任一 provider 健康即可成稿，等待时间
    # ≈最快节点而非串行之和）。输家线程随各自 timeout_s 自然收尾；
    # msgs 在 _chat_call 内有副本，跨线程共享安全。
    _rdead = time.monotonic() + _REVIEW_BUDGET_S
    _seen_bases = {cfg.get("base_url")}
    _nodes = [cfg]
    for _fcfg in load_fallback_configs():
        if _fcfg.get("base_url") in _seen_bases:
            continue
        _seen_bases.add(_fcfg.get("base_url"))
        _nodes.append(_fcfg)
    import concurrent.futures as _cf
    text = None
    _ex = _cf.ThreadPoolExecutor(max_workers=len(_nodes),
                                 thread_name_prefix="nrace")
    try:
        _futs = [_ex.submit(_chat_call, msgs, _n, _transport, True, _rdead)
                 for _n in _nodes]
        for _f in _cf.as_completed(_futs):
            try:
                _t = _f.result()
            except Exception:
                _t = None
            if _t:
                text = _t
                break
    finally:
        _ex.shutdown(wait=False)     # 不等输家线程——任务即可交卷
    return text


def spawn_name_review_task(names: list[str], facts: list[str] | None = None,
                           config: dict | None = None,
                           _transport=None) -> str | None:
    """后台起一个起名点评任务，复用 _tasks/GC/轮询端点。关闭时返回 None。"""
    cfg = config or load_config()
    if cfg is None:
        return None
    if not _rate_ok("review", 20):          # R230t（R32-P0-4）：点评限速
        # R2517（审-P3-7）：与 chat 同款哨兵——此前 None 与「功能关闭」
        # 无法区分，前端把限速当关停。
        return "__rate_limited__"
    tid = secrets.token_urlsafe(16)
    with _tasks_lock:
        _gc_tasks()
        # R230a-6（R12-P1-1）：与 spawn_ai_task 同构补双帽——未鉴权点评
        # 端点此前零上限，无限在途线程可烧光 quota。
        if len(_tasks) >= _MAX_TASK_ROWS:
            return None
        pending = sum(1 for t in _tasks.values() if t["status"] == "pending")
        if pending >= _MAX_PENDING:
            return None
        _tasks[tid] = {"status": "pending", "text": None,
                       "created": time.monotonic()}

    def _run() -> None:
        with _tasks_lock:
            rec0 = _tasks.get(tid)
            if rec0 is not None:
                rec0["started"] = time.monotonic()
        try:
            text = review_names(names, facts=facts, config=cfg,
                                _transport=_transport)
            status = "done" if text else "failed"
        except BaseException:            # R2511：同 polish/chat 径防 pending 泄漏
            status, text = "failed", None
        with _tasks_lock:
            rec = _tasks.get(tid)
            if rec is not None:
                rec["status"] = status
                rec["text"] = text

    threading.Thread(target=_run, name="ai-name-" + tid[:8],
                     daemon=True).start()
    return tid


def chat_session_closed(session_id: str) -> bool:
    """该会话是否已到轮数封顶（R230d，P2-7 前端引导用）。"""
    with _chat_lock:
        sess = _chat_sessions.get(session_id)
        return bool(sess and sess.get("closed"))


def spawn_chat_task(session_id: str, user_msg: str,
                    facts: list[str] | None = None,
                    verdict_facts: list[str] | None = None,
                    config: dict | None = None,
                    _transport=None,
                    verdict_day: str | None = None,
                    result_verdicts: list[str] | None = None) -> str | None:
    """后台起一个 chat 任务，复用 _tasks/GC/轮询端点。关闭时返回 None。

    verdict_day：判定所锚定的日子（透传 chat() 的跨日作废判断）。"""
    cfg = config or load_config()
    if cfg is None:
        return None
    # R2349r（R82-P2-2）：危机红线排在限流闸之前——此前超频的直连
    # 危机消息拿到的是静默降级（{} → 前端按 DISABLE 处理）。预置
    # 已完成任务把转介文案送回去，不烧 LLM、不落历史（与 chat()
    # 内的危机路径同口径）。
    _msg0 = (user_msg or "").strip()
    # R2524（审-LLM-P1-2）：危机/敏感短路此前每请求 token_urlsafe
    # 新行——未过限流的短路 256 发匿名 POST 即灌满 _tasks 行帽，
    # 全 AI 层停摆至 TTL（细流可无限续死）。固定文案走罐头任务行：
    # 同 tid 覆盖写、行数不增，轮询端点照常读到 done 文案。
    if _msg0 and _is_crisis(_msg0):
        tid = _CANNED_TASK_IDS["crisis"]
        with _tasks_lock:
            _tasks[tid] = {"status": "done", "text": _CHAT_REFUSAL,
                           "created": time.monotonic(),
                           "started": time.monotonic()}
        return tid
    # R2359（R114-P4-1）：非自伤生死/重病消息与危机同走免配额直返——
    # 此前先进队占 8/min 再进线程拿固定转介，连发 8+ 后「歇口气」会
    # 把转介句顶掉，用户第 9 条起看不到该看的文案。
    if _msg0 and _is_sensitive(_msg0):
        tid = _CANNED_TASK_IDS["sensitive"]
        with _tasks_lock:
            _tasks[tid] = {"status": "done", "text": _SENSITIVE_REPLY,
                           "created": time.monotonic(),
                           "started": time.monotonic()}
        return tid
    # R230t（R32-P0-4）：每 sid 每分钟 8 任务——正常连聊远低于此；
    # 换 sid 重试撞全局帽。
    # R2355（R111-P2-6）：超限改哨兵串返回——调用方回 rate_limited=True，
    # 前端提示「聊太急歇口气」而不是按功能关停永久锁输入框。
    if not chat_session_closed(session_id):
        if not _rate_ok("chat:" + (session_id or "anon"),
                        _RATE_CHAT_PER_SID):
            return "__rate_limited__"
    else:
        # R2400（R123-P2-6）：收尾态只回确定性文案（不烧 LLM）——此前
        # 照吃 8/min 配额，用户到顶再发 2 条就撞「歇口气」，文案口径
        # 打架（先说聊够又说太急）。独立放宽上限，防刷屏仍有限。
        if not _rate_ok("chatx:" + (session_id or "anon"),
                        _RATE_CHAT_PER_SID * 4):
            return "__rate_limited__"
    tid = secrets.token_urlsafe(16)
    with _tasks_lock:
        _gc_tasks()
        # R228r：在途任务上限——超限时返回 None（上层按「功能关闭」静默降级，
        # 前端轮询端点不出现该任务，与 DISABLE 行为一致）
        # R230a-6（R12-P2-1）：行帽此前只落在 spawn_ai_task——chat 补上同款。
        if len(_tasks) >= _MAX_TASK_ROWS:
            return None
        pending = sum(1 for t in _tasks.values() if t["status"] == "pending")
        if pending >= _MAX_PENDING:
            return None
        _tasks[tid] = {"status": "pending", "text": None,
                       "created": time.monotonic()}

    def _run() -> None:
        # R230v（R34-#5）：标记实际起动时刻——_session_lock 排队期间
        # 前端据此区分「排队中」与「生成中」，轮询预算从起动算而非入队算。
        # R233r（R49-P2-3）：会话被 TTL 回收/从未见过 → fresh 标记——
        # 前端据此提示「隔了几天小满可能记不全」。
        def _mark_started():
            # R2511：fresh 挪到锁内打标时刻采样——等锁期间先到的
            # 同会话兄弟已建 sess，此刻再查「是不是第一条」才如实
            # （入队时采样会把排在第二的消息误标 fresh）。
            with _chat_lock:
                _fresh = session_id not in _chat_sessions
            with _tasks_lock:
                rec0 = _tasks.get(tid)
                if rec0 is not None:
                    rec0["started"] = time.monotonic()
                    rec0["fresh"] = _fresh
        try:
            text = chat(session_id, user_msg, facts=facts,
                        verdict_facts=verdict_facts, config=cfg,
                        _transport=_transport, verdict_day=verdict_day,
                        result_verdicts=result_verdicts,
                        _task_started=_mark_started)
            status = "done" if text else "failed"
        except BaseException as _wexc:    # R2511：同 polish 径防 pending 泄漏
            status, text = "failed", None
            _llm_log(f"chat task 未捕获 {type(_wexc).__name__}")
        with _tasks_lock:
            rec = _tasks.get(tid)
            if rec is not None:
                rec["status"] = status
                rec["text"] = text
                rec["closed"] = chat_session_closed(session_id)

    threading.Thread(target=_run, name="ai-chat-" + tid[:8],
                     daemon=True).start()
    return tid


# ---------------------------------------------------------------------------
# 各功能的 facts 组装（全部来自已算出的字段，零新事实）
# ---------------------------------------------------------------------------

def facts_bazi(paipan: dict, warm: dict, question: str | None,
               gender: str | None = None,
               hour_known: bool = True) -> list[str]:
    b = paipan or {}
    w = warm or {}
    card = w.get("energy_card") or {}
    # R3233（循环优化）：时辰未知的盘 render 里第 4 柱是默认午时——
    # 直接喂模型会诱导 AI 把默认当真时辰讲（前端卡面已换「时辰未知」，
    # facts 侧同源处理）。只改喂模型的串，排盘事实不动。
    _render = b.get("render") or ""
    if hour_known is False:
        _t = _render.split()
        if len(_t) >= 4 and _t[3].endswith("时"):
            _t[3] = "时辰未知"
        _render = " ".join(_t)
    facts = [
        f"四柱：{_render}",
        # R2400（R135-P1-2）：None 值字面量会写成「一句话结论：None」
        # 喂给模型——or "" 兜住。
        f"一句话结论：{w.get('one_liner') or ''}",
    ]
    # R230a-6（R12-P2-3）：_SYSTEM 要求称谓与性别一致，但此前 facts 里
    # 根本没有性别——模型只能猜（B-016 只盖了 taohua/hehun/qiming 三路）。
    if gender in ("男", "女"):
        facts.append(f"性别：{gender}")
    if card:
        facts.append("本命元素：{}（{}）".format(card.get("element") or "",
                                              card.get("element_note") or ""))
        if card.get("lucky_colors"):
            facts.append("幸运色：" + "、".join(card["lucky_colors"]))
        if card.get("lucky_numbers"):
            facts.append("幸运数字：" + "、".join(str(n) for n in card["lucky_numbers"]))
    reply0 = (w.get("reply") or [None])[0]
    if reply0:
        # R230a-6（R12-P3-8）：字段名改中性标记——口语化字段名可能被模型
        # 当指令/台词复读。R2400（R135-P2-1）：`ctx:` 是内部构形外露——
        # 改中文自然标签。
        facts.append("语境：" + _fact_line(reply0))
    # R2539（因果层红利）：解读的确定性因果行也喂给模型——用户追问
    # 「为什么」时模型手里得有眼下运/针对落点/五行分布，不是只有四柱。
    # 全部取自 warm.details（interpreter 确定性原文），不新增事实。
    for s in w.get("details") or []:
        title = s.get("title") or ""
        lines = s.get("lines") or []
        if title == "五行强弱" and lines:
            _fe = _fact_line(lines[0])
            facts.append("五行分布："
                         + (_fe[3:] if _fe.startswith("分布：") else _fe))
        elif title == "大运走势":
            _cur = next((l for l in lines if "←眼下" in l
                         and l.startswith("第 ")), None)
            if _cur:
                facts.append("眼下大运：" + _fact_line(_cur))
        elif title.startswith("针对") and lines:
            facts.append("盘面落点：" + _fact_line(lines[0]))
    # R3148：时间问坐标行进 facts——用户带「今年/最近/下个月」提问时
    # warm.reply 里已算好的流年/流月/顺劲月锚此前不进解读块上下文，
    # 成稿只能泛写「运势起伏」。把这些确定性锚喂给模型。
    for _rl in (w.get("reply") or [])[1:]:
        if any(k in _rl for k in ("年度主基调", "当月基调", "眼下走在第",
                                  "偏顺气的月份", "要使劲的月份")):
            facts.append("时间坐标：" + _fact_line(_rl))
    return facts


def facts_taohua(t: dict, warm: dict | None = None,
                 gender: str | None = None) -> list[str]:
    # R2539：hit_pillars 等字段是英文键（'day'/'hour'）——直接喂模型
    # 会在回复里漏英文柱名；统一翻成中文柱名（命中层全表适用）。
    _EN2CN = {"year": "年", "month": "月", "day": "日", "hour": "时",
              "年": "年", "月": "月", "日": "日", "时": "时"}
    _cn = lambda ps: "、".join(_EN2CN.get(str(p), str(p)) + "柱"
                              for p in (ps or []))
    hits = _cn(t.get("hit_pillars")) or "四柱均未临"
    hl_p = _cn(t.get("hongluan_pillar")) or "未临柱"
    tx_p = _cn(t.get("tianxi_pillar")) or "未临柱"
    # R2349s（R84-P1-12）：taohua.py 的强度值是 "mid" 不是 "medium"——
    # 此前 mid 落不进映射，英文原值直接喂给 AI facts。
    # R2400（R135-P1-2）：上游强度值两种写法都在流通（"mid"/"medium"）——
    # 未映射的会原样英文落进事实行。
    strength_warm = {"strong": "旺", "mid": "平", "medium": "平",
                     "weak": "慢热"}.get(t.get("strength"),
                                          t.get("strength") or "")
    facts = [
        # R191b（B-016 同型补齐）：桃花解读天然依赖性别，必须显式给
        "性别：{}".format(gender if gender in ("男", "女") else "未填写"),
        "桃花星（咸池）落在{}支：{}".format(t.get("year_zhi", ""), t.get("peach_zhi", "")),
        "本命桃花临柱：{}".format(hits),
        "红鸾在{}（{}），天喜在{}（{}）".format(
            t.get("hongluan", ""), hl_p, t.get("tianxi", ""), tx_p),
        "桃花整体节奏：{}".format(strength_warm),
    ]
    # R2539（因果层红利）：临柱只报「年支/日支」模型仍不知道这个位置
    # 管什么——补柱位人生域白话（与 interpreter._POS_DOMAIN 同一张表）。
    if t.get("hit_pillars"):
        from guji.interpreter import _POS_DOMAIN
        _EN2CN = {"year": "年", "month": "月", "day": "日", "hour": "时"}
        doms = [_POS_DOMAIN.get(_EN2CN.get(str(p), str(p)[:1]))
                for p in t["hit_pillars"]]
        doms = [d for d in doms if d]
        if doms:
            facts.append("这些位置管：{}".format("、".join(doms)))
    dayun = t.get("dayun_hits") or []
    if dayun:
        d0 = dayun[0]
        facts.append("大运桃花应期：{}年起走{}运".format(
            d0.get("year_start") or "？", d0.get("pillar") or ""))
    # R3098（R3087 同型）：判词带+入口预判进事实——warm.reply[0]/[1]
    # 是「缘分信号偏X——锚点」与「入口预判：…」，小满口经须与判词
    # 一致，否则用户问「我桃花怎么样」两套话。
    _wr = (warm or {}).get("reply") or []
    for _wl in _wr[:2]:
        if "判词" in _wl or "入口" in _wl:
            facts.append(_fact_line(_wl))
    if warm and warm.get("one_liner"):
        facts.append("语境：" + _fact_line(warm["one_liner"]))
    return facts


def facts_hehun(h: dict, warm: dict | None = None,
                gender_a: str | None = None,
                gender_b: str | None = None) -> list[str]:
    rel = "六冲" if h.get("clash") else ("六合" if h.get("combine") else "无明显冲合")
    facts = [
        # R191b（B-016 同型补齐）：合婚是两个人的盘，双方性别都给
        "双方性别：{} / {}".format(
            gender_a if gender_a in ("男", "女") else "未填写",
            gender_b if gender_b in ("男", "女") else "未填写"),
        "两人年支：{}×{}，关系：{}".format(h.get("year_zhi_a", ""),
                                         h.get("year_zhi_b", ""), rel),
        # R3097：同五行是比和不是「相生：否」——同气中性偏顺，否读作负
        # 会误导模型判「不相生=不合」。三分支：相生/比和/相克。
        "日主五行：{} 与 {}，{}".format(
            h.get("day_wx_a", ""), h.get("day_wx_b", ""),
            ("相生" if h.get("day_wx_sheng")
             else "同气比和" if h.get("day_wx_same") else "相克")),
        "两人桃花支：{}/{}，{}".format(h.get("peach_a", ""), h.get("peach_b", ""),
                                     "相同" if h.get("peach_same") else "不同"),
    ]
    # R2539（因果层红利）：夫妻宫（日支）关系是合婚里权重最高的宫——
    # warm 判词早看它了，模型 facts 之前没有，答「哪里合/冲」会只说年支。
    if h.get("day_zhi_rel"):
        facts.append("夫妻宫（日支）：{}/{} {}".format(
            h.get("day_zhi_a") or "", h.get("day_zhi_b") or "",
            h.get("day_zhi_rel") or ""))
    # R3087（specs/010）：合拍指数+判词行进事实——小满被问「我们合不合」
    # 时口径必须与判词层一致，不然 warm 判「磕绊偏多」小满却说「挺好的」。
    if isinstance(h.get("match_score"), int):
        facts.append("合拍指数：{}/99".format(h["match_score"]))
    _wr = (warm or {}).get("reply") or []
    if _wr:
        facts.append("判词：" + _fact_line(_wr[0]))
    # R204b（D-257b）：天干五合 + 十神互见进事实行（yinyuan skill 融入）
    # R2400（R135-P2-3）：a_bazi/b_bazi 可为 None——.get 会 AttributeError。
    _ab = h.get("a_bazi") or {}
    _bb = h.get("b_bazi") or {}
    if h.get("gan_he"):
        facts.append("日干五合：{}与{}（传统上主互相吸引）".format(
            (_ab.get("day") or "")[:1], (_bb.get("day") or "")[:1]))
    if h.get("god_a_sees_b"):
        facts.append("日主十神互见：{}见{}为{}，{}见{}为{}".format(
            (_ab.get("day") or "")[:1], (_bb.get("day") or "")[:1],
            h.get("god_a_sees_b") or "",
            (_bb.get("day") or "")[:1], (_ab.get("day") or "")[:1],
            h.get("god_b_sees_a") or ""))
    if warm and warm.get("one_liner"):
        facts.append("语境：" + _fact_line(warm["one_liner"]))
    return facts


def facts_qiming(q: dict, gender: str | None = None,
                 warm: dict | None = None) -> list[str]:
    fe = q.get("five_elements") or {}
    miss = fe.get("missing") or []
    weak = [w for w in (fe.get("weak") or []) if w]
    names = [n.get("full_name") for n in (q.get("full_names") or [])[:3]
             if n.get("full_name")]
    # R191b（B-016）：性别必须显式喂给模型——否则它会自己猜，实测猜出
    # 「林先生」（入参 gender=女）。称谓是事实，不是模型可选项。
    facts = [
        "姓氏：{}".format(q.get("surname") or ""),
        # R3194：四柱渲染串此前漏喂——模型看不到日主坐标只能空谈
        # 「补五行」。render 是「甲申年 庚午月 … 日主：乙」一行。
        "排盘：{}".format((q.get("bazi") or {}).get("render") or "未算"),
        "性别：{}".format("女" if gender == "女" else
                          ("男" if gender == "男" else "未填写")),
        # R2400（R135-P1-2）：dict repr（{'木': 2.6}）直接喂模型是内部
        # 外形——格式化成「木2.6」列。
        "五行分布：{}".format(
            "、".join(f"{k}{v}" for k, v in (fe.get("counts") or {}).items())
            if isinstance(fe.get("counts"), dict) and fe.get("counts")
            else "未计算"),
        # R3099：weak 键此前不读——五行俱全但偏弱行被报成「无」，小满
        # 口径与 warm 卡面（「金、木偏弱」）打架。
        "所缺或最弱行：{}".format(
            ("缺{}；偏弱{}".format("、".join(miss), "、".join(weak))
             if miss and weak else
             "缺{}".format("、".join(miss)) if miss else
             "偏弱{}".format("、".join(weak)) if weak else "无")),
    ]
    if names:
        facts.append("推荐完整名：" + "、".join(names))
    # R3191：候选名的真实出处/释义进事实——此前模型看不到 origin，
    # 只能编造「出自《XX》」的幻觉来源（实抓出「林苹秩出自」悬空句）。
    # 有典的给典，无典的明说「无文献出处」堵死编造空间。
    _og_n = 0
    for _n in (q.get("full_names") or [])[:3]:
        if not isinstance(_n, dict):
            continue
        _fn = _n.get("full_name") or ""
        _og = (_n.get("origin") or "").strip()
        _st = (_n.get("story") or "").strip()
        if _fn and _og:
            _og_n += 1
            facts.append("「{}」真实出处：{}{}".format(
                _fn, _og, "；释义：" + _st[:60] if _st else ""))
        elif _fn:
            facts.append("「{}」：词库生成，无文献出处，不要编造来源".format(_fn))
    _fed = min(len(q.get("full_names") or []), 3)
    if _og_n and _og_n < _fed:
        facts.append("候选名中只有 {} 个带典籍出处，不要说「都取自经典」".format(_og_n))
    # R233w：warm 层文案进事实——模型点评照着确定性口径说，不自由发挥。
    for _ln in ((warm or {}).get("reply") or []):
        facts.append("参考口吻：" + _ln)
    return facts


def facts_tarot(t: dict, warm: dict | None = None,
                question: str | None = None) -> list[str]:
    """塔罗卡事实——牌面坐标+判词级行，AI 解读块同口径深加工。

    R3154：塔罗/六爻此前没有 AI 解读块——八字/桃花/合婚/起名都享
    「判词同口径的深加工段」，倾诉欲最高的抽牌场景反而只有确定性
    文案一层。
    """
    draws = t.get("draws") or []
    cards = []
    for d in draws:
        nm = d.get("name") or ""
        pos = d.get("position") or ""
        up = "正位" if d.get("upright") else "逆位"
        cards.append((str(pos) + "位：" if pos else "") + nm + "·" + up)
    facts = ["抽到的牌：" + ("、".join(cards) if cards else "（无牌）")]
    if t.get("spread"):
        facts.append("牌阵：" + str(t["spread"]))
    if question:
        facts.append("她问的是：" + str(question)[:60])
    # 判词级口径行升格——综合收尾/三段式处方照着卡面说，不自由发挥。
    for _ln in ((warm or {}).get("reply") or []):
        _ls = str(_ln)
        if ("综合来看" in _ls or "这组牌" in _ls or "判词" in _ls
                or "先做" in _ls or "观察信号" in _ls):
            facts.append(("判词：" if not _ls.startswith("判词")
                          else "") + _fact_line(_ls))
    return facts


def facts_liuyao(res: dict, warm: dict | None = None,
                 question: str | None = None) -> list[str]:
    """六爻卦事实，卦名/动爻/世应用神坐标+应期处方判词行。"""
    ben = res.get("ben") or {}
    bian = res.get("bian") or {}
    facts = [
        "本卦：{}".format(ben.get("gua_name") or ""),
        "变卦：{}".format(bian.get("gua_name") or "无（六爻安静）"),
    ]
    mv = ben.get("moving_lines") or []
    facts.append("动爻：" + ("、".join("第{}爻".format(i) for i in mv)
                           if mv else "无"))
    pp = (res.get("paipan") or {}).get("ben_gua") or {}
    ys = pp.get("lines") or []
    for y in ys:
        if y.get("is_shi"):
            facts.append("世爻（代表问事人）：第{}爻 {}{}·{}·{}".format(
                y.get("position"), y.get("stem") or "",
                y.get("branch") or "", y.get("wuxing") or "",
                y.get("liuqin") or ""))
        if y.get("is_ying"):
            facts.append("应爻（代表事情那头）：第{}爻 {}{}·{}·{}".format(
                y.get("position"), y.get("stem") or "",
                y.get("branch") or "", y.get("wuxing") or "",
                y.get("liuqin") or ""))
    if question:
        facts.append("她问的是：" + str(question)[:60])
    # 判词级行升格——梳理行/口径行/应期/月建旺衰/旬空/三段式处方照卡面说。
    for _ln in ((warm or {}).get("reply") or []):
        _ls = str(_ln)
        if ("照传统口径" in _ls or "应期参考" in _ls or "判词" in _ls
                or "最实一步" in _ls or "观察信号" in _ls
                or "月令" in _ls or "旬空" in _ls or "落空亡" in _ls
                or "回头生" in _ls or "回头克" in _ls
                or "化进神" in _ls or "化退神" in _ls or "暗处有动静" in _ls
                or "伏吟" in _ls or "反吟" in _ls or "劲使出来就散" in _ls
                or "六合" in _ls or "六冲" in _ls or "卦象格局" in _ls
                or "先做" in _ls):
            facts.append(("判词：" if not _ls.startswith("判词")
                          else "") + _fact_line(_ls))
    return facts


def facts_huangli(h: dict) -> list[str]:
    """黄历卡事实（R3189）：黄历是唯一没 AI 段的卡——宜忌/值神/
    冲煞/建除全是确定性坐标，polish 的活是把它串成「今天的天气
    预报」式人话，不替黄历编新宜忌。"""
    facts: list[str] = []
    if h.get("date"):
        facts.append("日期：{}（{}）".format(
            h["date"], h.get("ganzhi_day_cn") or ""))
    if h.get("yi"):
        facts.append("今日宜：" + "、".join(str(x) for x in h["yi"][:8]))
    if h.get("ji"):
        facts.append("今日忌：" + "、".join(str(x) for x in h["ji"][:8]))
    if h.get("zhishen"):
        _zj = h.get("zhishen_ji")
        facts.append("值神：{}{}".format(
            h["zhishen"],
            "（吉）" if _zj is True else ("（凶）" if _zj is False else "")))
    if h.get("jianchu"):
        facts.append("建除十二神：" + str(h["jianchu"]))
    if h.get("xiu"):
        facts.append("值宿：" + str(h["xiu"]))
    _ln = h.get("lunar") or {}
    if _ln.get("month_cn") or _ln.get("day_cn"):
        facts.append("农历：{}{}{}".format(
            _ln.get("ganzhi_year_cn") or "",
            _ln.get("month_cn") or "", _ln.get("day_cn") or ""))
    _pz = h.get("pengzu") or {}
    if _pz.get("gan_text") or _pz.get("zhi_text"):
        facts.append("彭祖百忌：{}；{}".format(
            _pz.get("gan_text") or "", _pz.get("zhi_text") or ""))
    _hs = [x.get("branch") for x in (h.get("hours") or [])
           if isinstance(x, dict) and x.get("ji") and x.get("branch")]
    if _hs:
        facts.append("今日吉时：" + "、".join(str(b) + "时" for b in _hs))
    _cs = h.get("chongsha") or {}
    if _cs.get("chong_animal"):
        facts.append("冲煞：冲{}（煞{}方）".format(
            _cs["chong_animal"], _cs.get("sha_fang") or ""))
    if h.get("term_today"):
        _tt = h["term_today"]
        facts.append("今日交节：" + str(_tt.get("name") or ""))
    if h.get("festival"):
        facts.append("今天是：" + str(h["festival"]))
    facts.append("口径：黄历是老黄历的民俗说法，把宜忌翻成人话陪她"
                 "看日子，别念成吉凶判决书，更别劝她做重大决定")
    return facts


def facts_xingzuo(z: dict) -> list[str]:
    """星座日运卡事实（R3193）：十二宫日运此前是唯一没有 AI 段的
    卡面——当班宫+三运（爱情/事业/财运）全是写死文案坐标，polish
    的活是把当班宫的三行串成一段口语天气，不替星座编运势。"""
    facts: list[str] = []
    if z.get("date"):
        facts.append("日期：{}（{}）".format(
            z["date"], z.get("day_ganzhi") or ""))
    if z.get("today_sign"):
        facts.append("今日值宫：{}座，{}".format(
            z["today_sign"], z.get("today_note") or ""))
    for _s in (z.get("signs") or []):
        if not isinstance(_s, dict) or not _s.get("is_today"):
            continue
        if _s.get("sign_note"):
            facts.append("当班总运：{}".format(_s["sign_note"]))
        if _s.get("love"):
            facts.append("爱情运：{}".format(_s["love"]))
        if _s.get("career"):
            facts.append("事业运：{}".format(_s["career"]))
        if _s.get("wealth"):
            facts.append("财运：{}".format(_s["wealth"]))
        break
    facts.append("口径：星座日运是轻娱乐，把当班宫的三运串成口语"
                 "天气，别上纲成人生指导，更别编其他宫的运势")
    return facts


def facts_xzmatch(m: dict) -> list[str]:
    """星座合盘卡事实——象组/分数/lines 判词级行进 polish。

    R3155：闺蜜互测是分享型场景——卡面 bullet 已够细，加一段
    口语化 AI 解读让「念给对方听」这个动作成立。
    """
    facts = [
        "星座合盘：{}座 × {}座（{}象 × {}象）".format(
            m.get("a") or "", m.get("b") or "",
            m.get("elem_a") or "", m.get("elem_b") or ""),
        "合拍指数：{}/99（{}）".format(m.get("score") or "",
                                      m.get("label") or ""),
    ]
    for _ln in (m.get("lines") or [])[:4]:
        _ls = str(_ln)
        # 交权尾（「星座只是地图」）不进 facts——模型自己会说保留意见
        if "地图" in _ls and "路" in _ls:
            continue
        facts.append("判词：" + _fact_line(_ls))
    return facts
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # 1. 无 key 配置 → None（降级）
    off = dict(_DEFAULTS, enabled=True, api_key="REPLACE_WITH_YOUR_KEY")
    assert polish(["四柱：戊寅"], config=off) is None, "无 key 应降级为 None"
    print("PASS 无 key 降级")

    # 1b. 环境总开关（D-245a）
    os.environ[_ENV_DISABLE] = "1"
    try:
        assert load_config() is None, "BOOKS_LLM_DISABLE=1 应禁用"
    finally:
        del os.environ[_ENV_DISABLE]
    print("PASS 环境总开关")

    # 2. enabled=false → None
    dis = dict(_DEFAULTS, enabled=False, api_key="x" * 40)
    assert polish(["四柱：戊寅"], config=dis) is None, "关闭应降级为 None"
    print("PASS 开关关闭降级")

    # 3. transport 抛超时 → None（静默）
    def _boom(payload, headers, url, timeout):
        raise TimeoutError("simulated")
    assert polish(["四柱：戊寅"], config=dict(_DEFAULTS, api_key="k"),
                  _transport=_boom) is None, "超时应静默降级"
    print("PASS 超时静默降级")

    # 4. transport 正常返回 → 文本出来且净化生效
    def _ok(payload, headers, url, timeout):
        assert payload["messages"][0]["role"] == "system"
        return {"choices": [{"message": {"content":
                 "「《滴天髓》第3页」说你的盘很稳。  对的人正在慢慢走向你，别急。"}}]}
    out = polish(["四柱：戊寅年"], question="感情运怎么样？",
                 config=dict(_DEFAULTS, api_key="k"), _transport=_ok)
    assert out is not None and "《" not in out and "第3页" not in out, out
    assert "对的人" in out
    print("PASS 正常路径 + 引用外观净化:", out)

    # 5. 空事实 → None
    assert polish([], config=dict(_DEFAULTS, api_key="k")) is None
    print("PASS 空事实降级")

    # 6. facts 组装器：输入字段全覆盖、无异常
    fb = facts_bazi({"render": "戊寅年 己未月"}, {"one_liner": "感情这块，盘里有着落点",
                    "energy_card": {"element": "土", "lucky_colors": ["红"],
                                    "lucky_numbers": [2, 7]},
                    "reply": ["你问「感情运怎么样？」"]}, "感情运怎么样？")
    assert any("四柱" in f for f in fb) and len(fb) >= 3
    ft = facts_taohua({"year_zhi": "寅", "peach_zhi": "卯", "hit_pillars": [],
                       "hongluan": "丑", "hongluan_pillar": [], "tianxi": "未",
                       "tianxi_pillar": ["month"], "strength": "weak",
                       "dayun_hits": [{"year_start": 2032, "pillar": "乙卯"}]})
    assert any("2032" in f for f in ft)
    fh = facts_hehun({"year_zhi_a": "寅", "year_zhi_b": "亥", "clash": False,
                      "combine": True, "day_wx_a": "土", "day_wx_b": "木",
                      "day_wx_sheng": True, "peach_a": "卯", "peach_b": "子",
                      "peach_same": False})
    assert any("六合" in f for f in fh)
    fq = facts_qiming({"surname": "林", "five_elements": {"counts": {"金": 0},
                       "missing": ["金"]}, "full_names": [{"full_name": "林锦瑶"}]},
                      gender="女")
    assert any("林锦瑶" in f for f in fq)
    assert "性别：女" in fq, fq                      # R191b（B-016）：性别必须喂给模型
    # R3146 补「排盘：未算」行后性别不再是 [1]——钉改成员判定，
    # 与上行「性别：女」同款（钉意图是喂没喂，不是固定槽位）。
    assert "性别：未填写" in facts_qiming(
        {"surname": "林", "five_elements": {}, "full_names": []})
    print("PASS facts 组装器 ×4（含 B-016 性别事实）")

    print("\n全部自测通过。在线联调命令见 specs/006-llm-polish/spec.md 判据 1。")
