"""基准方案：全时运行与固定错峰简化规则。"""

from __future__ import annotations

from typing import Any


def _num_wells_slots(wells: list[dict[str, Any]]) -> tuple[int, int]:
    n = len(wells)
    tlen = len(wells[0]["q_it"]) if n else 0
    return n, tlen


def derive_startup_matrix(schedule: list[list[int]]) -> list[list[int]]:
    n = len(schedule)
    T = len(schedule[0]) if n else 0
    y: list[list[int]] = [[0] * T for _ in range(n)]
    for i in range(n):
        y[i][0] = 1 if schedule[i][0] == 1 else 0
        for t in range(1, T):
            y[i][t] = 1 if schedule[i][t] == 1 and schedule[i][t - 1] == 0 else 0
    return y


def baseline_full_run(wells: list[dict[str, Any]]) -> tuple[list[list[int]], list[list[int]]]:
    n, T = _num_wells_slots(wells)
    x = [[1] * T for _ in range(n)]
    return x, derive_startup_matrix(x)


def baseline_simple_rule(wells: list[dict[str, Any]]) -> tuple[list[list[int]], list[list[int]]]:
    """
    固定错峰：低编号井避开 10-12 点峰段，高编号井避开 14-16 点峰段，
    形成简单轮停，便于与优化解对比。
    """
    n, T = _num_wells_slots(wells)
    x = [[1] * T for _ in range(n)]
    block_a = {10, 11, 12}
    block_b = {14, 15, 16}
    for i in range(n):
        for t in range(T):
            if i < n // 2 and t in block_a:
                x[i][t] = 0
            if i >= n // 2 and t in block_b:
                x[i][t] = 0
    return x, derive_startup_matrix(x)


def compute_metrics(
    wells: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    gamma_t: list[float],
    schedule: list[list[int]],
    startup: list[list[int]],
) -> dict[str, Any]:
    n, T = _num_wells_slots(wells)
    total_energy = 0.0
    total_production = 0.0
    hourly_load: list[float] = [0.0] * T
    total_carbon = 0.0

    for i in range(n):
        for t in range(T):
            if schedule[i][t]:
                e = float(wells[i]["e_it"][t])
                q = float(wells[i]["q_it"][t])
                total_energy += e
                total_production += q
                hourly_load[t] += e
                total_carbon += float(gamma_t[t]) * e

    expected_economic = 0.0
    for s in scenarios:
        p = float(s["p_s"])
        peak_hours = set(int(h) for h in s.get("peak_hours", []))
        p_peak = float(s["peak_price"])
        p_off = float(s["offpeak_price"])
        scen_cost = 0.0
        for i in range(n):
            for t in range(T):
                if not schedule[i][t]:
                    continue
                price = p_peak if t in peak_hours else p_off
                scen_cost += price * float(wells[i]["e_it"][t])
        start_cost = 0.0
        for i in range(n):
            for t in range(T):
                if startup[i][t]:
                    start_cost += float(wells[i]["c_start_i"])
        expected_economic += p * (scen_cost + start_cost)

    return {
        "total_energy": round(total_energy, 4),
        "total_carbon": round(total_carbon, 4),
        "expected_economic_cost": round(expected_economic, 4),
        "total_production": round(total_production, 4),
        "hourly_load": [round(v, 4) for v in hourly_load],
        "schedule_matrix": schedule,
        "startup_matrix": startup,
    }


def package_baseline(name: str, wells: list[dict[str, Any]], scenarios: list[dict[str, Any]], gamma_t: list[float]) -> dict[str, Any]:
    if name == "baseline_full_run":
        x, y = baseline_full_run(wells)
    elif name == "baseline_simple_rule":
        x, y = baseline_simple_rule(wells)
    else:
        raise ValueError(f"未知 baseline: {name}")
    m = compute_metrics(wells, scenarios, gamma_t, x, y)
    run_hours = {wells[i]["well_id"]: int(sum(x[i])) for i in range(len(wells))}
    return {
        "name": name,
        **m,
        "feasible": True,
        "infeasible_reason": None,
        "objective_score": None,
        "normalized_terms": {},
        "solver_status": "baseline",
        "solver_engine": "baseline-rule",
        "objective_value_scaled": None,
        "diagnostics": {
            "run_hours_by_well": run_hours,
            "meets_q_min_if_used_as_reference": None,
        },
    }


def meets_q_min(schedule: list[list[int]], wells: list[dict[str, Any]], q_min: float) -> bool:
    prod = 0.0
    for i, w in enumerate(wells):
        for t, on in enumerate(schedule[i]):
            if on:
                prod += float(w["q_it"][t])
    return prod >= q_min - 1e-6
