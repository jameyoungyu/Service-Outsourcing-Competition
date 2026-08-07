from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class LivenessData(Schema):
    status: Literal["ok"] = "ok"
    service: str = "indusopt-backend"


class ReadinessData(Schema):
    status: Literal["ready"] = "ready"
    database: Literal["connected"] = "connected"
    queue: Literal["connected"] = "connected"


class SystemInfoData(Schema):
    service: str = "indusopt-backend"
    version: str
    environment: str
    api_version: str = "v1"
    database_driver: str = "SQLAlchemy Async"
    queue_backend: str = "Redis + RQ"
    algorithm_contract_version: str = Field(default="ALG-0.1")
