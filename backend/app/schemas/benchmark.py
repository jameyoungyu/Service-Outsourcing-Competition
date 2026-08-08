"""Schemas for the in-product self-benchmark."""

from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource
from app.schemas.simulation import SimulationScenario


class BenchmarkRequest(Schema):
    scenarios: list[SimulationScenario] = Field(
        default=["S3", "S6"],
        min_length=1,
        max_length=6,
        description="要运行的基准场景；S6 为异构激励压力测试。",
    )
    n_samples: int = Field(default=4000, ge=500, le=50_000)
    seed: int = Field(default=20260807, ge=0, le=2_147_483_647)
    window_size: int = Field(default=60, ge=10, le=1_000)
    budget_windows: int = Field(default=12, ge=1, le=100)


class BenchmarkRow(Schema):
    """One measured cell of an ablation table."""

    scenario: str
    strategy: str
    metrics: dict[str, float]


class BenchmarkExperiment(Schema):
    """One ablation: the question it answers and the numbers that answer it."""

    key: str
    title: str
    question: str
    rows: list[BenchmarkRow]
    notes: list[str] = Field(default_factory=list)


class BenchmarkData(Schema):
    benchmark_id: UUID
    task: TaskResource
    scenarios: list[str]
    n_samples: int
    seed: int
    experiments: list[BenchmarkExperiment]
    duration_ms: float
