"""高级井群优化接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from core import page_adapter
from core.schemas import AutoOptimizeRequest, PageAdvancedParams, WellPageRow

router = APIRouter(tags=["advanced"])


class AdvancedWellInput(BaseModel):
    id: str = Field(min_length=1, description="井编号")
    power: float = Field(gt=0, description="额定功率 (kW)")
    q_rate: float = Field(ge=0, description="单位时段产量")
    startup_cost: float = Field(ge=0, description="启动成本")
    h_min: int = Field(ge=0, le=24, description="最小运行时长")
    h_max: int = Field(ge=0, le=24, description="最大运行时长")

    @model_validator(mode="after")
    def check_hours(self) -> "AdvancedWellInput":
        if self.h_max < self.h_min:
            raise ValueError("h_max 不能小于 h_min")
        return self


class AdvancedParams(BaseModel):
    oil_price: float = Field(gt=0, description="原油价格 (元/吨)")
    carbon_factor: float = Field(ge=0, description="碳排放因子")
    transformer_max: float = Field(gt=0, description="变压器最大容量 (kW)")
    q_min: float = Field(ge=0, description="最低日产量要求")
    peak_price: float = Field(gt=0, description="峰时电价")
    flat_price: float = Field(gt=0, description="平时电价")
    valley_price: float = Field(gt=0, description="谷时电价")
    daily_carbon_limit: float = Field(gt=0, description="日碳排放上限")


class AdvancedOptimizeRequest(BaseModel):
    wells: list[AdvancedWellInput] = Field(min_length=1, max_length=24)
    params: AdvancedParams


class AdvancedSchemeResult(BaseModel):
    name: str
    total_energy: float
    total_emission: float
    total_cost: float
    revenue: float
    profit: float
    total_oil: float
    peak_load: float
    total_startups: int
    load_profile: list[float]
    schedule: list[list[int]]


class AdvancedOptimizeResponse(BaseModel):
    best_scheme: Literal["energy", "benefit", "balanced"]
    schemes: dict[Literal["energy", "benefit", "balanced"], AdvancedSchemeResult]


@router.post("/api/advanced/optimize", response_model=AdvancedOptimizeResponse)
def advanced_optimize(request: AdvancedOptimizeRequest) -> AdvancedOptimizeResponse:
    if len(request.wells) != 6:
        raise HTTPException(status_code=400, detail="wells 数量必须为 6")

    for well in request.wells:
        if well.h_max < well.h_min:
            raise HTTPException(status_code=400, detail=f"井 {well.id} 的 h_max 不能小于 h_min")

    rows = []
    for well in request.wells:
        rows.append(
            WellPageRow(
                well_id=well.id,
                P_rated=well.power,
                q_rate=well.q_rate,
                c_start=well.startup_cost,
                H_min=well.h_min,
                H_max=well.h_max,
            )
        )

    params = request.params
    advanced = PageAdvancedParams(
        oil_price=params.oil_price,
        gamma=params.carbon_factor,
        P_max=params.transformer_max,
        Q_min=params.q_min,
        peak_price=params.peak_price,
        flat_price=params.flat_price,
        valley_price=params.valley_price,
        daily_carbon_limit=params.daily_carbon_limit,
    )

    auto_req = AutoOptimizeRequest(wells=rows, advanced=advanced)
    result = page_adapter.run_page_auto_optimize(auto_req)

    profiles = result.get("profiles", {})
    scheme_map = {"energy_first": "energy", "benefit_first": "benefit", "balanced": "balanced"}

    schemes: dict[str, AdvancedSchemeResult] = {}
    best_scheme = "balanced"
    best_profit = float("-inf")

    for key, mapped_key in scheme_map.items():
        profile = profiles.get(key, {})
        kpis = profile.get("kpis", {})
        res = profile.get("result", {})

        if not kpis.get("feasible"):
            schemes[mapped_key] = AdvancedSchemeResult(
                name="",
                total_energy=0.0,
                total_emission=0.0,
                total_cost=0.0,
                revenue=0.0,
                profit=float("-inf"),
                total_oil=0.0,
                peak_load=0.0,
                total_startups=0,
                load_profile=[0.0] * 24,
                schedule=[[0] * 24 for _ in range(6)],
            )
            continue

        schedule_matrix = res.get("schedule_matrix", [])
        while len(schedule_matrix) < 6:
            schedule_matrix.append([0] * 24)

        scheme = AdvancedSchemeResult(
            name={
                "energy_first": "节能优先",
                "benefit_first": "效益最高",
                "balanced": "平衡方案",
            }[key],
            total_energy=float(kpis.get("total_energy", 0)),
            total_emission=float(kpis.get("total_carbon", 0)),
            total_cost=float(kpis.get("electricity_and_startup_cost", 0)),
            revenue=float(kpis.get("oil_revenue", 0)),
            profit=float(kpis.get("profit", 0)),
            total_oil=float(kpis.get("total_oil", 0)),
            peak_load=float(kpis.get("peak_load_kw", 0)),
            total_startups=int(kpis.get("total_startups", 0)),
            load_profile=[float(x) for x in res.get("hourly_load", [0.0] * 24)],
            schedule=schedule_matrix,
        )

        schemes[mapped_key] = scheme

        if scheme.profit > best_profit:
            best_profit = scheme.profit
            best_scheme = mapped_key

    if best_profit == float("-inf"):
        raise HTTPException(status_code=400, detail="所有方案均无可行解，请检查约束条件")

    return AdvancedOptimizeResponse(best_scheme=best_scheme, schemes=schemes)