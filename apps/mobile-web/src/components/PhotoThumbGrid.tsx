import { useLayoutEffect } from "react";
import { api, type Photo } from "@/api";
import { MobileMasonryGrid } from "@/components/MobileMasonryGrid";
import { Link, useLocation } from "react-router-dom";

const SCROLL_STORAGE_PREFIX = "ai-photo-lib:mobile:scroll:";

function scrollStorageKey(returnTo: string) {
  return `${SCROLL_STORAGE_PREFIX}${returnTo}`;
}

export function PhotoThumbGrid({
  projectId,
  photos,
  photoIds,
  priorityPhotoIds,
}: {
  projectId: number;
  photos: Photo[];
  photoIds: number[];
  priorityPhotoIds?: ReadonlySet<number>;
}) {
  const location = useLocation();
  const returnTo = `${location.pathname}${location.search}`;

  useLayoutEffect(() => {
    const key = scrollStorageKey(returnTo);
    const savedValue = sessionStorage.getItem(key);
    if (savedValue == null) return;
    const savedScrollY = Number(savedValue);
    if (!Number.isFinite(savedScrollY)) return;

    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: savedScrollY, left: 0, behavior: "auto" });
      sessionStorage.removeItem(key);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [returnTo]);

  return (
    <MobileMasonryGrid
      items={photos}
      getKey={(photo) => photo.id}
      getItemHeight={(photo) => (photo.width && photo.height ? photo.height / photo.width : 3 / 4)}
      renderItem={(photo) => (
        <Link
          to={`/photos/${photo.id}`}
          state={{ photoIds, returnTo }}
          onClick={() => sessionStorage.setItem(scrollStorageKey(returnTo), String(window.scrollY))}
          className="mobile-grid-item"
          style={{ aspectRatio: photo.width && photo.height ? `${photo.width}/${photo.height}` : "4/3" }}
        >
          <img
            src={api.photos.thumbnailUrl(projectId, photo.id, photo.updated_at)}
            alt={photo.file_name}
            loading={priorityPhotoIds?.has(photo.id) ? "eager" : "lazy"}
            fetchPriority={priorityPhotoIds?.has(photo.id) ? "high" : "auto"}
            decoding="async"
            className="block h-full w-full object-cover"
          />
        </Link>
      )}
    />
  );
}
