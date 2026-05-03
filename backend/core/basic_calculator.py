"""基础单井节能优化计算器。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BasicCalculateRequest(BaseModel):
    power: float = Field(gt=0, description="抽油机功率 (kW)")
    output_value: float = Field(gt=0, description="油井产量")
    output_unit: Literal["day", "month", "year"] = Field(description="产量单位")
    electricity_price: float = Field(gt=0, description="工业电价 (元/kWh)")
    oil_price: float = Field(gt=0, description="原油价格 (元/吨)")
    max_loss_ratio: float = Field(ge=0, le=100, description="最大允许产量损失比 (%)")

    @field_validator("power", "output_value", "electricity_price", "oil_price")
    @classmethod
    def check_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("必须大于 0")
        return v

    @field_validator("max_loss_ratio")
    @classmethod
    def check_loss_ratio(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("必须在 0 到 100 之间")
        return v


class SchemeResult(BaseModel):
    name: str
    energy_savings: float
    money_saved: float
    production_loss: float
    loss_rate: float
    carbon_reduction: float
    net_profit: float


class BasicCalculateResponse(BaseModel):
    best_scheme: Literal["energy", "production", "balanced"]
    schemes: dict[Literal["energy", "production", "balanced"], SchemeResult]


def _convert_to_daily_output(output_value: float, output_unit: str) -> float:
    if output_unit == "day":
        return output_value
    elif output_unit == "month":
        return output_value / 30
    elif output_unit == "year":
        return output_value / 365
    return output_value


def _calculate_scheme(
    power: float,
    daily_output: float,
    electricity_price: float,
    oil_price: float,
    max_loss_ratio: float,
    target_loss_ratio: float,
) -> SchemeResult:
    target_loss = min(target_loss_ratio, max_loss_ratio)
    hours_per_day = 24
    base_energy = power * hours_per_day
    base_cost = base_energy * electricity_price
    base_revenue = daily_output * oil_price

    reduced_hours = hours_per_day * (1 - target_loss / 100)
    actual_energy = power * reduced_hours
    actual_cost = actual_energy * electricity_price
    actual_output = daily_output * (1 - target_loss / 100)
    actual_revenue = actual_output * oil_price

    energy_savings = base_energy - actual_energy
    money_saved = base_cost - actual_cost
    production_loss = daily_output - actual_output
    loss_rate = target_loss
    carbon_reduction = energy_savings * 0.6
    net_profit = actual_revenue - actual_cost

    return SchemeResult(
        name="",
        energy_savings=round(energy_savings, 4),
        money_saved=round(money_saved, 4),
        production_loss=round(production_loss, 4),
        loss_rate=round(loss_rate, 4),
        carbon_reduction=round(carbon_reduction, 4),
        net_profit=round(net_profit, 4),
    )


def calculate_basic(request: BasicCalculateRequest) -> BasicCalculateResponse:
    daily_output = _convert_to_daily_output(request.output_value, request.output_unit)

    energy_scheme = _calculate_scheme(
        request.power,
        daily_output,
        request.electricity_price,
        request.oil_price,
        request.max_loss_ratio,
        request.max_loss_ratio,
    )
    energy_scheme.name = "节能优先"

    production_scheme = _calculate_scheme(
        request.power,
        daily_output,
        request.electricity_price,
        request.oil_price,
        request.max_loss_ratio,
        min(0.1, request.max_loss_ratio),
    )
    production_scheme.name = "保产优先"

    balanced_ratio = request.max_loss_ratio * 0.3
    balanced_scheme = _calculate_scheme(
        request.power,
        daily_output,
        request.electricity_price,
        request.oil_price,
        request.max_loss_ratio,
        balanced_ratio,
    )
    balanced_scheme.name = "平衡方案"

    best_scheme = "balanced"
    best_profit = balanced_scheme.net_profit
    if energy_scheme.net_profit > best_profit:
        best_profit = energy_scheme.net_profit
        best_scheme = "energy"
    if production_scheme.net_profit > best_profit:
        best_profit = production_scheme.net_profit
        best_scheme = "production"

    return BasicCalculateResponse(
        best_scheme=best_scheme,
        schemes={
            "energy": energy_scheme,
            "production": production_scheme,
            "balanced": balanced_scheme,
        },
    )