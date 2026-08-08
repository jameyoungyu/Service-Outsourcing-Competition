"""Delay estimation by prewhitened cross-correlation, refined on the validation split.

Taking the peak of the raw input-output cross-correlation is the standard shortcut and it
is wrong in a specific, systematic way: ``r_uy(k)`` is the convolution of the true impulse
response with the *input's own autocovariance*. An industrial input is strongly
autocorrelated — operators hold a valve for minutes — so the correlation function is
smeared into a broad plateau whose maximum sits away from the true delay, and the bias is
in the same direction for every input.

Box-Jenkins prewhitening removes it. Fit an AR model to the input, filter both the input
and the output with that same filter, and the cross-correlation of the filtered pair is
proportional to the impulse response itself. The peak is then meaningful.

Prewhitening still only produces *candidates*. The final delay is chosen by refitting ARX
and comparing on the validation split, because cross-correlation cannot see interactions
between inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.regressor import (
    ArxStructure,
    FloatArray,
    IdentifiabilityError,
    build_regressor,
)
from algorithms.identifiability.validation import fit_percentage, free_run_simulate


@dataclass(frozen=True)
class DelayCandidate:
    """One plausible delay for one input, with the evidence behind it."""

    lag: int
    correlation: float
    confidence: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "lag": self.lag,
            "correlation": self.correlation,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class DelayEstimate:
    """Per-input delay evidence: the whole correlation curve plus ranked candidates."""

    column: str
    candidates: tuple[DelayCandidate, ...]
    correlations: tuple[float, ...]
    prewhitening_order: int
    # The best cross-correlation peak. The final answer is DelayResult.refined_delays,
    # which may differ once the validation-split search has weighed the inputs jointly.
    peak_lag: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "prewhitening_order": self.prewhitening_order,
            "peak_lag": self.peak_lag,
        }


@dataclass(frozen=True)
class DelayResult:
    """Outcome of candidate generation plus validation-split refinement."""

    estimates: tuple[DelayEstimate, ...]
    refined_delays: dict[str, int]
    validation_fit: float
    refinement_rounds: int
    uncertain_columns: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "estimates": [estimate.to_payload() for estimate in self.estimates],
            "refined_delays": dict(self.refined_delays),
            "validation_fit": self.validation_fit,
            "refinement_rounds": self.refinement_rounds,
            "uncertain_columns": list(self.uncertain_columns),
        }


def fit_ar_model(signal: FloatArray, *, max_order: int = 20) -> tuple[FloatArray, int]:
    """Fit an AR model whose order minimises AIC; return coefficients and the order.

    Coefficients follow ``u(k) + a_1 u(k-1) + ... + a_p u(k-p) = e(k)``, so filtering with
    them is a plain convolution.
    """

    values = np.asarray(signal, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 8:
        return np.zeros(0, dtype=float), 0
    centered = values - float(np.mean(values))
    if float(np.max(np.abs(centered))) <= 0:
        return np.zeros(0, dtype=float), 0

    limit = int(min(max_order, max(1, centered.size // 10)))
    best_order = 0
    best_criterion = float("inf")
    best_coefficients = np.zeros(0, dtype=float)
    n_samples = centered.size

    for order in range(1, limit + 1):
        rows = n_samples - order
        if rows <= order + 1:
            break
        design = np.column_stack(
            [-centered[order - lag - 1 : n_samples - lag - 1] for lag in range(order)]
        )
        target = centered[order:]
        try:
            coefficients, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
        except np.linalg.LinAlgError:
            break
        residual = target - design @ coefficients
        variance = float(np.mean(np.square(residual)))
        if variance <= 0:
            best_order, best_coefficients = order, np.asarray(coefficients, dtype=float)
            break
        criterion = rows * np.log(variance) + 2 * order
        if criterion < best_criterion:
            best_criterion = criterion
            best_order = order
            best_coefficients = np.asarray(coefficients, dtype=float)
    return best_coefficients, best_order


def apply_ar_filter(signal: FloatArray, coefficients: FloatArray) -> FloatArray:
    """Apply ``A(q)`` to a signal: ``v(k) = x(k) + sum a_i x(k-i)``."""

    values = np.asarray(signal, dtype=float)
    order = int(np.asarray(coefficients).size)
    if order == 0:
        return values - float(np.nanmean(values))
    centered = values - float(np.nanmean(values))
    filtered = centered[order:].copy()
    for lag in range(1, order + 1):
        filtered = filtered + coefficients[lag - 1] * centered[order - lag : centered.size - lag]
    return filtered


def prewhitened_cross_correlation(
    input_signal: FloatArray,
    output_signal: FloatArray,
    *,
    max_lag: int,
    max_ar_order: int = 20,
) -> tuple[FloatArray, int]:
    """Return correlations at lags ``0..max_lag`` between the prewhitened pair."""

    if max_lag < 0:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE", "max_lag 必须非负", {"max_lag": max_lag}
        )
    coefficients, order = fit_ar_model(input_signal, max_order=max_ar_order)
    filtered_input = apply_ar_filter(input_signal, coefficients)
    filtered_output = apply_ar_filter(output_signal, coefficients)
    length = min(filtered_input.size, filtered_output.size)
    filtered_input = filtered_input[:length]
    filtered_output = filtered_output[:length]

    correlations = np.zeros(max_lag + 1, dtype=float)
    for lag in range(max_lag + 1):
        if length - lag < 8:
            break
        left = filtered_input[: length - lag]
        right = filtered_output[lag:]
        finite = np.isfinite(left) & np.isfinite(right)
        if int(np.count_nonzero(finite)) < 8:
            continue
        left_valid = left[finite] - float(np.mean(left[finite]))
        right_valid = right[finite] - float(np.mean(right[finite]))
        denominator = float(np.linalg.norm(left_valid) * np.linalg.norm(right_valid))
        if denominator <= 0:
            continue
        correlations[lag] = float(np.dot(left_valid, right_valid) / denominator)
    return correlations, order


def rank_candidates(
    correlations: FloatArray,
    *,
    top_k: int,
    sample_count: int,
) -> tuple[DelayCandidate, ...]:
    """Return the ``top_k`` local peaks of ``|correlation|``, strongest first.

    Local peaks rather than the global maximum: a delay estimate should surface plausible
    alternatives so the refinement stage — and the engineer — can see how close the runner
    up was.
    """

    values = np.asarray(correlations, dtype=float)
    if values.size == 0:
        return ()
    magnitude = np.abs(values)
    peaks: list[int] = []
    for lag in range(values.size):
        left = magnitude[lag - 1] if lag > 0 else -np.inf
        right = magnitude[lag + 1] if lag + 1 < values.size else -np.inf
        if magnitude[lag] >= left and magnitude[lag] >= right and magnitude[lag] > 0:
            peaks.append(lag)
    if not peaks:
        peaks = [int(np.argmax(magnitude))]
    peaks.sort(key=lambda lag: magnitude[lag], reverse=True)

    band = 1.96 / np.sqrt(max(sample_count, 1))
    candidates = []
    for lag in peaks[: max(1, top_k)]:
        confidence = 0.0 if band <= 0 else float(min(1.0, magnitude[lag] / band / 3.0))
        candidates.append(
            DelayCandidate(
                lag=int(lag),
                correlation=float(values[lag]),
                confidence=confidence,
            )
        )
    return tuple(candidates)


def estimate_delays(
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    max_lag: int,
    top_k: int = 3,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    na: int = 2,
    nb: int = 2,
    max_ar_order: int = 20,
    max_combinations: int = 400,
) -> DelayResult:
    """Generate candidates by prewhitening, then refine them on the validation split.

    Refinement is coordinate descent over inputs: with the other delays held fixed, try
    each candidate for one input and keep the one with the best validation free-run FIT.
    A full grid over all inputs is exponential and buys little, since the delays interact
    only weakly once each is close.
    """

    if not inputs:
        raise IdentifiabilityError("INVALID_DATASET_SCHEMA", "时滞估计至少需要一个输入变量")
    measured = np.asarray(output, dtype=float)
    signals = {name: np.asarray(values, dtype=float) for name, values in inputs.items()}
    n_samples = int(measured.shape[0])
    train_stop = int(n_samples * train_ratio)
    validation_stop = int(n_samples * (train_ratio + validation_ratio))
    if train_stop <= max_lag + na + nb:
        raise IdentifiabilityError(
            "INSUFFICIENT_ROWS",
            "训练区间过短，无法在给定的最大滞后下估计时滞",
            {"train_rows": train_stop, "max_lag": max_lag},
        )

    estimates: list[DelayEstimate] = []
    for column, signal in signals.items():
        correlations, order = prewhitened_cross_correlation(
            signal[:train_stop],
            measured[:train_stop],
            max_lag=max_lag,
            max_ar_order=max_ar_order,
        )
        candidates = rank_candidates(correlations, top_k=top_k, sample_count=train_stop)
        estimates.append(
            DelayEstimate(
                column=column,
                candidates=candidates,
                correlations=tuple(float(value) for value in correlations),
                prewhitening_order=order,
                peak_lag=candidates[0].lag if candidates else 0,
            )
        )

    # Cross-correlation peaks are proposals, not answers: the true delay often sits one or
    # two samples off the peak once the other inputs are accounted for, so each peak is
    # widened into a small neighbourhood before the search.
    search_space = {
        estimate.column: _widen(
            [candidate.lag for candidate in estimate.candidates], max_lag=max_lag
        )
        for estimate in estimates
    }

    def score(candidate_delays: dict[str, int]) -> float:
        return _validation_fit(
            signals,
            measured,
            candidate_delays,
            na=na,
            nb=nb,
            start=train_stop,
            stop=validation_stop,
        )

    combinations = 1
    for options in search_space.values():
        combinations *= len(options)

    if combinations <= max_combinations:
        # Small enough to settle exactly; coordinate descent can stall in a local optimum
        # here because a wrong delay on one input can make every delay on another look bad.
        delays, best_fit = _exhaustive_search(search_space, score)
        rounds = 1
    else:
        delays, best_fit, rounds = _coordinate_descent(
            search_space,
            score,
            starts=[{column: options[0] for column, options in search_space.items()}]
            + [
                {
                    column: (options[position] if position < len(options) else options[0])
                    for column, options in search_space.items()
                }
                for position in range(1, 3)
            ],
        )

    uncertain = tuple(
        estimate.column
        for estimate in estimates
        if len(estimate.candidates) > 1
        and abs(abs(estimate.candidates[0].correlation) - abs(estimate.candidates[1].correlation))
        < 0.05
    )
    return DelayResult(
        estimates=tuple(estimates),
        refined_delays=delays,
        validation_fit=best_fit,
        refinement_rounds=rounds,
        uncertain_columns=uncertain,
    )


def _widen(lags: list[int], *, max_lag: int, radius: int = 1) -> list[int]:
    """Expand each candidate peak into a small neighbourhood, nearest-first."""

    expanded: list[int] = []
    for lag in lags:
        for offset in range(-radius, radius + 1):
            value = lag + offset
            if 0 <= value <= max_lag and value not in expanded:
                expanded.append(value)
    return expanded or [0]


def _exhaustive_search(
    search_space: Mapping[str, list[int]],
    score: Any,
) -> tuple[dict[str, int], float]:
    """Evaluate every delay combination and return the best."""

    columns = list(search_space)
    best: dict[str, int] = {column: search_space[column][0] for column in columns}
    best_score = float("-inf")

    def walk(position: int, current: dict[str, int]) -> None:
        nonlocal best, best_score
        if position == len(columns):
            value = score(current)
            if value > best_score:
                best_score = value
                best = dict(current)
            return
        column = columns[position]
        for lag in search_space[column]:
            current[column] = lag
            walk(position + 1, current)

    walk(0, {})
    return best, best_score


def _coordinate_descent(
    search_space: Mapping[str, list[int]],
    score: Any,
    *,
    starts: list[dict[str, int]],
    max_rounds: int = 4,
) -> tuple[dict[str, int], float, int]:
    """Coordinate descent from several starting points, keeping the overall best.

    Restarts matter: a single bad initial delay can make every alternative for another
    input look worse than it is, which pins a single-start descent to a poor optimum.
    """

    best: dict[str, int] = dict(starts[0])
    best_score = float("-inf")
    total_rounds = 0

    for start in starts:
        current = dict(start)
        current_score = score(current)
        improved = True
        rounds = 0
        while improved and rounds < max_rounds:
            improved = False
            rounds += 1
            for column, options in search_space.items():
                for lag in options:
                    if lag == current[column]:
                        continue
                    trial = dict(current)
                    trial[column] = lag
                    value = score(trial)
                    if value > current_score + 1e-9:
                        current_score = value
                        current = trial
                        improved = True
        total_rounds += rounds
        if current_score > best_score:
            best_score = current_score
            best = current
    return best, best_score, total_rounds


def _validation_fit(
    signals: Mapping[str, FloatArray],
    output: FloatArray,
    delays: Mapping[str, int],
    *,
    na: int,
    nb: int,
    start: int,
    stop: int,
) -> float:
    """Fit ARX on the training rows and score free-run simulation on the validation rows."""

    structure = ArxStructure.create(na=na, nb=nb, nk=dict(delays), input_columns=tuple(signals))
    try:
        train = build_regressor(
            inputs=dict(signals), output=output, structure=structure, start=0, stop=start
        )
        if train.n_rows <= train.n_parameters * 2:
            return float("-inf")
        theta, _, _, _ = np.linalg.lstsq(train.features, train.targets, rcond=None)
        measured, simulated = free_run_simulate(
            np.asarray(theta, dtype=float),
            structure,
            inputs=dict(signals),
            output=output,
            start=start,
            stop=stop,
        )
        return fit_percentage(measured, simulated)
    except IdentifiabilityError:
        return float("-inf")
    except np.linalg.LinAlgError:
        return float("-inf")
