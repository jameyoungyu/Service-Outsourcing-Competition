from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource


class CleanRequest(Schema):
    version_id: UUID
    dataset_id: UUID | None = None
    target_sample_period_seconds: float | None = Field(default=None, gt=0)
    # Canonical phase-1 names stay available. The aliases below preserve the
    # already-built browser client while it is upgraded in the next handoff.
    resample_period_s: float | None = Field(default=None, gt=0)
    interpolation: Literal["linear", "forward_fill", "backward_fill", "none"] = "linear"
    interpolation_method: (
        Literal["linear", "ffill", "bfill", "forward_fill", "backward_fill", "none"] | None
    ) = None
    anomaly_detector: Literal["iqr", "z_score", "hampel"] = "hampel"
    outlier_method: Literal["iqr", "zscore", "z_score", "hampel"] | None = None
    anomaly_strategy: Literal["keep", "set_null", "local_median", "linear_interpolate", "clip"] = (
        "linear_interpolate"
    )
    hampel_window: int = Field(default=7, ge=3, le=1_001)
    hampel_threshold: float = Field(default=3.0, gt=0)
    hampel_n_sigmas: float | None = Field(default=None, gt=0)
    z_score_threshold: float = Field(default=3.0, gt=0)
    max_consecutive_missing: int | None = Field(default=10, ge=1, le=100_000)
    duplicate_strategy: Literal["first", "mean"] = "mean"
    smoothing: Literal["none", "moving_average", "savitzky_golay"] = "none"
    smoothing_window: int = Field(default=5, ge=3, le=1_001)


class CleanSeries(Schema):
    column: str
    timestamps: list[datetime]
    raw_series: list[float | None]
    cleaned_series: list[float | None]
    replaced_indices: list[int] = Field(default_factory=list)


class CleanData(Schema):
    source_version_id: UUID
    derived_version_id: UUID
    task: TaskResource
    series: list[CleanSeries]
    # Additive browser-friendly projection. It describes the configured output
    # column (or the first numeric column when no output role exists).
    dataset_id: UUID | None = None
    new_version_id: UUID | None = None
    raw_series: list[float | None] = Field(default_factory=list)
    cleaned_series: list[float | None] = Field(default_factory=list)
    replaced_indices: list[int] = Field(default_factory=list)
    total_cleaned_points: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    recommended_downsample_factor: int = Field(default=1, ge=1)


class SegmentRequest(Schema):
    version_id: UUID
    input_columns: list[str] = Field(min_length=1)
    output_column: str = Field(min_length=1)
    window_size: int = Field(default=60, ge=5)
    min_segment_length: int = Field(default=100, ge=1)
    min_snr_db: float = 0.0
    max_segments: int = Field(default=10, ge=1, le=100)


class DynamicSegment(Schema):
    segment_id: str
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    snr_db: float
    dynamic_score: float
    recommendation: Literal["strongly_recommended", "recommended", "review", "rejected"]


class SegmentData(Schema):
    source_version_id: UUID
    task: TaskResource
    timestamps: list[datetime]
    series: dict[str, list[float | None]]
    segments: list[DynamicSegment]


class DelayRequest(Schema):
    version_id: UUID
    input_columns: list[str] = Field(min_length=1)
    output_column: str = Field(min_length=1)
    max_lag: int = Field(default=100, ge=0, le=10_000)
    top_k: int = Field(default=3, ge=1, le=20)


class DelayPeak(Schema):
    lag: int = Field(ge=0)
    correlation: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)


class DelayData(Schema):
    source_version_id: UUID
    task: TaskResource
    delays: list[int]
    correlations: dict[str, list[float]]
    best_delays: dict[str, int]
    candidate_peaks: dict[str, list[DelayPeak]]


class CollinearityRequest(Schema):
    version_id: UUID
    input_columns: list[str] = Field(min_length=2)
    correlation_threshold: float = Field(default=0.9, gt=0, le=1)
    vif_threshold: float = Field(default=10.0, gt=1)


class VariableRecommendation(Schema):
    variable: str
    action: Literal["keep", "drop", "merge", "review"]
    reason: str
    related_variables: list[str] = Field(default_factory=list)


class CollinearityData(Schema):
    source_version_id: UUID
    task: TaskResource
    variables: list[str]
    matrix: list[list[float]]
    vif_scores: dict[str, float]
    condition_number: float | None = None
    recommendations: list[VariableRecommendation]
