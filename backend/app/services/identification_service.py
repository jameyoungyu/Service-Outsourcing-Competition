"""Deterministic MISO ARX identification, partitioned evaluation and model artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from app.schemas.modeling import (
    ArxFitRequest,
    ArxMetrics,
    ArxPlotData,
    ArxResidualDiagnostics,
    SplitIndices,
)
from app.services.simulation_service import (
    SimulationArtifactNotFoundError,
    SimulationDataset,
    load_simulation_by_version,
)

FloatArray = NDArray[np.float64]


class ArxDomainError(Exception):
    """Stable algorithm error suitable for mapping to an API ErrorEnvelope."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class ArxFitResult:
    model_id: UUID
    dataset_id: UUID
    version_id: UUID
    estimator: Literal["ols", "ridge"]
    coefficients: dict[str, float]
    a_coefficients: list[float]
    b_coefficients: dict[str, list[float]]
    metrics: ArxMetrics
    plot_data: ArxPlotData
    residual_diagnostics: ArxResidualDiagnostics
    artifact_uri: str


def fit_arx(payload: ArxFitRequest, *, artifact_root: Path) -> ArxFitResult:
    """Fit a one-step MISO ARX baseline using only train data and chronological splits."""

    try:
        dataset = load_simulation_by_version(payload.version_id, artifact_root=artifact_root)
    except SimulationArtifactNotFoundError as error:
        raise ArxDomainError(
            "DATASET_VERSION_NOT_FOUND",
            "数据版本不存在或不是本地仿真产物",
            {"version_id": str(payload.version_id)},
        ) from error
    if payload.dataset_id is not None and payload.dataset_id != dataset.dataset_id:
        raise ArxDomainError(
            "DATASET_VERSION_MISMATCH",
            "数据集 ID 与数据版本不匹配",
            {"dataset_id": str(payload.dataset_id), "version_id": str(payload.version_id)},
        )
    input_columns = _resolve_input_columns(payload, dataset)
    nb = _normalize_orders(payload.nb, input_columns, name="nb", minimum=1)
    delays = _normalize_orders(payload.delays, input_columns, name="delays", minimum=0)
    estimator = payload.resolved_estimator()
    rows = _build_design_rows(
        dataset,
        input_columns=input_columns,
        output_column=payload.output_column,
        na=payload.na,
        nb=nb,
        delays=delays,
        train_ratio=payload.train_ratio,
        validation_ratio=payload.validation_ratio,
    )
    train_features, train_targets = _select_partition(rows, "train")
    if train_features.shape[0] < train_features.shape[1] * 3:
        raise ArxDomainError(
            "INSUFFICIENT_ROWS",
            "训练集有效样本不足以稳定估计 ARX 参数",
            {
                "required": int(train_features.shape[1] * 3),
                "actual": int(train_features.shape[0]),
            },
        )
    rank = int(np.linalg.matrix_rank(train_features))
    if estimator == "ols" and rank < train_features.shape[1]:
        raise ArxDomainError(
            "DESIGN_MATRIX_RANK_DEFICIENT",
            "ARX 设计矩阵秩不足，请减少共线变量或选择 Ridge",
            {"rank": rank, "features": int(train_features.shape[1])},
        )
    theta = _estimate_parameters(
        train_features,
        train_targets,
        estimator=estimator,
        ridge_alpha=payload.ridge_alpha,
    )
    predicted = rows.features @ theta
    residuals = rows.targets - predicted
    metrics = _partition_metrics(rows.partition_labels, rows.targets, predicted)
    feature_names = _feature_names(input_columns, payload.na, nb)
    coefficients = {name: float(value) for name, value in zip(feature_names, theta, strict=True)}
    a_coefficients = [coefficients[f"a{position}"] for position in range(1, payload.na + 1)]
    b_coefficients = {
        column: [coefficients[f"b_{column}_{lag}"] for lag in range(nb[column])]
        for column in input_columns
    }
    split_indices = SplitIndices(
        train_end=rows.train_boundary,
        val_end=rows.validation_boundary,
        test_end=rows.n_samples,
    )
    plot_data = ArxPlotData(
        indices=[int(value) for value in rows.time_indices],
        y_true=[float(value) for value in rows.targets],
        y_pred=[float(value) for value in predicted],
        residuals=[float(value) for value in residuals],
        splits=split_indices,
        split_indices=split_indices,
    )
    diagnostic = _residual_diagnostics(residuals)
    model_id = uuid4()
    artifact_uri = _persist_model_result(
        artifact_root,
        model_id=model_id,
        dataset=dataset,
        payload=payload,
        estimator=estimator,
        coefficients=coefficients,
        metrics=metrics,
    )
    return ArxFitResult(
        model_id=model_id,
        dataset_id=dataset.dataset_id,
        version_id=dataset.version_id,
        estimator=estimator,
        coefficients=coefficients,
        a_coefficients=a_coefficients,
        b_coefficients=b_coefficients,
        metrics=metrics,
        plot_data=plot_data,
        residual_diagnostics=diagnostic,
        artifact_uri=artifact_uri,
    )


