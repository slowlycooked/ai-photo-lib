import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/api";

const PAGE_SIZE = 50;

export function useMobilePhotos(projectId: number | null) {
  return useInfiniteQuery({
    queryKey: ["mobile-photos", projectId],
    enabled: projectId != null,
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      api.photos.list(projectId!, pageParam as number, PAGE_SIZE),
    getNextPageParam: (lastPage) => {
      const loaded = lastPage.page * lastPage.page_size;
      return loaded < lastPage.total ? lastPage.page + 1 : undefined;
    },
  });
}
