import math
import re
from collections import Counter

from openai import OpenAI

from config import settings


class EmbeddingGenerationSkill:
    dimension = 256

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def execute(self, text: str):
        if self.client is not None:
            response = self.client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text,
            )
            return response.data[0].embedding
        return self._fallback_embedding(text)

    def execute_many(self, texts: list[str]):
        if not texts:
            return []

        if self.client is not None:
            response = self.client.embeddings.create(
                model=settings.openai_embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]

        return [self._fallback_embedding(text) for text in texts]

    def _fallback_embedding(self, text: str):
        vector = [0.0] * self.dimension
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        counts = Counter(tokens)
        if not counts:
            return vector

        for token, count in counts.items():
            bucket = hash(token) % self.dimension
            vector[bucket] += float(count)

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]
        return vector
