"""llm_polish — LLM 润色层（specs/006-llm-polish）。

把确定性算好的坐标事实交给 LLM，换回 2–3 句温柔的话。它是 **附加层**：
  * 输入只有已算出的事实（不引入新命理断言）
  * 失败（无配置/断网/超时/坏响应）一律静默降级返回 None
  * 输出不落任何库（corpus/knowledge/history 三库零命中，判据 3）
  * key 只从 web/llm_config.json（gitignore）或环境变量读，不进日志

纪律（D-242a/D-243a/D-244a）：
  * httpx 直连 OpenAI 兼容 chat/completions，零新增 pip 依赖
  * 超时默认 8s；LLM 永远不是承重墙
  * 提示词禁止模型生成书名/页码/引文（判据：响应内零 citation 结构）

复验命令（PowerShell，项目根）：
    .\\.venv\\Scripts\\python.exe -m guji.llm_polish     # 本模块自测（离线部分）
"""
from __future__ import annotations

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
    # 语义：BOOKS_LLM_DISABLE=1/on/true/yes → 禁用；=0/off/false/no → 强制启用
    #（即使无 key 也走降级路径，行为一致）；未设置 → 按配置文件。
    _dis = os.getenv(_ENV_DISABLE)
    if _dis is not None and _dis.strip().lower() in ("1", "on", "true", "yes"):
        return None
    cfg = dict(_DEFAULTS)
    # 本文件在 <root>/src/guji/llm_polish.py；here 取到 .../src/guji 目录，
    # 再上两级即仓库根（web/ 的父目录）
    here = os.path.dirname(os.path.abspath(__file__))     # .../src/guji
    root = os.path.dirname(os.path.dirname(here))         # .../books
    path = os.path.join(root, "web", "llm_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass  # 无配置文件不算错——降级路径的一部分
    # 环境变量覆盖（部署形态用；key 不落盘的场景）
    if os.getenv(_ENV_KEY):
        cfg["api_key"] = os.environ[_ENV_KEY]
    if os.getenv(_ENV_BASE):
        cfg["base_url"] = os.environ[_ENV_BASE]
    if os.getenv(_ENV_MODEL):
        cfg["model"] = os.environ[_ENV_MODEL]

    if not cfg.get("enabled"):
        return None
    if not cfg.get("api_key") or cfg["api_key"].startswith("REPLACE"):
        return None
    return cfg


# ---------------------------------------------------------------------------
# 提示词：事实进、温柔话出。禁止新断言、禁止引用外观。
# ---------------------------------------------------------------------------

_SYSTEM = (
    "你是一个温柔的中文命理助手，为已经排好的八字盘写解读润色。"
    "规则：1) 只使用【给定事实】里的信息，绝不发明新的命理断言、绝不出示新的术语；"
    "若事实里有性别/双方性别，称谓与措辞必须与之一致（女性绝不可称先生，反之亦然）；"
    "2) 绝不引用任何书名、页码、原文（引文由系统另行展示）；"
    "3) 语气像善解人意的朋友：温暖、鼓励、不说教、不恐吓、不用宿命式表述"
    "（禁止：注定/孤独/没戏/克/必离）；4) 不给现实决策指令；"
    "5) 输出 2–3 句中文，总长不超过 90 字，不要分点、不要标题、不要 emoji。"
)

_TEMPLATE = (
    "【给定事实】\n{facts}\n\n"
    "【用户提问】{question}\n\n"
    "请基于给定事实写一段温柔的解读。"
)


def _render(facts: list[str], question: str | None) -> str:
    q = (question or "").strip() or "（未填写，请泛泛而谈）"
    return _TEMPLATE.format(facts="\n".join("- " + f for f in facts), question=q)


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
    cfg = config or load_config()
    if cfg is None:
        return None
    facts = [f for f in (facts or []) if f]
    if not facts:
        return None

    payload = {
        "model": cfg.get("model") or _DEFAULTS["model"],
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _render(facts, question)},
        ],
        "max_tokens": int(cfg.get("max_tokens") or _DEFAULTS["max_tokens"]),
        "temperature": 0.8,
    }
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": "Bearer " + cfg["api_key"],
               "Content-Type": "application/json"}
    timeout = float(cfg.get("timeout_s") or _DEFAULTS["timeout_s"])

    for i in range(max(1, _attempts)):
        try:
            if _transport is not None:                # 测试注入
                data = _transport(payload, headers, url, timeout)
            else:
                import httpx
                # B-020（R192b，审查轨 R132a-F2）：httpx 默认 trust_env=True，
                # 会拾取 Windows 注册表代理且无视 ProxyOverride——发往
                # 127.0.0.1/localhost 的请求被代理吞成 502 空响应（R192b 基线
                # 复现：mock 收到 0 个请求、polish 静默 None）。回环地址永远
                # 不该走系统代理，对 loopback 目标显式关掉 trust_env。
                # 远程目标（agnes 等）行为不变：仍走 trust_env=True 的默认客户端。
                if _is_loopback(url):
                    with httpx.Client(trust_env=False, timeout=timeout) as cli:
                        resp = cli.post(url, json=payload, headers=headers)
                else:
                    resp = httpx.post(url, json=payload, headers=headers,
                                      timeout=timeout)
                if resp.status_code != 200:
                    continue                          # 可重试：网关类错误
                data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            continue                                  # D-244a 静默降级 + 重试
        out = _sanitize(text)
        if out:
            return out
    return None


