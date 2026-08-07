"""Time alignment, interpolation, outlier treatment and smoothing primitives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import floor, isclose, isfinite
from typing import Literal

import numpy as np

from algorithms.cleaning.quality import is_missing
from algorithms.cleaning.tool import AlgorithmTool

InterpolationMethod = Literal["linear", "ffill", "bfill", "none"]
OutlierDetector = Literal["hampel", "iqr", "z_score"]
OutlierStrategy = Literal["keep", "set_null", "local_median", "linear_interpolate", "clip"]
SmoothingMethod = Literal["none", "moving_average", "savitzky_golay"]
DuplicateStrategy = Literal["first", "mean"]


@dataclass(frozen=True)
class CleaningContext:
    headers: list[str]
    timestamp_column: str
    timestamps: list[datetime]
    rows: Sequence[Mapping[str, str]]
    inferred_types: Mapping[str, str]


@dataclass(frozen=True)
class CleaningParameters:
    resample_period_seconds: float | None
    interpolation: InterpolationMethod
    max_consecutive_missing: int | None
    duplicate_strategy: DuplicateStrategy
    outlier_detector: OutlierDetector
    outlier_strategy: OutlierStrategy
    hampel_window: int
    hampel_threshold: float
    z_score_threshold: float
    smoothing: SmoothingMethod
    smoothing_window: int


@dataclass(frozen=True)
class DetectedOutlier:
    index: int
    median: float
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True)
class CleaningResult:
    timestamps: list[datetime]
    values: dict[str, list[str | float | None]]
    raw_numeric: dict[str, list[float | None]]
    cleaned_numeric: dict[str, list[float | None]]
    changed_indices: dict[str, list[int]]
    detected_outlier_indices: dict[str, list[int]]
    frozen_segments: list[dict[str, int | str]]
    warnings: list[str]

    @property
    def total_changed_points(self) -> int:
        return sum(len(indices) for indices in self.changed_indices.values())


@dataclass(frozen=True)
class _NormalisedFrame:
    timestamps: list[datetime]
    numeric: dict[str, list[float | None]]
    categorical: dict[str, list[str | None]]


class CleaningPipeline(AlgorithmTool[CleaningContext, CleaningParameters, CleaningResult]):
    """Pure cleaning pipeline that leaves all persistence decisions to its caller."""

    name = "align_resample_clean"
    input_schema: type[object] = CleaningContext
    output_schema: type[object] = CleaningResult

    def execute(self, context: CleaningContext, parameters: CleaningParameters) -> CleaningResult:
        normalised, duplicate_count = _normalise_timestamps(context, parameters.duplicate_strategy)
        aligned = (
            _resample(normalised, parameters.resample_period_seconds)
            if parameters.resample_period_seconds is not None
            else normalised
        )
        raw_numeric = {column: values.copy() for column, values in aligned.numeric.items()}
        cleaned_numeric: dict[str, list[float | None]] = {}
        changed_indices: dict[str, list[int]] = {}
        detected_indices: dict[str, list[int]] = {}
        frozen_segments: list[dict[str, int | str]] = []
        warnings: list[str] = []

        for column, raw_values in raw_numeric.items():
            interpolated, interpolation_changes = _interpolate_missing(
                raw_values,
                method=parameters.interpolation,
                max_consecutive_missing=parameters.max_consecutive_missing,
            )
            outliers = _detect_outliers(
                interpolated,
                detector=parameters.outlier_detector,
                hampel_window=parameters.hampel_window,
                hampel_threshold=parameters.hampel_threshold,
                z_score_threshold=parameters.z_score_threshold,
            )
            treated, treatment_changes = _treat_outliers(
                interpolated,
                outliers,
                strategy=parameters.outlier_strategy,
                interpolation=parameters.interpolation,
                max_consecutive_missing=parameters.max_consecutive_missing,
            )
            smoothed, smoothing_changes = _smooth(
                treated,
                method=parameters.smoothing,
                window=parameters.smoothing_window,
            )
            changed_indices[column] = sorted(
                interpolation_changes | treatment_changes | smoothing_changes
            )
            detected_indices[column] = [item.index for item in outliers]
            cleaned_numeric[column] = smoothed
            frozen_segments.extend(_frozen_segments(column, smoothed))

        if duplicate_count:
            warnings.append(
                f"已按 {parameters.duplicate_strategy} 规则处理 {duplicate_count} 个重复时间戳。"
            )
        remaining_missing = sum(
            value is None for values in cleaned_numeric.values() for value in values
        )
        if remaining_missing:
            warnings.append(f"仍保留 {remaining_missing} 个超出插值上限或边界的缺失值。")
        if frozen_segments:
            warnings.append(f"检测到 {len(frozen_segments)} 个冻结段，未自动删除。")

        values: dict[str, list[str | float | None]] = {}
        for column in context.headers:
            if column == context.timestamp_column:
                continue
            if column in cleaned_numeric:
                values[column] = list(cleaned_numeric[column])
            else:
                values[column] = list(aligned.categorical[column])
        return CleaningResult(
            timestamps=aligned.timestamps,
            values=values,
            raw_numeric=raw_numeric,
            cleaned_numeric=cleaned_numeric,
            changed_indices=changed_indices,
            detected_outlier_indices=detected_indices,
            frozen_segments=frozen_segments,
            warnings=warnings,
        )


def _normalise_timestamps(
    context: CleaningContext, duplicate_strategy: DuplicateStrategy
) -> tuple[_NormalisedFrame, int]:
    ordered_indices = sorted(
        range(len(context.timestamps)), key=lambda index: context.timestamps[index]
    )
    groups: list[list[int]] = []
    for index in ordered_indices:
        if not groups or context.timestamps[index] != context.timestamps[groups[-1][0]]:
            groups.append([index])
        else:
            groups[-1].append(index)
    numeric_columns = [
        column
        for column in context.headers
        if column != context.timestamp_column
        and context.inferred_types.get(column) in {"float", "integer"}
    ]
    categorical_columns = [
        column
        for column in context.headers
        if column not in numeric_columns and column != context.timestamp_column
    ]
    numeric: dict[str, list[float | None]] = {column: [] for column in numeric_columns}
    categorical: dict[str, list[str | None]] = {column: [] for column in categorical_columns}
    timestamps: list[datetime] = []
    for group in groups:
        timestamps.append(context.timestamps[group[0]])
        for column in numeric_columns:
            numeric_source = [_to_float(context.rows[index].get(column)) for index in group]
            numeric[column].append(_aggregate_numeric(numeric_source, duplicate_strategy))
        for column in categorical_columns:
            categorical_source = [
                _to_categorical(context.rows[index].get(column)) for index in group
            ]
            categorical[column].append(_aggregate_categorical(categorical_source))
    duplicate_count = sum(len(group) - 1 for group in groups)
    return _NormalisedFrame(
        timestamps=timestamps, numeric=numeric, categorical=categorical
    ), duplicate_count


def _resample(frame: _NormalisedFrame, period_seconds: float) -> _NormalisedFrame:
    if len(frame.timestamps) < 2:
        return frame
    start = frame.timestamps[0]
    duration = (frame.timestamps[-1] - start).total_seconds()
    target_count = int(floor(duration / period_seconds + 1e-9)) + 1
    timestamps = [
        start + timedelta(seconds=index * period_seconds) for index in range(target_count)
    ]
    bins: list[list[int]] = [[] for _ in timestamps]
    for source_index, timestamp in enumerate(frame.timestamps):
        ratio = (timestamp - start).total_seconds() / period_seconds
        nearest = int(floor(ratio + 0.5))
        if 0 <= nearest < target_count and abs(ratio - nearest) <= 0.5 + 1e-9:
            bins[nearest].append(source_index)
    numeric: dict[str, list[float | None]] = {}
    for column, values in frame.numeric.items():
        numeric[column] = [
            _mean_finite([values[index] for index in bucket]) if bucket else None for bucket in bins
        ]
    categorical: dict[str, list[str | None]] = {}
    for column, labels in frame.categorical.items():
        categorical[column] = [
            _first_present([labels[index] for index in bucket]) if bucket else None
            for bucket in bins
        ]
    return _NormalisedFrame(timestamps=timestamps, numeric=numeric, categorical=categorical)


def _interpolate_missing(
    values: Sequence[float | None],
    *,
    method: InterpolationMethod,
    max_consecutive_missing: int | None,
) -> tuple[list[float | None], set[int]]:
    result = list(values)
    changes: set[int] = set()
    if method == "none":
        return result, changes
    index = 0
    while index < len(result):
        if result[index] is not None:
            index += 1
            continue
        start = index
        while index < len(result) and result[index] is None:
            index += 1
        end = index
        length = end - start
        if max_consecutive_missing is not None and length > max_consecutive_missing:
            continue
        left = result[start - 1] if start > 0 else None
        right = result[end] if end < len(result) else None
        if method == "linear" and left is not None and right is not None:
            for offset in range(length):
                result[start + offset] = left + (right - left) * (offset + 1) / (length + 1)
                changes.add(start + offset)
        elif method == "ffill" and left is not None:
            for position in range(start, end):
                result[position] = left
                changes.add(position)
        elif method == "bfill" and right is not None:
            for position in range(start, end):
                result[position] = right
                changes.add(position)
    return result, changes


def _detect_outliers(
    values: Sequence[float | None],
    *,
    detector: OutlierDetector,
    hampel_window: int,
    hampel_threshold: float,
    z_score_threshold: float,
) -> list[DetectedOutlier]:
    if detector == "hampel":
        return _hampel_outliers(values, window=hampel_window, threshold=hampel_threshold)
    finite = np.asarray([value for value in values if value is not None], dtype=float)
    if finite.size < 4:
        return []
    median = float(np.median(finite))
    if detector == "iqr":
        q25, q75 = np.quantile(finite, [0.25, 0.75])
        iqr = q75 - q25
        if isclose(float(iqr), 0.0):
            return []
        lower, upper = float(q25 - 1.5 * iqr), float(q75 + 1.5 * iqr)
    else:
        mean, std = float(np.mean(finite)), float(np.std(finite, ddof=1))
        if isclose(std, 0.0):
            return []
        lower, upper = mean - z_score_threshold * std, mean + z_score_threshold * std
    return [
        DetectedOutlier(index=index, median=median, lower_bound=lower, upper_bound=upper)
        for index, value in enumerate(values)
        if value is not None and (value < lower or value > upper)
    ]


def _hampel_outliers(
    values: Sequence[float | None], *, window: int, threshold: float
) -> list[DetectedOutlier]:
    half_window = max(1, window // 2)
    detected: list[DetectedOutlier] = []
    for index, value in enumerate(values):
        if value is None:
            continue
        local = [
            candidate
            for candidate in values[
                max(0, index - half_window) : min(len(values), index + half_window + 1)
            ]
            if candidate is not None
        ]
        if len(local) < 3:
            continue
        median = float(np.median(np.asarray(local, dtype=float)))
        mad = float(np.median(np.abs(np.asarray(local, dtype=float) - median)))
        if isclose(mad, 0.0):
            if not isclose(value, median, rel_tol=1e-9, abs_tol=1e-12):
                detected.append(
                    DetectedOutlier(
                        index=index, median=median, lower_bound=median, upper_bound=median
                    )
                )
            continue
        robust_sigma = 1.4826 * mad
        lower, upper = median - threshold * robust_sigma, median + threshold * robust_sigma
        if value < lower or value > upper:
            detected.append(
                DetectedOutlier(index=index, median=median, lower_bound=lower, upper_bound=upper)
            )
    return detected


def _treat_outliers(
    values: Sequence[float | None],
    outliers: Sequence[DetectedOutlier],
    *,
    strategy: OutlierStrategy,
    interpolation: InterpolationMethod,
    max_consecutive_missing: int | None,
) -> tuple[list[float | None], set[int]]:
    result = list(values)
    changes: set[int] = set()
    if strategy == "keep":
        return result, changes
    for outlier in outliers:
        original = result[outlier.index]
        if strategy == "set_null" or strategy == "linear_interpolate":
            result[outlier.index] = None
        elif strategy == "local_median":
            result[outlier.index] = outlier.median
        else:
            assert original is not None
            result[outlier.index] = min(max(original, outlier.lower_bound), outlier.upper_bound)
        if result[outlier.index] != original:
            changes.add(outlier.index)
    if strategy == "linear_interpolate" and outliers:
        resolved_method: InterpolationMethod = (
            "linear" if interpolation == "none" else interpolation
        )
        interpolated, interpolation_changes = _interpolate_missing(
            result,
            method=resolved_method,
            max_consecutive_missing=max_consecutive_missing,
        )
        result = interpolated
        changes.update(interpolation_changes)
    return result, changes


def _smooth(
    values: Sequence[float | None], *, method: SmoothingMethod, window: int
) -> tuple[list[float | None], set[int]]:
    if method == "none":
        return list(values), set()
    normalised_window = window if window % 2 else window + 1
    result = list(values)
    changes: set[int] = set()
    half_window = normalised_window // 2
    for index, value in enumerate(values):
        if value is None:
            continue
        start, end = max(0, index - half_window), min(len(values), index + half_window + 1)
        local = [
            (position, candidate)
            for position, candidate in enumerate(values[start:end], start)
            if candidate is not None
        ]
        if len(local) < 3:
            continue
        if method == "moving_average":
            replacement = float(np.mean([candidate for _, candidate in local]))
        else:
            positions = np.asarray([position - index for position, _ in local], dtype=float)
            candidates = np.asarray([candidate for _, candidate in local], dtype=float)
            degree = min(2, len(local) - 1)
            replacement = float(np.polyfit(positions, candidates, degree)[-1])
        if not isclose(replacement, value, rel_tol=1e-12, abs_tol=1e-12):
            result[index] = replacement
            changes.add(index)
    return result, changes


def _frozen_segments(column: str, values: Sequence[float | None]) -> list[dict[str, int | str]]:
    segments: list[dict[str, int | str]] = []
    start: int | None = None
    previous: float | None = None
    for index, value in enumerate(values):
        if value is None:
            _append_segment(segments, column, start, index - 1)
            start, previous = None, None
        elif previous is not None and isclose(value, previous, rel_tol=1e-9, abs_tol=1e-12):
            if start is None:
                start = index - 1
            previous = value
        else:
            _append_segment(segments, column, start, index - 1)
            start, previous = None, value
    _append_segment(segments, column, start, len(values) - 1)
    return segments


def _append_segment(
    segments: list[dict[str, int | str]], column: str, start: int | None, end: int
) -> None:
    if start is None or end - start + 1 < 5:
        return
    segments.append(
        {
            "column": column,
            "start_index": start,
            "end_index": end,
            "length": end - start + 1,
        }
    )


def _to_float(value: str | None) -> float | None:
    if is_missing(value):
        return None
    try:
        numeric = float(value.strip()) if value is not None else float("nan")
    except ValueError:
        return None
    return numeric if isfinite(numeric) else None


def _to_categorical(value: str | None) -> str | None:
    return None if is_missing(value) else value


def _aggregate_numeric(values: Sequence[float | None], strategy: DuplicateStrategy) -> float | None:
    if strategy == "first":
        return values[0] if values else None
    return _mean_finite(values)


def _mean_finite(values: Sequence[float | None]) -> float | None:
    finite = [value for value in values if value is not None]
    return float(np.mean(finite)) if finite else None


def _aggregate_categorical(values: Sequence[str | None]) -> str | None:
    return values[0] if values else None


def _first_present(values: Sequence[str | None]) -> str | None:
    return next((value for value in values if value is not None), None)
