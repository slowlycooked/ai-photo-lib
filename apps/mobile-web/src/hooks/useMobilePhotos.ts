import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/api";

const PAGE_SIZE = 50;

export function useMobilePhotos(projectId: number | null) {
  return useInfiniteQuery({
    queryKey: ["mobile-photos", projectId],
    enabled: projectId != null,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.photos.list(projectId!, 1, PAGE_SIZE, "cursor", pageParam),
    getNextPageParam: (lastPage) =>
      lastPage.has_more && lastPage.next_cursor
        ? lastPage.next_cursor
        : undefined,
  });
}
