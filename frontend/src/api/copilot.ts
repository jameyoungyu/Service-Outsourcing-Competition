import apiClient from "./client";
import type { CopilotChatRequest, CopilotChatResponse, CopilotConfirmRequest } from "../types/api";

export const chatWithCopilot = (req: CopilotChatRequest): Promise<CopilotChatResponse> =>
  apiClient.post("/copilot/chat", req);

export const confirmCopilotStep = (
  req: CopilotConfirmRequest
): Promise<{ success: boolean; next_step_id?: string }> =>
  apiClient.post("/copilot/confirm", req);
