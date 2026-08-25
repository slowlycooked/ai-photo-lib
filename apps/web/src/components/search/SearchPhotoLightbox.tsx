import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { api } from "@/api";
import type { SearchResultItem } from "@/api/types";
import { queryKeys } from "@/api/queryKeys";
import { PhotoDetailModal } from "@/components/photo-card/PhotoDetailModal";

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
  const { data: photo, isLoading, isError } = useQuery({
    queryKey: queryKeys.projectPhotoDetail(projectId!, item.photo_id),
    queryFn: () => api.projectPhotos.get(projectId!, item.photo_id),
    enabled: projectId != null,
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 text-white">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-3 text-body-sm">正在加载照片详情…</span>
      </div>
    );
  }

  if (isError || !photo) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
        onClick={onClose}
      >
        <div
          className="flex max-w-sm flex-col items-center gap-3 rounded-lg bg-canvas p-6 text-center shadow-2xl"
          onClick={(event) => event.stopPropagation()}
        >
          <AlertCircle className="h-8 w-8 text-danger" />
          <p className="text-body-sm text-ink">无法加载照片详情</p>
          <button type="button" className="btn-secondary" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    );
  }

  return (
    <PhotoDetailModal
      photo={photo}
      onClose={onClose}
      onDeleted={() => onDeleted?.()}
    />
  );
}
