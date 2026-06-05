import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/api";
import type { SearchMode, TagField } from "@/api/types";

const PAGE_SIZE = 50;

interface UseSearchOptions {
  mode?: SearchMode;
  debug?: boolean;
  folderId?: number | null;
  folderScope?: string;
  tagField?: TagField | null;
  tagValue?: string | null;
  faceCountMin?: number | null;
  faceCountMax?: number | null;
  hasReviewPending?: boolean | null;
  hasUnnamedPeople?: boolean | null;
}

export function useSearch(
  query: string,
  projectId: number | null,
  options: UseSearchOptions = {},
) {
  const {
    mode = "auto",
    debug = false,
    folderId = null,
    folderScope = "subtree",
    tagField = null,
    tagValue = null,
    faceCountMin = null,
    faceCountMax = null,
    hasReviewPending = null,
    hasUnnamedPeople = null,
  } = options;

  const isTagFilter = tagField != null && tagValue != null;

  return useInfiniteQuery({
    queryKey: [
      "search",
      query,
      projectId,
      mode,
      debug,
      folderId,
      folderScope,
      tagField,
      tagValue,
      faceCountMin,
      faceCountMax,
      hasReviewPending,
      hasUnnamedPeople,
    ],
    queryFn: ({ pageParam = 1 }) =>
      api.projectSearch.search(
        projectId!,
        query,
        pageParam as number,
        PAGE_SIZE,
        folderId,
        folderScope as "subtree" | "direct",
        mode,
        debug,
        tagField,
        tagValue,
        faceCountMin,
        faceCountMax,
        hasReviewPending,
        hasUnnamedPeople,
      ),
    initialPageParam: 1,
    enabled: (query.trim().length > 0 || isTagFilter) && projectId !== null,
    getNextPageParam: (last, allPages, _lastPageParam, allPageParams) => {
      if (last.items.length < last.page_size) {
        return undefined;
      }

      const loadedUniqueCount = new Set(allPages.flatMap((page) => page.items.map((item) => item.photo_id))).size;
      if (loadedUniqueCount >= last.total) {
        return undefined;
      }

      const requestedPages = allPageParams
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0);
      const maxRequestedPage = requestedPages.length > 0 ? Math.max(...requestedPages) : 1;
      const nextPage = maxRequestedPage + 1;

      return requestedPages.includes(nextPage) ? undefined : nextPage;
    },
    staleTime: 60_000,
  });
}
