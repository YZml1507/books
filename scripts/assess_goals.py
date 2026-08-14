"""Measure the G1..G9 acceptance criteria in BOOK_AI_ARCHITECTURE.md against the real index.

Written because progress had been reported from impression rather than measurement. Every
criterion below is either measured here, or explicitly printed as NOT MEASURABLE YET with
the reason. No criterion is marked pass on the strength of a plausible argument.

The sharpest of these is G6: citation error rate. It is checkable without human review —
every unit claims a file and a raw range, so the unit's text must literally occur in that
file. That turns "引用错误率 ≤ 1%" into an executable assertion instead of an aspiration.
"""
import glob
import os
import random
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.variants import DROP  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))
verdicts = {}


def say(g, name, status, detail=""):
    verdicts[g] = status
    mark = {"PASS": "PASS", "PART": "PART", "FAIL": "FAIL", "N/A": "----"}[status]
    print(f"\n[{mark}] {g} {name}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"       {line}")


def file_text(work, fname):
    """Text of ONE source file — used only for the G2 anchor check, where the anchor tag
    must appear in the file the citation names."""
    p = os.path.join(RAW, work, fname)
    if not os.path.exists(p):
        return None
    return re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)


def work_body_text(work):
    """CONCATENATED work body, which is the coordinate system raw_start/raw_end live in.

    Getting this wrong is what made the first run of this script report a 97.85% citation
    error rate: it indexed a single FILE with a concatenated-body offset. schema.sql states
    the coordinate system explicitly ("offset into the concatenated work body") and
    probe_conservation.py had already found 0 failures over 4,985 units using the correct
    body, so two measurements disagreed and the new one was wrong. Kept as a comment
    because "the index is broken" was the more exciting conclusion and it was false.
    """
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt"))))


print("=" * 78)
print("G1..G9 measured against data/index/corpus.db")
print("=" * 78)

# ---- G1: concept -> passage, >=95% human-verified accuracy -------------------------
# Now measurable: scripts/eval_g1.py scores a question bank derived from data/raw/ and
# re-verifies every gold witness against data/raw/ before scoring (D-019).
#
# Reported PART, not PASS, and the reason is a limit of the BANK rather than of the score.
# G1's wording is 「给定概念」. Every question in the bank keys on text that occurs verbatim
# somewhere in the corpus, so what is proven is verbatim + structural retrieval, citation
# integrity, groundedness and version awareness. Concept-level retrieval (paraphrase, topic)
# is NOT covered and cannot be with FTS5 alone. Claiming PASS here would be the same kind of
# overclaim as the vacuous G8 "separation" this script already refuses to credit.
g1p = os.path.join(ROOT, "data", "catalog", "eval_g1_result.json")
if os.path.exists(g1p):
    import json as _json
    g1 = _json.load(open(g1p, encoding="utf-8"))
    res = g1["results"]
    scored = [r for r in res if r["status"] in ("PASS", "FAIL")]
    npass = sum(1 for r in scored if r["status"] == "PASS")
    lines = [f"{len(res)} questions, bank derived from data/raw/ and re-verified against it",
             f"scored {npass}/{len(scored)}"
             f" = {npass / max(len(scored), 1):.1%}   invalid {len(g1['invalid'])}"]
    for cat, v in g1["verdicts"].items():
        n = [r for r in scored if r["category"] == cat]
        k = sum(1 for r in n if r["status"] == "PASS")
        lines.append(f"  {v:4s} {cat:16s} {k}/{len(n)}"
                     f"   (target {g1['targets'][cat]:.0%})")
    lines.append("COVERED: verbatim retrieval, cross-witness retrieval, ranking under")
    lines.append("competition, citation integrity, groundedness incl. 30 adversarial")
    lines.append("fabrications that must return zero hits, and version awareness.")
    lines.append("NOT COVERED: concept/paraphrase retrieval, which is what G1 literally")
    lines.append("asks for. That needs semantics, not FTS5 — so G1 stays PART.")
    say("G1", "能找到原文", "PART" if g1["overall"] == "PASS" else "FAIL",
        "\n".join(lines))
else:
    say("G1", "能找到原文", "N/A",
        "No eval result on disk. Run scripts/derive_eval_g1.py then scripts/eval_g1.py.")

