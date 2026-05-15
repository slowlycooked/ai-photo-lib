import { useInfiniteQuery } from "@tanstack/react-query";
import { api, type Photo } from "@/lib/api";

const PAGE_SIZE = 50;

export function usePhotos() {
  return useInfiniteQuery({
    queryKey: ["photos"],
    queryFn: ({ pageParam = 1 }) => api.photos.list(pageParam as number, PAGE_SIZE),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = (last.page - 1) * last.page_size + last.items.length;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: 30_000,
  });
}

export type { Photo };
