import apiClient from "./client";
import type {
  CleanRequest,
  CleanResponse,
  SegmentRequest,
  SegmentResponse,
  DelayRequest,
  DelayResponse,
  CollinearityRequest,
  CollinearityResponse,
} from "../types/api";

export const cleanDataset = (req: CleanRequest): Promise<CleanResponse> =>
  apiClient.post("/preprocessing/clean", req);

export const segmentDataset = (req: SegmentRequest): Promise<SegmentResponse> =>
  apiClient.post("/preprocessing/segment", req);

export const calculateDelay = (req: DelayRequest): Promise<DelayResponse> =>
  apiClient.post("/preprocessing/delay", req);

export const calculateCollinearity = (req: CollinearityRequest): Promise<CollinearityResponse> =>
  apiClient.post("/preprocessing/collinearity", req);