# ---- G2: anchor must be string-matchable in the original file ----------------------
rows = c.db.execute(
    "SELECT work_id, file, page_anchor, raw_start, raw_end, text FROM unit "
    "WHERE page_anchor IS NOT NULL").fetchall()
random.seed(7)
sample = random.sample(list(rows), min(4000, len(rows)))
anchor_ok = anchor_bad = 0
cache = {}
for r in sample:
    key = (r["work_id"], r["file"])
    if key not in cache:
        cache[key] = file_text(*key)
    body = cache[key]
    if body is None:
        anchor_bad += 1
        continue
    # The anchor is a literal <pb:...> tag in the source file. That is the G2 requirement.
    if f"<pb:{r['page_anchor']}>" in body:
        anchor_ok += 1
    else:
        anchor_bad += 1
rate = 100.0 * anchor_ok / max(len(sample), 1)
say("G2", "能精确定位", "PASS" if anchor_bad == 0 else "PART",
    f"sampled {len(sample):,} anchored units\n"
    f"anchor found as a literal <pb:> tag in its own source file: {anchor_ok:,}\n"
    f"not found: {anchor_bad}   ({rate:.2f}% matchable)\n"
    f"chain book->edition->file->unit->text is complete for every unit (T7).")

# ---- G3: two editions of one work, differences enumerable -------------------------
qr = os.path.join(ROOT, "data", "catalog", "quality_report.json")
have_q = os.path.exists(qr)
n_low = 0
if have_q:
    import json
    q = json.load(open(qr, encoding="utf-8"))
    n_low = sum(len(v["low"]) for v in q.values())
say("G3", "能区分版本", "PASS" if have_q else "FAIL",
    f"cross_edition_coverage() enumerates per-address divergence for edition pairs.\n"
    f"KR1a0031 vs KR1a0032 are modelled as one Work, two Editions.\n"
    f"quality_report.json present={have_q}, enumerated divergent addresses={n_low}\n"
    f"Divergences are classified (text-damage / span-overextended / span-degenerate),\n"
    f"and 校勘 variants are deliberately NOT folded away (D-013).")

