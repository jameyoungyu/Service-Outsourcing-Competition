"""Control-relevant ARX validation: free-run simulation, stability and steady-state gain.

An APC controller predicts many steps ahead over its horizon, so the metric that decides
whether a model is deployable is the free-run (infinite-step) simulation error, not the
one-step-ahead prediction error. One-step FIT is flattering on any strongly autocorrelated
process output: feeding the *measured* ``y(k-1)`` back into the regressor lets a badly
identified model coast on persistence and still score above 99%.

This module therefore drives the model from the inputs alone after a short warm start,
and adds the two checks an engineer applies before trusting a model at all: is ``A(q)``
stable, and does each steady-state gain have the sign and magnitude the process is known
to have.
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

# How far past the measured output range a free-run trajectory may wander before it is
# clamped. Large enough that a merely poor model is never distorted, small enough that a
# diverging one cannot overflow.
DIVERGENCE_BOUND_FACTOR = 1e3


@dataclass(frozen=True)
class ModelValidation:
    """Everything needed to accept or reject an identified model."""

    one_step_fit: float
    free_run_fit: float
    free_run_rmse: float
    fit_gap: float
    stable: bool
    max_pole_modulus: float
    steady_state_gains: dict[str, float]
    residual_whiteness_ratio: float
    n_samples: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "one_step_fit": self.one_step_fit,
            "free_run_fit": self.free_run_fit,
            "free_run_rmse": self.free_run_rmse,
            "fit_gap": self.fit_gap,
            "stable": self.stable,
            "max_pole_modulus": self.max_pole_modulus,
            "steady_state_gains": dict(self.steady_state_gains),
            "residual_whiteness_ratio": self.residual_whiteness_ratio,
            "n_samples": self.n_samples,
        }


def unpack_parameters(
    theta: FloatArray,
    structure: ArxStructure,
) -> tuple[FloatArray, dict[str, FloatArray]]:
    """Split a parameter vector into the ``a`` vector and per-input ``b`` vectors."""

    values = np.asarray(theta, dtype=float).ravel()
    if values.size != structure.parameter_count:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "参数向量长度与 ARX 结构不一致",
            {"expected": structure.parameter_count, "actual": int(values.size)},
        )
    a_values = values[: structure.na]
    b_values: dict[str, FloatArray] = {}
    offset = structure.na
    for column in structure.input_columns:
        width = structure.nb[column]
        b_values[column] = values[offset : offset + width]
        offset += width
    return a_values, b_values


def is_stable(a_coefficients: FloatArray) -> tuple[bool, float]:
    """Return whether ``A(q) = 1 + a_1 q^-1 + ... `` has all poles inside the unit circle."""

    values = np.asarray(a_coefficients, dtype=float).ravel()
    if values.size == 0:
        return True, 0.0
    polynomial = np.concatenate(([1.0], values))
    roots = np.roots(polynomial)
    if roots.size == 0:
        return True, 0.0
    modulus = float(np.max(np.abs(roots)))
    return bool(modulus < 1.0), modulus


def steady_state_gains(
    theta: FloatArray,
    structure: ArxStructure,
) -> dict[str, float]:
    """Return ``K_j = sum(b_j) / (1 + sum(a))`` for every input.

    This is the number a process engineer can sanity-check directly ("opening the valve
    must raise the temperature"), which is why the closed loop can constrain it from prior
    knowledge instead of hoping the fit gets the sign right.
    """

    a_values, b_values = unpack_parameters(theta, structure)
    denominator = 1.0 + float(np.sum(a_values))
    if abs(denominator) < 1e-12:
        return dict.fromkeys(structure.input_columns, float("inf"))
    return {
        column: float(np.sum(b_values[column]) / denominator) for column in structure.input_columns
    }


def free_run_simulate(
    theta: FloatArray,
    structure: ArxStructure,
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    start: int,
    stop: int,
) -> tuple[FloatArray, FloatArray]:
    """Simulate the output from the inputs alone over ``[start, stop)``.

    The first ``na`` values are seeded from the measured output — the standard warm start —
    and every later sample uses the model's own previous predictions. Returns the measured
    and simulated slices, aligned.
    """

    a_values, b_values = unpack_parameters(theta, structure)
    measured = np.asarray(output, dtype=float)
    n_samples = int(measured.shape[0])
    first = max(start, structure.max_history)
    last = min(stop, n_samples)
    if last - first <= structure.na:
        raise IdentifiabilityError(
            "INSUFFICIENT_ROWS",
            "自由仿真区间长度不足",
            {"start": first, "stop": last, "na": structure.na},
        )
    signals = {
        column: np.asarray(inputs[column], dtype=float) for column in structure.input_columns
    }

    # The input contribution does not depend on the simulated output, so it is computed
    # for the whole horizon at once. Only the output feedback has to stay sequential,
    # which turns the inner loop from O(horizon * inputs * nb) Python operations into
    # O(horizon * na) — the closed-loop optimiser runs this thousands of times.
    contribution = np.zeros(n_samples, dtype=float)
    index = np.arange(first, last, dtype=int)
    for column in structure.input_columns:
        signal = signals[column]
        delay = structure.nk[column]
        coefficients = b_values[column]
        for lag in range(structure.nb[column]):
            contribution[index] += coefficients[lag] * signal[index - delay - lag]

    # An unstable A(q) makes the recursion grow without bound. Left alone it overflows to
    # inf within a few hundred steps and poisons every downstream statistic with NaN, so
    # the trajectory is clamped to a generous multiple of the observed output range. The
    # resulting FIT is terrible, which is the correct verdict on a diverging model, and it
    # is a finite number the optimiser can rank instead of a crash.
    finite_measured = measured[np.isfinite(measured)]
    scale = float(np.max(np.abs(finite_measured))) if finite_measured.size else 1.0
    bound = max(scale, 1.0) * DIVERGENCE_BOUND_FACTOR

    simulated = measured.copy()
    for time_index in range(first, last):
        value = float(contribution[time_index])
        for lag in range(1, structure.na + 1):
            value -= a_values[lag - 1] * simulated[time_index - lag]
        if not np.isfinite(value):
            value = float(np.sign(simulated[time_index - 1]) or 1.0) * bound
        elif value > bound:
            value = bound
        elif value < -bound:
            value = -bound
        simulated[time_index] = value

    return measured[first:last], simulated[first:last]


def fit_percentage(actual: FloatArray, predicted: FloatArray) -> float:
    """Return the standard identification FIT in percent, clipped from below at -100."""

    measured = np.asarray(actual, dtype=float)
    estimate = np.asarray(predicted, dtype=float)
    centered = measured - float(np.mean(measured))
    denominator = float(np.linalg.norm(centered))
    if denominator == 0:
        raise IdentifiabilityError(
            "NUMERICAL_INSTABILITY",
            "输出恒定，FIT 无定义",
        )
    residual = float(np.linalg.norm(measured - estimate))
    return float(max(-100.0, 100.0 * (1.0 - residual / denominator)))


def residual_whiteness_ratio(residuals: FloatArray, *, max_lag: int = 20) -> float:
    """Fraction of residual autocorrelation lags inside the 95% white-noise band.

    1.0 means the residual looks white, so the model captured the deterministic dynamics;
    a low value means structure was left on the table regardless of how good FIT looks.
    """

    values = np.asarray(residuals, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size < 8:
        return float("nan")
    centered = values - float(np.mean(values))
    denominator = float(np.dot(centered, centered))
    if denominator == 0:
        return 1.0
    lags = min(max_lag, values.size - 1)
    bound = 1.96 / np.sqrt(values.size)
    inside = 0
    for lag in range(1, lags + 1):
        correlation = float(np.dot(centered[:-lag], centered[lag:]) / denominator)
        if abs(correlation) <= bound:
            inside += 1
    return inside / lags if lags else float("nan")


def validate_model(
    theta: FloatArray,
    structure: ArxStructure,
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    start: int,
    stop: int,
) -> ModelValidation:
    """Score a model the way an APC engineer would before deploying it."""

    measured, simulated = free_run_simulate(
        theta,
        structure,
        inputs=inputs,
        output=output,
        start=start,
        stop=stop,
    )
    free_run = fit_percentage(measured, simulated)
    free_run_rmse = float(np.sqrt(np.mean(np.square(measured - simulated))))

    regressor = build_regressor(
        inputs=dict(inputs),
        output=np.asarray(output, dtype=float),
        structure=structure,
        start=start,
        stop=stop,
    )
    predicted = regressor.features @ np.asarray(theta, dtype=float).ravel()
    one_step = fit_percentage(regressor.targets, predicted)
    residuals = regressor.targets - predicted

    a_values, _ = unpack_parameters(theta, structure)
    stable, modulus = is_stable(a_values)
    return ModelValidation(
        one_step_fit=one_step,
        free_run_fit=free_run,
        free_run_rmse=free_run_rmse,
        fit_gap=one_step - free_run,
        stable=stable,
        max_pole_modulus=modulus,
        steady_state_gains=steady_state_gains(theta, structure),
        residual_whiteness_ratio=residual_whiteness_ratio(residuals),
        n_samples=int(measured.size),
    )
