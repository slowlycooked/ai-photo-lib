import { api, type Photo } from "@/api";
import { Link } from "react-router-dom";

export function PhotoThumbGrid({
  projectId,
  photos,
  photoIds,
}: {
  projectId: number;
  photos: Photo[];
  photoIds: number[];
}) {
  return (
    <div className="mobile-grid">
      {photos.map((photo) => (
        <Link
          key={photo.id}
          to={`/photos/${photo.id}`}
          state={{ photoIds }}
          className="mobile-grid-item"
        >
          <img
            src={api.photos.thumbnailUrl(projectId, photo.id, photo.updated_at)}
            alt={photo.file_name}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        </Link>
      ))}
    </div>
  );
}
