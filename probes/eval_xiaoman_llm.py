"""probes/eval_xiaoman_llm.py — 小满真机事实遵循评测（R229o）。

需要真实 LLM：环境有 BOOKS_LLM_API_KEY 时跑；无则 SKIP-ENV 退出 2。
不进 CI——每次烧真额度且结果有温度漂移，定位为人工复验工具：

    BOOKS_LLM_API_KEY=... .venv/bin/python probes/eval_xiaoman_llm.py

流程：spawn uvicorn（不起 mock）→ 14 条问法逐条 POST /api/chat +
轮询 /api/ai/{tid} → 打印「事实行 | 回复」对照，人工/半自动评分。
每条用全新 session_id（_CHAT_MAX_TURNS=6 防沉迷收尾会吃掉后续轮次，
共用会话会测到收尾文案而不是模型）。

退出码：0=全部有回复且零裸 *；1=有失败；2=无 key / 服务起不来。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 18377
BASE = f"http://127.0.0.1:{PORT}"

MSGS = [
    "明天适合出行吗", "大后天能剪头发吗", "下周三面试顺利吗",
    "今晚能跟对象约会吗", "我明天想去领证", "后天适合搬家吗",
    "今天适合养猫吗", "这周五去面试好不好", "下周末出去玩行吗",
    "今天宜做什么", "明天適合出行嗎", "星期天去逛街可以吗",
    "跟对象吵架了怎么办", "周三去拔牙可以吗",
    # R229z：节日/绝对日期/后缀表达——事实行应锚定真实日期
    "中秋节适合搬家吗", "国庆节前一天出行怎么样", "10月25号相亲好吗",
    "去年中秋那天我去面试了",
    # R229z续7/9：节气/农历/月末表达
    "冬至那天吃饺子合适吗", "惊蛰后去剪头发怎么样",
    "腊月廿三祭灶好不好", "下个月5号开业行吗",
]


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())


def main() -> int:
    if not os.getenv("BOOKS_LLM_API_KEY"):
        print("eval_xiaoman_llm SKIP-ENV: 无 BOOKS_LLM_API_KEY——"
              "这是烧真额度的人工复验工具，不进 CI")
        return 2

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.app:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", PORT), 0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("eval_xiaoman_llm SKIP-ENV: 服务起不来")
            return 2

        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "web"))
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from web import services
        import datetime
        now = datetime.datetime.now()

        sid_base = "eval-" + str(int(time.time()))
        n_fail = 0
        for i, m in enumerate(MSGS):
            r = _post("/api/chat",
                      {"session_id": f"{sid_base}-{i}", "message": m})
            tid = r.get("chat_task_id")
            reply = ""
            if tid:
                for _ in range(80):
                    a = _get(f"/api/ai/{tid}")
                    if a.get("status") == "done":
                        reply = a.get("text", "")
                        break
                    if a.get("status") == "failed":
                        reply = "ERR:" + str(a)
                        n_fail += 1
                        break
                    time.sleep(0.75)
            else:
                n_fail += 1
            facts = services.chat_huangli_facts(m, now)
            print("=" * 70)
            print("Q:", m)
            print("FACTS:", " | ".join(facts) if facts else "（无黄历事实）")
            print("REPLY:", reply[:400].replace("\n", " "))
            if "*" in reply:
                print("!! 含裸 *")
                n_fail += 1
            if not reply:
                n_fail += 1
        print("=" * 70)
        if n_fail:
            print(f"eval_xiaoman_llm: {n_fail} 条失败/异常")
            return 1
        print(f"eval_xiaoman_llm: {len(MSGS)} 条全部有回复、零裸 * "
              "——事实遵循度请对照 FACTS/REPLY 人工核")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
