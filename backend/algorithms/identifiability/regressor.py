"""Pure-NumPy MISO ARX regressor construction shared by selection and validation.

The regressor convention matches ``app.services.identification_service``:

    y(k) + a_1 y(k-1) + ... + a_na y(k-na)
        = sum_j sum_{l=0}^{nb_j-1} b[j,l] * u_j(k - nk_j - l) + e(k)

so a row is ``phi(k) = [-y(k-1) ... -y(k-na), u_1(k-nk_1) ... , u_m(k-nk_m-nb_m+1)]``
and ``y(k) = phi(k) @ theta + e(k)``.

Unlike the service, this module takes plain arrays. That keeps it usable from the
closed-loop optimizer, from tests, and from offline experiments without dragging in
Pydantic request models or artifact storage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int_]


class IdentifiabilityError(Exception):
    """Stable algorithm error suitable for mapping onto an API ErrorEnvelope."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ArxStructure:
    """The model structure that fixes the regressor layout.

    ``na`` is the output order, ``nb[column]`` the numerator order of each input and
    ``nk[column]`` its pure input-output delay in samples.
    """

    na: int
    nb: dict[str, int]
    nk: dict[str, int]
    input_columns: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        na: int,
        nb: Mapping[str, int] | int,
        nk: Mapping[str, int] | int,
        input_columns: Sequence[str],
    ) -> ArxStructure:
        columns = tuple(input_columns)
        if not columns:
            raise IdentifiabilityError(
                "INVALID_DATASET_SCHEMA",
                "ARX 结构至少需要一个输入变量",
            )
        if len(set(columns)) != len(columns):
            raise IdentifiabilityError(
                "INVALID_DATASET_SCHEMA",
                "ARX 输入变量存在重复列名",
                {"input_columns": list(columns)},
            )
        if na < 1:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                "na 必须大于等于 1",
                {"na": na},
            )
        nb_map = _expand_orders(nb, columns, name="nb", minimum=1)
        nk_map = _expand_orders(nk, columns, name="nk", minimum=0)
        return cls(na=na, nb=nb_map, nk=nk_map, input_columns=columns)

    @property
    def parameter_count(self) -> int:
        return self.na + sum(self.nb[column] for column in self.input_columns)

    @property
    def max_history(self) -> int:
        """The first sample index for which a complete regressor row exists."""

        input_history = max(self.nk[column] + self.nb[column] - 1 for column in self.input_columns)
        return max(self.na, input_history)

    def feature_names(self) -> list[str]:
        names = [f"a{position}" for position in range(1, self.na + 1)]
        for column in self.input_columns:
            names.extend(f"b_{column}_{lag}" for lag in range(self.nb[column]))
        return names


@dataclass(frozen=True)
class RegressorMatrix:
    """A finite, leakage-free ARX design matrix plus the sample index of each row."""

    features: FloatArray
    targets: FloatArray
    time_indices: IntArray
    structure: ArxStructure

    @property
    def n_rows(self) -> int:
        return int(self.features.shape[0])

    @property
    def n_parameters(self) -> int:
        return int(self.features.shape[1])

    def take(self, positions: IntArray | Sequence[int]) -> RegressorMatrix:
        index = np.asarray(positions, dtype=int)
        return RegressorMatrix(
            features=self.features[index],
            targets=self.targets[index],
            time_indices=self.time_indices[index],
            structure=self.structure,
        )


def build_regressor(
    *,
    inputs: Mapping[str, FloatArray],
    output: FloatArray,
    structure: ArxStructure,
    start: int | None = None,
    stop: int | None = None,
) -> RegressorMatrix:
    """Build the ARX design matrix over ``[start, stop)`` of the sample axis.

    Rows whose regressor or target is not finite are dropped rather than imputed: the
    caller already decided how to clean the data, and silently inventing values here
    would corrupt both the information measure and the fit.
    """

    output_array = np.asarray(output, dtype=float)
    n_samples = int(output_array.shape[0])
    columns = structure.input_columns
    missing = [column for column in columns if column not in inputs]
    if missing:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "输入数据缺少 ARX 结构声明的变量",
            {"missing_columns": missing},
        )
    signals = {column: np.asarray(inputs[column], dtype=float) for column in columns}
    inconsistent = {
        column: int(signal.shape[0])
        for column, signal in signals.items()
        if signal.shape[0] != n_samples
    }
    if inconsistent:
        raise IdentifiabilityError(
            "INVALID_DATASET_SCHEMA",
            "输入变量与输出变量长度不一致",
            {"expected": n_samples, "actual": inconsistent},
        )

    first = structure.max_history if start is None else max(start, structure.max_history)
    last = n_samples if stop is None else min(stop, n_samples)
    if last <= first:
        raise IdentifiabilityError(
            "INSUFFICIENT_ROWS",
            "可用样本区间不足以构造 ARX 回归矩阵",
            {"start": first, "stop": last, "max_history": structure.max_history},
        )

    index = np.arange(first, last, dtype=int)
    blocks: list[FloatArray] = [
        -output_array[index - lag].reshape(-1, 1) for lag in range(1, structure.na + 1)
    ]
    for column in columns:
        signal = signals[column]
        delay = structure.nk[column]
        blocks.extend(
            signal[index - delay - lag].reshape(-1, 1) for lag in range(structure.nb[column])
        )
    features = np.hstack(blocks)
    targets = output_array[index]

    finite = np.isfinite(targets) & np.all(np.isfinite(features), axis=1)
    if not bool(np.any(finite)):
        raise IdentifiabilityError(
            "INSUFFICIENT_ROWS",
            "没有足够的有限值样本构造 ARX 回归矩阵",
            {"start": first, "stop": last},
        )
    return RegressorMatrix(
        features=features[finite],
        targets=targets[finite],
        time_indices=index[finite],
        structure=structure,
    )


def _expand_orders(
    value: Mapping[str, int] | int,
    columns: tuple[str, ...],
    *,
    name: str,
    minimum: int,
) -> dict[str, int]:
    if isinstance(value, int):
        orders = dict.fromkeys(columns, value)
    else:
        missing = sorted(set(columns) - set(value))
        if missing:
            raise IdentifiabilityError(
                "PARAMETER_OUT_OF_RANGE",
                f"{name} 必须覆盖全部输入变量",
                {"parameter": name, "missing": missing},
            )
        orders = {column: int(value[column]) for column in columns}
    invalid = {column: order for column, order in orders.items() if order < minimum}
    if invalid:
        raise IdentifiabilityError(
            "PARAMETER_OUT_OF_RANGE",
            f"{name} 包含低于下限的值",
            {"parameter": name, "minimum": minimum, "invalid": invalid},
        )
    return orders
