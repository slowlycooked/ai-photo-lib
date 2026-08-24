import { lazy, Suspense, useState } from "react";
import { ImageIcon, MapPin } from "lucide-react";
import type { Photo } from "@/api";
import { api } from "@/api";
import { formatLocationAddress, formatLocationSummary } from "@/lib/utils";

const PhotoDetailModal = lazy(() =>
  import("./photo-card/PhotoDetailModal").then((module) => ({
    default: module.PhotoDetailModal,
  })),
);

interface PhotoCardProps {
  photo: Photo;
  priority?: boolean;
  selectMode?: boolean;
  selected?: boolean;
  onToggleSelect?: (photoId: number, checked: boolean) => void;
  onDeleted?: (photoId: number) => void;
}

export function PhotoCard({
  photo,
  priority = false,
  selectMode = false,
  selected = false,
  onToggleSelect,
  onDeleted,
}: PhotoCardProps) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const [showDetail, setShowDetail] = useState(false);
  const locationSummary = formatLocationSummary(photo, { short: true });
  const locationAddress = formatLocationAddress(photo);
  const thumbnailUrl = api.projectPhotos.thumbnailUrl(photo.project_id, photo.id, photo.updated_at);
  const retryThumbnailUrl = retryNonce
    ? `${thumbnailUrl}${thumbnailUrl.includes("?") ? "&" : "?"}retry=${retryNonce}`
    : thumbnailUrl;
  const gpsFallback =
    photo.gps_latitude != null && photo.gps_longitude != null
      ? `${photo.gps_latitude.toFixed(5)}, ${photo.gps_longitude.toFixed(5)}`
      : null;

  return (
    <>
      <div
        className="masonry-item cursor-pointer group relative bg-surface-card"
        onClick={() => setShowDetail(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setShowDetail(true)}
        aria-label={`查看照片 ${photo.file_name}`}
      >
        {selectMode && (
          <label
            className={[
              "absolute left-2 top-2 z-10 rounded-full bg-canvas/95 p-1 shadow-sm transition-opacity duration-150",
              selected ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100",
            ].join(" ")}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={selected}
              onChange={(e) => onToggleSelect?.(photo.id, e.target.checked)}
              className="h-4 w-4"
              aria-label={`选择照片 ${photo.file_name}`}
            />
          </label>
        )}

        {errored ? (
          <button
            type="button"
            className="w-full h-32 flex flex-col items-center justify-center gap-1 bg-surface-card"
            onClick={(event) => {
              event.stopPropagation();
              setLoaded(false);
              setErrored(false);
              setRetryNonce(Date.now());
            }}
          >
            <ImageIcon className="w-6 h-6 text-stone" />
            <span className="text-caption-sm text-stone">无法加载，点击重试</span>
          </button>
        ) : (
          <div
            className="relative w-full"
            style={{ aspectRatio: photo.width && photo.height ? `${photo.width}/${photo.height}` : "4/3" }}
          >
            {!loaded && <div className="absolute inset-0 bg-secondary-bg animate-pulse" />}
            <img
              src={retryThumbnailUrl}
              alt={photo.file_name}
              className="block w-full h-full object-cover"
              style={{ opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
              loading={priority ? "eager" : "lazy"}
              fetchPriority={priority ? "high" : "auto"}
              decoding="async"
              onLoad={() => setLoaded(true)}
              onError={() => setErrored(true)}
            />
          </div>
        )}

        <div
          className="absolute inset-0 rounded-md opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none"
          style={{ background: "linear-gradient(to bottom, transparent 50%, rgba(0,0,0,0.35) 100%)" }}
        />

        {photo.taken_at && (
          <div
            className={[
              "absolute top-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150",
              selectMode ? "left-11" : "left-2",
            ].join(" ")}
          >
            <span className="bg-canvas text-ink text-btn-sm font-bold px-3 py-1 rounded-full shadow-sm whitespace-nowrap">
              {new Date(photo.taken_at).toLocaleDateString("zh-CN", { month: "short", year: "numeric" })}
            </span>
          </div>
        )}

        {(locationSummary || gpsFallback) && (
          <div className="absolute right-2 bottom-2 max-w-[62%] opacity-95 group-hover:opacity-100 transition-opacity duration-150 overflow-hidden">
            <span
              className="flex items-center gap-1.5 bg-black/72 text-white text-[11px] font-medium px-3 py-1 rounded-full shadow-sm overflow-hidden border border-white/12 backdrop-blur-sm"
              title={locationAddress ?? locationSummary ?? gpsFallback ?? ""}
            >
              <MapPin className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate min-w-0">{locationSummary ?? gpsFallback}</span>
            </span>
          </div>
        )}
      </div>

      {showDetail && (
        <Suspense
          fallback={
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 text-white">
              <span className="text-body-sm">正在加载照片详情…</span>
            </div>
          }
        >
          <PhotoDetailModal
            photo={photo}
            onClose={() => setShowDetail(false)}
            onDeleted={onDeleted}
          />
        </Suspense>
      )}
    </>
  );
}
