"""Sensitivity sweep for window length and sample budget.

``EXP-1.1`` §7 item 4 records the largest remaining threat to its own conclusions: every
number in it was measured at ``window_size=60`` with a budget of 12 windows. A selection
method that only wins at one operating point is not a method, it is a coincidence. This
script varies both axes and reports where each strategy holds up and where it does not.

Two design decisions matter for the comparison to mean anything:

* **The budget is expressed in rows, not windows.** At a fixed window count, a length-30
  window and a length-180 window buy wildly different sample counts, and overlapping
  windows deduplicate differently on top of that. Holding the row budget fixed is what
  makes "same budget, different method" a true statement.
* **The row budget is a ceiling, never a target.** A strategy that stops early because the
  information gain died is reported with its actual coverage, not padded up to the limit.
  That is the behaviour under test, not an artifact to be normalised away.

Usage::

    python scripts/sweep_selection_sensitivity.py
    python scripts/sweep_selection_sensitivity.py --repeats 5 --json ../docs/experiments/sensitivity-sweep.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.identifiability.excitation import profile_excitation  # noqa: E402
from algorithms.identifiability.regressor import (  # noqa: E402
    RegressorMatrix,
    build_regressor,
)
from algorithms.identifiability.selection import (  # noqa: E402
    build_window_grid,
    select_by_energy,
    select_informative_windows,
)
from algorithms.identifiability.validation import validate_model  # noqa: E402
from algorithms.identifiability.weighted_score import select_by_weighted_score  # noqa: E402
from scripts.benchmark_identifiability import (  # noqa: E402
    Scenario,
    _true_gains,
    fit_ols,
    synthesize,
)

WINDOW_SIZES = (30, 60, 90, 120, 180)
COVERAGE_TARGETS = (0.05, 0.10, 0.15, 0.25)
STRATEGIES = ("energy", "weighted", "ids")


def sweep_cell(
    scenario: Scenario,
    *,
    window_size: int,
    budget_rows: int,
    train_stop: int,
    n_samples: int,
) -> list[dict[str, Any]]:
    """One (window length, row budget) point: every strategy, same data, same budget."""

    full = build_regressor(
        inputs=scenario.inputs,
        output=scenario.output,
        structure=scenario.structure,
        start=0,
        stop=train_stop,
    )
    grid = build_window_grid(full, window_size=window_size, stride=max(1, window_size // 2))
    validation_range = (train_stop, n_samples)

    rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        if strategy == "energy":
            positions = select_by_energy(full, grid, budget_rows=budget_rows)
        elif strategy == "weighted":
            positions = select_by_weighted_score(
                full,
                grid,
                inputs=scenario.inputs,
                output=scenario.output,
                budget_rows=budget_rows,
            )
        else:
            positions = select_informative_windows(
                full, grid, budget_rows=budget_rows, ridge=1e-6, inputs=scenario.inputs
            ).row_positions

        subset = full.take(positions)
        if subset.n_rows <= full.n_parameters:
            # Not enough rows to even form a determined system: record it as such rather
            # than letting lstsq return a least-norm answer that looks like an estimate.
            rows.append(
                {
                    "strategy": strategy,
                    "train_rows": int(subset.n_rows),
                    "coverage_ratio": subset.n_rows / full.n_rows,
                    "underdetermined": True,
                }
            )
            continue

        theta = fit_ols(subset)
        rows.append(_evaluate(strategy, theta, scenario, subset, full, validation_range))
    return rows


def _evaluate(
    strategy: str,
    theta: np.ndarray,
    scenario: Scenario,
    subset: RegressorMatrix,
    full: RegressorMatrix,
    validation_range: tuple[int, int],
) -> dict[str, Any]:
    truth = scenario.true_theta
    validation = validate_model(
        theta,
        scenario.structure,
        inputs=scenario.inputs,
        output=scenario.output,
        start=validation_range[0],
        stop=validation_range[1],
    )
    profile = profile_excitation(
        subset,
        inputs={column: values[subset.time_indices] for column, values in scenario.inputs.items()},
        ridge=1e-6,
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
    return {
        "strategy": strategy,
        "train_rows": int(subset.n_rows),
        "coverage_ratio": subset.n_rows / full.n_rows,
        "parameter_error": float(np.linalg.norm(theta - truth) / np.linalg.norm(truth)),
        "one_step_fit": validation.one_step_fit,
        "free_run_fit": validation.free_run_fit,
        "max_gain_error": gain_error,
        "condition_number": profile.condition_number,
        "rank_deficient": bool(profile.rank_deficient),
        "underdetermined": False,
    }


def run_sweep(
    *,
    scenario_names: tuple[str, ...],
    n_samples: int,
    seed: int,
    repeats: int,
    train_ratio: float,
) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for name in scenario_names:
        for offset in range(repeats):
            scenario = synthesize(scenario=name, n_samples=n_samples, seed=seed + offset)
            train_stop = int(n_samples * train_ratio)
            for window_size in WINDOW_SIZES:
                for coverage in COVERAGE_TARGETS:
                    budget_rows = int(train_stop * coverage)
                    if budget_rows < window_size:
                        continue  # the budget cannot hold a single window; not a data point
                    cells.append(
                        {
                            "scenario": name,
                            "seed": seed + offset,
                            "window_size": window_size,
                            "coverage_target": coverage,
                            "budget_rows": budget_rows,
                            "results": sweep_cell(
                                scenario,
                                window_size=window_size,
                                budget_rows=budget_rows,
                                train_stop=train_stop,
                                n_samples=n_samples,
                            ),
                        }
                    )
    return {
        "configuration": {
            "scenarios": list(scenario_names),
            "n_samples": n_samples,
            "seed": seed,
            "repeats": repeats,
            "train_ratio": train_ratio,
            "window_sizes": list(WINDOW_SIZES),
            "coverage_targets": list(COVERAGE_TARGETS),
        },
        "cells": cells,
    }


def aggregate(document: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Mean over seeds, keyed by scenario / window size / coverage / strategy."""

    buckets: dict[tuple[str, int, float, str], list[dict[str, Any]]] = {}
    for cell in document["cells"]:
        for row in cell["results"]:
            key = (cell["scenario"], cell["window_size"], cell["coverage_target"], row["strategy"])
            buckets.setdefault(key, []).append(row)

    summary: dict[str, dict[str, dict[str, Any]]] = {}
    for (scenario, window_size, coverage, strategy), group in buckets.items():
        usable = [row for row in group if not row["underdetermined"]]
        outer = summary.setdefault(scenario, {})
        inner = outer.setdefault(f"w{window_size}_c{coverage:.2f}", {})
        if not usable:
            inner[strategy] = {"underdetermined_runs": len(group)}
            continue
        inner[strategy] = {
            "parameter_error": float(np.mean([row["parameter_error"] for row in usable])),
            "free_run_fit": float(np.mean([row["free_run_fit"] for row in usable])),
            "max_gain_error": float(np.mean([row["max_gain_error"] for row in usable])),
            "coverage_ratio": float(np.mean([row["coverage_ratio"] for row in usable])),
            "rank_deficient_runs": sum(1 for row in usable if row["rank_deficient"]),
            "runs": len(usable),
            "underdetermined_runs": len(group) - len(usable),
        }
    return summary