_LEAK_PAT = re.compile(
    r"《[^》]{1,20}》|第\s*\d+\s*页|page\s*\d+|p\.\s*\d+", re.IGNORECASE)

_LOOPBACK_PAT = re.compile(
    r"^https?://(127\.0\.0\.1|\[::1?\]|localhost)(:\d+)?(/|$)", re.IGNORECASE)


def _is_loopback(url: str) -> bool:
    """URL 是否指向回环地址（B-020：loopback 不走系统代理）。"""
    return bool(_LOOPBACK_PAT.match(url or ""))


def _sanitize(text: str | None) -> str | None:
    """输出净化：去书名号引用外观、裁掉空段。判据 6 的代码侧兜底。"""
    if not text:
        return None
    text = _LEAK_PAT.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = text.strip("\"“”'‘")
    if len(text) < 6:
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
_POLL_CAP_S = 40.0           # 前端轮询上限（秒）；到点未完成按失败处理（不渲染）

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _gc_tasks() -> None:
    """清掉超 TTL 的已完成任务记录。调用方必须已持有 _tasks_lock。"""
    now = time.monotonic()
    stale = [tid for tid, t in _tasks.items()
             if now - t["created"] > _TASK_TTL_S]
    for tid in stale:
        _tasks.pop(tid, None)


def spawn_ai_task(facts: list[str], question: str | None = None,
                  config: dict | None = None, _transport=None) -> str | None:
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
    tid = secrets.token_urlsafe(16)
    with _tasks_lock:
        _gc_tasks()
        _tasks[tid] = {"status": "pending", "text": None,
                       "created": time.monotonic()}

    def _run() -> None:
        try:
            text = polish(facts, question, cfg, _transport=_transport)
            status = "done" if text else "failed"
        except Exception:                     # D-244a：任何异常都降级，不抛
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
        return {"status": rec["status"], "text": rec["text"]}


# ---------------------------------------------------------------------------
# 各功能的 facts 组装（全部来自已算出的字段，零新事实）
# ---------------------------------------------------------------------------

def facts_bazi(paipan: dict, warm: dict, question: str | None) -> list[str]:
    b = paipan or {}
    w = warm or {}
    card = w.get("energy_card") or {}
    facts = [
        f"四柱：{b.get('render', '')}",
        f"一句话结论：{w.get('one_liner', '')}",
    ]
    if card:
        facts.append("本命元素：{}（{}）".format(card.get("element", ""),
                                              card.get("element_note", "")))
        if card.get("lucky_colors"):
            facts.append("幸运色：" + "、".join(card["lucky_colors"]))
        if card.get("lucky_numbers"):
            facts.append("幸运数字：" + "、".join(str(n) for n in card["lucky_numbers"]))
    reply0 = (w.get("reply") or [None])[0]
    if reply0:
        facts.append("针对提问的坐标描述：" + reply0)
    return facts


