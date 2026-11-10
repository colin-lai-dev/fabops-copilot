"""Lexical scoring: jieba + BM25, and bge-m3 sparse (lexical weights) matching.

Both score only the candidates they are given; the caller passes chunks that already passed
the permission filter (ADR-0003: filter first, then rank), so corpus statistics such as IDF
come from what the user may see.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache

import jieba

from fabops.data import world

jieba.setLogLevel(logging.WARNING)

# IDs and codes (FX1-ETCHER-02, ETC-PRS-0412, INC-2026-0001) stay whole tokens; jieba would
# split them on the hyphens.
_CODE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+")
_KEEP = re.compile(r"\w", re.UNICODE)


@lru_cache
def _load_domain_dictionary() -> None:
    """Fab glossary (alarm names, PM types, abbreviations), as a real site would maintain."""
    words = [a.name for a in world.ALARM_TYPES] + world.PM_TYPES + list(world.DEPARTMENTS.values())
    words += ["監控晶圓", "處置程序", "根本原因", "停機", "復機", "派貨", "模組經理"]
    words += [w for canon, vs in world.ABBREVIATIONS.items() for w in (canon, *vs)]
    for w in words:
        jieba.add_word(w)


def tokenize(text: str, *, domain_dict: bool = True) -> list[str]:
    if domain_dict:
        _load_domain_dictionary()
    codes = [c.lower() for c in _CODE.findall(text)]
    rest = _CODE.sub(" ", text)
    words = [t.lower().strip() for t in jieba.lcut_for_search(rest)]
    return codes + [t for t in words if t and _KEEP.search(t)]


def bm25_scores(
    query_tokens: Sequence[str],
    docs_tokens: Sequence[Sequence[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    n = len(docs_tokens)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in docs_tokens) / n or 1.0
    df = Counter(t for d in docs_tokens for t in set(d))
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in set(query_tokens)}
    scores = []
    for d in docs_tokens:
        tf = Counter(d)
        norm = k1 * (1 - b + b * len(d) / avgdl)
        scores.append(
            sum(idf[t] * tf[t] * (k1 + 1) / (tf[t] + norm) for t in query_tokens if tf[t])
        )
    return scores


def sparse_scores(query: dict[str, float], docs: Sequence[dict[str, float]]) -> list[float]:
    """bge-m3 lexical matching: sum of weight products over shared tokens."""
    return [sum(w * d[t] for t, w in query.items() if t in d) for d in docs]
