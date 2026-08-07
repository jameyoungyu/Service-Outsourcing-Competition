from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(Schema):
    code: str = Field(examples=["DATASET_NOT_FOUND"])
    message: str = Field(examples=["数据集不存在"])
    details: dict[str, Any] = Field(default_factory=dict)


class SuccessEnvelope(Schema, Generic[DataT]):
    success: Literal[True] = True
    data: DataT
    error: None = None
    request_id: UUID


class ErrorEnvelope(Schema):
    success: Literal[False] = False
    data: None = None
    error: ErrorDetail
    request_id: UUID


TaskState = Literal[
    "queued",
    "running",
    "waiting_confirmation",
    "succeeded",
    "partial_success",
    "failed",
    "cancelled",
]


class TaskProgress(Schema):
    current: int = Field(ge=0, examples=[2])
    total: int = Field(ge=0, examples=[8])
    percent: float = Field(ge=0, le=100, examples=[25])
    stage: str = Field(examples=["detect_dynamic_segments"])
    message: str = Field(examples=["正在计算窗口质量分数"])


class TaskResource(Schema):
    id: UUID
    status: TaskState
    progress: TaskProgress
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorDetail | None = None


class PageInfo(Schema):
    page: int = Field(ge=1, default=1)
    page_size: int = Field(ge=1, le=100, default=20)
    total: int = Field(ge=0, default=0)


class PaginationParams(Schema):
    page: int = Field(ge=1, default=1)
    page_size: int = Field(ge=1, le=100, default=20)