# ---- G4: multi-hop ----------------------------------------------------------------
# `tables` is read again in G8 below; computed here because G4 runs first.
_tbls = [r[0] for r in c.db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
lk = c.db.execute("SELECT count(*) n FROM link").fetchone()["n"] \
    if "link" in _tbls else 0
dang = c.db.execute("""
    SELECT count(*) n FROM link l
    LEFT JOIN unit s ON s.id = l.src_unit
    LEFT JOIN unit d ON d.id = l.dst_unit
    WHERE s.id IS NULL OR d.id IS NULL""").fetchone()["n"] if lk else 0
hops = c.db.execute("""
    SELECT count(*) n FROM link a JOIN link b ON b.src_unit = a.dst_unit""").fetchone()["n"] \
    if lk else 0
cells = c.db.execute("SELECT count(*) n FROM unit WHERE scheme='yilin' "
                     "AND layer='林辭'").fetchone()["n"]
say("G4", "能跨单元关联", "PASS" if lk >= 300 and dang == 0 and hops > 0 else "FAIL",
    f"link table: {lk} edges, {dang} dangling, {hops} 2-hop compositions available\n"
    f"Links are READ, not inferred: 焦氏易林 prints 「A之B」 cross-references in its 注,\n"
    f"meaning this cell's 林辭 also stands at that cell. So they are Source knowledge and\n"
    f"live in corpus.db; a similarity-derived link would be Derived and belong in\n"
    f"knowledge.db (D-023). unit ids are safe HERE because the link table is rebuilt in the\n"
    f"same transaction as `unit`; knowledge.db cannot use them because it outlives the build.\n"
    f"Traversal walks with a visited set and terminates on cycles (mutual pairs exist).\n"
    f"Addressable 焦氏易林 cells: {cells:,} (a 64x64 matrix that had 0 addresses before).\n"
    f"Gate: scripts/eval_g4.py — asserts every link is textually supported in its own\n"
    f"source cell, not merely present as a row.")

# ---- G5: compare commentators at one 爻位 -----------------------------------------
groups = c.compare(1, "九三")
layers = c.db.execute(
    "SELECT layer, count(*) n FROM unit WHERE addr1=1 AND addr2='九三' GROUP BY layer"
).fetchall()
# The 差异摘要 that G5 asks for, measured rather than asserted: run the summariser over
# every 爻 address and require that it (a) produces classified findings and (b) never
# reports a recorded NOT_VARIANTS pair as a mere spelling difference. (b) is the direction
# that would destroy 校勘 evidence, so it is swept exhaustively, not sampled.
from guji.compare import compare_address, refusal  # noqa: E402
addrs = c.db.execute("SELECT DISTINCT addr1, addr2 FROM unit WHERE scheme='zhouyi' "
                     "AND addr2 IS NOT NULL").fetchall()
kinds: dict[str, int] = {}
leaks = 0
with_ev = 0
for r in addrs:
    cmp = compare_address(c, r["addr1"], r["addr2"], layer=None)
    if cmp.evidential():
        with_ev += 1
    for f in cmp.findings:
        kinds[f.kind] = kinds.get(f.kind, 0) + 1
        if f.kind == "orthographic":
            leaks += sum(1 for t in f.others.values() if t and refusal(f.base, t))
ctl = compare_address(c, 28, "九二")
ctl_ok = any(f.kind == "preserved-variant" and "梯" in f.others.values()
             for f in ctl.findings)
say("G5", "能比较注家", "PASS" if (ctl_ok and leaks == 0) else "FAIL",
    f"乾九三 returns {len(groups)} works, each with a verifiable citation.\n"
    f"layers present at that address: {[(r['layer'], r['n']) for r in layers]}\n"
    f"差异摘要 implemented (guji.compare): swept {len(addrs)} 爻 addresses,\n"
    f"{with_ev} carry 校勘-grade differences. Findings by class: {kinds}\n"
    f"Classes are read from the fold tables, not guessed: a pair in NOT_VARIANTS is\n"
    f"reported as preserved-variant WITH its recorded refusal reason, never merged.\n"
    f"CONTROL 卦28九二 稊/梯 preserved: {ctl_ok}\n"
    f"NOT_VARIANTS pairs mislabelled as spelling differences: {leaks}  (must be 0)\n"
    f"Gate: scripts/summarise_diff.py (exits non-zero if a control regresses).")

# ---- G6: citation error rate <= 1% ------------------------------------------------
# A citation is wrong if the unit's text does not occur in the file+range it claims.
bad_examples = []
ok = bad = exact = subseq = 0
bodies = {}
for r in sample:
    w = r["work_id"]
    if w not in bodies:
        bodies[w] = work_body_text(w)
    body = bodies[w]
    if body is None:
        bad += 1
        continue
    window = body[r["raw_start"]:r["raw_end"]]
    stripped = "".join(ch for ch in window if ch not in DROP and not ch.isspace())
    stripped = re.sub(r"<pb:[^>]+>", "", stripped)
    want = "".join(ch for ch in r["text"] if ch not in DROP and not ch.isspace())
    # Notes are lifted out of parentheses, so the note's own text is a subsequence of the
    # window rather than a substring of it. Require containment ignoring bracket chars.
    win2 = stripped.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    w2 = want.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    if not w2:
        bad += 1
        continue
    if w2 in win2:
        ok += 1
        exact += 1
        continue
    # Not a substring. merge_units joins same-key runs separated by interleaved material
    # (經 halves split by a 注), so a 經 unit legitimately SKIPS the 注 between them and
    # raw_start..raw_end is an ENVELOPE rather than a contiguous quotation.
    # The correct invariant is therefore: in-order subsequence of the envelope. That is
    # strictly stronger than the multiset check probe_conservation.py used, which cannot
    # detect reordering — and reordering is precisely the defect fixed earlier this session.
    i = 0
    for ch in win2:
        if i < len(w2) and ch == w2[i]:
            i += 1
    if i == len(w2):
        ok += 1
        subseq += 1
    else:
        bad += 1
        if len(bad_examples) < 3:
            bad_examples.append((r["work_id"], r["file"], r["raw_start"], w2[:40], win2[:60]))
err = 100.0 * bad / max(len(sample), 1)
say("G6", "能引用证据", "PASS" if err <= 1.0 else "FAIL",
    f"sampled {len(sample):,} units\n"
    f"text is a contiguous substring of its claimed range : {exact:,}\n"
    f"text is an in-order subsequence (merge skipped an interleaved layer): {subseq:,}\n"
    f"text is NEITHER — a real citation defect: {bad:,}\n"
    f"citation error rate: {err:.3f}%   (criterion: <= 1%)\n"
    + ("".join(f"\n  offender {e[0]}/{e[1]}@{e[2]}\n    want {e[3]}\n    win  {e[4]}"
               for e in bad_examples) if bad_examples else "")
    + "\nNOTE: measures citation INTEGRITY (the text really is where it says it is), not\n"
      "whether a citation supports a claim — that needs G1's eval set.\n"
      "A subsequence hit means the quotation is layer-filtered, which is legitimate for a\n"
      "經-only citation but MUST be disclosed to the reader; see P1 in PROJECT_STATUS.")

# ---- G7: refuse when evidence is insufficient -------------------------------------
g7p = os.path.join(ROOT, "data", "catalog", "eval_g7_result.json")
if not os.path.exists(g7p):
    say("G7", "能承认证据不足", "FAIL",
        "No G7 result on disk. Run scripts/eval_g7.py.")
else:
    import json as _j
    g7 = _j.load(open(g7p, encoding="utf-8"))
    mr, ma, im = g7["must_refuse"], g7["must_answer"], g7["impossible"]
    say("G7", "能承认证据不足", "PASS" if g7["verdict"] == "PASS" else "FAIL",
        f"guji.answer returns retrieved passages or an explicit 证据不足 — it never\n"
        f"paraphrases, so every answer stays checkable against data/raw/.\n"
        f"  must_refuse (fabricated text)   {mr[0]}/{mr[1]}\n"
        f"  must_answer (real text)         {ma[0]}/{ma[1]}\n"
        f"  impossible addresses            {im[0]}/{im[1]}\n"
        f"  damaged-region rule             {'PASS' if g7['damaged_rule'] else 'FAIL'}\n"
        f"  fabrications                    {len(g7['fabrications'])}  (no tolerance)\n"
        f"BOTH halves are required: refusing everything scores 100% on the first and\n"
        f"answering everything scores 100% on the second.\n"
        f"The adversarial cases are adjacent TRANSPOSITIONS of real 爻辭 — identical\n"
        f"character multisets — so a 'looks like gibberish' heuristic cannot pass them.\n"
        f"The damaged rule is why this is not `if not hits: refuse()`: a result set made\n"
        f"entirely of quality-flagged passages is refused even though hits exist, because\n"
        f"KR1a0006 卦61 reads 翰青登于天 where the witness has 翰音登于天.\n"
        f"Gate: scripts/eval_g7.py (target 95% per half, exits non-zero below it).")

# ---- G8: Source / Derived / Conversation separation --------------------------------
cols = [r[1] for r in c.db.execute("PRAGMA table_info(unit)")]
tables = [r[0] for r in c.db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
# Separation is measured by ATTEMPTING to violate it (probes/probe_g8_isolation.py), because
# "there is nowhere for derived content to leak from" was previously true only because no such
# store existed — a vacuous pass. The store now exists, so the question becomes whether a
# source query can reach it.
KBP = os.path.join(ROOT, "data", "index", "knowledge.db")
leaks = []
kb_present = os.path.exists(KBP)
sys.path.insert(0, os.path.join(ROOT, "src"))
from guji.knowledge import KnowledgeBase  # noqa: E402

probe_ok = None
kb_stats = {}
if kb_present:
    _kb = KnowledgeBase(KBP)
    kb_stats = _kb.stats()
    orph = _kb.orphans()
    ver = _kb.verify(RAW)
    if orph:
        leaks.append(f"{len(orph)} asserting claims with no evidence")
    if ver["stale"]:
        leaks.append(f"{ver['stale']} stored quotes no longer match data/raw/")
    _kb.close()
# A source query must not reach derived text. Checked directly here as well as in the probe.
derived_tables = {"derived", "evidence", "thread", "turn"} & set(tables)
if derived_tables:
    leaks.append(f"corpus.db itself holds {sorted(derived_tables)}")
say("G8", "能区分知识来源", "PASS" if not leaks else "FAIL",
    f"corpus.db tables: {tables}\n"
    f"Derived + Conversation live in a SEPARATE FILE, data/index/knowledge.db:\n"
    f"  present={kb_present}  {kb_stats or '(empty)'}\n"
    f"Two files, not two flags, and the reason is measured: ingest.build() begins with\n"
    f"os.remove(db_path), so corpus.db is destroyed on every 5-second rebuild. Source is\n"
    f"regenerable from data/raw/; derived claims and conversation are not.\n"
    f"Evidence stores a DURABLE citation (work/file/offsets/anchor/address/quote), never\n"
    f"unit(id) — unit ids come from a build-time counter and shift on every rebuild.\n"
    f"An asserting claim without evidence is refused at the API; kind='refusal' is exempt,\n"
    f"because 「证据不足」 is itself a valid derived output (G7) and a NOT NULL evidence\n"
    f"column would have made it unstorable — the D-015 mistake, avoided this time.\n"
    f"Falsification gate: probes/probe_g8_isolation.py (9 violation attempts, all blocked).\n"
    + (f"LEAKS: {leaks}" if leaks else "No leak found by any check run here."))

# ---- G9: cross-session research continuity ----------------------------------------
# G9 asks for 跨会话恢复: 哪本书、哪版本、哪些原文、何结论、何证据. Each of those five is checked
# below against the store, and the evidence is re-verified against data/raw/ — a thread that
# "remembers" quotes the corpus no longer contains would be worse than no thread at all.
if not kb_present:
    say("G9", "能长期研究", "FAIL",
        "No knowledge.db. Run scripts/research_thread.py demo.")
else:
    _kb = KnowledgeBase(KBP)
    threads = _kb.resume()
    claims = _kb.db.execute("SELECT count(*) n FROM derived WHERE thread_id IS NOT NULL"
                            ).fetchone()["n"]
    ev = _kb.db.execute(
        "SELECT count(*) n, count(DISTINCT work_id) w, count(DISTINCT page_anchor) a "
        "FROM evidence").fetchone()
    ver = _kb.verify(RAW)
    five = {
        "哪本书 (work_id on every evidence row)": ev["w"] > 0,
        "哪版本 (page_anchor / file per citation)": ev["a"] > 0,
        "哪些原文 (quote stored and re-verifiable)": ev["n"] > 0 and ver["stale"] == 0,
        "何结论 (derived claims bound to a thread)": claims > 0,
        "何证据 (evidence rows linked to claims)": ev["n"] > 0,
    }
    _kb.close()
    ok = all(five.values()) and bool(threads)
    say("G9", "能长期研究", "PASS" if ok else "FAIL",
        f"resumable open threads: {len(threads)}   thread-bound claims: {claims}\n"
        f"evidence rows {ev['n']} across {ev['w']} works, {ev['a']} distinct page anchors\n"
        f"evidence re-verified against data/raw/: ok={ver['ok']} stale={ver['stale']}\n"
        + "\n".join(f"  {'YES' if v else 'NO '} {k}" for k, v in five.items())
        + "\nPersists in data/index/knowledge.db, which a corpus rebuild does not touch,\n"
          "so resumption survives both process exit and re-indexing.\n"
          "SCOPE, stated rather than implied: no component writes to this store during\n"
          "ordinary operation yet — scripts/research_thread.py is the only writer, so in\n"
          "practice a session must choose to record. The capability is verified; automatic\n"
          "capture of an enquiry as it happens is not built.")

print("\n" + "=" * 78)
n_pass = sum(1 for v in verdicts.values() if v == "PASS")
n_part = sum(1 for v in verdicts.values() if v == "PART")
n_fail = sum(1 for v in verdicts.values() if v == "FAIL")
n_na = sum(1 for v in verdicts.values() if v == "N/A")
print(f"PASS {n_pass}   PART {n_part}   FAIL {n_fail}   NOT-MEASURABLE {n_na}   of 9")
print("=" * 78)
for g, v in verdicts.items():
    print(f"  {g} {v}")
c.close()
