import { useEffect, useRef } from "react";

interface UseInfiniteScrollSentinelOptions {
  hasNextPage?: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: (options?: { cancelRefetch?: boolean }) => Promise<unknown>;
  rootMargin?: string;
  requireScrollDown?: boolean;
}

export function useInfiniteScrollSentinel<TElement extends Element>({
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  rootMargin = "200px",
  requireScrollDown = false,
}: UseInfiniteScrollSentinelOptions) {
  const sentinelRef = useRef<TElement>(null);
  const fetchLockRef = useRef(false);
  const hasScrolledDownRef = useRef(!requireScrollDown);

  useEffect(() => {
    if (!isFetchingNextPage) {
      fetchLockRef.current = false;
    }
  }, [isFetchingNextPage]);

  useEffect(() => {
    hasScrolledDownRef.current = !requireScrollDown;
    if (!requireScrollDown) {
      return;
    }

    let lastScrollY = window.scrollY;
    const onScroll = () => {
      const currentScrollY = window.scrollY;
      if (currentScrollY > lastScrollY) {
        hasScrolledDownRef.current = true;
      }
      lastScrollY = currentScrollY;
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [requireScrollDown]);

  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (
          !entries[0].isIntersecting ||
          isFetchingNextPage ||
          fetchLockRef.current ||
          (requireScrollDown && !hasScrolledDownRef.current)
        ) {
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
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, requireScrollDown, rootMargin]);

  return sentinelRef;
}
