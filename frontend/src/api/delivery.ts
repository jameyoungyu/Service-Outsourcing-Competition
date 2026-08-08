import apiClient from "./client";
import type {
  ExportDatasetRequest,
  ExportDatasetResponse,
  ReportRequest,
  ReportResponse,
} from "../types/api";

/** Compose a report from persisted runs; every figure is bound to the run that produced it. */
export const generateReport = (req: ReportRequest): Promise<ReportResponse> =>
  apiClient.post("/reports/generate", req);

/** Export the rows the closed loop selected, plus a provenance manifest. */
export const exportDataset = (req: ExportDatasetRequest): Promise<ExportDatasetResponse> =>
  apiClient.post("/delivery/export", req);
