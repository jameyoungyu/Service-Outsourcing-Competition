from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import database_is_ready, get_session, redis_is_ready
from app.core.errors import AppError
from app.schemas.common import ErrorEnvelope, SuccessEnvelope
from app.schemas.copilot import (
    CopilotChatData,
    CopilotChatRequest,
    CopilotConfirmData,
    CopilotConfirmRequest,
    ExecutionPlan,
    ExecutionPlanStep,
)
from app.schemas.datasets import (
    DatasetConfigData,
    DatasetConfigRequest,
    DatasetDeleteData,
    DatasetDetail,
    DatasetListData,
    DatasetProfile,
    DatasetUploadData,
    DatasetVersionsData,
)
from app.schemas.modeling import (
    ArxFitData,
    ArxFitRequest,
)
from app.schemas.optimization import (
    OptimizationStartData,
    OptimizationStartRequest,
    OptimizationStatusData,
)
from app.schemas.preprocessing import (
    CleanData,
    CleanRequest,
    CollinearityData,
    CollinearityRequest,
    DelayData,
    DelayRequest,
    SegmentData,
    SegmentRequest,
)
from app.schemas.simulation import SimulationGenerateData, SimulationGenerateRequest
from app.schemas.system import LivenessData, ReadinessData, SystemInfoData
from app.schemas.tasks import CancelTaskData
from app.services.cleaning_service import CleaningDomainError, clean_dataset_version
from app.services.contract_stubs import completed_task, new_id, queued_task
from app.services.dataset_service import (
    DatasetDomainError,
    configure_dataset_columns,
    delete_dataset_asset,
    get_dataset_detail,
    list_dataset_summaries,
    upload_csv_dataset,
)
from app.services.dataset_service import (
    get_dataset_profile as get_dataset_profile_service,
)
from app.services.dataset_service import (
    get_dataset_versions as get_dataset_versions_service,
)
from app.services.identification_service import ArxDomainError
from app.services.identification_service import fit_arx as fit_arx_service
from app.services.segment_service import SegmentDomainError, select_dynamic_segments
from app.services.simulation_service import generate_simulation as generate_simulation_service

router = APIRouter()
DataT = TypeVar("DataT")
DatasetId = Annotated[UUID, Path(description="数据集 UUID。")]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope, "description": "请求参数或领域规则无效。"},
    404: {"model": ErrorEnvelope, "description": "目标资源不存在。"},
    422: {"model": ErrorEnvelope, "description": "请求体或路径参数未通过 Pydantic 校验。"},
    500: {"model": ErrorEnvelope, "description": "未预期的服务端错误。"},
}


def success(request: Request, data: DataT) -> SuccessEnvelope[DataT]:
    """Return the only success envelope used by every v1 endpoint."""

    return SuccessEnvelope(data=data, request_id=UUID(request.state.request_id))


@router.get(
    "/health/live",
    tags=["System"],
    summary="Liveness probe",
    response_model=SuccessEnvelope[LivenessData],
    responses=ERROR_RESPONSES,
)
async def health_live(request: Request) -> SuccessEnvelope[LivenessData]:
    return success(request, LivenessData())


@router.get(
    "/health/ready",
    tags=["System"],
    summary="Readiness probe for PostgreSQL and Redis",
    response_model=SuccessEnvelope[ReadinessData],
    responses={
        **ERROR_RESPONSES,
        503: {"model": ErrorEnvelope, "description": "PostgreSQL 或 Redis 尚不可用。"},
    },
)
async def health_ready(request: Request) -> SuccessEnvelope[ReadinessData]:
    database_ready, redis_ready = await database_is_ready(), await redis_is_ready()
    if not database_ready or not redis_ready:
        raise AppError(
            "SYSTEM_NOT_READY",
            "系统依赖尚未就绪",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"database": database_ready, "redis": redis_ready},
        )
    return success(request, ReadinessData())


