import { ChevronLeft, ChevronRight } from "lucide-react";
import type { TouchEvent } from "react";

export function PhotoViewer({
  src,
  poster,
  alt,
  mediaType,
  canPrev,
  canNext,
  onPrev,
  onNext,
  swipeHandlers,
}: {
  src: string;
  poster?: string;
  alt: string;
  mediaType?: string | null;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  swipeHandlers: {
    onTouchStart: (e: TouchEvent) => void;
    onTouchEnd: (e: TouchEvent) => void;
  };
}) {
  return (
    <div
      className="mobile-photo-viewer relative flex w-full items-center justify-center overflow-hidden rounded-2xl border border-mobileHairline bg-black"
      onTouchStart={swipeHandlers.onTouchStart}
      onTouchEnd={swipeHandlers.onTouchEnd}
    >
      {mediaType?.startsWith("video/") ? (
        <video
          src={src}
          poster={poster}
          controls
          playsInline
          preload="metadata"
          aria-label={`播放视频 ${alt}`}
          className="block h-full w-full object-contain focus-visible:ring-2 focus-visible:ring-mobileAccent"
        />
      ) : (
        <img src={src} alt={alt} className="block h-full w-full object-contain" />
      )}

      <button
        type="button"
        disabled={!canPrev}
        onClick={onPrev}
        className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 text-white disabled:opacity-40"
        aria-label="上一张"
      >
        <ChevronLeft size={18} />
      </button>
      <button
        type="button"
        disabled={!canNext}
        onClick={onNext}
        className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 text-white disabled:opacity-40"
        aria-label="下一张"
      >
        <ChevronRight size={18} />
      </button>
    </div>
  );
}
