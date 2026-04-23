"""规则版结果解释器（不接外部大模型）。"""

from __future__ import annotations

from typing import Any


def _peak_hours_from_scenarios(scenarios: list[dict[str, Any]]) -> set[int]:
    hs: set[int] = set()
    for s in scenarios:
        for h in s.get("peak_hours", []):
            hs.add(int(h))
    return hs


def explain_result(
    optimized: dict[str, Any],
    baseline_results: dict[str, dict[str, Any]],
    sensitivity: dict[str, Any] | None,
    wells: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, Any]:
    peak = _peak_hours_from_scenarios(scenarios)
    n = len(wells)
    T = len(wells[0]["q_it"]) if n else 0
    sched = optimized.get("schedule_matrix") or []
    b_full = baseline_results.get("baseline_full_run", {})
    rule_hits: list[dict[str, Any]] = []

    # 峰段运行强度（按井）
    peak_run_ratio: list[float] = []
    for i in range(n):
        run_peak = sum(1 for t in peak if t < T and sched and sched[i][t])
        denom = max(1, len([t for t in range(T) if t in peak]))
        peak_run_ratio.append(run_peak / denom)

    avg_peak = sum(peak_run_ratio) / max(1, n)
    avoid_peak_wells = [wells[i]["well_id"] for i in range(n) if peak_run_ratio[i] > avg_peak + 0.08]
    if avoid_peak_wells:
        rule_hits.append({"rule": "avoid_peak", "wells": avoid_peak_wells, "message": "这些井在峰时段运行占比较高，适合继续错峰优化。"})
    prefer_continuous: list[str] = []
    start_limited: list[str] = []

    for i in range(n):
        hmin = int(wells[i]["H_min_i"])
        nmax = int(wells[i]["N_max_i"])
        runs = 0
        in_run = False
        max_seg = 0
        seg = 0
        for t in range(T):
            on = sched[i][t] if sched else 0
            if on:
                if not in_run:
                    runs += 1
                    in_run = True
                    seg = 1
                else:
                    seg += 1
            else:
                in_run = False
                max_seg = max(max_seg, seg)
                seg = 0
        max_seg = max(max_seg, seg)
        if max_seg >= max(hmin, 8) and runs <= 2:
            prefer_continuous.append(wells[i]["well_id"])
        if nmax <= 2 and runs >= nmax:
            start_limited.append(wells[i]["well_id"])
    if prefer_continuous:
        rule_hits.append({"rule": "continuous_run", "wells": prefer_continuous, "message": "这些井更适合长段稳定运行。"})
    if start_limited:
        rule_hits.append({"rule": "start_limit", "wells": start_limited, "message": "这些井已经贴近启停上限，避免再做细碎切换。"})

    we, wc, wk = float(weights.get("w_energy", 0)), float(weights.get("w_carbon", 0)), float(weights.get("w_economic", 0))
    dom = max([("能耗", we), ("碳排放", wc), ("期望经济成本", wk)], key=lambda z: z[1])[0]

    # 与基准相比最大收益点
    benefits: list[tuple[str, float]] = []
    if b_full:
        if optimized.get("feasible"):
            e_save = (float(b_full["total_energy"]) - float(optimized["total_energy"])) / max(float(b_full["total_energy"]), 1e-9)
            c_save = (float(b_full["total_carbon"]) - float(optimized["total_carbon"])) / max(float(b_full["total_carbon"]), 1e-9)
            k_save = (float(b_full["expected_economic_cost"]) - float(optimized["expected_economic_cost"])) / max(
                float(b_full["expected_economic_cost"]), 1e-9
            )
            benefits = [("能耗下降", e_save), ("碳排下降", c_save), ("期望成本下降", k_save)]
    benefits.sort(key=lambda x: abs(x[1]), reverse=True)
    top_benefit = benefits[0][0] if benefits else "整体权衡"
    if benefits:
        rule_hits.append({"rule": "top_benefit", "metric": top_benefit, "value": round(benefits[0][1], 6)})

    lines = [
        f"当前加权目标最偏向：{dom}。",
        f"与“全时运行”基准相比，最显著的相对变化维度为：{top_benefit}。",
    ]
    if avoid_peak_wells:
        lines.append("建议在峰段减少开机或错峰的井：" + "、".join(avoid_peak_wells) + "。")
    if prefer_continuous:
        lines.append("更适合保持连续稳定运行的井：" + "、".join(prefer_continuous) + "。")
    if start_limited:
        lines.append("启停次数约束偏紧、需要重点盯防频繁启停的井：" + "、".join(start_limited) + "。")
    if not optimized.get("feasible"):
        lines.insert(0, f"本次优化无可行解：{optimized.get('infeasible_reason') or '请放宽约束后重试'}。")
        diag = optimized.get("diagnostics") or {}
        if diag.get("requested_Q_min") and diag.get("max_possible_production_if_all_on"):
            lines.append(
                f"当前 Q_min={diag['requested_Q_min']}，而全开机理论最大产量约为 {diag['max_possible_production_if_all_on']}。"
            )

    mgmt = "调度建议：优先在峰段安排低耗电井或已处于连续运行段的井保供，高耗电井尽量外移；启停受限井避免细碎开停；根据当日最敏感目标（能耗/碳/成本）微调权重后再求解。"

    summary = lines[0] + lines[1] if len(lines) >= 2 else (lines[0] if lines else mgmt)

    return {
        "dominant_objective": dom,
        "wells_suggested_avoid_peak": avoid_peak_wells,
        "wells_better_continuous": prefer_continuous,
        "wells_start_stop_limited": start_limited,
        "largest_benefit_vs_full_run": top_benefit,
        "rule_hits": rule_hits,
        "paragraphs": lines + [mgmt],
        "management_briefing": mgmt,
        "summary_one_line": summary,
        "sensitivity_note": "已结合敏感性扫描结果观察权重对指标的影响。" if sensitivity else None,
    }
