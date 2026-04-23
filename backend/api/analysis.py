from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from core import baseline, explain, sensitivity
from core.optimizer import OptimizePayload, optimize_schedule
from core.sample_generator import ensure_demo_files
from core.schemas import AnalysisRunRequest, AnalysisRunResponse, SensitivityRequest, SensitivityResponse
from core.storage import append_history
from core.utils import rate_improvement

router = APIRouter(tags=["analysis"])


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _comparison_block(optimized: dict[str, Any], ref: dict[str, Any]) -> dict[str, float]:
    return {
        "energy_saving_rate": round(rate_improvement(float(ref["total_energy"]), float(optimized["total_energy"])), 6),
        "carbon_reduction_rate": round(rate_improvement(float(ref["total_carbon"]), float(optimized["total_carbon"])), 6),
        "economic_improvement_rate": round(
            rate_improvement(float(ref["expected_economic_cost"]), float(optimized["expected_economic_cost"])),
            6,
        ),
    }


def _production_change_rate_plain(optimized: dict[str, Any], ref: dict[str, Any]) -> float:
    """产量变化率：(优化-基准)/基准；下降为负。"""
    b = float(ref["total_production"])
    o = float(optimized["total_production"])
    if b == 0:
        return 0.0
    return round((o - b) / b, 6)


def build_charts_payload(
    wells: list[dict[str, Any]],
    optimized: dict[str, Any],
    b_full: dict[str, Any],
    b_rule: dict[str, Any],
    sens: dict[str, Any],
) -> dict[str, Any]:
    well_ids = [str(w.get("well_id", "")) for w in wells]
    hours = [f"{h}:00" for h in range(24)]
    sched = optimized.get("schedule_matrix") or []
    heatmap_series: list[list[int]] = []
    for x_idx, row in enumerate(sched):
        for y_idx, v in enumerate(row):
            heatmap_series.append([x_idx, y_idx, int(v)])
    heatmap = {"x_axis": well_ids, "y_axis": hours, "series": heatmap_series}

    opt_load = optimized.get("hourly_load") or []
    full_load = b_full.get("hourly_load") or []
    rule_load = b_rule.get("hourly_load") or []
    hourly_load = {
        "categories": hours,
        "series": [
            {"name": "优化方案", "type": "line", "data": [float(v) for v in opt_load]},
            {"name": "全时运行", "type": "line", "data": [float(v) for v in full_load]},
            {"name": "固定错峰", "type": "line", "data": [float(v) for v in rule_load]},
        ],
    }
    cats = ["总能耗", "总碳排", "期望经济成本"]
    baseline_vs_optimized = {
        "categories": cats,
        "series": [
            {
                "name": "优化方案",
                "type": "bar",
                "data": [
                    float(optimized.get("total_energy") or 0),
                    float(optimized.get("total_carbon") or 0),
                    float(optimized.get("expected_economic_cost") or 0),
                ],
            },
            {
                "name": "全时运行",
                "type": "bar",
                "data": [
                    float(b_full.get("total_energy") or 0),
                    float(b_full.get("total_carbon") or 0),
                    float(b_full.get("expected_economic_cost") or 0),
                ],
            },
            {
                "name": "固定错峰",
                "type": "bar",
                "data": [
                    float(b_rule.get("total_energy") or 0),
                    float(b_rule.get("total_carbon") or 0),
                    float(b_rule.get("expected_economic_cost") or 0),
                ],
            },
        ],
    }
    cases = sens.get("cases") or []
    sensitivity_data = {
        "categories": [str(c.get("label", "")) for c in cases],
        "series": [
            {"name": "总能耗", "type": "line", "data": [float(c.get("total_energy") or 0) for c in cases]},
            {"name": "总碳排", "type": "line", "data": [float(c.get("total_carbon") or 0) for c in cases]},
            {
                "name": "期望经济成本",
                "type": "line",
                "data": [float(c.get("expected_economic_cost") or 0) for c in cases],
            },
        ],
    }
    return {
        "heatmap": heatmap,
        "hourly_load": hourly_load,
        "baseline_vs_optimized": baseline_vs_optimized,
        "sensitivity": sensitivity_data,
    }


def empty_charts_payload() -> dict[str, Any]:
    return {
        "heatmap": {"x_axis": [], "y_axis": [], "series": []},
        "hourly_load": {"categories": [], "series": []},
        "baseline_vs_optimized": {"categories": [], "series": []},
        "sensitivity": {"categories": [], "series": []},
    }


def _bundle_dicts(req: AnalysisRunRequest | SensitivityRequest) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
    wells = [w.model_dump() for w in req.wells]
    scenarios = [s.model_dump() for s in req.scenarios]
    if req.gamma_t is not None:
        gamma_t = list(req.gamma_t)
    else:
        from core.sample_generator import load_bundle_from_disk

        gamma_t = list(load_bundle_from_disk(_data_dir())["gamma_t"])
    return wells, scenarios, gamma_t