@dataclass(frozen=True)
class _DesignRows:
    features: FloatArray
    targets: FloatArray
    time_indices: NDArray[np.int_]
    partition_labels: list[Literal["train", "validation", "test"]]
    train_boundary: int
    validation_boundary: int
    n_samples: int


def _resolve_input_columns(payload: ArxFitRequest, dataset: SimulationDataset) -> list[str]:
    available = sorted(column for column in dataset.values if column.startswith("u"))
    input_columns = payload.input_columns or available
    invalid = sorted(set(input_columns) - set(available))
    if invalid:
        raise ArxDomainError(
            "INVALID_DATASET_SCHEMA",
            "请求的输入变量不存在",
            {"invalid_columns": invalid, "available_columns": available},
        )
    if not input_columns:
        raise ArxDomainError(
            "INVALID_DATASET_SCHEMA",
            "数据集不包含可用输入变量",
            {"available_columns": sorted(dataset.values)},
        )
    if payload.output_column not in dataset.values:
        raise ArxDomainError(
            "INVALID_DATASET_SCHEMA",
            "请求的输出变量不存在",
            {"output_column": payload.output_column, "available_columns": sorted(dataset.values)},
        )
    return input_columns


def _normalize_orders(
    value: dict[str, int] | list[int],
    input_columns: list[str],
    *,
    name: str,
    minimum: int,
) -> dict[str, int]:
    if isinstance(value, list):
        if len(value) != len(input_columns):
            raise ArxDomainError(
                "PARAMETER_OUT_OF_RANGE",
                f"{name} 数组长度必须与输入变量数量一致",
                {"parameter": name, "expected": len(input_columns), "actual": len(value)},
            )
        normalized = dict(zip(input_columns, value, strict=True))
    else:
        missing = sorted(set(input_columns) - set(value))
        extras = sorted(set(value) - set(input_columns))
        if missing or extras:
            raise ArxDomainError(
                "PARAMETER_OUT_OF_RANGE",
                f"{name} 字典必须与输入变量一一对应",
                {"parameter": name, "missing": missing, "extra": extras},
            )
        normalized = value
    invalid = {column: order for column, order in normalized.items() if order < minimum}
    if invalid:
        raise ArxDomainError(
            "PARAMETER_OUT_OF_RANGE",
            f"{name} 包含低于下限的值",
            {"parameter": name, "minimum": minimum, "invalid": invalid},
        )
    return normalized


def _build_design_rows(
    dataset: SimulationDataset,
    *,
    input_columns: list[str],
    output_column: str,
    na: int,
    nb: dict[str, int],
    delays: dict[str, int],
    train_ratio: float,
    validation_ratio: float,
) -> _DesignRows:
    if train_ratio + validation_ratio >= 1:
        raise ArxDomainError(
            "PARAMETER_OUT_OF_RANGE",
            "训练集与验证集比例之和必须小于 1",
            {"train_ratio": train_ratio, "validation_ratio": validation_ratio},
        )
    output = dataset.values[output_column]
    n_samples = len(output)
    max_history = max(na, max(delays[column] + nb[column] - 1 for column in input_columns))
    train_boundary = int(n_samples * train_ratio)
    validation_boundary = int(n_samples * (train_ratio + validation_ratio))
    guard = max_history
    feature_rows: list[FloatArray] = []
    targets: list[float] = []
    time_indices: list[int] = []
    labels: list[Literal["train", "validation", "test"]] = []
    for time_index in range(max_history, n_samples):
        partition = _partition_for_time(
            time_index,
            train_boundary=train_boundary,
            validation_boundary=validation_boundary,
            guard=guard,
        )
        if partition is None:
            continue
        features = [-float(output[time_index - lag]) for lag in range(1, na + 1)]
        for column in input_columns:
            signal = dataset.values[column]
            features.extend(
                float(signal[time_index - delays[column] - lag]) for lag in range(nb[column])
            )
        target = float(output[time_index])
        feature_array = np.asarray(features, dtype=float)
        if not np.isfinite(target) or not np.all(np.isfinite(feature_array)):
            continue
        feature_rows.append(feature_array)
        targets.append(target)
        time_indices.append(time_index)
        labels.append(partition)
    if not feature_rows:
        raise ArxDomainError(
            "INSUFFICIENT_ROWS",
            "没有足够的有限值样本构造 ARX 回归矩阵",
            {"n_samples": n_samples, "max_history": max_history},
        )
    return _DesignRows(
        features=np.vstack(feature_rows),
        targets=np.asarray(targets, dtype=float),
        time_indices=np.asarray(time_indices, dtype=int),
        partition_labels=labels,
        train_boundary=train_boundary,
        validation_boundary=validation_boundary,
        n_samples=n_samples,
    )


def _partition_for_time(
    time_index: int,
    *,
    train_boundary: int,
    validation_boundary: int,
    guard: int,
) -> Literal["train", "validation", "test"] | None:
    if time_index < train_boundary - guard:
        return "train"
    if train_boundary + guard <= time_index < validation_boundary - guard:
        return "validation"
    if time_index >= validation_boundary + guard:
        return "test"
    return None


