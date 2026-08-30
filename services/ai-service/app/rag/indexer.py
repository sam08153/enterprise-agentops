from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.rag.chunker import chunk_document
from app.rag.embeddings import DeterministicHashEmbedding, get_default_embedding_model
from app.rag.loader import load_documents


@dataclass(frozen=True)
class IngestionResult:
    tenant_name: str
    documents_indexed: int
    chunks_indexed: int


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def get_db_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(settings.database_url, row_factory=dict_row)


def ensure_tenant_id(conn, tenant_name: str) -> str:
    row = conn.execute("SELECT id FROM tenants WHERE name = %s", (tenant_name,)).fetchone()
    if row:
        return str(row["id"])

    inserted = conn.execute(
        "INSERT INTO tenants (name) VALUES (%s) RETURNING id",
        (tenant_name,),
    ).fetchone()
    return str(inserted["id"])


def upsert_document(conn, tenant_id: str, source: str, content: str) -> str:
    title = Path(source).stem

    existing = conn.execute(
        "SELECT id FROM documents WHERE tenant_id = %s AND source = %s",
        (tenant_id, source),
    ).fetchone()

    if existing:
        document_id = str(existing["id"])
        conn.execute(
            "UPDATE documents SET title = %s, content = %s WHERE id = %s",
            (title, content, document_id),
        )
        return document_id

    inserted = conn.execute(
        "INSERT INTO documents (tenant_id, title, content, source) VALUES (%s, %s, %s, %s) RETURNING id",
        (tenant_id, title, content, source),
    ).fetchone()
    return str(inserted["id"])


def replace_document_chunks(
    conn,
    document_id: str,
    chunks: Iterable[dict],
    embeddings: Iterable[list[float]],
) -> int:
    conn.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))

    inserted_count = 0
    for chunk, embedding in zip(chunks, embeddings, strict=False):
        conn.execute(
            "INSERT INTO document_chunks (document_id, content, embedding) VALUES (%s, %s, %s::vector)",
            (document_id, chunk["content"], _vector_literal(embedding)),
        )
        inserted_count += 1
    return inserted_count


def ingest_directory(
    directory: str | Path,
    tenant_name: str = "demo",
    chunk_size: int = 800,
    overlap: int = 100,
    embedding_model: DeterministicHashEmbedding | None = None,
) -> IngestionResult:
    embedding_model = embedding_model or get_default_embedding_model()

    raw_documents = load_documents(directory)

    documents_indexed = 0
    chunks_indexed = 0

    with get_db_connection() as conn:
        tenant_id = ensure_tenant_id(conn, tenant_name)

        for doc in raw_documents:
            document_id = upsert_document(
                conn,
                tenant_id=tenant_id,
                source=doc["source"],
                content=doc["content"],
            )
            doc_with_id = {**doc, "document_id": document_id}

            chunks = chunk_document(doc_with_id, chunk_size=chunk_size, overlap=overlap)
            vectors = embedding_model.embed_texts([c["content"] for c in chunks])

            chunks_indexed += replace_document_chunks(conn, document_id, chunks, vectors)
            documents_indexed += 1

    return IngestionResult(
        tenant_name=tenant_name,
        documents_indexed=documents_indexed,
        chunks_indexed=chunks_indexed,
    )
