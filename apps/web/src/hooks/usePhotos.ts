import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, type Photo, type FolderScope } from "@/api";
import { queryKeys } from "@/api/queryKeys";

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
    queryKey: queryKeys.photos(projectId ?? null, dateFrom, dateTo, folderId, folderScope),
    queryFn: ({ pageParam = 1 }) =>
      projectId != null
        ? api.projects.photos(projectId, pageParam as number, PAGE_SIZE, dateFrom, dateTo, folderId, folderScope)
        : Promise.resolve({ total: 0, page: 1, page_size: PAGE_SIZE, items: [] }),
    initialPageParam: 1,
    enabled: projectId != null,
    getNextPageParam: (last, allPages, _lastPageParam, allPageParams) => {
      if (last.items.length < last.page_size) {
        return undefined;
      }

      const loadedUniqueCount = new Set(allPages.flatMap((page) => page.items.map((item) => item.id))).size;
      if (loadedUniqueCount >= last.total) {
        return undefined;
      }

      const requestedPages = allPageParams
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0);
      const maxRequestedPage = requestedPages.length > 0 ? Math.max(...requestedPages) : 1;
      const nextPage = maxRequestedPage + 1;

      // Never request the same page twice for a single query key.
      return requestedPages.includes(nextPage) ? undefined : nextPage;
    },
    staleTime: 30_000,
  });
}

export function useTimeline(projectId?: number | null, folderId?: number | null, folderScope: FolderScope = "subtree") {
  return useQuery({
    queryKey: queryKeys.timeline(projectId ?? null, folderId, folderScope),
    queryFn: () => projectId != null
      ? api.projects.timeline(projectId, folderId, folderScope)
      : Promise.resolve({ items: [] }),
    enabled: projectId != null,
    staleTime: 60_000,
  });
}

export type { Photo };
