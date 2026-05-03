"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


NUM_SLOTS = 24


class ObjectiveWeights(BaseModel):
    w_energy: float = Field(ge=0, description="能耗目标权重")
    w_carbon: float = Field(ge=0, description="碳排目标权重")
    w_economic: float = Field(ge=0, description="期望经济成本权重")

    @model_validator(mode="after")
    def validate_total(self) -> "ObjectiveWeights":
        total = self.w_energy + self.w_carbon + self.w_economic
        if total <= 0:
            raise ValueError("weights 权重之和必须大于 0")
        return self


class WellInput(BaseModel):
    well_id: str = Field(min_length=1)
    name: str | None = None
    q_it: list[float]
    e_it: list[float]
    c_start_i: float = Field(ge=0)
    H_min_i: int = Field(ge=0, le=NUM_SLOTS)
    H_max_i: int = Field(ge=0, le=NUM_SLOTS)
    N_max_i: int = Field(ge=0, le=NUM_SLOTS)

    @model_validator(mode="before")
    @classmethod
    def normalize_series_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        def _expand_to_24(v: Any) -> Any:
            if isinstance(v, (int, float)):
                return [float(v)] * NUM_SLOTS
            if isinstance(v, str):
                try:
                    fv = float(v)
                    return [fv] * NUM_SLOTS
                except ValueError:
                    return v
            if isinstance(v, list):
                return v
            return v

        # 兼容：q_it 允许单数字，自动扩成 24 时段
        if "q_it" in data:
            data["q_it"] = _expand_to_24(data.get("q_it"))

        # 兼容：e_it 允许单数字；或缺失/无效时用 power_consumption 兜底
        if "e_it" in data:
            expanded = _expand_to_24(data.get("e_it"))
            if isinstance(expanded, list):
                data["e_it"] = expanded
            elif "power_consumption" in data:
                data["e_it"] = _expand_to_24(data.get("power_consumption"))
            else:
                data["e_it"] = expanded
        elif "power_consumption" in data:
            data["e_it"] = _expand_to_24(data.get("power_consumption"))

        return data

    @field_validator("q_it", "e_it", mode="before")
    @classmethod
    def coerce_series_or_raise(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, list):
            return value
        if isinstance(value, (int, float)):
            return [float(value)] * NUM_SLOTS
        if isinstance(value, str):
            try:
                fv = float(value)
                return [fv] * NUM_SLOTS
            except ValueError:
                pass
        raise ValueError(f"{info.field_name} 应为长度24数组，已检测到标量/非数组输入。")

    @field_validator("q_it", "e_it")
    @classmethod
    def check_slot_length(cls, values: list[float]) -> list[float]:
        if len(values) != NUM_SLOTS:
            raise ValueError(f"序列长度必须为 {NUM_SLOTS}")
        return values

    @field_validator("q_it")
    @classmethod
    def check_q_non_negative(cls, values: list[float]) -> list[float]:
        if any(v < 0 for v in values):
            raise ValueError("q_it 不能包含负数")
        return values

    @field_validator("e_it")
    @classmethod
    def check_e_positive(cls, values: list[float]) -> list[float]:
        if any(v < 0 for v in values):
            raise ValueError("e_it 不能包含负数")
        return values

    @model_validator(mode="after")
    def check_hours(self) -> "WellInput":
        if self.H_max_i < self.H_min_i:
            raise ValueError("H_max_i 不能小于 H_min_i")
        return self


class ScenarioInput(BaseModel):
    id: str = Field(min_length=1)
    label: str | None = None
    p_s: float = Field(gt=0, le=1)
    peak_price: float = Field(gt=0)
    offpeak_price: float = Field(gt=0)
    peak_hours: list[int] = Field(default_factory=list)

    @field_validator("peak_hours")
    @classmethod
    def check_peak_hours(cls, values: list[int]) -> list[int]:
        bad = [h for h in values if h < 0 or h >= NUM_SLOTS]
        if bad:
            raise ValueError(f"peak_hours 存在越界时段: {bad}")
        return values


class OptionalConstraints(BaseModel):
    hourly_load_cap: list[float] | None = Field(
        default=None,
        description="长度 24 的分时负荷上限；为空则不启用",
    )

    @field_validator("hourly_load_cap")
    @classmethod
    def check_len(cls, values: list[float] | None) -> list[float] | None:
        if values is None:
            return values
        if len(values) != NUM_SLOTS:
            raise ValueError(f"hourly_load_cap 长度必须为 {NUM_SLOTS}")
        if any(v < 0 for v in values):
            raise ValueError("hourly_load_cap 不能包含负数")
        return values


