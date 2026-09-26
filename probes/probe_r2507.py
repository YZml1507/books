"""probes/probe_r2507.py — R2507 批次修复回归闸。

钉扎本轮修复（源码级 + TestClient，离线不打 LLM）：

 1. app_research.js 比对爻位校验正反写反（自测实锤 P1）——真实爻名
    规则：2–5 爻「性先位后」（九二/六三/…），初/上「位先性后」
    （初九/上六），乾坤专属用九/用六。旧正则
    (初|二|三|四|五|上)(九|六) 让默认值「九二」都过不了、
    10/12 合法爻名全被拒，反放行二九/五六伪名。

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


# 前端必须遵守的爻名真值表（与后端 accepted-addr 语义一致）。
_YAO_VALID = ["初九", "初六", "九二", "九三", "九四", "九五",
              "六二", "六三", "六四", "六五", "上九", "上六",
              "用九", "用六"]
_YAO_INVALID = ["二九", "三九", "四九", "五九", "二六", "三六",
                "四六", "五六", "九一", "六七", "用二", "初二",
                "九", "abc"]


def main() -> int:
    _js = open(os.path.join(ROOT, "web", "static", "app_research.js"),
               encoding="utf-8").read()
    # 共享 _YAO_RE 常量本体——抽出来对真值表逐条判。
    _m = re.search(r"_YAO_RE\s*=\s*(/[^/]+/)", _js)
    check("_YAO_RE 共享正则存在", _m is not None)
    if _m:
        try:
            _rx = re.compile(_m.group(1)[1:-1])
            _bad = ([y for y in _YAO_VALID if not _rx.match(y)],
                    [y for y in _YAO_INVALID if _rx.match(y)])
            check("14 个合法爻名全放行", not _bad[0], f"拒收={_bad[0]}")
            check("14 个伪名全拒收", not _bad[1], f"放行={_bad[1]}")
        except re.error as e:
            check("_YAO_RE 可编译", False, str(e))
    # 两处调用点都走共享常量（不再各持一份拷贝）。
    check("doAddr 走 _YAO_RE",
          "_asend.indexOf('ayao') >= 0 && _ayv && !_YAO_RE.test(_ayv)"
          in _js)
    check("doCompare 走 _YAO_RE",
          "_cyv && !_YAO_RE.test(_cyv)" in _js)
    # doAddr 的校验必须先于 params 组装、且被 scheme 白名单门控
    # （bcv 等编址下隐藏 ayao 残值不得拦请求）。
    _daddr = _js.split("async function doAddr")[1].split("async function")[0]
    check("doAddr 校验在 _asend 之后",
          _daddr.index("_asend") < _daddr.index("_YAO_RE.test"))

    # 后端对照（TestClient 直测）：合法名进 addr 回显，真值链不断
    from fastapi.testclient import TestClient
    from web.app import create_app
    c = TestClient(create_app())
    for y in ("九二", "六三"):
        r = c.get("/api/compare", params={"gua": 28, "yao": y})
        check(f"后端 compare 收 {y}",
              r.status_code == 200 and y in r.json().get("addr", ""),
              f"status={r.status_code}")

    # ── 汇总 ──────────────────────────────────────────────────
    _fails = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{'=' * 50}\n{len(RESULTS)} checks, "
          f"{len(_fails)} failed")
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
