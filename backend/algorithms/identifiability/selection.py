"""Identifiability-driven selection of high-value modelling segments.

The industrial pain this solves is stated in the A14 brief: the genuinely informative
identification samples are drowned in steady-state data. The usual answer is a weighted
"quality score" whose coefficients nobody can defend. This module answers instead with
optimal experiment design applied retrospectively to historical data.

Let each candidate window ``W`` contribute the Gram block ``A_W = Phi_W^T Phi_W``. For a
selected set ``S`` the objective is

    J(S) = log det( lambda * I + sum_{W in S} A_W )

``J`` is monotone and submodular in ``S``, so greedy maximisation under a cardinality
budget is within ``1 - 1/e`` of the optimum, and — because the marginal gains can only
shrink — the lazy (CELF) variant returns the identical selection while evaluating a small
fraction of the candidates. The marginal gain of each accepted window, expressed in bits,
is the "how much did this segment actually teach the model" number the report shows the
engineer, and it is a physical quantity rather than a tuned weight.
"""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from algorithms.identifiability.excitation import (
    NATS_PER_BIT,
    ExcitationReport,
    log_det_information,
    marginal_log_det_gain,
    profile_excitation,
)
from algorithms.identifiability.regressor import (
    FloatArray,
    IdentifiabilityError,
    IntArray,
    RegressorMatrix,
)

# Below this many selected windows the design goes rank-deficient on heterogeneous
# excitation even under the D-optimal criterion: a handful of windows cannot span every
# parameter direction however cleverly they are picked. Measured in EXP-3.0 — at a 5%
# budget, window 60 (3 windows) stays full-rank while windows 90/120/180 (2/1/1 windows)
# are rank-deficient on every one of 5 seeds.
MIN_WINDOWS_FOR_COVERAGE = 3


@dataclass(frozen=True)
class WindowGrid:
    """Candidate contiguous windows expressed as row positions in a regressor matrix."""

    positions: tuple[IntArray, ...]
    window_size: int
    stride: int
    source_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_indices:
            object.__setattr__(self, "source_indices", tuple(range(len(self.positions))))
        elif len(self.source_indices) != len(self.positions):
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "source_indices 必须与候选窗口数量一致",
                {"positions": len(self.positions), "source_indices": len(self.source_indices)},
            )

    @property
    def count(self) -> int:
        return len(self.positions)

    def subset(self, indices: Sequence[int]) -> WindowGrid:
        """Keep only the listed windows, preserving their identity in the original grid.

        Used to hand the gate's survivors to the selector without renumbering them, so a
        report can still say "window 37 was chosen" and mean the same window the gate
        scored.
        """

        chosen = list(indices)
        invalid = [index for index in chosen if not 0 <= index < len(self.positions)]
        if invalid:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "窗口下标越界",
                {"invalid_indices": invalid, "count": len(self.positions)},
            )
        return WindowGrid(
            positions=tuple(self.positions[index] for index in chosen),
            window_size=self.window_size,
            stride=self.stride,
            source_indices=tuple(self.source_indices[index] for index in chosen),
        )


@dataclass(frozen=True)
class SelectedWindow:
    """One accepted window and the evidence that justified accepting it."""

    rank: int
    window_index: int
    start_index: int
    end_index: int
    n_rows: int
    information_gain_nats: float
    information_gain_bits: float
    cumulative_log_det: float
    input_energy: float
    output_energy: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "window_index": self.window_index,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "n_rows": self.n_rows,
            "information_gain_nats": self.information_gain_nats,
            "information_gain_bits": self.information_gain_bits,
            "cumulative_log_det": self.cumulative_log_det,
            "input_energy": self.input_energy,
            "output_energy": self.output_energy,
        }


