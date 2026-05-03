from __future__ import annotations

from fastapi import APIRouter

from core.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_root() -> HealthResponse:
    return HealthResponse(status="ok", service="oil-pump-optimization-backend", version="1.1.0")


@router.get("/api/health", response_model=HealthResponse)
def health_api() -> HealthResponse:
    return HealthResponse(status="ok", service="oil-pump-optimization-backend", version="1.1.0")
