"""The conventional weighted quality score, implemented properly as a comparison baseline.

``ALG-0.1`` §6.2 specified a weighted sum of input energy, output energy, SNR, response
association and duration, minus penalties for anomalies, missing data and steady state.
That is what most implementations of this task will use, and comparing D-optimal selection
only against raw input energy would be comparing against a straw man.

So the full score is implemented here at its stated weights, and the ablation runs it as a
third strategy. Two things came out of actually measuring it, one of them not what this
docstring originally predicted:

* On heterogeneous excitation (``S6``) it fails *identically* to raw input energy —
  14.81 ± 0.06 % parameter error versus energy's 14.82 ± 0.07 % over 10 seeds, both
  rank-deficient. The extra components do not rescue it, because **each window is scored in
  isolation**: nothing in the formula can express "this window teaches the model the same
  thing the last one already did". Redundancy is invisible to it by construction.
* It is also not a *stronger* baseline than energy on clean synthetic data, which is what
  was expected. The reason is visible in the component dump: on windows with real
  excitation, ``input_energy``, ``output_energy`` and ``snr`` all saturate together, so a
  weighted sum of them re-ranks by very nearly the same quantity. The penalty terms that
  would separate it — anomaly and missing ratio — are zero on uncontaminated records.

Where it *does* win is the homogeneous, clean case (``S3`` through the product benchmark:
3.75 % versus D-optimal's 4.80 %), which is recorded in ``EXP-2.1`` rather than hidden. When
every dynamic window carries the same information, ranking by quality is the right thing to
do and modelling redundancy buys nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.gating import estimate_noise_sigma, hampel_anomaly_mask
from algorithms.identifiability.regressor import FloatArray, IdentifiabilityError, RegressorMatrix
from algorithms.identifiability.selection import WindowGrid

# Weights frozen in ALG-0.1 §6.2. Reproduced verbatim so the comparison is against the
# specification as written, not against a version tuned to lose.
WEIGHTS: dict[str, float] = {
    "input_energy": 0.25,
    "output_energy": 0.20,
    "snr": 0.20,
    "response_association": 0.20,
    "duration": 0.15,
    "anomaly_ratio": -0.25,
    "missing_ratio": -0.20,
    "steady_state": -0.20,
    "short_segment": -0.10,
}


@dataclass(frozen=True)
class WindowScore:
    """One window's weighted score and every component behind it."""

    window_index: int
    score: float
    components: dict[str, float]

    def to_payload(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "score": self.score,
            "components": dict(self.components),
        }


def score_windows(
    regressor: RegressorMatrix,
    grid: WindowGrid,
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    min_segment_length: int = 30,
) -> list[WindowScore]:
    """Score every candidate window with the full weighted formula.

    Components are normalised to ``[0, 1]`` across the candidate set using robust
    percentiles, which is what makes a weighted sum of quantities in different units
    meaningful at all.
    """

    if grid.count == 0:
        raise IdentifiabilityError("NO_DYNAMIC_SEGMENT_FOUND", "候选窗口为空，无法评分")

    measured = np.asarray(output, dtype=float)
    signals = {name: np.asarray(values, dtype=float) for name, values in inputs.items()}
    noise_sigma = estimate_noise_sigma(measured)
    rows = np.asarray(regressor.time_indices, dtype=int)
    # Hampel is a whole-signal operation; computing it once per channel instead of once
    # per channel per window keeps the baseline cheap enough to be a fair comparison.
    anomaly_masks = [hampel_anomaly_mask(values) for values in (*signals.values(), measured)]

    raw: list[dict[str, float]] = []
    for positions in grid.positions:
        samples = rows[np.asarray(positions, dtype=int)]
        raw.append(
            {
                "input_energy": _input_energy(signals, samples),
                "output_energy": _output_energy(measured, samples),
                "snr": _snr(measured, samples, noise_sigma),
                "response_association": _response_association(signals, measured, samples),
                "duration": float(samples.size),
                "anomaly_ratio": _anomaly_ratio(anomaly_masks, samples),
                "missing_ratio": _missing_ratio(signals, measured, samples),
                "short_segment": 1.0 if samples.size < min_segment_length else 0.0,
            }
        )

    normalised = {
        key: _normalise([item[key] for item in raw])
        for key in ("input_energy", "output_energy", "snr", "response_association", "duration")
    }
    # Steady state is the complement of input activity: a window that barely moves is
    # penalised in proportion to how little it moves.
    steady = [1.0 - value for value in normalised["input_energy"]]

    scored: list[WindowScore] = []
    for index, item in enumerate(raw):
        components = {
            "input_energy": normalised["input_energy"][index],
            "output_energy": normalised["output_energy"][index],
            "snr": normalised["snr"][index],
            "response_association": normalised["response_association"][index],
            "duration": normalised["duration"][index],
            "anomaly_ratio": item["anomaly_ratio"],
            "missing_ratio": item["missing_ratio"],
            "steady_state": steady[index],
            "short_segment": item["short_segment"],
        }
        score = sum(WEIGHTS[key] * value for key, value in components.items())
        scored.append(WindowScore(window_index=index, score=float(score), components=components))
    return scored


