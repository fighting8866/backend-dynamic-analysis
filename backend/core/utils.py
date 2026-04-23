"""通用数值与校验工具。"""

from __future__ import annotations

from typing import Iterable


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0 or den is None:
        return default
    return num / den


def normalize_weights(w_energy: float, w_carbon: float, w_economic: float) -> tuple[float, float, float]:
    s = float(w_energy) + float(w_carbon) + float(w_economic)
    if s <= 0:
        raise ValueError("权重之和必须大于 0")
    return w_energy / s, w_carbon / s, w_economic / s


def min_max_normalize(value: float, vmin: float, vmax: float, eps: float = 1e-9) -> float:
    """线性缩放到 [0,1]，vmin 映射为 0，vmax 映射为 1（均为最小化方向下的锚点）。"""
    span = vmax - vmin
    if abs(span) < eps:
        return 0.5
    return clamp((value - vmin) / span, 0.0, 1.0)


def rate_improvement(baseline: float, optimized: float, *, higher_is_better: bool = False) -> float:
    """相对变化率：(基线 - 优化)/基线，表示“改善比例”。能耗/碳/成本默认越小越好。"""
    if baseline == 0:
        return 0.0
    if higher_is_better:
        return (optimized - baseline) / baseline
    return (baseline - optimized) / baseline


def flatten_matrix(mat: list[list[float]]) -> list[float]:
    out: list[float] = []
    for row in mat:
        out.extend(row)
    return out


def sum_2d(mat: Iterable[Iterable[float]]) -> float:
    return sum(sum(row) for row in mat)
