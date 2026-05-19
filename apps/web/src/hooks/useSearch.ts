import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const PAGE_SIZE = 50;

export function useSearch(query: string, projectId?: number | null) {
  return useInfiniteQuery({
    queryKey: ["search", query, projectId],
    queryFn: ({ pageParam = 1 }) =>
      api.search.query(query, pageParam as number, PAGE_SIZE, projectId),
    initialPageParam: 1,
    enabled: query.trim().length > 0,
    getNextPageParam: (last) => {
      const loaded = (last.page - 1) * last.page_size + last.items.length;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: 60_000,
  });
}
