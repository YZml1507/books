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
    engine_ok_seen = False
    for p in targets:
        if not os.path.exists(p):
            print(f"  MISSING: {p}")
            continue
        rep = compare(p)
        print(rep.summarise())
        print()
        if rep.pymupdf.ok or rep.markitdown.ok:
            engine_ok_seen = True
        if rep.both_junk:
            fails.append(p)

    print("=" * 78)
    # R229x（R7 审计 #1 假闸门）：两引擎都不可用时此前照样打 PASS——
    # 一字节没比对过还标绿。现区分：
    #   * 全部目标双双引擎 error → SKIP-ENV（exit 0，但明示没真比对，
    #     要跑真闸门请先 pip install pymupdf markitdown）
    #   * 至少一引擎 ok 且无双 junk → 真 PASS
    if fails:
        print(f"FAIL: {len(fails)} source(s) where BOTH engines are junk — OCR mandatory:")
        for p in fails:
            print(f"  {p}")
        return 1
    if not engine_ok_seen:
        print("SKIP-ENV: pymupdf/markitdown 均未可用，本环境未做真实比对"
              "（pip install pymupdf markitdown 后可跑真闸门）")
        return 0
    print(f"PASS: {len(targets)} target(s) scanned, 0 double-junk")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
