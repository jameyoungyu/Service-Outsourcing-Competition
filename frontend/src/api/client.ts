import axios, { AxiosError, type AxiosInstance, type AxiosResponse } from "axios";
import type { ApiResponse, ErrorEnvelope } from "../types/api";

export class ApiError extends Error {
  code: string;
  requestId: string;
  details?: Record<string, any> | null;

  constructor(code: string, message: string, requestId: string, details?: Record<string, any> | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<any>>) => {
    const body = response.data;
    if (body.success === true) {
      return body.data;
    } else if (body.success === false) {
      const err = body as ErrorEnvelope;
      throw new ApiError(
        err.error?.code || "UNKNOWN_ERROR",
        err.error?.message || "请求处理失败",
        err.request_id || "",
        err.error?.details
      );
    }
    return body;
  },
  (error: AxiosError<ErrorEnvelope>) => {
    if (error.response && error.response.data && error.response.data.success === false) {
      const err = error.response.data;
      throw new ApiError(
        err.error?.code || `HTTP_${error.response.status}`,
        err.error?.message || error.message,
        err.request_id || "",
        err.error?.details
      );
    }
    throw new ApiError(
      `HTTP_${error.response?.status || 500}`,
      error.message || "网络连接异常",
      "",
      null
    );
  }
);

export default apiClient;