@dataclass(frozen=True)
class SelectionResult:
    """The selected subset plus everything the report and the audit log need."""

    selected: tuple[SelectedWindow, ...]
    row_positions: IntArray
    regressor: RegressorMatrix
    excitation: ExcitationReport
    baseline_log_det: float
    selected_log_det: float
    candidate_count: int
    evaluated_candidates: int
    naive_candidate_evaluations: int
    coverage_ratio: float
    stopped_reason: str

    @property
    def lazy_speedup(self) -> float:
        """How many candidate evaluations lazy greedy saved versus the naive loop."""

        if self.evaluated_candidates == 0:
            return 1.0
        return self.naive_candidate_evaluations / self.evaluated_candidates

    @property
    def budget_advisory(self) -> str | None:
        """Warn when the budget was too small for the criterion to do its job.

        Measured in ``EXP-3.0``: below :data:`MIN_WINDOWS_FOR_COVERAGE` selected windows the
        D-optimal criterion goes rank-deficient on heterogeneous excitation just like the
        heuristics do — not because the criterion failed, but because a handful of windows
        cannot span every parameter direction no matter how they are chosen. The engineer
        needs to be told that widening the budget or shortening the window is the fix, and
        that a model fitted from this subset is not trustworthy.

        This is an advisory, not a block. Sometimes two windows is genuinely all the record
        contains, and refusing to proceed would leave the engineer with nothing. The
        rank-deficiency flag on the excitation report remains the hard signal.
        """

        if len(self.selected) >= MIN_WINDOWS_FOR_COVERAGE:
            return None
        return (
            f"仅选出 {len(self.selected)} 个窗口（建议至少 {MIN_WINDOWS_FOR_COVERAGE} 个）。"
            "实测表明窗口数过少时，信息准则也无法覆盖全部参数方向，设计矩阵仍可能秩亏"
            "（EXP-3.0）。建议增大样本预算或缩短窗口长度后重跑。"
        )

    @property
    def information_retention(self) -> float:
        """Fraction of the full-data ``log det`` retained by the selected subset.

        Reported as a ratio of information volumes; values above 1 mean the subset is
        better conditioned than the full record, which happens when steady-state samples
        add rows without adding rank.
        """

        if not np.isfinite(self.baseline_log_det) or self.baseline_log_det == 0:
            return float("nan")
        return self.selected_log_det / self.baseline_log_det

    def to_payload(self) -> dict[str, Any]:
        return {
            "selected_windows": [window.to_payload() for window in self.selected],
            "selected_rows": int(self.row_positions.size),
            "candidate_count": self.candidate_count,
            "evaluated_candidates": self.evaluated_candidates,
            "naive_candidate_evaluations": self.naive_candidate_evaluations,
            "lazy_speedup": self.lazy_speedup,
            "coverage_ratio": self.coverage_ratio,
            "baseline_log_det": self.baseline_log_det,
            "selected_log_det": self.selected_log_det,
            "information_retention": self.information_retention,
            "stopped_reason": self.stopped_reason,
            "budget_advisory": self.budget_advisory,
            "excitation": self.excitation.to_payload(),
        }


def build_window_grid(
    regressor: RegressorMatrix,
    *,
    window_size: int,
    stride: int | None = None,
    row_range: tuple[int, int] | None = None,
) -> WindowGrid:
    """Slice a regressor into candidate windows without crossing a partition boundary.

    ``row_range`` is a half-open interval of row positions; restricting it to the training
    partition is what keeps validation and test samples out of the selection decision.
    """

    if window_size < 1:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "window_size 必须大于等于 1",
            {"window_size": window_size},
        )
    step = window_size if stride is None else stride
    if step < 1:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "stride 必须大于等于 1",
            {"stride": step},
        )
    first, last = (0, regressor.n_rows) if row_range is None else row_range
    first = max(0, first)
    last = min(regressor.n_rows, last)
    if last - first < window_size:
        raise IdentifiabilityError(
            "INSUFFICIENT_ROWS",
            "可选区间长度不足以切出一个候选窗口",
            {"available_rows": last - first, "window_size": window_size},
        )
    starts = range(first, last - window_size + 1, step)
    positions = tuple(np.arange(start, start + window_size, dtype=int) for start in starts)
    return WindowGrid(positions=positions, window_size=window_size, stride=step)


