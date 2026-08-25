import { BASE, request, qs } from "./client";
import type {
  FaceClusterUnknownRequest,
  FaceClusterUnknownResponse,
  FaceClusterUnknownStatusResponse,
  FaceDetectionDetail,
  FaceDetectionListResponse,
  FaceRematchUnknownRequest,
  FaceRematchUnknownResponse,
  FaceRematchUnknownStatusResponse,
  FaceScanProjectStartRequest,
  FaceScanProjectStartResponse,
  FaceScanProjectStatusResponse,
  FaceScanResponse,
} from "./types";

export const projectFacesApi = {
  scanPhoto: (projectId: number, photoId: number) =>
    request<FaceScanResponse>(`/projects/${projectId}/photos/${photoId}/face-scan`, {
      method: "POST",
    }),

  startProjectScan: (
    projectId: number,
    body: FaceScanProjectStartRequest = {},
  ) =>
    request<FaceScanProjectStartResponse>(
      `/projects/${projectId}/face-scan-project/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  projectScanStatus: (projectId: number) =>
    request<FaceScanProjectStatusResponse>(
      `/projects/${projectId}/face-scan-project/status`,
    ),

  cancelProjectScan: (projectId: number) =>
    request<FaceScanProjectStatusResponse>(
      `/projects/${projectId}/face-scan-project/cancel`,
      { method: "POST" },
    ),

  clusterUnknown: (
    projectId: number,
    body: FaceClusterUnknownRequest = {},
  ) =>
    request<FaceClusterUnknownResponse>(`/projects/${projectId}/face-cluster-unknown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  clusterUnknownStatus: (projectId: number) =>
    request<FaceClusterUnknownStatusResponse>(
      `/projects/${projectId}/face-cluster-unknown/status`,
    ),

  cancelClusterUnknown: (projectId: number) =>
    request<FaceClusterUnknownStatusResponse>(
      `/projects/${projectId}/face-cluster-unknown/cancel`,
      { method: "POST" },
    ),

  rematchUnknown: (
    projectId: number,
    body: FaceRematchUnknownRequest = {},
  ) =>
    request<FaceRematchUnknownResponse>(`/projects/${projectId}/face-rematch-unknown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  rematchUnknownStatus: (
    projectId: number,
    filter: Pick<FaceRematchUnknownRequest, "scope" | "person_id"> = {},
  ) =>
    request<FaceRematchUnknownStatusResponse>(
      `/projects/${projectId}/face-rematch-unknown/status${qs({
        scope: filter.scope,
        person_id: filter.person_id,
      })}`,
    ),

  cancelRematchUnknown: (projectId: number) =>
    request<FaceRematchUnknownStatusResponse>(
      `/projects/${projectId}/face-rematch-unknown/cancel`,
      { method: "POST" },
    ),

  list: (
    projectId: number,
    page = 1,
    pageSize = 50,
    photoId?: number | null,
    status?: string | null,
  ) =>
    request<FaceDetectionListResponse>(
      `/projects/${projectId}/faces${qs({
        page,
        page_size: pageSize,
        photo_id: photoId,
        status: status ?? undefined,
      })}`,
    ),

  get: (projectId: number, faceId: number) =>
    request<FaceDetectionDetail>(`/projects/${projectId}/faces/${faceId}`),

  cropUrl: (projectId: number, faceId: number, updatedAt?: string | null) => {
    const base = `${BASE}/projects/${projectId}/faces/${faceId}/crop`;
    if (!updatedAt) return base;
    const version = Date.parse(updatedAt);
    return Number.isNaN(version) ? base : `${base}?v=${version}`;
  },
};
