"""队友单页 HTML（6 井 × 24 时 + 分时电价/互斥/夜间/风暴/碳上限）→ 后端 OR-Tools 三方案自动优化。"""

from __future__ import annotations

from typing import Any

from . import baseline
from .optimizer import OptimizePayload, optimize_schedule
from .schemas import AutoOptimizeRequest, NUM_SLOTS, PageAdvancedParams, WellPageRow


def _clock_to_index(h: int) -> int:
    h = int(h)
    if 1 <= h <= 24:
        return h - 1
    return max(0, min(23, h))


def _build_hourly_prices(adv: dict[str, Any]) -> list[float]:
    peak_set = {_clock_to_index(h) for h in adv["peak_hours_clock"]}
    flat_set = {_clock_to_index(h) for h in adv["flat_hours_clock"]}
    out: list[float] = []
    for t in range(NUM_SLOTS):
        if t in peak_set:
            out.append(float(adv["peak_price"]))
        elif t in flat_set:
            out.append(float(adv["flat_price"]))
        else:
            out.append(float(adv["valley_price"]))
    return out


def _rows_to_internal_wells(rows: list[WellPageRow], n_max: int) -> list[dict[str, Any]]:
    internal: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        wid = row.well_id
        if not wid and row.id is not None:
            wid = f"W{int(row.id):02d}"
        if not wid:
            wid = f"W{idx + 1:02d}"
        qr = float(row.q_rate)
        pr = float(row.P_rated)
        internal.append(
            {
                "well_id": wid,
                "name": wid,
                "q_it": [qr] * NUM_SLOTS,
                "e_it": [pr] * NUM_SLOTS,
                "c_start_i": float(row.c_start),
                "H_min_i": int(row.H_min),
                "H_max_i": int(row.H_max),
                "N_max_i": int(n_max),
            }
        )
    return internal


def _build_extra_constraints(adv: dict[str, Any], n_wells: int) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    mutex: list[list[int]] = []
    for pair in adv["mutex_pairs_clock"]:
        if len(pair) != 2:
            continue
        a, b = int(pair[0]) - 1, int(pair[1]) - 1
        if 0 <= a < n_wells and 0 <= b < n_wells:
            mutex.append([a, b])

    forbidden: list[list[int]] = []
    for w1 in adv["noisy_wells_clock"]:
        wi = int(w1) - 1
        if not (0 <= wi < n_wells):
            continue
        for h in adv["night_hours_clock"]:
            forbidden.append([wi, _clock_to_index(h)])

    storm: list[list[int]] = []
    for h in adv["storm_hours_clock"]:
        storm.append([_clock_to_index(h), int(adv["max_running_during_storm"])])
    return mutex, forbidden, storm


def _count_startups(startup: list[list[int]]) -> int:
    return int(sum(sum(row) for row in startup))


def _kpis(res: dict[str, Any], oil_price: float) -> dict[str, Any]:
    if not res.get("feasible"):
        return {"feasible": False}
    oil = float(res["total_production"])
    revenue = float(oil_price) * oil
    cost = float(res["expected_economic_cost"])
    profit = revenue - cost
    return {
        "feasible": True,
        "total_energy": float(res["total_energy"]),
        "total_carbon": float(res["total_carbon"]),
        "total_oil": oil,
        "electricity_and_startup_cost": cost,
        "oil_revenue": revenue,
        "profit": profit,
        "total_startups": _count_startups(res.get("startup_matrix") or []),
        "peak_load_kw": max(res.get("hourly_load") or [0.0]) if res.get("hourly_load") else 0.0,
    }


def _placeholder_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": "tariff_placeholder",
            "label": "占位（真实电价由 custom_price_t 驱动）",
            "p_s": 1.0,
            "peak_price": 1.0,
            "offpeak_price": 0.0,
            "peak_hours": [],
        }
    ]


