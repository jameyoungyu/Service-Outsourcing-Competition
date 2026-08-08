"""MISO ARX identification with control-relevant acceptance (phase 7).

The core here is pure: arrays in, coefficients and metrics out. ``identification_service``
reuses it for the simulation path, the route uses the async wrapper for any version, and
the closed-loop optimiser calls it directly thousands of times, so it must not touch the
database or the filesystem.

Two things differ from a textbook least-squares fit:

* **Free-run simulation is the primary metric.** One-step-ahead prediction is fed the
  measured ``y(k-1)``, so on an autocorrelated process a badly identified model still
  scores above 95% by copying the previous sample. The closed loop optimises the free-run
  number; the one-step number is kept as a diagnostic, and their gap is itself a warning.
* **Engineering priors are hard constraints.** A steady-state gain with the wrong sign is
  not a slightly worse model, it is a wrong one, and reporting it as a success would cost
  the engineer more time than returning nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import numpy as np
from algorithms.identifiability.regressor import (
    ArxStructure,
    FloatArray,
    IdentifiabilityError,
    RegressorMatrix,
    build_regressor,
)
from algorithms.identifiability.validation import (
    ModelValidation,
    fit_percentage,
    free_run_simulate,
    is_stable,
    residual_whiteness_ratio,
    steady_state_gains,
    validate_model,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.models.operation_log import OperationLog
from app.schemas.modeling import (
    ArxFitData,
    ArxFitRequest,
    ArxMetrics,
    ArxPlotData,
    ArxResidualDiagnostics,
    ModelValidationData,
    PriorViolation,
    SplitIndices,
)
from app.services.contract_stubs import completed_task
from app.services.version_data import VersionDataError, VersionSeries, load_version_series

MAX_PLOT_POINTS = 6_000


class ModelingDomainError(Exception):
    """A client-safe identification failure for the standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class ArxCoreResult:
    """Everything one identification run produces, before persistence."""

    structure: ArxStructure
    theta: FloatArray
    coefficients: dict[str, float]
    a_coefficients: list[float]
    b_coefficients: dict[str, list[float]]
    metrics: ArxMetrics
    plot_data: ArxPlotData
    residual_diagnostics: ArxResidualDiagnostics
    validation: ModelValidation
    prior_violations: tuple[PriorViolation, ...]
    training_rows: int
    free_run_series: list[float]
    input_columns: list[str]
    output_column: str
    estimator: Literal["ols", "ridge"]

    @property
    def objective_fit(self) -> float:
        """The number the closed loop maximises: validation free-run FIT."""

        value = self.metrics.val_free_run_fit
        return float(value) if value is not None and np.isfinite(value) else float("-inf")


