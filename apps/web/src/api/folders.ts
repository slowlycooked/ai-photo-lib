import { request, qs, BASE } from "./client";
import type {
  FolderBreadcrumbResponse,
  FolderTreeResponse,
} from "./types";

export const foldersApi = {
  tree: (projectId: number) =>
    request<FolderTreeResponse>(`/projects/${projectId}/folders/tree`),

  breadcrumb: (projectId: number, folderId: number) =>
    request<FolderBreadcrumbResponse>(
      `/projects/${projectId}/folders/${folderId}/breadcrumb`,
    ),
};
