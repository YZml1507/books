"""G7: adversarial test of 「能承认证据不足」. Pass condition >= 95%, pre-registered.

    python scripts/eval_g7.py

Reuses the G1 bank rather than inventing cases, which matters for two reasons: those
questions are already verified against data/raw/ (so "this string is absent" is a measured
fact, not an assumption), and the 30 adversarial items are adjacent TRANSPOSITIONS of real
爻辭 — character-multiset identical to genuine text. A refusal rule that keys on "looks like
gibberish" fails them, which is exactly the point.

Both halves are scored, and a system must pass both:

  must_refuse   fabricated / absent text  -> must output 证据不足
  must_answer   real text                 -> must return evidence, NOT refuse

Scoring one half alone is meaningless. Refusing everything scores 100% on the first;
answering everything scores 100% on the second. The gate requires >= 95% on each, plus zero
fabrications (a refusal that nevertheless returns text, or an answer whose text is not in the
corpus) — that last count must be exactly 0 and is not subject to the 95% tolerance.
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.answer import answer_address, answer_text  # noqa: E402
from guji.evalset import body_in, works_on_disk  # noqa: E402
from guji.variants import fold  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
BANK = os.path.join(ROOT, "data", "catalog", "eval_g1.json")
OUT = os.path.join(ROOT, "data", "catalog", "eval_g7_result.json")
TARGET = 0.95


def main() -> int:
    if not os.path.exists(BANK):
        print("no eval bank — run scripts/derive_eval_g1.py first")
        return 2
    bank = json.load(open(BANK, encoding="utf-8"))
    c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

    refuse_cases = [q for q in bank["questions"] if q["category"] == "grounded_neg"]
    answer_cases = [q for q in bank["questions"] if q["category"] == "grounded_pos"]
    # A third kind the bank does not contain: addresses that genuinely do not exist. 卦65 is
    # outside King Wen order, and 乾 has no yin lines, so 卦1·六二 cannot exist. Both must be
    # refused rather than answered with something nearby.
    impossible = [(65, "初九"), (1, "六二"), (2, "九五"), (99, None)]

    print("=" * 78)
    print(f"G7 adversarial refusal test — {len(refuse_cases)} must refuse, "
          f"{len(answer_cases)} must answer, {len(impossible)} impossible addresses")
    print("=" * 78)

    results = []
    fabrications = []

    print("\n--- half 1: fabricated text MUST be refused ---")
    ref_ok = 0
    for q in refuse_cases:
        a = answer_text(c, q["query"])
        ok = a.refused
        if ok:
            ref_ok += 1
        else:
            # Confirm against the raw corpus before calling it a fabrication: the claim is
            # that this string is absent from all 28 works.
            f = fold(q["query"])
            where = [w for w in works_on_disk(RAW)
                     if f in body_in(RAW, w, "folded_notes")
                     or f in body_in(RAW, w, "folded_jing")]
            if not where:
                fabrications.append((q["id"], q["query"], a.evidence[0].citation()
                                     if a.evidence else "?"))
            print(f"  [FAIL] {q['id']:14s} answered instead of refusing "
                  f"({len(a.evidence)} passages; present in raw: {where or 'NOWHERE'})")
        results.append({"id": q["id"], "half": "must_refuse",
                        "status": "PASS" if ok else "FAIL", "reason": a.reason})
    print(f"  refused {ref_ok}/{len(refuse_cases)} = "
          f"{ref_ok / max(len(refuse_cases), 1):.1%}")

    print("\n--- half 2: real text MUST be answered, not refused ---")
    ans_ok = 0
    for q in answer_cases:
        a = answer_text(c, q["query"])
        ok = (not a.refused) and bool(a.evidence)
        if ok:
            # An answer must actually contain what was asked for; otherwise it is a
            # different failure wearing an answer's clothes (FTS implicit AND).
            want = fold(q["query"])
            if not any(want in fold(h.text) for h in a.evidence):
                ok = False
                fabrications.append((q["id"], q["query"],
                                     "answer returned passages lacking the query text"))
        if ok:
            ans_ok += 1
        else:
            print(f"  [FAIL] {q['id']:14s} {'refused: ' + a.reason if a.refused else 'no usable evidence'}")
        results.append({"id": q["id"], "half": "must_answer",
                        "status": "PASS" if ok else "FAIL", "reason": a.reason})
    print(f"  answered {ans_ok}/{len(answer_cases)} = "
          f"{ans_ok / max(len(answer_cases), 1):.1%}")

    print("\n--- half 3: impossible addresses MUST be refused ---")
    imp_ok = 0
    for a1, a2 in impossible:
        a = answer_address(c, a1, a2)
        ok = a.refused
        imp_ok += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] 卦{a1}{'·' + a2 if a2 else ''}: "
              f"{a.reason[:70] if a.refused else str(len(a.evidence)) + ' passages returned'}")
        results.append({"id": f"IMP-{a1}-{a2}", "half": "impossible",
                        "status": "PASS" if ok else "FAIL", "reason": a.reason})

    print("\n--- damaged-region rule: a flagged-only result must refuse ---")
    # KR1a0006 卦61 上九 is the known OCR-damaged control. Query a string unique to the
    # damaged reading: an answer there would be presenting corruption as evidence.
    dmg = answer_text(c, "翰青登于天")
    dmg_ok = dmg.refused and "损坏" in dmg.reason
    print(f"  [{'PASS' if dmg_ok else 'FAIL'}] 翰青登于天 -> "
          f"{dmg.reason[:88] if dmg.refused else f'{len(dmg.evidence)} passages returned'}")
    results.append({"id": "DMG-61", "half": "damaged",
                    "status": "PASS" if dmg_ok else "FAIL", "reason": dmg.reason})
    # And the mirror: the CORRECT reading must still be answerable.
    good = answer_text(c, "翰音登于天")
    good_ok = not good.refused
    print(f"  [{'PASS' if good_ok else 'FAIL'}] 翰音登于天 (correct reading) -> "
          f"{'answered with ' + str(len(good.evidence)) + ' passages' if good_ok else good.reason}")
    results.append({"id": "DMG-61-mirror", "half": "damaged",
                    "status": "PASS" if good_ok else "FAIL", "reason": good.reason})

    r_rate = ref_ok / max(len(refuse_cases), 1)
    a_rate = ans_ok / max(len(answer_cases), 1)
    i_rate = imp_ok / max(len(impossible), 1)
    verdict = ("PASS" if r_rate >= TARGET and a_rate >= TARGET and i_rate >= TARGET
               and dmg_ok and good_ok and not fabrications else "FAIL")
    print(f"\n{'=' * 78}")
    print(f"must_refuse   {ref_ok}/{len(refuse_cases)} = {r_rate:.1%}  (target {TARGET:.0%})")
    print(f"must_answer   {ans_ok}/{len(answer_cases)} = {a_rate:.1%}  (target {TARGET:.0%})")
    print(f"impossible    {imp_ok}/{len(impossible)} = {i_rate:.1%}  (target {TARGET:.0%})")
    print(f"damaged rule  {'PASS' if dmg_ok and good_ok else 'FAIL'}  "
          f"(refuse damaged-only, still answer the sound reading)")
    print(f"FABRICATIONS  {len(fabrications)}   (must be 0, no tolerance)")
    for f in fabrications[:5]:
        print(f"   {f[0]} {f[1]!r} -> {f[2]}")
    print(f"\nG7 = {verdict}")
    print("=" * 78)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"verdict": verdict, "target": TARGET,
                   "must_refuse": [ref_ok, len(refuse_cases)],
                   "must_answer": [ans_ok, len(answer_cases)],
                   "impossible": [imp_ok, len(impossible)],
                   "damaged_rule": bool(dmg_ok and good_ok),
                   "fabrications": fabrications, "results": results},
                  fh, ensure_ascii=False, indent=1)
    print(f"-> {os.path.relpath(OUT, ROOT)}")
    c.close()
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