def _select_partition(rows: _DesignRows, partition: str) -> tuple[FloatArray, FloatArray]:
    positions = [index for index, label in enumerate(rows.partition_labels) if label == partition]
    if not positions:
        raise ArxDomainError(
            "INSUFFICIENT_ROWS",
            "指定时间分区没有足够的有效样本",
            {"partition": partition},
        )
    index_array = np.asarray(positions, dtype=int)
    return rows.features[index_array], rows.targets[index_array]


def _estimate_parameters(
    features: FloatArray,
    targets: FloatArray,
    *,
    estimator: Literal["ols", "ridge"],
    ridge_alpha: float | None,
) -> FloatArray:
    try:
        if estimator == "ols":
            estimate, _, _, _ = np.linalg.lstsq(features, targets, rcond=None)
            return np.asarray(estimate, dtype=float)
        alpha = ridge_alpha if ridge_alpha is not None else 1.0
        regularizer = np.eye(features.shape[1], dtype=float) * alpha
        return np.asarray(
            np.linalg.solve(features.T @ features + regularizer, features.T @ targets),
            dtype=float,
        )
    except np.linalg.LinAlgError as error:
        raise ArxDomainError(
            "NUMERICAL_INSTABILITY",
            "ARX 数值求解失败",
            {"estimator": estimator},
        ) from error


def _feature_names(input_columns: list[str], na: int, nb: dict[str, int]) -> list[str]:
    names = [f"a{position}" for position in range(1, na + 1)]
    for column in input_columns:
        names.extend(f"b_{column}_{lag}" for lag in range(nb[column]))
    return names


def _partition_metrics(
    labels: list[Literal["train", "validation", "test"]],
    actual: FloatArray,
    predicted: FloatArray,
) -> ArxMetrics:
    values = {
        label: _metric_values(
            actual[
                np.asarray([index for index, item in enumerate(labels) if item == label], dtype=int)
            ],
            predicted[
                np.asarray([index for index, item in enumerate(labels) if item == label], dtype=int)
            ],
        )
        for label in ("train", "validation", "test")
    }
    test_values = values["test"]
    return ArxMetrics(
        train_r2=values["train"]["r2"],
        train_fit=values["train"]["fit"],
        train_rmse=values["train"]["rmse"],
        val_r2=values["validation"]["r2"],
        val_fit=values["validation"]["fit"],
        val_rmse=values["validation"]["rmse"],
        test_r2=test_values["r2"],
        test_fit=test_values["fit"],
        test_rmse=test_values["rmse"],
        rmse=test_values["rmse"],
        mae=test_values["mae"],
        nrmse=test_values["nrmse"],
    )


def _metric_values(actual: FloatArray, predicted: FloatArray) -> dict[str, float | None]:
    if len(actual) == 0:
        return {"rmse": None, "mae": None, "r2": None, "fit": None, "nrmse": None}
    residual = actual - predicted
    rmse = float(np.sqrt(np.mean(np.square(residual))))
    mae = float(np.mean(np.abs(residual)))
    centered = actual - np.mean(actual)
    denominator = float(np.dot(centered, centered))
    r2 = None if denominator == 0 else float(1 - np.dot(residual, residual) / denominator)
    norm = float(np.linalg.norm(centered))
    fit = None if norm == 0 else float(100 * (1 - np.linalg.norm(residual) / norm))
    robust_range = float(np.percentile(actual, 95) - np.percentile(actual, 5))
    nrmse = None if robust_range == 0 else float(rmse / robust_range)
    return {"rmse": rmse, "mae": mae, "r2": r2, "fit": fit, "nrmse": nrmse}


def _residual_diagnostics(residuals: FloatArray) -> ArxResidualDiagnostics:
    centered = residuals - np.mean(residuals)
    denominator = float(np.dot(centered, centered))
    max_lag = min(40, max(0, len(centered) - 1))
    if denominator == 0:
        values = [1.0] + [0.0] * max_lag
    else:
        values = [1.0]
        values.extend(
            float(np.dot(centered[:-lag], centered[lag:]) / denominator)
            for lag in range(1, max_lag + 1)
        )
    confidence = None if len(residuals) == 0 else float(1.96 / np.sqrt(len(residuals)))
    return ArxResidualDiagnostics(acf_values=values, confidence_interval=confidence)


def _persist_model_result(
    artifact_root: Path,
    *,
    model_id: UUID,
    dataset: SimulationDataset,
    payload: ArxFitRequest,
    estimator: Literal["ols", "ridge"],
    coefficients: dict[str, float],
    metrics: ArxMetrics,
) -> str:
    models_root = artifact_root / "models"
    models_root.mkdir(parents=True, exist_ok=True)
    path = models_root / f"{model_id}.json"
    document = {
        "model_id": str(model_id),
        "dataset_id": str(dataset.dataset_id),
        "version_id": str(dataset.version_id),
        "scenario": dataset.scenario,
        "estimator": estimator,
        "configuration": payload.model_dump(mode="json"),
        "coefficients": coefficients,
        "metrics": metrics.model_dump(mode="json"),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path.relative_to(artifact_root).as_posix()
