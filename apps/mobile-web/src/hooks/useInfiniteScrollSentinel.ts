import { useEffect, useRef } from "react";

export function useInfiniteScrollSentinel(
  onIntersect: () => void,
  enabled: boolean,
  rootMargin = "240px",
) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!enabled || !ref.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          onIntersect();
        }
      },
      { rootMargin },
    );

    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [enabled, onIntersect, rootMargin]);

  return ref;
}
