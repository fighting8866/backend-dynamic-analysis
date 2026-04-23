"""多组权重下的敏感性分析。"""

from __future__ import annotations

from typing import Any

from .optimizer import OptimizePayload, optimize_schedule
from .schemas import ObjectiveWeights


DEFAULT_TEMPLATES: list[dict[str, Any]] = [
    {"name": "节能优先", "weights": {"w_energy": 0.65, "w_carbon": 0.25, "w_economic": 0.10}},
    {"name": "降碳优先", "weights": {"w_energy": 0.20, "w_carbon": 0.65, "w_economic": 0.15}},
    {"name": "经济优先", "weights": {"w_energy": 0.15, "w_carbon": 0.15, "w_economic": 0.70}},
    {"name": "平衡方案", "weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33}},
]


def sensitivity_analysis(
    wells: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    gamma_t: list[float],
    Q_min: float,
    weight_sets: list[ObjectiveWeights] | None,
    hourly_load_cap: list[float] | None = None,
) -> dict[str, Any]:
    if weight_sets:
        sets = weight_sets
        names = [f"自定义{i+1}" for i in range(len(sets))]
        meta = None
    else:
        sets = [ObjectiveWeights(**t["weights"]) for t in DEFAULT_TEMPLATES]
        names = [t["name"] for t in DEFAULT_TEMPLATES]
        meta = DEFAULT_TEMPLATES

    rows: list[dict[str, Any]] = []
    for idx, w in enumerate(sets):
        payload = OptimizePayload(
            wells=wells,
            scenarios=scenarios,
            gamma_t=gamma_t,
            w_energy=w.w_energy,
            w_carbon=w.w_carbon,
            w_economic=w.w_economic,
            Q_min=Q_min,
            hourly_load_cap=hourly_load_cap,
        )
        res = optimize_schedule(payload)
        label = names[idx] if idx < len(names) else f"方案{idx+1}"
        rows.append(
            {
                "label": label,
                "weights": {"w_energy": w.w_energy, "w_carbon": w.w_carbon, "w_economic": w.w_economic},
                "feasible": res["feasible"],
                "infeasible_reason": res.get("infeasible_reason"),
                "total_energy": res["total_energy"],
                "total_carbon": res["total_carbon"],
                "expected_economic_cost": res["expected_economic_cost"],
                "objective_score": res.get("objective_score"),
                "total_production": res["total_production"],
                "solver_engine": res.get("solver_engine"),
            }
        )

    feasible_cases = [row for row in rows if row["feasible"]]
    best_case = min(feasible_cases, key=lambda row: row["objective_score"] if row["objective_score"] is not None else 999999) if feasible_cases else None

    return {
        "cases": rows,
        "templates_meta": meta,
        "best_case_label": best_case["label"] if best_case else None,
        "feasible_case_count": len(feasible_cases),
    }
