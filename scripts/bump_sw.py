#!/usr/bin/env python3
"""把 sw.js 的 CACHE 名与 shell-hash 标记同步到 app.js 当前内容哈希。

用法：改了 web/static/app.js 后跑 `python scripts/bump_sw.py`。
selftest 的 sw.shell_hash 闸会强制这一步——不改就直接红。
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "web" / "static" / "app.js"
SW = ROOT / "web" / "static" / "sw.js"

LINE = re.compile(r"var CACHE = '[^']*';\s*// shell-hash: \S+")


def shell_hash() -> str:
    return hashlib.sha256(APP_JS.read_bytes()).hexdigest()[:12]


def main() -> int:
    h = shell_hash()
    src = SW.read_text(encoding="utf-8")
    new_line = f"var CACHE = 'books-shell-{h}';   // shell-hash: {h}"
    out, n = LINE.subn(new_line, src)
    if n != 1:
        raise SystemExit(f"sw.js 里 shell-hash 行匹配 {n} 处（应恰 1 处）")
    if out == src:
        print(f"已是最新 books-shell-{h}")
        return 0
    SW.write_text(out, encoding="utf-8")
    print(f"CACHE -> books-shell-{h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