def select_by_weighted_score(
    regressor: RegressorMatrix,
    grid: WindowGrid,
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    budget_windows: int,
) -> np.ndarray:
    """Take the top-scoring windows. Row positions, deduplicated, like the other selectors."""

    if budget_windows < 1:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE", "budget_windows 必须大于等于 1", {"budget": budget_windows}
        )
    scored = score_windows(regressor, grid, inputs=inputs, output=output)
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    chosen = ranked[: min(budget_windows, grid.count)]
    return np.unique(np.concatenate([grid.positions[item.window_index] for item in chosen]))


def _normalise(values: list[float]) -> list[float]:
    """Robust min-max to [0,1] using the 5th and 95th percentiles."""

    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return [0.0] * len(values)
    low = float(np.percentile(finite, 5))
    high = float(np.percentile(finite, 95))
    if high <= low:
        return [0.0 if not np.isfinite(value) else 0.5 for value in values]
    return [
        0.0 if not np.isfinite(value) else float(np.clip((value - low) / (high - low), 0.0, 1.0))
        for value in values
    ]


def _input_energy(signals: Mapping[str, FloatArray], samples: np.ndarray) -> float:
    total = 0.0
    for values in signals.values():
        window = values[samples]
        window = window[np.isfinite(window)]
        if window.size >= 2:
            total += float(np.mean(np.square(np.diff(window))))
    return total


def _output_energy(output: FloatArray, samples: np.ndarray) -> float:
    window = output[samples]
    window = window[np.isfinite(window)]
    if window.size < 2:
        return 0.0
    return float(np.mean(np.square(np.diff(window))))


def _snr(output: FloatArray, samples: np.ndarray, noise_sigma: float) -> float:
    window = output[samples]
    window = window[np.isfinite(window)]
    if window.size < 2 or noise_sigma <= 0:
        return 0.0
    power = float(np.var(window))
    if power <= 0:
        return 0.0
    return float(10.0 * np.log10(power / (noise_sigma**2)))


def _response_association(
    signals: Mapping[str, FloatArray],
    output: FloatArray,
    samples: np.ndarray,
) -> float:
    """Largest absolute correlation between an input's change and the output's change."""

    target = output[samples]
    if target.size < 3:
        return 0.0
    delta_y = np.diff(target)
    best = 0.0
    for values in signals.values():
        delta_u = np.diff(values[samples])
        finite = np.isfinite(delta_u) & np.isfinite(delta_y)
        if int(np.count_nonzero(finite)) < 3:
            continue
        left = delta_u[finite] - float(np.mean(delta_u[finite]))
        right = delta_y[finite] - float(np.mean(delta_y[finite]))
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 0:
            continue
        best = max(best, abs(float(np.dot(left, right) / denominator)))
    return best


def _anomaly_ratio(masks: list[np.ndarray], samples: np.ndarray) -> float:
    total = 0
    flagged = 0
    for mask in masks:
        window = mask[samples]
        total += int(window.size)
        flagged += int(np.count_nonzero(window))
    return flagged / total if total else 0.0


def _missing_ratio(
    signals: Mapping[str, FloatArray],
    output: FloatArray,
    samples: np.ndarray,
) -> float:
    total = 0
    missing = 0
    for values in (*signals.values(), output):
        window = values[samples]
        total += int(window.size)
        missing += int(np.count_nonzero(~np.isfinite(window)))
    return missing / total if total else 0.0
