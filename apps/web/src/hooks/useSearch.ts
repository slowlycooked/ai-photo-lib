import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SearchMode, TagField } from "@/api/types";

const PAGE_SIZE = 50;

interface UseSearchOptions {
  mode?: SearchMode;
  debug?: boolean;
  folderId?: number | null;
  folderScope?: string;
  tagField?: TagField | null;
  tagValue?: string | null;
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
  } = options;

  const isTagFilter = tagField != null && tagValue != null;

  return useInfiniteQuery({
    queryKey: ["search", query, projectId, mode, debug, folderId, folderScope, tagField, tagValue],
    queryFn: ({ pageParam = 1 }) =>
      api.projects.search(
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
      ),
    initialPageParam: 1,
    enabled: (query.trim().length > 0 || isTagFilter) && projectId !== null,
    getNextPageParam: (last) => {
      const loaded = (last.page - 1) * last.page_size + last.items.length;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: 60_000,
  });
}