def _build_page_style_charts(
    profiles: dict[str, dict[str, Any]],
    well_ids: list[str],
    hourly_price: list[float],
    internal_wells: list[dict[str, Any]],
    oil_price: float,
    gamma_t: list[float],
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    hours = [f"{h}:00" for h in range(NUM_SLOTS)]
    load_series: list[dict[str, Any]] = []
    name_map = {"energy_first": "节能优先", "benefit_first": "效益最高", "balanced": "平衡方案"}
    for key, zh in name_map.items():
        r = profiles[key]["result"]
        if r.get("feasible") and r.get("hourly_load"):
            load_series.append({"name": zh, "type": "line", "smooth": True, "data": [float(x) for x in r["hourly_load"]]})

    balanced = profiles.get("balanced", {}).get("result") or {}
    sched = balanced.get("schedule_matrix") or []
    heat_data: list[list[int]] = []
    for t in range(NUM_SLOTS):
        for i in range(len(well_ids)):
            v = int(sched[i][t]) if i < len(sched) and t < len(sched[i]) else 0
            heat_data.append([t, i, v])

    vals_energy: list[float] = []
    vals_profit: list[float] = []
    vals_oil: list[float] = []
    vals_start: list[float] = []
    for key in ("energy_first", "benefit_first", "balanced"):
        k = profiles[key].get("kpis") or {}
        if not k.get("feasible"):
            vals_energy.append(0.0)
            vals_profit.append(0.0)
            vals_oil.append(0.0)
            vals_start.append(0.0)
        else:
            vals_energy.append(float(k["total_energy"]))
            vals_profit.append(abs(float(k["profit"])))
            vals_oil.append(float(k["total_oil"]))
            vals_start.append(float(k["total_startups"]))
    max_energy = max(vals_energy + [1.0])
    max_profit = max(vals_profit + [1.0])
    max_oil = max(vals_oil + [1.0])
    max_start = max(vals_start + [1.0])

    radar_series: list[dict[str, Any]] = []
    colors = {"energy_first": "#00d9ff", "benefit_first": "#00ff88", "balanced": "#ffd700"}
    for key, zh in name_map.items():
        k = profiles[key].get("kpis") or {}
        if k.get("feasible"):
            radar_series.append(
                {
                    "name": zh,
                    "value": [
                        k["total_energy"],
                        abs(k["profit"]),
                        k["total_oil"],
                        k["total_startups"],
                    ],
                    "lineStyle": {"color": colors[key]},
                }
            )

    b_full = baseline.package_baseline(
        "baseline_full_run",
        internal_wells,
        scenarios,
        gamma_t,
        hourly_electricity_price=hourly_price,
    )
    bar_series: list[dict[str, Any]] = []
    for key, zh in name_map.items():
        r = profiles[key]["result"]
        k = profiles[key].get("kpis") or {}
        if r.get("feasible") and k.get("feasible"):
            e_save = float(b_full["total_energy"]) - float(r["total_energy"])
            cost_save = float(b_full["expected_economic_cost"]) - float(r["expected_economic_cost"])
            carb_save = float(b_full["total_carbon"]) - float(r["total_carbon"])
            bar_series.append(
                {
                    "name": zh,
                    "type": "bar",
                    "data": [round(e_save, 4), round(cost_save, 4), round(carb_save, 4), round(k["profit"], 4)],
                }
            )

    return {
        "load_curve": {"categories": hours, "series": load_series},
        "heatmap_balanced": {"x_axis_hours": hours, "y_axis_wells": well_ids, "data": heat_data},
        "radar": {
            "indicators": [
                {"name": "能耗(低好)", "max": max_energy},
                {"name": "利润(高好)", "max": max_profit},
                {"name": "产量(高好)", "max": max_oil},
                {"name": "启停(少好)", "max": max_start},
            ],
            "series": radar_series,
        },
        "basic_comparison_style": {
            "categories": ["节电量(kWh)", "电费节省(元)", "碳减排(等量比)", "净收益(元)"],
            "series": bar_series,
        },
    }


def run_page_auto_optimize(req: AutoOptimizeRequest) -> dict[str, Any]:
    adv_obj = req.advanced or PageAdvancedParams()
    adv = adv_obj.model_dump()
    internal = _rows_to_internal_wells(req.wells, adv["N_max_startups_default"])
    n = len(internal)
    prices = _build_hourly_prices(adv)
    mutex, forbidden, storm = _build_extra_constraints(adv, n)
    scenarios = _placeholder_scenarios()
    gamma_t = [float(adv["gamma"])] * NUM_SLOTS

    profiles_cfg = [
        ("energy_first", 0.8, 0.1, 0.1),
        ("benefit_first", 0.1, 0.1, 0.8),
        ("balanced", 0.4, 0.3, 0.3),
    ]
    profiles: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    for key, we, wc, wk in profiles_cfg:
        payload = OptimizePayload(
            wells=internal,
            scenarios=scenarios,
            gamma_t=gamma_t,
            w_energy=we,
            w_carbon=wc,
            w_economic=wk,
            Q_min=float(adv["Q_min"]),
            hourly_load_cap=[float(adv["P_max"])] * NUM_SLOTS,
            custom_price_t=prices,
            daily_carbon_cap=float(adv["daily_carbon_limit"]),
            mutex_pairs=mutex or None,
            forbidden_well_hour=forbidden or None,
            storm_limits=storm or None,
        )
        res = optimize_schedule(payload)
        kpis = _kpis(res, float(adv["oil_price"]))
        profiles[key] = {
            "weights": {"w_energy": we, "w_carbon": wc, "w_economic": wk},
            "result": res,
            "kpis": kpis,
        }
        if not res.get("feasible"):
            notes.append(f"{key}: {res.get('infeasible_reason') or '无可行解'}")

    well_ids = [w["well_id"] for w in internal]
    charts = _build_page_style_charts(profiles, well_ids, prices, internal, float(adv["oil_price"]), gamma_t, scenarios)

    best_key = None
    best_profit = float("-inf")
    for key in ("energy_first", "benefit_first", "balanced"):
        k = profiles[key].get("kpis") or {}
        if k.get("feasible") and float(k.get("profit", -1e30)) > best_profit:
            best_profit = float(k["profit"])
            best_key = key

    return {
        "mode": "page_auto_triple",
        "advanced_params_normalized": adv,
        "wells_internal": internal,
        "hourly_electricity_price": prices,
        "profiles": profiles,
        "recommended_profile": best_key,
        "charts_payload_page": charts,
        "notes": notes,
    }
