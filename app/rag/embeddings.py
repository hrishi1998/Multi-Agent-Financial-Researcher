import hashlib
import math
import os
from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Pluggable embedding backend. Tests use the deterministic hash provider."""

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError


class HashEmbeddingProvider(BaseEmbeddingProvider):
    """Local, deterministic bag-of-words hash embedding. No network or API key."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    async def embed_text(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Optional OpenAI/LangChain slot. Falls back to the hash provider if unused."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self.model = model
        self._fallback = HashEmbeddingProvider()

    async def embed_text(self, text: str) -> List[float]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return await self._fallback.embed_text(text)
        try:
            from langchain_openai import OpenAIEmbeddings

            embeddings = OpenAIEmbeddings(model=self.model, api_key=api_key)
            return list(await embeddings.aembed_query(text))
        except Exception:
            return await self._fallback.embed_text(text)


def get_embedding_provider() -> BaseEmbeddingProvider:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbeddingProvider()
    return HashEmbeddingProvider()
