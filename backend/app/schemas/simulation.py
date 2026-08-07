from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema

SimulationScenario = Literal["S1", "S2", "S3", "S4", "S5"]


class SimulationGenerateRequest(Schema):
    scenario: SimulationScenario = Field(description="冻结的基准场景编号。")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    dataset_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="阶段 1 前端兼容字段；优先于 name。",
    )
    n_steps: int | None = Field(default=None, ge=100, le=1_000_000)
    num_samples: int | None = Field(
        default=None,
        ge=100,
        le=1_000_000,
        description="阶段 1 前端兼容字段；优先于 n_steps。",
    )
    sample_period_seconds: float = Field(default=1.0, gt=0)
    input_count: int = Field(default=2, ge=1, le=20)
    noise_sigma: float | None = Field(default=None, ge=0)
    noise_level: float | None = Field(
        default=None,
        ge=0,
        description="阶段 1 前端兼容字段；优先于 noise_sigma。",
    )
    anomaly_rate: float = Field(default=0.0, ge=0, le=0.5)
    missing_rate: float = Field(default=0.0, ge=0, le=0.5)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


class GroundTruthSegment(Schema):
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    start_idx: int = Field(ge=0)
    end_idx: int = Field(ge=0)
    segment_type: str
    snr_db: float | None = None


class SimulationGroundTruth(Schema):
    system_type: Literal["MISO_ARX"] = "MISO_ARX"
    true_na: int = Field(ge=1)
    true_nb: list[int]
    true_delays: list[int]
    true_delays_by_input: dict[str, int]
    true_parameters: dict[str, float]
    ar_coefficients: list[float]
    input_coefficients: dict[str, list[float]]
    dynamic_segments: list[GroundTruthSegment]
    anomaly_indices: dict[str, list[int]]
    missing_indices: dict[str, list[int]]
    freeze_segments: list[dict[str, int | str]]
    drift_segments: list[dict[str, int | str]]
    irregular_timestamp_indices: list[int]
    duplicate_timestamp_indices: list[int]
    redundant_variables: list[str]
    variable_dependencies: dict[str, str]
    noise_level: float = Field(ge=0)
    seed: int


class SimulationGenerateData(Schema):
    dataset_id: UUID
    dataset_name: str
    version_id: UUID
    scenario: SimulationScenario
    file_path: str = Field(description="受控的相对仿真产物标识，不是服务器绝对路径。")
    ground_truth_path: str = Field(description="受控的相对真值产物标识，不是服务器绝对路径。")
    num_rows: int = Field(ge=0)
    num_cols: int = Field(ge=0)
    columns: list[str]
    ground_truth: SimulationGroundTruth
