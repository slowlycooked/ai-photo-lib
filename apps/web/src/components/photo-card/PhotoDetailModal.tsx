import { useEffect } from "react";
import type { Photo } from "@/api";
import { useAuth } from "@/contexts/AuthContext";
import { usePhotoDetailModalData } from "@/hooks/usePhotoDetailModalData";
import { PhotoAiSection } from "./PhotoAiSection";
import { PhotoDeletePanel } from "./PhotoDeletePanel";
import { PhotoDetailHeader } from "./PhotoDetailHeader";
import { PhotoFacesSection } from "./PhotoFacesSection";
import { PhotoMetadataSection } from "./PhotoMetadataSection";
import { canManageProjects } from "@/lib/permissions";

interface PhotoDetailModalProps {
  photo: Photo;
  onClose: () => void;
  onDeleted?: (photoId: number) => void;
}

export function PhotoDetailModal({ photo, onClose, onDeleted }: PhotoDetailModalProps) {
  const auth = useAuth();
  const canDeletePhoto = canManageProjects(auth.session);
  const isVideo = photo.mime_type?.startsWith("video/") ?? false;
  const {
    aiData,
    aiLoading,
    deleteMessage,
    deleteOriginal,
    deletePhotoMutation,
    detail,
    faceMessage,
    faceScanMutation,
    facesData,
    facesError,
    facesLoading,
    handleDeleteRecord,
    projectId,
    refreshFaces,
    setDeleteOriginal,
  } = usePhotoDetailModalData({ photo, onClose, onDeleted });

  useEffect(() => {
    const scrollY = window.scrollY;
    const previousOverflow = document.body.style.overflow;
    const previouslyFocused = document.activeElement;

    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      window.scrollTo({ top: scrollY, left: 0, behavior: "auto" });
      if (previouslyFocused instanceof HTMLElement) {
        previouslyFocused.focus({ preventScroll: true });
      }
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.85)" }}
      onClick={onClose}
    >
      <div
        className="bg-canvas rounded-lg shadow-2xl max-w-5xl w-full overflow-hidden overflow-y-auto"
        style={{ maxHeight: "90vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        <PhotoDetailHeader
          photo={photo}
          canDelete={canDeletePhoto}
          deleteOriginal={deleteOriginal}
          isDeleting={deletePhotoMutation.isPending}
          onClose={onClose}
          onDeleteRecord={handleDeleteRecord}
        />

        <div className="p-6 space-y-3">
          <h2 className="text-heading-md font-semibold text-ink truncate">{photo.file_name}</h2>

          <PhotoMetadataSection photo={photo} detail={detail} />

          <div className="flex items-center gap-2 pt-1">
            <span
              className={[
                "px-3 py-1 rounded-full text-caption-md font-semibold",
                photo.status === "ai_indexed"
                  ? "bg-blue-100 text-blue-800"
                  : photo.status === "indexed"
                    ? "bg-green-100 text-green-800"
                    : photo.status === "pending"
                      ? "bg-secondary-bg text-mute"
                      : "bg-amber-100 text-amber-800",
              ].join(" ")}
            >
              {photo.status === "ai_indexed"
                ? "AI 已分析"
                : photo.status === "indexed"
                  ? "已索引"
                  : photo.status === "pending"
                    ? "待分析"
                    : photo.status}
            </span>
          </div>

          <PhotoAiSection aiData={aiData} isLoading={aiLoading} />

          <div className="pt-2 border-t border-hairline">
            {canDeletePhoto && (
              <PhotoDeletePanel
                deleteOriginal={deleteOriginal}
                setDeleteOriginal={setDeleteOriginal}
                deleteMessage={deleteMessage}
                deletePhotoMutation={deletePhotoMutation}
                onDeleteRecord={handleDeleteRecord}
              />
            )}
            {!isVideo && (
              <PhotoFacesSection
                projectId={projectId}
                photoId={photo.id}
                facesData={facesData}
                facesLoading={facesLoading}
                facesError={facesError}
                faceMessage={faceMessage}
                faceScanMutation={faceScanMutation}
                refreshFaces={refreshFaces}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
