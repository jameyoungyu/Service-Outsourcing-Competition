import apiClient from "./client";
import type {
  DatasetItem,
  DatasetListResponse,
  DatasetUploadResponse,
  DatasetProfile,
  DatasetVersionsResponse,
  DatasetDeleteResponse,
  DatasetConfigRequest,
} from "../types/api";

export const uploadDataset = (file: File, name?: string): Promise<DatasetUploadResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  if (name) {
    formData.append("name", name);
  }
  return apiClient.post("/datasets/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
};

export const getDatasets = (page = 1, pageSize = 20): Promise<DatasetListResponse> =>
  apiClient.get(`/datasets?page=${page}&page_size=${pageSize}`);

export const getDatasetDetail = (datasetId: string): Promise<DatasetItem> =>
  apiClient.get(`/datasets/${datasetId}`);

export const configureDataset = (
  datasetId: string,
  payload: DatasetConfigRequest
): Promise<{ dataset: DatasetItem; profile: DatasetProfile }> =>
  apiClient.post(`/datasets/${datasetId}/config`, payload);

export const getDatasetProfile = (datasetId: string): Promise<DatasetProfile> =>
  apiClient.get(`/datasets/${datasetId}/profile`);

export const getDatasetVersions = (datasetId: string): Promise<DatasetVersionsResponse> =>
  apiClient.get(`/datasets/${datasetId}/versions`);

export const deleteDataset = (datasetId: string): Promise<DatasetDeleteResponse> =>
  apiClient.delete(`/datasets/${datasetId}`);
