from __future__ import annotations

import math
import re
from collections import Counter

from app.rag.embeddings import DeterministicHashEmbedding, get_default_embedding_model
from app.rag.indexer import _vector_literal, get_db_connection


_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-\.]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _bm25_scores(query: str, documents: list[dict], k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    tokenized_docs: list[list[str]] = [_tokenize(d.get("content", "")) for d in documents]
    query_terms = _tokenize(query)
    if not query_terms or not documents:
        return {}

    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        for term in set(tokens):
            doc_freq[term] += 1

    doc_lens = [len(tokens) for tokens in tokenized_docs]
    avgdl = (sum(doc_lens) / len(doc_lens)) if doc_lens else 0.0

    scores: dict[str, float] = {}
    N = len(documents)

    for idx, tokens in enumerate(tokenized_docs):
        if not tokens:
            continue

        tf = Counter(tokens)
        dl = doc_lens[idx]
        score = 0.0

        for term in query_terms:
            n_qi = doc_freq.get(term, 0)
            if n_qi == 0:
                continue

            idf = math.log(1.0 + (N - n_qi + 0.5) / (n_qi + 0.5))
            f = tf.get(term, 0)
            denom = f + k1 * (1.0 - b + b * (dl / (avgdl or 1.0)))
            score += idf * ((f * (k1 + 1.0)) / (denom or 1.0))

        scores[str(documents[idx]["id"])] = score

    return scores


def _normalize_scores(scores_by_id: dict[str, float]) -> dict[str, float]:
    if not scores_by_id:
        return {}
    max_score = max(scores_by_id.values()) or 0.0
    if max_score <= 0.0:
        return {k: 0.0 for k in scores_by_id}
    return {k: (v / max_score) for k, v in scores_by_id.items()}


def vector_search(
    query: str,
    tenant_name: str,
    k: int = 5,
    embedding_model: DeterministicHashEmbedding | None = None,
) -> list[dict]:
    embedding_model = embedding_model or get_default_embedding_model()
    query_vec = embedding_model.embed_text(query)
    query_vec_lit = _vector_literal(query_vec)

    sql = """
        SELECT
            dc.id,
            d.source,
            dc.content,
            (1 - (dc.embedding <=> %s::vector)) AS vector_score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN tenants t ON t.id = d.tenant_id
        WHERE t.name = %s AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> %s::vector
        LIMIT %s
    """

    with get_db_connection() as conn:
        rows = conn.execute(sql, (query_vec_lit, tenant_name, query_vec_lit, k)).fetchall()

    results = []
    for r in rows:
        score = float(r.get("vector_score") or 0.0)
        results.append(
            {
                "id": str(r["id"]),
                "source": r.get("source") or "",
                "content": r.get("content") or "",
                "vector_score": score,
            }
        )
    return results


def bm25_search(query: str, tenant_name: str, k: int = 5) -> list[dict]:
    sql = """
        SELECT
            dc.id,
            d.source,
            dc.content
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN tenants t ON t.id = d.tenant_id
        WHERE t.name = %s
    """

    with get_db_connection() as conn:
        rows = conn.execute(sql, (tenant_name,)).fetchall()

    docs = [{"id": str(r["id"]), "source": r.get("source") or "", "content": r.get("content") or ""} for r in rows]
    scores = _bm25_scores(query, docs)

    ranked = sorted(docs, key=lambda d: scores.get(d["id"], 0.0), reverse=True)
    results = []
    for d in ranked[:k]:
        results.append(
            {
                **d,
                "bm25_score": float(scores.get(d["id"], 0.0)),
            }
        )
    return results


def hybrid_search(
    query: str,
    tenant_name: str = "demo",
    top_k: int = 5,
    vector_k: int = 5,
    bm25_k: int = 5,
    vector_weight: float = 0.7,
    bm25_weight: float = 0.3,
    embedding_model: DeterministicHashEmbedding | None = None,
) -> list[dict]:
    vector_results = vector_search(
        query=query,
        tenant_name=tenant_name,
        k=vector_k,
        embedding_model=embedding_model,
    )
    bm25_results = bm25_search(query=query, tenant_name=tenant_name, k=bm25_k)

    vector_norm = _normalize_scores({r["id"]: max(0.0, float(r.get("vector_score") or 0.0)) for r in vector_results})
    bm25_norm = _normalize_scores({r["id"]: max(0.0, float(r.get("bm25_score") or 0.0)) for r in bm25_results})

    merged: dict[str, dict] = {}

    for r in vector_results:
        merged[r["id"]] = {**r, "bm25_score": 0.0}

    for r in bm25_results:
        if r["id"] in merged:
            merged[r["id"]].update(r)
        else:
            merged[r["id"]] = {**r, "vector_score": 0.0}

    fused = []
    for chunk_id, r in merged.items():
        score = vector_weight * vector_norm.get(chunk_id, 0.0) + bm25_weight * bm25_norm.get(chunk_id, 0.0)
        fused.append(
            {
                "id": chunk_id,
                "source": r.get("source") or "",
                "content": r.get("content") or "",
                "score": float(score),
                "vector_score": float(r.get("vector_score") or 0.0),
                "bm25_score": float(r.get("bm25_score") or 0.0),
            }
        )

    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused[:top_k]