def select_informative_windows(
    regressor: RegressorMatrix,
    grid: WindowGrid,
    *,
    budget_rows: int | None = None,
    budget_windows: int | None = None,
    ridge: float = 1e-6,
    min_information_gain_bits: float = 0.0,
    inputs: dict[str, FloatArray] | None = None,
) -> SelectionResult:
    """Greedily select the windows that maximise ``log det`` of the Fisher information.

    Exactly one of ``budget_rows`` / ``budget_windows`` bounds the selection; the loop also
    stops as soon as the next best window would contribute less than
    ``min_information_gain_bits``, which is what prevents the optimiser from padding the
    data set with steady-state windows that cost compute and teach nothing.
    """

    if grid.count == 0:
        raise IdentifiabilityError(
            "NO_DYNAMIC_SEGMENT_FOUND",
            "候选窗口为空，无法执行可辨识性优选",
        )
    if ridge <= 0:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "ridge 必须为正值，否则空集的 log det 无定义",
            {"ridge": ridge},
        )
    max_windows, max_rows = _resolve_budget(
        grid,
        budget_rows=budget_rows,
        budget_windows=budget_windows,
    )

    features = regressor.features
    parameter_count = regressor.n_parameters
    grams = [features[position].T @ features[position] for position in grid.positions]

    information = ridge * np.eye(parameter_count, dtype=float)
    factor = np.linalg.cholesky(information)
    current_log_det = log_det_information(information)
    baseline_log_det = log_det_information(
        features.T @ features + ridge * np.eye(parameter_count, dtype=float)
    )

    # Lazy greedy: submodularity means a stale gain is an upper bound, so a candidate whose
    # stale gain already loses to a freshly evaluated one can never win this round.
    heap: list[tuple[float, int, int]] = []
    evaluated = 0
    for index, gram in enumerate(grams):
        gain = marginal_log_det_gain(factor, gram)
        evaluated += 1
        heapq.heappush(heap, (-gain, index, 0))

    selected: list[SelectedWindow] = []
    chosen_rows: list[IntArray] = []
    covered = np.zeros(regressor.n_rows, dtype=bool)
    taken: set[int] = set()
    naive_evaluations = 0
    stopped_reason = "budget_reached"
    minimum_gain_nats = min_information_gain_bits * NATS_PER_BIT

    while len(selected) < max_windows:
        naive_evaluations += grid.count - len(taken)
        best_index = -1
        best_gain = float("-inf")
        while heap:
            negative_gain, index, stamp = heapq.heappop(heap)
            if index in taken:
                continue
            if stamp == len(selected):
                best_index = index
                best_gain = -negative_gain
                break
            gain = marginal_log_det_gain(factor, grams[index])
            evaluated += 1
            heapq.heappush(heap, (-gain, index, len(selected)))
        if best_index < 0:
            stopped_reason = "candidates_exhausted"
            break
        if best_gain <= minimum_gain_nats:
            stopped_reason = "information_gain_below_threshold"
            break

        positions = grid.positions[best_index]
        # Windows may overlap when stride < window_size, so the budget counts unique rows.
        projected_rows = int(np.count_nonzero(covered)) + int(np.count_nonzero(~covered[positions]))
        if max_rows is not None and projected_rows > max_rows and selected:
            stopped_reason = "row_budget_reached"
            break

        information = information + grams[best_index]
        factor = np.linalg.cholesky(information)
        current_log_det += best_gain
        taken.add(best_index)
        chosen_rows.append(positions)
        covered[positions] = True
        selected.append(
            SelectedWindow(
                rank=len(selected) + 1,
                window_index=grid.source_indices[best_index],
                start_index=int(regressor.time_indices[positions[0]]),
                end_index=int(regressor.time_indices[positions[-1]]),
                n_rows=int(positions.size),
                information_gain_nats=best_gain,
                information_gain_bits=best_gain / NATS_PER_BIT,
                cumulative_log_det=current_log_det,
                input_energy=_input_energy(regressor, positions),
                output_energy=_output_energy(regressor, positions),
            )
        )

    if not selected:
        raise IdentifiabilityError(
            "NO_DYNAMIC_SEGMENT_FOUND",
            "没有任何候选窗口的信息增益超过阈值",
            {"min_information_gain_bits": min_information_gain_bits},
        )

    row_positions = np.unique(np.concatenate(chosen_rows))
    subset = regressor.take(row_positions)
    subset_inputs = (
        None
        if inputs is None
        else {
            column: np.asarray(values, dtype=float)[regressor.time_indices[row_positions]]
            for column, values in inputs.items()
        }
    )
    excitation = profile_excitation(subset, inputs=subset_inputs, ridge=ridge)
    return SelectionResult(
        selected=tuple(selected),
        row_positions=row_positions,
        regressor=subset,
        excitation=excitation,
        baseline_log_det=baseline_log_det,
        selected_log_det=log_det_information(
            subset.features.T @ subset.features + ridge * np.eye(parameter_count, dtype=float)
        ),
        candidate_count=grid.count,
        evaluated_candidates=evaluated,
        naive_candidate_evaluations=naive_evaluations,
        coverage_ratio=float(row_positions.size) / float(regressor.n_rows),
        stopped_reason=stopped_reason,
    )


