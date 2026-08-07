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

    def resolved_estimator(self) -> Literal["ols", "ridge"]:
        return self.estimation_method or self.estimator


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
