import { useQuery } from "@tanstack/react-query";
import { api } from "@/api";

export function useFolderTree(projectId?: number | null) {
  return useQuery({
    queryKey: ["folders", projectId],
    queryFn: ({ signal }) => api.folders.tree(projectId!, signal),
    enabled: !!projectId,
    staleTime: 60_000, // 1 分钟
  });
}

export function useFolderBreadcrumb(projectId?: number | null, folderId?: number | null) {
  return useQuery({
    queryKey: ["folder-breadcrumb", projectId, folderId],
    queryFn: ({ signal }) => api.folders.breadcrumb(projectId!, folderId!, signal),
    enabled: !!projectId && !!folderId,
    staleTime: 60_000,
  });
}
