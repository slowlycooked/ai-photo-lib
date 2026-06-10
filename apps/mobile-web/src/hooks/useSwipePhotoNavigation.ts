import { useMemo, useRef } from "react";
import type { TouchEvent } from "react";

interface SwipeOptions {
  threshold?: number;
  onPrev: () => void;
  onNext: () => void;
}

export function useSwipePhotoNavigation(options: SwipeOptions) {
  const { onPrev, onNext } = options;
  const threshold = options.threshold ?? 40;
  const startX = useRef<number | null>(null);

  return useMemo(
    () => ({
      onTouchStart: (e: TouchEvent) => {
        startX.current = e.changedTouches[0]?.clientX ?? null;
      },
      onTouchEnd: (e: TouchEvent) => {
        const start = startX.current;
        const end = e.changedTouches[0]?.clientX;
        startX.current = null;
        if (start == null || end == null) return;

        const delta = end - start;
        if (Math.abs(delta) < threshold) return;
        if (delta > 0) {
          onPrev();
          return;
        }
        onNext();
      },
    }),
    [onPrev, onNext, threshold],
  );
}
