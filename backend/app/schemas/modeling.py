from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource


class ArxFitRequest(Schema):
    version_id: UUID
    dataset_id: UUID | None = None
    input_columns: list[str] = Field(default_factory=list)
    output_column: str = "y"
    na: int = Field(ge=1, le=100)
    nb: dict[str, int] | list[int] = Field(
        description="每个输入变量的 b 阶次；允许阶段 1 前端使用的同序数组。"
    )
    delays: dict[str, int] | list[int] = Field(
        description="每个输入变量的 nk；允许阶段 1 前端使用的同序数组。"
    )
    estimator: Literal["ols", "ridge"] = "ols"
    estimation_method: Literal["ols", "ridge"] | None = Field(
        default=None,
        description="阶段 1 前端兼容字段；优先于 estimator。",
    )
    ridge_alpha: float | None = Field(default=None, ge=0)
    train_ratio: float = Field(default=0.6, gt=0, lt=1)
    validation_ratio: float = Field(default=0.2, gt=0, lt=1)
    # Restrict the training rows to specific sample indices, e.g. the output of
    # quality-constrained D-optimal selection. Empty means "use every training row".
    training_sample_indices: list[int] = Field(default_factory=list)
    # Engineering priors. A model that violates them is rejected rather than reported,
    # because a gain with the wrong sign is not a slightly worse model, it is a wrong one.
    gain_sign: dict[str, Literal["positive", "negative"]] = Field(default_factory=dict)
    gain_bounds: dict[str, tuple[float, float]] = Field(default_factory=dict)
    require_stable: bool = False

    def resolved_estimator(self) -> Literal["ols", "ridge"]:
        return self.estimation_method or self.estimator


class PriorViolation(Schema):
    """One engineering prior the identified model failed."""

    variable: str
    kind: Literal["gain_sign", "gain_bounds", "stability"]
    expected: str
    actual: float | None = None


class ModelValidationData(Schema):
    """Control-relevant acceptance evidence.

    ``free_run_fit`` is the primary metric: an APC controller predicts many steps ahead,
    so one-step FIT — which is fed the measured previous output — flatters any model on an
    autocorrelated process. ``one_step_fit`` is kept as a diagnostic, and a large
    ``fit_gap`` is itself the signal that the model is coasting on persistence.
    """

    one_step_fit: float | None = None
    free_run_fit: float | None = None
    free_run_rmse: float | None = None
    fit_gap: float | None = None
    stable: bool = True
    max_pole_modulus: float | None = None
    steady_state_gains: dict[str, float] = Field(default_factory=dict)
    residual_whiteness_ratio: float | None = None
    n_samples: int = Field(default=0, ge=0)
    partition: str = "validation"
    excitation_shortfall: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description=(
            "持续激励阶次低于 na+nb 的通道及其实际/所需阶次。"
            "这是诊断而非阻断：实测该判据无法区分可用与不可用的数据（见 ALG-0.2 §3）。"
        ),
    )


class ArxMetrics(Schema):
    train_r2: float | None = None
    train_fit: float | None = None
    train_rmse: float | None = None
    val_r2: float | None = None
    val_fit: float | None = None
    val_rmse: float | None = None
    test_r2: float | None = None
    test_fit: float | None = None
    test_rmse: float | None = None
    rmse: float | None = None
    mae: float | None = None
    nrmse: float | None = None
    # Free-run (infinite-step) simulation FIT per partition — the primary metric.
    train_free_run_fit: float | None = None
    val_free_run_fit: float | None = None
    test_free_run_fit: float | None = None
    aic: float | None = None
    bic: float | None = None


class SplitIndices(Schema):
    train_end: int = Field(ge=0)
    val_end: int = Field(ge=0)
    test_end: int = Field(ge=0)


class ArxPlotData(Schema):
    indices: list[int]
    y_true: list[float]
    y_pred: list[float]
    residuals: list[float]
    splits: SplitIndices
    split_indices: SplitIndices | None = None


class ArxResidualDiagnostics(Schema):
    acf_values: list[float]
    confidence_interval: float | None = None


class ArxFitData(Schema):
    model_id: UUID
    task: TaskResource
    estimator: Literal["ols", "ridge"]
    dataset_id: UUID | None = None
    version_id: UUID | None = None
    coefficients: dict[str, float]
    a_coefficients: list[float] = Field(default_factory=list)
    b_coefficients: dict[str, list[float]] = Field(default_factory=dict)
    metrics: ArxMetrics
    plot_data: ArxPlotData
    residual_diagnostics: ArxResidualDiagnostics
    artifact_uri: str | None = None
    validation: ModelValidationData | None = None
    prior_violations: list[PriorViolation] = Field(default_factory=list)
    training_rows: int = Field(default=0, ge=0)
    free_run_series: list[float] = Field(default_factory=list)
