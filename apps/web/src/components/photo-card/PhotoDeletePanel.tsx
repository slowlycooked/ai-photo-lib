import type { UseMutationResult } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import type { PhotoDeleteResponse } from "@/api/types";

interface PhotoDeletePanelProps {
  deleteOriginal: boolean;
  setDeleteOriginal: (value: boolean) => void;
  deleteMessage: string | null;
  deletePhotoMutation: UseMutationResult<PhotoDeleteResponse, Error, void>;
  onDeleteRecord: () => void;
}

export function PhotoDeletePanel({
  deleteOriginal,
  setDeleteOriginal,
  deleteMessage,
  deletePhotoMutation,
  onDeleteRecord,
}: PhotoDeletePanelProps) {
  return (
    <div className="mb-3 rounded-md border border-danger/30 bg-danger/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-body-sm font-semibold text-danger">手动清理</p>
          <p className="text-caption-sm text-mute mt-1">
            默认仅删除库记录与缩略图，不会直接操作本地原图。
          </p>
        </div>
        <button
          type="button"
          onClick={onDeleteRecord}
          disabled={deletePhotoMutation.isPending}
          className="inline-flex items-center gap-1.5 rounded-md border border-danger/40 px-3 py-1.5 text-body-sm text-danger hover:bg-danger/10 disabled:opacity-60"
        >
          {deletePhotoMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Trash2 className="w-3.5 h-3.5" />
          )}
          删除记录
        </button>
      </div>
      <label className="mt-2 flex items-center gap-2 text-caption-sm text-ink">
        <input
          type="checkbox"
          checked={deleteOriginal}
          onChange={(e) => setDeleteOriginal(e.target.checked)}
          className="h-4 w-4"
        />
        将原图写入 NAS 垃圾箱清单（应用不直接删除原图）
      </label>
      {deleteMessage && <p className="mt-2 text-caption-sm text-mute">{deleteMessage}</p>}
    </div>
  );
}
