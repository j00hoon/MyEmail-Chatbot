from __future__ import annotations

from typing import Iterable, Sequence


def _require_langchain():
    try:
        from langchain.chains.query_constructor.schema import AttributeInfo
        from langchain.retrievers import ContextualCompressionRetriever
        from langchain.retrievers.multi_query import MultiQueryRetriever
        from langchain.retrievers.self_query.base import SelfQueryRetriever
        from langchain.retrievers.ensemble import EnsembleRetriever
        from langchain_community.retrievers import BM25Retriever
        from langchain_community.vectorstores import FAISS
        from langchain_core.documents import Document
        from langchain_core.output_parsers import BaseOutputParser
        from langchain_core.prompts import PromptTemplate
        from langchain_cohere import CohereRerank
    except ImportError as exc:
        raise ImportError(
            "LangChain email retrieval helpers require langchain, langchain-community, "
            "langchain-openai, langchain-cohere, rank-bm25, and faiss-cpu."
        ) from exc

    return {
        "AttributeInfo": AttributeInfo,
        "ContextualCompressionRetriever": ContextualCompressionRetriever,
        "MultiQueryRetriever": MultiQueryRetriever,
        "SelfQueryRetriever": SelfQueryRetriever,
        "EnsembleRetriever": EnsembleRetriever,
        "BM25Retriever": BM25Retriever,
        "FAISS": FAISS,
        "Document": Document,
        "BaseOutputParser": BaseOutputParser,
        "PromptTemplate": PromptTemplate,
        "CohereRerank": CohereRerank,
    }


def build_email_documents(email_chunks: Iterable[dict]) -> list:
    """Convert email chunk payloads into LangChain Documents."""
    lc = _require_langchain()
    Document = lc["Document"]

    documents = []
    for chunk in email_chunks:
        documents.append(
            Document(
                page_content=chunk["page_content"],
                metadata={
                    "email_id": chunk.get("email_id"),
                    "gmail_message_id": chunk.get("gmail_message_id"),
                    "sender": chunk.get("sender"),
                    "date": chunk.get("date"),
                    "subject": chunk.get("subject"),
                    "attachment_names": chunk.get("attachment_names", []),
                    "chunk_id": chunk.get("chunk_id"),
                },
            )
        )
    return documents


def build_ensemble_retriever(documents: Sequence, embeddings, top_k: int = 8, precomputed_vectors: Sequence[Sequence[float]] | None = None):
    """
    Build a BM25 + FAISS hybrid retriever with weighted reciprocal rank fusion.

    Weights are fixed to 0.4 for BM25 and 0.6 for vector search.
    """
    lc = _require_langchain()
    BM25Retriever = lc["BM25Retriever"]
    FAISS = lc["FAISS"]
    EnsembleRetriever = lc["EnsembleRetriever"]

    bm25_retriever = BM25Retriever.from_documents(list(documents))
    bm25_retriever.k = top_k

    if precomputed_vectors is not None:
        text_embeddings = [
            (document.page_content, list(vector))
            for document, vector in zip(documents, precomputed_vectors)
        ]
        faiss_store = FAISS.from_embeddings(
            text_embeddings=text_embeddings,
            embedding=embeddings,
            metadatas=[document.metadata for document in documents],
        )
    else:
        faiss_store = FAISS.from_documents(list(documents), embeddings)
    vector_retriever = faiss_store.as_retriever(search_kwargs={"k": top_k})

    ensemble = EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[0.4, 0.6],
    )
    return ensemble, faiss_store


def build_contextual_compression_retriever(
    base_retriever,
    *,
    cohere_api_key: str | None = None,
    model: str = "rerank-english-v3.0",
    top_n: int = 3,
):
    """Wrap a retriever with Cohere reranking and return top 3 compressed docs."""
    lc = _require_langchain()
    ContextualCompressionRetriever = lc["ContextualCompressionRetriever"]
    CohereRerank = lc["CohereRerank"]

    compressor = CohereRerank(
        cohere_api_key=cohere_api_key,
        model=model,
        top_n=top_n,
    )
    return ContextualCompressionRetriever(
        base_retriever=base_retriever,
        base_compressor=compressor,
    )


def build_email_self_query_retriever(vectorstore, llm, *, search_kwargs: dict | None = None):
    """
    Build a SelfQueryRetriever that supports sender/date/subject metadata filters.

    This lets the LLM translate prompts like:
    "emails from John last week"
    into a semantic query plus structured metadata filters.
    """
    lc = _require_langchain()
    AttributeInfo = lc["AttributeInfo"]
    SelfQueryRetriever = lc["SelfQueryRetriever"]

    metadata_field_info = [
        AttributeInfo(
            name="sender",
            description="The email sender, usually a person name and/or email address",
            type="string",
        ),
        AttributeInfo(
            name="date",
            description="The sent date of the email chunk in ISO or RFC-style string form",
            type="string",
        ),
        AttributeInfo(
            name="subject",
            description="The email subject line",
            type="string",
        ),
    ]

    return SelfQueryRetriever.from_llm(
        llm=llm,
        vectorstore=vectorstore,
        document_contents="Email chunks from a personal Gmail mailbox",
        metadata_field_info=metadata_field_info,
        search_kwargs=search_kwargs or {"k": 8},
        enable_limit=True,
        use_original_query=True,
    )


def build_multi_query_retriever(base_retriever, llm, *, query_count: int = 3):
    """
    Build a MultiQueryRetriever that rewrites one user question into 3 variants.
    """
    lc = _require_langchain()
    BaseOutputParser = lc["BaseOutputParser"]
    PromptTemplate = lc["PromptTemplate"]
    MultiQueryRetriever = lc["MultiQueryRetriever"]

    class LineListOutputParser(BaseOutputParser[list[str]]):
        def parse(self, text: str) -> list[str]:
            lines = [line.strip() for line in text.strip().splitlines()]
            cleaned = []
            for line in lines:
                if not line:
                    continue
                cleaned.append(line.lstrip("0123456789.-) ").strip())
            return cleaned[:query_count]

    output_parser = LineListOutputParser()
    prompt = PromptTemplate(
        input_variables=["question"],
        template=(
            "You generate alternate search queries for personal email retrieval.\n"
            f"Create exactly {query_count} different phrasings of the user's question.\n"
            "Keep the intent identical, but vary wording, specificity, and metadata focus.\n"
            "Return only the rewritten queries, one per line.\n\n"
            "Original question: {question}"
        ),
    )
    llm_chain = prompt | llm | output_parser

    retriever = MultiQueryRetriever(
        retriever=base_retriever,
        llm_chain=llm_chain,
        parser_key="lines",
    )
    return retriever, llm_chain


def generate_multi_queries(question: str, llm_chain) -> list[str]:
    """Generate alternate queries from the MultiQueryRetriever chain."""
    return llm_chain.invoke({"question": question})