@router.get(
    "/system/info",
    tags=["System"],
    summary="Get service and contract metadata",
    response_model=SuccessEnvelope[SystemInfoData],
    responses=ERROR_RESPONSES,
)
async def system_info(request: Request) -> SuccessEnvelope[SystemInfoData]:
    settings = get_settings()
    return success(
        request,
        SystemInfoData(version=settings.app_version, environment=settings.app_env),
    )


@router.post(
    "/simulation/generate",
    tags=["Simulation"],
    summary="Generate an S1-S5 benchmark dataset",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessEnvelope[SimulationGenerateData],
    responses=ERROR_RESPONSES,
)
async def generate_simulation(
    request: Request, payload: SimulationGenerateRequest
) -> SuccessEnvelope[SimulationGenerateData]:
    generated = generate_simulation_service(payload, artifact_root=get_settings().artifact_root)
    return success(request, generated)


@router.post(
    "/datasets/upload",
    tags=["Datasets"],
    summary="Upload a CSV dataset for asynchronous parsing",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[DatasetUploadData],
    responses={**ERROR_RESPONSES, 413: {"model": ErrorEnvelope, "description": "文件超过限制。"}},
)
async def upload_dataset(
    request: Request,
    file: Annotated[UploadFile, File(description="CSV 文件。")],
    session: Annotated[AsyncSession, Depends(get_session)],
    name: Annotated[str | None, Form(max_length=120)] = None,
) -> SuccessEnvelope[DatasetUploadData]:
    """Synchronously validate a CSV while retaining the phase-1 async response envelope."""

    try:
        uploaded = await upload_csv_dataset(
            session,
            upload=file,
            display_name=name,
            artifact_root=get_settings().artifact_root,
        )
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=413 if error.code == "DATASET_FILE_TOO_LARGE" else error.status_code,
            details=error.details,
        ) from error
    return success(
        request,
        DatasetUploadData(
            dataset=uploaded.summary,
            parse_task=completed_task(
                stage="parse_upload",
                message="CSV 已完成校验、持久化和质量画像计算。",
            ),
            deduplicated=uploaded.deduplicated,
        ),
    )


