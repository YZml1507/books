"""Q-07 dual-engine disagreement gate — productised from D-001 probes.

Usage:
    python scripts/check_dual_engine.py [path/to/file ...]

With no arguments, runs over every PDF/EPUB under data/raw_ext/ and the
Downloads probes dir (if present). Reports a table and exits 0 unless BOTH
engines are junk on the same source (OCR-mandatory state).

The gate does NOT fail on disagreement alone — disagreement between two
independent parsers is information about the source, not a parse error. It
fails only when both engines are junk on the same source, meaning neither
extractor can rescue the other and OCR is the only remaining path (D-001).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.dual_engine import compare  # noqa: E402

EXT_DIR = os.path.join(ROOT, "data", "raw_ext", "generality")
DL = os.path.join(os.path.expanduser("~"), "Downloads")


def _default_targets() -> list[str]:
    targets = []
    for root in (EXT_DIR, DL):
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root)):
            sub = os.path.join(root, d)
            if not os.path.isdir(sub):
                continue
            for f in sorted(os.listdir(sub)):
                if f.lower().endswith((".pdf", ".epub")):
                    targets.append(os.path.join(sub, f))
    return targets


def main(argv: list[str]) -> int:
    targets = argv[1:] or _default_targets()
    if not targets:
        print("dual-engine gate: no PDF/EPUB targets found")
        return 0

    print(f"=== Q-07 dual-engine gate: {len(targets)} target(s) ===")
    fails = []
    for p in targets:
        if not os.path.exists(p):
            print(f"  MISSING: {p}")
            continue
        rep = compare(p)
        print(rep.summarise())
        print()
        if rep.both_junk:
            fails.append(p)

    print("=" * 78)
    if fails:
        print(f"FAIL: {len(fails)} source(s) where BOTH engines are junk — OCR mandatory:")
        for p in fails:
            print(f"  {p}")
        return 1
    print(f"PASS: {len(targets)} target(s) scanned, 0 double-junk")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
