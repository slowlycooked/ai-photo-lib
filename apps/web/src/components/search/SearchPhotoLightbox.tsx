import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Trash2, X } from "lucide-react";
import { api } from "@/api";
import type { SearchResultItem } from "@/api/types";
import { queryKeys } from "@/api/queryKeys";
import { formatLocationSummary } from "@/lib/utils";

interface SearchPhotoLightboxProps {
  item: SearchResultItem;
  projectId: number | null | undefined;
  onClose: () => void;
  onDeleted?: () => void;
}

export function SearchPhotoLightbox({
  item,
  projectId,
  onClose,
  onDeleted,
}: SearchPhotoLightboxProps) {
  const [imgLoaded, setImgLoaded] = useState(false);
  const [deleteOriginal, setDeleteOriginal] = useState(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const locationSummary = formatLocationSummary(item, { short: true });
  const takenAtLabel = item.taken_at
    ? new Date(item.taken_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const previewUrl =
    projectId != null
      ? api.projectPhotos.previewUrl(projectId, item.photo_id)
      : item.thumbnail_url;

  const downloadUrl =
    projectId != null
      ? api.projectPhotos.originalUrl(projectId, item.photo_id)
      : undefined;

  const deletePhotoMutation = useMutation({
    mutationFn: () => api.projectPhotos.deleteRecord(projectId!, item.photo_id, deleteOriginal),
    onSuccess: () => {
      setDeleteMessage(deleteOriginal ? "已删除库记录、缩略图和本地原图" : "已删除库记录和缩略图");
      if (projectId != null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.photosBase(projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.timeline(projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
      }
      queryClient.invalidateQueries({ queryKey: ["search"] });
      onDeleted?.();
      onClose();
    },
    onError: (error: Error) => setDeleteMessage(`删除失败：${error.message}`),
  });

  function handleDeleteRecord() {
    if (projectId == null) return;
    const actionText = deleteOriginal ? "删除库记录、缩略图并尝试删除本地原图" : "仅删除库记录和缩略图";
    if (!window.confirm(`确认${actionText}吗？`)) {
      return;
    }
    deletePhotoMutation.mutate();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.85)" }}
      onClick={onClose}
    >
      <div
        className="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="absolute top-3 right-3 flex gap-2 z-10">
          {downloadUrl && (
            <a
              href={downloadUrl}
              download={item.file_name}
              onClick={(e) => e.stopPropagation()}
              className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
              aria-label="下载原图"
              title="下载原图"
            >
              <Download className="w-4 h-4 text-white" />
            </a>
          )}
          {projectId != null && (
            <button
              type="button"
              onClick={handleDeleteRecord}
              disabled={deletePhotoMutation.isPending}
              className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors disabled:opacity-60"
              aria-label="删除库记录"
              title={deleteOriginal ? "删除库记录、缩略图和本地原图" : "仅删除库记录和缩略图"}
            >
              {deletePhotoMutation.isPending ? (
                <Loader2 className="w-4 h-4 text-red-300 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4 text-red-300" />
              )}
            </button>
          )}
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors"
            aria-label="关闭预览"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {!imgLoaded && (
          <div className="flex items-center justify-center" style={{ minWidth: 200, minHeight: 200 }}>
            <Loader2 className="w-8 h-8 animate-spin text-white/60" />
          </div>
        )}
        <img
          src={previewUrl}
          alt={item.file_name}
          className="rounded-md object-contain shadow-2xl"
          style={{
            maxWidth: "90vw",
            maxHeight: "80vh",
            opacity: imgLoaded ? 1 : 0,
            transition: "opacity 0.2s",
          }}
          onLoad={() => setImgLoaded(true)}
        />

        {(item.caption || item.file_name) && (
          <div className="mt-3 px-4 py-2 rounded-md bg-black/60 text-white text-sm max-w-lg text-center space-y-1">
            {item.caption && <p className="line-clamp-2">{item.caption}</p>}
            {(locationSummary || takenAtLabel) && (
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-white/80">
                {locationSummary && <span>{locationSummary}</span>}
                {takenAtLabel && <span>{takenAtLabel}</span>}
              </div>
            )}
            <p className="text-white/60 text-xs truncate">{item.file_name}</p>
            {projectId != null && (
              <div className="border-t border-white/15 pt-2 mt-2 space-y-2 text-left">
                <label className="flex items-center gap-2 text-xs text-white/85">
                  <input
                    type="checkbox"
                    checked={deleteOriginal}
                    onChange={(e) => setDeleteOriginal(e.target.checked)}
                    className="h-3.5 w-3.5"
                  />
                  同时删除本地原图（hard copy 删除）
                </label>
                <p className="text-[11px] text-white/65">默认只清理库记录与缩略图。</p>
                {deleteMessage && <p className="text-[11px] text-white/70">{deleteMessage}</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
