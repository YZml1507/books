"""probes/probe_r2506.py — R2506 批次修复回归闸。

钉扎本轮修复（TestClient + 源码级钉扎，离线不打 LLM）：

 1. 门页限速桶（审-F1）：不信 XFF 时桶键退化为全局桶——Dockerfile 以
    --forwarded-allow-ips '*' 起 uvicorn，request.client.host 被自填
    XFF[0] 改写，旋转 XFF 即无限换桶。现轮换 XFF 仍 429；且先验口令
    再扣桶——桶满后对口令 POST 仍 302（攻击者灌桶锁不住主人）。
 2. 控制字剥离（审-F2）：liuyao coins 的 question 走 strip_zw（此前
    method!="time" 早退跳过）；bazi location 同剥；备份回灌的
    name/question 剥 C0/双向符（_CTRL_RE）。
 3. GET 日期参数规范形（审-F3）：Py3.11+ fromisoformat 放宽收
    20260101/2026-W01-1——daily date/bday、huangli date/today、
    xingzuo date 与 POST 的 _iso_canonical 同口径，往返比对拒掉；
    today= 年份钳节气表适用界（9999-12-31 此前静默 200）。
 4. 递归 JSON body → 422（审-F4）：~950 层嵌套在 json.loads 抛
    RecursionError——非 JSONDecodeError，此前穿透成英文 500。
 5. 前端钉扎（审-U1..U5，源码级）：日签失败重试钮 + online 兜底
    重拉；historyDetail tabindex/-1 + focus；dailyMore 失败补
    _syncBtn + 重试文案；xz 卡 aria-label 并入日运正文；
    「存个生日」CTA 44px 触控热区。

退出码：0 全绿；1 有 FAIL；2 probe 自身出错。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")
# 端点级写（liuyao record/bazi 自动落台账）不进真实库——import_rows
# 直调仍生效且用例内自删行；不留 CI 残留。
os.environ.setdefault("BOOKS_PAIPAN_HISTORY_DISABLE", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  {detail}" if detail else ""))


def main() -> int:
    from fastapi.testclient import TestClient
    from web.app import create_app

    c = TestClient(create_app())

    # ── 1. 门页限速：全局桶 + 先验后扣（审-F1）─────────────────
    os.environ["BOOKS_ACCESS_TOKEN"] = "r2506-token"
    try:
        gc = TestClient(create_app())
        # 轮换伪造 XFF 打错口令 → 全局桶仍累计，第 11 次起 429
        codes = [gc.post("/_gate", content="key=wrong",
                         headers={"x-forwarded-for": f"9.9.{i}.9"})
                 .status_code for i in range(12)]
        check("伪造 XFF 轮换 → 第 11 次仍 429（全局桶）",
              codes[:10] == [403] * 10 and codes[10] == 429
              and codes[11] == 429, f"codes={codes}")
        # 桶满后对口令 POST 仍放行——主人不被攻击者灌桶锁死
        ok1 = gc.post("/_gate", content="key=r2506-token",
                      follow_redirects=False)
        check("桶满后对口令仍 302（先验后扣不查桶）",
              ok1.status_code == 302,
              f"status={ok1.status_code}")
        # 对口令 ?key= 直通——新客户端（无 cookie）走真分支仍 302
        gc2 = TestClient(create_app())
        ok2 = gc2.get("/?key=r2506-token", follow_redirects=False)
        check("对口令 ?key= 直通仍 302", ok2.status_code == 302,
              f"status={ok2.status_code}")
    finally:
        os.environ.pop("BOOKS_ACCESS_TOKEN", None)

    # ── 2. 控制字剥离（审-F2）─────────────────────────────────
    r = c.post("/api/liuyao", json={
        "method": "coins",
        "question": "面试‮能过吗‬"})
    check("liuyao coins question 剥双向符",
          r.status_code == 200 and "‮" not in r.json().get("question", "")
          and "‬" not in r.json().get("question", ""),
          f"q={r.json().get('question')!r}")
    r = c.post("/api/bazi", json={
        "year": 1990, "month": 5, "day": 15, "hour": 10,
        "gender": "女", "location": "北京\x00朝阳"})
    _loc = ""
    if r.status_code == 200:
        _j = r.json()
        _loc = (_j.get("calc", {}) or {}).get("location") or \
            ((_j.get("input_echo") or {}).get("location")) or ""
    check("bazi location 剥控制字",
          r.status_code == 200 and _loc and "\x00" not in _loc,
          f"status={r.status_code} loc={_loc!r}")

    # 备份回灌：name/question 控制字剥（import_rows 写真实库→读回→
    # 按返回 id 删行清场）
    import sqlite3
    import guji.paipan_history as _ph
    _PDB = _ph.DB_PATH
    _w, _s, _nr = _ph.import_rows(
        [{"ts": "2026-01-01T00:00", "type": "bazi",
          "name": "坏\x00名字‮", "question": "问⁦题",
          "req": {}, "result": {"a": 1}}])
    _con = sqlite3.connect(_PDB)
    try:
        _nm = _con.execute(
            "SELECT name FROM records WHERE id=?",
            (_nr[0]["id"],)).fetchone()[0] if _nr else None
        check("import_rows name 剥控制字",
              _w == 1 and _nm is not None
              and "\x00" not in _nm and "‮" not in _nm,
              f"written={_w} name={_nm!r}")
        for _row in _nr:
            _con.execute("DELETE FROM records WHERE id=?", (_row["id"],))
        _con.commit()
    finally:
        _con.close()

    # ── 3. GET 日期规范形（审-F3）─────────────────────────────
    for path, params, name in [
        ("/api/daily", {"date": "20260101"}, "daily date 紧凑形拒"),
        ("/api/daily", {"date": "2026-W01-1"}, "daily date 周历形拒"),
        ("/api/daily", {"date": "2026-01-01", "bday": "19900101"},
         "daily bday 紧凑形拒"),
        ("/api/xingzuo", {"date": "20260101"}, "xingzuo 紧凑形拒"),
        ("/api/huangli", {"today": "9999-12-31"}, "today 表外年拒"),
        ("/api/huangli", {"today": "20260101"}, "today 紧凑形拒"),
    ]:
        r = c.get(path, params=params)
        check(name + " → 400", r.status_code == 400,
              f"status={r.status_code}")
    # 规范形与合法值不受影响
    r = c.get("/api/daily", params={"date": "2026-01-01"})
    check("daily 规范形仍 200", r.status_code == 200,
          f"status={r.status_code}")
    r = c.get("/api/huangli", params={"today": "2026-01-01"})
    check("huangli today 规范形仍 200", r.status_code == 200,
          f"status={r.status_code}")

    # ── 4. 递归 JSON → 422（审-F4）─────────────────────────────
    _deep = "[" * 1200 + "]" * 1200
    r = c.post("/api/user/prefs", content=_deep,
               headers={"content-type": "application/json"})
    check("递归 JSON → 422 非 5xx", r.status_code == 422,
          f"status={r.status_code}")

    # ── 4b. CORS 预检穿门禁 + 裸 /api 404（审-F5/F6）───────────
    os.environ["BOOKS_ACCESS_TOKEN"] = "r2506-token"
    os.environ["BOOKS_CORS_ORIGINS"] = "https://yzml1507.github.io"
    try:
        gc = TestClient(create_app())
        r = gc.options("/api/bazi", headers={
            "Origin": "https://yzml1507.github.io",
            "Access-Control-Request-Method": "POST"})
        check("门禁下 OPTIONS 预检 → CORS 中间件回答（非 401）",
              r.status_code != 401 and
              r.headers.get("access-control-allow-origin")
              == "https://yzml1507.github.io",
              f"status={r.status_code} acao="
              f"{r.headers.get('access-control-allow-origin')}")
        # 真实 POST 仍被门禁拦（预检放行不松绑业务请求）
        r = gc.post("/api/bazi", json={
            "year": 1990, "month": 5, "day": 15, "hour": 10,
            "gender": "女"},
            headers={"Origin": "https://yzml1507.github.io"})
        check("门禁下真实 POST 仍 401", r.status_code == 401,
              f"status={r.status_code}")
    finally:
        os.environ.pop("BOOKS_ACCESS_TOKEN", None)
        os.environ.pop("BOOKS_CORS_ORIGINS", None)
    r = c.get("/api")
    check("GET /api（裸路径）→ 404 JSON 非 HTML",
          r.status_code == 404 and
          "text/html" not in r.headers.get("content-type", ""),
          f"status={r.status_code} ct={r.headers.get('content-type')}")
    r = c.get("/static")
    check("GET /static（裸路径）→ 404 非 HTML", r.status_code == 404,
          f"status={r.status_code}")

    # ── 5. 前端源码钉扎（审-U1..U5）────────────────────────────
    _js = open(os.path.join(ROOT, "web", "static", "app.js"),
               encoding="utf-8").read()
    _html = open(os.path.join(ROOT, "web", "static", "index.html"),
                 encoding="utf-8").read()
    _css = open(os.path.join(ROOT, "web", "static", "styles.css"),
                encoding="utf-8").read()
    check("U1 日签失败有重试钮",
          "dailyRetry" in _js and "loadDaily();" in _js)
    check("U1 online 兜底重拉",
          "if (!window.__lastDaily)" in _js)
    check("U2 historyDetail tabindex=-1",
          'id="historyDetail" class="ph-detail" tabindex="-1"' in _html)
    check("U2 展开后 focus 到详情",
          "detailEl.focus({ preventScroll: true })" in _js)
    check("U3 dailyMore 失败补 _syncBtn + 重试文案",
          "再点一次按钮重试" in _js)
    check("U4 xz 卡 aria-label 并入正文",
          "s.note || ''" in _js and "点按展开三运明细" in _js)
    check("U5 CTA 44px 触控热区",
          ".daily-personal-cta{padding:11px 0" in _css)

    # ── 汇总 ──────────────────────────────────────────────────
    _fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 50}\n{len(RESULTS)} checks, "
          f"{len(_fails)} failed")
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
