import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, type Photo, type FolderScope } from "@/lib/api";

const PAGE_SIZE = 50;

interface UsePhotosOptions {
  projectId?: number | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  folderId?: number | null;
  folderScope?: FolderScope;
}

export function usePhotos({ projectId, dateFrom, dateTo, folderId, folderScope = "subtree" }: UsePhotosOptions = {}) {
  return useInfiniteQuery({
    queryKey: ["photos", projectId, dateFrom, dateTo, folderId, folderScope],
    queryFn: ({ pageParam = 1 }) =>
      projectId != null
        ? api.projects.photos(projectId, pageParam as number, PAGE_SIZE, dateFrom, dateTo, folderId, folderScope)
        : Promise.resolve({ total: 0, page: 1, page_size: PAGE_SIZE, items: [] }),
    initialPageParam: 1,
    enabled: projectId != null,
    getNextPageParam: (last) => {
      const loaded = (last.page - 1) * last.page_size + last.items.length;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: 30_000,
  });
}

export function useTimeline(projectId?: number | null, folderId?: number | null, folderScope: FolderScope = "subtree") {
  return useQuery({
    queryKey: ["timeline", projectId, folderId, folderScope],
    queryFn: () => projectId != null
      ? api.projects.timeline(projectId, folderId, folderScope)
      : Promise.resolve({ items: [] }),
    enabled: projectId != null,
    staleTime: 60_000,
  });
}

export type { Photo };
