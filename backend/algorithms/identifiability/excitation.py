"""Fisher information, persistent excitation and optimal-design criteria for ARX data.

For an ARX model with white residual variance ``sigma^2``, the least-squares estimate has
covariance ``sigma^2 (Phi^T Phi)^-1``. The information a data set carries about the
parameters is therefore the Gram matrix ``M = Phi^T Phi`` (up to the noise scale), and
"which samples are worth keeping" becomes a classical optimal-experiment-design question
rather than a matter of hand-tuned weights:

* D-optimality maximises ``log det M`` — it shrinks the volume of the joint confidence
  ellipsoid, and it is the criterion this project optimises because it is monotone and
  submodular in the sample set, which buys a greedy approximation guarantee.
* A-optimality minimises ``trace(M^-1)`` — the summed parameter variance.
* E-optimality maximises ``lambda_min(M)`` — the worst-conditioned parameter direction.

Persistent excitation is reported alongside because D-optimality answers "how good is
this data" while the PE order answers the prior question "is this data capable of
identifying a model of this order at all".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from algorithms.identifiability.regressor import (
    FloatArray,
    IdentifiabilityError,
    RegressorMatrix,
)

NATS_PER_BIT = float(np.log(2.0))

# Finite-sample conditioning threshold for the persistent-excitation test. Any real record
# containing a transition has a formally full-rank covariance matrix, so the question is
# never "is it singular" but "is the weakest direction supported by enough samples to be
# estimable". Calibrated on the S1-S6 benchmarks: at 1e-3 the test reproduces the textbook
# result that a signal built from m distinct level changes is persistently exciting of
# order m (one step -> 1, two steps -> 2, white noise -> the requested maximum).
DEFAULT_EXCITATION_TOLERANCE = 1e-3


@dataclass(frozen=True)
class ExcitationReport:
    """Explainable evidence about how identifiable a candidate data set is."""

    n_rows: int
    n_parameters: int
    log_det: float
    log_det_bits: float
    condition_number: float
    min_eigenvalue: float
    a_optimality: float
    persistent_excitation_order: dict[str, int]
    required_excitation_order: dict[str, int]
    excitation_satisfied: bool
    rank: int
    rank_deficient: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_parameters": self.n_parameters,
            "log_det": self.log_det,
            "log_det_bits": self.log_det_bits,
            "condition_number": self.condition_number,
            "min_eigenvalue": self.min_eigenvalue,
            "a_optimality": self.a_optimality,
            "persistent_excitation_order": dict(self.persistent_excitation_order),
            "required_excitation_order": dict(self.required_excitation_order),
            "excitation_satisfied": self.excitation_satisfied,
            "rank": self.rank,
            "rank_deficient": self.rank_deficient,
        }


def fisher_information(features: FloatArray, *, ridge: float = 0.0) -> FloatArray:
    """Return the (regularised) Gram matrix ``Phi^T Phi + ridge * I``.

    ``ridge`` keeps ``log det`` finite for candidate sets that are smaller than the
    parameter vector, which is what makes greedy selection able to start from nothing.
    """

    matrix = np.asarray(features, dtype=float)
    if matrix.ndim != 2:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "Fisher 信息矩阵需要二维回归矩阵",
            {"shape": list(matrix.shape)},
        )
    if ridge < 0:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "ridge 正则项必须非负",
            {"ridge": ridge},
        )
    gram = matrix.T @ matrix
    if ridge:
        gram = gram + ridge * np.eye(gram.shape[0], dtype=float)
    return np.asarray(gram, dtype=float)


def log_det_information(information: FloatArray) -> float:
    """Return ``log det`` of a PSD matrix, or ``-inf`` when it is singular."""

    sign, value = np.linalg.slogdet(np.asarray(information, dtype=float))
    if sign <= 0:
        return float("-inf")
    return float(value)


def persistent_excitation_order(
    signal: FloatArray,
    *,
    max_order: int,
    tolerance: float = DEFAULT_EXCITATION_TOLERANCE,
) -> int:
    """Return the largest ``n <= max_order`` for which the signal is PE of order ``n``.

    A signal is persistently exciting of order ``n`` when the ``n x n`` covariance matrix
    of ``[u(k), ..., u(k-n+1)]`` is positive definite. Numerically we require the
    eigenvalue spread to stay above ``tolerance``, which is what separates a genuinely
    exciting segment from one that only looks non-constant because of noise.

    A long steady hold therefore scores 0 or 1 while a multi-level step sequence scores
    high — exactly the distinction the closed loop needs and the reason a steady segment
    contributes almost nothing to the identification, no matter how clean it looks.
    """

    values = np.asarray(signal, dtype=float)
    values = values[np.isfinite(values)]
    if max_order < 1:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            "max_order 必须大于等于 1",
            {"max_order": max_order},
        )
    if values.size == 0:
        return 0
    centered = values - float(np.mean(values))
    scale = float(np.max(np.abs(values)))
    if scale <= 0:
        return 0
    order = 0
    for candidate in range(1, max_order + 1):
        window_count = values.size - candidate + 1
        if window_count < candidate + 1:
            break
        stacked = np.lib.stride_tricks.sliding_window_view(values, candidate)
        covariance = (stacked.T @ stacked) / float(window_count)
        eigenvalues = np.linalg.eigvalsh(covariance)
        largest = float(eigenvalues[-1])
        smallest = float(eigenvalues[0])
        if largest <= 0 or smallest <= tolerance * largest:
            break
        order = candidate
    if order == 0 and float(np.max(np.abs(centered))) <= tolerance * scale:
        # A constant, non-zero hold still excites the static gain direction only.
        return 1 if scale > 0 else 0
    return order


def profile_excitation(
    regressor: RegressorMatrix,
    *,
    inputs: dict[str, FloatArray] | None = None,
    ridge: float = 0.0,
    tolerance: float = DEFAULT_EXCITATION_TOLERANCE,
) -> ExcitationReport:
    """Summarise identifiability of a candidate regressor set for the report layer.

    ``inputs`` are the raw input signals restricted to the same samples; when omitted the
    PE order is computed from the input block of the regressor itself.
    """

    structure = regressor.structure
    information = fisher_information(regressor.features, ridge=ridge)
    eigenvalues = np.linalg.eigvalsh(information)
    smallest = float(eigenvalues[0])
    largest = float(eigenvalues[-1])
    condition = float("inf") if smallest <= 0 else largest / smallest
    a_optimality = float("inf") if smallest <= 0 else float(np.sum(1.0 / eigenvalues))
    rank = int(np.linalg.matrix_rank(regressor.features))

    if inputs is None:
        inputs = _input_block_signals(regressor)
    required = {column: structure.nb[column] + structure.na for column in structure.input_columns}
    orders = {
        column: persistent_excitation_order(
            inputs[column],
            max_order=max(required[column] + 2, 2),
            tolerance=tolerance,
        )
        for column in structure.input_columns
        if column in inputs
    }
    satisfied = all(orders.get(column, 0) >= required[column] for column in structure.input_columns)

    log_det = log_det_information(information)
    return ExcitationReport(
        n_rows=regressor.n_rows,
        n_parameters=regressor.n_parameters,
        log_det=log_det,
        log_det_bits=log_det / NATS_PER_BIT if np.isfinite(log_det) else float("-inf"),
        condition_number=condition,
        min_eigenvalue=smallest,
        a_optimality=a_optimality,
        persistent_excitation_order=orders,
        required_excitation_order=required,
        excitation_satisfied=satisfied,
        rank=rank,
        rank_deficient=rank < regressor.n_parameters,
    )


def _input_block_signals(regressor: RegressorMatrix) -> dict[str, FloatArray]:
    """Recover one column per input from the regressor's ``b`` block."""

    structure = regressor.structure
    offset = structure.na
    signals: dict[str, FloatArray] = {}
    for column in structure.input_columns:
        signals[column] = np.asarray(regressor.features[:, offset], dtype=float)
        offset += structure.nb[column]
    return signals


def marginal_log_det_gain(
    cholesky_factor: NDArray[np.floating[Any]],
    addition: NDArray[np.floating[Any]],
) -> float:
    """Return ``log det(M + A) - log det(M)`` given the Cholesky factor ``L`` of ``M``.

    Using the identity ``log det(M + A) - log det(M) = log det(I + L^-1 A L^-T)`` keeps the
    greedy loop at ``O(p^3)`` per candidate instead of refactorising the full Gram matrix,
    and never forms ``M^-1`` explicitly. ``A`` is the candidate block's own Gram matrix,
    which the caller precomputes once and reuses across every greedy iteration.
    """

    addition = np.asarray(addition, dtype=float)
    solved = np.linalg.solve(cholesky_factor, addition)
    projected = np.linalg.solve(cholesky_factor, solved.T).T
    symmetric = 0.5 * (projected + projected.T)
    sign, value = np.linalg.slogdet(np.eye(symmetric.shape[0]) + symmetric)
    if sign <= 0:
        return float("-inf")
    return float(value)