def facts_taohua(t: dict, warm: dict | None = None,
                 gender: str | None = None) -> list[str]:
    hits = "、".join(t.get("hit_pillars") or []) or "四柱均未临"
    hl_p = "、".join(t.get("hongluan_pillar") or []) or "未临柱"
    tx_p = "、".join(t.get("tianxi_pillar") or []) or "未临柱"
    strength_warm = {"strong": "旺", "medium": "平", "weak": "慢热"}.get(
        t.get("strength"), t.get("strength", ""))
    facts = [
        # R191b（B-016 同型补齐）：桃花解读天然依赖性别，必须显式给
        "性别：{}".format(gender if gender in ("男", "女") else "未填写"),
        "桃花星（咸池）落在{}支：{}".format(t.get("year_zhi", ""), t.get("peach_zhi", "")),
        "本命桃花临柱：{}".format(hits),
        "红鸾在{}（{}），天喜在{}（{}）".format(
            t.get("hongluan", ""), hl_p, t.get("tianxi", ""), tx_p),
        "桃花整体节奏：{}".format(strength_warm),
    ]
    dayun = t.get("dayun_hits") or []
    if dayun:
        d0 = dayun[0]
        facts.append("大运桃花应期：{}年起走{}运".format(d0.get("year_start"),
                                                     d0.get("pillar")))
    if warm and warm.get("one_liner"):
        facts.append("人话结论：" + warm["one_liner"])
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
        "日主五行：{} 与 {}，相生：{}".format(
            h.get("day_wx_a", ""), h.get("day_wx_b", ""),
            "是" if h.get("day_wx_sheng") else "否"),
        "两人桃花支：{}/{}，{}".format(h.get("peach_a", ""), h.get("peach_b", ""),
                                     "相同" if h.get("peach_same") else "不同"),
    ]
    # R204b（D-257b）：天干五合 + 十神互见进事实行（yinyuan skill 融入）
    if h.get("gan_he"):
        facts.append("日干五合：{}与{}（传统上主互相吸引）".format(
            h.get("a_bazi", {}).get("day", "")[:1],
            h.get("b_bazi", {}).get("day", "")[:1]))
    if h.get("god_a_sees_b"):
        facts.append("日主十神互见：{}见{}为{}，{}见{}为{}".format(
            h.get("a_bazi", {}).get("day", "")[:1],
            h.get("b_bazi", {}).get("day", "")[:1], h.get("god_a_sees_b", ""),
            h.get("b_bazi", {}).get("day", "")[:1],
            h.get("a_bazi", {}).get("day", "")[:1], h.get("god_b_sees_a", "")))
    if warm and warm.get("one_liner"):
        facts.append("人话结论：" + warm["one_liner"])
    return facts


def facts_qiming(q: dict, gender: str | None = None) -> list[str]:
    fe = q.get("five_elements") or {}
    miss = fe.get("missing") or []
    names = [n.get("full_name") for n in (q.get("full_names") or [])[:3]
             if n.get("full_name")]
    # R191b（B-016）：性别必须显式喂给模型——否则它会自己猜，实测猜出
    # 「林先生」（入参 gender=女）。称谓是事实，不是模型可选项。
    facts = [
        "姓氏：{}".format(q.get("surname", "")),
        "性别：{}".format("女" if gender == "女" else
                          ("男" if gender == "男" else "未填写")),
        "五行分布：{}".format(fe.get("counts", {})),
        "所缺或最弱行：{}".format("、".join(miss) if miss else "无"),
    ]
    if names:
        facts.append("推荐完整名：" + "、".join(names))
    return facts


# ---------------------------------------------------------------------------
# 自测（离线部分：配置缺失降级 / transport 注入 / 净化器）
# ---------------------------------------------------------------------------
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
    assert facts_qiming({"surname": "林", "five_elements": {},
                         "full_names": []})[1] == "性别：未填写"
    print("PASS facts 组装器 ×4（含 B-016 性别事实）")

    print("\n全部自测通过。在线联调命令见 specs/006-llm-polish/spec.md 判据 1。")
