"""G5 差异摘要: parallel witnesses at one address + a classified difference summary.

    python scripts/summarise_diff.py                 # run the control set (the gate)
    python scripts/summarise_diff.py 28 九二          # summarise one address
    python scripts/summarise_diff.py 1 九三 --layer 注

Exits non-zero if any control fails, so this cannot rot into a no-op — the same discipline
as check_quality.py's 卦61 control (L-03).

THE CONTROLS ARE THE POINT, and they were written before the first run. A summariser is
only useful if it can be trusted not to flatten 校勘 evidence, so the gate asserts the
hard direction: 稊/梯 and 跛/破 MUST come back as preserved-variant with a recorded reason,
and an orthographic difference MUST NOT be reported as a textual variant. A summariser
that merged those would still print something plausible — which is why plausibility is
not evidence here (GOAL §2).
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.compare import compare_address  # noqa: E402

DB = os.path.join(ROOT, "data", "index", "corpus.db")

# (卦, 爻, readings that must be reported, required class, layer, why)
#
# The layer column is not incidental. 卜/下 sits inside 朱熹's own commentary, which is a
# shared text ONLY because KR1a0031 and KR1a0032 are two editions of the same commentator —
# so that control must compare 經+注 (layer=None). Across different commentators only the
# 經 is shared. The first version of this control set asked for 卜/下 in the 經 layer and
# failed for that reason, which is the control working correctly.
CONTROLS = [
    (28, "九二", ("稊", "梯"), "preserved-variant", "經",
     "枯楊生稊 / 生梯 — refused as a fold; must stay two readings"),
    (54, "初九", ("跛", "破"), "preserved-variant", None,
     "跛能履 / 破能履 — refused as a fold; must stay two readings"),
    (1, "九三", ("下", "卜"), "divergent", None,
     "居下之上 / 居卜之上 — survives folding, almost certainly a KR1a0031 misprint, "
     "but the module must report rather than adjudicate"),
    (30, "九三", ("昃", "昊"), "preserved-variant", None,
     "日昃之離 / 日昊之離 — 昊 is a correct character elsewhere, so folding was refused"),
]


def show(c: Corpus, gua: int, yao: str, layer: str | None = "經") -> None:
    cmp = compare_address(c, gua, yao, layer=layer)
    print(f"\n{'=' * 78}\n{cmp.addr}   layer={layer or '經+注'}   "
          f"witnesses={len(cmp.witnesses)}   reference={cmp.reference}")
    print("=" * 78)
    if not cmp.witnesses:
        print("  no units at this address")
        return
    for w, t in sorted(cmp.witnesses.items()):
        print(f"\n[{w}] {cmp.citations.get(w, '')}")
        print(f"  {t[:180]}{'…' if len(t) > 180 else ''}")

    ev = cmp.evidential()
    print(f"\n--- 差异摘要 ---")
    print(f"  校勘性差异 {len(ev)} 处" + (
        f"；正字法差异 {cmp.counts().get('orthographic', 0)} 处" if cmp.counts().get("orthographic") else ""))
    if cmp.commentary:
        print("  各家注文体量: " + "  ".join(f"{w}={n}字" for w, n in
                                            sorted(cmp.commentary.items())))
    if cmp.agree:
        print("  ** 各证在此地址上无实质文本差异 **")
    for f in cmp.findings:
        print("  " + f.line())


def controls(c: Corpus) -> int:
    print("=" * 78)
    print("CONTROL SET — 校勘 variants must survive the summary, not be flattened")
    print("=" * 78)
    fails = []
    for gua, yao, chars, want_kind, layer, why in CONTROLS:
        cmp = compare_address(c, gua, yao, layer=layer)
        base, other = chars
        # Direction-agnostic: which witness happens to be the alignment reference is an
        # implementation detail, and 卜/下 is reported base=卜 because it is found on the
        # EDITION axis (KR1a0031 vs KR1a0032) rather than against the 底本.
        found = None
        for f in cmp.findings:
            readings = {f.base} | {t for t in f.others.values() if t}
            if set(chars) <= readings:
                found = f
                break
        if not found:
            present = {w: [ch for ch in chars if ch in t]
                       for w, t in cmp.witnesses.items()
                       if any(ch in t for ch in chars)}
            print(f"\n  [FAIL] 卦{gua}{yao} {base}/{other} not reported at all")
            print(f"         {why}")
            print(f"         witnesses carrying either reading: {present}")
            fails.append(f"卦{gua}{yao}:absent")
            continue
        ok = found.kind == want_kind
        print(f"\n  [{'PASS' if ok else 'FAIL'}] 卦{gua}{yao} {base}/{other} -> "
              f"{found.kind} (want {want_kind})")
        print(f"         {found.line()}")
        if not ok:
            fails.append(f"卦{gua}{yao}:kind={found.kind}")

    # Mirror obligation 1: an orthographic difference must NOT be dressed up as a variant.
    print(f"\n{'-' * 78}\n  A. orthographic differences must not be classed as 異文")
    from guji.variants import fold as _f
    bad, checked = [], 0
    addrs = [(1, "初九"), (2, "六五"), (3, "六二"), (28, "九二"), (54, "初九"),
             (30, "九三"), (32, "初六"), (49, "六二"), (56, "初六"), (63, "六四")]
    for gua, yao in addrs:
        for lay in ("經", None):
            cmp = compare_address(c, gua, yao, layer=lay)
            for f in cmp.findings:
                if f.kind != "divergent":
                    continue
                for w, t in f.others.items():
                    checked += 1
                    if t and _f(f.base) == _f(t):
                        bad.append((gua, yao, f.base, t, w))
    print(f"    checked {checked} 'divergent' readings; "
          f"{'none' if not bad else len(bad)} fold to the same string")
    for gua, yao, a, b, w in bad[:8]:
        print(f"    [FAIL] 卦{gua}{yao} {a!r}/{b!r} ({w}) folds equal but called divergent")
        fails.append(f"卦{gua}{yao}:mislabelled")

    # Mirror obligation 2: a REFUSED pair must never be reported as orthographic. This is
    # the direction that would silently destroy 校勘 evidence, so it is asserted over every
    # 爻 address in the index rather than over a sample.
    print(f"\n{'-' * 78}\n  B. no NOT_VARIANTS pair may be classed orthographic "
          f"(swept over all 爻 addresses)")
    rows = c.db.execute("SELECT DISTINCT addr1, addr2 FROM unit WHERE scheme='zhouyi' "
                        "AND addr2 IS NOT NULL ORDER BY addr1, addr2").fetchall()
    from guji.compare import refusal
    swept = leaks = 0
    for r in rows:
        cmp = compare_address(c, r["addr1"], r["addr2"], layer=None)
        for f in cmp.findings:
            if f.kind != "orthographic":
                continue
            for w, t in f.others.items():
                swept += 1
                if t and refusal(f.base, t):
                    leaks += 1
                    print(f"    [FAIL] 卦{r['addr1']}{r['addr2']} {f.base!r}/{t!r} is a "
                          f"recorded refusal but was called orthographic")
                    fails.append(f"卦{r['addr1']}{r['addr2']}:refusal-leak")
    print(f"    swept {len(rows)} addresses, {swept} orthographic readings, "
          f"{leaks} refusal leaks")

    print(f"\n{'=' * 78}")
    print("PASS — 差异摘要 preserves 校勘 evidence" if not fails else f"FAIL: {fails}")
    return 1 if fails else 0


def main() -> int:
    c = Corpus(DB)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    layer: str | None = "經"
    if "--layer" in sys.argv:
        v = sys.argv[sys.argv.index("--layer") + 1]
        # "all"/"none" mean "do not filter", i.e. compare 經+注 together. Without this the
        # string "none" reaches SQL as a layer name and silently matches nothing.
        layer = None if v.lower() in ("none", "all", "經+注") else v
    try:
        if len(args) >= 2:
            show(c, int(args[0]), args[1], layer)
            return 0
        rc = controls(c)
        show(c, 28, "九二")
        show(c, 1, "九三", layer=None)
        return rc
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
