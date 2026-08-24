import { ApiError, BASE, request, qs } from "./client";
import type {
  AIAnalysis,
  FolderScope,
  PhotoBatchDeleteRequest,
  PhotoBatchDeleteResponse,
  PhotoDeleteResponse,
  PhotoDetail,
  PhotoListResponse,
  TimelineResponse,
} from "./types";

export const projectPhotosApi = {
  list: (
    projectId: number,
    page = 1,
    pageSize = 50,
    dateFrom?: string | null,
    dateTo?: string | null,
    folderId?: number | null,
    folderScope: FolderScope = "subtree",
    pagination: "offset" | "cursor" = "offset",
    cursor?: string | null,
  ) =>
    request<PhotoListResponse>(
      `/projects/${projectId}/photos${qs({
        page,
        page_size: pageSize,
        date_from: dateFrom,
        date_to: dateTo,
        folder_id: folderId,
        folder_scope: folderScope,
        pagination,
        cursor,
      })}`,
    ),

  timeline: (
    projectId: number,
    folderId?: number | null,
    folderScope: FolderScope = "subtree",
  ) =>
    request<TimelineResponse>(
      `/projects/${projectId}/photos/timeline${qs({
        folder_id: folderId,
        folder_scope: folderScope,
      })}`,
    ),

  get: (projectId: number, photoId: number) =>
    request<PhotoDetail>(`/projects/${projectId}/photos/${photoId}`),

  ai: (projectId: number, photoId: number) =>
    request<AIAnalysis>(`/projects/${projectId}/photos/${photoId}/ai`),

  thumbnailUrl: (projectId: number, photoId: number, updatedAt?: string | null) => {
    const base = `${BASE}/projects/${projectId}/photos/${photoId}/thumbnail`;
    if (!updatedAt) return base;
    const version = Date.parse(updatedAt);
    return Number.isNaN(version) ? base : `${base}?v=${version}`;
  },

  originalUrl: (projectId: number, photoId: number) =>
    `${BASE}/projects/${projectId}/photos/${photoId}/original`,

  previewUrl: (projectId: number, photoId: number) =>
    `${BASE}/projects/${projectId}/photos/${photoId}/preview`,

  deleteRecord: async (
    projectId: number,
    photoId: number,
    deleteOriginal = false,
  ) => {
    const query = qs({ delete_original: deleteOriginal || undefined });
    try {
      return await request<PhotoDeleteResponse>(
        `/projects/${projectId}/photos/${photoId}${query}`,
        { method: "DELETE" },
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 405) {
        return request<PhotoDeleteResponse>(
          `/projects/${projectId}/photos/${photoId}/delete${query}`,
          { method: "POST" },
        );
      }
      throw error;
    }
  },

  batchDeleteRecords: (projectId: number, body: PhotoBatchDeleteRequest) =>
    request<PhotoBatchDeleteResponse>(`/projects/${projectId}/photos/batch-delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
