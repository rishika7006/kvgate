"""Pluggable text embedders for the semantic cache.

The default ``HashingEmbedder`` is fully dependency-free: it hashes character
n-grams into a fixed-dimension L2-normalized vector. It is NOT a true semantic
model, but it captures lexical overlap well enough to demonstrate and test the
semantic-cache machinery out of the box. For real semantic hits, swap in the
``sentence_transformers`` or ``openai`` embedder via config.
"""

from __future__ import annotations

import abc
import hashlib
import math
import re
from typing import List

_WORD = re.compile(r"\w+")


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class Embedder(abc.ABC):
    dim: int

    @abc.abstractmethod
    def embed(self, text: str) -> List[float]: ...


class HashingEmbedder(Embedder):
    def __init__(self, dim: int = 256, ngram: int = 3) -> None:
        self.dim = dim
        self.ngram = ngram

    def _tokens(self, text: str) -> List[str]:
        words = _WORD.findall(text.lower())
        grams = list(words)
        for n in (2, self.ngram):
            grams += [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
        return grams or [text.lower()]

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in self._tokens(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class SentenceTransformerEmbedder(Embedder):  # pragma: no cover - optional dep
    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence_transformers embedder requested but not installed. "
                "Install with: pip install 'kvgate[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(model)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> List[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


def build_embedder(kind: str, model: str) -> Embedder:
    if kind == "sentence_transformers":
        return SentenceTransformerEmbedder(model)
    if kind == "openai":  # pragma: no cover - requires network/keys
        raise NotImplementedError(
            "openai embedder is config-only; wire your key via the provider section."
        )
    return HashingEmbedder()
