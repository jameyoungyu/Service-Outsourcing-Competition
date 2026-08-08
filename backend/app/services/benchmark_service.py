"""One-click self-benchmark: the system measuring its own claims (phase 11).

Most entries cannot demonstrate that their preprocessing helped, because on real plant data
there is nothing to compare against. This project generates its own benchmarks with recorded
ground truth, so every claim in the report can be re-derived on demand rather than asserted.

Three ablations run here, each answering a question the design took a position on:

* **selection** — does quality-constrained D-optimal selection beat the conventional
  energy heuristic, and does it hold up against using every row?
* **metric** — how much do one-step and free-run FIT actually disagree? If they agreed,
  choosing free-run as the closed-loop objective would be pedantry.
* **delay** — does prewhitening move the cross-correlation peak closer to the true delay?

Every number returned is computed during the request. Nothing is cached from a previous run
and nothing is hard-coded, so a result that contradicts the documentation will show it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from algorithms.identifiability.delay import (
    prewhitened_cross_correlation,
)
from algorithms.identifiability.regressor import ArxStructure, build_regressor
from algorithms.identifiability.selection import (
    build_window_grid,
    select_by_energy,
    select_informative_windows,
)
from algorithms.identifiability.validation import fit_percentage, free_run_simulate
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.schemas.benchmark import (
    BenchmarkData,
    BenchmarkExperiment,
    BenchmarkRequest,
    BenchmarkRow,
)
from app.schemas.simulation import SimulationGenerateRequest
from app.services.contract_stubs import completed_task
from app.services.simulation_service import generate_simulation, load_simulation_by_version

TRAIN_RATIO = 0.7


class BenchmarkDomainError(Exception):
    """A client-safe benchmark failure for the standard error envelope."""

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
class Scenario:
    """One generated benchmark plus the ground truth it was built from."""

    name: str
    inputs: dict[str, np.ndarray]
    output: np.ndarray
    structure: ArxStructure
    true_theta: np.ndarray
    true_delays: dict[str, int]


async def run_benchmark(
    session: AsyncSession,
    *,
    payload: BenchmarkRequest,
    artifact_root: Path,
) -> BenchmarkData:
    """Generate the scenarios, run every ablation and return the measured table."""

    started = time.perf_counter()
    experiments: list[BenchmarkExperiment] = []
    scenarios: dict[str, Scenario] = {}
    for name in payload.scenarios:
        scenarios[name] = _generate(
            name,
            n_samples=payload.n_samples,
            seed=payload.seed,
            artifact_root=artifact_root,
        )

    experiments.append(_selection_experiment(scenarios, payload))
    experiments.append(_metric_experiment(scenarios, payload))
    experiments.append(_delay_experiment(scenarios))

    duration = (time.perf_counter() - started) * 1000.0
    benchmark_id = uuid4()
    now = datetime.now(UTC)
    session.add(
        ProcessingRun(
            id=benchmark_id,
            dataset_id=None,
            source_version_id=None,
            run_type="benchmark.selfcheck",
            status="succeeded",
            parameters=payload.model_dump(mode="json"),
            result={
                "experiments": [experiment.model_dump(mode="json") for experiment in experiments]
            },
            created_at=now,
            finished_at=now,
        )
    )
    await session.commit()

    return BenchmarkData(
        benchmark_id=benchmark_id,
        task=completed_task(
            stage="run_benchmark",
            message="自评测基准已完成，全部数值由本次运行实时计算。",
        ),
        scenarios=list(payload.scenarios),
        n_samples=payload.n_samples,
        seed=payload.seed,
        experiments=experiments,
        duration_ms=duration,
    )


def _generate(name: str, *, n_samples: int, seed: int, artifact_root: Path) -> Scenario:
    """Generate a benchmark through the real simulation service, then read it back."""

    try:
        generated = generate_simulation(
            SimulationGenerateRequest(
                scenario=name,
                n_steps=n_samples,
                seed=seed,
                input_count=3,
                dataset_name=f"benchmark_{name.lower()}",
            ),
            artifact_root=artifact_root,
        )
    except Exception as error:  # pragma: no cover - guarded by schema validation
        raise BenchmarkDomainError(
            "BENCHMARK_GENERATION_FAILED", f"场景 {name} 生成失败：{error}"
        ) from error

    dataset = load_simulation_by_version(generated.version_id, artifact_root=artifact_root)
    truth = generated.ground_truth
    columns = tuple(sorted(column for column in dataset.values if column.startswith("u")))
    nb = {column: len(truth.input_coefficients[column]) for column in columns}
    delays = {column: truth.true_delays_by_input[column] for column in columns}
    structure = ArxStructure.create(na=truth.true_na, nb=nb, nk=delays, input_columns=columns)
    theta = np.concatenate(
        [np.asarray(truth.ar_coefficients, dtype=float)]
        + [np.asarray(truth.input_coefficients[column], dtype=float) for column in columns]
    )
    return Scenario(
        name=name,
        inputs={column: dataset.values[column] for column in columns},
        output=dataset.values["y"],
        structure=structure,
        true_theta=theta,
        true_delays=delays,
    )


def _selection_experiment(
    scenarios: dict[str, Scenario], payload: BenchmarkRequest
) -> BenchmarkExperiment:
    """full vs energy heuristic vs quality-constrained D-optimal, at equal budget."""

    rows: list[BenchmarkRow] = []
    for name, scenario in scenarios.items():
        regressor = build_regressor(
            inputs=scenario.inputs,
            output=scenario.output,
            structure=scenario.structure,
        )
        train_rows = int(regressor.n_rows * TRAIN_RATIO)
        if train_rows < payload.window_size * 2:
            continue
        grid = build_window_grid(
            regressor,
            window_size=payload.window_size,
            stride=payload.window_size // 2,
            row_range=(0, train_rows),
        )
        full_rows = np.arange(train_rows, dtype=int)

        for strategy in ("full", "energy", "ids"):
            if strategy == "full":
                positions = full_rows
            elif strategy == "energy":
                positions = select_by_energy(regressor, grid, budget_windows=payload.budget_windows)
            else:
                positions = select_informative_windows(
                    regressor,
                    grid,
                    budget_windows=payload.budget_windows,
                    ridge=1e-6,
                    inputs=scenario.inputs,
                ).row_positions

            theta, _, _, _ = np.linalg.lstsq(
                regressor.features[positions], regressor.targets[positions], rcond=None
            )
            theta = np.asarray(theta, dtype=float)
            parameter_error = float(
                np.linalg.norm(theta - scenario.true_theta) / np.linalg.norm(scenario.true_theta)
            )
            free_run = _free_run(scenario, theta, start=train_rows)
            rows.append(
                BenchmarkRow(
                    scenario=name,
                    strategy=strategy,
                    metrics={
                        "train_rows": float(positions.size),
                        "coverage_ratio": float(positions.size) / float(regressor.n_rows),
                        "parameter_error": parameter_error,
                        "free_run_fit": free_run,
                        "condition_number": _condition(regressor.features[positions]),
                    },
                )
            )

    return BenchmarkExperiment(
        key="selection",
        title="数据优选消融：全量 vs 能量启发式 vs 质量约束 D-最优",
        question="等预算下，质量约束 D-最优优选能否达到全量数据的辨识精度，且不像能量法那样失效？",
        rows=rows,
        notes=[
            "参数误差以仿真真值为基准，与拟合优度无关。",
            "自由仿真 FIT 在未参与优选的验证区间上计算。",
            "同构激励场景下三者差异很小；差距出现在异构激励（S6）。",
        ],
    )


def _metric_experiment(
    scenarios: dict[str, Scenario], payload: BenchmarkRequest
) -> BenchmarkExperiment:
    """Measure how far one-step and free-run FIT disagree on the same models."""

    rows: list[BenchmarkRow] = []
    for name, scenario in scenarios.items():
        regressor = build_regressor(
            inputs=scenario.inputs, output=scenario.output, structure=scenario.structure
        )
        train_rows = int(regressor.n_rows * TRAIN_RATIO)
        if train_rows < 200:
            continue

        # A well-fitted model and a starved one: the pair the metric has to tell apart.
        variants = {
            "well_fitted": np.arange(train_rows, dtype=int),
            "starved": np.arange(20, min(train_rows, 240), dtype=int),
        }
        for label, positions in variants.items():
            if positions.size <= regressor.n_parameters * 2:
                continue
            theta, _, _, _ = np.linalg.lstsq(
                regressor.features[positions], regressor.targets[positions], rcond=None
            )
            theta = np.asarray(theta, dtype=float)
            validation = np.arange(train_rows, regressor.n_rows, dtype=int)
            one_step = fit_percentage(
                regressor.targets[validation], regressor.features[validation] @ theta
            )
            free_run = _free_run(scenario, theta, start=train_rows)
            rows.append(
                BenchmarkRow(
                    scenario=name,
                    strategy=label,
                    metrics={
                        "one_step_fit": one_step,
                        "free_run_fit": free_run,
                        "fit_gap": one_step - free_run,
                    },
                )
            )

    spreads = _discrimination(rows)
    _ = payload
    return BenchmarkExperiment(
        key="metric",
        title="指标区分度：一步预测 FIT vs 自由仿真 FIT",
        question="一步预测 FIT 能否区分良好模型与欠拟合模型？若不能，它就不适合作为闭环目标函数。",
        rows=rows,
        notes=[
            "同一组模型下，两个指标的跨度之比即为区分度之比。",
            *[
                f"{scenario}：一步预测跨度 {values['one_step']:.2f} 个点，"
                f"自由仿真跨度 {values['free_run']:.2f} 个点，"
                f"区分度之比 {values['ratio']:.1f}×"
                for scenario, values in spreads.items()
            ],
        ],
    )


def _delay_experiment(scenarios: dict[str, Scenario]) -> BenchmarkExperiment:
    """Compare the raw and prewhitened cross-correlation peaks against the truth."""

    rows: list[BenchmarkRow] = []
    for name, scenario in scenarios.items():
        train_stop = int(scenario.output.shape[0] * TRAIN_RATIO)
        max_lag = 30
        for column, signal in scenario.inputs.items():
            truth = scenario.true_delays[column]
            prewhitened, order = prewhitened_cross_correlation(
                signal[:train_stop], scenario.output[:train_stop], max_lag=max_lag
            )
            prewhitened_peak = int(np.argmax(np.abs(prewhitened)))
            raw_peak = _raw_peak(signal[:train_stop], scenario.output[:train_stop], max_lag)
            rows.append(
                BenchmarkRow(
                    scenario=name,
                    strategy=column,
                    metrics={
                        "true_delay": float(truth),
                        "raw_peak": float(raw_peak),
                        "prewhitened_peak": float(prewhitened_peak),
                        "raw_error": float(abs(raw_peak - truth)),
                        "prewhitened_error": float(abs(prewhitened_peak - truth)),
                        "ar_order": float(order),
                    },
                )
            )

    improved = sum(1 for row in rows if row.metrics["prewhitened_error"] < row.metrics["raw_error"])
    worse = sum(1 for row in rows if row.metrics["prewhitened_error"] > row.metrics["raw_error"])
    return BenchmarkExperiment(
        key="delay",
        title="时滞估计：朴素互相关 vs 预白化互相关",
        question="预白化能否消除输入自相关造成的峰值偏移？",
        rows=rows,
        notes=[
            f"预白化更接近真值的通道数：{improved}；更差的通道数：{worse}；"
            f"其余持平，共 {len(rows)} 个通道。",
            "朴素互相关的偏差方向是系统性的，因为它等于真实脉冲响应与输入自协方差的卷积。",
        ],
    )


def _free_run(scenario: Scenario, theta: np.ndarray, *, start: int) -> float:
    try:
        measured, simulated = free_run_simulate(
            theta,
            scenario.structure,
            inputs=scenario.inputs,
            output=scenario.output,
            start=start,
            stop=scenario.output.shape[0],
        )
        return fit_percentage(measured, simulated)
    except Exception:  # noqa: BLE001 - a diverged variant is a result, not a crash
        return float("-100")


def _raw_peak(signal: np.ndarray, output: np.ndarray, max_lag: int) -> int:
    centered_input = signal - float(np.mean(signal))
    centered_output = output - float(np.mean(output))
    best_lag, best_value = 0, -1.0
    for lag in range(max_lag + 1):
        left = centered_input[: signal.size - lag]
        right = centered_output[lag:]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 0:
            continue
        value = abs(float(np.dot(left, right) / denominator))
        if value > best_value:
            best_lag, best_value = lag, value
    return best_lag


def _condition(features: np.ndarray) -> float:
    if features.size == 0:
        return float("inf")
    singular = np.linalg.svd(features, compute_uv=False)
    if singular.size == 0 or singular[-1] <= 0:
        return float("inf")
    return float(singular[0] / singular[-1])


def _discrimination(rows: list[BenchmarkRow]) -> dict[str, dict[str, float]]:
    """Per scenario, the spread of each metric across model variants."""

    grouped: dict[str, list[BenchmarkRow]] = {}
    for row in rows:
        grouped.setdefault(row.scenario, []).append(row)

    spreads: dict[str, dict[str, float]] = {}
    for scenario, group in grouped.items():
        if len(group) < 2:
            continue
        one_step = [row.metrics["one_step_fit"] for row in group]
        free_run = [row.metrics["free_run_fit"] for row in group]
        one_spread = max(one_step) - min(one_step)
        free_spread = max(free_run) - min(free_run)
        spreads[scenario] = {
            "one_step": one_spread,
            "free_run": free_spread,
            "ratio": free_spread / one_spread if one_spread > 1e-9 else float("inf"),
        }
    return spreads
