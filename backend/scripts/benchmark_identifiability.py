"""Ablation experiment for identifiability-driven data selection.

Reproduces the A14 core pain point — informative dynamics buried in steady-state data —
and compares three ways of choosing which samples to identify from, at an equal sample
budget:

* ``full``    : every training sample, the do-nothing baseline;
* ``energy``  : top-K windows by input change energy, i.e. the conventional heuristic;
* ``ids``     : greedy D-optimal selection maximising ``log det`` of the Fisher information.

The scenario mirrors the ``S3`` generator in ``app.services.simulation_service`` (long
steady holds with short step / ramp / pulse excitations, second-order ARX with per-input
delays), reimplemented here with plain NumPy so the experiment runs without the API stack.

Usage::

    python scripts/benchmark_identifiability.py
    python scripts/benchmark_identifiability.py --json results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.identifiability.excitation import profile_excitation  # noqa: E402
from algorithms.identifiability.regressor import (  # noqa: E402
    ArxStructure,
    RegressorMatrix,
    build_regressor,
)
from algorithms.identifiability.selection import (  # noqa: E402
    build_window_grid,
    select_by_energy,
    select_informative_windows,
)
from algorithms.identifiability.validation import validate_model  # noqa: E402

FloatArray = NDArray[np.float64]

# Mirrors _scenario_parameters() in app/services/simulation_service.py for S3.
AR_COEFFICIENTS = [-1.4, 0.48]
INPUT_COEFFICIENTS = {"u1": [0.36, 0.12], "u2": [0.18, 0.06], "u3": [0.12, 0.04]}
DELAYS = {"u1": 3, "u2": 8, "u3": 5}
NOISE_LEVEL = 0.03


@dataclass
class Scenario:
    inputs: dict[str, FloatArray]
    output: FloatArray
    true_theta: FloatArray
    structure: ArxStructure
    dynamic_fraction: float
    segments: list[tuple[int, int, str]] = field(default_factory=list)


def synthesize(
    *,
    scenario: str = "S6",
    n_samples: int = 6000,
    seed: int = 20260807,
    dynamic_fraction: float = 0.12,
) -> Scenario:
    """Long steady record with a handful of short, genuinely informative excitations.

    ``S3`` reproduces the existing homogeneous benchmark: every burst moves every input at
    once, so any dynamic window teaches the model roughly the same thing.

    ``S6`` is the heterogeneous-excitation case this project adds, and it is what plant
    historians actually look like: operators step one valve during one campaign and a
    different one weeks later, and the visually dramatic moves cluster on a single
    variable. Selecting by energy then piles up redundant ``u1`` bursts and leaves ``u2``
    and ``u3`` barely excited, which is precisely the failure mode a determinant-based
    criterion avoids because ``log det`` rewards covering new parameter directions rather
    than repeating a large one.
    """

    generator = np.random.default_rng(seed)
    columns = tuple(INPUT_COEFFICIENTS)
    inputs = {column: np.zeros(n_samples, dtype=float) for column in columns}

    budget = max(60, int(n_samples * dynamic_fraction))
    plan = _burst_plan(scenario)
    width = max(20, budget // len(plan))
    segments: list[tuple[int, int, str]] = []

    for fraction, kind, movers, scale in plan:
        position = int(n_samples * fraction)
        end = min(n_samples, position + width)
        segments.append((position, end - 1, kind))
        for column in movers:
            amplitude = scale * float(generator.uniform(0.85, 1.15))
            amplitude *= float(generator.choice([-1.0, 1.0]))
            signal = inputs[column]
            if kind == "step":
                signal[position:end] = amplitude
            elif kind == "ramp":
                signal[position:end] = np.linspace(0.0, amplitude, end - position)
            else:
                middle = position + (end - position) // 2
                signal[position:middle] = amplitude
                signal[middle:end] = -0.4 * amplitude

    structure = ArxStructure.create(
        na=len(AR_COEFFICIENTS),
        nb={column: len(INPUT_COEFFICIENTS[column]) for column in columns},
        nk=DELAYS,
        input_columns=columns,
    )
    output = _simulate_arx(inputs, generator=generator)
    true_theta = np.concatenate(
        [np.asarray(AR_COEFFICIENTS, dtype=float)]
        + [np.asarray(INPUT_COEFFICIENTS[column], dtype=float) for column in columns]
    )
    return Scenario(
        inputs=inputs,
        output=output,
        true_theta=true_theta,
        structure=structure,
        dynamic_fraction=dynamic_fraction,
        segments=segments,
    )


def _burst_plan(scenario: str) -> list[tuple[float, str, tuple[str, ...], float]]:
    """Return ``(position fraction, shape, inputs moved, amplitude)`` per excitation burst."""

    columns = tuple(INPUT_COEFFICIENTS)
    if scenario.upper() == "S3":
        return [
            (0.12, "step", columns, 1.4),
            (0.34, "ramp", columns, 1.4),
            (0.56, "pulse", columns, 1.4),
            (0.79, "step", columns, 1.4),
        ]
    if scenario.upper() != "S6":
        raise ValueError(f"unknown scenario {scenario!r}, expected S3 or S6")
    # Large, repetitive moves on u1; rarer and smaller moves on u2 and u3.
    return [
        (0.06, "step", ("u1",), 1.60),
        (0.14, "step", ("u1",), 1.55),
        (0.22, "ramp", ("u2",), 0.65),
        (0.30, "step", ("u1",), 1.50),
        (0.38, "pulse", ("u1",), 1.58),
        (0.46, "step", ("u3",), 0.60),
        (0.54, "step", ("u1",), 1.52),
        (0.62, "pulse", ("u2",), 0.62),
        (0.70, "ramp", ("u1",), 1.56),
        (0.78, "step", ("u3",), 0.58),
    ]


def _simulate_arx(inputs: dict[str, FloatArray], *, generator: np.random.Generator) -> FloatArray:
    n_samples = len(next(iter(inputs.values())))
    output = np.zeros(n_samples, dtype=float)
    max_history = max(
        len(AR_COEFFICIENTS),
        max(DELAYS[column] + len(INPUT_COEFFICIENTS[column]) - 1 for column in inputs),
    )
    for time_index in range(max_history, n_samples):
        value = 0.0
        for lag, coefficient in enumerate(AR_COEFFICIENTS, start=1):
            value -= coefficient * output[time_index - lag]
        for column, signal in inputs.items():
            for lag, coefficient in enumerate(INPUT_COEFFICIENTS[column]):
                value += coefficient * signal[time_index - DELAYS[column] - lag]
        output[time_index] = value + generator.normal(0.0, NOISE_LEVEL)
    return output


def fit_ols(regressor: RegressorMatrix) -> FloatArray:
    estimate, _, _, _ = np.linalg.lstsq(regressor.features, regressor.targets, rcond=None)
    return np.asarray(estimate, dtype=float)


def evaluate(
    label: str,
    theta: FloatArray,
    scenario: Scenario,
    *,
    n_rows: int,
    validation_range: tuple[int, int],
    fit_seconds: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    truth = scenario.true_theta
    parameter_error = float(np.linalg.norm(theta - truth) / np.linalg.norm(truth))
    validation = validate_model(
        theta,
        scenario.structure,
        inputs=scenario.inputs,
        output=scenario.output,
        start=validation_range[0],
        stop=validation_range[1],
    )
    true_gains = _true_gains(scenario)
    gain_error = float(
        np.max(
            [
                abs(validation.steady_state_gains[column] - true_gains[column])
                / abs(true_gains[column])
                for column in scenario.structure.input_columns
            ]
        )
    )
    payload: dict[str, Any] = {
        "strategy": label,
        "train_rows": n_rows,
        "parameter_error": parameter_error,
        "one_step_fit": validation.one_step_fit,
        "free_run_fit": validation.free_run_fit,
        "fit_gap": validation.fit_gap,
        "max_gain_error": gain_error,
        "stable": validation.stable,
        "residual_whiteness_ratio": validation.residual_whiteness_ratio,
        "fit_seconds": fit_seconds,
    }
    payload.update(extra or {})
    return payload


def _true_gains(scenario: Scenario) -> dict[str, float]:
    denominator = 1.0 + float(np.sum(AR_COEFFICIENTS))
    return {
        column: float(np.sum(INPUT_COEFFICIENTS[column]) / denominator)
        for column in scenario.structure.input_columns
    }


def run_experiment(
    *,
    scenario_name: str,
    n_samples: int,
    seed: int,
    window_size: int,
    budget_windows: int,
    train_ratio: float,
) -> dict[str, Any]:
    scenario = synthesize(scenario=scenario_name, n_samples=n_samples, seed=seed)
    train_stop = int(n_samples * train_ratio)
    validation_range = (train_stop, n_samples)

    full = build_regressor(
        inputs=scenario.inputs,
        output=scenario.output,
        structure=scenario.structure,
        start=0,
        stop=train_stop,
    )
    grid = build_window_grid(full, window_size=window_size, stride=window_size // 2)

    results: list[dict[str, Any]] = []

    started = time.perf_counter()
    theta_full = fit_ols(full)
    full_seconds = time.perf_counter() - started
    full_profile = profile_excitation(full, inputs=_restrict(scenario, full), ridge=1e-6)
    results.append(
        evaluate(
            "full",
            theta_full,
            scenario,
            n_rows=full.n_rows,
            validation_range=validation_range,
            fit_seconds=full_seconds,
            extra={
                "log_det": full_profile.log_det,
                "condition_number": full_profile.condition_number,
                "excitation_satisfied": full_profile.excitation_satisfied,
                "coverage_ratio": 1.0,
            },
        )
    )

    started = time.perf_counter()
    energy_rows = select_by_energy(full, grid, budget_windows=budget_windows)
    energy_subset = full.take(energy_rows)
    theta_energy = fit_ols(energy_subset)
    energy_seconds = time.perf_counter() - started
    energy_profile = profile_excitation(
        energy_subset, inputs=_restrict(scenario, energy_subset), ridge=1e-6
    )
    results.append(
        evaluate(
            "energy",
            theta_energy,
            scenario,
            n_rows=energy_subset.n_rows,
            validation_range=validation_range,
            fit_seconds=energy_seconds,
            extra={
                "log_det": energy_profile.log_det,
                "condition_number": energy_profile.condition_number,
                "excitation_satisfied": energy_profile.excitation_satisfied,
                "coverage_ratio": energy_subset.n_rows / full.n_rows,
            },
        )
    )

    started = time.perf_counter()
    selection = select_informative_windows(
        full,
        grid,
        budget_windows=budget_windows,
        ridge=1e-6,
        inputs=scenario.inputs,
    )
    theta_ids = fit_ols(selection.regressor)
    ids_seconds = time.perf_counter() - started
    results.append(
        evaluate(
            "ids",
            theta_ids,
            scenario,
            n_rows=selection.regressor.n_rows,
            validation_range=validation_range,
            fit_seconds=ids_seconds,
            extra={
                "log_det": selection.selected_log_det,
                "condition_number": selection.excitation.condition_number,
                "excitation_satisfied": selection.excitation.excitation_satisfied,
                "coverage_ratio": selection.coverage_ratio,
                "information_retention": selection.information_retention,
                "lazy_speedup": selection.lazy_speedup,
                "evaluated_candidates": selection.evaluated_candidates,
                "naive_candidate_evaluations": selection.naive_candidate_evaluations,
                "stopped_reason": selection.stopped_reason,
            },
        )
    )

    return {
        "configuration": {
            "scenario": scenario_name.upper(),
            "n_samples": n_samples,
            "seed": seed,
            "window_size": window_size,
            "budget_windows": budget_windows,
            "train_ratio": train_ratio,
            "train_rows": full.n_rows,
            "candidate_windows": grid.count,
            "noise_level": NOISE_LEVEL,
            "dynamic_fraction": scenario.dynamic_fraction,
        },
        "true_gains": _true_gains(scenario),
        "results": results,
        "selected_windows": [window.to_payload() for window in selection.selected],
    }


def _restrict(scenario: Scenario, regressor: RegressorMatrix) -> dict[str, FloatArray]:
    return {column: values[regressor.time_indices] for column, values in scenario.inputs.items()}


AGGREGATED_KEYS = (
    "parameter_error",
    "one_step_fit",
    "free_run_fit",
    "max_gain_error",
    "condition_number",
    "coverage_ratio",
)


def aggregate(reports: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    """Collapse repeated seeds into mean / std / worst per strategy."""

    collected: dict[str, dict[str, list[float]]] = {}
    for report in reports:
        for row in report["results"]:
            bucket = collected.setdefault(row["strategy"], {key: [] for key in AGGREGATED_KEYS})
            for key in AGGREGATED_KEYS:
                bucket[key].append(float(row[key]))
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for strategy, metrics in collected.items():
        summary[strategy] = {
            key: {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "median": float(np.median(values)),
                "worst": float(np.max(values) if _higher_is_worse(key) else np.min(values)),
            }
            for key, values in metrics.items()
        }
    return summary


def _higher_is_worse(key: str) -> bool:
    return key in {"parameter_error", "max_gain_error", "condition_number"}


def format_summary(summary: dict[str, dict[str, dict[str, float]]], *, repeats: int) -> str:
    header = (
        f"{'strategy':<8} {'θ err mean±std':>20} {'free-run mean±std':>22} "
        f"{'gain err mean':>14} {'cond median':>13}"
    )
    lines = [f"aggregate over {repeats} seeds", header, "-" * len(header)]
    for strategy, metrics in summary.items():
        parameter = metrics["parameter_error"]
        free_run = metrics["free_run_fit"]
        gain = metrics["max_gain_error"]
        condition = metrics["condition_number"]
        lines.append(
            f"{strategy:<8} "
            f"{parameter['mean'] * 100:>13.2f}±{parameter['std'] * 100:<6.2f} "
            f"{free_run['mean']:>15.2f}±{free_run['std']:<6.2f} "
            f"{gain['mean'] * 100:>13.2f}% {condition['median']:>13.3g}"
        )
    return "\n".join(lines)


def format_table(report: dict[str, Any]) -> str:
    header = (
        f"{'strategy':<8} {'rows':>6} {'cover':>7} {'θ err':>9} "
        f"{'1-step':>8} {'free-run':>9} {'gap':>8} {'gain err':>9} {'log det':>10} {'cond':>10}"
    )
    lines = [header, "-" * len(header)]
    for row in report["results"]:
        lines.append(
            f"{row['strategy']:<8} {row['train_rows']:>6d} "
            f"{row['coverage_ratio'] * 100:>6.1f}% {row['parameter_error'] * 100:>8.2f}% "
            f"{row['one_step_fit']:>7.2f}% {row['free_run_fit']:>8.2f}% "
            f"{row['fit_gap']:>7.2f} {row['max_gain_error'] * 100:>8.2f}% "
            f"{row['log_det']:>10.2f} {row['condition_number']:>10.3g}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["S3", "S6", "all"], default="all")
    parser.add_argument("--samples", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--window-size", type=int, default=60)
    parser.add_argument("--budget-windows", type=int, default=12)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--repeats", type=int, default=1, help="consecutive seeds to average")
    parser.add_argument("--json", type=Path, default=None)
    arguments = parser.parse_args()

    names = ["S3", "S6"] if arguments.scenario == "all" else [arguments.scenario]
    document: dict[str, Any] = {"runs": [], "summary": {}}
    for name in names:
        reports = [
            run_experiment(
                scenario_name=name,
                n_samples=arguments.samples,
                seed=arguments.seed + offset,
                window_size=arguments.window_size,
                budget_windows=arguments.budget_windows,
                train_ratio=arguments.train_ratio,
            )
            for offset in range(arguments.repeats)
        ]
        document["runs"].extend(reports)
        configuration = reports[0]["configuration"]
        print(
            f"[{configuration['scenario']}] {configuration['n_samples']} samples, "
            f"{configuration['train_rows']} training rows, "
            f"{configuration['candidate_windows']} candidate windows of "
            f"{configuration['window_size']}, budget {configuration['budget_windows']} windows"
        )
        print()
        print(format_table(reports[0]))
        print()
        ids = next(row for row in reports[0]["results"] if row["strategy"] == "ids")
        print(
            f"lazy greedy evaluated {ids['evaluated_candidates']} candidates "
            f"vs {ids['naive_candidate_evaluations']} naive "
            f"({ids['lazy_speedup']:.2f}x fewer), stopped: {ids['stopped_reason']}"
        )
        print(
            "information retention vs full training data: "
            f"{ids['information_retention'] * 100:.2f}%"
        )
        if arguments.repeats > 1:
            summary = aggregate(reports)
            document["summary"][configuration["scenario"]] = summary
            print()
            print(format_summary(summary, repeats=arguments.repeats))
        print()

    if arguments.json:
        arguments.json.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {arguments.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
