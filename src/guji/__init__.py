"""古籍 alignment primitives for the Book Research Infrastructure.

Two modules, both driven by measurements recorded in docs/DECISIONS.md:
  variants — the single shared 異體字 fold table (D-003)
  anchors  — 卦/爻 addressing, the cross-edition join key (D-005, D-006)
"""
from .anchors import (
    Cleaned,
    GuaSpan,
    clean,
    detect_mislabelled_yao,
    extract_yao,
    gua_number,
    gua_spans,
    gua_symbol,
    lines_from_trigrams,
    yao_names,
)
from .search import Corpus, Hit, fts_phrase
from .variants import FOLD, fold, segment_cjk

__all__ = [
    "Cleaned", "GuaSpan", "clean", "detect_mislabelled_yao",
    "extract_yao", "gua_number", "gua_spans",
    "gua_symbol", "lines_from_trigrams", "yao_names", "FOLD", "fold", "segment_cjk",
    "Corpus", "Hit", "fts_phrase",
]
