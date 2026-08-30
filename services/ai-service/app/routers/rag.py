from fastapi import APIRouter

from app.rag.retriever import hybrid_search
from app.schemas import RagSearchRequest, RagSearchResponse, RagSearchResult

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/search", response_model=RagSearchResponse)
def rag_search(request: RagSearchRequest):
    results = hybrid_search(query=request.query, tenant_name=request.tenant_id, top_k=5)
    return RagSearchResponse(
        query=request.query,
        tenant_id=request.tenant_id,
        results=[
            RagSearchResult(
                source=r["source"],
                score=float(r["score"]),
                content=r["content"],
            )
            for r in results
        ],
    )
