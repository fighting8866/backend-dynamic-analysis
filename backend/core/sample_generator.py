"""可复现的 demo 井群与电价情景数据生成（固定随机种子）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEMO_SEED = 20250423
NUM_WELLS = 10
NUM_SLOTS = 24

# 峰段：白天高负荷电价敏感时段（可按需调整）
PEAK_HOURS = list(range(9, 16))  # 9-15


def _smooth_series(base: float, amplitude: float, phase: float, t: int) -> float:
    import math

    return base + amplitude * math.sin(2 * math.pi * (t + phase) / 24.0)


def generate_wells_demo(rng: Any) -> list[dict[str, Any]]:
    wells: list[dict[str, Any]] = []
    for i in range(NUM_WELLS):
        # 井型差异：高产井耗电略高，低产井更“轻”
        q_base = 12.0 + i * 1.1 + rng.uniform(-0.4, 0.4)
        e_base = 35.0 + i * 2.2 + rng.uniform(-1.5, 1.5)
        q_it: list[float] = []
        e_it: list[float] = []
        for t in range(NUM_SLOTS):
            # 日内波动：产量/耗电随泵效与液面波动缓慢变化
            q = max(2.0, _smooth_series(q_base, 1.2 + 0.05 * i, i * 0.7, t) + rng.uniform(-0.35, 0.35))
            e = max(8.0, _smooth_series(e_base, 4.0 + 0.2 * i, i * 0.4, t) + rng.uniform(-1.0, 1.0))
            q_it.append(round(q, 3))
            e_it.append(round(e, 3))

        c_start = round(180.0 + i * 22.0 + rng.uniform(0, 40), 2)
        # 约束：高耗电井允许略少连续运行，高产井要求更长连续段
        h_min = 6 + (i % 3)
        h_max = 20 - (i % 4)
        if h_max <= h_min:
            h_max = h_min + 4
        n_max = 2 + (i % 3)

        wells.append(
            {
                "well_id": f"W{i+1:02d}",
                "name": f"井区-{i+1}号抽油机",
                "q_it": q_it,
                "e_it": e_it,
                "c_start_i": c_start,
                "H_min_i": h_min,
                "H_max_i": h_max,
                "N_max_i": n_max,
            }
        )
    return wells


def generate_gamma_t(rng: Any) -> list[float]:
    """分时段碳排因子（与电网/自备电组合相关的简化曲线）。"""
    import math

    gamma: list[float] = []
    for t in range(NUM_SLOTS):
        # 白天因子略高（外购电结构假设）
        base = 0.42 + 0.06 * math.sin(2 * math.pi * (t - 6) / 24.0)
        gamma.append(round(max(0.25, base + rng.uniform(-0.02, 0.02)), 4))
    return gamma


def generate_scenarios_demo(rng: Any) -> list[dict[str, Any]]:
    """三情景：峰时电价随机，非峰固定；概率和为 1。"""
    offpeak = round(0.38 + rng.uniform(-0.01, 0.01), 4)
    scenarios = [
        {
            "id": "low",
            "label": "低峰价情景",
            "p_s": 0.35,
            "peak_price": round(0.72 + rng.uniform(-0.02, 0.02), 4),
            "offpeak_price": offpeak,
            "peak_hours": PEAK_HOURS,
        },
        {
            "id": "mid",
            "label": "中峰价情景",
            "p_s": 0.45,
            "peak_price": round(0.95 + rng.uniform(-0.02, 0.02), 4),
            "offpeak_price": offpeak,
            "peak_hours": PEAK_HOURS,
        },
        {
            "id": "high",
            "label": "高峰价情景",
            "p_s": 0.20,
            "peak_price": round(1.28 + rng.uniform(-0.02, 0.02), 4),
            "offpeak_price": offpeak,
            "peak_hours": PEAK_HOURS,
        },
    ]
    psum = sum(float(s["p_s"]) for s in scenarios)
    for s in scenarios:
        s["p_s"] = round(float(s["p_s"]) / psum, 4)
    diff = 1.0 - sum(float(s["p_s"]) for s in scenarios)
    scenarios[-1]["p_s"] = round(float(scenarios[-1]["p_s"]) + diff, 4)
    return scenarios


def build_demo_bundle() -> dict[str, Any]:
    import random

    rng = random.Random(DEMO_SEED)
    wells = generate_wells_demo(rng)
    scenarios = generate_scenarios_demo(rng)
    gamma_t = generate_gamma_t(rng)
    full_run_production = sum(float(w["q_it"][t]) for w in wells for t in range(NUM_SLOTS))
    recommended_q_min = round(full_run_production * 0.62, 4)
    run_request_example = {
        "wells": wells,
        "scenarios": scenarios,
        "gamma_t": gamma_t,
        "weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
        "Q_min": recommended_q_min,
        "optional_constraints": None,
        "baseline_compare": "both",
    }
    return {
        "meta": {
            "seed": DEMO_SEED,
            "num_wells": NUM_WELLS,
            "num_slots": NUM_SLOTS,
            "peak_hours": PEAK_HOURS,
        },
        "wells": wells,
        "scenarios": scenarios,
        "gamma_t": gamma_t,
        "recommended_weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
        "recommended_Q_min": recommended_q_min,
        "request_template": {
            "weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
            "Q_min": recommended_q_min,
            "optional_constraints": None,
        },
        "run_request_example": run_request_example,
    }


def _write_wells_csv(data_dir: Path, wells: list[dict[str, Any]]) -> None:
    import csv

    p = data_dir / "wells_demo_hourly.csv"
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["well_id", "hour", "q_it", "e_it"])
        for well in wells:
            wid = well["well_id"]
            for t in range(NUM_SLOTS):
                w.writerow([wid, t, well["q_it"][t], well["e_it"][t]])


def ensure_demo_files(data_dir: Path) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_demo_bundle()
    wells_path = data_dir / "wells_demo.json"
    scen_path = data_dir / "scenarios_demo.json"
    wells_path.write_text(json.dumps({"wells": bundle["wells"], "gamma_t": bundle["gamma_t"], "meta": bundle["meta"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    scen_path.write_text(json.dumps({"scenarios": bundle["scenarios"], "meta": bundle["meta"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_wells_csv(data_dir, bundle["wells"])
    hist = data_dir / "history.json"
    if not hist.exists():
        hist.write_text(json.dumps({"records": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def load_bundle_from_disk(data_dir: Path) -> dict[str, Any]:
    wells_path = data_dir / "wells_demo.json"
    scen_path = data_dir / "scenarios_demo.json"
    wells_obj = json.loads(wells_path.read_text(encoding="utf-8"))
    scen_obj = json.loads(scen_path.read_text(encoding="utf-8"))
    qmin = round(sum(float(w["q_it"][t]) for w in wells_obj["wells"] for t in range(NUM_SLOTS)) * 0.62, 4)
    return {
        "meta": wells_obj.get("meta", {}),
        "wells": wells_obj["wells"],
        "scenarios": scen_obj["scenarios"],
        "gamma_t": wells_obj["gamma_t"],
        "recommended_weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
        "recommended_Q_min": qmin,
        "request_template": {
            "weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
            "Q_min": qmin,
            "optional_constraints": None,
        },
        "run_request_example": {
            "wells": wells_obj["wells"],
            "scenarios": scen_obj["scenarios"],
            "gamma_t": wells_obj["gamma_t"],
            "weights": {"w_energy": 0.34, "w_carbon": 0.33, "w_economic": 0.33},
            "Q_min": qmin,
            "optional_constraints": None,
            "baseline_compare": "both",
        },
    }
