#!/usr/bin/env python3
"""导出全部用户数据为单个 JSON——换电脑/重装时的迁移闭环。

    python scripts/export_userdata.py [输出路径]

默认写到 ./books_userdata_<日期>.json。覆盖三类用户库：
  * paipan_history.db：records（排盘台账）
  * knowledge.db   ：thread/turn/derived/evidence/favorites/user_prefs
                    （研究线程、收藏、偏好——含 WAL 侧车里尚未
                    checkpoint 的已提交写入）

corpus.db 不含用户数据（可重建），data/raw/ 是语料不是数据——都不导出。
mode=ro 只读打开：绝不写库；普通读连接能正确看到 WAL 里未 checkpoint
的已提交数据（immutable=1 会跳过 WAL 读漏尾部写入，这里不用它）。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "data", "index")

TABLES = {
    "paipan_history.db": ["records"],
    "knowledge.db": ["thread", "turn", "derived", "evidence",
                     "favorites", "user_prefs"],
}


def _dump(db_path: str, tables: list[str]) -> dict:
    if not os.path.exists(db_path):
        return {"_missing": True}
    # mode=ro：只读；WAL 模式下读者照样读到 wal 中已提交页
    uri = "file:" + db_path + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        have = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        out = {}
        for t in tables:
            if t not in have:
                out[t] = {"_missing_table": True}
                continue
            out[t] = [dict(r) for r in
                      conn.execute(f"SELECT * FROM {t}")]
        return out
    finally:
        conn.close()


def main() -> int:
    out_path = (sys.argv[1] if len(sys.argv) > 1 else
                os.path.join(os.getcwd(),
                             "books_userdata_" +
                             time.strftime("%Y%m%d") + ".json"))
    payload = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "format": "books-userdata-v1",
        "dbs": {},
    }
    total = 0
    for db_name, tables in TABLES.items():
        dumped = _dump(os.path.join(INDEX, db_name), tables)
        payload["dbs"][db_name] = dumped
        for t, rows in dumped.items():
            if isinstance(rows, list):
                total += len(rows)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"已导出 {total} 行用户数据 -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