def select_by_energy(
    regressor: RegressorMatrix,
    grid: WindowGrid,
    *,
    budget_windows: int | None = None,
    budget_rows: int | None = None,
) -> IntArray:
    """Rank windows by input change energy only — the heuristic baseline to beat.

    This is the behaviour a conventional "dynamic segment score" reduces to. It is kept in
    the library on purpose so the ablation experiment compares against a real
    implementation rather than a straw man.
    """

    scores = np.asarray(
        [_input_energy(regressor, positions) for positions in grid.positions],
        dtype=float,
    )
    return take_top_k(
        grid,
        scores,
        budget_windows=budget_windows,
        budget_rows=budget_rows,
    )


def take_top_k(
    grid: WindowGrid,
    scores: FloatArray,
    *,
    budget_windows: int | None = None,
    budget_rows: int | None = None,
) -> IntArray:
    """Collect the highest-scoring windows as deduplicated row positions.

    Shared by every per-window scoring baseline so they differ only in how they score,
    never in how they spend the budget.

    ``budget_rows`` exists because comparing strategies at a fixed *window* count is not a
    fair comparison once window length varies: overlapping windows deduplicate differently,
    so the same window count buys different sample counts. Windows are taken in score order
    until the next one would push the deduplicated row count over the budget — never past
    it, so a row budget is a ceiling rather than a target.
    """

    if (budget_rows is None) == (budget_windows is None):
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "必须且只能指定 budget_rows 或 budget_windows 之一",
            {"budget_rows": budget_rows, "budget_windows": budget_windows},
        )
    if grid.count == 0:
        raise IdentifiabilityError(
            "NO_DYNAMIC_SEGMENT_FOUND",
            "候选窗口为空，无法执行 Top-K 优选",
        )

    order = [int(index) for index in np.argsort(-np.asarray(scores, dtype=float))]

    if budget_windows is not None:
        if budget_windows < 1:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "budget_windows 必须大于等于 1",
                {"budget_windows": budget_windows},
            )
        chosen = order[: min(budget_windows, grid.count)]
        return np.unique(np.concatenate([grid.positions[index] for index in chosen]))

    assert budget_rows is not None
    if budget_rows < grid.window_size:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "budget_rows 必须至少容纳一个候选窗口",
            {"budget_rows": budget_rows, "window_size": grid.window_size},
        )
    accumulated: set[int] = set()
    for index in order:
        candidate = accumulated | {int(row) for row in grid.positions[index]}
        if len(candidate) > budget_rows:
            continue
        accumulated = candidate
    return np.array(sorted(accumulated), dtype=int)


def _resolve_budget(
    grid: WindowGrid,
    *,
    budget_rows: int | None,
    budget_windows: int | None,
) -> tuple[int, int | None]:
    if (budget_rows is None) == (budget_windows is None):
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "必须且只能指定 budget_rows 或 budget_windows 之一",
            {"budget_rows": budget_rows, "budget_windows": budget_windows},
        )
    if budget_windows is not None:
        if budget_windows < 1:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "budget_windows 必须大于等于 1",
                {"budget_windows": budget_windows},
            )
        return min(budget_windows, grid.count), None
    assert budget_rows is not None
    if budget_rows < grid.window_size:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "budget_rows 必须至少容纳一个候选窗口",
            {"budget_rows": budget_rows, "window_size": grid.window_size},
        )
    return grid.count, budget_rows


def _input_energy(regressor: RegressorMatrix, positions: Sequence[int] | IntArray) -> float:
    structure = regressor.structure
    offset = structure.na
    columns = [offset]
    for column in structure.input_columns[:-1]:
        offset += structure.nb[column]
        columns.append(offset)
    block = regressor.features[np.asarray(positions, dtype=int)][:, columns]
    if block.shape[0] < 2:
        return 0.0
    return float(np.mean(np.sum(np.square(np.diff(block, axis=0)), axis=1)))


def _output_energy(regressor: RegressorMatrix, positions: Sequence[int] | IntArray) -> float:
    block = regressor.targets[np.asarray(positions, dtype=int)]
    if block.size < 2:
        return 0.0
    return float(np.mean(np.square(np.diff(block))))