class AnalysisRunRequest(BaseModel):
    wells: list[WellInput]
    scenarios: list[ScenarioInput]
    gamma_t: list[float] | None = Field(default=None, description="24 时段碳排因子；缺省则读取样例值")
    weights: ObjectiveWeights | None = Field(default=None, description="目标权重；缺省时自动使用默认值")
    Q_min: float | None = Field(default=None, ge=0, description="24h 最低总产量约束；缺省时自动估算")
    optional_constraints: OptionalConstraints | None = None
    baseline_compare: Literal["full_run", "simple_rule", "both"] = "both"

    @field_validator("gamma_t")
    @classmethod
    def check_gamma(cls, values: list[float] | None) -> list[float] | None:
        if values is None:
            return values
        if len(values) != NUM_SLOTS:
            raise ValueError(f"gamma_t 长度必须为 {NUM_SLOTS}")
        if any(v < 0 for v in values):
            raise ValueError("gamma_t 不能包含负数")
        return values

    @model_validator(mode="after")
    def validate_scenarios(self) -> "AnalysisRunRequest":
        if not self.wells:
            raise ValueError("wells 不能为空")
        if not self.scenarios:
            raise ValueError("scenarios 不能为空")
        prob_sum = sum(s.p_s for s in self.scenarios)
        if abs(prob_sum - 1.0) > 1e-3:
            raise ValueError(f"scenarios 概率之和必须约等于 1，当前为 {prob_sum:.6f}")
        return self


class SensitivityRequest(BaseModel):
    wells: list[WellInput]
    scenarios: list[ScenarioInput]
    gamma_t: list[float] | None = Field(default=None, description="24 时段碳排因子；缺省则读取样例值")
    Q_min: float = Field(ge=0)
    optional_constraints: OptionalConstraints | None = None
    weight_sets: list[ObjectiveWeights] | None = Field(default=None, description="自定义权重组合")

    @field_validator("gamma_t")
    @classmethod
    def check_gamma_s(cls, values: list[float] | None) -> list[float] | None:
        if values is None:
            return values
        if len(values) != NUM_SLOTS:
            raise ValueError(f"gamma_t 长度必须为 {NUM_SLOTS}")
        if any(v < 0 for v in values):
            raise ValueError("gamma_t 不能包含负数")
        return values

    @model_validator(mode="after")
    def validate_scenarios(self) -> "SensitivityRequest":
        if not self.wells:
            raise ValueError("wells 不能为空")
        if not self.scenarios:
            raise ValueError("scenarios 不能为空")
        prob_sum = sum(s.p_s for s in self.scenarios)
        if abs(prob_sum - 1.0) > 1e-3:
            raise ValueError(f"scenarios 概率之和必须约等于 1，当前为 {prob_sum:.6f}")
        return self


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class HistoryRecordSummary(BaseModel):
    id: str
    created_at: str
    input_summary: dict[str, Any]
    objective_weights: dict[str, float]
    optimized_core_metrics: dict[str, Any]
    explanation_summary: str


class HistoryListResponse(BaseModel):
    records: list[HistoryRecordSummary]


class HistoryDeleteResponse(BaseModel):
    deleted: bool
    id: str


class MetricSummary(BaseModel):
    feasible: bool
    infeasible_reason: str | None = None
    total_energy: float
    total_carbon: float
    expected_economic_cost: float
    objective_score: float | None = None
    total_production: float
    hourly_load: list[float]
    schedule_matrix: list[list[int]] = Field(default_factory=list)
    startup_matrix: list[list[int]] = Field(default_factory=list)
    normalized_terms: dict[str, Any] = Field(default_factory=dict)
    solver_status: str | None = None
    solver_engine: str | None = None
    objective_value_scaled: int | float | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ComparisonBlock(BaseModel):
    energy_saving_rate: float
    carbon_reduction_rate: float
    economic_improvement_rate: float
    production_change_rate: float


