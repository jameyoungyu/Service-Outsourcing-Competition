"""Collinearity diagnostics and redundancy recommendations for MISO inputs.

Strongly correlated inputs do not bias the ARX fit, they inflate its variance: the normal
equations become ill-conditioned and the coefficients get large, opposing and unstable, so
the steady-state gains an engineer reads off the model become nonsense even when the
prediction error looks fine. That is why this stage reports the condition number and VIF
alongside plain correlation — correlation catches pairs, VIF and the condition number
catch the multi-variable case where no single pair looks alarming.

Recommendations are advisory. Nothing is dropped without confirmation, because which of
two collinear tags is the physically meaningful one is a process question, not a
statistical one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.regressor import FloatArray, IdentifiabilityError


@dataclass(frozen=True)
class CorrelatedPair:
    """Two inputs whose correlation exceeds the alarm threshold."""

    left: str
    right: str
    pearson: float
    spearman: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "pearson": self.pearson,
            "spearman": self.spearman,
        }


@dataclass(frozen=True)
class CollinearityAdvice:
    """One advisory action for one variable."""

    variable: str
    action: str
    reason: str
    related_variables: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "action": self.action,
            "reason": self.reason,
            "related_variables": list(self.related_variables),
        }


@dataclass(frozen=True)
class CollinearityResult:
    """Full diagnostic bundle for the report and the variable-selection stage."""

    variables: tuple[str, ...]
    pearson: tuple[tuple[float, ...], ...]
    spearman: tuple[tuple[float, ...], ...]
    vif: dict[str, float]
    condition_number: float
    correlated_pairs: tuple[CorrelatedPair, ...]
    groups: tuple[tuple[str, ...], ...]
    advice: tuple[CollinearityAdvice, ...]
    thresholds: dict[str, float]

    def to_payload(self) -> dict[str, Any]:
        return {
            "variables": list(self.variables),
            "pearson": [list(row) for row in self.pearson],
            "spearman": [list(row) for row in self.spearman],
            "vif": dict(self.vif),
            "condition_number": self.condition_number,
            "correlated_pairs": [pair.to_payload() for pair in self.correlated_pairs],
            "groups": [list(group) for group in self.groups],
            "advice": [item.to_payload() for item in self.advice],
            "thresholds": dict(self.thresholds),
        }


def correlation_matrix(
    columns: tuple[str, ...],
    values: Mapping[str, FloatArray],
    *,
    rank_based: bool = False,
) -> tuple[tuple[float, ...], ...]:
    """Pearson, or Spearman when ``rank_based``. Non-finite samples are dropped pairwise."""

    size = len(columns)
    matrix = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(i, size):
            left = np.asarray(values[columns[i]], dtype=float)
            right = np.asarray(values[columns[j]], dtype=float)
            finite = np.isfinite(left) & np.isfinite(right)
            if int(np.count_nonzero(finite)) < 3:
                value = 0.0
            else:
                a = left[finite]
                b = right[finite]
                if rank_based:
                    a = _rank(a)
                    b = _rank(b)
                value = _pearson(a, b)
            matrix[i][j] = value
            matrix[j][i] = value
    return tuple(tuple(row) for row in matrix)


def variance_inflation_factors(
    columns: tuple[str, ...],
    values: Mapping[str, FloatArray],
) -> dict[str, float]:
    """``VIF_j = 1 / (1 - R_j^2)`` from regressing each input on all the others."""

    if len(columns) < 2:
        return dict.fromkeys(columns, 1.0)
    stacked, kept = _finite_matrix(columns, values)
    if stacked.shape[0] <= len(kept):
        return dict.fromkeys(columns, float("inf"))

    factors: dict[str, float] = {}
    for position, column in enumerate(kept):
        target = stacked[:, position]
        others = np.delete(stacked, position, axis=1)
        design = np.column_stack([np.ones(others.shape[0]), others])
        try:
            coefficients, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        except np.linalg.LinAlgError:
            factors[column] = float("inf")
            continue
        residual = target - design @ coefficients
        centered = target - float(np.mean(target))
        total = float(np.dot(centered, centered))
        if total <= 0:
            factors[column] = float("inf")
            continue
        r_squared = 1.0 - float(np.dot(residual, residual)) / total
        factors[column] = float("inf") if r_squared >= 1.0 else float(1.0 / (1.0 - r_squared))
    for column in columns:
        factors.setdefault(column, float("nan"))
    return factors


def design_condition_number(
    columns: tuple[str, ...],
    values: Mapping[str, FloatArray],
) -> float:
    """Condition number of the standardised input matrix.

    Standardising first matters: without it the number reports the unit mismatch between a
    flow in t/h and a temperature in degrees, not the collinearity we are diagnosing.
    """

    stacked, kept = _finite_matrix(columns, values)
    if stacked.size == 0 or not kept:
        return float("inf")
    scaled = np.empty_like(stacked)
    for position in range(stacked.shape[1]):
        column = stacked[:, position]
        spread = float(np.std(column))
        scaled[:, position] = (column - float(np.mean(column))) / (spread if spread > 0 else 1.0)
    singular = np.linalg.svd(scaled, compute_uv=False)
    if singular.size == 0 or float(singular[-1]) <= 0:
        return float("inf")
    return float(singular[0] / singular[-1])


def analyze_collinearity(
    *,
    inputs: Mapping[str, FloatArray],
    correlation_threshold: float = 0.90,
    vif_threshold: float = 10.0,
    condition_threshold: float = 30.0,
) -> CollinearityResult:
    """Compute every diagnostic and turn the alarms into advisory actions."""

    columns = tuple(inputs)
    if len(columns) < 2:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "共线性分析至少需要两个输入变量",
            {"input_columns": list(columns)},
        )
    if not 0 < correlation_threshold <= 1:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "correlation_threshold 必须位于 (0,1]",
            {"correlation_threshold": correlation_threshold},
        )

    pearson = correlation_matrix(columns, inputs)
    spearman = correlation_matrix(columns, inputs, rank_based=True)
    vif = variance_inflation_factors(columns, inputs)
    condition = design_condition_number(columns, inputs)

    pairs = tuple(
        CorrelatedPair(
            left=columns[i],
            right=columns[j],
            pearson=pearson[i][j],
            spearman=spearman[i][j],
        )
        for i in range(len(columns))
        for j in range(i + 1, len(columns))
        if abs(pearson[i][j]) >= correlation_threshold
    )
    groups = _correlation_groups(columns, pearson, correlation_threshold)
    advice = _build_advice(
        columns=columns,
        groups=groups,
        vif=vif,
        inputs=inputs,
        vif_threshold=vif_threshold,
        condition=condition,
        condition_threshold=condition_threshold,
    )
    return CollinearityResult(
        variables=columns,
        pearson=pearson,
        spearman=spearman,
        vif=vif,
        condition_number=condition,
        correlated_pairs=pairs,
        groups=groups,
        advice=advice,
        thresholds={
            "correlation_threshold": correlation_threshold,
            "vif_threshold": vif_threshold,
            "condition_threshold": condition_threshold,
        },
    )


def _build_advice(
    *,
    columns: tuple[str, ...],
    groups: tuple[tuple[str, ...], ...],
    vif: Mapping[str, float],
    inputs: Mapping[str, FloatArray],
    vif_threshold: float,
    condition: float,
    condition_threshold: float,
) -> tuple[CollinearityAdvice, ...]:
    advice: list[CollinearityAdvice] = []
    grouped: set[str] = set()
    for group in groups:
        grouped.update(group)
        # Keep the member with the most usable samples; ties go to the lower VIF.
        ranked = sorted(
            group,
            key=lambda name: (
                -int(np.count_nonzero(np.isfinite(np.asarray(inputs[name], dtype=float)))),
                _safe_vif(vif.get(name)),
            ),
        )
        keeper = ranked[0]
        advice.append(
            CollinearityAdvice(
                variable=keeper,
                action="keep",
                reason=(
                    f"与 {', '.join(name for name in group if name != keeper)} 高度相关，"
                    "该变量有效样本最多，建议保留为代表变量。"
                ),
                related_variables=tuple(name for name in group if name != keeper),
            )
        )
        for name in ranked[1:]:
            advice.append(
                CollinearityAdvice(
                    variable=name,
                    action="drop",
                    reason=f"与代表变量 {keeper} 高度相关，建议在人工确认后剔除以改善条件数。",
                    related_variables=(keeper,),
                )
            )
    for column in columns:
        if column in grouped:
            continue
        factor = vif.get(column, float("nan"))
        if np.isfinite(factor) and factor >= vif_threshold:
            advice.append(
                CollinearityAdvice(
                    variable=column,
                    action="review",
                    reason=(
                        f"两两相关未超阈值，但 VIF={factor:.2f} 已超过 {vif_threshold:.1f}，"
                        "说明存在多变量共线，需要人工复核。"
                    ),
                    related_variables=(),
                )
            )
        else:
            advice.append(
                CollinearityAdvice(
                    variable=column,
                    action="keep",
                    reason="相关性与 VIF 均在阈值内。",
                    related_variables=(),
                )
            )
    if np.isfinite(condition) and condition >= condition_threshold and not groups:
        advice.append(
            CollinearityAdvice(
                variable="__design__",
                action="review",
                reason=(
                    f"设计矩阵条件数 {condition:.1f} 超过 {condition_threshold:.1f}，"
                    "建议改用岭回归或补充激励试验。"
                ),
                related_variables=tuple(columns),
            )
        )
    return tuple(advice)


def _correlation_groups(
    columns: tuple[str, ...],
    matrix: tuple[tuple[float, ...], ...],
    threshold: float,
) -> tuple[tuple[str, ...], ...]:
    """Union-find over the "correlated above threshold" relation."""

    parent = list(range(len(columns)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            if abs(matrix[i][j]) >= threshold:
                left, right = find(i), find(j)
                if left != right:
                    parent[right] = left

    buckets: dict[int, list[str]] = {}
    for index, column in enumerate(columns):
        buckets.setdefault(find(index), []).append(column)
    return tuple(tuple(group) for group in buckets.values() if len(group) > 1)


def _finite_matrix(
    columns: tuple[str, ...],
    values: Mapping[str, FloatArray],
) -> tuple[np.ndarray, list[str]]:
    kept = [column for column in columns if column in values]
    if not kept:
        return np.zeros((0, 0)), []
    stacked = np.column_stack([np.asarray(values[column], dtype=float) for column in kept])
    finite = np.all(np.isfinite(stacked), axis=1)
    return stacked[finite], kept


def _pearson(left: np.ndarray, right: np.ndarray) -> float:
    a = left - float(np.mean(left))
    b = right - float(np.mean(right))
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))


def _rank(values: np.ndarray) -> np.ndarray:
    """Average ranks, so tied values do not fabricate an ordering."""

    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    unique, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    if unique.size != values.size:
        sums = np.zeros(unique.size, dtype=float)
        np.add.at(sums, inverse, ranks)
        ranks = (sums / counts)[inverse]
    return ranks


def _safe_vif(value: float | None) -> float:
    if value is None or not np.isfinite(value):
        return float("inf")
    return float(value)
