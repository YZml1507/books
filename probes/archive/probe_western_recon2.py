"""READ-ONLY recon round 2: per-book depth, false-positive traps, Iliad cross-translation.

Round 1 (probe_western_recon.py) found: Plato .txt has ZERO Stephanus markers; Herodotus
has 735 line-initial `N. ` section markers; neither Iliad has any line numbering. This
round verifies each of those against html+epub (so "not in the txt" is not confused with
"not in the edition") and measures the traps bcv.py warns about.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Users\Lenovo\Desktop\projects\books")
MAN = ROOT / "data" / "catalog" / "generality_manifest.json"
MANIFEST = {d["slug"]: d for d in json.loads(MAN.read_text(encoding="utf-8"))}


def txt(slug: str) -> str:
    return (ROOT / MANIFEST[slug]["files"]["txt"]["path"]).read_text(
        encoding="utf-8", errors="replace")


def html(slug: str) -> str:
    return (ROOT / MANIFEST[slug]["files"]["html"]["path"]).read_text(
        encoding="utf-8", errors="replace")


def epub_parts(slug: str) -> list[tuple[str, str]]:
    p = ROOT / MANIFEST[slug]["files"]["epub"]["path"]
    out = []
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n.lower().endswith((".xhtml", ".html", ".htm", ".xml", ".ncx", ".opf")):
                out.append((n, z.read(n).decode("utf-8", errors="replace")))
    return out


def body(t: str) -> tuple[str, int]:
    s = re.search(r"\*\*\*\s*START OF (?:TH(?:E|IS) )?PROJECT GUTENBERG.*?\*\*\*", t)
    e = re.search(r"\*\*\*\s*END OF (?:TH(?:E|IS) )?PROJECT GUTENBERG.*?\*\*\*", t)
    b0 = s.end() if s else 0
    b1 = e.start() if e else len(t)
    return t[b0:b1], b0


def hits(pat: str, t: str, flags=re.M) -> list[re.Match]:
    return list(re.compile(pat, flags).finditer(t))


def quote(ms: list[re.Match], n: int = 5, base: int = 0, width: int = 88) -> None:
    for m in ms[:n]:
        print(f"       @{m.start()+base:>7} {m.group(0)[:width]!r}")


def head(s: str) -> None:
    print("\n" + "=" * 96 + f"\n{s}\n" + "=" * 96)


def plato() -> None:
    head("T7-c PLATO / stephanus -- does the marker exist in ANY format?")
    t = txt("plato-republic")
    b, b0 = body(t)
    for label, pat in [
        ("NNNa-e adjacent digits+letter", r"\b\d{2,3}[a-e]\b"),
        ("St. paren form (327 a)", r"\b\d{2,3}\s?[a-e]\b"),
        ("word 'Stephanus'", r"[Ss]tephanus"),
        ("word 'pagination'", r"pagination"),
        ("digit run 3+ anywhere", r"\b\d{3,4}\b"),
    ]:
        ms = hits(pat, t, 0)
        print(f"  txt  {label:<32} n={len(ms)}")
        quote(ms, 6)
    h = html("plato-republic")
    for label, pat in [
        ("NNNa-e in html", r"\b\d{2,3}[a-e]\b"),
        ("Stephanus in html", r"[Ss]tephanus"),
        ("<span class=... margin", r'class="[^"]*(?:margin|marg|pagenum|linenum)[^"]*"'),
        ("id=page/pg anchors", r'id="(?:page|pg|Page)[^"]*"'),
        ("any <sup>", r"<sup[^>]*>.{0,20}"),
    ]:
        ms = hits(pat, h, 0)
        print(f"  html {label:<32} n={len(ms)}")
        quote(ms, 5)
    tot_st = tot_sp = 0
    for name, part in epub_parts("plato-republic"):
        n_st = len(hits(r"\b\d{2,3}[a-e]\b", part, 0))
        n_sp = len(hits(r"[Ss]tephanus", part, 0))
        tot_st += n_st
        tot_sp += n_sp
    print(f"  epub parts={len(epub_parts('plato-republic'))} "
          f"NNNa-e={tot_st} 'Stephanus'={tot_sp}")
    print("  --- what addresses DO exist ---")
    bk = hits(r"^\s*BOOK\s+([IVX]+)\.?\s*$", b)
    print(f"  BOOK headings (own line) n={len(bk)}")
    quote(bk, 30, b0)
    dlg = re.search(r"^\s*THE REPUBLIC\.?\s*$", b, re.M)
    per = re.search(r"^\s*PERSONS OF THE DIALOGUE", b, re.M)
    print(f"  'THE REPUBLIC.' own line @{dlg.start()+b0 if dlg else None}  "
          f"'PERSONS OF THE DIALOGUE' @{per.start()+b0 if per else None}")
    intro_end = per.start() if per else 0
    print(f"  front matter (Jowett intro/analysis) = {intro_end} chars "
          f"= {intro_end/len(b):.1%} of body -- TRAP: it discusses every Book by name")
    fm = hits(r"^.*\bBOOK\s+[IVX]+\b.*$", b[:intro_end])
    print(f"  'BOOK n' mentions inside front matter n={len(fm)}")
    quote(fm, 6, b0)
    print("  --- dialogue speaker markers? ---")
    for pat in (r"^\s*(?:SOCRATES|GLAUCON|ADEIMANTUS|THRASYMACHUS|POLEMARCHUS)\b.*",
                r"^[A-Z][a-z]+:\s"):
        ms = hits(pat, b)
        print(f"    {pat[:40]:<42} n={len(ms)}")
        quote(ms, 3, b0)


def shakespeare() -> None:
    head("T7-d SHAKESPEARE / play-act-scene")
    t = txt("shakespeare")
    b, b0 = body(t)
    lines = b.splitlines()
    toc0 = next(i for i, l in enumerate(lines) if l.strip() == "Contents")
    toc = [l.strip() for l in lines[toc0 + 1:toc0 + 60] if l.strip()]
    print(f"  TOC at line {toc0}, {len(toc)} entries (TRAP a: second chain of titles)")
    for e in toc[:8]:
        print(f"     TOC {e!r}")
    titles = [e for e in toc if e.isupper() or e.upper() == e]
    print(f"  uppercase TOC entries n={len(titles)}")
    # body occurrences of each TOC title, on its own line
    print("  --- each title: how many own-line occurrences in body? ---")
    multi = 0
    for e in toc[:44]:
        ms = hits(rf"^\s*{re.escape(e)}\s*$", b)
        if len(ms) != 2:
            multi += 1
        if len(ms) != 2 or e in ("THE SONNETS", "CYMBELINE"):
            print(f"     n={len(ms)} {e!r} @{[m.start()+b0 for m in ms][:4]}")
    print(f"  titles whose own-line count != 2 : {multi}")
    print("  --- ACT / SCENE forms ---")
    act = hits(r"^\s*ACT\s+([IVXL]+)\s*$", b)
    act_ex = hits(r"^\s*ACT\s+[IVXL]+\..*$", b)
    sc = hits(r"^\s*SCENE\s+([IVXL]+)\.?(.*)$", b)
    print(f"  'ACT n' alone       n={len(act)}"); quote(act, 4, b0)
    print(f"  'ACT n. rest'       n={len(act_ex)}"); quote(act_ex, 6, b0)
    print(f"  'SCENE n. rest'     n={len(sc)}"); quote(sc, 4, b0)
    print("  --- TRAP: ACT/SCENE mentioned inside dialogue or stage directions ---")
    for pat in (r"^.{1,40}\bACT\s+[IVXL]+\b.{5,}$", r"^\s+SCENE\b.*",
                r"^.*\bACT\b.*\bSCENE\b.*$"):
        ms = hits(pat, b)
        print(f"    {pat[:44]:<46} n={len(ms)}")
        quote(ms, 4, b0)
    print("  --- TRAP: works with NO act/scene (poems) ---")
    for w in ("THE SONNETS", "VENUS AND ADONIS", "THE RAPE OF LUCRECE",
              "A LOVER’S COMPLAINT", "THE PASSIONATE PILGRIM", "THE PHOENIX AND THE TURTLE"):
        ms = hits(rf"^\s*{re.escape(w)}\s*$", b)
        print(f"    {w:<30} own-line occurrences={len(ms)} @{[m.start()+b0 for m in ms]}")
    son = hits(r"^\s{0,6}(\d{1,3})\s*$", b)
    print(f"  bare-number lines (sonnet numbers) n={len(son)}")
    quote(son, 6, b0)
    print("  --- per-play act/scene consistency (first 6 plays after TOC) ---")
    tpos = []
    for e in toc[:44]:
        ms = hits(rf"^\s*{re.escape(e)}\s*$", b)
        if len(ms) >= 2:
            tpos.append((ms[-1].start(), e))
    tpos.sort()
    for i, (pos, name) in enumerate(tpos[:8]):
        end = tpos[i + 1][0] if i + 1 < len(tpos) else len(b)
        seg = b[pos:end]
        a = [m.group(1) for m in hits(r"^\s*ACT\s+([IVXL]+)", seg)]
        s = [m.group(1) for m in hits(r"^\s*SCENE\s+([IVXL]+)", seg)]
        print(f"    {name[:38]:<40} chars={end-pos:>7} acts={a} n_scenes={len(s)}")


def euclid() -> None:
    head("T7-e EUCLID / book-proposition -- NO .txt, verify what exists")
    d = MANIFEST["euclid-elements"]
    print(f"  manifest formats: {sorted(d['files'])}   (txt absent: {'txt' not in d['files']})")
    for k, v in d["files"].items():
        p = ROOT / v["path"]
        print(f"    {k:<5} exists={p.exists()} bytes={p.stat().st_size if p.exists() else 0} "
              f"path={p}")
    h = html("euclid-elements")
    print(f"  html chars={len(h)}")
    print(f"  <img> n={len(hits(r'<img[^>]*>', h, 0))}  "
          f"<svg n={len(hits(r'<svg', h, 0))}  "
          f"<table n={len(hits(r'<table', h, 0))}")
    imgs = hits(r'<img[^>]*src="([^"]+)"[^>]*>', h, 0)
    quote(imgs, 4)
    txtonly = re.sub(r"<[^>]+>", " ", h)
    txtonly = re.sub(r"&[a-zA-Z#0-9]+;", " ", txtonly)
    print(f"  html stripped-of-tags chars={len(txtonly)}")
    print("  --- proposition / book markers in RAW HTML ---")
    for label, pat in [
        ("PROP. ...", r"PROP\.?[^<\n]{0,40}"),
        ("PROPOSITION", r"PROPOSITION[^<\n]{0,40}"),
        ("BOOK I..VI heading", r"BOOK\s+[IVX]+[^<\n]{0,40}"),
        ("Def./DEFINITION", r"DEF(?:INITION)?[SNIT]*\.?[^<\n]{0,30}"),
        ("class=... prop", r'class="[^"]{0,30}"'),
        ("id= anchors", r'id="([^"]+)"'),
        ("Q.E.D.", r"Q\.\s?E\.\s?D\."),
        ("Cor. (corollary)", r"\bCor\.[^<\n]{0,30}"),
    ]:
        ms = hits(pat, h, 0)
        print(f"    RAWHTML {label:<24} n={len(ms)}")
        quote(ms, 5)
    print("  --- proposition markers in TAG-STRIPPED text ---")
    for label, pat in [
        ("PROP. n.--Problem/Theorem", r"PROP\.\s*[IVXLC]+\.?\s*[—\-–]*\s*(?:Problem|Theorem)?"),
        ("PROP. bare", r"PROP\.\s*[IVXLC0-9]+"),
        ("BOOK n", r"BOOK\s+[IVX]+"),
    ]:
        ms = hits(pat, txtonly, 0)
        print(f"    STRIP {label:<32} n={len(ms)}")
        quote(ms, 6)
    print("  --- epub parts ---")
    parts = epub_parts("euclid-elements")
    for name, part in parts:
        np = len(hits(r"PROP\.\s*[IVXLC0-9]+", part, 0))
        print(f"    {name:<44} chars={len(part):>8} PROP.n={np}")
    p = ROOT / d["files"]["epub"]["path"]
    with zipfile.ZipFile(p) as z:
        nonhtml = [n for n in z.namelist()
                   if not n.lower().endswith((".xhtml", ".html", ".xml", ".ncx", ".opf"))]
    print(f"    epub non-markup entries n={len(nonhtml)}: {nonhtml[:12]}")


def darwin() -> None:
    head("T7-f DARWIN / chapter only?")
    t = txt("darwin-origin")
    b, b0 = body(t)
    ch = hits(r"^\s*CHAPTER\s+([IVXL]+|\d+)\.?\s*(.*)$", b)
    print(f"  CHAPTER lines n={len(ch)}  (TRAP: TOC chain + body chain)")
    for m in ch:
        print(f"     @{m.start()+b0:>7} {m.group(0)[:76]!r}")
    print("  --- numbering style inconsistency check ---")
    styles = {}
    for m in ch:
        k = "roman" if m.group(1).isalpha() else "arabic"
        styles[k] = styles.get(k, 0) + 1
    print(f"     {styles}")
    print("  --- any finer address? ---")
    for label, pat in [
        ("line-init 'N.' prose", r"^\s{0,4}\d{1,3}\.\s+[A-Z]"),
        ("§ section sign", r"§"),
        ("[Page n]", r"\[Page[^\]]*\]"),
        ("(p. n)", r"\(p\.\s*\d+\)"),
        ("footnote *", r"^\s*\*"),
        ("ALL-CAPS run-in heads", r"^[A-Z][A-Z ,\-—]{8,60}\.?$"),
    ]:
        ms = hits(pat, b)
        print(f"    {label:<26} n={len(ms)}")
        quote(ms, 4, b0)


def herodotus() -> None:
    head("T7-f HERODOTUS / book-section -- round 1 found 735 'N. ' markers, verify")
    t = txt("herodotus")
    b, b0 = body(t)
    bk = hits(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b)
    print(f"  BOOK headings n={len(bk)}")
    for m in bk:
        print(f"     @{m.start()+b0:>7} {m.group(0)[:80]!r}")
    print("  --- section markers, verbatim with raw offsets ---")
    sec = hits(r"^(\d{1,3})\.\s+(\S.{0,70})", b)
    print(f"  line-initial 'N. text' n={len(sec)}")
    quote(sec, 8, b0)
    # per-book distribution
    print("  --- per book: count, min, max, monotonicity, gaps ---")
    bounds = [m.start() for m in bk] + [len(b)]
    for i, m in enumerate(bk):
        seg_lo, seg_hi = bounds[i], bounds[i + 1]
        nums = [int(x.group(1)) for x in sec if seg_lo <= x.start() < seg_hi]
        if not nums:
            print(f"     {m.group(0)[:34]!r}: no sections")
            continue
        asc = all(y > x for x, y in zip(nums, nums[1:]))
        present = set(nums)
        missing = [n for n in range(1, max(nums) + 1) if n not in present]
        dups = len(nums) - len(present)
        print(f"     BOOK {m.group(1):<4} n={len(nums):>4} min={min(nums)} max={max(nums)} "
              f"strictly_ascending={asc} dups={dups} missing={len(missing)} "
              f"first_missing={missing[:12]}")
    pre = [x for x in sec if x.start() < bk[0].start()]
    print(f"  TRAP: 'N. ' markers BEFORE book I (preface/TOC) n={len(pre)}")
    quote(pre, 6, b0)
    print("  --- other traps ---")
    for label, pat in [
        ("{greek transliteration}", r"\{[^}]{0,50}\}"),
        ("footnote markers", r"^\s*\d{1,3}\s*$"),
        ("NOTES/APPENDIX heads", r"^\s*(NOTES?|APPENDIX|INDEX|CONTENTS)\b.*"),
        ("running head 'HERODOTUS'", r"^\s*HERODOTUS.*"),
        ("'N.' followed by lowercase", r"^\d{1,3}\.\s+[a-z]"),
        ("date-like '1890.'", r"^\d{4}\.\s"),
    ]:
        ms = hits(pat, b)
        print(f"    {label:<28} n={len(ms)}")
        quote(ms, 4, b0)


def iliad() -> None:
    head("T7-g ILIAD PAIR / book-line -- do line numbers exist at all?")
    data = {}
    for slug in ("homer-iliad-but", "homer-iliad-pope"):
        t = txt(slug)
        b, b0 = body(t)
        print(f"\n  --- {slug}  body_chars={len(b)} ---")
        for label, pat in [
            ("right-margin int (2+ sp)", r"\S[ \t]{2,}\d{1,4}[ \t]*$"),
            ("bare int line", r"^[ \t]{0,10}\d{1,4}[ \t]*$"),
            ("(NN) parenthetical int", r"\(\d{1,4}\)"),
            ("line NN / l. NN", r"\b(?:line|l\.)\s*\d{1,4}\b"),
            ("any digit at EOL", r"\d[ \t]*$"),
            ("'ARGUMENT'", r"^\s*ARGUMENT\b.*"),
            ("footnote ref [N]", r"\[\d{1,3}\]"),
            ("BOOK heading own line", r"^\s*BOOK\s+([IVXL]+)\.?\s*$"),
        ]:
            ms = hits(pat, b)
            print(f"    {label:<28} n={len(ms)}")
            quote(ms, 4, b0)
        h = html(slug)
        for label, pat in [("html bare int in tag", r">\s*\d{1,4}\s*<"),
                           ("html class linenum", r'class="[^"]*(?:line|marg|num)[^"]*"')]:
            ms = hits(pat, h, 0)
            print(f"    HTML {label:<23} n={len(ms)}")
            quote(ms, 4)
        bk = hits(r"^\s*BOOK\s+([IVXL]+)\.?\s*$", b)
        # last occurrence of each numeral = body heading (first = TOC)
        seen: dict[str, list[int]] = {}
        for m in bk:
            seen.setdefault(m.group(1), []).append(m.start())
        print(f"    distinct BOOK numerals={len(seen)} "
              f"occurrences_per_numeral={sorted({len(v) for v in seen.values()})}")
        starts = sorted(v[-1] for v in seen.values())
        data[slug] = (b, b0, seen, starts)
    print("\n  --- cross-translation: is book N the same content? ---")
    for slug in data:
        b, b0, seen, starts = data[slug]
        print(f"\n   {slug}")
        for numeral in ("I", "II", "IX", "XXII", "XXIV"):
            if numeral not in seen:
                print(f"     BOOK {numeral}: absent")
                continue
            pos = seen[numeral][-1]
            nxt = min((s for s in starts if s > pos), default=len(b))
            seg = b[pos:nxt]
            after = re.sub(r"\s+", " ", seg[:520]).strip()
            print(f"     BOOK {numeral:<5} @{pos+b0:>8} chars={nxt-pos:>7}")
            print(f"        {after[:300]!r}")
    print("\n  --- length ratio per book (alignment sanity) ---")
    bt, _, st, _ = data["homer-iliad-but"]
    bp, _, sp, _ = data["homer-iliad-pope"]
    allst = sorted(v[-1] for v in st.values())
    allsp = sorted(v[-1] for v in sp.values())
    for numeral in ("I", "II", "III", "IX", "XVI", "XXII", "XXIV"):
        if numeral not in st or numeral not in sp:
            continue
        p1 = st[numeral][-1]
        e1 = min((s for s in allst if s > p1), default=len(bt))
        p2 = sp[numeral][-1]
        e2 = min((s for s in allsp if s > p2), default=len(bp))
        print(f"    BOOK {numeral:<5} butler={e1-p1:>7} pope={e2-p2:>7} "
              f"ratio={(e2-p2)/(e1-p1):.2f}")


def pass3a() -> None:
    head("PASS 3a  SHAKESPEARE: why do acts appear twice per play?")
    t = txt("shakespeare")
    b, b0 = body(t)
    print("  RAW DUMP body[98900:101750] (region of the doubled ACT run)")
    print(repr(b[98900:101750]))
    print("\n  --- 'Contents' lines inside the body (per-play contents blocks) ---")
    c = hits(r"^\s*Contents\s*$", b)
    print(f"  own-line 'Contents' n={len(c)}")
    quote(c, 8, b0)
    print("\n  --- KING HENRY THE EIGHTH triple occurrence context ---")
    for off in (1983190, 1983910):
        i = off - b0
        print(f"   @{off}: {b[i-200:i+260]!r}")
    print("\n  --- scene numbering resets per act? (ALL'S WELL) ---")
    st = hits(r"^\s*ALL’S WELL THAT ENDS WELL\s*$", b)[-1].start()
    en = hits(r"^\s*THE TRAGEDY OF ANTONY AND CLEOPATRA\s*$", b)[-1].start()
    seg = b[st:en]
    for m in hits(r"^\s*(ACT\s+[IVXL]+|SCENE\s+[IVXL]+)\b(.{0,44})", seg):
        print(f"     @{m.start()+st+b0:>8} {m.group(0).strip()[:66]!r}")


def pass3b() -> None:
    head("PASS 3b  HERODOTUS: notes regions and the 27 absent section numbers")
    t = txt("herodotus")
    b, b0 = body(t)
    nb = hits(r"^\s*NOTES TO (?:PREFACE|BOOK [IVX]+)\s*$", b)
    print(f"  NOTES blocks n={len(nb)}")
    quote(nb, 8, b0)
    print("  RAW DUMP first 900 chars of 'NOTES TO BOOK I'")
    n1 = nb[1].start()
    print(repr(b[n1:n1 + 900]))
    sec = hits(r"^(\d{1,3})\.\s+(\S.{0,60})", b)
    bk = hits(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b)
    print("\n  --- are any section markers inside a NOTES block? ---")
    note_spans = []
    for m in nb:
        nxt = min([x.start() for x in bk if x.start() > m.start()] +
                  [len(b)])
        note_spans.append((m.start(), nxt, m.group(0).strip()))
        print(f"     {m.group(0).strip():<20} span=[{m.start()+b0},{nxt+b0}) "
              f"chars={nxt-m.start()}")
    for lo, hi, name in note_spans:
        inside = [x for x in sec if lo <= x.start() < hi]
        print(f"     {name:<20} line-init 'N.' markers inside = {len(inside)}")
        quote(inside, 3, b0)
    print("\n  --- how do the 27 absent numbers appear? (book I: 15, 29, 44) ---")
    for n in (15, 29, 44, 95):
        for m in hits(rf"(?<!\d)\b{n}\.\s", b[:270843 - b0]):
            i = m.start()
            frag = b[max(0, i - 90):i + 90].replace("\n", "\\n")
            print(f"     want {n}. -> @{i+b0:>7} {frag!r}")
            break
    print("\n  --- verbatim: two consecutive sections at a book boundary ---")
    i = bk[1].start()
    print(repr(b[i - 260:i + 620]))


def pass3c() -> None:
    head("PASS 3c  EUCLID: per-book proposition counts, raw marker shape")
    h = html("euclid-elements")
    print("  RAW DUMP html around first PROP marker")
    m = re.search(r"PROP\.", h)
    print(repr(h[m.start() - 700:m.start() + 700]))
    strip = re.sub(r"<[^>]+>", " ", h)
    strip = re.sub(r"&[a-zA-Z#0-9]+;", " ", strip)
    bk = list(re.finditer(r"BOOK\s+([IVX]+)\.", strip))
    print(f"\n  BOOK markers in stripped text n={len(bk)}")
    for x in bk:
        print(f"     @{x.start():>8} {strip[x.start():x.start()+70].split()!r}")
    props = list(re.finditer(r"PROP\.\s*([IVXLC]+)\.?\s*([—\-–]{0,2})\s*(\w{0,9})", strip))
    print(f"\n  PROP markers n={len(props)}")
    for x in props[:8]:
        print(f"     @{x.start():>8} {x.group(0)!r}")
    bounds = [x.start() for x in bk] + [len(strip)]
    for i, x in enumerate(bk):
        seg = [p for p in props if x.start() <= p.start() < bounds[i + 1]]
        kinds: dict[str, int] = {}
        for p in seg:
            kinds[p.group(3)[:9] or "?"] = kinds.get(p.group(3)[:9] or "?", 0) + 1
        print(f"     BOOK {x.group(1):<4} props={len(seg):>4} kinds={kinds}")
    print("\n  --- other addressable unit types ---")
    for label, pat in [("DEFINITIONS heading", r"DEFINITIONS?\."),
                       ("Def. n.", r"Def\.\s*[ivxlcIVXLC0-9]+"),
                       ("Cor.", r"Cor\.\s*[0-9ivx]*"),
                       ("Exercises", r"Exercises?\."),
                       ("AXIOMS/POSTULATES", r"(?:AXIOMS|POSTULATES)"),
                       ("Q.E.D./Q.E.F.", r"Q\.\s*E\.\s*[DF]\."),
                       ("PROP. arabic", r"PROP\.\s*\d+")]:
        ms = list(re.finditer(pat, strip))
        print(f"    {label:<22} n={len(ms)}")
        for x in ms[:3]:
            print(f"       @{x.start():>8} {strip[x.start():x.start()+56]!r}")


def pass3d() -> None:
    head("PASS 3d  PLATO front matter size + trap mentions; ILIAD prose vs verse")
    t = txt("plato-republic")
    b, b0 = body(t)
    d_start = hits(r"^\s*BOOK\s+I\.\s*$", b)[-1].start()
    print(f"  dialogue starts (last 'BOOK I.') at body idx {d_start} = raw @{d_start+b0}")
    print(f"  body chars={len(b)}  front matter={d_start} = {d_start/len(b):.1%}")
    print(f"  dialogue chars={len(b)-d_start} = {(len(b)-d_start)/len(b):.1%}")
    print("  TRAP: 'Book n'/'in the Republic' mentions inside the Jowett analysis")
    for pat in (r"\bBook\s+[IVX]+\b", r"\bbook\s+[ivx]+\b", r"^\s*ANALYSIS", r"\bStephanus\b"):
        ms = hits(pat, b[:d_start], re.M)
        print(f"    {pat:<26} n={len(ms)}")
        quote(ms, 4, b0)
    print("  RAW DUMP dialogue opening (Plato) body[d_start:d_start+700]")
    print(repr(b[d_start:d_start + 700]))
    head("ILIAD: prose vs verse line geometry, and Pope book XXIV boundary")
    for slug in ("homer-iliad-but", "homer-iliad-pope"):
        bb, bo = body(txt(slug))
        bk = hits(r"^\s*BOOK\s+([IVXL]+)\.?\s*$", bb)
        start = bk[-1].start()
        seg = bb[start:start + 4000]
        ls = [l for l in seg.splitlines() if l.strip()]
        avg = sum(len(l) for l in ls) / len(ls)
        cap = sum(1 for l in ls if l.strip()[:1].isupper()) / len(ls)
        print(f"  {slug}: sample lines={len(ls)} avg_len={avg:.1f} "
              f"frac_line_starts_uppercase={cap:.2f}")
        print(f"    first 6 lines of BOOK XXIV: {ls[:6]!r}")
        tail = bb[bk[-1].start():]
        print(f"    chars after last BOOK heading = {len(tail)}")
        for pat in (r"^\s*(?:CONCLUDING|NOTES|INDEX|APPENDIX|THE END)\b.*",
                    r"^\s*BOOK\s+[IVXL]+\b.*"):
            ms = hits(pat, tail)
            print(f"      {pat[:38]:<40} n={len(ms)}")
            quote(ms, 5, bk[-1].start() + bo)
    print("\n  --- landmark alignment inside BOOK I (no line numbers, so use content) ---")
    for slug, marks in (("homer-iliad-but",
                         ["Chryses", "Calchas", "Thetis", "Olympus", "Vulcan|Hephaestus"]),
                        ("homer-iliad-pope",
                         ["Chryses", "Calchas", "Thetis", "Olympus", "Vulcan|Hephaestus"])):
        bb, bo = body(txt(slug))
        bk = hits(r"^\s*BOOK\s+([IVXL]+)\.?\s*$", bb)
        pos = {m.group(1): m.start() for m in bk}
        s = pos["I"] if bk[0].group(1) != "I" else [m.start() for m in bk
                                                   if m.group(1) == "I"][-1]
        e = min([m.start() for m in bk if m.start() > s] + [len(bb)])
        seg = bb[s:e]
        print(f"   {slug} BOOK I chars={len(seg)}")
        for w in marks:
            m = re.search(w, seg)
            print(f"     {w:<20} first@ {m.start() if m else None} "
                  f"= {(m.start()/len(seg)) if m else -1:.3f} of book")


def pass3e() -> None:
    head("PASS 3e-1  HERODOTUS: the 27 absent section numbers")
    t = txt("herodotus")
    b, b0 = body(t)
    sec = hits(r"^(\d{1,3})\.\s+(\S.{0,50})", b)
    bk = hits(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b)
    bounds = [m.start() for m in bk] + [len(b)]
    nums = [(int(x.group(1)), x.start()) for x in sec
            if bounds[0] <= x.start() < bounds[1]]
    have = {n for n, _ in nums}
    for want in (15, 29, 44, 95):
        prev = max((p for n, p in nums if n == want - 1), default=None)
        nxt = min((p for n, p in nums if n == want + 1), default=None)
        print(f"\n   section {want} absent; span between {want-1}@{prev} and "
              f"{want+1}@{nxt} = {None if not (prev and nxt) else nxt-prev} chars")
        if prev and nxt:
            seg = b[prev:nxt]
            m = re.search(rf"(?<!\d){want}\.", seg)
            print(f"     literal '{want}.' inside that span at rel {m.start() if m else None}")
            if m:
                print(f"     {seg[max(0,m.start()-160):m.start()+140]!r}")
            else:
                print(f"     TAIL {seg[-300:]!r}")
    print(f"\n   book I numbers present={len(have)} of max={max(have)}")

    head("PASS 3e-2  EUCLID: per-character small-caps markup shatters words")
    h = html("euclid-elements")
    print(f"  <span class=\"small-caps\"> n={len(hits(r'class=.small-caps.', h, 0))}")
    print(f"  class=\"cmcsc-10\" (caps/smallcaps font) n={len(hits(r'cmcsc-10', h, 0))}")
    print(f"  class=\"cmmi-10\" (math italic) n={len(hits(r'cmmi-10', h, 0))}")
    print(f"  class=\"cmr-\" (roman) n={len(hits(r'cmr-\d', h, 0))}")
    strip = re.sub(r"<[^>]+>", "", h)          # NO space substitution
    strip = re.sub(r"&#x[0-9A-Fa-f]+;|&[a-z]+;", "", strip)
    print("  --- with tags removed and NO space inserted, do words rejoin? ---")
    for pat in (r"PROP\.\s*[IVXLC]+\.?[—\-–]*\w{0,10}", r"DEFINITIONS?\.",
                r"Q\.E\.D\.", r"BOOK\s+[IVX]+\."):
        ms = hits(pat, strip, 0)
        print(f"    {pat[:34]:<36} n={len(ms)}")
        for x in ms[:6]:
            print(f"       @{x.start():>8} {strip[x.start():x.start()+46]!r}")
    print("\n  --- sample of body prose after tag removal (is it readable?) ---")
    i = strip.find("PROP.")
    print(repr(strip[i:i + 700]))
    print("\n  --- proposition numbering per book, sequential? ---")
    props = list(re.finditer(r"PROP\.\s*([IVXLC]+)\.?", strip))
    bkm = list(re.finditer(r"BOOK\s+([IVX]+)\.", strip))
    bb = [m.start() for m in bkm] + [len(strip)]
    rom = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

    def rv(s: str) -> int:
        tot = prev = 0
        for c in reversed(s.upper()):
            v = rom.get(c, 0)
            tot += -v if v < prev else v
            prev = max(prev, v)
        return tot
    for i2, m in enumerate(bkm):
        seg = [rv(p.group(1)) for p in props if m.start() <= p.start() < bb[i2 + 1]]
        if not seg:
            continue
        asc = all(y > x for x, y in zip(seg, seg[1:]))
        print(f"    BOOK {m.group(1):<4} n={len(seg):>3} first={seg[0]} last={seg[-1]} "
              f"strictly_ascending={asc} missing="
              f"{[k for k in range(1, seg[-1]+1) if k not in set(seg)]}")

    head("PASS 3e-3  ILIAD: alignment inside book I, skipping heading/ARGUMENT")
    for slug, skip in (("homer-iliad-but", 0), ("homer-iliad-pope", 1)):
        bb2, bo = body(txt(slug))
        bk2 = hits(r"^\s*BOOK\s+([IVXL]+)\.?\s*$", bb2)
        pos = [m.start() for m in bk2 if m.group(1) == "I"][-1]
        end = min([m.start() for m in bk2 if m.start() > pos] + [len(bb2)])
        seg = bb2[pos:end]
        if skip:
            a = re.search(r"^\s*ARGUMENT\.", seg, re.M)
            # poem starts after the argument paragraph block
            poem = re.search(r"\n\n", seg[a.end():])
            body_start = a.end() + poem.end() if poem else 0
            # skip whole argument: find first verse-looking run
            mm = list(re.finditer(r"\n\n", seg))
            body_start = mm[3].end() if len(mm) > 3 else body_start
        else:
            mm = list(re.finditer(r"\n\n", seg))
            body_start = mm[0].end() if mm else 0
        poemseg = seg[body_start:]
        print(f"\n   {slug} BOOK I: total={len(seg)} poem_start_rel={body_start} "
              f"poem_chars={len(poemseg)}")
        print(f"     opening: {re.sub(r'[ ]+', ' ', poemseg[:230])!r}")
        for w in ("Chryses", "Calchas", "Chalcas", "Thersites", "Briseis|Briseïs",
                  "Thetis", "Vulcan|Hephaestus", "nectar"):
            m = re.search(w, poemseg)
            f = m.start() / len(poemseg) if m else -1
            print(f"     {w:<20} @{m.start() if m else None} = {f:.3f}")
        nl = [l for l in poemseg.splitlines() if l.strip()]
        print(f"     text lines={len(nl)} avg={sum(map(len, nl))/len(nl):.1f}")

    head("PASS 3e-4  SHAKESPEARE: unit inventory")
    b3, b03 = body(txt("shakespeare"))
    print(f"  own-line 'Contents' n={len(hits(r'^\s*Contents\s*$', b3))} "
          f"(1 global + per-play)")
    print(f"  'Dramatis Person' n={len(hits(r'Dramatis Person', b3, 0))}")
    print(f"  title-case 'Scene N.' (contents only) "
          f"n={len(hits(r'^\s*Scene\s+[IVXL]+\.', b3))}")
    print(f"  UPPER 'SCENE N.' (body only) "
          f"n={len(hits(r'^\s*SCENE\s+[IVXL]+\.', b3))}")
    print(f"  'SCENE:' dramatis line n={len(hits(r'^\s*SCENE:', b3))}")
    for w in ("Prologue", "Epilogue", "INDUCTION", "Induction", "Chorus", "THE END"):
        print(f"  own-line {w!r} n={len(hits(rf'^\s*{w}\.?\s*$', b3))}")


def pass3f() -> None:
    head("PASS 3f-1  HERODOTUS: marker form incl. comma; footnote FP risk")
    b, b0 = body(txt("herodotus"))
    for label, pat in [
        ("^(N). text  (period only)", r"^(\d{1,3})\.\s+\S"),
        ("^(N), text  (comma only)", r"^(\d{1,3}),\s+\S"),
        ("^(N)[.,] text (both)", r"^(\d{1,3})[.,]\s+\S"),
        ("^(N) text  (NO punctuation) = FP risk", r"^(\d{1,3})\s+[a-zA-Z]"),
        ("inline ' N ' footnote refs", r"(?<=[.,;:]) \d{1,3} (?=[A-Za-z])"),
    ]:
        ms = hits(pat, b)
        print(f"    {label:<42} n={len(ms)}")
        quote(ms, 4, b0)
    bk = hits(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b)
    bounds = [m.start() for m in bk] + [len(b)]
    sec = hits(r"^(\d{1,3})[.,]\s+\S", b)
    print("\n  --- per book with BOTH punctuation forms accepted ---")
    for i, m in enumerate(bk):
        nums = [int(x.group(1)) for x in sec if bounds[i] <= x.start() < bounds[i + 1]]
        miss = [n for n in range(1, max(nums) + 1) if n not in set(nums)]
        print(f"    BOOK {m.group(1):<4} n={len(nums):>4} max={max(nums)} "
              f"asc={all(y > x for x, y in zip(nums, nums[1:]))} missing={miss}")

    head("PASS 3f-2  ILIAD: clean landmark comparison inside BOOK I")
    res = {}
    for slug in ("homer-iliad-but", "homer-iliad-pope"):
        bb, bo = body(txt(slug))
        bk2 = hits(r"^\s*BOOK\s+([IVXL]+)\.?\s*$", bb)
        s = [m.start() for m in bk2 if m.group(1) == "I"][-1]
        e = min([m.start() for m in bk2 if m.start() > s] + [len(bb)])
        seg = bb[s:e]
        if slug.endswith("pope"):
            k = re.search(r"Achilles’ wrath|Achilles' wrath|ACHILLES’ wrath", seg)
            start = k.start() if k else 0
        else:
            k = re.search(r"Sing, O goddess", seg)
            start = k.start() if k else 0
        poem = seg[start:]
        print(f"\n   {slug}: book_I_total={len(seg)} poem_start_rel={start} "
              f"poem_chars={len(poem)}")
        print(f"     first 160: {re.sub(r'[ ]+',' ',poem[:160])!r}")
        print(f"     last  160: {re.sub(r'[ ]+',' ',poem[-160:])!r}")
        marks = ["Chryses", "Calchas|Chalcas", "Briseis|Briseïs", "Minerva|Athene",
                 "Nestor", "Thetis", "Vulcan|Hephaestus", "nectar", "Juno|Hera"]
        got = {}
        for w in marks:
            m2 = re.search(w, poem)
            got[w] = m2.start() / len(poem) if m2 else None
        res[slug] = (got, len(poem))
        for w in marks:
            v = got[w]
            print(f"     {w:<20} {'None' if v is None else f'{v:.3f}'}")
    print("\n   --- |delta| in relative position between the two translations ---")
    a, la = res["homer-iliad-but"]
    c, lc = res["homer-iliad-pope"]
    ds = []
    for w in a:
        if a[w] is not None and c[w] is not None:
            d = abs(a[w] - c[w])
            ds.append(d)
            print(f"     {w:<20} butler={a[w]:.3f} pope={c[w]:.3f} delta={d:.3f}")
    print(f"     mean |delta| = {sum(ds)/len(ds):.3f} over {len(ds)} landmarks")
    print(f"     book I poem chars: butler={la} pope={lc} ratio={lc/la:.2f}")

    head("PASS 3f-3  SHAKESPEARE: per-work act/scene inventory (all works)")
    b3, b03 = body(txt("shakespeare"))
    lines = b3.splitlines()
    toc0 = next(i for i, l in enumerate(lines) if l.strip() == "Contents")
    toc = [l.strip() for l in lines[toc0 + 1:toc0 + 60] if l.strip()]
    starts = []
    for e in toc:
        ms = hits(rf"^\s*{re.escape(e)}\s*$", b3)
        if len(ms) >= 2:
            starts.append((ms[1].start(), e))
    starts.sort()
    print(f"  works located in body: {len(starts)} of {len(toc)} TOC entries")
    tot_sc = 0
    for i, (p, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(b3)
        seg = b3[p:end]
        # body headings only: uppercase SCENE
        acts = [m.group(1) for m in hits(r"^\s*ACT\s+([IVXL]+)\b", seg)]
        body_sc = hits(r"^\s*SCENE\s+([IVXL]+)\.", seg)
        toc_sc = hits(r"^\s*Scene\s+[IVXL]+\.", seg)
        tot_sc += len(body_sc)
        print(f"    {name[:40]:<42} chars={end-p:>7} ACTlines={len(acts):>2} "
              f"SCENE={len(body_sc):>2} Scene(toc)={len(toc_sc):>2}")
    print(f"  total body SCENE headings = {tot_sc}")


def pass3g() -> None:
    head("PASS 3g  SHAKESPEARE anomalies: Henry VI pt1/pt2, Richard II, Pericles")
    b, b0 = body(txt("shakespeare"))
    for title in ("THE FIRST PART OF HENRY THE SIXTH", "KING RICHARD THE SECOND",
                  "PERICLES, PRINCE OF TYRE", "MUCH ADO ABOUT NOTHING"):
        ms = hits(rf"^\s*{re.escape(title)}\s*$", b)
        p = ms[1].start()
        print(f"\n  ### {title}  heading @{p+b0}")
        print(f"  RAW first 700 chars after heading:\n{b[p:p+700]!r}")
        end = p + 200000
        seg = b[p:end]
        sc = hits(r"^\s*SCENE\s+([IVXL]+)\.(.{0,40})", seg)
        print(f"  uppercase 'SCENE n.' in first 200k n={len(sc)}; first 8:")
        quote(sc, 8, p + b0)
    print("\n  --- global: which heading spellings exist for scenes? ---")
    for pat in (r"^\s*SCENE\s+[IVXL]+\.", r"^\s*Scene\s+[IVXL]+\.",
                r"^\s*SCENE\s+[IVXL]+[^.\n]", r"^\s*SCENE:", r"^\s*Scene\s+[IVXL]+[^.\n]"):
        ms = hits(pat, b)
        print(f"    {pat:<34} n={len(ms)}")
        quote(ms, 2, b0)
    print("\n  --- units with no scene number ---")
    for w in ("Prologue", "Epilogue", "INDUCTION", "Chorus", "ACT I", "SCENE I"):
        ms = hits(rf"^\s*{w}\.?\s*$", b)
        print(f"    own-line {w!r:<12} n={len(ms)} first@{[m.start()+b0 for m in ms][:6]}")


def pass3h() -> None:
    head("PASS 3h-1  SHAKESPEARE: true scene count = after 'Dramatis Person' only")
    b, b0 = body(txt("shakespeare"))
    lines = b.splitlines()
    toc0 = next(i for i, l in enumerate(lines) if l.strip() == "Contents")
    toc = [l.strip() for l in lines[toc0 + 1:toc0 + 60] if l.strip()]
    starts = []
    for e in toc:
        ms = hits(rf"^\s*{re.escape(e)}\s*$", b)
        if len(ms) >= 2:
            starts.append((ms[1].start(), e))
    starts.sort()
    tot = 0
    plays = 0
    bad = []
    for i, (p, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(b)
        seg = b[p:end]
        dp = re.search(r"Dramatis Person", seg)
        after = seg[dp.end():] if dp else seg
        sc = hits(r"^\s*SCENE\s+([IVXL]+)\.", after)
        ac = hits(r"^\s*ACT\s+([IVXL]+)\b", after)
        if ac:
            plays += 1
            tot += len(sc)
        if len(ac) not in (0, 5):
            bad.append((name, len(ac), len(sc)))
        if not dp and end - p > 1000:
            bad.append((name + "  [NO Dramatis Personae]", len(ac), len(sc)))
    print(f"  plays with ACT headings after Dramatis Personae = {plays}")
    print(f"  total SCENE headings after Dramatis Personae   = {tot}")
    print("  works whose ACT count != 5 (or lacking Dramatis Personae):")
    for n, a, s in bad:
        print(f"     {n[:52]:<54} acts={a} scenes={s}")

    head("PASS 3h-2  DARWIN + HERODOTUS: any page anchor in html/epub?")
    for slug in ("darwin-origin", "herodotus", "plato-republic",
                 "homer-iliad-but", "homer-iliad-pope"):
        h = html(slug)
        print(f"\n  {slug} html chars={len(h)}")
        for label, pat in [
            ("id=\"page...\"/pagenum", r'id="(?:page|Page|pagenum|pg)[^"]*"'),
            ("class=pagenum", r'class="[^"]*pagenum[^"]*"'),
            ("[Pg NN] / [Page NN]", r"\[P(?:g|age)[^\]]{0,10}\]"),
            ("epub:type=pagebreak", r"pagebreak"),
            ("<a id=... numeric", r'<a id="[^"]*\d+[^"]*"'),
        ]:
            ms = hits(pat, h, 0)
            print(f"    {label:<26} n={len(ms)}")
            quote(ms, 3)


def pass3i() -> None:
    head("PASS 3i  exact page-anchor counts (page_anchor column analogue)")
    for slug in ("darwin-origin", "herodotus", "plato-republic", "shakespeare",
                 "homer-iliad-but", "homer-iliad-pope", "euclid-elements"):
        h = html(slug)
        pg = hits(r'<a id="Page(\d+)"', h, 0)
        anyp = hits(r'id="[Pp]age[_\-]?(\d+)"', h, 0)
        nums = [int(m.group(1)) for m in anyp]
        print(f"  {slug:<20} <a id=\"PageN\" n={len(pg):>4}  "
              f"id=page-like n={len(anyp):>4} "
              f"range={min(nums) if nums else '-'}..{max(nums) if nums else '-'}")
        quote(anyp, 3)
    print("\n  --- Euclid: are propositions individually anchored? ---")
    h = html("euclid-elements")
    for pat in (r'id="[^"]*[Pp]rop[^"]*"', r'id="Q\d+-\d+-\d+"',
                r'href="#[^"]*"', r'<a id="[^"]*"'):
        ms = hits(pat, h, 0)
        print(f"    {pat:<28} n={len(ms)}")
        quote(ms, 4)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    fns = {"plato": plato, "shak": shakespeare, "euclid": euclid,
           "darwin": darwin, "herod": herodotus, "iliad": iliad,
           "p3a": pass3a, "p3b": pass3b, "p3c": pass3c, "p3d": pass3d,
           "p3e": pass3e, "p3f": pass3f, "p3g": pass3g, "p3h": pass3h,
           "p3i": pass3i}
    for k, f in fns.items():
        if which in ("all", k):
            f()
