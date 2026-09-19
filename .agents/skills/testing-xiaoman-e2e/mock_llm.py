#!/usr/bin/env python3
"""Mock OpenAI-compatible LLM server for e2e testing 小满的解忧铺.

Binds 127.0.0.1:8901 and implements POST /v1/chat/completions, returning a
fixed assistant reply. Every request body is appended to mock_llm_requests.log
(next to this script) so tests can verify backend-injected facts
(e.g. 黄历判定：…).

Usage:
    python3 mock_llm.py                          # serve on 127.0.0.1:8901
    MOCK_LLM_PORT=8902 MOCK_LLM_REPLY='…' python3 mock_llm.py

The default reply deliberately contains a paired `**粗体**` AND an unpaired
`**` to exercise the `**`-fallback in renderRichText; override with
MOCK_LLM_REPLY if you need plain text.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("MOCK_LLM_PORT", "8901"))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_llm_requests.log")
REPLY = os.environ.get(
    "MOCK_LLM_REPLY",
    "这是一个**模拟**回复。\n"
    "今天的判断是：宜出行。\n"
    "这一行留着不配对的 ** 用于测试 fallback。",
)


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(raw.decode("utf-8", "replace") + "\n")
        if self.path.rstrip("/").endswith("/chat/completions"):
            self._json(200, {
                "id": "mock-1",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": REPLY}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })
        else:
            self._json(404, {"error": {"message": f"no mock route for {self.path}"}})

    def do_GET(self):  # noqa: N802
        self._json(200, {"status": "ok", "port": PORT})

    def log_message(self, fmt, *args):
        sys.stderr.write("mock_llm: " + fmt % args + "\n")


if __name__ == "__main__":
    print(f"mock_llm on http://127.0.0.1:{PORT}/v1  (requests logged to {LOG})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
