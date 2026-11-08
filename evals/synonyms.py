"""Synonym / abbreviation table for fact matching (ADR-0005), derived from the data rules.

Maps a canonical term to the variants the corpus uses for it, so the scorer can accept
"月PM" for "月保養". Extend here rather than in score.py so the table stays reviewable.
"""

from __future__ import annotations

from fabops.data import world


def synonym_table() -> dict[str, list[str]]:
    table = {canon: list(variants) for canon, variants in world.ABBREVIATIONS.items()}
    # Typos are deliberately *not* synonyms: an answer should not reproduce a typo.
    return table