@router.get(
    "/datasets",
    tags=["Datasets"],
    summary="List datasets",
    response_model=SuccessEnvelope[DatasetListData],
    responses=ERROR_RESPONSES,
)
async def list_datasets(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessEnvelope[DatasetListData]:
    return success(request, await list_dataset_summaries(session, page=page, page_size=page_size))


@router.post(
    "/datasets/{dataset_id}/config",
    tags=["Datasets"],
    summary="Confirm time/input/output column roles and recompute the profile",
    response_model=SuccessEnvelope[DatasetConfigData],
    responses=ERROR_RESPONSES,
)
async def configure_dataset(
    request: Request,
    dataset_id: DatasetId,
    payload: DatasetConfigRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[DatasetConfigData]:
    try:
        data = await configure_dataset_columns(
            session,
            dataset_id=dataset_id,
            payload=payload,
            artifact_root=get_settings().artifact_root,
        )
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.get(
    "/datasets/{dataset_id}",
    tags=["Datasets"],
    summary="Get a dataset and its parsed column metadata",
    response_model=SuccessEnvelope[DatasetDetail],
    responses=ERROR_RESPONSES,
)
async def get_dataset(
    request: Request,
    dataset_id: DatasetId,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[DatasetDetail]:
    try:
        data = await get_dataset_detail(
            session,
            dataset_id=dataset_id,
            artifact_root=get_settings().artifact_root,
        )
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.delete(
    "/datasets/{dataset_id}",
    tags=["Datasets"],
    summary="Cascade-delete a dataset's database records",
    response_model=SuccessEnvelope[DatasetDeleteData],
    responses=ERROR_RESPONSES,
)
async def delete_dataset(
    request: Request,
    dataset_id: DatasetId,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[DatasetDeleteData]:
    try:
        await delete_dataset_asset(session, dataset_id=dataset_id)
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, DatasetDeleteData(dataset_id=dataset_id))


@router.get(
    "/datasets/{dataset_id}/profile",
    tags=["Datasets"],
    summary="Get the quality profile for the active dataset version",
    response_model=SuccessEnvelope[DatasetProfile],
    responses=ERROR_RESPONSES,
)
async def get_dataset_profile(
    request: Request,
    dataset_id: DatasetId,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[DatasetProfile]:
    try:
        data = await get_dataset_profile_service(session, dataset_id=dataset_id)
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.get(
    "/datasets/{dataset_id}/versions",
    tags=["Datasets"],
    summary="Get the immutable data-version lineage DAG",
    response_model=SuccessEnvelope[DatasetVersionsData],
    responses=ERROR_RESPONSES,
)
async def get_dataset_versions(
    request: Request,
    dataset_id: DatasetId,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[DatasetVersionsData]:
    try:
        data = await get_dataset_versions_service(session, dataset_id=dataset_id)
    except DatasetDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.post(
    "/preprocessing/clean",
    tags=["Preprocessing"],
    summary="Queue time alignment, interpolation and anomaly cleaning",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[CleanData],
    responses=ERROR_RESPONSES,
)
async def clean_data(
    request: Request,
    payload: CleanRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[CleanData]:
    """Run the real cleaning pipeline and register an immutable derived version."""

    try:
        data = await clean_dataset_version(
            session,
            payload=payload,
            artifact_root=get_settings().artifact_root,
        )
    except CleaningDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.post(
    "/preprocessing/segment",
    tags=["Preprocessing"],
    summary="Queue dynamic-response segment identification",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[SegmentData],
    responses=ERROR_RESPONSES,
)
async def segment_data(
    request: Request,
    payload: SegmentRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SuccessEnvelope[SegmentData]:
    """Gate candidate windows on quality, then select by D-optimal information gain."""

    try:
        data = await select_dynamic_segments(
            session,
            payload=payload,
            artifact_root=get_settings().artifact_root,
        )
    except SegmentDomainError as error:
        raise AppError(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        ) from error
    return success(request, data)


@router.post(
    "/preprocessing/delay",
    tags=["Preprocessing"],
    summary="Queue multi-variable lag-correlation analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[DelayData],
    responses=ERROR_RESPONSES,
)
async def estimate_delay(request: Request, payload: DelayRequest) -> SuccessEnvelope[DelayData]:
    return success(
        request,
        DelayData(
            source_version_id=payload.version_id,
            task=queued_task(stage="estimate_delays"),
            delays=[],
            correlations={column: [] for column in payload.input_columns},
            best_delays={},
            candidate_peaks={},
        ),
    )


@router.post(
    "/preprocessing/collinearity",
    tags=["Preprocessing"],
    summary="Queue Pearson and VIF collinearity diagnostics",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[CollinearityData],
    responses=ERROR_RESPONSES,
)
async def analyze_collinearity(
    request: Request, payload: CollinearityRequest
) -> SuccessEnvelope[CollinearityData]:
    return success(
        request,
        CollinearityData(
            source_version_id=payload.version_id,
            task=queued_task(stage="analyze_collinearity"),
            variables=payload.input_columns,
            matrix=[],
            vif_scores={},
            condition_number=None,
            recommendations=[],
        ),
    )


@router.post(
    "/modeling/arx/fit",
    tags=["Modeling"],
    summary="Run MISO ARX identification and chronological partitioned evaluation",
    response_model=SuccessEnvelope[ArxFitData],
    responses=ERROR_RESPONSES,
)
async def fit_arx(request: Request, payload: ArxFitRequest) -> SuccessEnvelope[ArxFitData]:
    try:
        result = fit_arx_service(payload, artifact_root=get_settings().artifact_root)
    except ArxDomainError as error:
        status_code = 404 if error.code in {"DATASET_VERSION_NOT_FOUND"} else 400
        raise AppError(
            error.code,
            error.message,
            status_code=status_code,
            details=error.details,
        ) from error
    return success(
        request,
        ArxFitData(
            model_id=result.model_id,
            task=completed_task(stage="fit_arx", message="ARX 基线辨识与多分区评价已完成。"),
            estimator=result.estimator,
            dataset_id=result.dataset_id,
            version_id=result.version_id,
            coefficients=result.coefficients,
            a_coefficients=result.a_coefficients,
            b_coefficients=result.b_coefficients,
            metrics=result.metrics,
            plot_data=result.plot_data,
            residual_diagnostics=result.residual_diagnostics,
            artifact_uri=result.artifact_uri,
        ),
    )


@router.post(
    "/optimization/optuna/start",
    tags=["Optimization"],
    summary="Start a cancellable Optuna pipeline-optimization study",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessEnvelope[OptimizationStartData],
    responses=ERROR_RESPONSES,
)
async def start_optimization(
    request: Request, payload: OptimizationStartRequest
) -> SuccessEnvelope[OptimizationStartData]:
    return success(
        request,
        OptimizationStartData(study_id=new_id(), task=queued_task(stage="optimize_pipeline")),
    )


@router.get(
    "/optimization/optuna/{study_id}/status",
    tags=["Optimization"],
    summary="Get Optuna trial progress, convergence curve and parameter importance",
    response_model=SuccessEnvelope[OptimizationStatusData],
    responses=ERROR_RESPONSES,
)
async def optimization_status(
    request: Request, study_id: Annotated[UUID, Path(description="Optuna study UUID。")]
) -> SuccessEnvelope[OptimizationStatusData]:
    return success(
        request,
        OptimizationStatusData(
            study_id=study_id,
            task=queued_task(stage="optimize_pipeline"),
            trials=[],
            best_trial_id=None,
            best_value=None,
            best_curve=[],
            param_importances={},
        ),
    )


@router.post(
    "/tasks/{task_id}/cancel",
    tags=["Tasks"],
    summary="Request cooperative cancellation of an asynchronous task",
    response_model=SuccessEnvelope[CancelTaskData],
    responses=ERROR_RESPONSES,
)
async def cancel_task(
    request: Request, task_id: Annotated[UUID, Path(description="后台任务 UUID。")]
) -> SuccessEnvelope[CancelTaskData]:
    return success(
        request,
        CancelTaskData(task_id=task_id, task=queued_task(status="cancelled", stage="cancelled")),
    )


@router.post(
    "/copilot/chat",
    tags=["Copilot"],
    summary="Create a validated, whitelisted copilot execution-plan DAG",
    response_model=SuccessEnvelope[CopilotChatData],
    responses=ERROR_RESPONSES,
)
async def copilot_chat(
    request: Request, payload: CopilotChatRequest
) -> SuccessEnvelope[CopilotChatData]:
    plan = ExecutionPlan(
        goal=payload.message,
        dataset_id=payload.dataset_id,
        steps=[
            ExecutionPlanStep(
                step_id="profile",
                tool="profile_dataset",
                depends_on=[],
                requires_confirmation=False,
            )
        ],
        assumptions=["阶段 1 返回经白名单校验的计划骨架，不会执行算法。"],
    )
    return success(request, CopilotChatData(copilot_run_id=new_id(), plan=plan, task=None))


@router.post(
    "/copilot/confirm",
    tags=["Copilot"],
    summary="Record a human-in-the-loop approval or rejection",
    response_model=SuccessEnvelope[CopilotConfirmData],
    responses=ERROR_RESPONSES,
)
async def copilot_confirm(
    request: Request, payload: CopilotConfirmRequest
) -> SuccessEnvelope[CopilotConfirmData]:
    return success(
        request,
        CopilotConfirmData(
            copilot_run_id=payload.copilot_run_id,
            confirmation_id=payload.confirmation_id,
            decision="approved" if payload.approved else "rejected",
            task=(
                queued_task(status="queued", stage="await_execution") if payload.approved else None
            ),
        ),
    )
