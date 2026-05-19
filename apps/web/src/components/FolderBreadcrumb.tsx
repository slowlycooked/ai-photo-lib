import { FolderBreadcrumbItem } from "@/lib/api";
import { ChevronRightIcon } from "lucide-react";

interface FolderBreadcrumbProps {
  items: FolderBreadcrumbItem[];
  onSelectFolder?: (folderId: number) => void;
}

export function FolderBreadcrumb({ items, onSelectFolder }: FolderBreadcrumbProps) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-1 text-sm text-gray-600 mb-4">
      {items.map((item, index) => (
        <div key={item.id} className="flex items-center gap-1">
          <button
            onClick={() => onSelectFolder?.(item.id)}
            className="text-blue-600 hover:text-blue-800 hover:underline truncate max-w-xs"
            title={item.relative_path || "全部照片"}
          >
            {item.name || "全部照片"}
          </button>
          {index < items.length - 1 && <ChevronRightIcon size={16} />}
        </div>
      ))}
    </div>
  );
}
