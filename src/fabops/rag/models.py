"""bge-m3 (dense + sparse in one pass) and bge-reranker, loaded lazily once per process.

Both come from FlagEmbedding so dense and sparse share one model source (Colin, 2026-11-08);
Ollama is used only for LLM generation. Tests replace `Encoder` / `Reranker` with fakes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from fabops.config import get_settings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


@dataclass
class Encoded:
    dense: list[list[float]]
    sparse: list[dict[str, float]]  # token id -> weight


class Encoder(Protocol):
    def encode(self, texts: list[str]) -> Encoded: ...


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class BGEM3Encoder:
    def __init__(self, model: str, device: str, batch_size: int = 16):
        from FlagEmbedding import BGEM3FlagModel

        self._m = BGEM3FlagModel(model, use_fp16=device != "cpu", devices=device)
        self.batch_size = batch_size

    def encode(self, texts: list[str]) -> Encoded:
        out = self._m.encode(
            texts, batch_size=self.batch_size, return_dense=True, return_sparse=True
        )
        return Encoded(
            dense=[v.tolist() for v in out["dense_vecs"]],
            sparse=[{k: float(w) for k, w in d.items()} for d in out["lexical_weights"]],
        )


class BGEReranker:
    def __init__(self, model: str, device: str):
        from FlagEmbedding import FlagReranker

        self._m = FlagReranker(model, use_fp16=device != "cpu", devices=device)

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        s = self._m.compute_score([[query, t] for t in texts])
        return [float(x) for x in (s if isinstance(s, list) else [s])]


@lru_cache
def default_encoder() -> Encoder:
    cfg = get_settings()
    return BGEM3Encoder(cfg.embed_model, cfg.embed_device)


@lru_cache
def default_reranker() -> Reranker:
    cfg = get_settings()
    return BGEReranker(cfg.rerank_model, cfg.embed_device)