class ExplanationResponse(BaseModel):
    dominant_objective: str
    wells_suggested_avoid_peak: list[str]
    wells_better_continuous: list[str]
    wells_start_stop_limited: list[str]
    largest_benefit_vs_full_run: str
    rule_hits: list[dict[str, Any]]
    paragraphs: list[str]
    management_briefing: str
    summary_one_line: str
    sensitivity_note: str | None = None


class ChartsPayloadResponse(BaseModel):
    heatmap: dict[str, Any]
    hourly_load: dict[str, Any]
    baseline_vs_optimized: dict[str, Any]
    sensitivity: dict[str, Any]


class SensitivityCaseResponse(BaseModel):
    label: str
    weights: dict[str, float]
    feasible: bool
    infeasible_reason: str | None = None
    total_energy: float
    total_carbon: float
    expected_economic_cost: float
    objective_score: float | None = None
    total_production: float
    solver_engine: str | None = None


class SensitivityResponse(BaseModel):
    cases: list[SensitivityCaseResponse]
    templates_meta: list[dict[str, Any]] | None = None
    best_case_label: str | None = None
    feasible_case_count: int
    charts_payload: dict[str, Any] | None = None


class AnalysisRunResponse(BaseModel):
    input_summary: dict[str, Any]
    optimized_result: MetricSummary
    baseline_results: dict[str, MetricSummary]
    comparison_summary: dict[str, ComparisonBlock]
    explanation: ExplanationResponse
    charts_payload: ChartsPayloadResponse
    saved_record_id: str
    sensitivity_preview: SensitivityResponse


class SampleDataResponse(BaseModel):
    meta: dict[str, Any]
    wells: list[WellInput]
    scenarios: list[ScenarioInput]
    gamma_t: list[float]
    recommended_weights: ObjectiveWeights
    recommended_Q_min: float
    request_template: dict[str, Any]
    run_request_example: dict[str, Any]


class WellPageRow(BaseModel):
    """与队友单页 demo 表单字段对齐（单井标量参数，后端展开为 24 时段）。"""

    id: int | None = None
    well_id: str | None = None
    P_rated: float = Field(default=30, gt=0, description="额定功率/时段耗电近似 (kW)")
    q_rate: float = Field(default=0.5, ge=0, description="单位时段产量近似")
    c_start: float = Field(default=100, ge=0, description="启动成本")
    H_min: int = Field(default=4, ge=0, le=NUM_SLOTS)
    H_max: int = Field(default=20, ge=0, le=NUM_SLOTS)

    @model_validator(mode="after")
    def check_hours(self) -> "WellPageRow":
        if self.H_max < self.H_min:
            raise ValueError("H_max 不能小于 H_min")
        return self


class PageAdvancedParams(BaseModel):
    """与队友 HTML 高级参数默认值对齐。"""

    oil_price: float = Field(default=3500, ge=0)
    gamma: float = Field(default=0.5, ge=0, description="碳排折算系数（对应 HTML gamma）")
    P_max: float = Field(default=250, gt=0, description="变压器/母线分时总负荷上限 (kW)")
    Q_min: float = Field(default=20, ge=0, description="24h 最低总产量")
    peak_price: float = Field(default=0.8225, gt=0)
    flat_price: float = Field(default=0.6277, gt=0)
    valley_price: float = Field(default=0.4329, gt=0)
    daily_carbon_limit: float = Field(default=1500, gt=0, description="日碳排上限（与模型量纲一致）")
    peak_hours_clock: list[int] = Field(default_factory=lambda: [8, 9, 10, 11, 12, 18, 19, 20, 21, 22])
    flat_hours_clock: list[int] = Field(default_factory=lambda: [12, 13, 14, 15, 16, 17, 18, 22, 23, 24])
    mutex_pairs_clock: list[list[int]] = Field(default_factory=lambda: [[1, 3]])
    noisy_wells_clock: list[int] = Field(default_factory=lambda: [3, 6])
    night_hours_clock: list[int] = Field(default_factory=lambda: [23, 24, 1, 2, 3, 4, 5])
    storm_hours_clock: list[int] = Field(default_factory=lambda: [13, 14])
    max_running_during_storm: int = Field(default=6, ge=0)
    N_max_startups_default: int = Field(default=8, ge=0, le=NUM_SLOTS, description="每井最大启动次数默认")


class AutoOptimizeRequest(BaseModel):
    wells: list[WellPageRow] = Field(min_length=1, max_length=24)
    advanced: PageAdvancedParams | None = None
