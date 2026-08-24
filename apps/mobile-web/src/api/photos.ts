import { BASE, qs, request } from "./client";
import type { PhotoDetail, PhotoListResponse } from "./types";

export const photosApi = {
  list: (
    projectId: number,
    page = 1,
    pageSize = 50,
    pagination: "offset" | "cursor" = "offset",
    cursor?: string | null,
  ) =>
    request<PhotoListResponse>(
      `/projects/${projectId}/photos${qs({
        page,
        page_size: pageSize,
        pagination,
        cursor,
      })}`,
    ),

  get: (projectId: number, photoId: number) =>
    request<PhotoDetail>(`/projects/${projectId}/photos/${photoId}`),

  thumbnailUrl: (projectId: number, photoId: number, updatedAt?: string | null) => {
    const base = `${BASE}/projects/${projectId}/photos/${photoId}/thumbnail`;
    if (!updatedAt) return base;
    const version = Date.parse(updatedAt);
    return Number.isNaN(version) ? base : `${base}?v=${version}`;
  },

  previewUrl: (projectId: number, photoId: number) =>
    `${BASE}/projects/${projectId}/photos/${photoId}/preview`,

  originalUrl: (projectId: number, photoId: number) =>
    `${BASE}/projects/${projectId}/photos/${photoId}/original`,
};
