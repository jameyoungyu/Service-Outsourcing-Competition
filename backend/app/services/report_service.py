"""Report assembly and optimised-dataset export (phase 10).

The report is composed from persisted ``ProcessingRun`` records, never from values held in
memory by whoever is generating it. Every figure enters through a placeholder that names the
run it came from, so the document is a view over the audit trail rather than a retelling of
it. :mod:`algorithms.report.provenance` enforces that: a draft containing a bare numeral is
rejected before rendering.

Export writes the rows the closed loop actually selected, plus a manifest recording which
runs produced the selection, so the delivered CSV can be traced back to the decisions that
shaped it.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from algorithms.report.provenance import RenderResult, render_template, validate_draft
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import ProcessingRun
from app.models.operation_log import OperationLog
from app.models.optimization import OptimizationStudy
from app.schemas.reporting import (
    ExportDatasetData,
    ExportDatasetRequest,
    ReportBinding,
    ReportData,
    ReportRequest,
    ReportSection,
)
from app.services.contract_stubs import completed_task
from app.services.version_data import VersionDataError, load_version_series

# Reports cite recent work, not the whole history; this bounds the scan below.
RUN_SCAN_LIMIT = 500


class ReportDomainError(Exception):
    """A client-safe reporting failure for the standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class RunIndex:
    """Persisted runs keyed by short id, as the placeholder resolver sees them."""

    records: dict[str, dict[str, Any]]
    by_type: dict[str, str]

    def latest(self, run_type: str) -> str | None:
        return self.by_type.get(run_type)


async def build_run_index(
    session: AsyncSession,
    *,
    dataset_id: UUID | None,
    version_id: UUID | None,
) -> RunIndex:
    """Load the runs a report may cite, newest first per type."""

    statement = (
        select(ProcessingRun).order_by(ProcessingRun.created_at.desc()).limit(RUN_SCAN_LIMIT)
    )
    runs = list((await session.scalars(statement)).all())
    runs = [run for run in runs if _matches(run, dataset_id=dataset_id, version_id=version_id)]

    records: dict[str, dict[str, Any]] = {}
    by_type: dict[str, str] = {}
    for run in runs:
        short = _short_id(run.id)
        records[short] = {
            "run_id": str(run.id),
            "run_type": run.run_type,
            "status": run.status,
            "parameters": dict(run.parameters or {}),
            "created_at": run.created_at.isoformat() if run.created_at else "",
            **(run.result or {}),
        }
        by_type.setdefault(run.run_type, short)
    return RunIndex(records=records, by_type=by_type)


async def generate_report(
    session: AsyncSession,
    *,
    payload: ReportRequest,
    artifact_root: Path,
) -> ReportData:
    """Compose, validate and render a provenance-bound report."""

    index = await build_run_index(
        session, dataset_id=payload.dataset_id, version_id=payload.version_id
    )
    if not index.records:
        raise ReportDomainError(
            "REPORT_NO_RUNS",
            "该数据集尚无可引用的处理运行记录，无法生成报告。",
            status_code=404,
        )

    study = None
    if payload.study_id is not None:
        study = await session.get(OptimizationStudy, payload.study_id)
        if study is None:
            raise ReportDomainError(
                "OPTIMIZATION_STUDY_NOT_FOUND", "寻优任务不存在。", status_code=404
            )
        index.records["study"] = {
            "best_value": study.best_value,
            "best_params": dict(study.best_params or {}),
            "statistics": dict(study.statistics or {}),
            "objective": study.objective,
        }

    sections = _compose(index, payload)
    template = "\n\n".join(f"## {section.title}\n\n{section.body}" for section in sections)

    # The draft must contain no bare numerals. This is checked even though the composer is
    # ours, because the same path serves LLM-authored drafts and must not be weaker there.
    violations = validate_draft(template)
    if violations:
        raise ReportDomainError(
            "REPORT_CONTAINS_UNBOUND_NUMERAL",
            "报告草稿包含未溯源的数字字面量，已拒绝渲染。",
            details={"violations": [violation.to_payload() for violation in violations[:20]]},
        )

    rendered = render_template(template, runs=index.records)
    report_id = uuid4()
    artifact_uri = _write_report(
        artifact_root,
        report_id=report_id,
        rendered=rendered,
        payload=payload,
        index=index,
    )
    await _persist(session, report_id=report_id, payload=payload, rendered=rendered)

    return ReportData(
        report_id=report_id,
        dataset_id=payload.dataset_id,
        task=completed_task(stage="generate_report", message="图文报告已生成，全部数值均已溯源。"),
        title=payload.title,
        markdown=rendered.text,
        sections=sections,
        bindings=[ReportBinding(**binding.to_payload()) for binding in rendered.bindings],
        unresolved=list(rendered.unresolved),
        fully_resolved=rendered.fully_resolved,
        artifact_uri=artifact_uri,
        cited_runs=sorted(index.records),
    )


