import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export function useFolderTree(projectId?: number | null) {
  return useQuery({
    queryKey: ["folders", projectId],
    queryFn: () => api.folders.tree(projectId!),
    enabled: !!projectId,
    staleTime: 60_000, // 1 分钟
  });
}

export function useFolderBreadcrumb(projectId?: number | null, folderId?: number | null) {
  return useQuery({
    queryKey: ["folder-breadcrumb", projectId, folderId],
    queryFn: () => api.folders.breadcrumb(projectId!, folderId!),
    enabled: !!projectId && !!folderId,
    staleTime: 60_000,
  });
}
