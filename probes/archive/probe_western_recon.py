"""READ-ONLY recon of the generality test set (T7-c..g).

Round 1: what is actually on disk, and does any canonical-address marker exist in the
bytes? No writes anywhere. Mirrors the questions bcv.py had to answer for the Bibles.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Lenovo\Desktop\projects\books")
MAN = ROOT / "data" / "catalog" / "generality_manifest.json"

SLUGS = [
    "plato-republic", "shakespeare", "euclid-elements",
    "darwin-origin", "herodotus", "homer-iliad-but", "homer-iliad-pope",
]


def load(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def gut_bounds(t: str) -> tuple[int, int]:
    """Gutenberg licence boilerplate bounds -- trap 4 (licence text)."""
    s = re.search(r"\*\*\*\s*START OF (?:TH(?:E|IS) )?PROJECT GUTENBERG.*?\*\*\*", t)
    e = re.search(r"\*\*\*\s*END OF (?:TH(?:E|IS) )?PROJECT GUTENBERG.*?\*\*\*", t)
    return (s.end() if s else 0), (e.start() if e else len(t))


def show(label: str, pat: str, t: str, limit: int = 4, flags=re.M) -> int:
    rx = re.compile(pat, flags)
    hits = list(rx.finditer(t))
    print(f"    {label:<34} n={len(hits)}")
    for m in hits[:limit]:
        frag = m.group(0)[:78].replace("\n", "\\n")
        print(f"       @{m.start():>7} {frag!r}")
    return len(hits)


def main() -> None:
    man = {d["slug"]: d for d in json.loads(MAN.read_text(encoding="utf-8"))}
    for slug in SLUGS:
        d = man[slug]
        print("=" * 100)
        print(f"{slug}  tier={d['tier']}  expected={d['expected_address_scheme']!r}")
        print(f"  title={d['title'][:70]!r} translators={d.get('translators')}")
        print(f"  formats on disk: {sorted(d['files'])}")
        if "txt" not in d["files"]:
            print("  !! NO .txt IN MANIFEST")
            hp = ROOT / d["files"]["html"]["path"]
            h = load(hp)
            print(f"  html {hp.name}: bytes={hp.stat().st_size} chars={len(h)}")
            continue
        tp = ROOT / d["files"]["txt"]["path"]
        t = load(tp)
        b0, b1 = gut_bounds(t)
        body = t[b0:b1]
        print(f"  txt {tp.name}: bytes={tp.stat().st_size} chars={len(t)} "
              f"body=[{b0}:{b1}] body_chars={len(body)} lines={body.count(chr(10))}")
        print("  --- first 25 non-empty body lines ---")
        n = 0
        off = b0
        for line in body.splitlines():
            if line.strip():
                print(f"    L{n:<3} @{off:>7} {line[:92]!r}")
                n += 1
                if n >= 25:
                    break
            off += len(line) + 1
        print("  --- candidate marker families (whole file, incl. boilerplate) ---")
        show("stephanus  NNNa-e paren/bracket", r"[\[(]\s*\d{2,3}\s*[a-e]\s*[\])]", t)
        show("stephanus  bare NNNa line-init", r"^\s*\d{2,3}[a-e]\b.*", t)
        show("ACT ...", r"^\s*ACT[ \t]+[IVXL0-9]+.*", t)
        show("SCENE ...", r"^\s*SCENE[ \t]+[IVXL0-9]+.*", t)
        show("BOOK ...", r"^\s*BOOK[ \t]+[IVXL0-9]+.*", t)
        show("CHAPTER ...", r"^\s*CHAPTER[ \t]+[IVXL0-9]+.*", t)
        show("PROP(OSITION) ...", r"^\s*PROP(?:OSITION)?\.?[ \t]*[IVXL0-9]+.*", t)
        show("right-margin line no (>=4 sp + digits)",
             r"^.*\S[ \t]{4,}\d{1,4}[ \t]*$", t)
        show("line-init bare int (1-3 digits alone)", r"^[ \t]{0,8}(\d{1,3})\.?[ \t]*$", t)
        show("line-init 'NN.' + prose (section no)", r"^[ \t]{0,8}\d{1,3}\.[ \t]+[A-Z\"']", t)
        show("[Page NN] anchor", r"\[Page[^\]]{0,12}\]", t)
        show("[NN] footnote ref", r"\[\d{1,3}\]", t)


if __name__ == "__main__":
    sys.exit(main())
