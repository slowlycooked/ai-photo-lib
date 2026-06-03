import { useEffect, useRef } from "react";

interface UseInfiniteScrollSentinelOptions {
  hasNextPage?: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: (options?: { cancelRefetch?: boolean }) => Promise<unknown>;
  rootMargin?: string;
}

export function useInfiniteScrollSentinel<TElement extends Element>({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  rootMargin = "200px",
}: UseInfiniteScrollSentinelOptions) {
  const sentinelRef = useRef<TElement>(null);
  const fetchLockRef = useRef(false);

  useEffect(() => {
    if (!isFetchingNextPage) {
      fetchLockRef.current = false;
    }
  }, [isFetchingNextPage]);

  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting || isFetchingNextPage || fetchLockRef.current) {
          return;
        }

        fetchLockRef.current = true;
        void fetchNextPage({ cancelRefetch: false }).finally(() => {
          fetchLockRef.current = false;
        });
      },
      { rootMargin },
    );

    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, rootMargin]);

  return sentinelRef;
}