def _compose(index: RunIndex, payload: ReportRequest) -> list[ReportSection]:
    """Build the section bodies. Numbers appear only as placeholders."""

    sections: list[ReportSection] = []

    profile = index.latest("preprocessing.segment")
    clean = index.latest("preprocessing.clean")
    delay = index.latest("preprocessing.delay")
    collinearity = index.latest("preprocessing.collinearity")
    modeling = index.latest("modeling.arx")
    agent = index.latest("agent.copilot")

    sections.append(
        ReportSection(
            key="overview",
            title="一、分析概述",
            body=(
                f"本报告由 IndusOpt 自动生成，引用了 {{{{run:{next(iter(index.records))}.run_type}}}} "
                "等处理运行记录。报告中的每一个数值均通过占位符从运行数据库解析，"
                "不经过任何自然语言改写环节。"
            ),
        )
    )

    if clean:
        sections.append(
            ReportSection(
                key="cleaning",
                title="二、数据清洗与规整",
                body=(
                    f"清洗共修改数据点 {{{{run:{clean}.total_cleaned_points}}}} 个，"
                    f"检出冻结段 {{{{run:{clean}.frozen_segment_count}}}} 个，"
                    f"派生版本 {{{{run:{clean}.derived_version_id}}}}。"
                ),
            )
        )

    if profile:
        sections.append(
            ReportSection(
                key="selection",
                title="三、质量门控与 D-最优数据优选",
                body=(
                    f"候选窗口 {{{{run:{profile}.selection.candidate_count}}}} 个，"
                    f"通过质量门控 {{{{run:{profile}.selection.gated_count}}}} 个，"
                    f"最终选中 {{{{run:{profile}.selection.selected_count}}}} 个区间，"
                    f"采样占比 {{{{run:{profile}.selection.coverage_ratio}}}}。"
                    f"选中子集的设计矩阵条件数为 "
                    f"{{{{run:{profile}.selection.condition_number}}}}，"
                    f"持续激励条件满足情况："
                    f"{{{{run:{profile}.selection.excitation_satisfied}}}}。"
                    "\n\n先执行质量门控再做信息增益优选，是因为尖峰扰动在 log det 意义上"
                    "恰恰是“高信息量”的；不先剔除，信息准则会优先选中工程师本应丢弃的数据。"
                ),
            )
        )

    if delay:
        sections.append(
            ReportSection(
                key="delay",
                title="四、时滞估计",
                body=(
                    f"预白化互相关生成候选后，由验证集自由仿真 FIT 复核，"
                    f"最终时滞为 {{{{run:{delay}.refined_delays}}}}，"
                    f"复核时验证集自由仿真 FIT 为 {{{{run:{delay}.validation_fit}}}}。"
                ),
            )
        )

    if collinearity:
        sections.append(
            ReportSection(
                key="collinearity",
                title="五、共线性诊断",
                body=(
                    f"设计矩阵条件数 {{{{run:{collinearity}.condition_number}}}}，"
                    f"检出高相关变量组 {{{{run:{collinearity}.groups}}}}。"
                    "剔除建议为咨询性质，需人工确认后方可生效。"
                ),
            )
        )

    if modeling:
        sections.append(
            ReportSection(
                key="model",
                title="六、模型辨识与评价",
                body=(
                    f"验证集自由仿真 FIT 为 "
                    f"{{{{run:{modeling}.validation.free_run_fit}}}}，"
                    f"一步预测 FIT 为 {{{{run:{modeling}.validation.one_step_fit}}}}，"
                    f"两者差值 {{{{run:{modeling}.validation.fit_gap}}}}。"
                    f"模型稳定性：{{{{run:{modeling}.validation.stable}}}}，"
                    f"最大极点模 {{{{run:{modeling}.validation.max_pole_modulus}}}}，"
                    f"残差白度 {{{{run:{modeling}.validation.residual_whiteness_ratio}}}}，"
                    f"训练样本数 {{{{run:{modeling}.training_rows}}}}。"
                    "\n\n以自由仿真 FIT 作为主指标，是因为 APC 在预测时域内做多步预测；"
                    "一步预测会把实测上一时刻喂回模型，在强自相关过程上对劣质模型同样给出高分。"
                ),
            )
        )

    if "study" in index.records:
        sections.append(
            ReportSection(
                key="optimization",
                title="七、闭环寻优",
                body=(
                    "寻优目标为 {{run:study.objective}}，"
                    "最优目标值 {{run:study.best_value}}，"
                    "最优参数组合 {{run:study.best_params}}。"
                    "共完成有效试验 {{run:study.statistics.completed_trials}} 个，"
                    "剪枝 {{run:study.statistics.pruned_trials}} 个，"
                    "失败 {{run:study.statistics.failed_trials}} 个；"
                    "昂贵环节摊薄倍数 "
                    "{{run:study.statistics.evaluations_per_selection}}。"
                ),
            )
        )

    if agent:
        sections.append(
            ReportSection(
                key="compliance",
                title="八、合规证明",
                body=(
                    f"本次 Agent 运行的合规证明编号为 "
                    f"{{{{run:{agent}.compliance.proof_id}}}}，"
                    f"校验结论 {{{{run:{agent}.compliance.passed}}}}，"
                    f"签名 {{{{run:{agent}.compliance.signature}}}}，"
                    f"代码版本 {{{{run:{agent}.compliance.code_version}}}}。"
                ),
            )
        )

    sections.append(
        ReportSection(
            key="limitations",
            title="九、局限与风险提示",
            body=(
                "本报告的结论建立在线性 ARX 假设成立的前提下。若过程存在显著非线性、"
                "时变增益或未测扰动，模型的外推能力将下降。"
                "D-最优优选在同构激励场景下相对常规能量启发式无显著优势，"
                "其价值在于异构激励（真实历史数据的常态）下不会失效。"
                "报告中的全部数值均来自实际运行记录，未经任何模型改写。"
            ),
        )
    )
    _ = payload
    return sections


