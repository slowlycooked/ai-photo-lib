import { useSearchParams } from "react-router-dom";
import { TimelineGrid } from "@/components/TimelineGrid";
import { PhotoBrowseLayout } from "@/components/PhotoBrowseLayout";
import { useProjectContext } from "@/contexts/ProjectContext";
import type { FolderScope } from "@/api";

export function PhotosPage() {
  const { currentProjectId } = useProjectContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFolderId = searchParams.get("folder_id") ? Number(searchParams.get("folder_id")) : null;
  const folderScope = (searchParams.get("folder_scope") ?? "subtree") as FolderScope;

  const handleSelectFolder = (folderId: number, scope: FolderScope) => {
    setSearchParams({
      folder_id: folderId.toString(),
      folder_scope: scope,
    });
  };

  const handleClearFolder = () => {
    setSearchParams({});
  };

  return (
    <main className="w-full px-4 py-6 sm:px-6">
      <div>
        <PhotoBrowseLayout
          projectId={currentProjectId}
          selectedFolderId={selectedFolderId}
          folderScope={folderScope}
          onSelectFolder={handleSelectFolder}
          onClearFolder={handleClearFolder}
        >
          <TimelineGrid 
            projectId={currentProjectId} 
            folderId={selectedFolderId}
            folderScope={folderScope}
          />
        </PhotoBrowseLayout>
      </div>
    </main>
  );
}
