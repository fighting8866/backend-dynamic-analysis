from __future__ import annotations

from fastapi import APIRouter

from core.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="well-cluster-analysis-backend", version="1.1.0")
