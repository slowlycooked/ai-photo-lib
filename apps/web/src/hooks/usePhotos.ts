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
  initialPage?: number;
}

export function usePhotos({
  projectId,
  dateFrom,
  dateTo,
  folderId,
  folderScope = "subtree",
  initialPage,
}: UsePhotosOptions = {}) {
  const locateMode = initialPage != null;
  return useInfiniteQuery({
    queryKey: queryKeys.photos(
      projectId ?? null,
      dateFrom,
      dateTo,
      folderId,
      folderScope,
      initialPage,
    ),
    queryFn: ({ pageParam }) =>
      projectId != null
        ? api.projectPhotos.list(
            projectId,
            locateMode ? Number(pageParam) : 1,
            PAGE_SIZE,
            dateFrom,
            dateTo,
            folderId,
            folderScope,
            locateMode ? "offset" : "cursor",
            locateMode ? null : String(pageParam || "") || null,
          )
        : Promise.resolve({
            total: 0,
            page: 1,
            page_size: PAGE_SIZE,
            items: [],
            next_cursor: null,
            has_more: false,
          }),
    initialPageParam: locateMode ? initialPage : null as number | string | null,
    enabled: projectId != null,
    getNextPageParam: (last) => {
      if (locateMode) {
        return last.page * last.page_size < last.total ? last.page + 1 : undefined;
      }
      return last.has_more && last.next_cursor ? last.next_cursor : undefined;
    },
    staleTime: 30_000,
  });
}

export function useTimeline(projectId?: number | null, folderId?: number | null, folderScope: FolderScope = "subtree") {
  return useQuery({
    queryKey: queryKeys.timeline(projectId ?? null, folderId, folderScope),
    queryFn: () => projectId != null
      ? api.projectPhotos.timeline(projectId, folderId, folderScope)
      : Promise.resolve({ items: [] }),
    enabled: projectId != null,
    staleTime: 60_000,
  });
}

export type { Photo };
