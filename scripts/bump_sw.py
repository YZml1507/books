#!/usr/bin/env python3
"""把 sw.js 的 CACHE 名与 shell-hash 标记同步到 shell 文件集的当前内容哈希。

用法：改了 web/static/ 下任何壳文件后跑 `python scripts/bump_sw.py`。
selftest 的 sw.shell_hash 闸会强制这一步——不改就直接红。

R230t（R31-P2-11）：此前只哈希 app.js——改 styles.css/index.html/
图标不 bump，老客仍粘旧壳（缓存名没变，SW 不重装）。现在哈希 SHELL
预缓存清单里所有文件的拼接内容；清单本身变了也计入。
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"
SW = STATIC / "sw.js"

LINE = re.compile(r"var CACHE = '[^']*';\s*// shell-hash: \S+")
SHELL_LIST = re.compile(r"var SHELL = \[([^\]]*)\]")


# R2345（R63-P2-2）：二线资产（牌面/星座卡/海报底图/字体分片）只走
# 运行时缓存——内容变更不换 CACHE 名 = 老客无限期看旧图。纳入哈希：
# 改这些文件同样必须 bump，SW 重装后运行时缓存随 CACHE 名一起换新。
EXTRA_GLOBS = (
    "tarot/*",
    "cream/zodiac-*.jpg",
    "shared/poster-bg-*.jpg",
    "cream/poster-mascot.png",
    "cream/icon-512-maskable.png",
    "fonts/lxgw/lxgwwenkai-regular-subset-*.woff2",
    # R2349u（R91-P2-5）：og 分享卡此前漏出哈希——换图不 bump，
    # 已装用户/分享爬虫无限期看旧卡。
    "shared/og-card.jpg",
)


def _extra_paths() -> list[Path]:
    out: list[Path] = []
    for g in EXTRA_GLOBS:
        out.extend(sorted(STATIC.glob(g)))
    return out


def _shell_paths(src: str) -> list[Path]:
    m = SHELL_LIST.search(src)
    if not m:
        raise SystemExit("sw.js 里找不到 SHELL 预缓存清单")
    out = []
    for url in re.findall(r"'([^']+)'", m.group(1)):
        if url == "/":
            url = "/static/index.html"
        if url.startswith("/static/"):
            out.append(STATIC / url[len("/static/"):])
    return out


def shell_hash() -> str:
    src = SW.read_text(encoding="utf-8")
    h = hashlib.sha256()
    for p in _shell_paths(src) + _extra_paths():
        h.update(p.name.encode())
        h.update(b"\0")
        # R2349u（R91-P2-5）：缺文件此前按 MISSING 静默计哈希——
        # 核心壳件漏装会让 SW install 失败且闸还绿着。直接报错。
        if not p.exists():
            raise SystemExit(f"壳清单文件缺失：{p.relative_to(STATIC)}")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:12]


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