@router.post("/api/analysis/run", response_model=AnalysisRunResponse)
def run_analysis(req: AnalysisRunRequest) -> dict[str, Any]:
    ensure_demo_files(_data_dir())
    wells, scenarios, gamma_t = _bundle_dicts(req)

    cap = req.optional_constraints.hourly_load_cap if req.optional_constraints else None

    payload = OptimizePayload(
        wells=wells,
        scenarios=scenarios,
        gamma_t=list(gamma_t),
        w_energy=req.weights.w_energy,
        w_carbon=req.weights.w_carbon,
        w_economic=req.weights.w_economic,
        Q_min=req.Q_min,
        hourly_load_cap=cap,
    )
    opt = optimize_schedule(payload)

    b_full = baseline.package_baseline("baseline_full_run", wells, scenarios, list(gamma_t))
    b_rule = baseline.package_baseline("baseline_simple_rule", wells, scenarios, list(gamma_t))
    if req.baseline_compare == "full_run":
        baseline_results = {"baseline_full_run": b_full}
    elif req.baseline_compare == "simple_rule":
        baseline_results = {"baseline_simple_rule": b_rule}
    else:
        baseline_results = {"baseline_full_run": b_full, "baseline_simple_rule": b_rule}

    sens = sensitivity.sensitivity_analysis(wells, scenarios, list(gamma_t), req.Q_min, None, cap)

    wdict = {
        "w_energy": float(req.weights.w_energy),
        "w_carbon": float(req.weights.w_carbon),
        "w_economic": float(req.weights.w_economic),
    }
    ssum = sum(wdict.values()) or 1.0
    wnorm = {k: round(v / ssum, 6) for k, v in wdict.items()}

    explanation = explain.explain_result(opt, baseline_results, sens, wells, scenarios, wnorm)

    cmp_full = _comparison_block(opt, b_full)
    cmp_full["production_change_rate"] = _production_change_rate_plain(opt, b_full)

    comparison_summary = {"vs_baseline_full_run": cmp_full}
    if "baseline_simple_rule" in baseline_results:
        comparison_summary["vs_baseline_simple_rule"] = {
            **_comparison_block(opt, b_rule),
            "production_change_rate": _production_change_rate_plain(opt, b_rule),
        }

    charts_payload = build_charts_payload(wells, opt, b_full, b_rule, sens)
    if not isinstance(charts_payload, dict):
        charts_payload = empty_charts_payload()

    input_summary = {
        "num_wells": len(wells),
        "num_slots": len(wells[0]["q_it"]) if wells else 0,
        "Q_min": req.Q_min,
        "weights_raw": wdict,
        "weights_normalized": wnorm,
        "optional_constraints": req.optional_constraints.model_dump() if req.optional_constraints else None,
        "scenario_probability_sum": round(sum(float(s["p_s"]) for s in scenarios), 6),
    }

    core_metrics = {
        "feasible": opt.get("feasible"),
        "total_energy": opt.get("total_energy"),
        "total_carbon": opt.get("total_carbon"),
        "expected_economic_cost": opt.get("expected_economic_cost"),
        "objective_score": opt.get("objective_score"),
        "total_production": opt.get("total_production"),
    }

    rid = append_history(
        _data_dir() / "history.json",
        input_summary=input_summary,
        objective_weights=wnorm,
        optimized_core_metrics=core_metrics,
        explanation_summary=str(explanation.get("summary_one_line") or ""),
    )

    return {
        "input_summary": input_summary,
        "optimized_result": opt,
        "baseline_results": baseline_results,
        "comparison_summary": comparison_summary,
        "explanation": explanation,
        "charts_payload": charts_payload,
        "saved_record_id": rid,
        "sensitivity_preview": sens,
    }


@router.post("/api/analysis/sensitivity", response_model=SensitivityResponse)
def run_sensitivity(req: SensitivityRequest) -> dict[str, Any]:
    ensure_demo_files(_data_dir())
    wells, scenarios, gamma_t = _bundle_dicts(req)
    cap = req.optional_constraints.hourly_load_cap if req.optional_constraints else None
    sens = sensitivity.sensitivity_analysis(wells, scenarios, list(gamma_t), req.Q_min, req.weight_sets, cap)
    cases = sens.get("cases") or []
    sens["charts_payload"] = {
        "heatmap": {"x_axis": [], "y_axis": [], "series": []},
        "hourly_load": {"categories": [], "series": []},
        "baseline_vs_optimized": {"categories": [], "series": []},
        "sensitivity": {
            "categories": [str(c.get("label", "")) for c in cases],
            "series": [
                {"name": "总能耗", "type": "line", "data": [float(c.get("total_energy") or 0) for c in cases]},
                {"name": "总碳排", "type": "line", "data": [float(c.get("total_carbon") or 0) for c in cases]},
                {
                    "name": "期望经济成本",
                    "type": "line",
                    "data": [float(c.get("expected_economic_cost") or 0) for c in cases],
                },
            ],
        },
    }
    return sens
