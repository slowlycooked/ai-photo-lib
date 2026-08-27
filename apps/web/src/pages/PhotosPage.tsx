import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ImageOff, Loader2 } from "lucide-react";
import { TimelineGrid } from "@/components/TimelineGrid";
import { PhotoBrowseLayout } from "@/components/PhotoBrowseLayout";
import { useProjectContext } from "@/contexts/ProjectContext";
import type { FolderScope } from "@/api";
import { api } from "@/api";
import { queryKeys } from "@/api/queryKeys";

export function PhotosPage() {
  const { currentProjectId } = useProjectContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFolderId = searchParams.get("folder_id") ? Number(searchParams.get("folder_id")) : null;
  const folderScope = (searchParams.get("folder_scope") ?? "subtree") as FolderScope;
  const requestedPhotoId = Number(searchParams.get("photo_id"));
  const targetPhotoId = Number.isInteger(requestedPhotoId) && requestedPhotoId > 0
    ? requestedPhotoId
    : null;
  const locationQuery = useQuery({
    queryKey: queryKeys.projectPhotoLocation(currentProjectId, targetPhotoId),
    queryFn: () => api.projectPhotos.locate(currentProjectId!, targetPhotoId!),
    enabled: currentProjectId != null && targetPhotoId != null,
  });
  const location = locationQuery.data;
  const effectiveFolderId = targetPhotoId != null && location
    ? location.folder_id
    : selectedFolderId;
  const effectiveFolderScope: FolderScope = targetPhotoId != null && location
    ? "direct"
    : folderScope;

  const handleSelectFolder = (folderId: number, scope: FolderScope) => {
    setSearchParams({
      folder_id: folderId.toString(),
      folder_scope: scope,
    });
  };

  const handleClearFolder = () => {
    setSearchParams({});
  };

  const handleClearTarget = () => {
    const next = new URLSearchParams();
    if (location?.folder_id != null) {
      next.set("folder_id", String(location.folder_id));
      next.set("folder_scope", "direct");
    }
    setSearchParams(next);
  };

  return (
    <main className="w-full px-4 py-6 sm:px-6">
      <div>
        <PhotoBrowseLayout
          projectId={currentProjectId}
          selectedFolderId={effectiveFolderId}
          folderScope={effectiveFolderScope}
          onSelectFolder={handleSelectFolder}
          onClearFolder={handleClearFolder}
        >
          {targetPhotoId != null && locationQuery.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-24 text-mute">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-body-sm">正在定位照片在图库中的位置…</span>
            </div>
          ) : targetPhotoId != null && locationQuery.isError ? (
            <div className="flex flex-col items-center justify-center gap-3 py-24 text-mute">
              <ImageOff className="h-8 w-8" />
              <p className="text-body-sm">无法定位这张照片，它可能已从图库中移除</p>
              <button type="button" onClick={handleClearTarget} className="text-primary hover:text-primary-pressed">
                返回图库
              </button>
            </div>
          ) : (
            <TimelineGrid
              projectId={currentProjectId}
              folderId={effectiveFolderId}
              folderScope={effectiveFolderScope}
              initialPage={location?.page}
              targetPhotoId={targetPhotoId}
              targetAvailable={location?.is_browsable}
              targetFolderPath={location?.folder_path}
              onClearTarget={handleClearTarget}
            />
          )}
        </PhotoBrowseLayout>
      </div>
    </main>
  );
}
