from __future__ import annotations

import argparse
import json
from pathlib import Path

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from retrieval.langchain_email_retrievers import (
    build_email_documents,
    build_ensemble_retriever,
    build_multi_query_retriever,
    generate_multi_queries,
)


def load_email_chunks(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Generate 3 alternate queries with MultiQueryRetriever.")
    parser.add_argument("question", help="Original user question")
    parser.add_argument(
        "--chunks-json",
        default="backend/data/email_chunks.json",
        help="Path to prebuilt email chunk JSON payloads",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="Embedding model to use for FAISS indexing",
    )
    parser.add_argument(
        "--chat-model",
        default="gpt-4o-mini",
        help="Chat model used to rewrite queries",
    )
    args = parser.parse_args()

    chunk_payloads = load_email_chunks(Path(args.chunks_json))
    documents = build_email_documents(chunk_payloads)

    embeddings = OpenAIEmbeddings(model=args.embedding_model)
    llm = ChatOpenAI(model=args.chat_model, temperature=0)

    ensemble_retriever, _ = build_ensemble_retriever(documents=documents, embeddings=embeddings)
    _, llm_chain = build_multi_query_retriever(
        base_retriever=ensemble_retriever,
        llm=llm,
        query_count=3,
    )

    queries = generate_multi_queries(args.question, llm_chain)
    print("Generated queries:")
    for index, query in enumerate(queries, start=1):
        print(f"{index}. {query}")


if __name__ == "__main__":
    main()
