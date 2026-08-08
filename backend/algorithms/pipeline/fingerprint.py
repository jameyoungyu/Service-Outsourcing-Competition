"""Data-profile fingerprints used to retrieve a warm start from past studies.

The brief asks for a "self-evolving" preprocessing engine. Looping inside one session does
not evolve anything — close the browser and the system has learned nothing. What does
evolve is a memory keyed by *what kind of data this is*, so a new dataset can start from
the parameters that already worked on a similar process.

The fingerprint is deliberately built from quantities the profiling stage already
computes, and each component is normalised to a comparable scale so plain Euclidean
distance is meaningful. Nothing derived from the test partition enters it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.gating import estimate_noise_sigma
from algorithms.identifiability.regressor import FloatArray

# Order matters: the vector is compared positionally.
FINGERPRINT_FIELDS = (
    "log_sample_count",
    "input_count",
    "missing_ratio",
    "anomaly_ratio",
    "snr_db_scaled",
    "dynamic_ratio",
    "output_autocorrelation",
    "input_autocorrelation",
    "collinearity_scaled",
)


@dataclass(frozen=True)
class ProfileFingerprint:
    """A fixed-length description of a dataset's character."""

    values: dict[str, float]

    @property
    def vector(self) -> list[float]:
        return [float(self.values.get(name, 0.0)) for name in FINGERPRINT_FIELDS]

    def to_payload(self) -> dict[str, Any]:
        return {"fields": list(FINGERPRINT_FIELDS), "values": dict(self.values)}


def build_fingerprint(
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
) -> ProfileFingerprint:
    """Summarise a dataset into comparable, bounded features."""

    measured = np.asarray(output, dtype=float)
    signals = {name: np.asarray(values, dtype=float) for name, values in inputs.items()}
    n_samples = max(int(measured.shape[0]), 1)

    total = measured.size + sum(signal.size for signal in signals.values())
    missing = int(np.count_nonzero(~np.isfinite(measured))) + sum(
        int(np.count_nonzero(~np.isfinite(signal))) for signal in signals.values()
    )

    noise_sigma = estimate_noise_sigma(measured)
    finite_output = measured[np.isfinite(measured)]
    signal_power = float(np.var(finite_output)) if finite_output.size > 1 else 0.0
    if noise_sigma > 0 and signal_power > 0:
        snr_db = 10.0 * float(np.log10(signal_power / (noise_sigma**2)))
    else:
        snr_db = 60.0
    # Squash to [0,1] over a 0-60 dB working range; industrial SNR outside that is rare
    # and the exact value stops mattering for choosing a starting point.
    snr_scaled = float(np.clip(snr_db / 60.0, 0.0, 1.0))

    return ProfileFingerprint(
        values={
            "log_sample_count": float(np.log10(n_samples)) / 6.0,
            "input_count": float(min(len(signals), 8)) / 8.0,
            "missing_ratio": missing / total if total else 0.0,
            "anomaly_ratio": _outlier_ratio(measured),
            "snr_db_scaled": snr_scaled,
            "dynamic_ratio": _dynamic_ratio(signals),
            "output_autocorrelation": _lag_one_autocorrelation(measured),
            "input_autocorrelation": float(
                np.mean([_lag_one_autocorrelation(signal) for signal in signals.values()])
            )
            if signals
            else 0.0,
            "collinearity_scaled": _collinearity(signals),
        }
    )


def fingerprint_distance(left: list[float], right: list[float]) -> float:
    """Euclidean distance between two fingerprint vectors; inf if shapes disagree."""

    if len(left) != len(right) or not left:
        return float("inf")
    return float(np.linalg.norm(np.asarray(left, dtype=float) - np.asarray(right, dtype=float)))


def _outlier_ratio(values: FloatArray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < 8:
        return 0.0
    median = float(np.median(finite))
    deviation = float(np.median(np.abs(finite - median)))
    if deviation <= 0:
        return 0.0
    scale = 1.4826 * deviation
    return float(np.count_nonzero(np.abs(finite - median) > 3.0 * scale) / finite.size)


def _dynamic_ratio(signals: Mapping[str, FloatArray]) -> float:
    """Fraction of samples where the inputs are actually moving."""

    if not signals:
        return 0.0
    moving = []
    for values in signals.values():
        finite = values[np.isfinite(values)]
        if finite.size < 2:
            continue
        activity = np.abs(np.diff(finite))
        threshold = float(np.percentile(activity, 95)) * 0.05
        if threshold <= 0:
            moving.append(0.0)
            continue
        moving.append(float(np.count_nonzero(activity > threshold) / activity.size))
    return float(np.mean(moving)) if moving else 0.0


def _lag_one_autocorrelation(values: FloatArray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < 3:
        return 0.0
    centered = finite - float(np.mean(finite))
    denominator = float(np.dot(centered, centered))
    if denominator <= 0:
        return 0.0
    return float(np.clip(np.dot(centered[:-1], centered[1:]) / denominator, -1.0, 1.0))


def _collinearity(signals: Mapping[str, FloatArray]) -> float:
    """Largest absolute pairwise correlation among the inputs."""

    names = list(signals)
    if len(names) < 2:
        return 0.0
    worst = 0.0
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            left = signals[names[i]]
            right = signals[names[j]]
            finite = np.isfinite(left) & np.isfinite(right)
            if int(np.count_nonzero(finite)) < 3:
                continue
            a = left[finite] - float(np.mean(left[finite]))
            b = right[finite] - float(np.mean(right[finite]))
            denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denominator <= 0:
                continue
            worst = max(worst, abs(float(np.dot(a, b) / denominator)))
    return float(np.clip(worst, 0.0, 1.0))
