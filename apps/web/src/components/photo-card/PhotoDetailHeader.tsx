import { useState } from "react";
import { Download, ImageIcon, Loader2, Trash2, X } from "lucide-react";
import { api, type Photo } from "@/api";

interface PhotoDetailHeaderProps {
  photo: Photo;
  canDelete: boolean;
  deleteOriginal: boolean;
  isDeleting: boolean;
  onClose: () => void;
  onDeleteRecord: () => void;
}

export function PhotoDetailHeader({
  photo,
  canDelete,
  deleteOriginal,
  isDeleting,
  onClose,
  onDeleteRecord,
}: PhotoDetailHeaderProps) {
  const [loaded, setLoaded] = useState(false);
  const projectId = photo.project_id;

  return (
    <div className="relative flex min-h-52 items-center justify-center bg-black">
      {!loaded && (
        <div className="absolute inset-0 flex items-center justify-center">
          <ImageIcon className="w-10 h-10 text-white/50" />
        </div>
      )}
      <img
        src={api.projectPhotos.previewUrl(projectId, photo.id)}
        alt={photo.file_name}
        className="max-h-[70vh] max-w-full object-contain"
        style={{ opacity: loaded ? 1 : 0, transition: "opacity 0.2s" }}
        onLoad={() => setLoaded(true)}
      />
      <button
        onClick={onClose}
        className="absolute top-3 right-3 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center shadow-md hover:bg-black/80 transition-colors"
        aria-label="关闭"
      >
        <X className="w-4 h-4 text-white" />
      </button>
      <a
        href={api.projectPhotos.originalUrl(projectId, photo.id)}
        download={photo.file_name}
        onClick={(e) => e.stopPropagation()}
        className="absolute top-3 right-14 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center shadow-md hover:bg-black/80 transition-colors"
        aria-label="下载原图"
        title="下载原图"
      >
        <Download className="w-4 h-4 text-white" />
      </a>
      {canDelete && (
        <button
          type="button"
          onClick={onDeleteRecord}
          disabled={isDeleting}
          className="absolute top-3 right-24 w-9 h-9 rounded-full bg-black/60 flex items-center justify-center shadow-md hover:bg-black/80 transition-colors disabled:opacity-60"
          aria-label="删除库记录"
          title={deleteOriginal ? "删除库记录、缩略图和本地原图" : "仅删除库记录和缩略图"}
        >
          {isDeleting ? (
            <Loader2 className="w-4 h-4 text-danger animate-spin" />
          ) : (
            <Trash2 className="w-4 h-4 text-danger" />
          )}
        </button>
      )}
    </div>
  );
}
