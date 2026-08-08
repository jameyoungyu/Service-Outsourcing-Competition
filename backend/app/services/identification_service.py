"""Simulation-artifact ARX entry point, kept as a thin adapter over the shared core.

Phase 2 introduced this module as the only identification path. Phase 7 generalised the
maths into ``modeling_service.fit_arx_core`` so it works on uploaded CSVs too and reports
free-run simulation alongside one-step prediction. This module now only resolves an S1-S6
artifact and delegates, so there is exactly one implementation of the regression.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from app.schemas.modeling import (
    ArxFitRequest,
    ArxMetrics,
    ArxPlotData,
    ArxResidualDiagnostics,
    ModelValidationData,
    PriorViolation,
)
from app.services.modeling_service import (
    ModelingDomainError,
    fit_arx_core,
    to_validation_data,
)
from app.services.simulation_service import (
    SimulationArtifactNotFoundError,
    SimulationDataset,
    load_simulation_by_version,
)


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
    validation: ModelValidationData | None = None
    prior_violations: tuple[PriorViolation, ...] = ()


def fit_arx(payload: ArxFitRequest, *, artifact_root: Path) -> ArxFitResult:
    """Fit a MISO ARX model on a local simulation artifact and persist the result."""

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
    if payload.output_column not in dataset.values:
        raise ArxDomainError(
            "INVALID_DATASET_SCHEMA",
            "请求的输出变量不存在",
            {
                "output_column": payload.output_column,
                "available_columns": sorted(dataset.values),
            },
        )

    try:
        result = fit_arx_core(
            inputs={column: dataset.values[column] for column in input_columns},
            output=dataset.values[payload.output_column],
            payload=payload,
            input_columns=input_columns,
        )
    except ModelingDomainError as error:
        raise ArxDomainError(error.code, error.message, error.details) from error

    model_id = uuid4()
    artifact_uri = _persist_model_result(
        artifact_root,
        model_id=model_id,
        dataset=dataset,
        payload=payload,
        estimator=result.estimator,
        coefficients=result.coefficients,
        metrics=result.metrics,
    )
    return ArxFitResult(
        model_id=model_id,
        dataset_id=dataset.dataset_id,
        version_id=dataset.version_id,
        estimator=result.estimator,
        coefficients=result.coefficients,
        a_coefficients=result.a_coefficients,
        b_coefficients=result.b_coefficients,
        metrics=result.metrics,
        plot_data=result.plot_data,
        residual_diagnostics=result.residual_diagnostics,
        artifact_uri=artifact_uri,
        validation=to_validation_data(result.validation),
        prior_violations=result.prior_violations,
    )


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
    return input_columns


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


__all__ = ["ArxDomainError", "ArxFitResult", "fit_arx"]
