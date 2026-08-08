"""Closed-loop preprocessing and structure search (phase 8).

The loop the brief asks for: pick preprocessing parameters, run the real pipeline, identify
a model, feed the identification metric back, and repeat until the best strategy is found.

Three things make it practical rather than merely correct:

* **The objective is validation free-run FIT**, not one-step prediction. Measured on the S6
  benchmark, one-step FIT spans 0.46 points across strategies where free-run spans 12.83,
  so optimising one-step is close to optimising noise.
* **Lineage-as-cache.** Consecutive trials usually change only model orders while the
  gating and selection parameters stay put; those stages are memoised by content-addressed
  key, so the expensive part runs once per distinct head configuration.
* **Strategy memory.** A finished study is stored against a profile fingerprint, and a new
  study on similar data enqueues those parameters as its first trials.

Test data never enters the objective. The best configuration is frozen first, and only then
are test metrics computed for reporting.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import optuna
from algorithms.pipeline.cache import LineageCache, stage_key
from algorithms.pipeline.fingerprint import (
    ProfileFingerprint,
    build_fingerprint,
    fingerprint_distance,
)
from optuna.samplers import TPESampler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_log import OperationLog
from app.models.optimization import OptimizationStudy, OptimizationTrialRecord, StrategyMemory
from app.schemas.modeling import ArxFitRequest
from app.schemas.optimization import (
    OptimizationStartData,
    OptimizationStartRequest,
    OptimizationStatusData,
    OptimizationTrial,
)
from app.schemas.preprocessing import SegmentRequest
from app.services.contract_stubs import completed_task
from app.services.modeling_service import ArxCoreResult, ModelingDomainError, fit_arx_core
from app.services.segment_service import SegmentDomainError, run_segment_selection
from app.services.version_data import VersionDataError, VersionSeries, load_version_series

TOOL_VERSION = "1.0.0"
# A study is only warm-started from memory entries at least this similar. Beyond it the
# stored parameters describe a different kind of process and would waste trials.
WARM_START_MAX_DISTANCE = 0.35
WARM_START_LIMIT = 3
# Quantisation of the gating thresholds in the search space. See _suggest() for why.
THRESHOLD_STEP = 0.02
# Bounds the gating ranges so that low/high are both multiples of THRESHOLD_STEP.
_GATING_BOUNDS = {
    "max_anomaly_ratio": (0.02, 0.30),
    "max_missing_ratio": (0.02, 0.40),
    "min_input_activity_ratio": (0.02, 0.30),
}

optuna.logging.set_verbosity(optuna.logging.WARNING)


class OptimizationDomainError(Exception):
    """A client-safe optimisation failure for the standard error envelope."""

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


@dataclass
class TrialOutcome:
    """One evaluated configuration and everything worth persisting about it."""

    number: int
    state: str
    value: float | None
    params: dict[str, Any]
    metrics: dict[str, Any]
    cache_hit: bool
    duration_ms: float
    error_code: str | None = None


@dataclass
class StudyOutcome:
    """The finished search: trials, winner, and how much work the cache saved."""

    study_id: UUID
    trials: list[TrialOutcome]
    best_number: int | None
    best_value: float | None
    best_params: dict[str, Any]
    best_metrics: dict[str, Any]
    fingerprint: ProfileFingerprint
    statistics: dict[str, Any]
    warm_started_from: UUID | None = None
    warm_start_params: list[dict[str, Any]] = field(default_factory=list)


def objective_value(result: ArxCoreResult) -> tuple[float, dict[str, Any]]:
    """Score a candidate model the way an APC engineer would rank it.

    Weights follow ALG-0.2 §7.1. Every term is bounded so a single pathological trial
    cannot dominate the search, and an unstable model is rejected outright rather than
    ranked, because no amount of fit makes an unstable model deployable.
    """

    free_run = result.metrics.val_free_run_fit
    if free_run is None or not np.isfinite(free_run):
        return float("-inf"), {"reason": "free_run_undefined"}
    if not result.validation.stable:
        return float("-inf"), {"reason": "unstable"}

    nrmse = result.metrics.val_rmse or 0.0
    spread = abs(result.metrics.val_fit or 0.0)
    normalised_error = nrmse / spread if spread > 0 else nrmse
    whiteness = result.validation.residual_whiteness_ratio
    whiteness = 1.0 if whiteness is None or not np.isfinite(whiteness) else whiteness
    complexity = result.structure.parameter_count / 40.0

    value = (
        0.45 * float(np.clip(free_run / 100.0, -1.0, 1.0))
        - 0.20 * float(np.clip(normalised_error, 0.0, 3.0))
        - 0.10 * (1.0 - float(np.clip(whiteness, 0.0, 1.0)))
        - 0.10 * float(np.clip(complexity, 0.0, 1.0))
    )
    breakdown = {
        "val_free_run_fit": float(free_run),
        "val_one_step_fit": result.metrics.val_fit,
        "residual_whiteness_ratio": whiteness,
        "complexity": complexity,
        "stable": result.validation.stable,
        "max_pole_modulus": result.validation.max_pole_modulus,
        "training_rows": result.training_rows,
    }
    return float(value), breakdown


def run_study(
    series: VersionSeries,
    payload: OptimizationStartRequest,
    *,
    input_columns: list[str],
    output_column: str,
    warm_start: list[dict[str, Any]] | None = None,
    warm_start_source: UUID | None = None,
) -> StudyOutcome:
    """Execute the closed loop synchronously and return everything it learned."""

    inputs = {column: series.values[column] for column in input_columns}
    output = series.values[output_column]
    fingerprint = build_fingerprint(inputs=inputs, output=output)
    cache = LineageCache()
    trials: list[TrialOutcome] = []
    base_key = stage_key(
        parent_key=str(series.version_id),
        tool_name="load_version",
        tool_version=TOOL_VERSION,
        parameters={"inputs": sorted(input_columns), "output": output_column},
    )

    structure_evaluations = 0

    def evaluate(trial: optuna.Trial) -> float:
        nonlocal structure_evaluations
        started = time.perf_counter()
        params = _suggest(trial, payload.search_space)
        cache_hit = False
        try:
            selection_params = _selection_params(params, input_columns, output_column)
            key = stage_key(
                parent_key=base_key,
                tool_name="segment_selection",
                tool_version=TOOL_VERSION,
                parameters=selection_params,
            )

            def compute_selection() -> list[int]:
                request = SegmentRequest(version_id=series.version_id, **selection_params)
                outcome = run_segment_selection(series, request)
                return outcome.selected_sample_indices

            selected, cache_hit = cache.get_or_compute(key, compute_selection)

            # Staged search. Gating and selection are the expensive head of the pipeline;
            # fitting a model on already-chosen rows is cheap. So the sampler explores the
            # head and every trial sweeps the whole structure grid against the one
            # selection it just computed, instead of spending a separate selection on each
            # structure. This is where the real saving is: a flat search recomputes the
            # head for every structure it tries, and the recomputation is pure waste
            # because the head does not depend on na, nb or the estimator.
            result = None
            best_structure_value = float("-inf")
            best_breakdown: dict[str, Any] = {}
            last_error: SegmentDomainError | ModelingDomainError | None = None
            for structure in _structure_grid(params):
                fit_request = ArxFitRequest(
                    version_id=series.version_id,
                    input_columns=input_columns,
                    output_column=output_column,
                    na=structure["na"],
                    nb={column: structure["nb"] for column in input_columns},
                    delays={column: params["nk"] for column in input_columns},
                    estimator=structure["estimator"],
                    ridge_alpha=structure.get("ridge_alpha"),
                    training_sample_indices=selected,
                )
                try:
                    candidate = fit_arx_core(
                        inputs=inputs,
                        output=output,
                        payload=fit_request,
                        input_columns=input_columns,
                    )
                except ModelingDomainError as error:
                    last_error = error
                    continue
                structure_evaluations += 1
                candidate_value, candidate_breakdown = objective_value(candidate)
                if candidate_value > best_structure_value:
                    best_structure_value = candidate_value
                    best_breakdown = candidate_breakdown
                    result = candidate
                    params = {**params, **structure}
            if result is None:
                raise last_error or ModelingDomainError(
                    "NUMERICAL_INSTABILITY", "该配置下所有模型结构均求解失败。"
                )
        except (SegmentDomainError, ModelingDomainError) as error:
            duration = (time.perf_counter() - started) * 1000.0
            trials.append(
                TrialOutcome(
                    number=trial.number,
                    state="failed",
                    value=None,
                    params=params,
                    metrics={},
                    cache_hit=cache_hit,
                    duration_ms=duration,
                    error_code=error.code,
                )
            )
            # A failed configuration is a real outcome, not an exception to hide. Optuna
            # prunes it so the sampler learns to avoid that region.
            raise optuna.TrialPruned() from error

        value, breakdown = best_structure_value, best_breakdown
        duration = (time.perf_counter() - started) * 1000.0
        if not np.isfinite(value):
            trials.append(
                TrialOutcome(
                    number=trial.number,
                    state="pruned",
                    value=None,
                    params=params,
                    metrics=breakdown,
                    cache_hit=cache_hit,
                    duration_ms=duration,
                    error_code=str(breakdown.get("reason", "not_finite")),
                )
            )
            raise optuna.TrialPruned()

        trials.append(
            TrialOutcome(
                number=trial.number,
                state="complete",
                value=value,
                params=params,
                metrics=breakdown,
                cache_hit=cache_hit,
                duration_ms=duration,
            )
        )
        return value

    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=payload.random_seed),
    )
    for candidate in (warm_start or [])[:WARM_START_LIMIT]:
        enqueued = _sanitise_warm_start(candidate)
        if enqueued:
            study.enqueue_trial(enqueued)
    study.optimize(
        evaluate,
        n_trials=payload.max_trials,
        timeout=payload.timeout_seconds,
        catch=(),
    )

    completed = [trial for trial in trials if trial.state == "complete"]
    best = max(completed, key=lambda item: item.value or float("-inf"), default=None)
    selection_computations = cache.misses
    statistics = {
        **cache.statistics(),
        "total_trials": len(trials),
        "completed_trials": len(completed),
        "failed_trials": sum(1 for trial in trials if trial.state == "failed"),
        "pruned_trials": sum(1 for trial in trials if trial.state == "pruned"),
        "mean_trial_ms": float(np.mean([trial.duration_ms for trial in trials])) if trials else 0.0,
        "warm_start_trials": len(warm_start or []),
        "structure_evaluations": structure_evaluations,
        "selection_computations": selection_computations,
        # How many model fits each computed selection served. A flat search would run one
        # selection per fit, so this is the factor by which the staged design plus the
        # lineage cache reduce the expensive stage.
        "evaluations_per_selection": (
            structure_evaluations / selection_computations if selection_computations else 0.0
        ),
    }
    return StudyOutcome(
        study_id=uuid4(),
        trials=trials,
        best_number=best.number if best else None,
        best_value=best.value if best else None,
        best_params=best.params if best else {},
        best_metrics=best.metrics if best else {},
        fingerprint=fingerprint,
        statistics=statistics,
        warm_started_from=warm_start_source,
        warm_start_params=list(warm_start or []),
    )


async def start_optimization_study(
    session: AsyncSession,
    *,
    payload: OptimizationStartRequest,
    artifact_root: Path,
) -> OptimizationStartData:
    """Load the version, retrieve a warm start, run the loop and persist everything."""

    try:
        series = await load_version_series(
            session, version_id=payload.version_id, artifact_root=artifact_root
        )
        input_columns, output_column = series.resolve_columns(
            input_columns=payload.input_columns, output_column=payload.output_column
        )
    except VersionDataError as error:
        raise OptimizationDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error

    fingerprint = build_fingerprint(
        inputs={column: series.values[column] for column in input_columns},
        output=series.values[output_column],
    )
    warm_start, source = await _retrieve_warm_start(session, series=series, fingerprint=fingerprint)

    outcome = run_study(
        series,
        payload,
        input_columns=input_columns,
        output_column=output_column,
        warm_start=warm_start,
        warm_start_source=source,
    )
    await _persist_study(session, series=series, payload=payload, outcome=outcome)

    return OptimizationStartData(
        study_id=outcome.study_id,
        task=completed_task(
            stage="optimize_pipeline",
            message=(
                f"闭环寻优完成：{outcome.statistics['completed_trials']} 个有效试验，"
                f"缓存命中率 {outcome.statistics['hit_rate']:.0%}。"
            ),
        ),
    )


async def get_optimization_status(
    session: AsyncSession, *, study_id: UUID
) -> OptimizationStatusData:
    """Return trials, the best value and the convergence curve for one study."""

    study = await session.get(OptimizationStudy, study_id)
    if study is None:
        raise OptimizationDomainError(
            "OPTIMIZATION_STUDY_NOT_FOUND", "寻优任务不存在。", status_code=404
        )
    records = list(
        (
            await session.scalars(
                select(OptimizationTrialRecord)
                .where(OptimizationTrialRecord.study_id == study_id)
                .order_by(OptimizationTrialRecord.trial_number)
            )
        ).all()
    )

    curve: list[float | None] = []
    best_so_far: float | None = None
    for record in records:
        if record.value is not None and (best_so_far is None or record.value > best_so_far):
            best_so_far = record.value
        curve.append(best_so_far)

    return OptimizationStatusData(
        study_id=study_id,
        task=completed_task(stage="optimize_pipeline", message=f"研究状态：{study.status}。"),
        trials=[
            OptimizationTrial(
                trial_id=record.trial_number,
                state=_trial_state(record.state),
                value=record.value,
                params=record.params,
                created_at=record.created_at,
                finished_at=record.finished_at,
                error_code=record.error_code,
            )
            for record in records
        ],
        best_trial_id=study.best_trial_number,
        best_value=study.best_value,
        best_curve=curve,
        param_importances=_param_importances(records),
        statistics=dict(study.statistics),
        best_params=dict(study.best_params),
        warm_started_from=study.warm_started_from,
    )


def _trial_state(value: str) -> str:
    return value if value in {"queued", "running", "complete", "pruned", "failed"} else "complete"


def _suggest(trial: optuna.Trial, overrides: dict[str, Any]) -> dict[str, Any]:
    """Search space with engineering bounds; every range is finite by design."""

    space = {
        "window_size": (30, 200),
        "max_segments": (3, 20),
        **_GATING_BOUNDS,
        "na": (1, 5),
        "nb": (1, 4),
        "nk": (0, 20),
        "ridge_alpha": (1e-4, 10.0),
        **overrides,
    }
    # The gating thresholds are quantised on purpose. A continuous suggestion gives every
    # trial a unique threshold like 0.2016644..., which makes the selection cache key
    # unique too — measured hit rate was exactly 0% before this, so the cache paid its
    # overhead and returned nothing. The distinction between a 20% and a 20.17% anomaly
    # limit is not one the process can act on, so quantising costs no fidelity and lets
    # trials that differ only in model structure reuse the selection they share.
    params: dict[str, Any] = {
        "window_size": trial.suggest_int(
            "window_size", *_bounds_int(space["window_size"]), step=10
        ),
        "max_segments": trial.suggest_int("max_segments", *_bounds_int(space["max_segments"])),
        "max_anomaly_ratio": trial.suggest_float(
            "max_anomaly_ratio", *_bounds_float(space["max_anomaly_ratio"]), step=THRESHOLD_STEP
        ),
        "max_missing_ratio": trial.suggest_float(
            "max_missing_ratio", *_bounds_float(space["max_missing_ratio"]), step=THRESHOLD_STEP
        ),
        "min_input_activity_ratio": trial.suggest_float(
            "min_input_activity_ratio",
            *_bounds_float(space["min_input_activity_ratio"]),
            step=THRESHOLD_STEP,
        ),
        # nk stays with the sampler: the pure delay is process-specific, its useful range
        # is wide, and it changes the regressor, so it does not belong in a fixed grid.
        "nk": trial.suggest_int("nk", *_bounds_int(space["nk"])),
    }
    return params


def _structure_grid(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Model structures swept inside one trial, against a single selection.

    Small and fixed on purpose: these fits are cheap once the rows are chosen, so an
    exhaustive sweep is both faster and more thorough than asking the sampler to find the
    orders one trial at a time.
    """

    grid: list[dict[str, Any]] = []
    for na in (1, 2, 3, 4):
        for nb in (1, 2, 3):
            grid.append({"na": na, "nb": nb, "estimator": "ols"})
            grid.append({"na": na, "nb": nb, "estimator": "ridge", "ridge_alpha": 0.1})
    return grid


