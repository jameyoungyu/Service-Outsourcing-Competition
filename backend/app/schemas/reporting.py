"""Schemas for provenance-bound reports and optimised-dataset delivery."""

from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema, TaskResource


class ReportRequest(Schema):
    dataset_id: UUID | None = None
    version_id: UUID | None = None
    study_id: UUID | None = None
    title: str = Field(default="IndusOpt 建模数据优选与辨识报告", min_length=1, max_length=200)


class ReportSection(Schema):
    key: str
    title: str
    body: str


class ReportBinding(Schema):
    """One number in the report, and the run record it was read from."""

    placeholder: str
    kind: str
    run_id: str
    path: str
    value: str
    resolved: bool


class ReportData(Schema):
    report_id: UUID
    dataset_id: UUID | None = None
    task: TaskResource
    title: str
    markdown: str
    sections: list[ReportSection]
    # Every figure in `markdown` appears here with its source run and field path.
    bindings: list[ReportBinding] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    fully_resolved: bool = True
    artifact_uri: str | None = None
    cited_runs: list[str] = Field(default_factory=list)


class ExportDatasetRequest(Schema):
    version_id: UUID
    dataset_id: UUID | None = None
    input_columns: list[str] = Field(default_factory=list)
    output_column: str | None = None
    # Explicit rows to export. When empty the latest selection run's rows are used.
    sample_indices: list[int] = Field(default_factory=list)


class ExportDatasetData(Schema):
    export_id: UUID
    dataset_id: UUID | None = None
    version_id: UUID
    task: TaskResource
    csv_uri: str
    manifest_uri: str
    exported_rows: int = Field(ge=0)
    source_rows: int = Field(ge=0)
    coverage_ratio: float
    columns: list[str] = Field(default_factory=list)
