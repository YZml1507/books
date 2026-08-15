"""web/app.py — 八字排盘网页端后端（FastAPI）。

编排层，复用 src/guji 的既有模块，不复制业务逻辑：
  POST /api/bazi   {year, month, day, hour, gender, use_llm, question}
                  -> {paipan, evidence[], llm}
  GET  /          单页前端（web/static/index.html）

红线遵守（与 CLI 一致）：
  * LLM KEY 只在服务端（llm_config.json，已 gitignore），API 响应不回传 key。
  * LLM 解读不落库、不缓存——每次请求即时调用，仅进程内返回。
  * 引用与生成分离：evidence 与 llm 分字段返回，前端分段展示。
  * 输入校验在系统边界（Pydantic + 显式范围检查），非法输入 400 中文报错。
  * 首请求可能较慢（bge 语义路径首次加载模型/向量缓存），后续复用缓存。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from guji import llm_reader  # noqa: E402
from guji.bazi import compute  # noqa: E402
from guji.bazi_lookup import retrieve_fast, retrieve_semantic  # noqa: E402

app = FastAPI(title="八字命理检索", version="0.1.0")

INDEX = os.path.join(ROOT, "web", "static", "index.html")

YEAR_LO, YEAR_HI = 1900, 2100


class BaziRequest(BaseModel):
    year: int = Field(..., description="公历年份")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    use_llm: bool = False
    question: str | None = None

    def validate_ranges(self) -> None:
        if not (YEAR_LO <= self.year <= YEAR_HI):
            raise HTTPException(400, f"year 需在 {YEAR_LO}-{YEAR_HI} 之间（节气表适用范围）")
        if not (1 <= self.month <= 12):
            raise HTTPException(400, "month 需在 1-12")
        if not (1 <= self.day <= 31):
            raise HTTPException(400, "day 需在 1-31")
        if not (0 <= self.hour <= 23):
            raise HTTPException(400, "hour 需在 0-23")
        if self.gender not in ("男", "女"):
            raise HTTPException(400, "gender 只能是 男 或 女")


@app.get("/")
def index():
    if not os.path.exists(INDEX):
        raise HTTPException(500, "前端文件缺失：web/static/index.html")
    return FileResponse(INDEX)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": llm_reader.available()}


@app.post("/api/bazi")
def bazi_api(req: BaziRequest):
    req.validate_ranges()
    try:
        b = compute(req.year, req.month, req.day, req.hour, req.gender)
    except Exception as exc:  # 排盘异常（如节气表范围外）→ 4xx，不崩
        raise HTTPException(422, f"排盘失败：{exc}") from exc

    evidence = retrieve_fast(b, per_query=2, per_work=1)
    # 去重（同一单元 FTS 多词命中），保留前 12 条
    seen, dedup = set(), []
    for e in evidence:
        k = (e["work_id"], e["page_anchor"], e["text"][:40])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
        if len(dedup) >= 12:
            break
    evidence = dedup

    llm_out = {"ok": False, "text": None, "model": None}
    if req.use_llm:
        if not llm_reader.available():
            llm_out["text"] = ("未配置 LLM：请复制 llm_config.example.json 为 "
                               "llm_config.json 并填写 base_url/api_key。")
        else:
            try:
                text = llm_reader.interpret(b.render(), evidence, req.question)
                llm_out = {"ok": True, "text": text,
                           "model": os.environ.get("LLM_MODEL", "llm_config.json")}
            except Exception as exc:  # 网络/API 错误：引用证据不受影响
                llm_out["text"] = f"LLM 调用失败：{exc}"

    return {
        "paipan": {
            "render": b.render(),
            "nayin": b.nayin,
            "warn": b.warn,
        },
        "evidence": evidence,
        "llm": llm_out,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
