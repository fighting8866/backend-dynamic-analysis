"""多目标优化求解器：OR-Tools 主解，PuLP 兜底。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import baseline
from .utils import clamp, normalize_weights, safe_div

try:
    from ortools.sat.python import cp_model
except Exception:  # pragma: no cover - 安装缺失时走兜底
    cp_model = None

try:
    import pulp
except Exception:  # pragma: no cover - 安装缺失时仅保留 OR-Tools
    pulp = None


@dataclass
class OptimizePayload:
    wells: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]
    gamma_t: list[float]
    w_energy: float
    w_carbon: float
    w_economic: float
    Q_min: float
    hourly_load_cap: list[float] | None = None
    # 可选：与队友单页 demo 对齐的扩展约束与分时电价（长度 24）
    custom_price_t: list[float] | None = None
    daily_carbon_cap: float | None = None
    mutex_pairs: list[list[int]] | None = None
    forbidden_well_hour: list[list[int]] | None = None
    storm_limits: list[list[int]] | None = None


def _empty_result(n: int, T: int, reason: str, diagnostics: dict[str, Any] | None = None, solver_engine: str | None = None) -> dict[str, Any]:
    return {
        "feasible": False,
        "infeasible_reason": reason,
        "schedule_matrix": [[0] * T for _ in range(n)],
        "startup_matrix": [[0] * T for _ in range(n)],
        "total_energy": 0.0,
        "total_carbon": 0.0,
        "expected_economic_cost": 0.0,
        "objective_score": None,
        "total_production": 0.0,
        "hourly_load": [0.0] * T,
        "normalized_terms": {},
        "solver_status": None,
        "solver_engine": solver_engine,
        "objective_value_scaled": None,
        "diagnostics": diagnostics or {},
    }


def _expected_electricity_price_t(scenarios: list[dict[str, Any]], t: int) -> float:
    s = 0.0
    for sc in scenarios:
        p = float(sc["p_s"])
        peak_hours = set(int(h) for h in sc.get("peak_hours", []))
        price = float(sc["peak_price"]) if t in peak_hours else float(sc["offpeak_price"])
        s += p * price
    return s


def _price_at_t(payload: OptimizePayload, t: int) -> float:
    if payload.custom_price_t is not None and len(payload.custom_price_t) == len(payload.wells[0]["q_it"]):
        return float(payload.custom_price_t[t])
    return _expected_electricity_price_t(payload.scenarios, t)


def _anchor_metrics(
    wells: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    gamma_t: list[float],
    hourly_price: list[float] | None = None,
) -> dict[str, tuple[float, float]]:
    b0 = baseline.package_baseline("baseline_full_run", wells, scenarios, gamma_t, hourly_electricity_price=hourly_price)
    b1 = baseline.package_baseline("baseline_simple_rule", wells, scenarios, gamma_t, hourly_electricity_price=hourly_price)

    def span(key: str) -> tuple[float, float]:
        v0 = float(b0[key])
        v1 = float(b1[key])
        lo, hi = min(v0, v1), max(v0, v1)
        if abs(hi - lo) < 1e-6:
            hi = lo + 1.0
        return lo, hi

    return {
        "energy": span("total_energy"),
        "carbon": span("total_carbon"),
        "economic": span("expected_economic_cost"),
    }


def _build_diagnostics(payload: OptimizePayload) -> dict[str, Any]:
    wells = payload.wells
    T = len(wells[0]["q_it"]) if wells else 0
    max_possible_production = round(sum(float(w["q_it"][t]) for w in wells for t in range(T)), 4)
    min_required_runtime = {w["well_id"]: int(w["H_min_i"]) for w in wells}
    max_allowed_runtime = {w["well_id"]: int(w["H_max_i"]) for w in wells}
    cap_binding_hours: list[int] = []
    if payload.hourly_load_cap:
        for t in range(T):
            cap = float(payload.hourly_load_cap[t])
            min_hourly_load = sum(float(w["e_it"][t]) for w in wells if int(w["H_min_i"]) >= T)
            if min_hourly_load > cap + 1e-6:
                cap_binding_hours.append(t)
    return {
        "requested_Q_min": round(float(payload.Q_min), 4),
        "max_possible_production_if_all_on": max_possible_production,
        "num_wells": len(wells),
        "num_slots": T,
        "min_required_runtime_by_well": min_required_runtime,
        "max_allowed_runtime_by_well": max_allowed_runtime,
        "hourly_cap_conflict_hours": cap_binding_hours,
    }


def _finalize_result(
    payload: OptimizePayload,
    schedule_matrix: list[list[int]],
    startup_matrix: list[list[int]],
    *,
    solver_status: str,
    solver_engine: str,
    objective_value_scaled: int | float | None,
    anchors: dict[str, tuple[float, float]],
    weights_normalized: tuple[float, float, float],
) -> dict[str, Any]:
    m = baseline.compute_metrics(
        payload.wells,
        payload.scenarios,
        payload.gamma_t,
        schedule_matrix,
        startup_matrix,
        hourly_electricity_price=payload.custom_price_t,
    )
    te = float(m["total_energy"])
    tc = float(m["total_carbon"])
    ek = float(m["expected_economic_cost"])

    E_lo, E_hi = anchors["energy"]
    C_lo, C_hi = anchors["carbon"]
    K_lo, K_hi = anchors["economic"]
    we, wc, wk = weights_normalized

    ze = clamp(safe_div(te - E_lo, E_hi - E_lo, 0.5), 0.0, 1.0)
    zc = clamp(safe_div(tc - C_lo, C_hi - C_lo, 0.5), 0.0, 1.0)
    zk = clamp(safe_div(ek - K_lo, K_hi - K_lo, 0.5), 0.0, 1.0)
    obj_score = we * ze + wc * zc + wk * zk

    return {
        "feasible": True,
        "infeasible_reason": None,
        "schedule_matrix": schedule_matrix,
        "startup_matrix": startup_matrix,
        "total_energy": m["total_energy"],
        "total_carbon": m["total_carbon"],
        "expected_economic_cost": m["expected_economic_cost"],
        "objective_score": round(float(obj_score), 6),
        "total_production": m["total_production"],
        "hourly_load": m["hourly_load"],
        "normalized_terms": {
            "z_energy": round(ze, 6),
            "z_carbon": round(zc, 6),
            "z_economic": round(zk, 6),
            "anchors": {
                "energy": {"min": E_lo, "max": E_hi},
                "carbon": {"min": C_lo, "max": C_hi},
                "economic": {"min": K_lo, "max": K_hi},
            },
            "weights_normalized": {"w_energy": round(we, 6), "w_carbon": round(wc, 6), "w_economic": round(wk, 6)},
        },
        "solver_status": solver_status,
        "solver_engine": solver_engine,
        "objective_value_scaled": objective_value_scaled,
        "diagnostics": _build_diagnostics(payload),
    }


def _solve_with_ortools(payload: OptimizePayload, anchors: dict[str, tuple[float, float]], weights_normalized: tuple[float, float, float]) -> dict[str, Any]:
    if cp_model is None:
        raise RuntimeError("OR-Tools 不可用")

    wells = payload.wells
    n = len(wells)
    T = len(wells[0]["q_it"]) if n else 0
    we, wc, wk = weights_normalized
    E_lo, E_hi = anchors["energy"]
    C_lo, C_hi = anchors["carbon"]
    K_lo, K_hi = anchors["economic"]

    model = cp_model.CpModel()
    x = [[model.NewBoolVar(f"x_{i}_{t}") for t in range(T)] for i in range(n)]
    y = [[model.NewBoolVar(f"y_{i}_{t}") for t in range(T)] for i in range(n)]

    prod_terms: list[Any] = []
    for i in range(n):
        for t in range(T):
            q = int(round(float(wells[i]["q_it"][t]) * 1000))
            prod_terms.append(q * x[i][t])
    model.Add(sum(prod_terms) >= int(round(payload.Q_min * 1000)))

    for i in range(n):
        model.Add(sum(x[i][t] for t in range(T)) >= int(wells[i]["H_min_i"]))
        model.Add(sum(x[i][t] for t in range(T)) <= int(wells[i]["H_max_i"]))

    for i in range(n):
        nmax = int(wells[i]["N_max_i"])
        model.Add(y[i][0] == x[i][0])
        for t in range(1, T):
            model.Add(y[i][t] >= x[i][t] - x[i][t - 1])
            model.Add(y[i][t] <= x[i][t])
            model.Add(y[i][t] <= 1 - x[i][t - 1])
        model.Add(sum(y[i][t] for t in range(T)) <= nmax)

    if payload.hourly_load_cap:
        for t in range(T):
            terms = [int(round(float(wells[i]["e_it"][t]) * 1000)) * x[i][t] for i in range(n)]
            model.Add(sum(terms) <= int(round(float(payload.hourly_load_cap[t]) * 1000)))

    if payload.mutex_pairs:
        for pair in payload.mutex_pairs:
            if len(pair) != 2:
                continue
            i, j = int(pair[0]), int(pair[1])
            if not (0 <= i < n and 0 <= j < n):
                continue
            for tt in range(T):
                model.Add(x[i][tt] + x[j][tt] <= 1)

    if payload.forbidden_well_hour:
        for pair in payload.forbidden_well_hour:
            if len(pair) != 2:
                continue
            ii, tt = int(pair[0]), int(pair[1])
            if 0 <= ii < n and 0 <= tt < T:
                model.Add(x[ii][tt] == 0)

    if payload.storm_limits:
        for pair in payload.storm_limits:
            if len(pair) != 2:
                continue
            tt, mx = int(pair[0]), int(pair[1])
            if 0 <= tt < T and mx >= 0:
                model.Add(sum(x[i][tt] for i in range(n)) <= mx)

    if payload.daily_carbon_cap is not None:
        cap = float(payload.daily_carbon_cap)
        cterms: list[Any] = []
        for i in range(n):
            for tt in range(T):
                coef = int(round(float(wells[i]["e_it"][tt]) * float(payload.gamma_t[tt]) * 1000))
                cterms.append(coef * x[i][tt])
        if cterms:
            model.Add(sum(cterms) <= int(round(cap * 1000)))

    den_E = max(E_hi - E_lo, 1e-6)
    den_C = max(C_hi - C_lo, 1e-6)
    den_K = max(K_hi - K_lo, 1e-6)
    M = 100_000
    obj_terms: list[Any] = []
    for i in range(n):
        cs = float(wells[i]["c_start_i"])
        for t in range(T):
            e = float(wells[i]["e_it"][t])
            g = float(payload.gamma_t[t])
            pt = _price_at_t(payload, t)
            cx = int(round(M * (we * e / den_E + wc * g * e / den_C + wk * pt * e / den_K)))
            obj_terms.append(cx * x[i][t])
            obj_terms.append(int(round(M * wk * cs / den_K)) * y[i][t])
    model.Minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
        return _empty_result(
            n,
            T,
            "约束无可行解（产量、时长、启停次数、负荷上限等组合过紧）",
            diagnostics=_build_diagnostics(payload),
            solver_engine="ortools-cp-sat",
        ) | {"solver_status": solver.StatusName(status)}
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"OR-Tools 未得到可用解，状态={solver.StatusName(status)}")

    sched = [[int(solver.Value(x[i][t])) for t in range(T)] for i in range(n)]
    st = [[int(solver.Value(y[i][t])) for t in range(T)] for i in range(n)]
    return _finalize_result(
        payload,
        sched,
        st,
        solver_status=solver.StatusName(status),
        solver_engine="ortools-cp-sat",
        objective_value_scaled=int(solver.ObjectiveValue()),
        anchors=anchors,
        weights_normalized=weights_normalized,
    )


def _solve_with_pulp(payload: OptimizePayload, anchors: dict[str, tuple[float, float]], weights_normalized: tuple[float, float, float]) -> dict[str, Any]:
    if pulp is None:
        raise RuntimeError("PuLP 不可用")

    wells = payload.wells
    n = len(wells)
    T = len(wells[0]["q_it"]) if n else 0
    we, wc, wk = weights_normalized
    E_lo, E_hi = anchors["energy"]
    C_lo, C_hi = anchors["carbon"]
    K_lo, K_hi = anchors["economic"]

    problem = pulp.LpProblem("well_cluster_schedule", pulp.LpMinimize)
    x = {(i, t): pulp.LpVariable(f"x_{i}_{t}", cat="Binary") for i in range(n) for t in range(T)}
    y = {(i, t): pulp.LpVariable(f"y_{i}_{t}", cat="Binary") for i in range(n) for t in range(T)}

    problem += pulp.lpSum(float(wells[i]["q_it"][t]) * x[(i, t)] for i in range(n) for t in range(T)) >= float(payload.Q_min)

    for i in range(n):
        problem += pulp.lpSum(x[(i, t)] for t in range(T)) >= int(wells[i]["H_min_i"])
        problem += pulp.lpSum(x[(i, t)] for t in range(T)) <= int(wells[i]["H_max_i"])
        problem += y[(i, 0)] == x[(i, 0)]
        for t in range(1, T):
            problem += y[(i, t)] >= x[(i, t)] - x[(i, t - 1)]
            problem += y[(i, t)] <= x[(i, t)]
            problem += y[(i, t)] <= 1 - x[(i, t - 1)]
        problem += pulp.lpSum(y[(i, t)] for t in range(T)) <= int(wells[i]["N_max_i"])

    if payload.hourly_load_cap:
        for t in range(T):
            problem += pulp.lpSum(float(wells[i]["e_it"][t]) * x[(i, t)] for i in range(n)) <= float(payload.hourly_load_cap[t])

    if payload.mutex_pairs:
        for pair in payload.mutex_pairs:
            if len(pair) != 2:
                continue
            i, j = int(pair[0]), int(pair[1])
            if not (0 <= i < n and 0 <= j < n):
                continue
            for tt in range(T):
                problem += x[(i, tt)] + x[(j, tt)] <= 1

    if payload.forbidden_well_hour:
        for pair in payload.forbidden_well_hour:
            if len(pair) != 2:
                continue
            wi, tt = int(pair[0]), int(pair[1])
            if 0 <= wi < n and 0 <= tt < T:
                problem += x[(wi, tt)] == 0

    if payload.storm_limits:
        for pair in payload.storm_limits:
            if len(pair) != 2:
                continue
            tt, mx = int(pair[0]), int(pair[1])
            if 0 <= tt < T and mx >= 0:
                problem += pulp.lpSum(x[(i, tt)] for i in range(n)) <= mx

    if payload.daily_carbon_cap is not None:
        cap = float(payload.daily_carbon_cap)
        problem += (
            pulp.lpSum(float(wells[i]["e_it"][tt]) * float(payload.gamma_t[tt]) * x[(i, tt)] for i in range(n) for tt in range(T))
            <= cap
        )

    den_E = max(E_hi - E_lo, 1e-6)
    den_C = max(C_hi - C_lo, 1e-6)
    den_K = max(K_hi - K_lo, 1e-6)
    objective = []
    for i in range(n):
        start_cost = float(wells[i]["c_start_i"])
        for t in range(T):
            e = float(wells[i]["e_it"][t])
            g = float(payload.gamma_t[t])
            pt = _price_at_t(payload, t)
            objective.append((we * e / den_E + wc * g * e / den_C + wk * pt * e / den_K) * x[(i, t)])
            objective.append((wk * start_cost / den_K) * y[(i, t)])
    problem += pulp.lpSum(objective)

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=5)
    problem.solve(solver)
    status = pulp.LpStatus.get(problem.status, str(problem.status))
    if status != "Optimal":
        if status == "Infeasible":
            return _empty_result(
                n,
                T,
                "约束无可行解（PuLP 校验同样失败）",
                diagnostics=_build_diagnostics(payload),
                solver_engine="pulp-cbc",
            ) | {"solver_status": status}
        raise RuntimeError(f"PuLP 未得到可用解，状态={status}")

    sched = [[int(round(pulp.value(x[(i, t)]) or 0)) for t in range(T)] for i in range(n)]
    st = [[int(round(pulp.value(y[(i, t)]) or 0)) for t in range(T)] for i in range(n)]
    return _finalize_result(
        payload,
        sched,
        st,
        solver_status=status,
        solver_engine="pulp-cbc",
        objective_value_scaled=round(float(pulp.value(problem.objective) or 0.0), 6),
        anchors=anchors,
        weights_normalized=weights_normalized,
    )


def optimize_schedule(payload: OptimizePayload) -> dict[str, Any]:
    wells = payload.wells
    n = len(wells)
    T = len(wells[0]["q_it"]) if n else 0
    diagnostics = _build_diagnostics(payload) if wells else {}

    if not wells:
        return _empty_result(0, 0, "未提供 wells 数据", diagnostics=diagnostics)

    try:
        weights_normalized = normalize_weights(payload.w_energy, payload.w_carbon, payload.w_economic)
    except ValueError as exc:
        return _empty_result(n, T, str(exc), diagnostics=diagnostics)

    if payload.Q_min > diagnostics.get("max_possible_production_if_all_on", 0.0) + 1e-6:
        return _empty_result(
            n,
            T,
            f"Q_min={payload.Q_min:.4f} 超过全开机最大产量 {diagnostics['max_possible_production_if_all_on']:.4f}",
            diagnostics=diagnostics,
        )

    anchors = _anchor_metrics(wells, payload.scenarios, payload.gamma_t, hourly_price=payload.custom_price_t)
    errors: list[str] = []

    try:
        return _solve_with_ortools(payload, anchors, weights_normalized)
    except Exception as exc:
        errors.append(f"OR-Tools: {exc}")

    try:
        return _solve_with_pulp(payload, anchors, weights_normalized)
    except Exception as exc:
        errors.append(f"PuLP: {exc}")

    return _empty_result(
        n,
        T,
        "求解失败，OR-Tools 与 PuLP 均未返回可用结果",
        diagnostics={**diagnostics, "solver_errors": errors},
    )