def _write_report(
    artifact_root: Path,
    *,
    report_id: UUID,
    rendered: RenderResult,
    payload: ReportRequest,
    index: RunIndex,
) -> str:
    root = artifact_root / "reports"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{report_id}.md"
    header = (
        f"# {payload.title}\n\n"
        f"生成时间：{datetime.now(UTC).isoformat()}\n\n"
        f"引用运行记录：{', '.join(sorted(index.records))}\n\n"
        f"数值绑定数：{len(rendered.bindings)}，未解析：{len(rendered.unresolved)}\n\n"
        "---\n\n"
    )
    path.write_text(header + rendered.text + "\n", encoding="utf-8")
    return path.relative_to(artifact_root).as_posix()


async def _persist(
    session: AsyncSession,
    *,
    report_id: UUID,
    payload: ReportRequest,
    rendered: RenderResult,
) -> None:
    now = datetime.now(UTC)
    session.add(
        ProcessingRun(
            id=report_id,
            dataset_id=payload.dataset_id,
            source_version_id=payload.version_id,
            run_type="reporting.generate",
            status="succeeded",
            parameters=payload.model_dump(mode="json"),
            result=rendered.to_payload(),
            created_at=now,
            finished_at=now,
        )
    )
    session.add(
        OperationLog(
            id=uuid4(),
            event_type="reporting.generate.completed",
            subject_id=str(payload.dataset_id) if payload.dataset_id else str(report_id),
            payload_json=json.dumps(
                {
                    "report_id": str(report_id),
                    "bindings": len(rendered.bindings),
                    "unresolved": list(rendered.unresolved),
                    "executed_at": now.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=now,
        )
    )
    await session.commit()


async def export_optimised_dataset(
    session: AsyncSession,
    *,
    payload: ExportDatasetRequest,
    artifact_root: Path,
) -> ExportDatasetData:
    """Write the selected rows to CSV alongside a manifest naming their provenance."""

    try:
        series = await load_version_series(
            session,
            version_id=payload.version_id,
            artifact_root=artifact_root,
            dataset_id=payload.dataset_id,
        )
        input_columns, output_column = series.resolve_columns(
            input_columns=payload.input_columns or None,
            output_column=payload.output_column,
        )
    except VersionDataError as error:
        raise ReportDomainError(
            error.code, error.message, status_code=error.status_code, details=error.details
        ) from error

    indices = sorted(set(payload.sample_indices)) if payload.sample_indices else None
    if indices is None:
        statement = (
            select(ProcessingRun)
            .where(ProcessingRun.run_type == "preprocessing.segment")
            .order_by(ProcessingRun.created_at.desc())
            .limit(RUN_SCAN_LIMIT)
        )
        candidates = list((await session.scalars(statement)).all())
        run = next(
            (
                candidate
                for candidate in candidates
                if _matches(
                    candidate,
                    dataset_id=payload.dataset_id,
                    version_id=payload.version_id,
                )
            ),
            None,
        )
        if run is not None:
            indices = sorted(
                set(int(v) for v in (run.result or {}).get("selected_sample_indices", []))
            )
    if not indices:
        raise ReportDomainError(
            "EXPORT_NO_SELECTION",
            "没有可导出的优选样本，请先执行动态区间优选或显式提供样本下标。",
            status_code=404,
        )

    n_samples = series.n_samples
    indices = [index for index in indices if 0 <= index < n_samples]
    if not indices:
        raise ReportDomainError("EXPORT_NO_SELECTION", "优选样本下标全部越界。", status_code=400)

    export_id = uuid4()
    root = artifact_root / "exports"
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / f"{export_id}.csv"
    columns = [*input_columns, output_column]
    has_timestamps = len(series.timestamps) == n_samples

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow((["timestamp"] if has_timestamps else ["sample_index"]) + columns)
        for index in indices:
            first = series.timestamps[index].isoformat() if has_timestamps else str(index)
            row = [first]
            for column in columns:
                value = series.values[column][index]
                row.append("" if not np.isfinite(value) else format(float(value), ".12g"))
            writer.writerow(row)

    manifest_path = root / f"{export_id}.manifest.json"
    manifest = {
        "export_id": str(export_id),
        "dataset_id": str(series.dataset_id),
        "version_id": str(series.version_id),
        "origin": series.origin,
        "input_columns": list(input_columns),
        "output_column": output_column,
        "exported_rows": len(indices),
        "source_rows": n_samples,
        "coverage_ratio": len(indices) / n_samples if n_samples else 0.0,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    now = datetime.now(UTC)
    session.add(
        ProcessingRun(
            id=export_id,
            dataset_id=series.dataset_id if series.origin == "dataset" else None,
            source_version_id=series.version_id if series.origin == "dataset" else None,
            run_type="delivery.export",
            status="succeeded",
            parameters=payload.model_dump(mode="json"),
            result=manifest,
            created_at=now,
            finished_at=now,
        )
    )
    await session.commit()

    return ExportDatasetData(
        export_id=export_id,
        dataset_id=series.dataset_id,
        version_id=series.version_id,
        task=completed_task(stage="export_dataset", message="优选数据集已导出。"),
        csv_uri=csv_path.relative_to(artifact_root).as_posix(),
        manifest_uri=manifest_path.relative_to(artifact_root).as_posix(),
        exported_rows=len(indices),
        source_rows=n_samples,
        coverage_ratio=manifest["coverage_ratio"],
        columns=["timestamp" if has_timestamps else "sample_index", *columns],
    )


def _matches(
    run: ProcessingRun,
    *,
    dataset_id: UUID | None,
    version_id: UUID | None,
) -> bool:
    """Decide whether a run belongs to the requested dataset or version.

    The foreign keys alone are not enough. Runs on S1-S6 benchmark artifacts have no row in
    ``dataset_versions`` to point at, so their FKs are deliberately null and the identity
    lives in the run's own recorded parameters. Matching on both keeps benchmark runs — the
    ones every demonstration uses — citable in a report.
    """

    if dataset_id is None and version_id is None:
        return True
    parameters = run.parameters or {}
    if dataset_id is not None:
        if run.dataset_id == dataset_id:
            return True
        if str(parameters.get("dataset_id") or "") == str(dataset_id):
            return True
    if version_id is not None:
        if run.source_version_id == version_id:
            return True
        if str(parameters.get("version_id") or "") == str(version_id):
            return True
        if str(parameters.get("active_version_id") or "") == str(version_id):
            return True
    return False


def _short_id(value: UUID) -> str:
    """Placeholders read better with a short handle than a full UUID."""

    return f"r{str(value).replace('-', '')[:8]}"
