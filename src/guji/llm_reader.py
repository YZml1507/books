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
    "你是古籍命理资料的研究助理。用户会给你：一个人的生辰八字坐标，以及从"
    "命理古籍（三命通會、星學大成、李虛中命書等）检索到的原文引文。\n"
    "规则：\n"
    "1. 解读只能基于给定的原文引文展开，引文里没有的内容不得编造，"
    "不确定就明说'引文未涉及'。\n"
    "2. 输出分两段：先列'所依据的原文引文'（逐条照抄，注明出处），"
    "再给'解读'（白话，标注这是 LLM 生成、非古籍原文）。\n"
    "3. 不给出医疗/投资/法律等现实决策建议；命理内容仅作传统文化资料呈现。\n"
    "4. 语气克制，不作确定性断言。"
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


def interpret(render_line: str, evidence: list[dict], question: str | None = None) -> str:
    """坐标 + 原文证据 -> LLM 白话解读（纯函数，无副作用，不落库）。

    evidence: bazi_lookup 返回的 [{work_id, layer, page_anchor, file, text}, ...]
    """
    cfg = _cfg()
    if not cfg["key"]:
        raise RuntimeError("LLM_API_KEY 未配置：设置环境变量 LLM_API_KEY 后再用 --llm")

    ev_lines = []
    for i, e in enumerate(evidence, 1):
        page = f"@{e['page_anchor']}" if e.get("page_anchor") else "@?"
        ev_lines.append(f"[{i}] {e['work_id']}·{e.get('layer','')} {page} "
                        f"({e.get('file','')}): {e['text'][:220]}")
    user = f"排盘：{render_line}\n\n检索到的古籍原文引文：\n" + "\n".join(ev_lines)
    if question:
        user += f"\n\n用户问题：{question}"

    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 800,
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
