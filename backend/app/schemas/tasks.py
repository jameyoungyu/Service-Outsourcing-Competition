from uuid import UUID

from app.schemas.common import Schema, TaskResource


class CancelTaskData(Schema):
    task_id: UUID
    task: TaskResource
