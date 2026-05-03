"""基础单井优化接口。"""

from __future__ import annotations

from fastapi import APIRouter

from core.basic_calculator import BasicCalculateRequest, BasicCalculateResponse, calculate_basic

router = APIRouter(tags=["basic"])


@router.post("/api/basic/calculate", response_model=BasicCalculateResponse)
def basic_calculate(request: BasicCalculateRequest) -> BasicCalculateResponse:
    return calculate_basic(request)