from app.rag.retriever import hybrid_search


def search_knowledge(query: str, tenant_id: str = "demo") -> dict:
    results = hybrid_search(query=query, tenant_name=tenant_id, top_k=5)
    return {
        "query": query,
        "tenant_id": tenant_id,
        "results": [
            {
                "source": r["source"],
                "content": r["content"],
                "score": float(r["score"]),
            }
            for r in results
        ],
    }


SEARCH_KNOWLEDGE_TOOL_DEFINITION = {
    "name": "search_knowledge",
    "description": "Search organizational knowledge (runbooks, incidents, architecture docs) using hybrid retrieval (vector + keyword).",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "tenant_id": {"type": "string", "description": "Tenant name/id. Defaults to 'demo'."},
        },
        "required": ["query"],
    },
}
