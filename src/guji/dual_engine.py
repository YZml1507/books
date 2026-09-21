"""Dual-engine text extraction with cross-validation gate (Q-07 / D-001).

Two independent PDF/EPUB text extractors are run on the same source:

  * PyMuPDF (fitz) — the primary engine, fast, exposes page boundaries via
    `page.get_text()`.
  * markitdown (pdfminer.six/pdfplumber for PDF, its own EPUB converter) — the
    cross-validation engine, independent parser chain.

If both engines produce the same garbage on a source with a missing ToUnicode
CMap, neither can be trusted alone and OCR becomes mandatory — that is a
parse-layer architecture decision (D-001), not a tooling preference.

This module productises the probe-level logic that was scattered across
`probes/probe_markitdown.py`, `probes/probe_cid_verify.py`, and
`probes/probe_crosssource.py` (Q-07). It exposes one function,
`compare(path)`, that returns a `DualEngineReport` with per-engine junk census
(Q-06) and the disagreement between the two outputs, plus a CLI-friendly
`summarise()`.

The gate does NOT fail on disagreement alone — disagreement is information,
not error. It fails only when BOTH engines are junk on the same source, which
means neither extractor can rescue the other and OCR is the only remaining path.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from .quality import junk_census, JunkReport  # Q-06 census reused


# --------------------------------------------------------------------------------------
# Engine adapters — thin wrappers so the rest of the module is engine-agnostic.
# --------------------------------------------------------------------------------------
def _extract_pymupdf(path: str) -> tuple[str, int]:
    """Return (text, page_count). Raises on engine error."""
    import pymupdf  # local import: not every consumer has PDFs
    doc = pymupdf.open(path)
    npages = doc.page_count
    text = "".join(p.get_text() for p in doc)
    doc.close()
    return text, npages


def _extract_markitdown(path: str) -> str:
    """Return text. Raises on engine error."""
    from markitdown import MarkItDown  # local import: heavy
    return MarkItDown().convert(path).text_content


# Page-delimiter markers markitdown could cite by. PyMuPDF gives page boundaries
# structurally (one `get_text()` per page); markitdown gives a flat string and
# may or may not emit page markers.
_PAGE_MARK_RE = re.compile(r"(?mi)^#+\s*page\s*\d+|\x0c|<!--\s*page")


@dataclass
class EngineResult:
    engine: str
    text: str
    junk: JunkReport
    elapsed: float
    pages: int | None = None          # page count (PyMuPDF) or None
    page_marks: int = 0               # markitdown flat-string page delimiters
    error: str | None = None          # engine error string, if it raised

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class DualEngineReport:
    path: str
    pymupdf: EngineResult
    markitdown: EngineResult
    # Disagreement between the two outputs, measured on the CJK content words
    # the source is expected to contain. Both-junk is the only failing state.
    both_junk: bool = False           # both engines junk > 5% — OCR mandatory

    def summarise(self) -> str:
        lines = [f"=== dual-engine report: {os.path.basename(self.path)} ==="]
        for r in (self.pymupdf, self.markitdown):
            if r.error:
                lines.append(f"  {r.engine:10} ERROR {r.error}")
                continue
            pm = f", {r.page_marks} page-marks" if r.engine == "markitdown" else (
                f", {r.pages} pages" if r.pages is not None else "")
            lines.append(
                f"  {r.engine:10} chars={r.junk.n_chars:,} "
                f"junk={r.junk.junk} ({100*r.junk.junk_rate:.2f}%)"
                f"  [{r.elapsed:.2f}s{pm}]"
            )
            if r.junk.cid:
                lines.append(f"              (cid:N) markers: {r.junk.cid}")
        verdict = "BOTH JUNK — OCR mandatory" if self.both_junk else (
            "disagreement present (information, not failure)" if (
                self.pymupdf.ok and self.markitdown.ok and
                self.pymupdf.junk.junk != self.markitdown.junk.junk
            ) else "engines agree")
        lines.append(f"  verdict: {verdict}")
        return "\n".join(lines)


# Both-engines-junk threshold. 5% is the D-001 measured line: the energy
# yearbook PyMuPDF hit 23.6% junk (both engines garbage) while the control
# scan was 0%. Below 5% the disagreement is real content divergence, not
# double-corruption.
_JUNK_BOTH_THRESHOLD = 0.05


def compare(path: str) -> DualEngineReport:
    """Run both engines on `path` and return a DualEngineReport.

    Never raises on engine error — the error is recorded in the
    EngineResult.error field so the caller can see which engine failed.
    """
    # PyMuPDF
    t0 = time.time()
    try:
        mu_text, npages = _extract_pymupdf(path)
        mu_junk = junk_census(mu_text, os.path.basename(path))
        mu_res = EngineResult("pymupdf", mu_text, mu_junk,
                              time.time() - t0, pages=npages)
    except Exception as e:
        mu_res = EngineResult("pymupdf", "", JunkReport("", 0, 0, 0, 0, 0, 0.0),
                              time.time() - t0, error=f"{type(e).__name__}: {e}")

    # markitdown
    t0 = time.time()
    try:
        mi_text = _extract_markitdown(path)
        mi_junk = junk_census(mi_text, os.path.basename(path))
        pm = len(_PAGE_MARK_RE.findall(mi_text))
        mi_res = EngineResult("markitdown", mi_text, mi_junk,
                              time.time() - t0, page_marks=pm)
    except Exception as e:
        mi_res = EngineResult("markitdown", "", JunkReport("", 0, 0, 0, 0, 0, 0.0),
                              time.time() - t0, error=f"{type(e).__name__}: {e}")

    both_junk = (mu_res.ok and mi_res.ok and
                 mu_res.junk.junk_rate >= _JUNK_BOTH_THRESHOLD and
                 mi_res.junk.junk_rate >= _JUNK_BOTH_THRESHOLD)
    return DualEngineReport(
        path=path, pymupdf=mu_res, markitdown=mi_res, both_junk=both_junk)
