import hashlib
import math
import re
from dataclasses import dataclass

VECTOR_DIMENSIONS = 1024
VOYAGE3_MODEL = "voyage-3"
BGE_M3_MODEL = "bge-m3"
LOCAL_HASH_MODEL = "local-hash-1024"

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class EmbeddingResult:
    embedding: list[float]
    embedding_model: str


class DeterministicHashEmbedder:
    """Local deterministic fallback used for dev/tests before a paid embedder is configured."""

    model_name = LOCAL_HASH_MODEL

    def __init__(self, dimensions: int = VECTOR_DIMENSIONS) -> None:
        self.dimensions = dimensions

    async def embed_text(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            embedding=self.embed_text_sync(text),
            embedding_model=self.model_name,
        )

    def embed_text_sync(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_RE.findall(text.lower())
        if not tokens:
            tokens = [text.lower().strip() or "empty"]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
