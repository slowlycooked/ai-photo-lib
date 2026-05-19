import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, type Photo } from "@/lib/api";

const PAGE_SIZE = 50;

interface UsePhotosOptions {
  projectId?: number | null;
  dateFrom?: string | null;
  dateTo?: string | null;
}

export function usePhotos({ projectId, dateFrom, dateTo }: UsePhotosOptions = {}) {
  return useInfiniteQuery({
    queryKey: ["photos", projectId, dateFrom, dateTo],
    queryFn: ({ pageParam = 1 }) =>
      api.photos.list(pageParam as number, PAGE_SIZE, projectId, dateFrom, dateTo),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = (last.page - 1) * last.page_size + last.items.length;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: 30_000,
  });
}

export function useTimeline(projectId?: number | null) {
  return useQuery({
    queryKey: ["timeline", projectId],
    queryFn: () => api.photos.timeline(projectId),
    staleTime: 60_000,
  });
}

export type { Photo };
