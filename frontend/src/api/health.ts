import apiClient from "./client";
import type { LivenessData, ReadinessData, SystemInfoData } from "../types/api";

export const getHealthLive = (): Promise<LivenessData> => apiClient.get("/health/live");

export const getHealthReady = (): Promise<ReadinessData> => apiClient.get("/health/ready");

export const getSystemInfo = (): Promise<SystemInfoData> => apiClient.get("/system/info");
