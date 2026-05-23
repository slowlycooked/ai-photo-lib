import { ReactNode, useState } from "react";
import { FolderTreeSidebar } from "./FolderTreeSidebar";
import { FolderScope } from "@/api";

interface PhotoBrowseLayoutProps {
  projectId?: number | null;
  selectedFolderId?: number | null;
  folderScope?: FolderScope;
  onSelectFolder?: (folderId: number, scope: FolderScope) => void;
  onClearFolder?: () => void;
  children?: ReactNode;
}

export function PhotoBrowseLayout({
  projectId,
  selectedFolderId,
  folderScope = "subtree",
  onSelectFolder,
  onClearFolder,
  children,
}: PhotoBrowseLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="flex h-full gap-4">
      {/* 左侧：文件夹树 */}
      <div
        className={`transition-all duration-200 ${
          sidebarCollapsed ? "w-12" : "w-64"
        } flex-shrink-0 border-r border-gray-200 overflow-hidden`}
      >
        <FolderTreeSidebar
          projectId={projectId}
          selectedFolderId={selectedFolderId}
          folderScope={folderScope}
          onSelectFolder={onSelectFolder}
          onClearFolder={onClearFolder}
          isCollapsed={sidebarCollapsed}
          onToggleCollapsed={setSidebarCollapsed}
        />
      </div>

      {/* 右侧：照片和时间线 */}
      <div className="flex-1 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
