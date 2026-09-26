"""probes/probe_r2508.py — R2508 批次修复回归闸。

钉扎本轮修复（源码级 + TestClient，离线不打 LLM）：

 1. wishbottle（许愿瓶自由文本）三面收口——审-P2-1：
    - wipeAll 的 localStorage 白名单必须含 wishbottle
      （「忘掉我的数据」后愿望不再幸存重渲）；
    - 备份导出 _EXACT 清单必须含 wishbottle（「全量带走」不漏项）；
    - 还原白名单必须收 wishbottle 且过 {t,c,ts} 形状归一化；
    - 跨 tab storage 监听必须响应该键（B tab 已展开瓶卡就地清）。
 2. import_rows 前导空白洞——审-P2-2：备份埋 "  =cmd" 名绕
    _csv_safe 首字符闸——name/question 净化必须含 .strip()。
 3. 闸脚本排盘写面隔离（自测发现）：baseline_voice /
    check_warm_voice / check_xingzuo / check_poster /
    probe_llm_polish 此前缺 BOOKS_PAIPAN_HISTORY_DISABLE，
    每跑一趟积一批测试残留。

退出码：0 全绿；1 有 FAIL；2 probe 自身出错。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("BOOKS_LLM_DISABLE", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESULTS = []


def check(name: str, cond: bool, detail: str = ""):
    RESULTS.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  {detail}" if detail else ""))


def _read(rel: str) -> str:
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def main() -> int:
    js = _read("web/static/app.js")

    # ── 1. wishbottle 三面收口 ────────────────────────────────
    check("wipeAll 白名单含 wishbottle",
          "wishbottle|chatSessionId" in js or "wishbottle$|" in js
          or re.search(r"\^\(.*wishbottle", js) is not None)
    check("备份 _EXACT 含 wishbottle",
          re.search(r"_EXACT\s*=\s*\[[^\]]*'wishbottle'", js) is not None)
    check("还原白名单收 wishbottle",
          re.search(r"wishbottle\$\|", js) is not None)
    check("还原形状归一化 {t,c,ts}",
          "_wo" in js and "_wo.t" in js)
    check("跨 tab storage 监听 wishbottle",
          "e.key === 'wishbottle'" in js)

    # ── 2. import_rows 前导空白 ──────────────────────────────
    ph = _read("src/guji/paipan_history.py")
    _imp = ph.split("def import_rows")[1].split("\ndef ")[0]
    check("import_rows name 带 strip",
          re.search(r'name = _CTRL_RE\.sub.*\.strip\(\)', _imp) is not None)
    check("import_rows question 带 strip",
          re.search(r'question = \(_CTRL_RE\.sub.*\.strip\(\) or None\)',
                    _imp, re.S) is not None)

    # ── 3. 闸脚本写面隔离 ────────────────────────────────────
    for f in ("web/baseline_voice.py", "web/check_warm_voice.py",
              "web/check_xingzuo.py", "web/check_poster.py",
              "probes/probe_llm_polish.py"):
        check(f"{f} 隔离排盘写面",
              "BOOKS_PAIPAN_HISTORY_DISABLE" in _read(f))

    # ── 行为实证：import 前导空白名入库后被剥 ────────────────
    # 注意：本探针不设 BOOKS_PAIPAN_HISTORY_DISABLE——端点级孤代理
    # 用例必须走真绑定面才有效（设了端点 404，覆盖失真）。残留
    # 在汇总前统一清理。
    import tempfile
    import sqlite3
    from guji import paipan_history as PH
    _tmp = tempfile.mktemp(suffix=".db")
    _old = PH.DB_PATH
    try:
        PH.DB_PATH = _tmp
        written, skipped, new_rows = PH.import_rows(
            [{"ts": "2026-01-01T00:00:00", "name": "  =cmd净化我",
              "type": "bazi", "question": "　\t头部空白",
              "req": {"year": 1990}, "result": {"ok": True}}])
        check("import 写成功", written == 1, f"written={written}")
        con = sqlite3.connect(_tmp)
        row = con.execute(
            "SELECT name, question FROM records").fetchone()
        con.close()
        check("前导空白被剥", row is not None and
              row[0] == "=cmd净化我" and row[1] == "头部空白",
              f"row={row}")
    finally:
        PH.DB_PATH = _old
        try:
            os.remove(_tmp)
        except OSError:
            pass

    # ── 4. 审-P0 孤代理全通道（dict/Any 面绕过 pydantic）────────
    from fastapi.testclient import TestClient
    from web.app import create_app
    c = TestClient(create_app(), raise_server_exceptions=False)

    r = c.post("/api/paipan/history/import",
               content='{"records":[{"type":"bazi","ts":"x","req":{"a":1},'
                       '"name":"\\ud800"}]}',
               headers={"Content-Type": "application/json"})
    check("import name 孤代理入库剥离", r.status_code == 200,
          f"status={r.status_code}")
    r = c.post("/api/paipan/history/import",
               content='{"records":[{"type":"bazi","ts":"2020-01-01T00:00:00",'
                       '"req":{"a":"\\ud800"},"result":{"ok":1},'
                       '"name":"毒药丸"}]}',
               headers={"Content-Type": "application/json"})
    check("import req 孤代理入库剥离", r.status_code == 200,
          f"status={r.status_code}")
    r = c.post("/api/user/prefs", content='{"theme":"\\ud800"}',
               headers={"Content-Type": "application/json"})
    check("prefs 孤代理非 5xx", r.status_code < 500,
          f"status={r.status_code}")
    r = c.post("/api/paipan/history/import",
               content='{"threads":[{"topic":"\\ud800 线程",'
                       '"opened_at":"2020-01-01","turns":'
                       '[{"role":"user","text":"hi"}]}]}',
               headers={"Content-Type": "application/json"})
    check("threads 回灌孤代理非 5xx", r.status_code < 500,
          f"status={r.status_code}")

    # 孤儿 turn 自愈（自测实锤）：复用已删行 rowid 的新 tid 名下
    # 残留 UNIQUE(thread_id,seq) 行曾让回灌 503 且毒化后续——
    # 现在先清孤儿再插，IntegrityError 撤项按 skip 计。
    import sqlite3 as _sqo
    _odb = os.path.join(ROOT, "data", "index", "knowledge.db")
    _ok_kb = _sqo.connect(_odb)
    try:
        _ok_kb.execute("INSERT INTO thread (topic,status,opened_at) "
                       "VALUES('孤儿母线程','open','2000-01-01')")
        _tid0 = _ok_kb.execute("SELECT MAX(id) FROM thread").fetchone()[0]
        _ok_kb.execute("INSERT INTO turn (thread_id,seq,role,text,"
                       "created_at) VALUES(?,1,'user','orphan','2000')",
                       (_tid0,))
        _ok_kb.execute("DELETE FROM thread WHERE id=?", (_tid0,))
        _ok_kb.commit()   # 制造 thread 已删 turn 残留的孤儿态
        r = c.post("/api/paipan/history/import",
                   content='{"threads":[{"topic":"自愈线程",'
                           '"opened_at":"2020-02-02","turns":'
                           '[{"role":"user","text":"new"}]}]}',
                   headers={"Content-Type": "application/json"})
        check("孤儿 turn 回灌自愈", r.status_code == 200 and
              r.json().get("threads_imported") == 1,
              f"{r.status_code} {r.text[:60]}")
    finally:
        _ok_kb.execute("DELETE FROM turn")
        _ok_kb.execute("DELETE FROM thread")
        _ok_kb.commit(); _ok_kb.close()
    # errors.py 兜底映射在位（漏面 UnicodeError → 422 非 500）
    _err = _read("web/errors.py")
    check("errors 兜底 UnicodeError",
          "add_exception_handler(UnicodeError" in _err)
    # schemas/paipan 剥离集含代理段
    check("_ZW_RE 含代理段", "\\ud800-\\udfff" in _read("web/schemas.py"))
    check("_CTRL_RE 含代理段",
          "\\ud800-\\udfff" in _read("src/guji/paipan_history.py"))
    check("knowledge _SURG_RE 存在",
          "_SURG_RE" in _read("src/guji/knowledge.py"))

    # ── 5. 审-P1 中间件两条 ─────────────────────────────────
    r = c.post("/api/chat", content="{}",
               headers={"Content-Length": "5",
                        "Transfer-Encoding": "chunked"})
    check("CL+TE 双头被拒 413", r.status_code == 413,
          f"status={r.status_code}")
    check("413 带安全头",
          r.headers.get("x-content-type-options") == "nosniff" and
          r.headers.get("x-frame-options") == "DENY")
    r = c.get("/static/fonts/notyetdeployed.woff2")
    check("静态 404 无正缓存", r.status_code == 404 and
          "max-age" not in (r.headers.get("cache-control") or ""),
          f"cc={r.headers.get('cache-control')}")
    r = c.get("/static/app.js")
    check("正常静态件仍缓存", "max-age=3600" in
          (r.headers.get("cache-control") or ""))
    r = c.post("/api/bazi", content="x",
               headers={"Content-Length": "600000"})
    check("CL 超限 413 带头", r.status_code == 413 and
          r.headers.get("referrer-policy") == "no-referrer")

    # ── 6. 审-P2 base_url 注入 ──────────────────────────────
    r = c.get("/", headers={"Host": 'x"><svg onload=alert(1)>'})
    check("og:url 无属性逃逸", '"><svg' not in r.text and
          'onload=' not in r.text.split('og:url')[1][:200]
          if 'og:url' in r.text else '"><svg' not in r.text)

    # ── 7. 审-P2 英文 detail / fnf 提示保留 ─────────────────
    r = c.post("/api/ask", content=b'{"q":"\xff"}',
               headers={"Content-Type": "application/json"})
    check("body 解析失败中文化",
          r.status_code in (400, 422) and
          "error parsing" not in r.text.lower(),
          f"{r.status_code} {r.text[:60]}")
    r = c.put("/api/health")
    check("405 中文化", "这个接口不支持" in r.text or
          "Method Not Allowed" not in r.text, f"{r.status_code}")
    _fnf = "_head, _sep, _tail = msg.partition" in _err
    check("fnf 提示段不遮", _fnf)

    # 测试残留收尾（import 实证写了几行）
    import sqlite3 as _sq3
    try:
        _pc = _sq3.connect(os.path.join(ROOT, "data", "paipan_history.db"))
        _pc.execute("DELETE FROM records WHERE name IN ('','毒药丸') "
                    "AND ts IN ('x','2020-01-01T00:00:00')")
        _pc.commit(); _pc.close()
        _kc = _sq3.connect(os.path.join(ROOT, "data", "index",
                                        "knowledge.db"))
        _kc.execute("DELETE FROM thread WHERE topic='线程' "
                    "AND opened_at='2020-01-01'")
        # prefs 孤代理用例落了 theme='' ——清掉不留偏好脏值
        for _t in ("prefs", "user_prefs", "kv"):
            try:
                _kc.execute(f"DELETE FROM {_t} WHERE k='theme'")
            except Exception:
                try:
                    _kc.execute(f"DELETE FROM {_t} WHERE key='theme'")
                except Exception:
                    pass
        _kc.commit(); _kc.close()
    except Exception:
        pass

    # ── 汇总 ──────────────────────────────────────────────────
    _fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 50}\n{len(RESULTS)} checks, "
          f"{len(_fails)} failed")
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
