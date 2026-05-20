import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ScanPanel } from "@/components/ScanPanel";
import { AIPanel } from "@/components/AIPanel";
import { TimelineGrid } from "@/components/TimelineGrid";
import { PhotoBrowseLayout } from "@/components/PhotoBrowseLayout";
import { useScanStatus, useStartScan } from "@/hooks/useScan";
import { useProjectContext } from "@/contexts/ProjectContext";
import type { FolderScope } from "@/lib/api";

export function PhotosPage() {
  const { currentProjectId } = useProjectContext();
  const { data: scanStatus, isLoading: scanLoading } = useScanStatus(currentProjectId);
  const { mutate: startScan, isPending, error: scanError } = useStartScan(currentProjectId);
  
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
    <main className="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-5">
      <div className="space-y-5">
        <ScanPanel
          status={scanStatus}
          isLoading={scanLoading}
          onStart={() => startScan()}
          isPending={isPending}
          mutationError={scanError?.message ?? null}
        />
        {currentProjectId != null ? (
          <AIPanel projectId={currentProjectId} />
        ) : null}
      </div>
      
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
