"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    weights: ObjectiveWeights
    Q_min: float = Field(ge=0, description="24h 最低总产量约束")
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
    sensitivity_line: dict[str, Any]
    summary_cards: list[dict[str, Any]]


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
