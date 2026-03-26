from dataclasses import dataclass

from tools.vector_store import VectorStore


@dataclass
class VectorSearchSkill:
    vector_store: VectorStore

    def execute(self, query_embedding: list[float], query_text: str, top_k: int):
        return self.vector_store.search(
            query_embedding=query_embedding,
            query_text=query_text,
            top_k=top_k,
        )
