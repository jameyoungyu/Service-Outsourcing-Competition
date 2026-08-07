"""Quality gating that runs *before* any information-theoretic selection.

The D-optimal criterion answers "which segments teach the model the most". It cannot
answer "is this segment trustworthy at all" — a burst of spikes is highly informative in
the ``log det`` sense precisely because it is wild, and a frozen sensor reading looks
perfectly clean while contributing nothing. So the pipeline is two-stage and the order
matters:

1. **Gate**: reject windows with too much missing data, too many detected anomalies, too
   little excitation (steady holds), or too poor a signal-to-noise ratio.
2. **Select**: run the submodular D-optimal greedy over the survivors only.

Every rejected window keeps its reasons so the report can show the engineer what was
thrown away and why, rather than silently shrinking the data set.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.regressor import FloatArray, IdentifiabilityError

# MAD -> sigma for a normal distribution.
MAD_TO_SIGMA = 1.4826
# Variance inflation of a second difference of white noise: var(d2) = 6 * var(e).
SECOND_DIFFERENCE_VARIANCE_GAIN = 6.0


@dataclass(frozen=True)
class GatingThresholds:
    """Engineering limits a window must satisfy to enter the selection pool."""

    max_missing_ratio: float = 0.20
    max_anomaly_ratio: float = 0.10
    min_snr_db: float = 0.0
    min_input_activity_ratio: float = 0.05
    hampel_window: int = 11
    hampel_threshold: float = 3.0

    def validate(self) -> None:
        if not 0.0 <= self.max_missing_ratio <= 1.0:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "max_missing_ratio 必须位于 [0,1]",
                {"max_missing_ratio": self.max_missing_ratio},
            )
        if not 0.0 <= self.max_anomaly_ratio <= 1.0:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "max_anomaly_ratio 必须位于 [0,1]",
                {"max_anomaly_ratio": self.max_anomaly_ratio},
            )
        if self.min_input_activity_ratio < 0:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "min_input_activity_ratio 必须非负",
                {"min_input_activity_ratio": self.min_input_activity_ratio},
            )
        if self.hampel_window < 3 or self.hampel_window % 2 == 0:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "hampel_window 必须是大于等于 3 的奇数",
                {"hampel_window": self.hampel_window},
            )


@dataclass(frozen=True)
class WindowQuality:
    """Per-window evidence, kept for accepted and rejected windows alike."""

    window_index: int
    start_index: int
    end_index: int
    missing_ratio: float
    anomaly_ratio: float
    snr_db: float
    input_activity: float
    output_activity: float
    accepted: bool
    rejection_reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "window_index": self.window_index,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "missing_ratio": self.missing_ratio,
            "anomaly_ratio": self.anomaly_ratio,
            "snr_db": self.snr_db,
            "input_activity": self.input_activity,
            "output_activity": self.output_activity,
            "accepted": self.accepted,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class GatingReport:
    """Outcome of the gate, including why each window failed."""

    windows: tuple[WindowQuality, ...]
    accepted_indices: tuple[int, ...]
    thresholds: GatingThresholds
    rejection_counts: dict[str, int]
    noise_sigma: float

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_indices)

    def to_payload(self) -> dict[str, Any]:
        return {
            "windows": [window.to_payload() for window in self.windows],
            "accepted_indices": list(self.accepted_indices),
            "accepted_count": self.accepted_count,
            "candidate_count": len(self.windows),
            "rejection_counts": dict(self.rejection_counts),
            "noise_sigma": self.noise_sigma,
            "thresholds": {
                "max_missing_ratio": self.thresholds.max_missing_ratio,
                "max_anomaly_ratio": self.thresholds.max_anomaly_ratio,
                "min_snr_db": self.thresholds.min_snr_db,
                "min_input_activity_ratio": self.thresholds.min_input_activity_ratio,
            },
        }


def estimate_noise_sigma(signal: FloatArray) -> float:
    """Robustly estimate the additive noise level from the second difference.

    For ``y = s + e`` with a smooth ``s``, the second difference nearly annihilates ``s``
    and leaves ``var = 6 sigma^2``. Using the MAD instead of the standard deviation keeps
    the estimate from being dominated by the very spikes we are trying to detect.
    """

    values = np.asarray(signal, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 4:
        return 0.0
    second = np.diff(values, n=2)
    if second.size == 0:
        return 0.0
    deviation = float(np.median(np.abs(second - np.median(second))))
    return float(MAD_TO_SIGMA * deviation / np.sqrt(SECOND_DIFFERENCE_VARIANCE_GAIN))


def hampel_anomaly_mask(
    signal: FloatArray,
    *,
    window: int = 11,
    threshold: float = 3.0,
) -> np.ndarray:
    """Flag points whose deviation from the rolling median exceeds ``threshold`` MADs."""

    values = np.asarray(signal, dtype=float)
    n_samples = int(values.shape[0])
    mask = np.zeros(n_samples, dtype=bool)
    if n_samples < window or window < 3:
        return mask
    half = window // 2
    padded = np.pad(values, (half, half), mode="edge")
    frames = np.lib.stride_tricks.sliding_window_view(padded, window)
    # An all-NaN frame is a legitimate outcome on a long gap; it yields NaN statistics,
    # which the finite mask below turns into "not an anomaly" rather than a crash.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        centre = np.nanmedian(frames, axis=1)
        deviation = np.nanmedian(np.abs(frames - centre[:, None]), axis=1)
    scale = MAD_TO_SIGMA * deviation
    finite = np.isfinite(values) & np.isfinite(centre) & (scale > 0)
    mask[finite] = np.abs(values[finite] - centre[finite]) > threshold * scale[finite]
    return mask


def gate_windows(
    *,
    window_positions: tuple[np.ndarray, ...],
    time_indices: np.ndarray,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    thresholds: GatingThresholds | None = None,
) -> GatingReport:
    """Score and gate every candidate window on quality and excitation grounds.

    ``window_positions`` index into the regressor rows; ``time_indices`` maps a regressor
    row back to its sample index so the quality statistics are read from the original
    series rather than from lagged regressor columns.
    """

    limits = thresholds or GatingThresholds()
    limits.validate()

    measured = np.asarray(output, dtype=float)
    signals = {name: np.asarray(values, dtype=float) for name, values in inputs.items()}
    if not signals:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "质量门控至少需要一个输入变量",
        )

    noise_sigma = estimate_noise_sigma(measured)
    anomaly_masks = {
        name: hampel_anomaly_mask(
            values, window=limits.hampel_window, threshold=limits.hampel_threshold
        )
        for name, values in signals.items()
    }
    anomaly_masks["__output__"] = hampel_anomaly_mask(
        measured, window=limits.hampel_window, threshold=limits.hampel_threshold
    )

    rows = np.asarray(time_indices, dtype=int)
    sample_sets = [rows[np.asarray(positions, dtype=int)] for positions in window_positions]
    activities = [_input_activity(signals, samples) for samples in sample_sets]
    activity_reference = _activity_reference(activities)

    windows: list[WindowQuality] = []
    accepted: list[int] = []
    rejection_counts: dict[str, int] = {}

    for index, samples in enumerate(sample_sets):
        missing_ratio = _missing_ratio(signals, measured, samples)
        anomaly_ratio = _anomaly_ratio(anomaly_masks, samples)
        input_activity = activities[index]
        output_activity = _output_activity(measured, samples)
        snr_db = _snr_db(measured, samples, noise_sigma)

        reasons: list[str] = []
        if missing_ratio > limits.max_missing_ratio:
            reasons.append("missing_ratio_exceeded")
        if anomaly_ratio > limits.max_anomaly_ratio:
            reasons.append("anomaly_ratio_exceeded")
        if snr_db < limits.min_snr_db:
            reasons.append("snr_below_threshold")
        if (
            activity_reference > 0
            and input_activity < limits.min_input_activity_ratio * activity_reference
        ):
            reasons.append("steady_state_segment")
        elif activity_reference <= 0:
            reasons.append("no_input_excitation")

        is_accepted = not reasons
        if is_accepted:
            accepted.append(index)
        for reason in reasons:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

        windows.append(
            WindowQuality(
                window_index=index,
                start_index=int(samples[0]),
                end_index=int(samples[-1]),
                missing_ratio=missing_ratio,
                anomaly_ratio=anomaly_ratio,
                snr_db=snr_db,
                input_activity=input_activity,
                output_activity=output_activity,
                accepted=is_accepted,
                rejection_reasons=tuple(reasons),
            )
        )

    return GatingReport(
        windows=tuple(windows),
        accepted_indices=tuple(accepted),
        thresholds=limits,
        rejection_counts=rejection_counts,
        noise_sigma=noise_sigma,
    )


def _missing_ratio(
    signals: Mapping[str, FloatArray],
    output: FloatArray,
    samples: np.ndarray,
) -> float:
    total = 0
    missing = 0
    for values in signals.values():
        window = values[samples]
        total += int(window.size)
        missing += int(np.count_nonzero(~np.isfinite(window)))
    window = output[samples]
    total += int(window.size)
    missing += int(np.count_nonzero(~np.isfinite(window)))
    return missing / total if total else 1.0


def _anomaly_ratio(masks: Mapping[str, np.ndarray], samples: np.ndarray) -> float:
    total = 0
    flagged = 0
    for mask in masks.values():
        window = mask[samples]
        total += int(window.size)
        flagged += int(np.count_nonzero(window))
    return flagged / total if total else 0.0


def _input_activity(signals: Mapping[str, FloatArray], samples: np.ndarray) -> float:
    total = 0.0
    for values in signals.values():
        window = values[samples]
        window = window[np.isfinite(window)]
        if window.size < 2:
            continue
        total += float(np.mean(np.square(np.diff(window))))
    return total


def _output_activity(output: FloatArray, samples: np.ndarray) -> float:
    window = output[samples]
    window = window[np.isfinite(window)]
    if window.size < 2:
        return 0.0
    return float(np.mean(np.square(np.diff(window))))


def _activity_reference(activities: list[float]) -> float:
    """Reference scale for "is this window moving": the 95th percentile across windows.

    Windows are compared against each other rather than against an absolute threshold, so
    the criterion is scale-free and works whether the process is in bar or in degrees.

    A per-sample reference does not work here: on a record that is 90% steady — the case
    this whole feature exists for — most sample-to-sample differences are exactly zero, so
    any percentile of them collapses to zero and every window looks active. Taking the
    percentile over *window* activities keeps the reference anchored on how much the
    process moves when it actually moves, and P95 rather than the max keeps one spike
    window from raising the bar for everyone.
    """

    finite = [value for value in activities if np.isfinite(value) and value > 0]
    if not finite:
        return 0.0
    return float(np.percentile(np.asarray(finite, dtype=float), 95))


def _snr_db(output: FloatArray, samples: np.ndarray, noise_sigma: float) -> float:
    window = output[samples]
    window = window[np.isfinite(window)]
    if window.size < 2:
        return float("-inf")
    signal_power = float(np.var(window))
    if noise_sigma <= 0:
        return float("inf") if signal_power > 0 else float("-inf")
    ratio = signal_power / (noise_sigma**2)
    if ratio <= 0:
        return float("-inf")
    return float(10.0 * np.log10(ratio))
