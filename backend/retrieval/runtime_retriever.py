from __future__ import annotations

from dataclasses import dataclass

from config import settings
from skills.embedding_generation import EmbeddingGenerationSkill
from retrieval.langchain_email_retrievers import (
    build_contextual_compression_retriever,
    build_email_documents,
    build_email_self_query_retriever,
    build_ensemble_retriever,
    build_multi_query_retriever,
)


@dataclass
class RuntimeRetrieverPipeline:
    ensemble_retriever: object
    compression_retriever: object
    self_query_retriever: object | None
    multi_query_retriever: object

    def retrieve(self, question: str, *, mode: str = "general"):
        if mode == "self_query" and self.self_query_retriever is not None:
            return self.self_query_retriever.invoke(question)
        if mode == "multi_query":
            return self.multi_query_retriever.invoke(question)
        return self.compression_retriever.invoke(question)


def _embedding_base_class():
    try:
        from langchain_core.embeddings import Embeddings
        return Embeddings
    except ImportError:
        return object


class LangChainEmbeddingAdapter(_embedding_base_class()):
    def __init__(self):
        self.skill = EmbeddingGenerationSkill()

    def embed_query(self, text: str):
        return self.skill.execute(text)

    def embed_documents(self, texts: list[str]):
        return self.skill.execute_many(texts)


def build_runtime_retriever(vector_records: list[dict]):
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    if not settings.langchain_retrieval_enabled or not settings.openai_api_key:
        return None

    email_chunks = []
    for record in vector_records:
        metadata = record.get("metadata", {})
        email_chunks.append(
            {
                "email_id": metadata.get("email_id"),
                "gmail_message_id": metadata.get("gmail_message_id"),
                "sender": metadata.get("sender"),
                "date": metadata.get("sent_at"),
                "subject": metadata.get("subject"),
                "attachment_names": metadata.get("attachment_names", []),
                "chunk_id": record.get("id"),
                "page_content": metadata.get("document", ""),
            }
        )

    if not email_chunks:
        return None

    documents = build_email_documents(email_chunks)
    embeddings = LangChainEmbeddingAdapter()
    llm = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_chat_model,
        temperature=0,
    )

    ensemble_retriever, vectorstore = build_ensemble_retriever(
        documents=documents,
        embeddings=embeddings,
        top_k=settings.langchain_retrieval_top_k,
        precomputed_vectors=[record.get("embedding", []) for record in vector_records],
    )
    compression_retriever = ensemble_retriever
    if settings.cohere_api_key:
        try:
            compression_retriever = build_contextual_compression_retriever(
                ensemble_retriever,
                cohere_api_key=settings.cohere_api_key,
                top_n=3,
            )
        except Exception:
            compression_retriever = ensemble_retriever
    try:
        self_query_retriever = build_email_self_query_retriever(
            vectorstore=vectorstore,
            llm=llm,
            search_kwargs={"k": settings.langchain_retrieval_top_k},
        )
    except Exception:
        self_query_retriever = None
    multi_query_retriever, _ = build_multi_query_retriever(
        base_retriever=ensemble_retriever,
        llm=llm,
        query_count=3,
    )

    return RuntimeRetrieverPipeline(
        ensemble_retriever=ensemble_retriever,
        compression_retriever=compression_retriever,
        self_query_retriever=self_query_retriever,
        multi_query_retriever=multi_query_retriever,
    )
