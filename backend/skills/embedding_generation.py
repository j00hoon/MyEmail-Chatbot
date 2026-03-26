import math
import re
from collections import Counter

from openai import OpenAI

from config import settings


class EmbeddingGenerationSkill:
    dimension = 256

    def execute(self, text: str):
        if settings.openai_api_key:
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text,
            )
            return response.data[0].embedding
        return self._fallback_embedding(text)

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
