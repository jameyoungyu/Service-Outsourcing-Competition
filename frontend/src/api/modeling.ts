import apiClient from "./client";
import type {
  ARXFitRequest,
  ARXFitResponse,
  OptunaStartRequest,
  OptunaStatusResponse,
  TaskResource,
} from "../types/api";

export const fitARXModel = (req: ARXFitRequest): Promise<ARXFitResponse> =>
  apiClient.post("/modeling/arx/fit", req);

export const startOptunaStudy = (
  req: OptunaStartRequest
): Promise<{ study_id: string; task: TaskResource }> =>
  apiClient.post("/optimization/optuna/start", req);

export const getOptunaStatus = (studyId: string): Promise<OptunaStatusResponse> =>
  apiClient.get(`/optimization/optuna/${studyId}/status`);

export const cancelTask = (taskId: string): Promise<{ cancelled: boolean }> =>
  apiClient.post(`/tasks/${taskId}/cancel`);
