import { request, qs, BASE } from "./client";
import type {
  FolderBreadcrumbResponse,
  FolderTreeResponse,
} from "./types";

export const foldersApi = {
  tree: (projectId: number, signal?: AbortSignal) =>
    request<FolderTreeResponse>(`/projects/${projectId}/folders/tree`, { signal }),

  breadcrumb: (projectId: number, folderId: number, signal?: AbortSignal) =>
    request<FolderBreadcrumbResponse>(
      `/projects/${projectId}/folders/${folderId}/breadcrumb`,
      { signal },
    ),
};
