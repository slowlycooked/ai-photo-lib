import { useState } from "react";
import { ChevronDownIcon, ChevronRightIcon, XIcon } from "lucide-react";
import { useFolderTree } from "@/hooks/useFolders";
import { FolderNode, FolderScope } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FolderTreeSidebarProps {
  projectId?: number | null;
  selectedFolderId?: number | null;
  folderScope?: FolderScope;
  onSelectFolder?: (folderId: number, scope: FolderScope) => void;
  onClearFolder?: () => void;
  isCollapsed?: boolean;
  onToggleCollapsed?: (collapsed: boolean) => void;
}

interface FolderNodeState {
  [folderId: number]: boolean; // expanded state
}

export function FolderTreeSidebar({
  projectId,
  selectedFolderId,
  folderScope = "subtree",
  onSelectFolder,
  onClearFolder,
  isCollapsed = false,
  onToggleCollapsed,
}: FolderTreeSidebarProps) {
  const { data, isLoading } = useFolderTree(projectId);
  const [expandedFolders, setExpandedFolders] = useState<FolderNodeState>({});

  const toggleExpanded = (folderId: number) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [folderId]: !prev[folderId],
    }));
  };

  const handleSelectFolder = (folderId: number) => {
    onSelectFolder?.(folderId, folderScope);
  };

  const renderFolderNode = (node: FolderNode, depth: number = 0) => {
    if (!node) return null;
    const isExpanded = node.id && expandedFolders[node.id];
    const isSelected = node.id === selectedFolderId;
    const hasChildren = node.children && node.children.length > 0;

    return (
      <div key={node.id}>
        <div
          className={cn(
            "flex items-center px-2 py-1 text-sm cursor-pointer hover:bg-gray-100 rounded",
            isSelected && "bg-blue-100 text-blue-900 font-semibold"
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          {hasChildren && (
            <button
              onClick={() => toggleExpanded(node.id)}
              className="mr-1 p-0 w-5 h-5 flex items-center justify-center hover:bg-gray-200 rounded"
            >
              {isExpanded ? (
                <ChevronDownIcon size={16} />
              ) : (
                <ChevronRightIcon size={16} />
              )}
            </button>
          )}
          {!hasChildren && <div className="w-5" />}
          
          <button
            onClick={() => handleSelectFolder(node.id)}
            className="flex-1 text-left truncate"
          >
            {node.name || "全部照片"}
          </button>
          
          <span className="text-gray-500 text-xs ml-2 whitespace-nowrap">
            {node.photo_count_recursive}
          </span>
        </div>
        
        {isExpanded && hasChildren && (
          <div>
            {node.children!.map((child) => renderFolderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  if (isCollapsed) {
    return (
      <button
        onClick={() => onToggleCollapsed?.(false)}
        className="px-2 py-2 text-sm font-semibold hover:bg-gray-100 rounded"
      >
        📁
      </button>
    );
  }

  return (
    <div className="flex flex-col h-full border-r border-gray-200">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <h3 className="text-sm font-semibold">文件夹</h3>
        <button
          onClick={() => onToggleCollapsed?.(true)}
          className="p-1 hover:bg-gray-100 rounded"
          title="折叠"
        >
          <XIcon size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="px-3 py-2 text-sm text-gray-500">加载中...</div>
        ) : data?.root ? (
          <div className="p-2">
            {renderFolderNode(data.root)}
            {selectedFolderId && (
              <button
                onClick={() => onClearFolder?.()}
                className="w-full mt-2 px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded border border-blue-200"
              >
                清除筛选
              </button>
            )}
          </div>
        ) : (
          <div className="px-3 py-2 text-sm text-gray-500">无文件夹数据</div>
        )}
      </div>
    </div>
  );
}