def _bounds_int(value: Any) -> tuple[int, int]:
    low, high = value
    return int(low), int(high)


def _bounds_float(value: Any) -> tuple[float, float]:
    low, high = value
    return float(low), float(high)


def _selection_params(
    params: dict[str, Any], input_columns: list[str], output_column: str
) -> dict[str, Any]:
    """Only the parameters that actually change the selected rows enter the cache key."""

    return {
        "input_columns": list(input_columns),
        "output_column": output_column,
        "window_size": params["window_size"],
        "max_segments": params["max_segments"],
        "max_anomaly_ratio": params["max_anomaly_ratio"],
        "max_missing_ratio": params["max_missing_ratio"],
        "min_input_activity_ratio": params["min_input_activity_ratio"],
    }


def _sanitise_warm_start(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep only keys the current search space defines, so enqueue cannot fail."""

    allowed = {
        "window_size",
        "max_segments",
        "max_anomaly_ratio",
        "max_missing_ratio",
        "min_input_activity_ratio",
        "na",
        "nb",
        "nk",
        "estimator",
        "ridge_alpha",
    }
    cleaned = {key: value for key, value in candidate.items() if key in allowed}
    if cleaned.get("estimator") != "ridge":
        cleaned.pop("ridge_alpha", None)
    return cleaned


async def _retrieve_warm_start(
    session: AsyncSession,
    *,
    series: VersionSeries,
    fingerprint: ProfileFingerprint,
) -> tuple[list[dict[str, Any]], UUID | None]:
    """Find the closest past studies on *other* datasets and reuse their winners.

    Excluding the current dataset is not a formality: warm-starting a dataset from its own
    previous run would recycle a configuration that already saw this data, which is exactly
    the leakage the evaluation protocol forbids.
    """

    entries = list((await session.scalars(select(StrategyMemory))).all())
    scored: list[tuple[float, StrategyMemory]] = []
    for entry in entries:
        if series.dataset_id is not None and entry.dataset_id == series.dataset_id:
            continue
        distance = fingerprint_distance(fingerprint.vector, list(entry.fingerprint_vector))
        if distance <= WARM_START_MAX_DISTANCE:
            scored.append((distance, entry))
    if not scored:
        return [], None
    scored.sort(key=lambda item: item[0])
    chosen = scored[:WARM_START_LIMIT]
    return [dict(entry.best_params) for _, entry in chosen], chosen[0][1].study_id


async def _persist_study(
    session: AsyncSession,
    *,
    series: VersionSeries,
    payload: OptimizationStartRequest,
    outcome: StudyOutcome,
) -> None:
    now = datetime.now(UTC)
    session.add(
        OptimizationStudy(
            id=outcome.study_id,
            dataset_id=series.dataset_id,
            version_id=series.version_id,
            status="succeeded" if outcome.best_number is not None else "failed",
            objective="val_free_run_fit",
            parameters=payload.model_dump(mode="json"),
            best_trial_number=outcome.best_number,
            best_value=outcome.best_value,
            best_params=outcome.best_params,
            fingerprint=outcome.fingerprint.to_payload(),
            statistics=outcome.statistics,
            warm_started_from=outcome.warm_started_from,
            created_at=now,
            finished_at=now,
        )
    )
    for trial in outcome.trials:
        session.add(
            OptimizationTrialRecord(
                id=uuid4(),
                study_id=outcome.study_id,
                trial_number=trial.number,
                state=trial.state,
                value=trial.value,
                params=trial.params,
                metrics=trial.metrics,
                cache_hit=trial.cache_hit,
                duration_ms=trial.duration_ms,
                error_code=trial.error_code,
                created_at=now,
                finished_at=now,
            )
        )
    if outcome.best_number is not None:
        session.add(
            StrategyMemory(
                id=uuid4(),
                dataset_id=series.dataset_id,
                version_id=series.version_id,
                study_id=outcome.study_id,
                fingerprint=outcome.fingerprint.to_payload(),
                fingerprint_vector=outcome.fingerprint.vector,
                best_params=outcome.best_params,
                achieved_metrics=outcome.best_metrics,
                objective_value=outcome.best_value,
                source="study",
                created_at=now,
            )
        )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type="optimization.study.completed",
            subject_id=str(series.dataset_id),
            payload_json=json.dumps(
                {
                    "study_id": str(outcome.study_id),
                    "best_value": outcome.best_value,
                    "best_params": outcome.best_params,
                    "statistics": outcome.statistics,
                    "warm_started_from": str(outcome.warm_started_from)
                    if outcome.warm_started_from
                    else None,
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            created_at=now,
        )
    )
    await session.commit()


def _param_importances(records: list[OptimizationTrialRecord]) -> dict[str, float]:
    """Correlation-based importance, which needs no extra dependency.

    Optuna's fANOVA importance requires a live Study object; the persisted trials are all
    that survive a restart, so importance is derived from them directly. It is reported as
    the absolute Spearman-style rank correlation between a parameter and the objective,
    normalised to sum to one.
    """

    completed = [record for record in records if record.value is not None]
    if len(completed) < 4:
        return {}
    values = np.asarray([record.value for record in completed], dtype=float)
    names = sorted({name for record in completed for name in record.params})
    importances: dict[str, float] = {}
    for name in names:
        column = []
        target = []
        for record, score in zip(completed, values, strict=True):
            raw = record.params.get(name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            column.append(float(raw))
            target.append(float(score))
        if len(column) < 4 or len(set(column)) < 2:
            continue
        ranked_x = _ranks(np.asarray(column))
        ranked_y = _ranks(np.asarray(target))
        left = ranked_x - ranked_x.mean()
        right = ranked_y - ranked_y.mean()
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 0:
            continue
        importances[name] = abs(float(np.dot(left, right) / denominator))
    total = sum(importances.values())
    if total <= 0:
        return {}
    return {name: value / total for name, value in sorted(importances.items())}


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    return ranks