def fit_arx_core(
    *,
    inputs: dict[str, FloatArray],
    output: FloatArray,
    payload: ArxFitRequest,
    input_columns: list[str],
) -> ArxCoreResult:
    """Fit ARX on the training split and evaluate every partition two ways."""

    structure = _structure(payload, input_columns)
    n_samples = int(np.asarray(output, dtype=float).shape[0])
    train_end = int(n_samples * payload.train_ratio)
    val_end = int(n_samples * (payload.train_ratio + payload.validation_ratio))
    if val_end >= n_samples:
        raise ModelingDomainError(
            "PARAMETER_OUT_OF_RANGE",
            "训练集与验证集比例之和必须小于 1。",
            details={
                "train_ratio": payload.train_ratio,
                "validation_ratio": payload.validation_ratio,
            },
        )

    try:
        full = build_regressor(inputs=inputs, output=output, structure=structure)
    except IdentifiabilityError as error:
        raise ModelingDomainError(error.code, error.message, details=error.details) from error

    guard = structure.max_history
    train_rows = _partition_rows(full, 0, train_end - guard)
    if payload.training_sample_indices:
        allowed = set(int(value) for value in payload.training_sample_indices)
        train_rows = np.asarray(
            [row for row in train_rows if int(full.time_indices[row]) in allowed], dtype=int
        )
    if train_rows.size <= full.n_parameters * 2:
        raise ModelingDomainError(
            "INSUFFICIENT_ROWS",
            "训练样本不足以稳定估计 ARX 参数。",
            details={"required": full.n_parameters * 2 + 1, "actual": int(train_rows.size)},
        )

    train_features = full.features[train_rows]
    train_targets = full.targets[train_rows]
    estimator = payload.resolved_estimator()
    rank = int(np.linalg.matrix_rank(train_features))
    if estimator == "ols" and rank < train_features.shape[1]:
        raise ModelingDomainError(
            "DESIGN_MATRIX_RANK_DEFICIENT",
            "ARX 设计矩阵秩不足，请减少共线变量或改用 Ridge。",
            details={"rank": rank, "features": int(train_features.shape[1])},
        )
    theta = _estimate(train_features, train_targets, estimator, payload.ridge_alpha)

    predicted = full.features @ theta
    residuals = full.targets - predicted
    metrics = _metrics(
        full,
        theta=theta,
        structure=structure,
        inputs=inputs,
        output=output,
        train_end=train_end,
        val_end=val_end,
        n_samples=n_samples,
        train_rows=train_rows,
    )
    validation = validate_model(
        theta,
        structure,
        inputs=inputs,
        output=output,
        start=train_end,
        stop=val_end,
    )
    violations = _check_priors(theta, structure, payload, validation)
    _, free_run = free_run_simulate(
        theta, structure, inputs=inputs, output=output, start=0, stop=n_samples
    )

    names = structure.feature_names()
    coefficients = {name: float(value) for name, value in zip(names, theta, strict=True)}
    stride = max(1, full.n_rows // MAX_PLOT_POINTS)
    return ArxCoreResult(
        structure=structure,
        theta=theta,
        coefficients=coefficients,
        a_coefficients=[coefficients[f"a{i}"] for i in range(1, structure.na + 1)],
        b_coefficients={
            column: [coefficients[f"b_{column}_{lag}"] for lag in range(structure.nb[column])]
            for column in input_columns
        },
        metrics=metrics,
        plot_data=ArxPlotData(
            indices=[int(v) for v in full.time_indices[::stride]],
            y_true=[float(v) for v in full.targets[::stride]],
            y_pred=[float(v) for v in predicted[::stride]],
            residuals=[float(v) for v in residuals[::stride]],
            splits=SplitIndices(train_end=train_end, val_end=val_end, test_end=n_samples),
            split_indices=SplitIndices(train_end=train_end, val_end=val_end, test_end=n_samples),
        ),
        residual_diagnostics=_acf(residuals),
        validation=validation,
        prior_violations=violations,
        training_rows=int(train_rows.size),
        free_run_series=[float(v) for v in free_run[::stride]],
        input_columns=list(input_columns),
        output_column=payload.output_column,
        estimator=estimator,
    )


async def fit_arx_on_version(
    session: AsyncSession,
    *,
    payload: ArxFitRequest,
    artifact_root: Path,
) -> ArxFitData:
    """Load any version, identify, validate against priors and persist the run."""

    try:
        series = await load_version_series(
            session,
            version_id=payload.version_id,
            artifact_root=artifact_root,
            dataset_id=payload.dataset_id,
        )
        input_columns, output_column = series.resolve_columns(
            input_columns=payload.input_columns or None,
            output_column=payload.output_column,
        )
    except VersionDataError as error:
        raise ModelingDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error

    resolved = payload.model_copy(update={"output_column": output_column})
    result = fit_arx_core(
        inputs={column: series.values[column] for column in input_columns},
        output=series.values[output_column],
        payload=resolved,
        input_columns=input_columns,
    )
    if result.prior_violations:
        raise ModelingDomainError(
            "PRIOR_CONSTRAINT_VIOLATED",
            "辨识结果与工程先验冲突，模型未入库。",
            details={
                "violations": [
                    violation.model_dump(mode="json") for violation in result.prior_violations
                ]
            },
        )
    if payload.require_stable and not result.validation.stable:
        raise ModelingDomainError(
            "MODEL_UNSTABLE",
            "A(q) 存在单位圆外极点，模型不稳定，未入库。",
            details={"max_pole_modulus": result.validation.max_pole_modulus},
        )

    model_id = uuid4()
    artifact_uri = _persist_artifact(
        artifact_root, model_id=model_id, series=series, payload=resolved, result=result
    )
    await _persist_run(session, model_id=model_id, series=series, payload=resolved, result=result)

    return ArxFitData(
        model_id=model_id,
        task=completed_task(
            stage="fit_arx",
            message="ARX 辨识、自由仿真评价与先验校验已完成。",
        ),
        estimator=result.estimator,
        dataset_id=series.dataset_id,
        version_id=series.version_id,
        coefficients=result.coefficients,
        a_coefficients=result.a_coefficients,
        b_coefficients=result.b_coefficients,
        metrics=result.metrics,
        plot_data=result.plot_data,
        residual_diagnostics=result.residual_diagnostics,
        artifact_uri=artifact_uri,
        validation=to_validation_data(result.validation),
        prior_violations=list(result.prior_violations),
        training_rows=result.training_rows,
        free_run_series=result.free_run_series,
    )


def to_validation_data(validation: ModelValidation) -> ModelValidationData:
    return ModelValidationData(
        one_step_fit=_finite(validation.one_step_fit),
        free_run_fit=_finite(validation.free_run_fit),
        free_run_rmse=_finite(validation.free_run_rmse),
        fit_gap=_finite(validation.fit_gap),
        stable=validation.stable,
        max_pole_modulus=_finite(validation.max_pole_modulus),
        steady_state_gains={
            column: value
            for column, value in validation.steady_state_gains.items()
            if np.isfinite(value)
        },
        residual_whiteness_ratio=_finite(validation.residual_whiteness_ratio),
        n_samples=validation.n_samples,
    )


def _structure(payload: ArxFitRequest, input_columns: list[str]) -> ArxStructure:
    try:
        return ArxStructure.create(
            na=payload.na,
            nb=_orders(payload.nb, input_columns, "nb", 1),
            nk=_orders(payload.delays, input_columns, "delays", 0),
            input_columns=tuple(input_columns),
        )
    except IdentifiabilityError as error:
        raise ModelingDomainError(error.code, error.message, details=error.details) from error


def _orders(
    value: dict[str, int] | list[int],
    columns: list[str],
    name: str,
    minimum: int,
) -> dict[str, int]:
    if isinstance(value, list):
        if len(value) != len(columns):
            raise ModelingDomainError(
                "PARAMETER_OUT_OF_RANGE",
                f"{name} 数组长度必须与输入变量数量一致。",
                details={"parameter": name, "expected": len(columns), "actual": len(value)},
            )
        return dict(zip(columns, value, strict=True))
    missing = sorted(set(columns) - set(value))
    if missing:
        raise ModelingDomainError(
            "PARAMETER_OUT_OF_RANGE",
            f"{name} 必须覆盖全部输入变量。",
            details={"parameter": name, "missing": missing},
        )
    return {column: int(value[column]) for column in columns}


def _partition_rows(regressor: RegressorMatrix, start: int, stop: int) -> np.ndarray:
    times = regressor.time_indices
    return np.nonzero((times >= start) & (times < stop))[0]


def _estimate(
    features: FloatArray,
    targets: FloatArray,
    estimator: Literal["ols", "ridge"],
    ridge_alpha: float | None,
) -> FloatArray:
    try:
        if estimator == "ols":
            solution, _, _, _ = np.linalg.lstsq(features, targets, rcond=None)
            return np.asarray(solution, dtype=float)
        alpha = 1.0 if ridge_alpha is None else ridge_alpha
        regulariser = alpha * np.eye(features.shape[1], dtype=float)
        return np.asarray(
            np.linalg.solve(features.T @ features + regulariser, features.T @ targets),
            dtype=float,
        )
    except np.linalg.LinAlgError as error:
        raise ModelingDomainError(
            "NUMERICAL_INSTABILITY", "ARX 数值求解失败。", details={"estimator": estimator}
        ) from error


def _metrics(
    regressor: RegressorMatrix,
    *,
    theta: FloatArray,
    structure: ArxStructure,
    inputs: dict[str, FloatArray],
    output: FloatArray,
    train_end: int,
    val_end: int,
    n_samples: int,
    train_rows: np.ndarray,
) -> ArxMetrics:
    predicted = regressor.features @ theta
    guard = structure.max_history
    windows = {
        "train": (0, max(train_end - guard, 0)),
        "validation": (train_end + guard, max(val_end - guard, train_end + guard)),
        "test": (val_end + guard, n_samples),
    }
    one_step: dict[str, dict[str, float | None]] = {}
    free_run: dict[str, float | None] = {}
    for label, (start, stop) in windows.items():
        rows = _partition_rows(regressor, start, stop)
        one_step[label] = _scores(regressor.targets[rows], predicted[rows])
        free_run[label] = _free_run_fit(
            theta, structure, inputs=inputs, output=output, start=start, stop=stop
        )

    residual = regressor.targets[train_rows] - predicted[train_rows]
    rss = float(np.dot(residual, residual))
    n_train = int(train_rows.size)
    parameters = int(regressor.n_parameters)
    aic: float | None = None
    bic: float | None = None
    if rss > 0 and n_train > 0:
        aic = n_train * float(np.log(rss / n_train)) + 2 * parameters
        bic = n_train * float(np.log(rss / n_train)) + parameters * float(np.log(n_train))

    test = one_step["test"]
    return ArxMetrics(
        train_r2=one_step["train"]["r2"],
        train_fit=one_step["train"]["fit"],
        train_rmse=one_step["train"]["rmse"],
        val_r2=one_step["validation"]["r2"],
        val_fit=one_step["validation"]["fit"],
        val_rmse=one_step["validation"]["rmse"],
        test_r2=test["r2"],
        test_fit=test["fit"],
        test_rmse=test["rmse"],
        rmse=test["rmse"],
        mae=test["mae"],
        nrmse=test["nrmse"],
        train_free_run_fit=free_run["train"],
        val_free_run_fit=free_run["validation"],
        test_free_run_fit=free_run["test"],
        aic=aic,
        bic=bic,
    )


def _free_run_fit(
    theta: FloatArray,
    structure: ArxStructure,
    *,
    inputs: dict[str, FloatArray],
    output: FloatArray,
    start: int,
    stop: int,
) -> float | None:
    try:
        measured, simulated = free_run_simulate(
            theta, structure, inputs=inputs, output=output, start=start, stop=stop
        )
        return fit_percentage(measured, simulated)
    except IdentifiabilityError:
        return None


def _scores(actual: FloatArray, predicted: FloatArray) -> dict[str, float | None]:
    if actual.size == 0:
        return {"rmse": None, "mae": None, "r2": None, "fit": None, "nrmse": None}
    residual = actual - predicted
    rmse = float(np.sqrt(np.mean(np.square(residual))))
    centered = actual - float(np.mean(actual))
    denominator = float(np.dot(centered, centered))
    norm = float(np.linalg.norm(centered))
    spread = float(np.percentile(actual, 95) - np.percentile(actual, 5))
    return {
        "rmse": rmse,
        "mae": float(np.mean(np.abs(residual))),
        "r2": None if denominator == 0 else float(1 - np.dot(residual, residual) / denominator),
        "fit": None if norm == 0 else float(100 * (1 - np.linalg.norm(residual) / norm)),
        "nrmse": None if spread == 0 else float(rmse / spread),
    }


def _acf(residuals: FloatArray) -> ArxResidualDiagnostics:
    centered = residuals - float(np.mean(residuals))
    denominator = float(np.dot(centered, centered))
    max_lag = min(40, max(0, centered.size - 1))
    if denominator == 0:
        values = [1.0] + [0.0] * max_lag
    else:
        values = [1.0]
        values.extend(
            float(np.dot(centered[:-lag], centered[lag:]) / denominator)
            for lag in range(1, max_lag + 1)
        )
    confidence = None if residuals.size == 0 else float(1.96 / np.sqrt(residuals.size))
    return ArxResidualDiagnostics(acf_values=values, confidence_interval=confidence)


def _check_priors(
    theta: FloatArray,
    structure: ArxStructure,
    payload: ArxFitRequest,
    validation: ModelValidation,
) -> tuple[PriorViolation, ...]:
    """Compare the identified model against what the engineer already knows."""

    violations: list[PriorViolation] = []
    gains = steady_state_gains(theta, structure)
    for column, sign in payload.gain_sign.items():
        gain = gains.get(column)
        if gain is None or not np.isfinite(gain):
            continue
        if (sign == "positive" and gain <= 0) or (sign == "negative" and gain >= 0):
            violations.append(
                PriorViolation(variable=column, kind="gain_sign", expected=sign, actual=float(gain))
            )
    for column, bounds in payload.gain_bounds.items():
        gain = gains.get(column)
        if gain is None or not np.isfinite(gain):
            continue
        low, high = float(bounds[0]), float(bounds[1])
        if not low <= gain <= high:
            violations.append(
                PriorViolation(
                    variable=column,
                    kind="gain_bounds",
                    expected=f"[{low}, {high}]",
                    actual=float(gain),
                )
            )
    if payload.require_stable and not validation.stable:
        violations.append(
            PriorViolation(
                variable="__model__",
                kind="stability",
                expected="all poles inside the unit circle",
                actual=validation.max_pole_modulus,
            )
        )
    return tuple(violations)


def _persist_artifact(
    artifact_root: Path,
    *,
    model_id: UUID,
    series: VersionSeries,
    payload: ArxFitRequest,
    result: ArxCoreResult,
) -> str:
    root = artifact_root / "models"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{model_id}.json"
    document = {
        "model_id": str(model_id),
        "dataset_id": str(series.dataset_id),
        "version_id": str(series.version_id),
        "origin": series.origin,
        "estimator": result.estimator,
        "configuration": payload.model_dump(mode="json"),
        "coefficients": result.coefficients,
        "metrics": result.metrics.model_dump(mode="json"),
        "validation": to_validation_data(result.validation).model_dump(mode="json"),
        "training_rows": result.training_rows,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path.relative_to(artifact_root).as_posix()


async def _persist_run(
    session: AsyncSession,
    *,
    model_id: UUID,
    series: VersionSeries,
    payload: ArxFitRequest,
    result: ArxCoreResult,
) -> None:
    now = datetime.now(UTC)
    session.add(
        ProcessingRun(
            id=uuid4(),
            dataset_id=series.dataset_id if series.origin == "dataset" else None,
            source_version_id=series.version_id if series.origin == "dataset" else None,
            run_type="modeling.arx",
            status="succeeded",
            parameters=payload.model_dump(mode="json"),
            result={
                "model_id": str(model_id),
                "metrics": result.metrics.model_dump(mode="json"),
                "validation": to_validation_data(result.validation).model_dump(mode="json"),
                "coefficients": result.coefficients,
                "training_rows": result.training_rows,
            },
            created_at=now,
            finished_at=now,
        )
    )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type="modeling.arx.completed",
            subject_id=str(series.dataset_id),
            payload_json=json.dumps(
                {
                    "model_id": str(model_id),
                    "version_id": str(series.version_id),
                    "val_free_run_fit": result.metrics.val_free_run_fit,
                    "val_one_step_fit": result.metrics.val_fit,
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
        )
    )
    await session.commit()


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) if np.isfinite(value) else None


__all__ = [
    "ArxCoreResult",
    "ModelingDomainError",
    "fit_arx_core",
    "fit_arx_on_version",
    "is_stable",
    "residual_whiteness_ratio",
    "to_validation_data",
]
