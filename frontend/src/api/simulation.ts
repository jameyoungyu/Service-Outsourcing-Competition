import apiClient from "./client";
import type { SimulationGenerateRequest, SimulationGenerateResponse } from "../types/api";

export const generateSimulationDataset = (
  req: SimulationGenerateRequest
): Promise<SimulationGenerateResponse> => apiClient.post("/simulation/generate", req);
