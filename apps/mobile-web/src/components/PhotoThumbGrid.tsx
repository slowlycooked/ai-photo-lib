import { api, type Photo } from "@/api";
import { MobileMasonryGrid } from "@/components/MobileMasonryGrid";
import { Link } from "react-router-dom";

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
  return (
    <MobileMasonryGrid
      items={photos}
      getKey={(photo) => photo.id}
      getItemHeight={(photo) => (photo.width && photo.height ? photo.height / photo.width : 3 / 4)}
      renderItem={(photo) => (
        <Link
          to={`/photos/${photo.id}`}
          state={{ photoIds }}
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
