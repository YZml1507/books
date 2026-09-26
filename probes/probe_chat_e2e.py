#!/usr/bin/env python3
"""probe_chat_e2e — chat ENABLED 全链常驻闸（TestClient + 进程内 mock LLM）。

R2570：/api/chat→/api/ai/{tid} 的 happy path 此前只有手工 mock
验证（R2569），CI 零覆盖——check_async_ai 只管 DISABLE 降级面。
进程内 HTTPServer 当 OpenAI 兼容端点，断言：

1. POST /api/chat 返回 chat_task_id，轮询 /api/ai/{tid} 到 done。
2. 回复经后端 sanitize——配对 ** 记号剥掉（闲聊人设纯文本口径）。
3. mock 请求体含三层注入：人设 system + verdict_facts「黄历判定」
   + 用户消息；客户端 facts 透传在位。
4. 危机短路：罐头任务 done 文案，mock 零命中（不烧 LLM）。

用法：python3 probes/probe_chat_e2e.py（离线可跑，零外部服务）。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

MOCK_REPLY = "宝，这是**模拟**回复。\n不配对的 ** 会留给前端兜底。"
# 后端 sanitize 剥配对 ** 记号、孤儿 ** 原样透传（前端 renderRichText 兜底）
EXPECTED = "宝，这是模拟回复。\n不配对的 ** 会留给前端兜底。"
_HITS: list[dict] = []


class _MockLLM(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        _HITS.append(body)
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(
            {"choices": [{"message": {"content": MOCK_REPLY}}]}
        ).encode())

    def log_message(self, *a):   # 静默
        pass


def main() -> int:
    srv = HTTPServer(("127.0.0.1", 0), _MockLLM)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    saved = {k: os.environ.get(k) for k in (
        "BOOKS_LLM_API_KEY", "BOOKS_LLM_BASE_URL",
        "BOOKS_LLM_MODEL", "BOOKS_LLM_DISABLE")}
    os.environ["BOOKS_LLM_API_KEY"] = "probe-mock"
    os.environ["BOOKS_LLM_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
    os.environ["BOOKS_LLM_MODEL"] = "probe-mock"
    os.environ.pop("BOOKS_LLM_DISABLE", None)

    fails = []
    try:
        from fastapi.testclient import TestClient
        from web.app import app
        client = TestClient(app)

        # 1) happy path：黄历类问题触发 verdict_facts 注入
        r = client.post("/api/chat", json={
            "session_id": "probe-chat-e2e",
            "message": "明天适合出行吗",
            "client_date": "2026-09-27"})
        if r.status_code != 200 or "chat_task_id" not in r.json():
            fails.append(f"chat post: {r.status_code} {r.text[:80]}")
        else:
            tid = r.json()["chat_task_id"]
            st = {}
            for _ in range(60):
                time.sleep(0.25)
                st = client.get(f"/api/ai/{tid}").json()
                if st.get("status") in ("done", "failed"):
                    break
            if st.get("status") != "done":
                fails.append(f"poll not done: {st.get('status')}")
            elif st.get("text") != EXPECTED:
                fails.append(f"reply mismatch: {st.get('text')!r}")

        # 2) 三层注入 + facts 透传
        hits = list(_HITS)
        if not hits:
            fails.append("mock llm zero hits")
        else:
            body = hits[-1]
            payload = json.dumps(body, ensure_ascii=False)
            if "小满" not in payload:
                fails.append("persona system prompt missing")
            if "黄历判定" not in payload:
                fails.append("verdict_facts 黄历判定 missing")
            if "明天适合出行吗" not in payload:
                fails.append("user message missing")

        # 3) facts 透传
        _HITS.clear()
        r = client.post("/api/chat", json={
            "session_id": "probe-chat-e2e",
            "message": "帮我看看",
            "facts": ["探针事实：日主乙"]})
        if r.status_code == 200 and "chat_task_id" in r.json():
            tid = r.json()["chat_task_id"]
            for _ in range(60):
                time.sleep(0.25)
                st = client.get(f"/api/ai/{tid}").json()
                if st.get("status") in ("done", "failed"):
                    break
            if _HITS and "探针事实：日主乙" not in json.dumps(
                    _HITS[-1], ensure_ascii=False):
                fails.append("client facts passthrough missing")
        else:
            fails.append("facts post failed")

        # 4) 危机短路：罐头任务、mock 零命中
        _HITS.clear()
        r = client.post("/api/chat", json={
            "session_id": "probe-chat-e2e",
            "message": "不想活了"})
        if r.status_code == 200 and "chat_task_id" in r.json():
            st = client.get(f"/api/ai/{r.json()['chat_task_id']}").json()
            if st.get("status") != "done" or not st.get("text"):
                fails.append(f"crisis canned task: {st.get('status')}")
            if _HITS:
                fails.append("crisis path hit mock llm (should not burn)")
        else:
            fails.append("crisis post missing task")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        srv.shutdown()

    if fails:
        for f in fails:
            print("FAIL", f)
        return 1
    print("PASS probe_chat_e2e  4/4 (task->poll->done / 三层注入+facts透传 / 危机罐头零LLM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
