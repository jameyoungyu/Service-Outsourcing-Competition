"""Background job submission for the long-running closed-loop search.

A 120-trial study takes minutes. Running it inside the HTTP handler holds a connection open
for the whole time, and any proxy in front of the API will eventually cut it. So the study
can be handed to an RQ worker instead, and the caller gets a study id it can poll.

**Redis being unavailable is not an error here.** The venue may have no Redis, and the same
reasoning that keeps the system working without an LLM applies: the queue is an
optimisation, not a dependency. When it cannot be reached the caller is told so and the
study runs inline, which is exactly what happened before this module existed. What must
never happen is a request that reports success while the work was silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import get_settings

QUEUE_NAME = "indusopt"
# Studies are minutes, not seconds. The default RQ timeout of 180s would kill a legitimate
# 120-trial search partway through and leave the study row stuck at "running".
JOB_TIMEOUT_SECONDS = 3600
RESULT_TTL_SECONDS = 86_400


@dataclass(frozen=True)
class Submission:
    """What happened to a job request, in terms the caller can report honestly."""

    queued: bool
    job_id: str | None
    reason: str | None

    def to_payload(self) -> dict[str, Any]:
        return {"queued": self.queued, "job_id": self.job_id, "reason": self.reason}


def submit_optimization(study_id: UUID, payload: dict[str, Any]) -> Submission:
    """Try to enqueue the study. Returns why not, rather than raising, on any failure.

    The import of ``rq`` is local so that a deployment without the worker extras still
    imports this module cleanly; the caller falls back to inline execution either way.
    """

    settings = get_settings()
    if not settings.background_optimization:
        return Submission(
            queued=False, job_id=None, reason="后台执行未启用（INDUSOPT_BACKGROUND_OPTIMIZATION）"
        )

    try:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(settings.redis_url)
        connection.ping()
        queue = Queue(
            QUEUE_NAME,
            connection=connection,
            default_timeout=JOB_TIMEOUT_SECONDS,
        )
        job = queue.enqueue(
            "app.worker.run_optimization_job",
            str(study_id),
            payload,
            job_timeout=JOB_TIMEOUT_SECONDS,
            result_ttl=RESULT_TTL_SECONDS,
        )
    except Exception as error:  # noqa: BLE001 - any queue failure means "run it here"
        # Deliberately broad: a missing package, a refused connection and a misconfigured
        # URL all have the same correct response, and none of them should fail the request.
        return Submission(queued=False, job_id=None, reason=f"队列不可用（{type(error).__name__}）")

    return Submission(queued=True, job_id=job.id, reason=None)