def win_counts(summary: dict[str, dict[str, dict[str, Any]]]) -> dict[str, dict[str, int]]:
    """How many operating points each strategy wins on parameter error, per scenario."""

    counts: dict[str, dict[str, int]] = {}
    for scenario, points in summary.items():
        tally = dict.fromkeys(STRATEGIES, 0)
        for entry in points.values():
            scored = {
                strategy: values["parameter_error"]
                for strategy, values in entry.items()
                if "parameter_error" in values
            }
            if len(scored) < 2:
                continue
            tally[min(scored, key=lambda key: scored[key])] += 1
        counts[scenario] = tally
    return counts


def format_scenario(scenario: str, points: dict[str, dict[str, Any]]) -> str:
    header = (
        f"{'window/cover':<16}"
        + "".join(f"{strategy + ' θerr':>16}" for strategy in STRATEGIES)
        + f"{'秩亏(e/w/i)':>14}"
    )
    lines = [f"[{scenario}]", header, "-" * len(header)]
    for label in sorted(points, key=lambda key: (int(key[1:].split("_")[0]), key)):
        entry = points[label]
        cells = ""
        deficient = []
        for strategy in STRATEGIES:
            values = entry.get(strategy, {})
            if "parameter_error" in values:
                cells += f"{values['parameter_error'] * 100:>15.2f}%"
                deficient.append(str(values["rank_deficient_runs"]))
            else:
                cells += f"{'欠定':>16}"
                deficient.append("-")
        lines.append(f"{label:<16}{cells}{'/'.join(deficient):>14}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["S3", "S6", "all"], default="all")
    parser.add_argument("--samples", type=int, default=6000)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--json", type=Path, default=None)
    arguments = parser.parse_args()

    names = ("S3", "S6") if arguments.scenario == "all" else (arguments.scenario,)
    document = run_sweep(
        scenario_names=names,
        n_samples=arguments.samples,
        seed=arguments.seed,
        repeats=arguments.repeats,
        train_ratio=arguments.train_ratio,
    )
    summary = aggregate(document)
    document["summary"] = summary
    document["win_counts"] = win_counts(summary)

    print(
        f"{len(document['cells'])} operating points "
        f"({len(WINDOW_SIZES)} window sizes × {len(COVERAGE_TARGETS)} coverage targets × "
        f"{arguments.repeats} seeds × {len(names)} scenarios)\n"
    )
    for scenario in names:
        print(format_scenario(scenario, summary[scenario]))
        print()
    print("参数误差最优次数（每个操作点计一次）：")
    for scenario, tally in document["win_counts"].items():
        detail = "，".join(f"{strategy} {count}" for strategy, count in tally.items())
        print(f"  {scenario}: {detail}")

    if arguments.json:
        arguments.json.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {arguments.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
